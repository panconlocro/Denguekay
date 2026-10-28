"""Variables nuevas del bloque B (fase 2b del encargo de FE sobre E3·S4_s2), en memoria.

Cada variable de un origen ``o`` se toma del estado del distrito en la semana
de origen (la que cierra en ``origen_cierre``), calculado con semanas ≤ ``o``
(``diagnostico_inicios.estado_semanal``). Nada se escribe en ``data/``.

- **B1** dinámica espacial y **B3** historia propia ampliada: no dependen de
  ningún ajuste; se calculan una vez.
- **B2** distritos núcleo y **B5** anomalías climáticas: el ranking del
  núcleo y la climatología se ajustan con las semanas cerradas al ``corte`` de
  cada bloque (``preparar_bloque``).
- **B3**, casos de la temporada anterior: para la temporada 2017 se usa la
  temporada 2016 de la historia de la regla de brote (sin registro = cero);
  si un año necesario falta en la historia, queda nulo.
- **B4** línea base estacional: ``log(1 + umbral)`` de cada semana objetivo
  t+2, t+3 y t+4 con ``etiqueta_brote.umbral_brote_futuro`` (solo años
  previos; funciona también fuera del panel).
"""

import numpy as np
import pandas as pd

from src.modeling import diagnostico_inicios as di
from denguekay.model import horizon_strategies as eh
from src.modeling import preregistro_fe as pr
from src.modeling.etiqueta_brote import umbral_brote_futuro
from denguekay.data.calendar import mmwr_epi_week

COLUMNAS = {v["id"]: list(v["columnas"]) for v in pr.VARIANTES if v["bloque"] == "B"}
POR_BLOQUE = ("B2", "B5")
VENTANAS_B5 = {"o4_o": (0, 4), "o9_o5": (5, 9)}  # semanas antes de o, ambos extremos incluidos
CLIMA_B5 = ("temp_media", "temp_min", "hum_rel_media", "precip_total_mm")
COL_TEMPORADA_ANTERIOR = "propia_log_casos_temporada_anterior"


def semana_origen(origenes: pd.DataFrame) -> pd.Series:
    """Inicio (domingo) de la semana que cierra en ``origen_cierre``."""
    return pd.to_datetime(origenes.origen_cierre) - pd.Timedelta(days=6)


def temporada_anterior(serie: pd.DataFrame, historia: pd.DataFrame) -> pd.DataFrame:
    """``log(1 + casos)`` de la temporada anterior completa, por distrito y temporada.

    Usa la historia previa al panel (ausencias como cero) solo si los años
    que cubren esa temporada están en la historia; si no, nulo.
    """
    s = serie[["ubigeo", "anio", "semana", "casos_Dengue"]].copy()
    primero = int(s.anio.min())
    h = historia.loc[historia.anio.lt(primero) & historia.ubigeo.isin(set(s.ubigeo)),
                     ["ubigeo", "anio", "semana", "casos_Dengue"]]
    todo = pd.concat([h, s], ignore_index=True)
    todo["temporada"] = di.con_temporada(todo)
    totales = todo.groupby(["ubigeo", "temporada"]).casos_Dengue.sum()
    disponibles = set(h.anio) | set(s.anio)
    temporadas = sorted(set(di.con_temporada(s)))
    filas = []
    for u in sorted(s.ubigeo.unique()):
        for t in temporadas:
            previa = t - 1
            # La temporada previa abarca las semanas ≥ 35 de previa−1 y las < 35 de previa.
            valor = np.log1p(totales.get((u, previa), 0.0)) if {previa - 1, previa} <= disponibles else np.nan
            filas.append({"ubigeo": u, "temporada": t, COL_TEMPORADA_ANTERIOR: valor})
    return pd.DataFrame(filas)


def tabla_semanal(panel: pd.DataFrame, serie: pd.DataFrame, historia: pd.DataFrame,
                  corte: pd.Timestamp) -> pd.DataFrame:
    """B1, B2, B3 y B5 por distrito y semana ``w``, con datos de semanas ≤ ``w``.

    El núcleo (B2) y la climatología (B5) se ajustan con semanas cerradas al
    ``corte``; B1 y B3 no dependen del corte.
    """
    estado = di.estado_semanal(panel, serie, corte)
    estado = estado.sort_values(["ubigeo", "semana_inicio"]).reset_index(drop=True)
    grupo = estado.groupby("ubigeo")
    for c in CLIMA_B5:
        anomalia = f"{c}_anomalia"
        for nombre, (k0, k1) in VENTANAS_B5.items():
            estado[f"{anomalia}_{nombre}"] = (grupo[anomalia].shift(k0)
                                             .groupby(estado.ubigeo).rolling(k1 - k0 + 1).mean()
                                             .reset_index(level=0, drop=True))
    semanas = serie[["ubigeo", "semana_inicio", "anio", "semana"]].copy()
    semanas["semana_inicio"] = pd.to_datetime(semanas.semana_inicio)
    semanas["temporada"] = di.con_temporada(semanas)
    estado = estado.drop(columns=[COL_TEMPORADA_ANTERIOR]).merge(
        semanas[["ubigeo", "semana_inicio", "temporada"]], on=["ubigeo", "semana_inicio"], how="left",
        validate="one_to_one")
    estado = estado.merge(temporada_anterior(serie, historia), on=["ubigeo", "temporada"], how="left",
                          validate="many_to_one")
    columnas = [c for f in ("B1", "B2", "B3", "B5") for c in COLUMNAS[f]]
    return estado[["ubigeo", "semana_inicio", *columnas]]


