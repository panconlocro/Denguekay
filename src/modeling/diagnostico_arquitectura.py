"""Diagnóstico de errores de los modelos actuales (fase 1 de arquitectura).

Todo se calcula en memoria a partir de predicciones fuera de muestra ya
guardadas; no se reentrena ni se escribe en ``data/``. Las etiquetas
completas de gold solo se leen para ubicar rachas y semanas adyacentes.

Definiciones usadas en el diagnóstico (retrospectivas, no operativas):

- **Fase de la curva:** según la curva regional observada del bloque (suma de
  los 65 distritos por semana objetivo). Valle: menos del 10 % del máximo del
  bloque; pico: al menos 60 %; subida/bajada: el resto, antes/después de la
  semana del máximo.
- **Tamaño de distrito:** terciles de casos acumulados antes del inicio de la
  temporada 2021, es decir, antes de cualquier bloque evaluado.
- **Episodio:** racha de semanas consecutivas con ``brote = 1`` en un distrito.
- **Antelación:** semanas entre la emisión de la primera alerta pertinente
  (objetivo ``w`` emitido en ``w − h``) y el inicio ``t0`` del episodio:
  ``h − (w − t0)``. Se consideran alertas con objetivo desde ``t0 − 2``.
"""

import json
from pathlib import Path

import numpy as np
import pandas as pd

from src.eda.temporal import asignar_temporada
from src.modeling.evaluate import alertas_desde_conteos, metricas_alerta
from src.modeling.train import MINIMO_CASOS_BROTE, SEMANA_INICIO_TEMPORADA
from src.validation.contrato_pronostico import CLAVE

VARIANTE_REGRESION = "base_6"
VARIANTE_CLASIFICACION = "base_6_poblacion_2017"
BLOQUES_DIAGNOSTICO = ("temporada_2022", "temporada_2023", "temporada_2024")
NIVELES_CASOS = (0, 1, 5, 20, 100)
ETIQUETAS_NIVEL = ("0", "1–4", "5–19", "20–99", "≥100")
ORDEN_FASES = ("valle", "subida", "pico", "bajada")
VENTANA_ADYACENCIA = 2
SIN_BROTE_PREVIO = 8
SEMANA = pd.Timedelta(days=7)


def predicciones_seleccionadas(predicciones: pd.DataFrame, reporte: dict) -> pd.DataFrame:
    """Une regresión ``base_6`` y clasificación con población por distrito-semana.

    Agrega el umbral de probabilidad calibrado cronológicamente de cada bloque
    (``NaN`` en 2021, que solo sirvió como calibración inicial).
    """
    cols = CLAVE + ["semana_inicio", "horizonte", "bloque", "temporada",
                    "casos_Dengue", "brote", "umbral_brote_casos"]
    reg = predicciones[predicciones.variante.eq(VARIANTE_REGRESION)]
    cls = predicciones[predicciones.variante.eq(VARIANTE_CLASIFICACION)]
    if reg.empty or cls.empty:
        raise ValueError("Faltan las variantes seleccionadas en las predicciones")
    reg = reg.assign(persistencia=np.where(
        reg.horizonte.eq(2), reg.get("casos_lag_2"), reg.get("casos_lag_4")))
    datos = reg[cols + ["casos_predichos", "persistencia"]].merge(
        cls[cols + ["probabilidad_brote"]], on=cols, how="inner", validate="one_to_one")
    if len(datos) != len(reg) or len(datos) != len(cls):
        raise ValueError("Regresión y clasificación no cubren las mismas filas")
    if datos.persistencia.isna().any():
        raise ValueError("Persistencia incompleta")
    umbrales = {}
    for h, bloque_h in reporte["horizontes"].items():
        resultado = bloque_h["variantes"][VARIANTE_CLASIFICACION]
        for fold in [*resultado["folds"], resultado["sensibilidad_2025"]]:
            umbrales[(int(h), fold["bloque"])] = fold["clasificacion"]["umbral_probabilidad"]
    datos["umbral_probabilidad"] = [
        umbrales.get((h, b), np.nan) for h, b in zip(datos.horizonte, datos.bloque)]
    datos["semana_inicio"] = pd.to_datetime(datos.semana_inicio)
    datos["ubigeo"] = datos.ubigeo.astype("string")
    return datos.sort_values(["horizonte", "bloque", "ubigeo", "semana_inicio"]).reset_index(drop=True)


