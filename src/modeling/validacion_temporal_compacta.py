"""Evaluación progresiva de tres matrices compactas para ambos objetivos.

Cada umbral de alerta se calibra con predicciones de temporadas anteriores
cuyas etiquetas ya cerraron al primer origen del bloque evaluado.
"""

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd
from xgboost import __version__ as XGBOOST_VERSION

from src.modeling.contrato_xgboost import auditar_traspaso
from src.modeling.evaluate import seleccionar_umbral_f1
from src.modeling.features import FECHA_SOCIO_2017
from src.modeling.train import (
    ANIO_PRUEBA_SENSIBILIDAD, MINIMO_CASOS_BROTE, PARAMETROS_BASE,
    SEMANA_INICIO_TEMPORADA, columnas_variantes, evaluar_fold, predecir_fold,
    preparar_gold, separar_anio_calendario, separar_temporada,
)
from src.utils.paths import DOCS, GOLD, MODELS, SILVER_INTEGRADO
from src.validation.contrato_pronostico import CLAVE


TEMPORADAS = (2021, 2022, 2023, 2024)
TEMPORADAS_SELECCION = (2022, 2023)
POBLACION = "log_poblacion_censo_2017"


def variantes_compactas(horizonte: int) -> dict[str, list[str]]:
    """Define las matrices pequeñas antes de consultar los nuevos resultados."""
    bases = columnas_variantes(horizonte)
    return {
        "base_4": bases["historia_4"],
        "base_6": bases["historia_4_mas_2"],
        "base_6_poblacion_2017": [*bases["historia_4_mas_2"], POBLACION],
    }


def validar_matriz(datos: pd.DataFrame, horizonte: int) -> None:
    """Comprueba predictores completos y población fija por UBIGEO."""
    variantes = variantes_compactas(horizonte)
    columnas = sorted({c for cols in variantes.values() for c in cols})
    faltan = set(columnas) - set(datos)
    if faltan:
        raise ValueError(f"Faltan columnas de la matriz compacta: {sorted(faltan)}")
    if any(len(v) != len(set(v)) for v in variantes.values()):
        raise ValueError("La matriz compacta repite predictores")
    if set(columnas) & {"ubigeo", "casos_Dengue", "brote", "umbral_brote_casos"}:
        raise ValueError("La matriz compacta incluye identificador u objetivo")
    if datos[columnas].isna().any().any() or not np.isfinite(datos[columnas].to_numpy(float)).all():
        raise ValueError("Predictores compactos incompletos o no finitos")
    if datos[POBLACION].le(0).any() or datos.groupby("ubigeo")[POBLACION].nunique().ne(1).any():
        raise ValueError("La población censal de 2017 debe ser positiva y fija por UBIGEO")
    if datos.duplicated(CLAVE).any():
        raise ValueError("Distrito-semanas duplicadas")


def calibracion_disponible(
    predicciones_anteriores: list[pd.DataFrame], corte: pd.Timestamp,
) -> tuple[pd.DataFrame, int]:
    """Usa solo etiquetas cerradas antes del primer origen del bloque nuevo."""
    if not predicciones_anteriores:
        raise ValueError("Se necesita una temporada anterior para calibrar")
    anteriores = pd.concat(predicciones_anteriores, ignore_index=True)
    cierre_etiqueta = anteriores.semana_inicio + pd.Timedelta(days=6)
    disponibles = anteriores.loc[cierre_etiqueta.le(corte)].copy()
    if disponibles.empty or disponibles.brote.nunique() < 2:
        raise ValueError("Calibración sin dos clases disponibles al origen")
    if disponibles.duplicated(CLAVE).any():
        raise ValueError("Observaciones duplicadas para calibrar")
    if not (disponibles.semana_inicio + pd.Timedelta(days=6)).le(corte).all():
        raise ValueError("La calibración incluye etiquetas futuras")
    return disponibles, len(anteriores) - len(disponibles)


