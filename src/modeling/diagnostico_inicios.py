"""Diagnóstico de inicios de brote (fase 1 del encargo de FE sobre E3·S4_s2).

Describe qué pasa en las semanas previas a los **inicios limpios** del
periodo de diseño (temporadas 2017–2021; partición A acordada con Rosa)
frente a semanas comparables sin inicio. Es descriptivo: diferencias medias
con IC bootstrap por episodio, sin p-valores ni lenguaje causal.

Todo se calcula en memoria. El «estado» de un distrito en la semana ``w``
usa solo datos de semanas ≤ ``w``; el perfil de un inicio en ``s`` mira
``w = s − k`` con ``k = 1..12``. La climatología (anomalías), el ranking de
distritos núcleo y los terciles se ajustan **solo con el periodo de diseño**
y sirven únicamente para este diagnóstico: en la fase 2 se recalculan con el
entrenamiento de cada bloque.

Controles (dos tipos, ambos con la misma semana epidemiológica, dentro del
periodo de diseño, sin ``brote`` en la semana ni en las 8 previas y con esas
8 semanas observadas):

- ``semana``: cualquier distrito, cualquier temporada del periodo.
- ``distrito``: el mismo distrito en otras temporadas; si tiene menos de
  ``MIN_CONTROLES_DISTRITO``, distritos del mismo tercil de casos históricos.

Regla de consistencia (fijada antes de ver resultados), por variable y
ventana a priori, con la diferencia media inicio − control promediada en la
ventana:

- **observada**: el signo es el mismo en las 4 celdas (2017 y 2018–2021 ×
  control ``semana`` y ``distrito``) y el IC95 del periodo completo excluye
  el 0 con ambos controles;
- **hipótesis (solo 2017)**: no cumple lo anterior, pero en 2017 el signo
  coincide con ambos controles y su IC95 de 2017 excluye el 0 con ambos;
- **no observada**: el resto;
- **no evaluable**: falta alguna de esas celdas (p. ej. la temporada anterior
  no existe para 2017).
"""

import numpy as np
import pandas as pd

from denguekay.data.seasons import assign_season
from src.modeling import diagnostico_arquitectura as diag
from denguekay.features.climate import fit_climatology
from src.modeling.protocolo_arquitectura import bootstrap_estratificado
from denguekay.model.train import SEASON_START_WEEK
from denguekay.features.neighbors import geographic_catalog, neighborhood_matrix

TEMPORADAS_DISENO = (2017, 2018, 2019, 2020, 2021)
PERIODOS = {"2017": (2017,), "2018_2021": (2018, 2019, 2020, 2021)}
REZAGOS = tuple(range(1, 13))
SIN_BROTE_PREVIO = diag.SIN_BROTE_PREVIO
MIN_CONTROLES_DISTRITO = 2
N_NUCLEO = 5
K_VECINOS = 5
CLIMA = ("temp_media", "temp_min", "precip_total_mm", "hum_rel_media")
# Ventanas a priori (k = semanas antes del inicio, ambos extremos incluidos).
# origen_2_4: lo que ven los orígenes de h=2, 3 y 4 cuando el objetivo es la
# semana de inicio; previa_5_8: el contexto anterior. Clima: acumulados de
# 4–8 y 8–12 semanas acordados con Rosa (sin elegir el rezago que más resalte).
VENTANAS = {"origen_2_4": (2, 4), "previa_5_8": (5, 8), "clima_4_8": (4, 8), "clima_8_12": (8, 12)}

