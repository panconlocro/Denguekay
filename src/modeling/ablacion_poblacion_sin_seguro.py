"""Ablación condicional de población censal y fracción sin seguro de 2017.

Compara cuatro variantes predefinidas sobre las mismas distrito-semanas. No
selecciona un ganador con 2024 ni trata ese bloque ya inspeccionado como test
virgen. La pregunta principal es si sin seguro añade valor sobre población.
"""

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd
from xgboost import __version__ as XGBOOST_VERSION

from src.eda.carga import cargar_integrado
from src.modeling.ablacion_fracciones import preparar_fracciones
from src.modeling.contrato_xgboost import auditar_traspaso
from src.modeling.evaluate import seleccionar_umbral_f1
from src.modeling.features import FECHA_SOCIO_2017
from src.modeling.sociodemografia import referencia_2017
from src.modeling.train import (
    ANIO_PRUEBA_SENSIBILIDAD, MINIMO_CASOS_BROTE, PARAMETROS_BASE,
    SEMANA_INICIO_TEMPORADA, TEMPORADA_PRUEBA_PRINCIPAL,
    TEMPORADAS_VALIDACION, columnas_variantes, evaluar_fold,
    predecir_fold, separar_anio_calendario, separar_temporada,
)
from src.utils.paths import DOCS, GOLD, MODELS, SILVER_INTEGRADO


POBLACION = "log_poblacion_censo_2017"
SIN_SEGURO = "fraccion_sin_seguro_2017"


def variantes_condicionales(horizonte: int) -> dict[str, list[str]]:
    """Define base, cada rasgo fijo y su combinación antes de entrenar."""
    base = columnas_variantes(horizonte)["historia_4_mas_2"]
    return {
        "base_6": base,
        "poblacion_2017": [*base, POBLACION],
        "sin_seguro_2017": [*base, SIN_SEGURO],
        "poblacion_y_sin_seguro_2017": [*base, POBLACION, SIN_SEGURO],
    }


def validar_matriz_condicional(datos: pd.DataFrame, horizonte: int) -> None:
    """Exige las mismas filas completas y sin objetivos para cuatro variantes."""
    variantes = variantes_condicionales(horizonte)
    columnas = sorted({c for cols in variantes.values() for c in cols})
    faltan = set(columnas) - set(datos)
    if faltan:
        raise ValueError(f"Faltan predictores condicionales: {sorted(faltan)}")
    if any(len(cols) != len(set(cols)) for cols in variantes.values()):
        raise ValueError("Una variante contiene predictores duplicados")
    if {"casos_Dengue", "brote", "umbral_brote_casos", "ubigeo"} & set(columnas):
        raise ValueError("La matriz condicional contiene objetivo o identificador")
    for c in columnas:
        datos[c] = pd.to_numeric(datos[c], errors="raise")
    if datos[columnas].isna().any().any() or not np.isfinite(datos[columnas].to_numpy(float)).all():
        raise ValueError("La matriz condicional tiene nulos o valores no finitos")
    if not datos[SIN_SEGURO].between(0, 1).all():
        raise ValueError("La fracción sin seguro está fuera de [0, 1]")


def deltas_por_temporada(
    variantes: dict[str, dict], enfoque: str, *, tipo: str,
) -> dict[str, dict[str, float]]:
    """Calcula diferencias pareadas de F1 para añadir cada rasgo al otro."""
    if enfoque not in ("regresion", "clasificacion") or tipo not in ("validacion", "prueba_principal", "prueba_sensibilidad"):
        raise ValueError("Enfoque o tipo de bloque inválido")
    ruta = "alerta_derivada" if enfoque == "regresion" else "alerta_directa"
    campo = "folds_validacion" if tipo == "validacion" else "folds_prueba"
    por_variante = {}
    for nombre, resultado in variantes.items():
        folds = [f for f in resultado[campo] if f["tipo"] == tipo]
        por_variante[nombre] = {f["bloque"]: f[enfoque][ruta]["f1"] for f in folds}
        if len(por_variante[nombre]) != len(folds):
            raise ValueError("Bloques repetidos en comparación condicional")
    bloques = set(por_variante["base_6"])
    if not bloques or any(set(m) != bloques for m in por_variante.values()):
        raise ValueError("Las variantes no comparten los mismos bloques")
    comparaciones = {
        "poblacion_menos_base": ("poblacion_2017", "base_6"),
        "sin_seguro_menos_base": ("sin_seguro_2017", "base_6"),
        "ambos_menos_poblacion": ("poblacion_y_sin_seguro_2017", "poblacion_2017"),
        "ambos_menos_sin_seguro": ("poblacion_y_sin_seguro_2017", "sin_seguro_2017"),
    }
    return {nombre: {bloque: float(por_variante[a][bloque] - por_variante[b][bloque])
                     for bloque in sorted(bloques)}
            for nombre, (a, b) in comparaciones.items()}


