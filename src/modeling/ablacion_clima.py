"""Ablación XGBoost de clima observado y anomalías ajustadas por fold.

Cada fila representa la semana objetivo. Las climatologías se aprenden solo
con semanas climáticas cerradas antes del primer origen de cada bloque.
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
from src.modeling.clima import ajustar_climatologia, construir_clima
from src.modeling.contrato_xgboost import auditar_traspaso, familias_predictoras
from src.modeling.evaluate import seleccionar_umbral_f1
from src.modeling.train import (
    ANIO_PRUEBA_SENSIBILIDAD, MINIMO_CASOS_BROTE, PARAMETROS_BASE,
    SEMANA_INICIO_TEMPORADA, TEMPORADA_PRUEBA_PRINCIPAL,
    TEMPORADAS_VALIDACION, columnas_variantes, evaluar_fold,
    predecir_fold, preparar_gold, separar_anio_calendario,
    separar_temporada,
)
from src.modeling.seguimiento_mlflow import registrar_o_avisar
from src.utils.paths import DOCS, GOLD, MODELS, SILVER_INTEGRADO
from src.validation.contrato_pronostico import CLAVE
from src.validation.calidad_gx import validar_entradas_modelado


def variantes_climaticas(horizonte: int) -> dict[str, list[str]]:
    """Define cuatro variantes antes de observar sus resultados."""
    base = columnas_variantes(horizonte)["historia_4_mas_2"]
    observadas = familias_predictoras(horizonte)["clima"]
    anomalias = [f"hum_rel_media_anomalia_media5_h{horizonte}",
                 f"precip_total_mm_anomalia_media5_h{horizonte}"]
    return {
        "base_6": base,
        "mas_clima_observado": [*base, *observadas],
        "mas_anomalias": [*base, *anomalias],
        "mas_ambos": [*base, *observadas, *anomalias],
    }


def preparar_filas_comunes(gold: pd.DataFrame, horizonte: int) -> tuple[pd.DataFrame, int]:
    """Descarta solo el arranque sin ventana climática de cinco semanas."""
    datos, excluidas_base = preparar_gold(gold, horizonte)
    observadas = familias_predictoras(horizonte)["clima"]
    faltan = set(observadas) - set(datos)
    if faltan:
        raise ValueError(f"Faltan variables climáticas en gold: {sorted(faltan)}")
    for columna in observadas:
        datos[columna] = pd.to_numeric(datos[columna], errors="raise")
    incompletas = datos[observadas].isna().any(axis=1)
    orden = datos.sort_values(["ubigeo", "semana_inicio"])
    esperadas = orden.groupby("ubigeo").cumcount().lt(1)
    if not incompletas.loc[orden.index].reset_index(drop=True).equals(esperadas.reset_index(drop=True)):
        raise ValueError("Nulos climáticos fuera del arranque esperado")
    completos = datos.loc[~incompletas].copy().reset_index(drop=True)
    columnas = list({c for v in variantes_climaticas(horizonte).values() for c in v
                     if "anomalia" not in c})
    if completos[columnas].isna().any().any() or not np.isfinite(completos[columnas].to_numpy(float)).all():
        raise ValueError("Matriz climática incompleta o no finita")
    return completos, excluidas_base + int(incompletas.sum())


def agregar_anomalias_fold(
    train: pd.DataFrame, test: pd.DataFrame, silver: pd.DataFrame,
    horizonte: int, corte: pd.Timestamp,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Ajusta y cruza anomalías sin usar clima cerrado después del corte."""
    clima = construir_clima(silver, horizonte, ajustar_climatologia(silver, corte))
    columnas = [c for c in clima if "anomalia_media5" in c]
    if len(columnas) != 2 or clima.duplicated(CLAVE).any():
        raise ValueError("La transformación climática no produjo dos anomalías únicas")

    def cruzar(bloque: pd.DataFrame) -> pd.DataFrame:
        salida = bloque.merge(clima[CLAVE + columnas], on=CLAVE, how="left",
                             validate="one_to_one", sort=False)
        if len(salida) != len(bloque) or salida[columnas].isna().any().any():
            raise ValueError("Anomalías incompletas o cruce climático alteró filas")
        if not np.isfinite(salida[columnas].to_numpy(float)).all():
            raise ValueError("Anomalías no finitas")
        if not np.array_equal(salida["semana_inicio"].to_numpy(), bloque["semana_inicio"].to_numpy()):
            raise ValueError("El cruce climático alteró el orden temporal")
        return salida

    return cruzar(train), cruzar(test)


