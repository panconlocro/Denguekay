"""Compara individualmente las 15 fracciones sociodemográficas en XGBoost.

Cada fracción se añade sola a la misma base de seis predictores. Se ensayan
su referencia censal fija de 2017 y su serie anual reconstruida. La selección
usa solo temporadas de validación; la serie anual es retrospectiva porque
2018–2024 se interpoló usando el extremo de 2025.
"""

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd
from xgboost import __version__ as XGBOOST_VERSION

from src.eda.carga import cargar_integrado
from src.modeling.ablacion_espacial import elegir_variante_f1
from src.modeling.contrato_xgboost import auditar_traspaso
from src.modeling.evaluate import seleccionar_umbral_f1
from src.modeling.features import FECHA_SOCIO_2017
from src.modeling.sociodemografia import referencia_2017
from src.modeling.train import (
    ANIO_PRUEBA_SENSIBILIDAD, MINIMO_CASOS_BROTE, PARAMETROS_BASE,
    SEMANA_INICIO_TEMPORADA, TEMPORADA_PRUEBA_PRINCIPAL,
    TEMPORADAS_VALIDACION, columnas_variantes, evaluar_fold,
    predecir_fold, preparar_gold, separar_anio_calendario,
    separar_temporada,
)
from src.processing.socio_interpolacion import SOCIO_COLUMNS
from src.modeling.seguimiento_mlflow import registrar_o_avisar
from src.utils.paths import DOCS, GOLD, MODELS, SILVER_INTEGRADO
from src.validation.contrato_pronostico import CLAVE
from src.validation.calidad_gx import validar_entradas_modelado


FRACCIONES = tuple(c for c in SOCIO_COLUMNS if c.startswith("fraccion_"))
if len(FRACCIONES) != 15:
    raise ValueError("El contrato sociodemográfico requiere 15 fracciones")


def variantes_fracciones(horizonte: int) -> dict[str, list[str]]:
    """Predefine base y 30 adiciones individuales sin mirar las etiquetas."""
    base = columnas_variantes(horizonte)["historia_4_mas_2"]
    return {
        "base_6": base,
        **{f"fija__{c}": [*base, f"{c}_2017"] for c in FRACCIONES},
        **{f"anual__{c}": [*base, f"{c}_anual"] for c in FRACCIONES},
    }


def preparar_fracciones(
    gold: pd.DataFrame, referencia: pd.DataFrame, horizonte: int,
) -> tuple[pd.DataFrame, int]:
    """Anexa las 12 fracciones fijas ausentes de gold y valida todas las filas.

    Gold ya contiene tres fracciones fijas. Se comprueban contra la referencia
    de 2017 antes de añadir las demás por UBIGEO; nunca se unen por nombre.
    """
    datos, excluidas = preparar_gold(gold, horizonte)
    columnas_ref = ["ubigeo", *FRACCIONES]
    if not set(columnas_ref).issubset(referencia) or referencia.ubigeo.duplicated().any():
        raise ValueError("Referencia censal incompleta o con UBIGEO duplicado")
    ref = referencia[columnas_ref].rename(columns={c: f"{c}_2017" for c in FRACCIONES})
    presentes = [c for c in ref if c in datos and c != "ubigeo"]
    comparar = datos[["ubigeo", *presentes]].merge(
        ref[["ubigeo", *presentes]], on="ubigeo", how="left",
        suffixes=("_gold", "_censo"), validate="many_to_one", sort=False)
    if len(comparar) != len(datos):
        raise ValueError("La referencia censal cambió el número de filas")
    for c in presentes:
        a = pd.to_numeric(comparar[f"{c}_gold"], errors="raise").to_numpy(float)
        b = pd.to_numeric(comparar[f"{c}_censo"], errors="raise").to_numpy(float)
        if not np.isfinite(a).all() or not np.isfinite(b).all() or not np.allclose(a, b, rtol=0, atol=1e-10):
            raise ValueError(f"Gold y censo 2017 difieren para {c}")
    nuevas = [c for c in ref if c not in datos and c != "ubigeo"]
    salida = datos.merge(ref[["ubigeo", *nuevas]], on="ubigeo", how="left",
                         validate="many_to_one", sort=False)
    if len(salida) != len(datos) or not np.array_equal(
            salida.semana_inicio.to_numpy(), datos.semana_inicio.to_numpy()):
        raise ValueError("El cruce censal cambió filas u orden temporal")
    variantes = variantes_fracciones(horizonte)
    columnas = sorted({c for cols in variantes.values() for c in cols})
    faltan = set(columnas) - set(salida)
    if faltan:
        raise ValueError(f"Faltan fracciones de gold o censo: {sorted(faltan)}")
    for c in columnas:
        salida[c] = pd.to_numeric(salida[c], errors="raise")
    if salida[columnas].isna().any().any() or not np.isfinite(salida[columnas].to_numpy(float)).all():
        raise ValueError("La matriz de fracciones tiene nulos o valores no finitos")
    fracciones = [c for c in columnas if c.startswith("fraccion_")]
    if not salida[fracciones].ge(0).all().all() or not salida[fracciones].le(1).all().all():
        raise ValueError("Una fracción está fuera de [0, 1]")
    return salida, excluidas