def agregar_alertas(datos: pd.DataFrame) -> pd.DataFrame:
    """Calcula las cuatro reglas de alerta comparadas en el diagnóstico."""
    salida = datos.copy()
    limite = salida.umbral_brote_casos.to_numpy(float)
    salida["alerta_regresion"] = alertas_desde_conteos(
        salida.casos_predichos.to_numpy(float), limite, MINIMO_CASOS_BROTE)
    salida["alerta_persistencia"] = alertas_desde_conteos(
        salida.persistencia.to_numpy(float), limite, MINIMO_CASOS_BROTE)
    salida["alerta_cls_calibrada"] = salida.probabilidad_brote >= salida.umbral_probabilidad
    salida["alerta_cls_050"] = salida.probabilidad_brote >= 0.5
    return salida


def nivel_casos(casos: pd.Series) -> pd.Series:
    """Clasifica los casos reales en niveles fijos."""
    cortes = [*NIVELES_CASOS, np.inf]
    return pd.cut(casos, bins=[c - 0.5 for c in cortes], labels=ETIQUETAS_NIVEL, right=False)


def fase_curva(datos: pd.DataFrame, valle: float = 0.10, pico: float = 0.60) -> pd.Series:
    """Asigna la fase de la curva regional observada a cada fila del bloque."""
    fases = pd.Series(index=datos.index, dtype="object")
    for _, grupo in datos.groupby(["horizonte", "bloque"]):
        curva = grupo.groupby("semana_inicio").casos_Dengue.sum()
        maximo = curva.max()
        semana_max = curva.idxmax()
        if maximo <= 0:
            etiquetas = pd.Series("valle", index=curva.index)
        else:
            rel = curva / maximo
            etiquetas = pd.Series(np.where(curva.index < semana_max, "subida", "bajada"), index=curva.index)
            etiquetas[rel >= pico] = "pico"
            etiquetas[rel < valle] = "valle"
        fases.loc[grupo.index] = grupo.semana_inicio.map(etiquetas).to_numpy()
    return pd.Categorical(fases, categories=ORDEN_FASES, ordered=True)


def terciles_distrito(etiquetas: pd.DataFrame, temporada_corte: int = 2021) -> pd.Series:
    """Terciles de casos acumulados antes de la temporada de corte, por ubigeo."""
    temporada = asignar_temporada(etiquetas.anio, etiquetas.semana, SEMANA_INICIO_TEMPORADA)
    previos = etiquetas.loc[temporada < temporada_corte].groupby("ubigeo").casos_Dengue.sum()
    rango = previos.rank(method="first")
    return pd.qcut(rango, 3, labels=["bajo", "medio", "alto"]).rename("tercil_distrito")


