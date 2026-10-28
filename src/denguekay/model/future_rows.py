"""Future rows in memory, with the modelling functions and calendar."""

import numpy as np
import pandas as pd

from denguekay.features.gold import SOCIO_2017_DATE, HORIZONS
from denguekay.features.history_calendar import build_history_calendar
from denguekay.features.sociodemographics import reference_2017, build_sociodemography
from denguekay.evaluation.compact_validation import variantes_compactas
from denguekay.data.calendar import mmwr_epi_week
from denguekay.data.validation.forecast_contract import KEY, audit_origin, available_observations


def build_future_rows(panel, horizon, *, columns=None, cutoff_date=None, reference=None):
    """Forecast the target located exactly h weeks after the origin.

    Only the calendar is extended, with NaN cases. It reuses the lags and the
    fixed sociodemography; it computes neither climate nor future yearly
    population. The panel is cut at the requested close BEFORE building
    variables or reference values. Returns (complete rows, reasons of the
    unavailable rows).
    """
    # Operations only serve the horizons with persisted gold (h=2 and h=4);
    # the others exist only in memory for experiments.
    if horizon not in HORIZONS:
        raise ValueError("La inferencia futura solo admite los horizontes con gold persistido")
    variants = variantes_compactas(horizon)
    columns = columns or variants["base_6_poblacion_2017"]
    allowed = set(variants["base_6_poblacion_2017"])
    if not set(columns) <= allowed:
        raise ValueError("La inferencia futura solo admite las variantes compactas del protocolo")
    if panel.empty or not panel.ubigeo.map(lambda x: isinstance(x, str)).all():
        raise ValueError("El panel debe contener UBIGEO como texto")
    if not panel.ubigeo.str.fullmatch(r"[0-9]{6}").all() or panel.duplicated(KEY).any():
        raise ValueError("UBIGEO inválido o llaves repetidas en el panel")
    data = panel.copy()
    data["semana_inicio"] = pd.to_datetime(data.semana_inicio)
    cutoff = pd.Timestamp(cutoff_date) if cutoff_date is not None else data.semana_inicio.max() + pd.Timedelta(days=6)
    if pd.isna(cutoff) or cutoff.dayofweek != 5:
        raise ValueError("El corte de datos debe ser un cierre semanal de sábado")
    origin = cutoff.normalize() - pd.Timedelta(days=6)
    data = data.loc[(data.semana_inicio + pd.Timedelta(days=6)).le(cutoff)].copy()
    if data.empty:
        raise ValueError("No hay observaciones cerradas al corte solicitado")
    calendar = mmwr_epi_week(data.semana_inicio)
    if not (calendar.anio_epi.eq(data.anio).all() and calendar.semana_epi.eq(data.semana).all()):
        raise ValueError("El panel no coincide con el calendario MMWR")
    ref = (reference if reference is not None else reference_2017(data)) if "log_poblacion_censo_2017" in columns else None
    rows, unavailable = [], []
    target = origin + pd.Timedelta(weeks=horizon)
    target_cal = mmwr_epi_week(pd.Series([target])).iloc[0]
    for ubigeo, district in data.groupby("ubigeo", sort=True):
        reason = None
        if district.semana_inicio.max() != origin:
            reason = "El distrito no tiene observación para la semana de origen"
        elif ref is not None and not ref.ubigeo.eq(ubigeo).any():
            reason = "No hay referencia censal de 2017 para el distrito"
        else:
            dates = pd.date_range(district.semana_inicio.max() + pd.Timedelta(weeks=1), target, freq="7D")
            cal = mmwr_epi_week(pd.Series(dates))
            future = pd.DataFrame({"ubigeo": ubigeo, "anio": cal.anio_epi,
                                    "semana": cal.semana_epi, "semana_inicio": dates,
                                    "casos_Dengue": np.nan})
            extended = pd.concat([district, future], ignore_index=True)
            try:
                audit = audit_origin(extended, horizon)
            except ValueError:
                reason = "Historia semanal incompleta o fechas repetidas en el distrito"
            if reason is None:
                history = build_history_calendar(extended, horizon, allow_missing=True)
                if ref is not None:
                    socio = build_sociodemography(extended, horizon,
                        ref.loc[ref.ubigeo.eq(ubigeo)], SOCIO_2017_DATE)
                    history = history.merge(socio[KEY + ["log_poblacion_censo_2017"]],
                                               on=KEY, validate="one_to_one")
                row = history.loc[history.semana_inicio.eq(target)].copy()
                if len(row) != 1 or row[columns].isna().any().any() or not np.isfinite(row[columns].to_numpy(float)).all():
                    reason = "No hay historia suficiente o referencia disponible para las variables del modelo"
                else:
                    audited_origin = audit.loc[audit.semana_inicio.eq(target)]
                    if not available_observations(audited_origin,
                            pd.Series([origin]), pd.Series([cutoff])).all():
                        raise ValueError("La información no estaba disponible al origen del pronóstico")
                    if not row.origen_cierre.eq(cutoff).all():
                        raise ValueError("La fila futura no respeta el cierre de origen solicitado")
                    rows.append(row)
        if reason:
            unavailable.append({"ubigeo": ubigeo, "horizonte": horizon,
                "anio": int(target_cal.anio_epi), "semana": int(target_cal.semana_epi),
                "semana_inicio": str(target.date()), "disponible": False, "motivo": reason})
    fields = [*KEY, "semana_inicio", "origen_inicio", "origen_cierre", *columns]
    output = pd.concat(rows, ignore_index=True)[fields] if rows else pd.DataFrame(columns=fields)
    return output, unavailable
