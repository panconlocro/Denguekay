"""Ablación XGBoost de vecinos y jerarquía, sobre el gold ya construido.

Las variantes se comparan con las mismas filas y cortes. La selección usa
únicamente las temporadas de validación; las pruebas se ejecutan después.
"""

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd
from xgboost import __version__ as XGBOOST_VERSION

from src.modeling.contrato_xgboost import auditar_traspaso, familias_predictoras
from src.modeling.evaluate import alertas_desde_conteos, seleccionar_umbral_f1
from src.modeling.train import (
    ANIO_PRUEBA_SENSIBILIDAD, MINIMO_CASOS_BROTE, PARAMETROS_BASE,
    SEMANA_INICIO_TEMPORADA, TEMPORADA_PRUEBA_PRINCIPAL,
    TEMPORADAS_VALIDACION, columnas_variantes, evaluar_fold,
    predecir_fold, preparar_gold, separar_anio_calendario,
    separar_temporada,
)
from src.modeling.seguimiento_mlflow import registrar_o_avisar
from src.utils.paths import DOCS, GOLD, MODELS, SILVER_INTEGRADO
from src.validation.calidad_gx import validar_entradas_modelado


def variantes_espaciales(horizonte: int) -> dict[str, list[str]]:
    """Predefine base, vecinos, jerarquía y ambos sin usar objetivos futuros."""
    familias = familias_predictoras(horizonte)
    base = columnas_variantes(horizonte)["historia_4_mas_2"]
    vecinos = familias["vecinos"]
    jerarquia = familias["jerarquia"]
    return {
        "base_6": base,
        "mas_vecinos": [*base, *vecinos],
        "mas_jerarquia": [*base, *jerarquia],
        "mas_ambos": [*base, *vecinos, *jerarquia],
    }


def validar_matriz_espacial(
    datos: pd.DataFrame, variantes: dict[str, list[str]],
) -> None:
    """Exige idénticas filas completas para las cuatro variantes."""
    columnas = sorted({c for cols in variantes.values() for c in cols})
    faltan = set(columnas) - set(datos)
    if faltan:
        raise ValueError(f"Faltan candidatas espaciales: {sorted(faltan)}")
    for nombre, cols in variantes.items():
        if len(cols) != len(set(cols)):
            raise ValueError(f"{nombre} contiene predictores repetidos")
    if datos[columnas].isna().any().any() or not np.isfinite(datos[columnas].to_numpy(float)).all():
        raise ValueError("Las variantes espaciales tienen nulos o valores no finitos en filas modelables")


def elegir_variante_f1(
    resumen: dict[str, dict], enfoque: str, variantes: dict[str, list[str]],
) -> str:
    """Elige mayor F1 medio de validación; en empate, menos columnas."""
    if enfoque not in ("regresion", "clasificacion"):
        raise ValueError("Enfoque desconocido")
    def puntuacion(nombre: str) -> tuple[float, int, str]:
        folds = resumen[nombre]["folds_validacion"]
        if not folds or any(f["tipo"] != "validacion" for f in folds):
            raise ValueError("La selección solo admite folds de validación")
        ruta = "alerta_derivada" if enfoque == "regresion" else "alerta_directa"
        valores = [f[enfoque][ruta]["f1"] for f in folds]
        if any(v is None or not np.isfinite(v) for v in valores):
            raise ValueError("F1 de validación indefinido")
        return (float(np.mean(valores)), -len(variantes[nombre]), nombre)
    return max(variantes, key=puntuacion)


def _anotar_predicciones(
    pred: pd.DataFrame, prueba: pd.DataFrame, *, horizonte: int,
    variante: str, bloque: str,
) -> pd.DataFrame:
    pred = pred.copy()
    pred[f"casos_lag_{horizonte}"] = prueba[f"casos_lag_{horizonte}"].to_numpy(float)
    pred["horizonte"] = horizonte
    pred["variante"] = variante
    pred["bloque"] = bloque
    return pred


def resumir_silenciosos(
    pred: pd.DataFrame, ubigeos: list[str], umbral_clasificacion: float,
) -> dict[str, int]:
    """Cuenta alertas en distritos sin casos registrados en 2017–2024."""
    filas = pred.loc[pred.ubigeo.isin(ubigeos)]
    alertas_regresion = alertas_desde_conteos(
        filas.casos_predichos.to_numpy(float),
        filas.umbral_brote_casos.to_numpy(float), MINIMO_CASOS_BROTE,
    )
    return {
        "filas": len(filas),
        "positivos_observados": int(filas.brote.sum()),
        "alertas_regresion": int(alertas_regresion.sum()),
        "alertas_clasificacion": int(filas.probabilidad_brote.ge(umbral_clasificacion).sum()),
    }