def desglose_errores(datos: pd.DataFrame, por: list[str]) -> pd.DataFrame:
    """MAE, RMSE y sesgo del regresor y la persistencia por grupo."""
    def resumen(g: pd.DataFrame) -> pd.Series:
        e_mod = g.casos_predichos - g.casos_Dengue
        e_per = g.persistencia - g.casos_Dengue
        mae_m, mae_p = e_mod.abs().mean(), e_per.abs().mean()
        rmse_m, rmse_p = np.sqrt((e_mod ** 2).mean()), np.sqrt((e_per ** 2).mean())
        return pd.Series({
            "n": len(g), "casos_medios": g.casos_Dengue.mean(),
            "mae_modelo": mae_m, "mae_persistencia": mae_p,
            "razon_mae": mae_m / mae_p if mae_p else np.nan,
            "rmse_modelo": rmse_m, "rmse_persistencia": rmse_p,
            "razon_rmse": rmse_m / rmse_p if rmse_p else np.nan,
            "sesgo_modelo": e_mod.mean(), "sesgo_persistencia": e_per.mean(),
            "suma_predicha_sobre_real": (g.casos_predichos.sum() / g.casos_Dengue.sum()
                                         if g.casos_Dengue.sum() else np.nan),
        })
    return datos.groupby(por, observed=True).apply(resumen, include_groups=False).reset_index()


def adyacente_a_brote(filas: pd.DataFrame, etiquetas: pd.DataFrame,
                      ventana: int = VENTANA_ADYACENCIA) -> np.ndarray:
    """Indica si hay una semana ``brote`` del mismo distrito a ±``ventana`` semanas."""
    positivos = etiquetas.loc[etiquetas.brote.eq(1), ["ubigeo", "semana_inicio"]]
    por_distrito = {u: set(g.semana_inicio) for u, g in positivos.groupby("ubigeo")}
    desplazamientos = [d * SEMANA for d in range(-ventana, ventana + 1) if d]
    return np.array([
        any(s + d in por_distrito.get(u, ()) for d in desplazamientos)
        for u, s in zip(filas.ubigeo, filas.semana_inicio)
    ], dtype=bool)


def falsos_positivos(datos: pd.DataFrame, etiquetas: pd.DataFrame, alerta: str) -> pd.DataFrame:
    """Cuenta falsos positivos adyacentes a una racha real y aislados."""
    fp = datos.loc[datos[alerta] & datos.brote.eq(0)]
    fp = fp.assign(adyacente=adyacente_a_brote(fp, etiquetas))
    tabla = fp.groupby(["horizonte", "bloque"]).adyacente.agg(fp="size", adyacentes="sum").reset_index()
    tabla["aislados"] = tabla.fp - tabla.adyacentes
    tabla["fraccion_adyacentes"] = tabla.adyacentes / tabla.fp
    tabla.insert(0, "alerta", alerta)
    return tabla


def curva_fiabilidad(y: np.ndarray, p: np.ndarray, n_bins: int = 10) -> pd.DataFrame:
    """Frecuencia observada frente a probabilidad media en bins de igual ancho."""
    y, p = np.asarray(y, float), np.asarray(p, float)
    bins = np.minimum((p * n_bins).astype(int), n_bins - 1)
    tabla = pd.DataFrame({"bin": bins, "y": y, "p": p}).groupby("bin").agg(
        n=("y", "size"), prob_media=("p", "mean"), frecuencia_observada=("y", "mean"))
    tabla.index = [f"[{b / n_bins:.1f}, {(b + 1) / n_bins:.1f})" for b in tabla.index]
    return tabla


def metricas_probabilidad(datos: pd.DataFrame) -> pd.DataFrame:
    """Brier, AUPRC y alertas con el umbral 0,50 y el calibrado, por bloque."""
    filas = []
    for (h, bloque), g in datos.groupby(["horizonte", "bloque"]):
        y, p = g.brote.to_numpy(int), g.probabilidad_brote.to_numpy(float)
        fila = {"horizonte": h, "bloque": bloque, "positivos": int(y.sum()),
                "prob_media": p.mean(), "prevalencia": y.mean(),
                "brier": float(np.mean((p - y) ** 2))}
        for nombre, alerta in (("050", "alerta_cls_050"), ("calibrada", "alerta_cls_calibrada")):
            m = metricas_alerta(y, g[alerta].to_numpy(bool), puntaje=p)
            fila.update({f"{k}_{nombre}": m[k] for k in ("vp", "fp", "fn", "precision", "recall", "f1")})
            fila["auprc"] = m["auprc"]
        fila["umbral_calibrado"] = g.umbral_probabilidad.iloc[0]
        filas.append(fila)
    return pd.DataFrame(filas)