FAMILIAS = {
    "vecinos": ["vecinos_log_media_casos", "vecinos_frac_con_casos", "vecinos_frac_en_brote",
                "vecinos_n_casos_nuevos", "vecinos_log_media_casos_cambio_1", "vecinos_log_media_casos_cambio_4"],
    "jerarquia": ["provincia_log_otros_casos", "provincia_otros_frac_con_casos", "provincia_otros_frac_en_brote",
                  "provincia_log_otros_casos_cambio_1", "provincia_log_otros_casos_cambio_4",
                  "region_log_otros_casos", "region_otros_frac_con_casos", "region_otros_frac_en_brote",
                  "region_log_otros_casos_cambio_1", "region_log_otros_casos_cambio_4"],
    "nucleo": ["nucleo_log_casos", "nucleo_frac_en_brote", "nucleo_log_casos_cambio_4"],
    "propia": ["propia_log_casos", "propia_con_casos", "propia_semanas_desde_ultimo_caso",
               "propia_pendiente_4", "propia_aceleracion", "propia_log_casos_temporada_anterior"],
    "clima": [*CLIMA, *(f"{c}_anomalia" for c in CLIMA)],
}
VENTANAS_FAMILIA = {"vecinos": ("origen_2_4", "previa_5_8"), "jerarquia": ("origen_2_4", "previa_5_8"),
                    "nucleo": ("origen_2_4", "previa_5_8"), "propia": ("origen_2_4", "previa_5_8"),
                    "clima": ("clima_4_8", "clima_8_12")}
TOPE_SEMANAS_SIN_CASO = 52
ETIQUETAS = {
    "vecinos_log_media_casos": "Vecinos knn5: log(1 + casos medios)",
    "vecinos_frac_con_casos": "Vecinos knn5: fracción con casos",
    "vecinos_frac_en_brote": "Vecinos knn5: fracción en brote",
    "vecinos_n_casos_nuevos": "Vecinos knn5: nº con casos nuevos",
    "vecinos_log_media_casos_cambio_1": "Vecinos: cambio en 1 semana (log)",
    "vecinos_log_media_casos_cambio_4": "Vecinos: cambio en 4 semanas (log)",
    "provincia_log_otros_casos": "Provincia (sin el propio): log(1 + casos)",
    "provincia_otros_frac_con_casos": "Provincia: fracción con casos",
    "provincia_otros_frac_en_brote": "Provincia: fracción en brote",
    "provincia_log_otros_casos_cambio_1": "Provincia: cambio en 1 semana (log)",
    "provincia_log_otros_casos_cambio_4": "Provincia: cambio en 4 semanas (log)",
    "region_log_otros_casos": "Región (sin el propio): log(1 + casos)",
    "region_otros_frac_con_casos": "Región: fracción con casos",
    "region_otros_frac_en_brote": "Región: fracción en brote",
    "region_log_otros_casos_cambio_1": "Región: cambio en 1 semana (log)",
    "region_log_otros_casos_cambio_4": "Región: cambio en 4 semanas (log)",
    "nucleo_log_casos": "Núcleo (5 distritos, sin el propio): log(1 + casos)",
    "nucleo_frac_en_brote": "Núcleo: fracción en brote",
    "nucleo_log_casos_cambio_4": "Núcleo: cambio en 4 semanas (log)",
    "propia_log_casos": "Propio: log(1 + casos)",
    "propia_con_casos": "Propio: semana con casos (0/1)",
    "propia_semanas_desde_ultimo_caso": "Propio: semanas desde el último caso (tope 52)",
    "propia_pendiente_4": "Propio: pendiente 4 semanas (log)",
    "propia_aceleracion": "Propio: aceleración (log)",
    "propia_log_casos_temporada_anterior": "Propio: log(1 + casos de la temporada anterior)",
    "temp_media": "Temperatura media (°C)", "temp_min": "Temperatura mínima (°C)",
    "precip_total_mm": "Precipitación semanal (mm)", "hum_rel_media": "Humedad relativa media (%)",
    "temp_media_anomalia": "Anomalía de temperatura media (°C)",
    "temp_min_anomalia": "Anomalía de temperatura mínima (°C)",
    "precip_total_mm_anomalia": "Anomalía de precipitación (mm)",
    "hum_rel_media_anomalia": "Anomalía de humedad relativa (puntos %)",
}


# ---------------------------------------------------------------------------
# Inicios y periodo de diseño
# ---------------------------------------------------------------------------

def con_temporada(datos: pd.DataFrame) -> pd.Series:
    """Temporada epidemiológica (semana 35 en adelante pertenece a la siguiente)."""
    return assign_season(datos.anio, datos.semana, SEASON_START_WEEK)


def corte_diseno(serie: pd.DataFrame, temporadas: tuple[int, ...] = TEMPORADAS_DISENO) -> pd.Timestamp:
    """Cierre (sábado) de la última semana del periodo de diseño."""
    t = con_temporada(serie)
    return pd.Timestamp(serie.loc[t.isin(temporadas), "semana_inicio"].max()) + pd.Timedelta(days=6)