def elegir_en_validacion(
    resultados: dict[str, dict], enfoque: str, variantes: dict[str, list[str]],
) -> str:
    """Selecciona por F1 medio de 2022–2023; empate, menos columnas."""
    if enfoque not in {"regresion", "clasificacion"}:
        raise ValueError("Enfoque inválido")
    ruta = "alerta_derivada" if enfoque == "regresion" else "alerta_directa"

    def puntuacion(nombre: str) -> tuple[float, int, str]:
        folds = resultados[nombre]["folds"]
        usados = [f for f in folds if f["bloque"] in {f"temporada_{x}" for x in TEMPORADAS_SELECCION}]
        if len(usados) != len(TEMPORADAS_SELECCION):
            raise ValueError("Faltan folds progresivos para selección")
        return float(np.mean([f[enfoque][ruta]["f1"] for f in usados])), -len(variantes[nombre]), nombre

    return max(variantes, key=puntuacion)


def ejecutar_validacion_temporal_compacta(
    *, gold_dir: Path = GOLD,
    salida_dir: Path = MODELS / "experimentos" / "validacion_temporal_compacta",
    metricas_path: Path = DOCS / "modeling" / "metricas" / "validacion_temporal_compacta.json",
    auditar: bool = True,
) -> dict:
    """Entrena matrices predefinidas con calibración cronológica por temporada."""
    gold_dir, salida_dir, metricas_path = map(Path, (gold_dir, salida_dir, metricas_path))
    if auditar:
        auditar_traspaso(gold_dir=gold_dir)
    manifiesto_path = gold_dir / "manifest_fase6.json"
    manifiesto = json.loads(manifiesto_path.read_text(encoding="utf-8"))
    if manifiesto["regla_brote"]["minimo_casos"] != MINIMO_CASOS_BROTE:
        raise ValueError("El mínimo de brote difiere del manifiesto gold")
    reporte = {
        "experimento": "validacion_temporal_progresiva_matrices_compactas",
        "variantes_predefinidas": ["base_4", "base_6", "base_6_poblacion_2017"],
        "temporada_calibracion_inicial": 2021,
        "temporadas_seleccion": list(TEMPORADAS_SELECCION),
        "temporada_contraste": 2024,
        "sensibilidad_calendario": ANIO_PRUEBA_SENSIBILIDAD,
        "semana_inicio_temporada": SEMANA_INICIO_TEMPORADA,
        "regla_calibracion": "predicciones OOS de temporadas anteriores; etiqueta con cierre <= primer origen del bloque",
        "criterio_seleccion": "F1 medio no ponderado de 2022 y 2023; empate: menos columnas",
        "nota_2024": "2024 fue inspeccionado en ensayos previos; contraste exploratorio, no test virgen",
        "parametros": PARAMETROS_BASE,
        "version_xgboost": XGBOOST_VERSION,
        "sha256_manifest_gold": hashlib.sha256(manifiesto_path.read_bytes()).hexdigest(),
        "horizontes": {},
    }
    predicciones = []
    for h in (2, 4):
        archivo = gold_dir / f"{SILVER_INTEGRADO.stem}_h{h}_gold.csv"
        gold = pd.read_csv(archivo, dtype={"ubigeo": "string"},
                           parse_dates=["semana_inicio", "origen_inicio", "origen_cierre"])
        datos, excluidas = preparar_gold(gold, h)
        validar_matriz(datos, h)
        variantes = variantes_compactas(h)
        bloque_h = {
            "archivo_gold": archivo.name,
            "sha256_gold": hashlib.sha256(archivo.read_bytes()).hexdigest(),
            "filas_gold": len(gold), "filas_excluidas_arranque": excluidas,
            "filas_comparadas": len(datos), "variantes": {},
        }
        print(f"h={h}: {len(datos)} filas comunes; calibración progresiva")
        for nombre, columnas in variantes.items():
            previas: list[pd.DataFrame] = []
            resultado = {"columnas": columnas, "calibracion_inicial": None, "folds": [], "sensibilidad_2025": None}
            for temporada in TEMPORADAS:
                train, test, corte = separar_temporada(datos, temporada)
                if nombre.endswith("poblacion_2017") and test.origen_cierre.lt(pd.Timestamp(FECHA_SOCIO_2017)).any():
                    raise ValueError("Referencia censal no disponible en el bloque")
                pred, _, _ = predecir_fold(train, test, columnas)
                pred[f"casos_lag_{h}"] = test[f"casos_lag_{h}"].to_numpy(float)
                pred["horizonte"] = h
                pred["variante"] = nombre
                pred["bloque"] = f"temporada_{temporada}"
                predicciones.append(pred)
                if temporada == TEMPORADAS[0]:
                    resultado["calibracion_inicial"] = {
                        "bloque": f"temporada_{temporada}", "filas": len(pred),
                        "positivos": int(pred.brote.sum()), "sin_evaluacion_clasificacion": True,
                    }
                else:
                    cal, excluidas_no_disponibles = calibracion_disponible(previas, corte)
                    umbral = seleccionar_umbral_f1(
                        cal.brote.to_numpy(int), cal.probabilidad_brote.to_numpy(float))
                    fold = evaluar_fold(
                        pred, horizonte=h, variante=nombre, bloque=f"temporada_{temporada}",
                        tipo="seleccion" if temporada in TEMPORADAS_SELECCION else "contraste",
                        corte=corte, n_entrenamiento=len(train),
                        umbral_clasificacion=umbral["umbral"],
                    )
                    fold["positivos_entrenamiento"] = int(train.brote.sum())
                    fold["calibracion"] = {
                        "filas": len(cal), "positivos": int(cal.brote.sum()),
                        "etiquetas_no_disponibles": excluidas_no_disponibles,
                        "ultima_etiqueta_cerrada": str((cal.semana_inicio.max() + pd.Timedelta(days=6)).date()),
                        "seleccion_umbral": umbral,
                    }
                    resultado["folds"].append(fold)
                previas.append(pred)
            # La sensibilidad de 2025 se calcula con sus propias predicciones;
            # tampoco recibe etiquetas posteriores a su primer origen.
            train, test, corte = separar_anio_calendario(datos, ANIO_PRUEBA_SENSIBILIDAD)
            pred, _, _ = predecir_fold(train, test, columnas)
            pred[f"casos_lag_{h}"] = test[f"casos_lag_{h}"].to_numpy(float)
            pred["horizonte"] = h
            pred["variante"] = nombre
            pred["bloque"] = f"calendario_{ANIO_PRUEBA_SENSIBILIDAD}"
            predicciones.append(pred)
            cal, excluidas_no_disponibles = calibracion_disponible(previas, corte)
            umbral = seleccionar_umbral_f1(cal.brote.to_numpy(int), cal.probabilidad_brote.to_numpy(float))
            fold = evaluar_fold(
                pred, horizonte=h, variante=nombre, bloque=f"calendario_{ANIO_PRUEBA_SENSIBILIDAD}",
                tipo="sensibilidad", corte=corte, n_entrenamiento=len(train),
                umbral_clasificacion=umbral["umbral"],
            )
            fold["positivos_entrenamiento"] = int(train.brote.sum())
            fold["calibracion"] = {
                "filas": len(cal), "positivos": int(cal.brote.sum()),
                "etiquetas_no_disponibles": excluidas_no_disponibles,
                "ultima_etiqueta_cerrada": str((cal.semana_inicio.max() + pd.Timedelta(days=6)).date()),
                "seleccion_umbral": umbral,
            }
            resultado["sensibilidad_2025"] = fold
            bloque_h["variantes"][nombre] = resultado
        bloque_h["seleccion_2022_2023"] = {
            enfoque: elegir_en_validacion(bloque_h["variantes"], enfoque, variantes)
            for enfoque in ("regresion", "clasificacion")
        }
        reporte["horizontes"][str(h)] = bloque_h
    salida_dir.mkdir(parents=True, exist_ok=True)
    metricas_path.parent.mkdir(parents=True, exist_ok=True)
    pd.concat(predicciones, ignore_index=True).to_csv(salida_dir / "predicciones_por_bloque.csv", index=False)
    metricas_path.write_text(json.dumps(reporte, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return reporte


def main() -> None:
    """Ejecuta ``python -m src.modeling.validacion_temporal_compacta``."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--gold-dir", type=Path, default=GOLD)
    parser.add_argument("--salida-dir", type=Path,
                        default=MODELS / "experimentos" / "validacion_temporal_compacta")
    parser.add_argument("--metricas", type=Path,
                        default=DOCS / "modeling" / "metricas" / "validacion_temporal_compacta.json")
    args = parser.parse_args()
    reporte = ejecutar_validacion_temporal_compacta(
        gold_dir=args.gold_dir, salida_dir=args.salida_dir, metricas_path=args.metricas)
    print(f"Métricas: {args.metricas}")
    for h, bloque in reporte["horizontes"].items():
        print(f"h={h}: {bloque['seleccion_2022_2023']}")


if __name__ == "__main__":
    main()
