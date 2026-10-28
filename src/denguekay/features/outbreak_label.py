"""Retrospective labels of district weeks with a high case level.

The seasonal rule is parametrised explicitly: no threshold choice is implied by
importing this module. The history of the Excel file before the panel is sparse
and its absences are read as zero, as in the EDA's exploratory endemic channel;
that does not prove zero notification.
"""

from dataclasses import dataclass

import numpy as np
import pandas as pd

from denguekay.data.validation.forecast_contract import KEY


@dataclass(frozen=True)
class SeasonalOutbreakConfig:
    """Explicit parameters of the five-year seasonal rule."""

    multiplicador: float
    anios_previos: int = 5
    minimo_casos: int = 1


def _validate_cases(data: pd.DataFrame, name: str) -> pd.DataFrame:
    missing = set(KEY + ["casos_Dengue"]) - set(data)
    if missing:
        raise ValueError(f"{name} carece de columnas: {sorted(missing)}")
    if data.empty or data[KEY].isna().any().any():
        raise ValueError(f"{name} vacío o con llaves incompletas/duplicadas")
    clean = data[KEY + ["casos_Dengue"]].copy()
    clean["ubigeo"] = clean.ubigeo.astype("string").str.zfill(6)
    if not clean.ubigeo.str.fullmatch(r"\d{6}").all():
        raise ValueError(f"{name} contiene UBIGEO inválido")
    for field in ("anio", "semana"):
        clean[field] = pd.to_numeric(clean[field], errors="raise")
    if (clean["anio"] % 1 != 0).any() or (clean["semana"] % 1 != 0).any() or not clean.semana.between(1, 53).all():
        raise ValueError(f"{name} contiene años o semanas inválidos")
    clean["anio"] = clean.anio.astype(int)
    clean["semana"] = clean.semana.astype(int)
    if clean.duplicated(KEY).any():
        raise ValueError(f"{name} contiene llaves duplicadas")
    clean["casos_Dengue"] = pd.to_numeric(clean.casos_Dengue, errors="raise")
    if clean.casos_Dengue.isna().any() or not np.isfinite(clean.casos_Dengue.to_numpy(float)).all() or (clean.casos_Dengue < 0).any() or (clean.casos_Dengue % 1 != 0).any():
        raise ValueError(f"{name} contiene casos inválidos")
    return clean


def label_seasonal_outbreak(
    panel: pd.DataFrame, history: pd.DataFrame, *,
    multiplicador: float, anios_previos: int = 5, minimo_casos: int = 1,
) -> pd.DataFrame:
    """Flag each week with cases > mean + k·SD of the same week in previous years.

    It uses the ``anios_previos`` previous years of the same UBIGEO and
    epidemiological week (sample SD, ``ddof=1``). Each year is computed only
    with strictly earlier years. Week 53 is added to week 52 to build the
    reference, following the EDA's convention; the target row keeps its original
    week. Returns the threshold and the label aligned with ``panel``.
    ``minimo_casos`` is an explicit floor to flag positive weeks.
    """
    if not np.isfinite(multiplicador) or multiplicador <= 0:
        raise ValueError("multiplicador debe ser positivo y finito")
    if (not isinstance(anios_previos, int) or not isinstance(minimo_casos, int)
            or anios_previos < 2 or minimo_casos < 1):
        raise ValueError("anios_previos >= 2 y minimo_casos >= 1 son obligatorios")
    actual = _validate_cases(panel, "panel")
    previous_value = _validate_cases(history, "historia")
    first, last = int(actual.anio.min()), int(actual.anio.max())
    if set(actual.anio) != set(range(first, last + 1)):
        raise ValueError("El panel tiene años completos ausentes en el periodo de etiquetas")
    if not previous_value.anio.lt(first).all():
        raise ValueError("La historia debe terminar antes del primer año del panel")
    districts = sorted(actual.ubigeo.unique())
    previous_value = previous_value.loc[previous_value.ubigeo.isin(districts)]
    if previous_value.empty:
        raise ValueError("La historia no contiene distritos del panel")
    required_years = set(range(first - anios_previos, first))
    if not required_years.issubset(set(previous_value.anio)):
        raise ValueError(f"Faltan años de historia en los distritos del panel: {sorted(required_years - set(previous_value.anio))}")
    everything = pd.concat([previous_value, actual], ignore_index=True)
    everything["semana_ref"] = everything.semana.clip(upper=52)
    yearly = everything.groupby(["ubigeo", "anio", "semana_ref"], as_index=False).casos_Dengue.sum()
    index = pd.MultiIndex.from_product(
        [districts, range(1, 53)], names=["ubigeo", "semana_ref"],
    )
    matrix = yearly.pivot(index=["ubigeo", "semana_ref"], columns="anio", values="casos_Dengue")
    matrix = matrix.reindex(index=index, columns=range(first - anios_previos, last + 1)).fillna(0)
    outputs = []
    for year in sorted(actual.anio.unique()):
        window = matrix[list(range(year - anios_previos, year))]
        threshold = window.mean(axis=1) + multiplicador * window.std(axis=1, ddof=1)
        outputs.append(threshold.rename(year))
    table = pd.concat(outputs, axis=1).stack().rename("umbral_brote_casos").reset_index()
    table = table.rename(columns={"level_2": "anio"})
    keys = actual[KEY].assign(semana_ref=actual.semana.clip(upper=52))
    output = keys.merge(table, on=["ubigeo", "anio", "semana_ref"], how="left", validate="many_to_one", sort=False)
    if len(output) != len(panel) or output.umbral_brote_casos.isna().any():
        raise ValueError("No se pudo asignar umbral a todas las distrito-semanas")
    output["brote"] = ((actual.casos_Dengue.to_numpy() > output.umbral_brote_casos.to_numpy())
                       & (actual.casos_Dengue.to_numpy() >= minimo_casos)).astype("int8")
    return output[KEY + ["umbral_brote_casos", "brote"]]