def periodo_de(temporada: int) -> str:
    for nombre, temporadas in PERIODOS.items():
        if temporada in temporadas:
            return nombre
    return "seleccion_2022_2023" if temporada in (2022, 2023) else "fuera_diseno"


def inicios_limpios(serie: pd.DataFrame) -> pd.DataFrame:
    """Episodios con inicio limpio, su temporada, periodo y si son verificables.

    Verificable: las ``SIN_BROTE_PREVIO`` semanas previas al inicio están
    dentro del panel (en enero–febrero de 2017 no se puede comprobar).
    """
    eps = diag.episodios(serie)
    eps = eps[eps.semanas_previas_sin_brote >= SIN_BROTE_PREVIO].copy()
    calendario = serie[["ubigeo", "semana_inicio", "anio", "semana"]].rename(columns={"semana_inicio": "inicio"})
    eps = eps.merge(calendario, on=["ubigeo", "inicio"], how="left", validate="one_to_one")
    eps["temporada"] = con_temporada(eps)
    eps["periodo"] = eps.temporada.map(periodo_de)
    primera = pd.Timestamp(serie.semana_inicio.min())
    eps["verificable"] = (eps.inicio - primera).dt.days // 7 >= SIN_BROTE_PREVIO
    eps["semana_clima"] = eps.semana.clip(upper=52).astype(int)
    eps = eps.sort_values(["inicio", "ubigeo"]).reset_index(drop=True)
    eps["id_inicio"] = np.arange(len(eps))
    return eps


def conteo_inicios(inicios: pd.DataFrame) -> pd.DataFrame:
    """Inicios limpios y verificables por temporada y periodo."""
    return (inicios.groupby(["periodo", "temporada"])
            .agg(limpios=("id_inicio", "size"), verificables=("verificable", "sum"),
                 distritos=("ubigeo", "nunique"), semanas_brote_mediana=("semanas_brote", "median"))
            .reset_index())


# ---------------------------------------------------------------------------
# Estado semanal (solo datos de semanas ≤ w)
# ---------------------------------------------------------------------------

def _ancho(datos: pd.DataFrame, columna: str, ids: pd.Index) -> pd.DataFrame:
    tabla = datos.pivot(index="semana_inicio", columns="ubigeo", values=columna).reindex(columns=ids)
    if tabla.isna().any().any():
        raise ValueError(f"Faltan distrito-semanas en {columna}")
    return tabla.sort_index()


def _pendiente(y: pd.DataFrame, ventana: int = 4) -> pd.DataFrame:
    """Pendiente MCO de las últimas ``ventana`` semanas (incluida ``w``)."""
    x = np.arange(ventana) - (ventana - 1) / 2
    pesos = x / (x ** 2).sum()
    return sum(y.shift(ventana - 1 - i) * pesos[i] for i in range(ventana))


def ranking_nucleo(serie: pd.DataFrame, corte: pd.Timestamp) -> pd.Series:
    """Casos acumulados por distrito en semanas cerradas al corte, de mayor a menor."""
    cerradas = serie[(serie.semana_inicio + pd.Timedelta(days=6)).le(corte)]
    return cerradas.groupby("ubigeo").casos_Dengue.sum().sort_values(ascending=False, kind="stable")


def terciles(serie: pd.DataFrame, corte: pd.Timestamp) -> pd.Series:
    """Tercil de casos acumulados al corte (bajo, medio, alto) por distrito."""
    acumulado = ranking_nucleo(serie, corte)
    return pd.qcut(acumulado.rank(method="first"), 3, labels=["bajo", "medio", "alto"]).astype(str)


