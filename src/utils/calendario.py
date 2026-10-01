"""Calendario epidemiológico compartido por el pipeline, el EDA y el modelado."""

import pandas as pd


def semana_epi_mmwr(semana_inicio: pd.Series) -> pd.DataFrame:
    """Devuelve año y semana MMWR para domingos, conservando el índice.

    Las semanas van de domingo a sábado. La semana 1 es la primera con al
    menos cuatro días en el año nuevo: contiene su primer miércoles.
    No usa la numeración ISO, cuyo inicio de semana es lunes.
    """
    fechas = pd.to_datetime(semana_inicio)
    if (fechas.dt.weekday != 6).any():
        raise ValueError("semana_inicio debe ser domingo en todas las filas")
    anio = (fechas + pd.Timedelta(days=3)).dt.year
    enero_1 = pd.to_datetime(anio.astype(str) + "-01-01")
    domingo_0 = enero_1 - pd.to_timedelta((enero_1.dt.weekday + 1) % 7, unit="D")
    inicio_s1 = domingo_0.where(domingo_0 + pd.Timedelta(days=3) >= enero_1,
                                domingo_0 + pd.Timedelta(days=7))
    semana = (fechas - inicio_s1).dt.days // 7 + 1
    return pd.DataFrame({"anio_epi": anio.astype(int), "semana_epi": semana.astype(int)},
                        index=semana_inicio.index)
