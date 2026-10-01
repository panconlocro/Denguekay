"""Ablación XGBoost de sociodemografía fija y anual reconstruida.

El eje urbano se ajusta con la referencia censal de los distritos presentes
en el entrenamiento de cada fold. La comparación anual es retrospectiva:
las fracciones de 2018–2024 ya incorporan el extremo de 2025.
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
from src.modeling.contrato_xgboost import auditar_traspaso, familias_predictoras
from src.modeling.evaluate import seleccionar_umbral_f1
from src.modeling.features import FECHA_SOCIO_2017
from src.modeling.sociodemografia import (
    DIRECTAS, ajustar_eje_urbano, construir_sociodemografia,
    construir_sociodemografia_anual, referencia_2017,
)
from src.modeling.train import (
    ANIO_PRUEBA_SENSIBILIDAD, MINIMO_CASOS_BROTE, PARAMETROS_BASE,
    SEMANA_INICIO_TEMPORADA, TEMPORADA_PRUEBA_PRINCIPAL,
    TEMPORADAS_VALIDACION, columnas_variantes, evaluar_fold,
    predecir_fold, preparar_gold, separar_anio_calendario,
    separar_temporada,
)
from src.processing.socio_interpolacion import SOCIO_COLUMNS
from src.utils.paths import DOCS, GOLD, MODELS, SILVER_INTEGRADO
from src.validation.contrato_pronostico import CLAVE


def variantes_sociodemograficas(horizonte: int) -> dict[str, list[str]]:
    """Predefine variantes de 2017 y anuales sobre la misma base de seis."""
    base = columnas_variantes(horizonte)["historia_4_mas_2"]
    familias = familias_predictoras(horizonte)
    fijas = familias["socio_2017"]
    anuales = familias["socio_anual_reconstruida"]
    if fijas != [*(f"{c}_2017" for c in DIRECTAS), "log_poblacion_censo_2017"]:
        raise ValueError("Cambió el contrato de columnas censales fijas")
    fracciones_anuales = [f"{c}_anual" for c in SOCIO_COLUMNS if c != "poblacion"]
    if anuales != [*fracciones_anuales, "log_poblacion_anual"]:
        raise ValueError("Cambió el contrato de columnas anuales")
    return {
        "base_6": base,
        "fija_poblacion": [*base, fijas[-1]],
        "fija_tres": [*base, *fijas[:-1]],
        "fija_eje": [*base, "eje_urbano_2017"],
        "fija_poblacion_eje": [*base, fijas[-1], "eje_urbano_2017"],
        "anual_poblacion": [*base, "log_poblacion_anual"],
        "anual_tres": [*base, *(f"{c}_anual" for c in DIRECTAS)],
        "anual_eje": [*base, "eje_urbano_anual"],
        "anual_15": [*base, *fracciones_anuales],
        "anual_poblacion_eje": [*base, "log_poblacion_anual", "eje_urbano_anual"],
    }


def validar_matriz_sociodemografica(
    datos: pd.DataFrame, variantes: dict[str, list[str]],
) -> None:
    """Exige cobertura completa y finita de columnas ya publicadas en gold."""
    columnas = sorted({c for cols in variantes.values() for c in cols
                       if c not in ("eje_urbano_2017", "eje_urbano_anual")})
    faltan = set(columnas + ["socio_2017_disponible_al_origen"]) - set(datos)
    if faltan:
        raise ValueError(f"Faltan candidatas sociodemográficas: {sorted(faltan)}")
    if any(len(cols) != len(set(cols)) for cols in variantes.values()):
        raise ValueError("Una variante contiene predictores repetidos")
    for columna in columnas:
        datos[columna] = pd.to_numeric(datos[columna], errors="raise")
    if datos[columnas].isna().any().any() or not np.isfinite(datos[columnas].to_numpy(float)).all():
        raise ValueError("Hay datos sociodemográficos incompletos o no finitos")


def agregar_ejes_fold(
    train: pd.DataFrame, test: pd.DataFrame, silver: pd.DataFrame,
    referencia: pd.DataFrame, horizonte: int, corte: pd.Timestamp,
) -> tuple[pd.DataFrame, pd.DataFrame, float]:
    """Ajusta CP1 con distritos del entrenamiento y lo cruza sin perder filas."""
    distritos = set(train.ubigeo.astype(str))
    eje = ajustar_eje_urbano(referencia, distritos)
    fija = construir_sociodemografia(
        silver, horizonte, referencia, FECHA_SOCIO_2017, eje,
        enmascarar_antes_disponibilidad=False)
    anual = construir_sociodemografia_anual(silver, eje)
    if not set(test.ubigeo.astype(str)).issubset(distritos):
        raise ValueError("La prueba tiene distritos ajenos al entrenamiento")
    if test.origen_cierre.isna().any() or test.origen_cierre.lt(pd.Timestamp(FECHA_SOCIO_2017)).any():
        raise ValueError("La referencia censal no estaba disponible en un origen de prueba")
    if train.semana_inicio.max() + pd.Timedelta(days=6) > corte:
        raise ValueError("El entrenamiento contiene etiquetas posteriores al corte")
    ejes = fija[CLAVE + ["eje_urbano_2017"]].merge(
        anual[CLAVE + ["eje_urbano_anual"]], on=CLAVE,
        validate="one_to_one", sort=False)
    if len(ejes) != len(silver) or ejes.duplicated(CLAVE).any():
        raise ValueError("Los ejes sociodemográficos cambiaron el grano")

    def cruzar(bloque: pd.DataFrame) -> pd.DataFrame:
        salida = bloque.merge(ejes, on=CLAVE, how="left", validate="one_to_one", sort=False)
        columnas = ["eje_urbano_2017", "eje_urbano_anual"]
        if (len(salida) != len(bloque) or salida[columnas].isna().any().any()
                or not np.isfinite(salida[columnas].to_numpy(float)).all()):
            raise ValueError("Los ejes faltan o el cruce alteró filas")
        if not np.array_equal(salida.semana_inicio.to_numpy(), bloque.semana_inicio.to_numpy()):
            raise ValueError("El cruce alteró el orden temporal")
        return salida

    return cruzar(train), cruzar(test), eje.varianza_explicada


def ejecutar_ablacion_sociodemografica(
    *, silver_path: Path = SILVER_INTEGRADO, gold_dir: Path = GOLD,
    salida_dir: Path = MODELS / "experimentos" / "ablacion_sociodemografica",
    metricas_path: Path = DOCS / "modeling" / "metricas" / "ablacion_sociodemografica.json",
    auditar: bool = True,
) -> dict:
    """Selecciona por validación variantes fijas y anuales por separado."""
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
        "experimento": "ablacion_sociodemografica_xgboost",
        "validacion": list(TEMPORADAS_VALIDACION),
        "prueba_principal": f"temporada_{TEMPORADA_PRUEBA_PRINCIPAL}",
        "prueba_sensibilidad": f"calendario_{ANIO_PRUEBA_SENSIBILIDAD}",
        "semana_inicio_temporada": SEMANA_INICIO_TEMPORADA,
        "criterio": "F1 medio de validación por temporada; empate: menos columnas",
        "fecha_disponibilidad_fija_supuesta": FECHA_SOCIO_2017,
        "linaje_anual": "fracciones 2018-2024 reconstruidas con 2017 y 2025; evaluación retrospectiva, no pronóstico histórico operativo",
        "umbral_clasificacion": "máximo F1 agregado en validación; empate: umbral mayor",
        "parametros": PARAMETROS_BASE,
        "version_xgboost": XGBOOST_VERSION,
        "sha256_manifest_gold": hashlib.sha256(manifiesto_path.read_bytes()).hexdigest(),
        "sha256_silver": hashlib.sha256(silver_path.read_bytes()).hexdigest(),
        "nota_pruebas": "2024/2025 ya se inspeccionaron; no se usaron para elegir variantes nuevas",
        "horizontes": {},
    }
    modelos_guardar = []
    pred_validacion = []
    pred_prueba = []
    for h in (2, 4):
        archivo = gold_dir / f"{silver_path.stem}_h{h}_gold.csv"
        gold = pd.read_csv(archivo, dtype={"ubigeo": "string"},
                           parse_dates=["semana_inicio", "origen_inicio", "origen_cierre"])
        datos, excluidas = preparar_gold(gold, h)
        variantes = variantes_sociodemograficas(h)
        validar_matriz_sociodemografica(datos, variantes)
        bloque_h = {
            "archivo_gold": archivo.name,
            "sha256_gold": hashlib.sha256(archivo.read_bytes()).hexdigest(),
            "filas_gold": len(gold),
            "filas_excluidas_arranque": excluidas,
            "filas_comparadas": len(datos),
            "variantes": {},
            "pca_folds": [],
        }
        print(f"h={h}: {len(datos)} filas comunes; {excluidas} de arranque excluidas")
        validacion_folds = [(f"temporada_{t}", *separar_temporada(datos, t))
                            for t in TEMPORADAS_VALIDACION]
        for nombre, train, test, corte in validacion_folds:
            train_a, test_a, varianza = agregar_ejes_fold(
                train, test, silver, referencia, h, corte)
            bloque_h["pca_folds"].append({"bloque": nombre, "corte": str(corte.date()),
                                           "distritos_ajuste": int(train.ubigeo.nunique()),
                                           "varianza_explicada_cp1": varianza})
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
        grupos = {
            "fija": {k: v for k, v in variantes.items() if k == "base_6" or k.startswith("fija_")},
            "anual_retrospectiva": {k: v for k, v in variantes.items()
                                    if k == "base_6" or k.startswith("anual_")},
        }
        elegidas = {grupo: {enfoque: elegir_variante_f1(
            {k: bloque_h["variantes"][k] for k in opciones}, enfoque, opciones)
            for enfoque in ("regresion", "clasificacion")}
            for grupo, opciones in grupos.items()}
        bloque_h["elegidas_solo_validacion"] = elegidas
        prueba_folds = [
            (f"temporada_{TEMPORADA_PRUEBA_PRINCIPAL}", "prueba_principal",
             *separar_temporada(datos, TEMPORADA_PRUEBA_PRINCIPAL)),
            (f"calendario_{ANIO_PRUEBA_SENSIBILIDAD}", "prueba_sensibilidad",
             *separar_anio_calendario(datos, ANIO_PRUEBA_SENSIBILIDAD)),
        ]
        for nombre, tipo, train, test, corte in prueba_folds:
            train_a, test_a, varianza = agregar_ejes_fold(
                train, test, silver, referencia, h, corte)
            bloque_h["pca_folds"].append({"bloque": nombre, "corte": str(corte.date()),
                                           "distritos_ajuste": int(train.ubigeo.nunique()),
                                           "varianza_explicada_cp1": varianza})
            seleccionadas = dict.fromkeys([
                "base_6", *elegidas["fija"].values(),
                *elegidas["anual_retrospectiva"].values()])
            for variante in seleccionadas:
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
    return reporte


def main() -> None:
    """Ejecuta la ablación con ``python -m src.modeling.ablacion_sociodemografica``."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--silver", type=Path, default=SILVER_INTEGRADO)
    parser.add_argument("--gold-dir", type=Path, default=GOLD)
    parser.add_argument("--salida-dir", type=Path,
                        default=MODELS / "experimentos" / "ablacion_sociodemografica")
    parser.add_argument("--metricas", type=Path,
                        default=DOCS / "modeling" / "metricas" / "ablacion_sociodemografica.json")
    args = parser.parse_args()
    ejecutar_ablacion_sociodemografica(
        silver_path=args.silver, gold_dir=args.gold_dir,
        salida_dir=args.salida_dir, metricas_path=args.metricas)
    print(f"Métricas: {args.metricas}")


if __name__ == "__main__":
    main()