def future_outbreak_threshold(
    panel: pd.DataFrame, history: pd.DataFrame, targets: pd.DataFrame, *,
    multiplicador: float, anios_previos: int = 5,
) -> pd.Series:
    """Outbreak threshold of any target week, inside or outside the panel.

    Same rule as ``label_seasonal_outbreak``: same epidemiological week of the
    ``anios_previos`` previous years (53 is added to 52), mean + ``multiplicador``
    · sample SD (``ddof=1``), absences of the history before the panel as zero.
    It only uses years before the target week's year, so it works for weeks not
    in the panel yet (e.g. the first weeks of 2026 issued in December 2025).

    ``targets`` holds ``ubigeo``, ``anio`` and ``semana``; it returns a series
    aligned with its rows. It fails if a needed year is not covered: a panel year
    must reach at least the reference week, and the years before the panel must
    exist in ``history``.
    """
    if not np.isfinite(multiplicador) or multiplicador <= 0:
        raise ValueError("multiplicador debe ser positivo y finito")
    if not isinstance(anios_previos, int) or anios_previos < 2:
        raise ValueError("anios_previos >= 2 es obligatorio")
    actual = _validate_cases(panel, "panel")
    previous_value = _validate_cases(history, "historia")
    destination = targets[["ubigeo", "anio", "semana"]].copy()
    destination["ubigeo"] = destination.ubigeo.astype("string").str.zfill(6)
    destination["anio"] = pd.to_numeric(destination.anio, errors="raise").astype(int)
    destination["semana"] = pd.to_numeric(destination.semana, errors="raise").astype(int)
    if not destination.semana.between(1, 53).all():
        raise ValueError("objetivos contiene semanas inválidas")
    first, last = int(actual.anio.min()), int(actual.anio.max())
    if not previous_value.anio.lt(first).all():
        raise ValueError("La historia debe terminar antes del primer año del panel")
    districts = sorted(actual.ubigeo.unique())
    if not destination.ubigeo.isin(districts).all():
        raise ValueError("Hay objetivos de distritos fuera del panel")
    previous_value = previous_value.loc[previous_value.ubigeo.isin(districts)]
    destination["semana_ref"] = destination.semana.clip(upper=52)
    needed = {a for y in destination.anio.unique() for a in range(int(y) - anios_previos, int(y))}
    missing_history = sorted(a for a in needed if a < first and a not in set(previous_value.anio))
    if missing_history:
        raise ValueError(f"Faltan años de historia: {missing_history}")
    if max(needed) > last:
        raise ValueError("Un objetivo necesita años posteriores al último año del panel")
    covered = actual.assign(semana_ref=actual.semana.clip(upper=52)).groupby("anio").semana_ref.max()
    uses_last = destination[destination.anio.gt(last)]
    if not uses_last.empty and uses_last.semana_ref.max() > covered.loc[last]:
        raise ValueError("El último año del panel no cubre la semana de referencia de algún objetivo")
    everything = pd.concat([previous_value, actual], ignore_index=True)
    everything["semana_ref"] = everything.semana.clip(upper=52)
    yearly = everything.groupby(["ubigeo", "anio", "semana_ref"], as_index=False).casos_Dengue.sum()
    index = pd.MultiIndex.from_product([districts, range(1, 53)], names=["ubigeo", "semana_ref"])
    # Same columns as label_seasonal_outbreak to get exactly the same numbers.
    years = range(min(first - anios_previos, min(needed)), last + 1)
    matrix = yearly.pivot(index=["ubigeo", "semana_ref"], columns="anio", values="casos_Dengue")
    matrix = matrix.reindex(index=index, columns=years).fillna(0)
    outputs = []
    for year in sorted(destination.anio.unique()):
        window = matrix[list(range(year - anios_previos, year))]
        threshold = window.mean(axis=1) + multiplicador * window.std(axis=1, ddof=1)
        outputs.append(threshold.rename(year))
    table = pd.concat(outputs, axis=1).stack().rename("umbral_brote_casos").reset_index()
    table = table.rename(columns={"level_2": "anio"})
    output = destination.merge(table, on=["ubigeo", "anio", "semana_ref"], how="left", validate="many_to_one", sort=False)
    if len(output) != len(destination) or output.umbral_brote_casos.isna().any():
        raise ValueError("No se pudo asignar umbral a todos los objetivos")
    return pd.Series(output.umbral_brote_casos.to_numpy(), index=targets.index, name="umbral_brote_casos")