def ejecutar_ablacion_poblacion_sin_seguro(
    *, silver_path: Path = SILVER_INTEGRADO, gold_dir: Path = GOLD,
    salida_dir: Path = MODELS / "experimentos" / "ablacion_poblacion_sin_seguro",
    metricas_path: Path = DOCS / "modeling" / "metricas" / "ablacion_poblacion_sin_seguro.json",
    auditar: bool = True,
) -> dict:
    """Evalúa cuatro modelos fijos en los cortes temporales existentes."""
    silver_path, gold_dir, salida_dir, metricas_path = map(
        Path, (silver_path, gold_dir, salida_dir, metricas_path))
    if auditar:
        auditar_traspaso(silver_path=silver_path, gold_dir=gold_dir)
    silver = cargar_integrado(silver_path)
    referencia = referencia_2017(silver)
    manifiesto_path = gold_dir / "manifest_fase6.json"
    manifiesto = json.loads(manifiesto_path.read_text(encoding="utf-8"))
    if manifiesto["regla_brote"]["minimo_casos"] != MINIMO_CASOS_BROTE:
        raise ValueError("El mínimo de brote del manifiesto difiere del experimento")
    reporte = {
        "experimento": "ablacion_condicional_poblacion_sin_seguro_xgboost",
        "pregunta_principal": "¿fraccion_sin_seguro_2017 mejora frente a base_6 + log_poblacion_censo_2017?",
        "validacion": list(TEMPORADAS_VALIDACION),
        "prueba_principal": f"temporada_{TEMPORADA_PRUEBA_PRINCIPAL}",
        "prueba_sensibilidad": f"calendario_{ANIO_PRUEBA_SENSIBILIDAD}",
        "semana_inicio_temporada": SEMANA_INICIO_TEMPORADA,
        "umbral_clasificacion": "máximo F1 agregado en validación por variante; empate: umbral mayor",
        "fecha_disponibilidad_supuesta": FECHA_SOCIO_2017,
        "nota_interpretacion": "Comparación exploratoria predefinida; 2024 ya había sido inspeccionado",
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
        validar_matriz_condicional(datos, h)
        variantes = variantes_condicionales(h)
        bloque_h = {
            "archivo_gold": archivo.name,
            "sha256_gold": hashlib.sha256(archivo.read_bytes()).hexdigest(),
            "filas_gold": len(gold),
            "filas_excluidas_arranque": excluidas,
            "filas_comparadas": len(datos),
            "variantes": {},
        }
        print(f"h={h}: {len(datos)} filas comunes, cuatro variantes predefinidas")
        for temporada in TEMPORADAS_VALIDACION:
            train, test, corte = separar_temporada(datos, temporada)
            if test.origen_cierre.lt(pd.Timestamp(FECHA_SOCIO_2017)).any():
                raise ValueError("Referencia censal no disponible en validación")
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
            umbral = seleccionar_umbral_f1(
                validacion.brote.to_numpy(int), validacion.probabilidad_brote.to_numpy(float))
            resultado["seleccion_umbral"] = umbral
            for pred, corte, n_train, pos_train in corridas:
                fold = evaluar_fold(
                    pred, horizonte=h, variante=nombre, bloque=pred.bloque.iloc[0],
                    tipo="validacion", corte=corte, n_entrenamiento=n_train,
                    umbral_clasificacion=umbral["umbral"])
                fold["positivos_entrenamiento"] = pos_train
                resultado["folds_validacion"].append(fold)
        for bloque, tipo, separar, periodo in (
            (f"temporada_{TEMPORADA_PRUEBA_PRINCIPAL}", "prueba_principal",
             separar_temporada, TEMPORADA_PRUEBA_PRINCIPAL),
            (f"calendario_{ANIO_PRUEBA_SENSIBILIDAD}", "prueba_sensibilidad",
             separar_anio_calendario, ANIO_PRUEBA_SENSIBILIDAD),
        ):
            train, test, corte = separar(datos, periodo)
            if test.origen_cierre.lt(pd.Timestamp(FECHA_SOCIO_2017)).any():
                raise ValueError("Referencia censal no disponible en prueba")
            for nombre, columnas in variantes.items():
                pred, regresor, clasificador = predecir_fold(train, test, columnas)
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
        bloque_h["deltas_f1"] = {
            enfoque: {tipo: deltas_por_temporada(bloque_h["variantes"], enfoque, tipo=tipo)
                      for tipo in ("validacion", "prueba_principal", "prueba_sensibilidad")}
            for enfoque in ("regresion", "clasificacion")
        }
        reporte["horizontes"][str(h)] = bloque_h
    salida_dir.mkdir(parents=True, exist_ok=True)
    metricas_path.parent.mkdir(parents=True, exist_ok=True)
    for modelo, nombre in modelos_guardar:
        modelo.save_model(salida_dir / nombre)
    pd.concat(pred_validacion, ignore_index=True).to_csv(
        salida_dir / "predicciones_validacion.csv", index=False)
    pd.concat(pred_prueba, ignore_index=True).to_csv(
        salida_dir / "predicciones_prueba.csv", index=False)
    metricas_path.write_text(json.dumps(reporte, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return reporte


def main() -> None:
    """Ejecuta ``python -m src.modeling.ablacion_poblacion_sin_seguro``."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--silver", type=Path, default=SILVER_INTEGRADO)
    parser.add_argument("--gold-dir", type=Path, default=GOLD)
    parser.add_argument("--salida-dir", type=Path,
                        default=MODELS / "experimentos" / "ablacion_poblacion_sin_seguro")
    parser.add_argument("--metricas", type=Path,
                        default=DOCS / "modeling" / "metricas" / "ablacion_poblacion_sin_seguro.json")
    args = parser.parse_args()
    ejecutar_ablacion_poblacion_sin_seguro(
        silver_path=args.silver, gold_dir=args.gold_dir,
        salida_dir=args.salida_dir, metricas_path=args.metricas)
    print(f"Métricas: {args.metricas}")


if __name__ == "__main__":
    main()