def ejecutar_ablacion_espacial(
    *, gold_dir: Path = GOLD,
    salida_dir: Path = MODELS / "experimentos" / "ablacion_espacial",
    metricas_path: Path = DOCS / "modeling" / "metricas" / "ablacion_espacial.json",
    auditar: bool = True, validar_datos: bool = True,
    registrar_mlflow: bool = True,
) -> dict:
    """Compara bloques espaciales y prueba solo los elegidos en validación.

    Se mantiene el F1 para escoger el umbral de clasificación y comparar
    variantes de alerta. Cada horizonte y enfoque se selecciona por separado.
    """
    gold_dir, salida_dir, metricas_path = map(Path, (gold_dir, salida_dir, metricas_path))
    if auditar:
        auditar_traspaso(gold_dir=gold_dir)
    # Calidad de datos (Great Expectations) antes de entrenar; falla si gold/silver
    # incumplen su suite. El resumen se adjunta al run de MLflow.
    calidad = (validar_entradas_modelado(gold_dir=gold_dir, silver_path=None)
               if validar_datos else None)
    manifiesto_path = gold_dir / "manifest_fase6.json"
    manifiesto = json.loads(manifiesto_path.read_text(encoding="utf-8"))
    if manifiesto["regla_brote"]["minimo_casos"] != MINIMO_CASOS_BROTE:
        raise ValueError("El mínimo de brote del manifiesto difiere del experimento")
    reporte = {
        "experimento": "ablacion_espacial_xgboost",
        "validacion": list(TEMPORADAS_VALIDACION),
        "prueba_principal": f"temporada_{TEMPORADA_PRUEBA_PRINCIPAL}",
        "prueba_sensibilidad": f"calendario_{ANIO_PRUEBA_SENSIBILIDAD}",
        "semana_inicio_temporada": SEMANA_INICIO_TEMPORADA,
        "criterio": "F1 medio de validación por temporada; empate: menos columnas",
        "umbral_clasificacion": "máximo F1 agregado en validación; empate: umbral mayor",
        "parametros": PARAMETROS_BASE,
        "version_xgboost": XGBOOST_VERSION,
        "sha256_manifest_gold": hashlib.sha256(manifiesto_path.read_bytes()).hexdigest(),
        "nota_pruebas": "2024/2025 ya se inspeccionaron en el experimento base; no se usaron para elegir variables nuevas",
        "horizontes": {},
    }
    modelos_guardar = []
    pred_validacion = []
    pred_prueba = []
    for h in (2, 4):
        archivo = gold_dir / f"{SILVER_INTEGRADO.stem}_h{h}_gold.csv"
        gold = pd.read_csv(archivo, dtype={"ubigeo": "string"},
                           parse_dates=["semana_inicio", "origen_inicio", "origen_cierre"])
        datos, excluidas = preparar_gold(gold, h)
        variantes = variantes_espaciales(h)
        validar_matriz_espacial(datos, variantes)
        historico = gold.loc[gold.anio.lt(2025)].groupby("ubigeo").casos_Dengue.sum()
        silenciosos = sorted(historico.index[historico.eq(0)].astype(str).tolist())
        bloque_h = {
            "archivo_gold": archivo.name,
            "sha256_gold": hashlib.sha256(archivo.read_bytes()).hexdigest(),
            "filas_gold": len(gold),
            "filas_excluidas_arranque": excluidas,
            "filas_comparadas": len(datos),
            "ubigeos_sin_casos_registrados_2017_2024": silenciosos,
            "variantes": {},
        }
        print(f"h={h}: {len(datos)} filas comunes; {excluidas} de arranque excluidas")
        for nombre, columnas in variantes.items():
            corridas = {}
            for temporada in TEMPORADAS_VALIDACION:
                train, test, corte = separar_temporada(datos, temporada)
                pred, _, _ = predecir_fold(train, test, columnas)
                bloque = f"temporada_{temporada}"
                pred = _anotar_predicciones(pred, test, horizonte=h,
                                           variante=nombre, bloque=bloque)
                pred_validacion.append(pred)
                corridas[bloque] = (pred, corte, len(train), int(train.brote.sum()))
            validacion = pd.concat([corridas[f"temporada_{t}"][0]
                                    for t in TEMPORADAS_VALIDACION], ignore_index=True)
            umbral = seleccionar_umbral_f1(
                validacion.brote.to_numpy(int),
                validacion.probabilidad_brote.to_numpy(float),
            )
            folds = []
            for bloque, (pred, corte, n_train, pos_train) in corridas.items():
                fold = evaluar_fold(
                    pred, horizonte=h, variante=nombre, bloque=bloque,
                    tipo="validacion", corte=corte, n_entrenamiento=n_train,
                    umbral_clasificacion=umbral["umbral"],
                )
                fold["positivos_entrenamiento"] = pos_train
                folds.append(fold)
            bloque_h["variantes"][nombre] = {
                "columnas": columnas,
                "seleccion_umbral": umbral,
                "folds_validacion": folds,
                "folds_prueba": [],
            }
            reg_f1 = float(np.mean([f["regresion"]["alerta_derivada"]["f1"] for f in folds]))
            cls_f1 = float(np.mean([f["clasificacion"]["alerta_directa"]["f1"] for f in folds]))
            print(f"  {nombre}: F1 validación reg={reg_f1:.3f}, cls={cls_f1:.3f}")
        elegidas = {
            enfoque: elegir_variante_f1(bloque_h["variantes"], enfoque, variantes)
            for enfoque in ("regresion", "clasificacion")
        }
        bloque_h["elegidas_solo_validacion"] = elegidas
        # La base se conserva como referencia; los modelos elegidos se prueban
        # una sola vez en los bloques fijados desde el experimento inicial.
        for nombre in dict.fromkeys(["base_6", *elegidas.values()]):
            columnas = variantes[nombre]
            for bloque, tipo, periodo in (
                (f"temporada_{TEMPORADA_PRUEBA_PRINCIPAL}", "prueba_principal", TEMPORADA_PRUEBA_PRINCIPAL),
                (f"calendario_{ANIO_PRUEBA_SENSIBILIDAD}", "prueba_sensibilidad", ANIO_PRUEBA_SENSIBILIDAD),
            ):
                if tipo == "prueba_principal":
                    train, test, corte = separar_temporada(datos, periodo)
                else:
                    train, test, corte = separar_anio_calendario(datos, periodo)
                pred, regresor, clasificador = predecir_fold(train, test, columnas)
                pred = _anotar_predicciones(pred, test, horizonte=h,
                                           variante=nombre, bloque=bloque)
                pred_prueba.append(pred)
                umbral = bloque_h["variantes"][nombre]["seleccion_umbral"]["umbral"]
                fold = evaluar_fold(
                    pred, horizonte=h, variante=nombre, bloque=bloque, tipo=tipo,
                    corte=corte, n_entrenamiento=len(train),
                    umbral_clasificacion=umbral,
                )
                fold["positivos_entrenamiento"] = int(train.brote.sum())
                fold["distritos_sin_registros_2017_2024"] = resumir_silenciosos(
                    pred, silenciosos, umbral,
                )
                bloque_h["variantes"][nombre]["folds_prueba"].append(fold)
                modelos_guardar.extend([
                    (regresor, f"xgb_h{h}_{nombre}_regresion_{bloque}.json"),
                    (clasificador, f"xgb_h{h}_{nombre}_clasificacion_{bloque}.json"),
                ])
        reporte["horizontes"][str(h)] = bloque_h
        print(f"  Elegidas h={h}: {elegidas}")
    salida_dir.mkdir(parents=True, exist_ok=True)
    metricas_path.parent.mkdir(parents=True, exist_ok=True)
    for modelo, nombre in modelos_guardar:
        modelo.save_model(salida_dir / nombre)
    pd.concat(pred_validacion, ignore_index=True).to_csv(
        salida_dir / "predicciones_validacion.csv", index=False)
    pd.concat(pred_prueba, ignore_index=True).to_csv(
        salida_dir / "predicciones_prueba.csv", index=False)
    metricas_path.write_text(json.dumps(reporte, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if registrar_mlflow:
        registrar_o_avisar(
            "ablacion_espacial", reporte, metricas_path=metricas_path, salida_dir=salida_dir,
            gold_dir=gold_dir, calidad_datos=calidad)
    return reporte


def main() -> None:
    """Ejecuta la ablación desde ``python -m src.modeling.ablacion_espacial``."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--gold-dir", type=Path, default=GOLD)
    parser.add_argument("--salida-dir", type=Path,
                        default=MODELS / "experimentos" / "ablacion_espacial")
    parser.add_argument("--metricas", type=Path,
                        default=DOCS / "modeling" / "metricas" / "ablacion_espacial.json")
    parser.add_argument("--sin-validacion-datos", action="store_true",
                        help="No ejecutar las suites de Great Expectations")
    parser.add_argument("--sin-mlflow", action="store_true",
                        help="No registrar la corrida en MLflow")
    args = parser.parse_args()
    reporte = ejecutar_ablacion_espacial(
        validar_datos=not args.sin_validacion_datos, registrar_mlflow=not args.sin_mlflow,
        gold_dir=args.gold_dir, salida_dir=args.salida_dir,
        metricas_path=args.metricas,
    )
    print(f"Métricas: {args.metricas}")
    for h, bloque in reporte["horizontes"].items():
        print(f"h={h}: {bloque['elegidas_solo_validacion']}")


if __name__ == "__main__":
    main()