def estado_semanal(panel: pd.DataFrame, serie: pd.DataFrame, corte: pd.Timestamp,
                   n_nucleo: int = N_NUCLEO) -> pd.DataFrame:
    """Descriptores por distrito y semana ``w`` calculados con datos de semanas ≤ ``w``.

    ``serie`` trae ``casos_Dengue`` y ``brote`` (la etiqueta de ``w`` usa la
    misma semana de años previos y los casos de ``w``: se conoce al cerrar
    ``w``). El núcleo (los ``n_nucleo`` distritos con más casos al corte,
    excluido el propio) y la climatología de las anomalías se ajustan solo con
    semanas cerradas al ``corte``.
    """
    geo = geographic_catalog(panel)
    pesos, _ = neighborhood_matrix(geo, k=K_VECINOS)
    ids = pesos.index
    s = serie.copy()
    s["semana_inicio"] = pd.to_datetime(s.semana_inicio)
    y = _ancho(s, "casos_Dengue", ids).astype(float)
    b = _ancho(s, "brote", ids).astype(float)
    w = pesos.to_numpy()
    activos = (y > 0).astype(float)
    nuevos = ((y > 0) & (y.shift(1) == 0)).astype(float)

    provincias = geo.set_index("ubigeo").loc[ids, "provincia"].to_numpy()
    prov = (provincias[:, None] == provincias[None, :]).astype(float)
    np.fill_diagonal(prov, 0)
    region = np.ones_like(prov) - np.eye(len(ids))
    n_prov, n_reg = prov.sum(axis=1), region.sum(axis=1)

    orden = list(ranking_nucleo(s, corte).index)
    nucleo = np.zeros_like(prov)
    for i, u in enumerate(ids):
        for v in [v for v in orden if v != u][:n_nucleo]:
            nucleo[i, ids.get_loc(v)] = 1.0

    def marco(m):
        return pd.DataFrame(np.asarray(m), index=y.index, columns=ids)

    vals = {
        "vecinos_log_media_casos": np.log1p(marco(y.to_numpy() @ w.T)),
        "vecinos_frac_con_casos": marco(activos.to_numpy() @ w.T),
        "vecinos_frac_en_brote": marco(b.to_numpy() @ w.T),
        "vecinos_n_casos_nuevos": marco(nuevos.to_numpy() @ (w > 0).T.astype(float)),
        "provincia_log_otros_casos": np.log1p(marco(y.to_numpy() @ prov.T)),
        "provincia_otros_frac_con_casos": marco(activos.to_numpy() @ prov.T / n_prov),
        "provincia_otros_frac_en_brote": marco(b.to_numpy() @ prov.T / n_prov),
        "region_log_otros_casos": np.log1p(marco(y.to_numpy() @ region.T)),
        "region_otros_frac_con_casos": marco(activos.to_numpy() @ region.T / n_reg),
        "region_otros_frac_en_brote": marco(b.to_numpy() @ region.T / n_reg),
        "nucleo_log_casos": np.log1p(marco(y.to_numpy() @ nucleo.T)),
        "nucleo_frac_en_brote": marco(b.to_numpy() @ nucleo.T / n_nucleo),
    }
    for base in ("vecinos_log_media_casos", "provincia_log_otros_casos", "region_log_otros_casos"):
        vals[f"{base}_cambio_1"] = vals[base] - vals[base].shift(1)
        vals[f"{base}_cambio_4"] = vals[base] - vals[base].shift(4)
    vals["nucleo_log_casos_cambio_4"] = vals["nucleo_log_casos"] - vals["nucleo_log_casos"].shift(4)

    ly = np.log1p(y)
    vals["propia_log_casos"] = ly
    vals["propia_con_casos"] = activos
    ultima = pd.DataFrame(np.where(y.to_numpy() > 0, np.arange(len(y))[:, None], np.nan),
                          index=y.index, columns=ids).ffill()
    desde = np.arange(len(y))[:, None] - ultima
    vals["propia_semanas_desde_ultimo_caso"] = desde.fillna(TOPE_SEMANAS_SIN_CASO).clip(upper=TOPE_SEMANAS_SIN_CASO)
    vals["propia_pendiente_4"] = _pendiente(ly)
    vals["propia_aceleracion"] = (ly - ly.shift(1)) - (ly.shift(1) - ly.shift(2))
    semanas = s.drop_duplicates("semana_inicio").set_index("semana_inicio").loc[y.index]
    temporada = con_temporada(semanas).to_numpy()
    # Casos de la temporada anterior completa: cerrada antes de cualquier w de la actual.
    por_temporada = y.groupby(temporada).sum()
    anterior = por_temporada.shift(1).reindex(temporada)
    anterior.index = y.index
    vals["propia_log_casos_temporada_anterior"] = np.log1p(anterior)

    largo = []
    for nombre, m in vals.items():
        largo.append(m.stack(future_stack=True).rename(nombre))
    estado = pd.concat(largo, axis=1).reset_index()

    clima = panel[["ubigeo", "semana_inicio", "anio", "semana", *CLIMA]].copy()
    clima["semana_inicio"] = pd.to_datetime(clima.semana_inicio)
    clima["semana_clima"] = clima.semana.clip(upper=52).astype(int)
    climatologia = fit_climatology(panel, corte, CLIMA).table
    clima = clima.merge(climatologia, on=["ubigeo", "semana_clima"], how="left", suffixes=("", "_clim"),
                        validate="many_to_one")
    for c in CLIMA:
        clima[f"{c}_anomalia"] = clima[c] - clima[f"{c}_clim"]
    estado = estado.merge(clima[["ubigeo", "semana_inicio", *CLIMA, *(f"{c}_anomalia" for c in CLIMA)]],
                          on=["ubigeo", "semana_inicio"], how="left", validate="one_to_one")
    estado["ubigeo"] = estado.ubigeo.astype("string")
    return estado.sort_values(["ubigeo", "semana_inicio"]).reset_index(drop=True)


