"""Contrato auditable de entrada para la futura experimentación con XGBoost.

La fase 7 enumera candidatos y comprueba gold; no ajusta modelos ni decide
el corte final de entrenamiento y prueba.
"""

import hashlib
import json
from pathlib import Path

import pandas as pd

from src.eda.carga import cargar_integrado
from src.modeling.features import HORIZONTES, columnas_gold, validar_gold
from src.modeling.sociodemografia import DIRECTAS
from src.processing.socio_interpolacion import SOCIO_COLUMNS
from src.utils.paths import (
    DOCS, GOLD, SILVER_EPI_HISTORICO, SILVER_INTEGRADO, UBIGEO_CATALOG,
)
from src.validation.contrato_pronostico import CLAVE
from src.validation.expectations_integrado import (
    coverage_path, load_case_coverage, validate_complete, validate_geography,
)

NO_PREDICTORAS = (
    "casos_Dengue", "brote", "umbral_brote_casos", "ubigeo", "anio",
    "semana", "provincia", "distrito", "distrito_key", "semana_inicio",
    "origen_inicio", "origen_cierre", "socio_2017_disponible_al_origen",
    "socio_fracciones_interpoladas_con_2025",
)


def familias_predictoras(horizonte: int) -> dict[str, list[str]]:
    """Devuelve candidatos de gold por familia para `h=2` o `h=4`.

    Las familias opcionales se ensayan mediante ablaciones; devolverlas aquí
    no implica entrenar todas juntas ni validar su disponibilidad operativa.
    """
    if horizonte not in HORIZONTES:
        raise ValueError("El horizonte debe ser 2 o 4 semanas")
    h = horizonte
    return {
        "historia": [f"casos_lag_{h}", f"casos_lag_{h + 1}",
                     f"casos_media_4_h{h}", f"casos_semanas_positivas_4_h{h}"],
        "calendario": ["semana_epi_seno", "semana_epi_coseno"],
        "vecinos": [f"vecinos_media_casos_knn5_h{h}",
                     f"vecinos_frac_con_casos_knn5_h{h}"],
        "jerarquia": [f"provincia_otros_casos_h{h}",
                      f"provincia_otros_frac_con_casos_h{h}",
                      f"region_otros_casos_h{h}",
                      f"region_otros_frac_con_casos_h{h}"],
        "clima": [f"hum_rel_media_media5_h{h}",
                  f"precip_total_mm_media5_h{h}"],
        "socio_2017": [*(f"{c}_2017" for c in DIRECTAS),
                       "log_poblacion_censo_2017"],
        "socio_anual_reconstruida": [
            *(f"{c}_anual" for c in SOCIO_COLUMNS if c != "poblacion"),
            "log_poblacion_anual",
        ],
    }


