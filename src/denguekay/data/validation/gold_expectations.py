"""Great Expectations suite for the persisted gold and for the gold before the cleanup.

Declares, in an auditable way, the contract training relies on: exact schema,
unique key, UBIGEO from the catalogue, valid targets, physical or logical
ranges of the variables and no temporal leakage (the target week always
starts after the origin close). The strict structural start-up checks stay in
``denguekay.model.train.prepare_gold``.
"""

import great_expectations as gx

from denguekay.features.climate import D3_COLUMNS
from denguekay.features.gold import ONSET_COLUMNS, gold_columns, persisted_columns
from denguekay.data.validation.forecast_contract import KEY

# Minimum share of rows with populated predictors. The only nulls allowed
# are the structural start-up of each district (under 2 % today).
MIN_POPULATED_PREDICTORS = 0.95


def expectations_for_gold(horizon: int, ubigeos: list[str], *, persisted: bool = True) -> list:
    """Return the list of expectations of ``gold_h{horizon}``.

    With ``persisted=False``, those of the schema with all the candidates (backup and test fixtures).
    """
    E = gx.expectations
    h = horizon
    columns = persisted_columns(h) if persisted else gold_columns(h, with_outbreak=True)
    exp = [
        E.ExpectTableColumnsToMatchSet(column_set=columns, exact_match=True),
        E.ExpectTableRowCountToBeBetween(min_value=1),
        E.ExpectCompoundColumnsToBeUnique(column_list=KEY),
        E.ExpectColumnValuesToMatchRegex(column="ubigeo", regex=r"^\d{6}$"),
        E.ExpectColumnValuesToBeInSet(column="ubigeo", value_set=ubigeos),
        E.ExpectColumnUniqueValueCountToBeBetween(
            column="ubigeo", min_value=len(ubigeos), max_value=len(ubigeos)),
        E.ExpectColumnValuesToBeBetween(column="anio", min_value=2017),
        E.ExpectColumnValuesToBeBetween(column="semana", min_value=1, max_value=53),
        # Targets and label metadata: never null.
        E.ExpectColumnValuesToBeBetween(column="casos_Dengue", min_value=0),
        E.ExpectColumnValuesToBeBetween(column="umbral_brote_casos", min_value=0),
        E.ExpectColumnValuesToBeInSet(column="brote", value_set=[0, 1]),
        # No temporal leakage: the target week starts after the origin close.
        E.ExpectColumnPairValuesAToBeGreaterThanB(
            column_A="semana_inicio", column_B="origen_cierre",
            ignore_row_if="either_value_is_missing"),
    ]
    always_populated = [
        *KEY, "provincia", "distrito", "distrito_key", "semana_inicio",
        "casos_Dengue", "brote", "umbral_brote_casos",
        "semana_epi_seno", "semana_epi_coseno",
        *(c for c in columns if c.endswith(("_2017", "_anual"))),
    ]
    exp += [E.ExpectColumnValuesToNotBeNull(column=c) for c in dict.fromkeys(always_populated) if c in columns]

    # Lagged predictors: null only at each district's start-up.
    lagged = [
        "origen_inicio", "origen_cierre",
        f"casos_lag_{h}", f"casos_lag_{h + 1}", f"casos_media_4_h{h}",
        f"casos_semanas_positivas_4_h{h}", f"vecinos_media_casos_knn5_h{h}",
        f"vecinos_frac_con_casos_knn5_h{h}", f"provincia_otros_casos_h{h}",
        f"provincia_otros_frac_con_casos_h{h}", f"region_otros_casos_h{h}",
        f"region_otros_frac_con_casos_h{h}", f"hum_rel_media_media5_h{h}",
        f"precip_total_mm_media5_h{h}", *ONSET_COLUMNS,
    ]
    exp += [E.ExpectColumnValuesToNotBeNull(column=c, mostly=MIN_POPULATED_PREDICTORS)
            for c in lagged if c in columns]

    # Logical and physical ranges (these expectations ignore nulls).
    counts = [f"casos_lag_{h}", f"casos_lag_{h + 1}", f"casos_media_4_h{h}",
               f"vecinos_media_casos_knn5_h{h}", f"provincia_otros_casos_h{h}",
               f"region_otros_casos_h{h}", f"precip_total_mm_media5_h{h}", "propia_log_casos_temporada_anterior"]
    exp += [E.ExpectColumnValuesToBeBetween(column=c, min_value=0) for c in counts if c in columns]
    exp += [
        E.ExpectColumnValuesToBeBetween(column=f"casos_semanas_positivas_4_h{h}", min_value=0, max_value=4),
        E.ExpectColumnValuesToBeBetween(column="semana_epi_seno", min_value=-1, max_value=1),
        E.ExpectColumnValuesToBeBetween(column="semana_epi_coseno", min_value=-1, max_value=1),
        E.ExpectColumnValuesToBeBetween(column=f"hum_rel_media_media5_h{h}", min_value=0, max_value=100),
    ]
    # d3 (v3): ERA5-Land weekly mean temperature windows at the origin; the silver starts in 2000, so the only nulls
    # are the rows without an origin (each district's first weeks), as the lagged predictors above.
    d3 = [c for c in D3_COLUMNS if c in columns]
    exp += [E.ExpectColumnValuesToNotBeNull(column=c, mostly=MIN_POPULATED_PREDICTORS) for c in d3]
    exp += [E.ExpectColumnValuesToBeBetween(column=c, min_value=-20, max_value=50) for c in d3]
    fractions = [c for c in columns if c.startswith("fraccion_") or "_frac_" in c]
    exp += [E.ExpectColumnValuesToBeBetween(column=c, min_value=0, max_value=1) for c in fractions]
    exp += [E.ExpectColumnValuesToBeBetween(column=c, min_value=0, strict_min=True)
            for c in ("log_poblacion_censo_2017", "log_poblacion_anual") if c in columns]
    if persisted:
        exp.append(E.ExpectColumnValuesToBeBetween(column="propia_semanas_desde_ultimo_caso", min_value=0, max_value=52))
    return exp