def episodios(etiquetas: pd.DataFrame, hueco_max: int = VENTANA_ADYACENCIA) -> pd.DataFrame:
    """Episodios de ``brote`` por distrito, uniendo huecos de hasta ``hueco_max`` semanas.

    ``semanas_previas_sin_brote`` cuenta las semanas entre el fin del episodio
    anterior del distrito y este inicio (``inf`` si no hubo uno anterior).
    """
    pos = etiquetas.loc[etiquetas.brote.eq(1), ["ubigeo", "semana_inicio"]].sort_values(
        ["ubigeo", "semana_inicio"])
    salto = pos.groupby("ubigeo").semana_inicio.diff()
    nueva = salto.isna() | salto.gt((hueco_max + 1) * SEMANA)
    pos = pos.assign(episodio=nueva.cumsum())
    eps = pos.groupby("episodio").agg(
        ubigeo=("ubigeo", "first"), inicio=("semana_inicio", "min"),
        fin=("semana_inicio", "max"), semanas_brote=("semana_inicio", "size")).reset_index(drop=True)
    fin_anterior = eps.groupby("ubigeo").fin.shift()
    eps["semanas_previas_sin_brote"] = ((eps.inicio - fin_anterior).dt.days / 7 - 1).fillna(np.inf)
    return eps


def antelacion_episodios(datos: pd.DataFrame, etiquetas: pd.DataFrame, alertas: list[str],
                         previa: int = VENTANA_ADYACENCIA) -> pd.DataFrame:
    """Antelación de la primera alerta pertinente por episodio que inicia en el bloque.

    Solo se usan alertas del mismo bloque; un episodio que empieza en las
    primeras semanas puede perder alertas emitidas en el bloque anterior.
    """
    eps = episodios(etiquetas)
    filas = []
    for (h, bloque), g in datos.groupby(["horizonte", "bloque"]):
        semanas = g.semana_inicio
        dentro = eps[eps.inicio.between(semanas.min(), semanas.max())]
        por_distrito = {u: gg.set_index("semana_inicio") for u, gg in g.groupby("ubigeo")}
        for ep in dentro.itertuples(index=False):
            serie = por_distrito.get(ep.ubigeo)
            fila = {"horizonte": h, "bloque": bloque, "ubigeo": ep.ubigeo,
                    "inicio": ep.inicio, "semanas_brote": ep.semanas_brote,
                    "semanas_previas_sin_brote": ep.semanas_previas_sin_brote}
            ventana = serie.loc[ep.inicio - previa * SEMANA: ep.fin] if serie is not None else None
            for alerta in alertas:
                activas = ventana.index[ventana[alerta].to_numpy(bool)] if ventana is not None else []
                if len(activas):
                    w = activas.min()
                    fila[alerta] = h - (w - ep.inicio).days // 7
                else:
                    fila[alerta] = np.nan
            filas.append(fila)
    return pd.DataFrame(filas)


def resumen_antelacion(tabla: pd.DataFrame, alertas: list[str],
                       sin_brote_previo: int = 0) -> pd.DataFrame:
    """Detección y antelación por regla de alerta, horizonte y bloque.

    Con ``sin_brote_previo = k`` solo cuenta inicios «limpios»: episodios sin
    semanas ``brote`` en las ``k`` semanas previas del distrito, donde una
    alerta temprana no puede ser arrastre del episodio anterior.
    """
    filas = []
    tabla = tabla[tabla.semanas_previas_sin_brote >= sin_brote_previo]
    for (h, bloque), g in tabla.groupby(["horizonte", "bloque"]):
        for alerta in alertas:
            a = g[alerta]
            filas.append({
                "horizonte": h, "bloque": bloque, "alerta": alerta, "episodios": len(g),
                "detectados": float(a.notna().mean()),
                "antes_del_inicio": float((a >= 1).mean()),
                "antelacion_2_o_mas": float((a >= 2).mean()),
                "antelacion_mediana": float(a.median()) if a.notna().any() else np.nan,
            })
    return pd.DataFrame(filas)