# ---------------------------------------------------------------------------
# Controles
# ---------------------------------------------------------------------------

def semanas_elegibles(serie: pd.DataFrame, temporadas: tuple[int, ...] = TEMPORADAS_DISENO) -> pd.DataFrame:
    """Distrito-semanas sin brote en la semana ni en las 8 previas, observadas, del periodo."""
    s = serie.sort_values(["ubigeo", "semana_inicio"]).copy()
    s["temporada"] = con_temporada(s)
    previo = (s.groupby("ubigeo").brote.transform(lambda x: x.rolling(SIN_BROTE_PREVIO + 1, min_periods=1).max()))
    primera = pd.Timestamp(s.semana_inicio.min())
    observada = (s.semana_inicio - primera).dt.days // 7 >= SIN_BROTE_PREVIO
    ok = previo.eq(0) & observada & s.temporada.isin(temporadas)
    salida = s.loc[ok, ["ubigeo", "semana_inicio", "temporada", "semana"]].copy()
    salida["semana_clima"] = salida.semana.clip(upper=52).astype(int)
    return salida.drop(columns="semana").reset_index(drop=True)


def controles(inicios: pd.DataFrame, elegibles: pd.DataFrame, tercil: pd.Series,
              minimo_distrito: int = MIN_CONTROLES_DISTRITO) -> pd.DataFrame:
    """Pares inicio → control de los dos tipos (``semana`` y ``distrito``).

    ``distrito`` usa el mismo distrito en otras temporadas; si hay menos de
    ``minimo_distrito``, distritos del mismo ``tercil`` (``tipo_efectivo``
    queda en ``tercil``).
    """
    base = inicios[["id_inicio", "ubigeo", "temporada", "semana_clima"]]
    por_semana = base.merge(elegibles.rename(columns={"ubigeo": "ubigeo_control", "semana_inicio": "semana_control",
                                                      "temporada": "temporada_control"}),
                            on="semana_clima")
    semana = por_semana.assign(tipo="semana", tipo_efectivo="semana")
    mismo = por_semana[por_semana.ubigeo_control.eq(por_semana.ubigeo)
                       & por_semana.temporada_control.ne(por_semana.temporada)]
    n = mismo.groupby("id_inicio").size().reindex(base.id_inicio, fill_value=0)
    faltan = n[n < minimo_distrito].index
    t = por_semana.ubigeo.map(tercil)
    t_control = por_semana.ubigeo_control.map(tercil)
    respaldo = por_semana[por_semana.id_inicio.isin(faltan) & t.eq(t_control)
                          & ~(por_semana.ubigeo_control.eq(por_semana.ubigeo)
                              & por_semana.temporada_control.eq(por_semana.temporada))]
    distrito = pd.concat([mismo[~mismo.id_inicio.isin(faltan)].assign(tipo_efectivo="distrito"),
                          respaldo.assign(tipo_efectivo="tercil")], ignore_index=True).assign(tipo="distrito")
    cols = ["id_inicio", "tipo", "tipo_efectivo", "ubigeo_control", "semana_control"]
    return pd.concat([semana[cols], distrito[cols]], ignore_index=True)


