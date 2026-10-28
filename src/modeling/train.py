"""Primer experimento XGBoost: pronóstico de casos y alerta directa.

Cada fila es una semana objetivo. El modelo de cada temporada se ajusta una
sola vez antes de su primer origen y queda fijo durante esa temporada.
Los rezagos de semanas ya observadas dentro de la prueba sí están disponibles
para sus orígenes posteriores; ninguna etiqueta de prueba se usa para ajustar.
"""

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd
from xgboost import XGBClassifier, XGBRegressor, __version__ as XGBOOST_VERSION

from src.eda.temporal import asignar_temporada
from src.modeling.contrato_xgboost import auditar_traspaso, familias_predictoras
from src.modeling.dispositivo import configuracion_xgboost
from src.modeling.evaluate import (
    alertas_desde_conteos, metricas_alerta, metricas_conteos,
    seleccionar_umbral_f1,
)
from src.modeling.seguimiento_mlflow import registrar_o_avisar
from src.utils.paths import DOCS, GOLD, MODELS, SILVER_INTEGRADO
from src.utils.calendario import semana_epi_mmwr
from src.validation.contrato_pronostico import CLAVE
from src.validation.calidad_gx import validar_entradas_modelado

TEMPORADAS_VALIDACION = (2021, 2022, 2023)
TEMPORADA_PRUEBA_PRINCIPAL = 2024
ANIO_PRUEBA_SENSIBILIDAD = 2025
MINIMO_CASOS_BROTE = 2
SEMANA_INICIO_TEMPORADA = 35
SEMILLA = 17
PARAMETROS_BASE = {
    "n_estimators": 160,
    "max_depth": 3,
    "learning_rate": 0.05,
    "subsample": 0.8,
    "colsample_bytree": 0.9,
    "min_child_weight": 5,
    "reg_lambda": 5.0,
    "tree_method": "hist",
    "random_state": SEMILLA,
    # GPU NVIDIA si hay, si no CPU con todos los núcleos (config/config.yaml,
    # sección xgboost). Los hilos no cambian resultados; la GPU puede cambiar
    # decimales, por eso "device" queda en los parámetros del reporte.
    **configuracion_xgboost(),
}


def columnas_variantes(horizonte: int) -> dict[str, list[str]]:
    """Devuelve bases predefinidas de cuatro y seis variables disponibles."""
    familias = familias_predictoras(horizonte)
    historia = familias["historia"]
    return {
        "historia_4": [historia[0], historia[2], *familias["calendario"]],
        "historia_4_mas_2": [*historia, *familias["calendario"]],
    }