def concentracion_error(datos: pd.DataFrame, n_distritos: int = 5) -> pd.DataFrame:
    """Parte del error absoluto y cuadrático que aportan 2023 y los distritos mayores."""
    filas = []
    for h, g in datos.groupby("horizonte"):
        top = g.groupby("ubigeo").casos_Dengue.sum().nlargest(n_distritos).index
        for nombre, col in (("modelo", "casos_predichos"), ("persistencia", "persistencia")):
            ea = (g[col] - g.casos_Dengue).abs()
            ec = (g[col] - g.casos_Dengue) ** 2
            for grupo, mascara in (("temporada_2023", g.bloque.eq("temporada_2023")),
                                   (f"top{n_distritos}_distritos", g.ubigeo.isin(top)),
                                   ("ambos", g.bloque.eq("temporada_2023") & g.ubigeo.isin(top))):
                filas.append({
                    "horizonte": h, "pronostico": nombre, "grupo": grupo,
                    "fraccion_filas": float(mascara.mean()),
                    "fraccion_casos": float(g.casos_Dengue[mascara].sum() / g.casos_Dengue.sum()),
                    "fraccion_error_absoluto": float(ea[mascara].sum() / ea.sum()),
                    "fraccion_error_cuadratico": float(ec[mascara].sum() / ec.sum()),
                })
    return pd.DataFrame(filas)


def a_json(tabla: pd.DataFrame) -> list[dict]:
    """Convierte una tabla a registros JSON con números nativos y fechas en texto."""
    return json.loads(tabla.to_json(orient="records", date_format="iso", force_ascii=False))