def ejecutar_ablacion_clima(
    *, silver_path: Path = SILVER_INTEGRADO, gold_dir: Path = GOLD,
    salida_dir: Path = MODELS / "experimentos" / "ablacion_clima",
    metricas_path: Path = DOCS / "modeling" / "metricas" / "ablacion_clima.json",
    auditar: bool = True, validar_datos: bool = True,
    registrar_mlflow: bool = True,
) -> dict:
    """Compara variantes en validación y prueba solo las elegidas allí."""
    silver_path, gold_dir, salida_dir, metricas_path = map(
        Path, (silver_path, gold_dir, salida_dir, metricas_path))
    if auditar:
        auditar_traspaso(silver_path=silver_path, gold_dir=gold_dir)
    # Calidad de datos (Great Expectations) antes de entrenar; falla si gold/silver
    # incumplen su suite. El resumen se adjunta al run de MLflow.
    calidad = (validar_entradas_modelado(gold_dir=gold_dir, silver_path=silver_path)
               if validar_datos else None)
    silver = cargar_integrado(silver_path)
    manifiesto_path = gold_dir / "manifest_fase6.json"
    manifiesto = json.loads(manifiesto_path.read_text(encoding="utf-8"))
    if manifiesto["regla_brote"]["minimo_casos"] != MINIMO_CASOS_BROTE:
        raise ValueError("El mínimo de brote del manifiesto difiere del experimento")
    reporte = {
        "experimento": "ablacion_clima_xgboost",
        "validacion": list(TEMPORADAS_VALIDACION),
        "prueba_principal": f"temporada_{TEMPORADA_PRUEBA_PRINCIPAL}",
        "prueba_sensibilidad": f"calendario_{ANIO_PRUEBA_SENSIBILIDAD}",
        "semana_inicio_temporada": SEMANA_INICIO_TEMPORADA,
        "criterio": "F1 medio de validación por temporada; empate: menos columnas",
        "climatologia": "media por ubigeo y semana, semanas cerradas al primer origen del fold; 53 usa casilla 52",
        "umbral_clasificacion": "máximo F1 agregado en validación; empate: umbral mayor",
        "parametros": PARAMETROS_BASE,
        "version_xgboost": XGBOOST_VERSION,
        "sha256_manifest_gold": hashlib.sha256(manifiesto_path.read_bytes()).hexdigest(),
        "sha256_silver": hashlib.sha256(silver_path.read_bytes()).hexdigest(),
        "nota_pruebas": "2024/2025 ya se inspeccionaron en experimentos anteriores; no se usaron para elegir variables",
        "horizontes": {},
    }
    modelos_guardar = []
    pred_validacion = []
    pred_prueba = []
    for h in (2, 4):
        archivo = gold_dir / f"{silver_path.stem}_h{h}_gold.csv"
        gold = pd.read_csv(archivo, dtype={"ubigeo": "string"},
                           parse_dates=["semana_inicio", "origen_inicio", "origen_cierre"])
        datos, excluidas = preparar_filas_comunes(gold, h)
        variantes = variantes_climaticas(h)
        bloque_h = {
            "archivo_gold": archivo.name,
            "sha256_gold": hashlib.sha256(archivo.read_bytes()).hexdigest(),
            "filas_gold": len(gold),
            "filas_excluidas_arranque": excluidas,
            "filas_comparadas": len(datos),
            "variantes": {},
        }
        print(f"h={h}: {len(datos)} filas comunes; {excluidas} de arranque excluidas")
        validacion_folds = [(f"temporada_{t}", *separar_temporada(datos, t))
                            for t in TEMPORADAS_VALIDACION]
        # La misma climatología y las mismas filas sirven a todas las variantes
        # de un fold. Ajustar aquí impide que la prueba altere sus parámetros.
        for nombre, train, test, corte in validacion_folds:
            train_a, test_a = agregar_anomalias_fold(train, test, silver, h, corte)
            for variante, columnas in variantes.items():
                pred, _, _ = predecir_fold(train_a, test_a, columnas)
                pred[f"casos_lag_{h}"] = test_a[f"casos_lag_{h}"].to_numpy(float)
                pred["horizonte"] = h
                pred["variante"] = variante
                pred["bloque"] = nombre
                pred_validacion.append(pred)
                resultado = bloque_h["variantes"].setdefault(
                    variante, {"columnas": columnas, "seleccion_umbral": None,
                               "folds_validacion": [], "folds_prueba": []})
                resultado.setdefault("_corridas", []).append(
                    (pred, corte, len(train_a), int(train_a.brote.sum())))
        for variante, resultado in bloque_h["variantes"].items():
            corridas = resultado.pop("_corridas")
            validacion = pd.concat([x[0] for x in corridas], ignore_index=True)
            seleccion = seleccionar_umbral_f1(
                validacion.brote.to_numpy(int), validacion.probabilidad_brote.to_numpy(float))
            resultado["seleccion_umbral"] = seleccion
            for pred, corte, n_train, pos_train in corridas:
                fold = evaluar_fold(
                    pred, horizonte=h, variante=variante, bloque=pred.bloque.iloc[0],
                    tipo="validacion", corte=corte, n_entrenamiento=n_train,
                    umbral_clasificacion=seleccion["umbral"])
                fold["positivos_entrenamiento"] = pos_train
                resultado["folds_validacion"].append(fold)
            reg = np.mean([f["regresion"]["alerta_derivada"]["f1"] for f in resultado["folds_validacion"]])
            cls = np.mean([f["clasificacion"]["alerta_directa"]["f1"] for f in resultado["folds_validacion"]])
            print(f"  {variante}: F1 validación reg={reg:.3f}, cls={cls:.3f}")
        elegidas = {enfoque: elegir_variante_f1(bloque_h["variantes"], enfoque, variantes)
                    for enfoque in ("regresion", "clasificacion")}
        bloque_h["elegidas_solo_validacion"] = elegidas
        prueba_folds = [
            (f"temporada_{TEMPORADA_PRUEBA_PRINCIPAL}", "prueba_principal",
             *separar_temporada(datos, TEMPORADA_PRUEBA_PRINCIPAL)),
            (f"calendario_{ANIO_PRUEBA_SENSIBILIDAD}", "prueba_sensibilidad",
             *separar_anio_calendario(datos, ANIO_PRUEBA_SENSIBILIDAD)),
        ]
        for nombre, tipo, train, test, corte in prueba_folds:
            train_a, test_a = agregar_anomalias_fold(train, test, silver, h, corte)
            for variante in dict.fromkeys(["base_6", *elegidas.values()]):
                pred, regresor, clasificador = predecir_fold(train_a, test_a, variantes[variante])
                pred[f"casos_lag_{h}"] = test_a[f"casos_lag_{h}"].to_numpy(float)
                pred["horizonte"] = h
                pred["variante"] = variante
                pred["bloque"] = nombre
                pred_prueba.append(pred)
                umbral = bloque_h["variantes"][variante]["seleccion_umbral"]["umbral"]
                fold = evaluar_fold(
                    pred, horizonte=h, variante=variante, bloque=nombre, tipo=tipo,
                    corte=corte, n_entrenamiento=len(train_a),
                    umbral_clasificacion=umbral)
                fold["positivos_entrenamiento"] = int(train_a.brote.sum())
                bloque_h["variantes"][variante]["folds_prueba"].append(fold)
                modelos_guardar.extend([
                    (regresor, f"xgb_h{h}_{variante}_regresion_{nombre}.json"),
                    (clasificador, f"xgb_h{h}_{variante}_clasificacion_{nombre}.json"),
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
            "ablacion_clima", reporte, metricas_path=metricas_path, salida_dir=salida_dir,
            gold_dir=gold_dir, calidad_datos=calidad)
    return reporte


def main() -> None:
    """Ejecuta la ablación con ``python -m src.modeling.ablacion_clima``."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--silver", type=Path, default=SILVER_INTEGRADO)
    parser.add_argument("--gold-dir", type=Path, default=GOLD)
    parser.add_argument("--salida-dir", type=Path,
                        default=MODELS / "experimentos" / "ablacion_clima")
    parser.add_argument("--metricas", type=Path,
                        default=DOCS / "modeling" / "metricas" / "ablacion_clima.json")
    parser.add_argument("--sin-validacion-datos", action="store_true",
                        help="No ejecutar las suites de Great Expectations")
    parser.add_argument("--sin-mlflow", action="store_true",
                        help="No registrar la corrida en MLflow")
    args = parser.parse_args()
    ejecutar_ablacion_clima(
        validar_datos=not args.sin_validacion_datos, registrar_mlflow=not args.sin_mlflow,
        silver_path=args.silver, gold_dir=args.gold_dir,
        salida_dir=args.salida_dir, metricas_path=args.metricas)
    print(f"Métricas: {args.metricas}")


if __name__ == "__main__":
    main()