def preparar_gold(gold: pd.DataFrame, horizonte: int) -> tuple[pd.DataFrame, int]:
    """Valida el contrato mínimo y aparta solo nulos estructurales de arranque.

    Ambas variantes comparten las filas completas de la base de seis. La
    salida gold canónica no se modifica ni se rellena con ceros artificiales.
    """
    variantes = columnas_variantes(horizonte)
    base_seis = variantes["historia_4_mas_2"]
    requeridas = set(CLAVE + [
        "semana_inicio", "origen_inicio", "origen_cierre", "casos_Dengue",
        "brote", "umbral_brote_casos", *base_seis,
    ])
    faltan = requeridas - set(gold)
    if faltan or gold.empty or gold.duplicated(CLAVE).any() or gold[CLAVE].isna().any().any():
        raise ValueError(f"Gold vacío, con llaves duplicadas/incompletas o columnas ausentes: {sorted(faltan)}")
    datos = gold.copy()
    if not datos.ubigeo.astype("string").str.fullmatch(r"\d{6}").all():
        raise ValueError("ubigeo debe tener seis dígitos y ser texto")
    for col in ("semana_inicio", "origen_inicio", "origen_cierre"):
        datos[col] = pd.to_datetime(datos[col], errors="raise")
    for col in ("casos_Dengue", "brote", "umbral_brote_casos", *base_seis):
        datos[col] = pd.to_numeric(datos[col], errors="raise")
    if (datos[["casos_Dengue", "brote", "umbral_brote_casos"]].isna().any().any()
            or (datos.casos_Dengue < 0).any() or (datos.umbral_brote_casos < 0).any()
            or not np.isfinite(datos[["casos_Dengue", "brote", "umbral_brote_casos"]].to_numpy(float)).all()
            or not np.isin(datos.brote, [0, 1]).all()
            or (datos.casos_Dengue % 1 != 0).any()):
        raise ValueError("Objetivos o umbrales de gold inválidos")
    esperadas = alertas_desde_conteos(
        datos.casos_Dengue.to_numpy(float),
        datos.umbral_brote_casos.to_numpy(float), MINIMO_CASOS_BROTE,
    )
    if not np.array_equal(esperadas, datos.brote.to_numpy(bool)):
        raise ValueError("La etiqueta brote no coincide con la regla de gold")
    if (datos.semana_inicio.dt.weekday != 6).any():
        raise ValueError("semana_inicio debe ser domingo")
    calendario = semana_epi_mmwr(datos.semana_inicio)
    if (pd.to_numeric(datos.anio, errors="raise").ne(calendario.anio_epi)
            | pd.to_numeric(datos.semana, errors="raise").ne(calendario.semana_epi)).any():
        raise ValueError("anio/semana de gold no coinciden con el calendario epidemiológico MMWR")
    sin_ventana = datos[base_seis].isna().any(axis=1)
    ordenado = datos.sort_values(["ubigeo", "semana_inicio"])
    saltos = ordenado.groupby("ubigeo").semana_inicio.diff().dt.days.dropna()
    if not saltos.eq(7).all():
        raise ValueError("Gold tiene semanas faltantes o repetidas por distrito")
    posiciones = ordenado.groupby("ubigeo").cumcount()
    if not sin_ventana.loc[ordenado.index].reset_index(drop=True).equals(
        posiciones.lt(horizonte + 3).reset_index(drop=True)
    ):
        raise ValueError("Hay predictores faltantes fuera del arranque estructural")
    if datos.loc[~sin_ventana, ["origen_inicio", "origen_cierre"]].isna().any().any():
        raise ValueError("Hay predictores poblados sin origen temporal")
    if datos.loc[~sin_ventana, base_seis].isna().any().any():
        raise ValueError("Hay predictores incompletos fuera del arranque")
    if not np.isfinite(datos.loc[~sin_ventana, base_seis].to_numpy(float)).all():
        raise ValueError("Hay predictores no finitos")
    completos = datos.loc[~sin_ventana].copy()
    distancia = (completos.semana_inicio - completos.origen_inicio).dt.days
    if not distancia.eq(7 * horizonte).all() or not completos.origen_cierre.eq(completos.origen_inicio + pd.Timedelta(days=6)).all():
        raise ValueError("El origen no respeta el horizonte solicitado")
    completos["temporada"] = asignar_temporada(
        completos.anio, completos.semana, SEMANA_INICIO_TEMPORADA,
    )
    completos = completos.sort_values(["semana_inicio", "ubigeo"]).reset_index(drop=True)
    return completos, int(sin_ventana.sum())


def _separar_bloque(
    datos: pd.DataFrame, mascara: pd.Series, nombre: str,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.Timestamp]:
    """Separa un bloque temporal y exige etiquetas de train ya disponibles."""
    prueba = datos.loc[mascara].copy()
    if prueba.empty or prueba.origen_cierre.isna().any():
        raise ValueError(f"{nombre} vacío o sin origen")
    primera = prueba.semana_inicio.min()
    corte = prueba.loc[prueba.semana_inicio.eq(primera), "origen_cierre"].min()
    if not prueba.loc[prueba.semana_inicio.eq(primera), "origen_cierre"].eq(corte).all():
        raise ValueError("Los distritos tienen distinto primer origen de prueba")
    entrenamiento = datos.loc[(datos.semana_inicio + pd.Timedelta(days=6)).le(corte)].copy()
    if entrenamiento.empty or entrenamiento.brote.nunique() < 2:
        raise ValueError(f"Entrenamiento sin dos clases para {nombre}")
    if entrenamiento.semana_inicio.max() >= primera or not entrenamiento.origen_cierre.lt(entrenamiento.semana_inicio).all():
        raise ValueError("Solapamiento o fuga temporal en el corte")
    if set(map(tuple, entrenamiento[CLAVE].to_numpy())) & set(map(tuple, prueba[CLAVE].to_numpy())):
        raise ValueError("El entrenamiento contiene observaciones de prueba")
    return entrenamiento, prueba, corte