def guardar_seccion_metricas(ruta: Path, seccion: str, contenido: dict) -> Path:
    """Escribe o reemplaza una sección del JSON de métricas del encargo."""
    ruta = Path(ruta)
    actual = json.loads(ruta.read_text(encoding="utf-8")) if ruta.exists() else {}
    actual[seccion] = contenido
    ruta.parent.mkdir(parents=True, exist_ok=True)
    ruta.write_text(json.dumps(actual, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return ruta


# ---------------------------------------------------------------------------
# Figuras
# ---------------------------------------------------------------------------

def guardar_figura(fig, carpeta: Path, nombre: str) -> Path:
    """Guarda la figura como PNG en ``carpeta`` y la cierra."""
    import matplotlib.pyplot as plt

    carpeta = Path(carpeta)
    carpeta.mkdir(parents=True, exist_ok=True)
    ruta = carpeta / f"{nombre}.png"
    fig.savefig(ruta, dpi=130, bbox_inches="tight")
    plt.close(fig)
    return ruta


def figura_errores(tabla: pd.DataFrame, columna: str, titulo: str):
    """Barras de MAE y RMSE del modelo y la persistencia por grupo y horizonte."""
    import matplotlib.pyplot as plt

    horizontes = sorted(tabla.horizonte.unique())
    fig, ejes = plt.subplots(2, len(horizontes), figsize=(5.5 * len(horizontes), 7), squeeze=False)
    for j, h in enumerate(horizontes):
        t = tabla[tabla.horizonte.eq(h)]
        x = np.arange(len(t))
        for i, metrica in enumerate(("mae", "rmse")):
            ax = ejes[i, j]
            ax.bar(x - 0.2, t[f"{metrica}_modelo"], 0.4, label="XGBoost (log1p)")
            ax.bar(x + 0.2, t[f"{metrica}_persistencia"], 0.4, label="Persistencia")
            ax.set_xticks(x, t[columna].astype(str))
            ax.set_ylabel(f"{metrica.upper()} (casos)")
            ax.set_title(f"h={h}: {metrica.upper()}")
    ejes[0, 0].legend()
    fig.suptitle(titulo)
    fig.tight_layout()
    return fig


def figura_fiabilidad(datos: pd.DataFrame, n_bins: int = 10):
    """Diagrama de fiabilidad por horizonte y bloque."""
    import matplotlib.pyplot as plt

    horizontes = sorted(datos.horizonte.unique())
    fig, ejes = plt.subplots(1, len(horizontes), figsize=(5.5 * len(horizontes), 5), squeeze=False)
    for j, h in enumerate(horizontes):
        ax = ejes[0, j]
        ax.plot([0, 1], [0, 1], color="grey", linestyle="--", label="Calibración perfecta")
        for bloque, g in datos[datos.horizonte.eq(h)].groupby("bloque"):
            c = curva_fiabilidad(g.brote, g.probabilidad_brote, n_bins)
            brier = np.mean((g.probabilidad_brote - g.brote) ** 2)
            ax.plot(c.prob_media, c.frecuencia_observada, marker="o",
                    label=f"{bloque.replace('temporada_', 'temp. ')} (Brier {brier:.3f})")
        ax.axvline(0.5, color="black", linewidth=0.8)
        ax.set_xlabel("Probabilidad predicha de brote")
        ax.set_ylabel("Frecuencia observada de brote")
        ax.set_title(f"h={h}")
        ax.legend(fontsize=8)
    fig.suptitle("Diagrama de fiabilidad del clasificador (base_6 + población 2017)")
    fig.tight_layout()
    return fig


def figura_falsos_positivos(tabla: pd.DataFrame):
    """Barras apiladas de falsos positivos adyacentes y aislados."""
    import matplotlib.pyplot as plt

    fig, ax = plt.subplots(figsize=(11, 4.5))
    etiquetas = [f"h={r.horizonte} {r.bloque[-4:]}\n{r.alerta.replace('alerta_', '')}" for r in tabla.itertuples()]
    x = np.arange(len(tabla))
    ax.bar(x, tabla.adyacentes, label="Adyacentes a una racha (±2 semanas)")
    ax.bar(x, tabla.aislados, bottom=tabla.adyacentes, label="Aislados")
    ax.set_xticks(x, etiquetas, fontsize=7)
    ax.set_ylabel("Falsos positivos (distrito-semanas)")
    ax.legend()
    fig.tight_layout()
    return fig


def figura_antelacion(tabla: pd.DataFrame, alertas: list[str]):
    """Distribución de la antelación de la primera alerta por regla y horizonte."""
    import matplotlib.pyplot as plt

    horizontes = sorted(tabla.horizonte.unique())
    fig, ejes = plt.subplots(1, len(horizontes), figsize=(6 * len(horizontes), 4.5), squeeze=False)
    for j, h in enumerate(horizontes):
        ax = ejes[0, j]
        t = tabla[tabla.horizonte.eq(h)]
        valores = sorted(set(np.concatenate([t[a].dropna().to_numpy() for a in alertas])))
        x = np.arange(len(valores) + 1)
        ancho = 0.8 / len(alertas)
        for k, alerta in enumerate(alertas):
            conteo = [int(t[alerta].eq(v).sum()) for v in valores] + [int(t[alerta].isna().sum())]
            ax.bar(x + k * ancho, conteo, ancho, label=alerta.replace("alerta_", ""))
        ax.set_xticks(x + 0.4 - ancho / 2, [f"{int(v)}" for v in valores] + ["sin\nalerta"])
        ax.set_xlabel("Antelación de la primera alerta (semanas antes del inicio)")
        ax.set_ylabel("Episodios")
        ax.set_title(f"h={h}, temporadas 2022–2024")
        ax.legend(fontsize=8)
    fig.tight_layout()
    return fig