def opciones_grupo(variantes: dict[str, list[str]], grupo: str) -> dict[str, list[str]]:
    """Separa la referencia fija del análisis anual retrospectivo."""
    if grupo not in ("fija", "anual"):
        raise ValueError("Grupo sociodemográfico desconocido")
    opciones = {k: v for k, v in variantes.items()
                if k == "base_6" or k.startswith(f"{grupo}__")}
    if len(opciones) != 16:
        raise ValueError("Se esperan 15 fracciones individuales y la base")
    return opciones


def ganadora_por_temporada(
    resultados: dict[str, dict], opciones: dict[str, list[str]], enfoque: str,
) -> dict[str, str]:
    """Muestra si la misma candidata gana en cada temporada de validación."""
    ruta = "alerta_derivada" if enfoque == "regresion" else "alerta_directa"
    bloques = [f"temporada_{t}" for t in TEMPORADAS_VALIDACION]
    salida = {}
    for bloque in bloques:
        por_variante = {}
        for nombre in opciones:
            folds = resultados[nombre]["folds_validacion"]
            actual = [f for f in folds if f["bloque"] == bloque and f["tipo"] == "validacion"]
            if len(actual) != 1:
                raise ValueError(f"Falta fold de validación {bloque} en {nombre}")
            por_variante[nombre] = actual[0][enfoque][ruta]["f1"]
        salida[bloque] = max(opciones, key=lambda n: (
            por_variante[n], -len(opciones[n]), n))
    return salida