def separar_temporada(
    datos: pd.DataFrame, temporada: int,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.Timestamp]:
    """Forma un fold de temporada epidemiológica común a todos los distritos."""
    return _separar_bloque(datos, datos.temporada.eq(temporada), f"temporada {temporada}")


def separar_anio_calendario(
    datos: pd.DataFrame, anio: int,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.Timestamp]:
    """Forma una prueba anual para medir por separado el cambio de 2025."""
    return _separar_bloque(datos, datos.anio.eq(anio), f"año calendario {anio}")


def ajustar_modelos(
    entrenamiento: pd.DataFrame, columnas: list[str],
) -> tuple[XGBRegressor, XGBClassifier]:
    """Ajusta XGBoost de log1p(casos) y de brote, con hiperparámetros fijos."""
    x = entrenamiento[columnas]
    if x.isna().any().any() or not np.isfinite(x.to_numpy(float)).all():
        raise ValueError("Matriz de entrenamiento incompleta")
    regresor = XGBRegressor(objective="reg:squarederror", **PARAMETROS_BASE)
    clasificador = XGBClassifier(objective="binary:logistic", eval_metric="logloss", **PARAMETROS_BASE)
    regresor.fit(x, np.log1p(entrenamiento.casos_Dengue.to_numpy(float)))
    clasificador.fit(x, entrenamiento.brote.to_numpy(int))
    return regresor, clasificador


def conteos_desde_log1p(predicciones: np.ndarray) -> np.ndarray:
    """Invierte la salida del regresor con los límites originales del protocolo."""
    conteos = np.expm1(np.clip(predicciones, 0, 30)).clip(min=0)
    if not np.isfinite(conteos).all():
        raise ValueError("El modelo produjo conteos no finitos")
    return conteos


def predecir_fold(
    entrenamiento: pd.DataFrame, prueba: pd.DataFrame, columnas: list[str],
) -> tuple[pd.DataFrame, XGBRegressor, XGBClassifier]:
    """Predice ambos objetivos sobre exactamente las mismas distrito-semanas."""
    regresor, clasificador = ajustar_modelos(entrenamiento, columnas)
    x = prueba[columnas]
    conteos = conteos_desde_log1p(regresor.predict(x))
    probabilidades = clasificador.predict_proba(x)[:, 1]
    if not np.isfinite(conteos).all() or not np.isfinite(probabilidades).all():
        raise ValueError("El modelo produjo predicciones no finitas")
    salida = prueba[CLAVE + [
        "semana_inicio", "origen_cierre", "temporada", "casos_Dengue",
        "brote", "umbral_brote_casos",
    ]].copy()
    salida["casos_predichos"] = conteos
    salida["probabilidad_brote"] = probabilidades
    return salida, regresor, clasificador


def evaluar_fold(
    predicciones: pd.DataFrame, *, horizonte: int, variante: str,
    bloque: str, tipo: str, corte: pd.Timestamp, n_entrenamiento: int,
    umbral_clasificacion: float,
) -> dict:
    """Evalúa regresión, clasificación y persistencia en un mismo fold."""
    y = predicciones.brote.to_numpy(int)
    casos = predicciones.casos_Dengue.to_numpy(float)
    limite = predicciones.umbral_brote_casos.to_numpy(float)
    pronostico = predicciones.casos_predichos.to_numpy(float)
    persistencia = predicciones[f"casos_lag_{horizonte}"].to_numpy(float)
    margen = pronostico - np.maximum(limite, MINIMO_CASOS_BROTE)
    margen_persistencia = persistencia - np.maximum(limite, MINIMO_CASOS_BROTE)
    alerta_regresion = alertas_desde_conteos(pronostico, limite, MINIMO_CASOS_BROTE)
    alerta_persistencia = alertas_desde_conteos(persistencia, limite, MINIMO_CASOS_BROTE)
    prob = predicciones.probabilidad_brote.to_numpy(float)
    return {
        "horizonte": horizonte,
        "variante": variante,
        "bloque": bloque,
        "tipo": tipo,
        "primera_semana_objetivo": str(predicciones.semana_inicio.min().date()),
        "ultima_semana_objetivo": str(predicciones.semana_inicio.max().date()),
        "corte_ajuste": str(corte.date()),
        "n_entrenamiento": n_entrenamiento,
        "n_prueba": len(predicciones),
        "positivos_entrenamiento": None,
        "regresion": {
            "conteos": metricas_conteos(casos, pronostico),
            "alerta_derivada": metricas_alerta(y, alerta_regresion, puntaje=margen),
        },
        "clasificacion": {
            "umbral_probabilidad": umbral_clasificacion,
            "alerta_directa": metricas_alerta(y, prob >= umbral_clasificacion, puntaje=prob),
            "brier": float(np.mean((prob - y) ** 2)),
        },
        "persistencia": {
            "conteos": metricas_conteos(casos, persistencia),
            "alerta_derivada": metricas_alerta(y, alerta_persistencia, puntaje=margen_persistencia),
        },
    }


