"""Contrato temporal de una fila objetivo para pronósticos semanales."""

import pandas as pd

CLAVE = ["ubigeo", "anio", "semana"]


def auditar_origen(panel: pd.DataFrame, horizonte: int = 4) -> pd.DataFrame:
    """Asigna a cada semana objetivo el último cierre semanal admisible.

    Exige un panel semanal continuo por distrito. Las primeras ``horizonte``
    filas de cada distrito no tienen origen dentro del panel y quedan en NaT.
    No modifica ``panel`` ni construye predictores.
    """
    if horizonte < 1:
        raise ValueError("El horizonte debe ser al menos una semana")
    faltan = set(CLAVE + ["semana_inicio"]) - set(panel.columns)
    if faltan:
        raise ValueError(f"Faltan columnas del contrato temporal: {sorted(faltan)}")
    if panel.empty or panel[CLAVE + ["semana_inicio"]].isna().any().any():
        raise ValueError("El panel está vacío o tiene llaves/fechas faltantes")
    if panel.duplicated(CLAVE).any():
        raise ValueError("Hay llaves distrito-año-semana duplicadas")

    audit = panel[CLAVE + ["semana_inicio"]].copy()
    audit["semana_inicio"] = pd.to_datetime(audit["semana_inicio"], errors="raise")
    if (audit["semana_inicio"].dt.weekday != 6).any():
        raise ValueError("semana_inicio debe ser domingo")
    audit = audit.sort_values(["ubigeo", "semana_inicio"]).reset_index(drop=True)
    salto = audit.groupby("ubigeo")["semana_inicio"].diff().dt.days.dropna()
    if not salto.eq(7).all():
        raise ValueError("El panel contiene huecos o fechas repetidas por distrito")

    audit["origen_inicio"] = audit.groupby("ubigeo")["semana_inicio"].shift(horizonte)
    distancia = (audit["semana_inicio"] - audit["origen_inicio"]).dt.days.dropna()
    if not distancia.eq(7 * horizonte).all():
        raise ValueError("El origen no está a la distancia temporal esperada")
    audit["origen_cierre"] = audit["origen_inicio"] + pd.Timedelta(days=6)
    return audit


def observaciones_disponibles(
    audit: pd.DataFrame,
    semana_observada: pd.Series,
    fecha_disponible: pd.Series,
) -> pd.Series:
    """Indica si cada observación existía al cierre del origen de su fila.

    ``semana_observada`` es el domingo inicial del dato y
    ``fecha_disponible`` es su publicación efectiva. Un origen ausente
    devuelve False.
    """
    requeridas = {"origen_inicio", "origen_cierre"}
    if not requeridas.issubset(audit):
        raise ValueError("La auditoría carece de fechas de origen")
    if len(audit) != len(semana_observada) or len(audit) != len(fecha_disponible):
        raise ValueError("Las fechas de observación no se alinean con las filas")
    semana = pd.to_datetime(pd.Series(semana_observada).reset_index(drop=True))
    disponible = pd.to_datetime(pd.Series(fecha_disponible).reset_index(drop=True))
    origen = audit.reset_index(drop=True)
    return (origen["origen_inicio"].notna()
            & semana.notna() & disponible.notna()
            & semana.le(origen["origen_inicio"])
            & disponible.le(origen["origen_cierre"]))