def validar_columnas_modelo(
    gold: pd.DataFrame, manifiesto: dict, horizonte: int,
) -> dict[str, list[str]]:
    """Rechaza columnas inesperadas, etiquetas predictoras y linaje incoherente."""
    if gold.columns.duplicated().any() or set(gold) != set(columnas_gold(horizonte, con_brote=True)):
        raise ValueError("El esquema gold no coincide con el horizonte etiquetado")
    familias = familias_predictoras(horizonte)
    candidatas = [col for cols in familias.values() for col in cols]
    if len(candidatas) != len(set(candidatas)):
        raise ValueError("Una candidata aparece en más de una familia")
    if set(manifiesto.get("columnas_no_predictoras", [])) != set(NO_PREDICTORAS):
        raise ValueError("El manifiesto no enumera todas las exclusiones del modelo")
    if set(candidatas) & set(NO_PREDICTORAS) or set(candidatas) | set(NO_PREDICTORAS) != set(gold):
        raise ValueError("Las candidatas y exclusiones no particionan gold")
    return familias


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def auditar_traspaso(
    silver_path: Path = SILVER_INTEGRADO, gold_dir: Path = GOLD,
    catalog_path: Path = UBIGEO_CATALOG,
    historia_path: Path = SILVER_EPI_HISTORICO,
) -> dict:
    """Valida archivos persistidos, linaje y cobertura antes del modelado.

    Solo lee silver y gold. Devuelve cifras reproducibles para el notebook 23.
    """
    silver_path, gold_dir, catalog_path, historia_path = map(
        Path, (silver_path, gold_dir, catalog_path, historia_path),
    )
    panel = cargar_integrado(silver_path)
    cobertura_path = coverage_path(silver_path)
    cobertura = load_case_coverage(cobertura_path)
    if cobertura is None:
        raise ValueError("Falta la cobertura epidemiológica de silver")
    validate_complete(panel, cobertura)
    validate_geography(panel, catalog_path)
    manifiesto = json.loads((gold_dir / "manifest_fase6.json").read_text(encoding="utf-8"))
    if (manifiesto.get("fuente") != silver_path.name
            or manifiesto.get("sha256_fuente") != _sha256(silver_path)
            or manifiesto.get("sha256_cobertura") != _sha256(cobertura_path)
            or manifiesto.get("sha256_catalogo_geografico") != _sha256(catalog_path)):
        raise ValueError("El linaje de silver/cobertura/geografía no coincide con gold")
    regla = manifiesto.get("regla_brote")
    if not isinstance(regla, dict) or int(regla.get("minimo_casos", 0)) < 1:
        raise ValueError("Gold no tiene una regla de brote documentada")
    if (regla.get("fuente_historia") != historia_path.name
            or regla.get("sha256_fuente_historia") != _sha256(historia_path)):
        raise ValueError("La historia usada para etiquetar brote difiere del manifiesto")
    resumen = {"fuente": silver_path.name, "sha256_fuente": _sha256(silver_path),
               "regla_brote": regla, "horizontes": {}}
    etiquetas = []
    for h in HORIZONTES:
        registro = manifiesto.get("horizontes", {}).get(str(h), {})
        archivo = gold_dir / f"{silver_path.stem}_h{h}_gold.csv"
        if registro.get("archivo") != archivo.name or registro.get("sha256") != _sha256(archivo):
            raise ValueError(f"El hash o nombre de gold h={h} no coincide con el manifiesto")
        gold = pd.read_csv(archivo, dtype={"ubigeo": "string"},
                           parse_dates=["semana_inicio", "origen_inicio", "origen_cierre"])
        validacion = validar_gold(gold, panel, h, con_brote=True,
                                 minimo_casos_brote=regla["minimo_casos"])
        familias = validar_columnas_modelo(gold, manifiesto, h)
        candidatas = [col for cols in familias.values() for col in cols]
        resumen["horizontes"][str(h)] = {
            **validacion,
            "columnas": len(gold.columns),
            "candidatas": len(candidatas),
            "filas_candidatas_completas": int(gold[candidatas].notna().all(axis=1).sum()),
            "familias": familias,
            "nulos_por_familia": {
                nombre: int(gold[cols].isna().any(axis=1).sum())
                for nombre, cols in familias.items()
            },
            "positivos_brote": int(gold.brote.sum()),
            "positivos_por_anio": {
                str(y): int(n) for y, n in gold.groupby("anio").brote.sum().items()
            },
        }
        etiquetas.append(gold[CLAVE + ["brote", "umbral_brote_casos"]].sort_values(CLAVE).reset_index(drop=True))
    if not etiquetas[0].equals(etiquetas[1]):
        raise ValueError("Las etiquetas difieren entre horizontes")
    if resumen["horizontes"]["2"]["positivos_por_anio"] != manifiesto.get("positivos_brote_por_anio"):
        raise ValueError("Los conteos de brote difieren del manifiesto")
    return resumen


def resumir_ablaciones(metricas_dir: Path = DOCS / "feature_engineering" / "metricas") -> dict:
    """Resume las comparaciones ridge de conteos de fases 4 y 5 por horizonte.

    Delta MAE = modelo candidato menos su referencia; negativo favorece al
    candidato. Solo usa resultados ya medidos en los mismos cortes temporales.
    """
    metricas_dir = Path(metricas_dir)
    salidas = {}
    for fase, archivo in (("clima", "fase4_clima.json"),
                          ("sociodemografia", "fase5_sociodemografia.json")):
        resultados = json.loads((metricas_dir / archivo).read_text(encoding="utf-8"))["resultados"]
        por_modelo = {(int(r["horizonte"]), int(r["temporada"]), r["modelo"]): r
                      for r in resultados}
        if len(por_modelo) != len(resultados):
            raise ValueError(f"{archivo} tiene filas de ablación duplicadas")
        resumen_fase = {}
        for h in HORIZONTES:
            modelos = sorted({m for h0, _, m in por_modelo if h0 == h}
                            - {"persistencia", "historia_calendario"})
            resumen_h = {}
            for modelo in modelos:
                referencia = "mas_clima" if modelo.startswith("mas_clima_") else "historia_calendario"
                temporadas = sorted(y for h0, y, m in por_modelo if h0 == h and m == modelo)
                deltas = {}
                for y in temporadas:
                    base = por_modelo.get((h, y, referencia))
                    if base is None:
                        raise ValueError(f"{archivo}: falta referencia {referencia} para {h=}, {y=}")
                    candidato = por_modelo[(h, y, modelo)]
                    if any(candidato[c] != base[c] for c in (
                        "n_entrenamiento", "n_prueba", "primera_semana_prueba", "corte_ajuste"
                    )):
                        raise ValueError(f"{archivo}: {modelo} y {referencia} usan cortes/filas distintos")
                    deltas[str(y)] = candidato["mae_casos"] - base["mae_casos"]
                resumen_h[modelo] = {
                    "referencia": referencia,
                    "temporadas": temporadas,
                    "cortes_con_menor_mae": sum(delta < 0 for delta in deltas.values()),
                    "delta_mae_casos_por_temporada": {
                        y: round(delta, 6) for y, delta in deltas.items()
                    },
                }
            resumen_fase[str(h)] = resumen_h
        salidas[fase] = resumen_fase
    return salidas