def ejecutar_ablacion_fracciones(
    *, silver_path: Path = SILVER_INTEGRADO, gold_dir: Path = GOLD,
    salida_dir: Path = MODELS / "experimentos" / "ablacion_fracciones",
    metricas_path: Path = DOCS / "modeling" / "metricas" / "ablacion_fracciones.json",
    auditar: bool = True, validar_datos: bool = True,
    registrar_mlflow: bool = True,
) -> dict:
    """Compara 15 fracciones fijas y anuales para casos y alerta, por h."""
    silver_path, gold_dir, salida_dir, metricas_path = map(
        Path, (silver_path, gold_dir, salida_dir, metricas_path))
    if auditar:
        auditar_traspaso(silver_path=silver_path, gold_dir=gold_dir)
    # Calidad de datos (Great Expectations) antes de entrenar; falla si gold/silver
    # incumplen su suite. El resumen se adjunta al run de MLflow.
    calidad = (validar_entradas_modelado(gold_dir=gold_dir, silver_path=silver_path)
               if validar_datos else None)
    silver = cargar_integrado(silver_path)
    referencia = referencia_2017(silver)
    manifiesto_path = gold_dir / "manifest_fase6.json"
    manifiesto = json.loads(manifiesto_path.read_text(encoding="utf-8"))
    if manifiesto["regla_brote"]["minimo_casos"] != MINIMO_CASOS_BROTE:
        raise ValueError("El mínimo de brote del manifiesto difiere del experimento")
    reporte = {
        "experimento": "ablacion_individual_fracciones_xgboost",
        "fracciones": list(FRACCIONES),
        "validacion": list(TEMPORADAS_VALIDACION),
        "prueba_principal": f"temporada_{TEMPORADA_PRUEBA_PRINCIPAL}",
        "prueba_sensibilidad": f"calendario_{ANIO_PRUEBA_SENSIBILIDAD}",
        "criterio": "F1 medio de validación por temporada; empate: menos columnas",
        "umbral_clasificacion": "máximo F1 agregado en validación por variante; empate: umbral mayor",
        "fecha_disponibilidad_fija_supuesta": FECHA_SOCIO_2017,
        "linaje_anual": "fracciones 2018-2024 interpoladas con extremo de 2025; comparación retrospectiva",
        "nota_multiplicidad": "30 candidatas individuales en tres temporadas; los máximos de validación son exploratorios",
        "nota_pruebas": "2024/2025 ya se inspeccionaron; no se usan para elegir variables",
        "semana_inicio_temporada": SEMANA_INICIO_TEMPORADA,
        "parametros": PARAMETROS_BASE,
        "version_xgboost": XGBOOST_VERSION,
        "sha256_manifest_gold": hashlib.sha256(manifiesto_path.read_bytes()).hexdigest(),
        "sha256_silver": hashlib.sha256(silver_path.read_bytes()).hexdigest(),
        "horizontes": {},
    }
    modelos_guardar = []
    pred_validacion = []
    pred_prueba = []
    for h in (2, 4):
        archivo = gold_dir / f"{silver_path.stem}_h{h}_gold.csv"
        gold = pd.read_csv(archivo, dtype={"ubigeo": "string"},
                           parse_dates=["semana_inicio", "origen_inicio", "origen_cierre"])
        datos, excluidas = preparar_fracciones(gold, referencia, h)
        variantes = variantes_fracciones(h)
        bloque_h = {
            "archivo_gold": archivo.name,
            "sha256_gold": hashlib.sha256(archivo.read_bytes()).hexdigest(),
            "filas_gold": len(gold),
            "filas_excluidas_arranque": excluidas,
            "filas_comparadas": len(datos),
            "variantes": {},
        }
        print(f"h={h}: {len(datos)} filas comunes; {len(variantes)} variantes")
        for temporada in TEMPORADAS_VALIDACION:
            train, test, corte = separar_temporada(datos, temporada)
            if test.origen_cierre.lt(pd.Timestamp(FECHA_SOCIO_2017)).any():
                raise ValueError("Referencia censal no disponible en un origen de validación")
            bloque = f"temporada_{temporada}"
            for nombre, columnas in variantes.items():
                pred, _, _ = predecir_fold(train, test, columnas)
                pred[f"casos_lag_{h}"] = test[f"casos_lag_{h}"].to_numpy(float)
                pred["horizonte"] = h
                pred["variante"] = nombre
                pred["bloque"] = bloque
                pred_validacion.append(pred)
                resultado = bloque_h["variantes"].setdefault(
                    nombre, {"columnas": columnas, "seleccion_umbral": None,
                             "folds_validacion": [], "folds_prueba": []})
                resultado.setdefault("_corridas", []).append(
                    (pred, corte, len(train), int(train.brote.sum())))
        for nombre, resultado in bloque_h["variantes"].items():
            corridas = resultado.pop("_corridas")
            validacion = pd.concat([x[0] for x in corridas], ignore_index=True)
            seleccion = seleccionar_umbral_f1(
                validacion.brote.to_numpy(int), validacion.probabilidad_brote.to_numpy(float))
            resultado["seleccion_umbral"] = seleccion
            for pred, corte, n_train, pos_train in corridas:
                fold = evaluar_fold(
                    pred, horizonte=h, variante=nombre, bloque=pred.bloque.iloc[0],
                    tipo="validacion", corte=corte, n_entrenamiento=n_train,
                    umbral_clasificacion=seleccion["umbral"])
                fold["positivos_entrenamiento"] = pos_train
                resultado["folds_validacion"].append(fold)
        grupos = {g: opciones_grupo(variantes, g) for g in ("fija", "anual")}
        elegidas = {g: {enfoque: elegir_variante_f1(
            {k: bloque_h["variantes"][k] for k in opciones}, enfoque, opciones)
            for enfoque in ("regresion", "clasificacion")}
            for g, opciones in grupos.items()}
        estabilidad = {g: {enfoque: ganadora_por_temporada(
            bloque_h["variantes"], opciones, enfoque)
            for enfoque in ("regresion", "clasificacion")}
            for g, opciones in grupos.items()}
        bloque_h["elegidas_solo_validacion"] = elegidas
        bloque_h["ganadora_por_temporada"] = estabilidad
        print(f"  Selección h={h}: {elegidas}")
        for bloque, tipo, separar, periodo in (
            (f"temporada_{TEMPORADA_PRUEBA_PRINCIPAL}", "prueba_principal",
             separar_temporada, TEMPORADA_PRUEBA_PRINCIPAL),
            (f"calendario_{ANIO_PRUEBA_SENSIBILIDAD}", "prueba_sensibilidad",
             separar_anio_calendario, ANIO_PRUEBA_SENSIBILIDAD),
        ):
            train, test, corte = separar(datos, periodo)
            if test.origen_cierre.lt(pd.Timestamp(FECHA_SOCIO_2017)).any():
                raise ValueError("Referencia censal no disponible en un origen de prueba")
            seleccionadas = dict.fromkeys([
                "base_6", *elegidas["fija"].values(), *elegidas["anual"].values()])
            for nombre in seleccionadas:
                pred, regresor, clasificador = predecir_fold(train, test, variantes[nombre])
                pred[f"casos_lag_{h}"] = test[f"casos_lag_{h}"].to_numpy(float)
                pred["horizonte"] = h
                pred["variante"] = nombre
                pred["bloque"] = bloque
                pred_prueba.append(pred)
                umbral = bloque_h["variantes"][nombre]["seleccion_umbral"]["umbral"]
                fold = evaluar_fold(
                    pred, horizonte=h, variante=nombre, bloque=bloque, tipo=tipo,
                    corte=corte, n_entrenamiento=len(train),
                    umbral_clasificacion=umbral)
                fold["positivos_entrenamiento"] = int(train.brote.sum())
                bloque_h["variantes"][nombre]["folds_prueba"].append(fold)
                modelos_guardar.extend([
                    (regresor, f"xgb_h{h}_{nombre}_regresion_{bloque}.json"),
                    (clasificador, f"xgb_h{h}_{nombre}_clasificacion_{bloque}.json"),
                ])
        reporte["horizontes"][str(h)] = bloque_h
    salida_dir.mkdir(parents=True, exist_ok=True)
    metricas_path.parent.mkdir(parents=True, exist_ok=True)
    for modelo, nombre in modelos_guardar:
        modelo.save_model(salida_dir / nombre)
    pd.concat(pred_validacion, ignore_index=True).to_csv(
        salida_dir / "predicciones_validacion.csv.gz", index=False,
        compression="gzip")
    pd.concat(pred_prueba, ignore_index=True).to_csv(
        salida_dir / "predicciones_prueba.csv", index=False)
    metricas_path.write_text(json.dumps(reporte, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if registrar_mlflow:
        registrar_o_avisar(
            "ablacion_fracciones", reporte, metricas_path=metricas_path, salida_dir=salida_dir,
            gold_dir=gold_dir, calidad_datos=calidad)
    return reporte


def main() -> None:
    """Ejecuta ``python -m src.modeling.ablacion_fracciones``."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--silver", type=Path, default=SILVER_INTEGRADO)
    parser.add_argument("--gold-dir", type=Path, default=GOLD)
    parser.add_argument("--salida-dir", type=Path,
                        default=MODELS / "experimentos" / "ablacion_fracciones")
    parser.add_argument("--metricas", type=Path,
                        default=DOCS / "modeling" / "metricas" / "ablacion_fracciones.json")
    parser.add_argument("--sin-validacion-datos", action="store_true",
                        help="No ejecutar las suites de Great Expectations")
    parser.add_argument("--sin-mlflow", action="store_true",
                        help="No registrar la corrida en MLflow")
    args = parser.parse_args()
    ejecutar_ablacion_fracciones(
        validar_datos=not args.sin_validacion_datos, registrar_mlflow=not args.sin_mlflow,
        silver_path=args.silver, gold_dir=args.gold_dir,
        salida_dir=args.salida_dir, metricas_path=args.metricas)
    print(f"Métricas: {args.metricas}")


if __name__ == "__main__":
    main()
