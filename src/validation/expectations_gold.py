"""Suite de Great Expectations para los gold por horizonte (h=2 y h=4).

Declara en forma auditable el contrato que el entrenamiento asume: esquema
exacto, llave única, UBIGEO del catálogo, objetivos válidos, rangos físicos
o lógicos de las variables y ausencia de fuga temporal (la semana objetivo
siempre empieza después del cierre del origen). Las comprobaciones estrictas
de arranque estructural siguen en ``src.modeling.train.preparar_gold``.
"""

import great_expectations as gx

from src.modeling.features import columnas_gold
from src.validation.contrato_pronostico import CLAVE

# Proporción mínima de filas con predictores poblados. Los nulos permitidos
# son solo el arranque estructural de cada distrito (menos del 2 % hoy).
MINIMO_PREDICTORES_POBLADOS = 0.95


def expectativas_gold(horizonte: int, ubigeos: list[str]) -> list:
    """Devuelve la lista de expectativas de ``gold_h{horizonte}``."""
    E = gx.expectations
    h = horizonte
    columnas = columnas_gold(h, con_brote=True)
    exp = [
        E.ExpectTableColumnsToMatchSet(column_set=columnas, exact_match=True),
        E.ExpectTableRowCountToBeBetween(min_value=1),
        E.ExpectCompoundColumnsToBeUnique(column_list=CLAVE),
        E.ExpectColumnValuesToMatchRegex(column="ubigeo", regex=r"^\d{6}$"),
        E.ExpectColumnValuesToBeInSet(column="ubigeo", value_set=ubigeos),
        E.ExpectColumnUniqueValueCountToBeBetween(
            column="ubigeo", min_value=len(ubigeos), max_value=len(ubigeos)),
        E.ExpectColumnValuesToBeBetween(column="anio", min_value=2017),
        E.ExpectColumnValuesToBeBetween(column="semana", min_value=1, max_value=53),
        # Objetivos y metadatos de la etiqueta: nunca nulos.
        E.ExpectColumnValuesToBeBetween(column="casos_Dengue", min_value=0),
        E.ExpectColumnValuesToBeBetween(column="umbral_brote_casos", min_value=0),
        E.ExpectColumnValuesToBeInSet(column="brote", value_set=[0, 1]),
        # Sin fuga temporal: la semana objetivo empieza después del cierre del origen.
        E.ExpectColumnPairValuesAToBeGreaterThanB(
            column_A="semana_inicio", column_B="origen_cierre",
            ignore_row_if="either_value_is_missing"),
    ]
    siempre_pobladas = [
        *CLAVE, "provincia", "distrito", "distrito_key", "semana_inicio",
        "casos_Dengue", "brote", "umbral_brote_casos",
        "semana_epi_seno", "semana_epi_coseno",
        *(c for c in columnas if c.endswith(("_2017", "_anual"))),
    ]
    exp += [E.ExpectColumnValuesToNotBeNull(column=c) for c in dict.fromkeys(siempre_pobladas)]

    # Predictores rezagados: nulos solo en el arranque de cada distrito.
    rezagadas = [
        "origen_inicio", "origen_cierre",
        f"casos_lag_{h}", f"casos_lag_{h + 1}", f"casos_media_4_h{h}",
        f"casos_semanas_positivas_4_h{h}", f"vecinos_media_casos_knn5_h{h}",
        f"vecinos_frac_con_casos_knn5_h{h}", f"provincia_otros_casos_h{h}",
        f"provincia_otros_frac_con_casos_h{h}", f"region_otros_casos_h{h}",
        f"region_otros_frac_con_casos_h{h}", f"hum_rel_media_media5_h{h}",
        f"precip_total_mm_media5_h{h}",
    ]
    exp += [E.ExpectColumnValuesToNotBeNull(column=c, mostly=MINIMO_PREDICTORES_POBLADOS)
            for c in rezagadas]

    # Rangos lógicos y físicos (los nulos se ignoran en estas expectativas).
    conteos = [f"casos_lag_{h}", f"casos_lag_{h + 1}", f"casos_media_4_h{h}",
               f"vecinos_media_casos_knn5_h{h}", f"provincia_otros_casos_h{h}",
               f"region_otros_casos_h{h}", f"precip_total_mm_media5_h{h}"]
    exp += [E.ExpectColumnValuesToBeBetween(column=c, min_value=0) for c in conteos]
    exp += [
        E.ExpectColumnValuesToBeBetween(column=f"casos_semanas_positivas_4_h{h}", min_value=0, max_value=4),
        E.ExpectColumnValuesToBeBetween(column="semana_epi_seno", min_value=-1, max_value=1),
        E.ExpectColumnValuesToBeBetween(column="semana_epi_coseno", min_value=-1, max_value=1),
        E.ExpectColumnValuesToBeBetween(column=f"hum_rel_media_media5_h{h}", min_value=0, max_value=100),
    ]
    fracciones = [c for c in columnas if c.startswith("fraccion_") or "_frac_" in c]
    exp += [E.ExpectColumnValuesToBeBetween(column=c, min_value=0, max_value=1) for c in fracciones]
    exp += [E.ExpectColumnValuesToBeBetween(column=c, min_value=0, strict_min=True)
            for c in ("log_poblacion_censo_2017", "log_poblacion_anual")]
    return exp