# ---------------------------------------------------------------------------
# Perfiles y resúmenes
# ---------------------------------------------------------------------------

def perfiles(estado: pd.DataFrame, inicios: pd.DataFrame, pares: pd.DataFrame,
             variables: list[str], rezagos: tuple[int, ...] = REZAGOS) -> pd.DataFrame:
    """Diferencia inicio − media de controles para cada inicio, tipo, variable y ``k``."""
    est = estado.set_index(["ubigeo", "semana_inicio"])[variables]
    filas = []
    for k in rezagos:
        delta = pd.Timedelta(weeks=k)
        ini = est.reindex(pd.MultiIndex.from_arrays([inicios.ubigeo, inicios.inicio - delta])).to_numpy()
        ini = pd.DataFrame(ini, columns=variables).assign(id_inicio=inicios.id_inicio.to_numpy())
        ctl = est.reindex(pd.MultiIndex.from_arrays([pares.ubigeo_control, pares.semana_control - delta])).to_numpy()
        ctl = (pd.DataFrame(ctl, columns=variables)
               .assign(id_inicio=pares.id_inicio.to_numpy(), tipo=pares.tipo.to_numpy())
               .groupby(["id_inicio", "tipo"])[variables].mean())
        n_ctl = pares.groupby(["id_inicio", "tipo"]).size().rename("n_controles")
        for tipo in pares.tipo.unique():
            c = ctl.xs(tipo, level="tipo").reindex(ini.id_inicio)
            dif = ini[variables].to_numpy() - c.to_numpy()
            largo = pd.DataFrame(dif, columns=variables).assign(id_inicio=ini.id_inicio.to_numpy()).melt(
                "id_inicio", var_name="variable", value_name="diferencia")
            v_ini = ini.melt("id_inicio", var_name="variable", value_name="valor_inicio")
            v_ctl = c.reset_index().melt("id_inicio", var_name="variable", value_name="valor_control")
            largo = largo.merge(v_ini, on=["id_inicio", "variable"]).merge(v_ctl, on=["id_inicio", "variable"])
            filas.append(largo.assign(tipo_control=tipo, k=k)
                         .merge(n_ctl.xs(tipo, level="tipo").rename("n_controles").reset_index(), on="id_inicio",
                                how="left"))
    tabla = pd.concat(filas, ignore_index=True)
    return tabla.merge(inicios[["id_inicio", "periodo", "temporada"]], on="id_inicio", how="left")


def _resumen(g: pd.DataFrame, valor: str = "diferencia") -> pd.Series:
    g = g.dropna(subset=[valor])
    if g.empty:
        return pd.Series({"inicios": 0, "media": np.nan, "media_inicio": np.nan, "media_control": np.nan,
                          "ic95_inferior": np.nan, "ic95_superior": np.nan})
    medias = bootstrap_estratificado(g[valor].to_numpy(float), g.periodo.to_numpy())
    return pd.Series({"inicios": len(g), "media": float(g[valor].mean()),
                      "media_inicio": float(g.valor_inicio.mean()) if "valor_inicio" in g else np.nan,
                      "media_control": float(g.valor_control.mean()) if "valor_control" in g else np.nan,
                      "ic95_inferior": float(np.quantile(medias, 0.025)),
                      "ic95_superior": float(np.quantile(medias, 0.975))})


def _con_periodo_completo(tabla: pd.DataFrame) -> pd.DataFrame:
    return pd.concat([tabla, tabla.assign(periodo_resumen="2017_2021")], ignore_index=True)


def resumen_por_rezago(tabla: pd.DataFrame) -> pd.DataFrame:
    """Media e IC95 bootstrap (por episodio, estratificado por periodo) por ``k``."""
    t = _con_periodo_completo(tabla.assign(periodo_resumen=tabla.periodo))
    return (t.groupby(["periodo_resumen", "tipo_control", "variable", "k"])
            .apply(_resumen, include_groups=False).reset_index())