def ejecutar_experimento(
    *, gold_dir: Path = GOLD, salida_dir: Path = MODELS / "experimentos",
    metricas_path: Path = DOCS / "modeling" / "metricas" / "primer_xgboost.json",
    auditar: bool = True, validar_datos: bool = True,
    registrar_mlflow: bool = True,
) -> dict:
    """Entrena ambos enfoques en validación y pruebas temporales predefinidas.

    El umbral de clasificación se fija con predicciones fuera de muestra de
    las temporadas 2021–2023. La prueba principal es la temporada 2024; el
    año calendario 2025 completo es una sensibilidad aparte. Cada modelo
    de prueba se reentrena solo con etiquetas previas a su primer origen.
    """
    gold_dir, salida_dir, metricas_path = map(Path, (gold_dir, salida_dir, metricas_path))
    if auditar:
        auditar_traspaso(gold_dir=gold_dir)
    # Calidad de datos (Great Expectations) antes de entrenar; falla si gold/silver
    # incumplen su suite. El resumen se adjunta al run de MLflow.
    calidad = (validar_entradas_modelado(gold_dir=gold_dir, silver_path=None)
               if validar_datos else None)
    manifiesto = json.loads((gold_dir / "manifest_fase6.json").read_text(encoding="utf-8"))
    if manifiesto["regla_brote"]["minimo_casos"] != MINIMO_CASOS_BROTE:
        raise ValueError("El mínimo de brote del manifiesto difiere del experimento")
    resumen = {
        "objetivo": "conteos log1p y alerta binaria directa por separado",
        "validacion": list(TEMPORADAS_VALIDACION),
        "prueba_principal": f"temporada_{TEMPORADA_PRUEBA_PRINCIPAL}",
        "prueba_sensibilidad": f"calendario_{ANIO_PRUEBA_SENSIBILIDAD}",
        "semana_inicio_temporada": SEMANA_INICIO_TEMPORADA,
        "minimo_casos_brote": MINIMO_CASOS_BROTE,
        "criterio_umbral_clasificacion": "máximo F1 agregado en validación 2021-2023; empate: umbral mayor",
        "parametros": PARAMETROS_BASE,
        "version_xgboost": XGBOOST_VERSION,
        "sha256_manifest_gold": hashlib.sha256((gold_dir / "manifest_fase6.json").read_bytes()).hexdigest(),
        "horizontes": {},
    }
    modelos_guardar = []
    predicciones_guardar = []
    for h in (2, 4):
        archivo = gold_dir / f"{SILVER_INTEGRADO.stem}_h{h}_gold.csv"
        gold = pd.read_csv(archivo, dtype={"ubigeo": "string"},
                           parse_dates=["semana_inicio", "origen_inicio", "origen_cierre"])
        datos, excluidas = preparar_gold(gold, h)
        variantes = columnas_variantes(h)
        resumen_h = {
            "archivo_gold": archivo.name,
            "sha256_gold": hashlib.sha256(archivo.read_bytes()).hexdigest(),
            "filas_gold": len(gold), "filas_excluidas_arranque": excluidas,
            "filas_modelables": len(datos), "variantes": {},
        }
        print(f"h={h}: {len(datos)} filas modelables; {excluidas} de arranque fuera de la matriz")
        for nombre, columnas in variantes.items():
            corridas = {}
            bloques = [
                *( (f"temporada_{t}", "validacion", t) for t in TEMPORADAS_VALIDACION),
                (f"temporada_{TEMPORADA_PRUEBA_PRINCIPAL}", "prueba_principal", TEMPORADA_PRUEBA_PRINCIPAL),
                (f"calendario_{ANIO_PRUEBA_SENSIBILIDAD}", "prueba_sensibilidad", ANIO_PRUEBA_SENSIBILIDAD),
            ]
            for bloque, tipo, periodo in bloques:
                if bloque.startswith("temporada_"):
                    train, test, corte = separar_temporada(datos, periodo)
                else:
                    train, test, corte = separar_anio_calendario(datos, periodo)
                print(f"  {nombre}, {bloque}: train={len(train)}, test={len(test)}, corte={corte.date()}")
                pred, regresor, clasificador = predecir_fold(train, test, columnas)
                pred[f"casos_lag_{h}"] = test[f"casos_lag_{h}"].to_numpy(float)
                pred["horizonte"] = h
                pred["variante"] = nombre
                pred["bloque"] = bloque
                corridas[bloque] = (pred, corte, len(train), int(train.brote.sum()), tipo)
                predicciones_guardar.append(pred)
                if tipo != "validacion":
                    modelos_guardar.extend([
                        (regresor, f"xgb_h{h}_{nombre}_regresion_{bloque}.json"),
                        (clasificador, f"xgb_h{h}_{nombre}_clasificacion_{bloque}.json"),
                    ])
            validacion = pd.concat([
                corridas[f"temporada_{t}"][0] for t in TEMPORADAS_VALIDACION
            ], ignore_index=True)
            seleccion = seleccionar_umbral_f1(
                validacion.brote.to_numpy(int),
                validacion.probabilidad_brote.to_numpy(float),
            )
            folds = []
            for bloque, (pred, corte, n_train, pos_train, tipo) in corridas.items():
                fold = evaluar_fold(
                    pred, horizonte=h, variante=nombre, bloque=bloque, tipo=tipo,
                    corte=corte, n_entrenamiento=n_train,
                    umbral_clasificacion=seleccion["umbral"],
                )
                fold["positivos_entrenamiento"] = pos_train
                folds.append(fold)
            resumen_h["variantes"][nombre] = {
                "columnas": columnas,
                "seleccion_umbral": seleccion,
                "folds": folds,
            }
        resumen["horizontes"][str(h)] = resumen_h
    salida_dir.mkdir(parents=True, exist_ok=True)
    metricas_path.parent.mkdir(parents=True, exist_ok=True)
    for modelo, nombre in modelos_guardar:
        modelo.save_model(salida_dir / nombre)
    predicciones = pd.concat(predicciones_guardar, ignore_index=True)
    predicciones.to_csv(salida_dir / "predicciones_por_fold.csv", index=False)
    metricas_path.write_text(json.dumps(resumen, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if registrar_mlflow:
        registrar_o_avisar(
            "primer_xgboost", resumen, metricas_path=metricas_path, salida_dir=salida_dir,
            gold_dir=gold_dir, calidad_datos=calidad)
    return resumen


def main() -> None:
    """Ejecuta el primer experimento desde ``python -m src.modeling.train``."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--gold-dir", type=Path, default=GOLD)
    parser.add_argument("--salida-dir", type=Path, default=MODELS / "experimentos")
    parser.add_argument("--metricas", type=Path,
                        default=DOCS / "modeling" / "metricas" / "primer_xgboost.json")
    parser.add_argument("--sin-validacion-datos", action="store_true",
                        help="No ejecutar las suites de Great Expectations")
    parser.add_argument("--sin-mlflow", action="store_true",
                        help="No registrar la corrida en MLflow")
    args = parser.parse_args()
    resumen = ejecutar_experimento(
        validar_datos=not args.sin_validacion_datos, registrar_mlflow=not args.sin_mlflow,
        gold_dir=args.gold_dir, salida_dir=args.salida_dir,
        metricas_path=args.metricas,
    )
    print(f"Métricas: {args.metricas}")
    for h, resultado in resumen["horizontes"].items():
        print(f"h={h}: {list(resultado['variantes'])}")


if __name__ == "__main__":
    main()