def linea_base(origenes: pd.DataFrame, panel: pd.DataFrame, historia: pd.DataFrame, regla: dict) -> pd.DataFrame:
    """B4: ``log(1 + umbral)`` de las semanas objetivo o+h para h=2, 3 y 4 (una columna por h)."""
    base = semana_origen(origenes)
    salida = pd.DataFrame(index=origenes.index)
    for h in eh.STRATEGY_HORIZONS:
        destino = base + pd.Timedelta(weeks=h)
        cal = mmwr_epi_week(pd.Series(destino.to_numpy()))
        objetivos = pd.DataFrame({"ubigeo": origenes.ubigeo.to_numpy(), "anio": cal.anio_epi.to_numpy(),
                                  "semana": cal.semana_epi.to_numpy()}, index=origenes.index)
        umbral = umbral_brote_futuro(panel, historia, objetivos, multiplicador=regla["multiplicador"],
                                     anios_previos=regla["anios_previos"])
        salida[f"linea_base_log_umbral_h{h}"] = np.log1p(umbral.to_numpy())
    return salida


def agregar(origenes: pd.DataFrame, semanal: pd.DataFrame, columnas: list[str]) -> pd.DataFrame:
    """Une columnas de la tabla semanal a los orígenes por distrito y semana de origen (mismo índice)."""
    clave = pd.DataFrame({"ubigeo": origenes.ubigeo.astype("string").to_numpy(),
                          "semana_inicio": semana_origen(origenes).to_numpy()}, index=origenes.index)
    unido = clave.merge(semanal[["ubigeo", "semana_inicio", *columnas]], on=["ubigeo", "semana_inicio"],
                        how="left", validate="many_to_one")
    unido.index = origenes.index
    return origenes.drop(columns=[c for c in columnas if c in origenes]).join(unido[columnas])


class VariablesInicio:
    """Calcula y guarda en memoria las tablas semanales por corte."""

    def __init__(self, panel: pd.DataFrame, serie: pd.DataFrame, historia: pd.DataFrame, regla: dict):
        # Igual que construir_etiquetas: la historia solo aporta años anteriores al panel.
        historia = historia.loc[historia.anio.lt(int(panel.anio.min()))]
        self.panel, self.serie, self.historia, self.regla = panel, serie, historia, regla
        self._por_corte: dict[pd.Timestamp, pd.DataFrame] = {}

    def semanal(self, corte: pd.Timestamp) -> pd.DataFrame:
        corte = pd.Timestamp(corte)
        if corte not in self._por_corte:
            self._por_corte[corte] = tabla_semanal(self.panel, self.serie, self.historia, corte)
        return self._por_corte[corte]

    def origenes(self, base: pd.DataFrame, familias: list[str], corte_referencia: pd.Timestamp) -> pd.DataFrame:
        """Orígenes con las columnas de las familias pedidas.

        B2 y B5 se calculan aquí con ``corte_referencia`` solo para ubicar los
        nulos de arranque; en el experimento, ``preparar_bloque`` los reemplaza
        por los del corte de cada bloque.
        """
        salida = base
        semanal = [c for f in familias if f != "B4" for c in COLUMNAS[f]]
        if semanal:
            salida = agregar(salida, self.semanal(corte_referencia), semanal)
        if "B4" in familias:
            salida = salida.join(linea_base(salida, self.panel, self.historia, self.regla))
        return salida

    def preparar_bloque(self, familias: list[str]):
        """``preparar_bloque`` para ``predecir_e3``: recalcula B2/B5 con el corte del bloque."""
        columnas = [c for f in familias if f in POR_BLOQUE for c in COLUMNAS[f]]
        if not columnas:
            return None

        def preparar(origenes: pd.DataFrame, corte: pd.Timestamp) -> pd.DataFrame:
            return agregar(origenes, self.semanal(corte), columnas)
        return preparar