def por_ventana(tabla: pd.DataFrame, familias: dict = FAMILIAS) -> pd.DataFrame:
    """Diferencia media de cada inicio dentro de las ventanas a priori de su familia."""
    familia = {v: f for f, vs in familias.items() for v in vs}
    partes = []
    for nombre, (k0, k1) in VENTANAS.items():
        sel = tabla[tabla.k.between(k0, k1) & tabla.variable.map(familia).map(
            lambda f: nombre in VENTANAS_FAMILIA.get(f, ()))]
        if sel.empty:
            continue
        agg = (sel.groupby(["id_inicio", "periodo", "tipo_control", "variable"])
               [["diferencia", "valor_inicio", "valor_control"]].mean().reset_index().assign(ventana=nombre))
        partes.append(agg)
    salida = pd.concat(partes, ignore_index=True)
    salida["familia"] = salida.variable.map(familia)
    return salida


def resumen_ventanas(ventanas: pd.DataFrame) -> pd.DataFrame:
    """Media e IC95 por periodo (2017, 2018–2021 y completo), control, variable y ventana."""
    t = _con_periodo_completo(ventanas.assign(periodo_resumen=ventanas.periodo))
    return (t.groupby(["familia", "variable", "ventana", "tipo_control", "periodo_resumen"])
            .apply(_resumen, include_groups=False).reset_index())


def consistencia(resumen: pd.DataFrame) -> pd.DataFrame:
    """Aplica la regla de consistencia del docstring del módulo a cada variable y ventana."""
    filas = []
    for (familia, variable, ventana), g in resumen.groupby(["familia", "variable", "ventana"]):
        r = g.set_index(["tipo_control", "periodo_resumen"])
        def celda(tipo, periodo, col="media"):
            return float(r.loc[(tipo, periodo), col]) if (tipo, periodo) in r.index else np.nan
        signos = [np.sign(celda(t, p)) for t in ("semana", "distrito") for p in PERIODOS]
        excluye = lambda t, p: (celda(t, p, "ic95_inferior") > 0) or (celda(t, p, "ic95_superior") < 0)
        mismo_signo = len(set(signos)) == 1 and signos[0] != 0 and not np.isnan(signos[0])
        observada = mismo_signo and all(excluye(t, "2017_2021") for t in ("semana", "distrito"))
        s17 = {np.sign(celda(t, "2017")) for t in ("semana", "distrito")}
        solo_2017 = (len(s17) == 1 and 0 not in s17 and all(excluye(t, "2017") for t in ("semana", "distrito")))
        celdas = [celda(t, p) for t in ("semana", "distrito") for p in (*PERIODOS, "2017_2021")]
        if any(np.isnan(x) for x in celdas):
            veredicto = "no_evaluable"
        else:
            veredicto = "observada" if observada else ("hipotesis_solo_2017" if solo_2017 else "no_observada")
        filas.append({"familia": familia, "variable": variable, "ventana": ventana, "veredicto": veredicto,
                      "signo": int(signos[0]) if mismo_signo else 0,
                      **{f"media_{t}_{p}": celda(t, p) for t in ("semana", "distrito")
                         for p in (*PERIODOS, "2017_2021")}})
    return pd.DataFrame(filas)


# ---------------------------------------------------------------------------
# Inicios de 2021 con la referencia B (único bloque del periodo de diseño)
# ---------------------------------------------------------------------------

def inicios_con_prediccion(inicios: pd.DataFrame, predicciones: pd.DataFrame,
                           bloque: str = "temporada_2021") -> pd.DataFrame:
    """Probabilidad sin calibrar y casos predichos para la semana de inicio, por horizonte.

    Mediana entre semillas. En 2021 (bloque de calibración inicial) no hay
    probabilidad calibrada; se describe la cruda y el conteo.
    """
    p = predicciones[predicciones.bloque.eq(bloque)]
    med = (p.groupby(["ubigeo", "semana_inicio", "horizonte"])
           [["probabilidad_brote", "casos_predichos", "persistencia", "casos_Dengue"]].median().reset_index())
    ini = inicios[inicios.temporada.eq(int(bloque.split("_")[-1]))][["id_inicio", "ubigeo", "inicio", "semanas_brote"]]
    return ini.merge(med.rename(columns={"semana_inicio": "inicio"}), on=["ubigeo", "inicio"], how="left")


# ---------------------------------------------------------------------------
# Figuras
# ---------------------------------------------------------------------------

def figura_perfiles(resumen: pd.DataFrame, variables: list[str], titulo: str, etiquetas: dict | None = None):
    """Diferencia inicio − control por ``k`` (IC95), por periodo y tipo de control."""
    import matplotlib.pyplot as plt

    etiquetas = etiquetas or {}
    n = len(variables)
    columnas = 3
    filas = int(np.ceil(n / columnas))
    fig, ejes = plt.subplots(filas, columnas, figsize=(5.2 * columnas, 3.4 * filas), squeeze=False)
    estilos = {("2017", "semana"): ("#0072B2", "-"), ("2017", "distrito"): ("#0072B2", "--"),
               ("2018_2021", "semana"): ("#D55E00", "-"), ("2018_2021", "distrito"): ("#D55E00", "--")}
    for ax, v in zip(ejes.ravel(), variables):
        for (periodo, tipo), (color, linea) in estilos.items():
            g = resumen[resumen.variable.eq(v) & resumen.periodo_resumen.eq(periodo)
                        & resumen.tipo_control.eq(tipo)].sort_values("k")
            ax.plot(-g.k, g.media, color=color, linestyle=linea, marker="o", markersize=3,
                    label=f"{periodo.replace('_', '–')} · control {tipo}")
            ax.fill_between(-g.k, g.ic95_inferior, g.ic95_superior, color=color, alpha=0.08)
        ax.axhline(0, color="grey", linewidth=0.8)
        ax.set_title(etiquetas.get(v, v), fontsize=9)
        ax.set_xlabel("Semanas antes del inicio (−k)")
        ax.set_ylabel("Inicio − control")
    for ax in ejes.ravel()[n:]:
        ax.axis("off")
    ejes[0, 0].legend(fontsize=7)
    fig.suptitle(titulo)
    fig.tight_layout()
    return fig


def errores_por_fase(evaluaciones: list[dict], bloques: tuple[str, ...]) -> pd.DataFrame:
    """Mediana y rango entre semillas de los errores por fase de la curva regional."""
    todas = pd.concat([e["errores_por_fase"] for e in evaluaciones], ignore_index=True)
    todas = todas[todas.bloque.isin(bloques)].astype({"fase": str})
    columnas = ["razon_mae", "razon_rmse", "sesgo_modelo", "sesgo_persistencia", "suma_predicha_sobre_real"]
    g = todas.groupby(["horizonte", "bloque", "fase"])
    salida = g[["n", *columnas]].median()
    rango = (g[["razon_mae", "razon_rmse"]].max() - g[["razon_mae", "razon_rmse"]].min()).add_prefix("rango_")
    return salida.join(rango).reset_index()


def figura_errores_fase(tabla: pd.DataFrame):
    """MAE relativo a la persistencia por fase de la curva, horizonte y temporada."""
    import matplotlib.pyplot as plt

    orden = [f for f in diag.ORDEN_FASES if f in set(tabla.fase)]
    bloques = sorted(tabla.bloque.unique())
    fig, ejes = plt.subplots(1, len(bloques), figsize=(6 * len(bloques), 4), squeeze=False)
    for ax, bloque in zip(ejes.ravel(), bloques):
        t = tabla[tabla.bloque.eq(bloque)]
        x = np.arange(len(orden))
        for i, h in enumerate(sorted(t.horizonte.unique())):
            g = t[t.horizonte.eq(h)].set_index("fase").reindex(orden)
            ax.bar(x + (i - 1) * 0.27, g.razon_mae, 0.27, yerr=g.rango_razon_mae / 2, label=f"h={h}")
        ax.axhline(1, color="grey", linewidth=0.8)
        ax.set_xticks(x, orden)
        ax.set_ylabel("MAE modelo / MAE persistencia")
        ax.set_title(bloque.replace("temporada_", "Temporada "))
        ax.legend(fontsize=8)
    fig.suptitle("E3·S4_s2 (referencia B): error de casos por fase de la curva regional")
    fig.tight_layout()
    return fig
