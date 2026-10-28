"""Error diagnosis of the current models (phase 1 of the architecture study).

Everything is computed in memory from out-of-sample predictions already saved;
nothing is retrained or written to ``data/``. The full gold labels are only read
to locate streaks and adjacent weeks.

Definitions used in the diagnosis (retrospective, not operational):

- **Curve phase:** according to the block's observed regional curve (sum of
  the 65 districts per target week). Valley: under 10 % of the block's
  maximum; peak: at least 60 %; rise/fall: the rest, before/after the week of
  the maximum.
- **District size:** terciles of the cases accumulated before the start of
  season 2021, that is, before any evaluated block.
- **Episode:** streak of consecutive weeks with ``brote = 1`` in a district.
- **Lead time:** weeks between issuing the first relevant alert (target ``w``
  issued at ``w - h``) and the episode start ``t0``: ``h - (w - t0)``. Alerts
  with a target from ``t0 - 2`` onwards are considered.
"""

import json
from pathlib import Path

import numpy as np
import pandas as pd

from denguekay.data.seasons import assign_season
from denguekay.evaluation.metrics import alerts_from_counts, alert_metrics
from denguekay.model.train import MIN_OUTBREAK_CASES, SEASON_START_WEEK
from denguekay.data.validation.forecast_contract import KEY

REGRESSION_VARIANT = "base_6"
CLASSIFICATION_VARIANT = "base_6_poblacion_2017"
DIAGNOSIS_BLOCKS = ("temporada_2022", "temporada_2023", "temporada_2024")
CASE_LEVELS = (0, 1, 5, 20, 100)
LEVEL_LABELS = ("0", "1–4", "5–19", "20–99", "≥100")
PHASE_ORDER = ("valle", "subida", "pico", "bajada")
ADJACENCY_WINDOW = 2
NO_PREVIOUS_OUTBREAK = 8
WEEK = pd.Timedelta(days=7)


def selected_predictions(predictions: pd.DataFrame, report: dict) -> pd.DataFrame:
    """Join the ``base_6`` regression and the classification with population per district-week.

    It adds each block's chronologically calibrated probability threshold
    (``NaN`` in 2021, which only served as the initial calibration).
    """
    cols = KEY + ["semana_inicio", "horizonte", "bloque", "temporada",
                    "casos_Dengue", "brote", "umbral_brote_casos"]
    reg = predictions[predictions.variante.eq(REGRESSION_VARIANT)]
    cls = predictions[predictions.variante.eq(CLASSIFICATION_VARIANT)]
    if reg.empty or cls.empty:
        raise ValueError("Faltan las variantes seleccionadas en las predicciones")
    reg = reg.assign(persistencia=np.where(
        reg.horizonte.eq(2), reg.get("casos_lag_2"), reg.get("casos_lag_4")))
    data = reg[cols + ["casos_predichos", "persistencia"]].merge(
        cls[cols + ["probabilidad_brote"]], on=cols, how="inner", validate="one_to_one")
    if len(data) != len(reg) or len(data) != len(cls):
        raise ValueError("Regresión y clasificación no cubren las mismas filas")
    if data.persistencia.isna().any():
        raise ValueError("Persistencia incompleta")
    thresholds = {}
    for h, block_h in report["horizontes"].items():
        result = block_h["variantes"][CLASSIFICATION_VARIANT]
        for fold in [*result["folds"], result["sensibilidad_2025"]]:
            thresholds[(int(h), fold["bloque"])] = fold["clasificacion"]["umbral_probabilidad"]
    data["umbral_probabilidad"] = [
        thresholds.get((h, b), np.nan) for h, b in zip(data.horizonte, data.bloque)]
    data["semana_inicio"] = pd.to_datetime(data.semana_inicio)
    data["ubigeo"] = data.ubigeo.astype("string")
    return data.sort_values(["horizonte", "bloque", "ubigeo", "semana_inicio"]).reset_index(drop=True)


def add_alerts(data: pd.DataFrame) -> pd.DataFrame:
    """Compute the four alert rules compared in the diagnosis."""
    output = data.copy()
    limit = output.umbral_brote_casos.to_numpy(float)
    output["alerta_regresion"] = alerts_from_counts(
        output.casos_predichos.to_numpy(float), limit, MIN_OUTBREAK_CASES)
    output["alerta_persistencia"] = alerts_from_counts(
        output.persistencia.to_numpy(float), limit, MIN_OUTBREAK_CASES)
    output["alerta_cls_calibrada"] = output.probabilidad_brote >= output.umbral_probabilidad
    output["alerta_cls_050"] = output.probabilidad_brote >= 0.5
    return output


def case_level(cases: pd.Series) -> pd.Series:
    """Classify the actual cases into fixed levels."""
    cutoffs = [*CASE_LEVELS, np.inf]
    return pd.cut(cases, bins=[c - 0.5 for c in cutoffs], labels=LEVEL_LABELS, right=False)


def curve_phase(data: pd.DataFrame, valley: float = 0.10, peak: float = 0.60) -> pd.Series:
    """Assign the phase of the observed regional curve to each row of the block."""
    phases = pd.Series(index=data.index, dtype="object")
    for _, group in data.groupby(["horizonte", "bloque"]):
        curve = group.groupby("semana_inicio").casos_Dengue.sum()
        maximum = curve.max()
        max_week = curve.idxmax()
        if maximum <= 0:
            labels = pd.Series("valle", index=curve.index)
        else:
            rel = curve / maximum
            labels = pd.Series(np.where(curve.index < max_week, "subida", "bajada"), index=curve.index)
            labels[rel >= peak] = "pico"
            labels[rel < valley] = "valle"
        phases.loc[group.index] = group.semana_inicio.map(labels).to_numpy()
    return pd.Categorical(phases, categories=PHASE_ORDER, ordered=True)


def district_terciles(labels: pd.DataFrame, cutoff_season: int = 2021) -> pd.Series:
    """Terciles of the cases accumulated before the cutoff season, per ubigeo."""
    season = assign_season(labels.anio, labels.semana, SEASON_START_WEEK)
    previous_rows = labels.loc[season < cutoff_season].groupby("ubigeo").casos_Dengue.sum()
    span = previous_rows.rank(method="first")
    return pd.qcut(span, 3, labels=["bajo", "medio", "alto"]).rename("tercil_distrito")


def error_breakdown(data: pd.DataFrame, por: list[str]) -> pd.DataFrame:
    """MAE, RMSE and bias of the regressor and of persistence per group."""
    def summary(g: pd.DataFrame) -> pd.Series:
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
    return data.groupby(por, observed=True).apply(summary, include_groups=False).reset_index()


def adjacent_to_outbreak(rows: pd.DataFrame, labels: pd.DataFrame,
                      window: int = ADJACENCY_WINDOW) -> np.ndarray:
    """Tell whether there is a ``brote`` week of the same district within ±``window`` weeks."""
    positives = labels.loc[labels.brote.eq(1), ["ubigeo", "semana_inicio"]]
    by_district = {u: set(g.semana_inicio) for u, g in positives.groupby("ubigeo")}
    shifts = [d * WEEK for d in range(-window, window + 1) if d]
    return np.array([
        any(s + d in by_district.get(u, ()) for d in shifts)
        for u, s in zip(rows.ubigeo, rows.semana_inicio)
    ], dtype=bool)


def false_positives(data: pd.DataFrame, labels: pd.DataFrame, alert: str) -> pd.DataFrame:
    """Count false positives adjacent to a real streak and isolated ones."""
    fp = data.loc[data[alert] & data.brote.eq(0)]
    fp = fp.assign(adyacente=adjacent_to_outbreak(fp, labels))
    table = fp.groupby(["horizonte", "bloque"]).adyacente.agg(fp="size", adyacentes="sum").reset_index()
    table["aislados"] = table.fp - table.adyacentes
    table["fraccion_adyacentes"] = table.adyacentes / table.fp
    table.insert(0, "alerta", alert)
    return table


def reliability_curve(y: np.ndarray, p: np.ndarray, n_bins: int = 10) -> pd.DataFrame:
    """Observed frequency against mean probability in equal-width bins."""
    y, p = np.asarray(y, float), np.asarray(p, float)
    bins = np.minimum((p * n_bins).astype(int), n_bins - 1)
    table = pd.DataFrame({"bin": bins, "y": y, "p": p}).groupby("bin").agg(
        n=("y", "size"), prob_media=("p", "mean"), frecuencia_observada=("y", "mean"))
    table.index = [f"[{b / n_bins:.1f}, {(b + 1) / n_bins:.1f})" for b in table.index]
    return table


def probability_metrics(data: pd.DataFrame) -> pd.DataFrame:
    """Brier, AUPRC and alerts with the 0.50 and the calibrated threshold, per block."""
    rows = []
    for (h, block), g in data.groupby(["horizonte", "bloque"]):
        y, p = g.brote.to_numpy(int), g.probabilidad_brote.to_numpy(float)
        row = {"horizonte": h, "bloque": block, "positivos": int(y.sum()),
                "prob_media": p.mean(), "prevalencia": y.mean(),
                "brier": float(np.mean((p - y) ** 2))}
        for name, alert in (("050", "alerta_cls_050"), ("calibrada", "alerta_cls_calibrada")):
            m = alert_metrics(y, g[alert].to_numpy(bool), score=p)
            row.update({f"{k}_{name}": m[k] for k in ("vp", "fp", "fn", "precision", "recall", "f1")})
            row["auprc"] = m["auprc"]
        row["umbral_calibrado"] = g.umbral_probabilidad.iloc[0]
        rows.append(row)
    return pd.DataFrame(rows)


def episodes(labels: pd.DataFrame, max_gap: int = ADJACENCY_WINDOW) -> pd.DataFrame:
    """``brote`` episodes per district, joining gaps of up to ``max_gap`` weeks.

    ``semanas_previas_sin_brote`` counts the weeks between the end of the
    district's previous episode and this start (``inf`` if there was none).
    """
    pos = labels.loc[labels.brote.eq(1), ["ubigeo", "semana_inicio"]].sort_values(
        ["ubigeo", "semana_inicio"])
    gap = pos.groupby("ubigeo").semana_inicio.diff()
    new_row = gap.isna() | gap.gt((max_gap + 1) * WEEK)
    pos = pos.assign(episodio=new_row.cumsum())
    eps = pos.groupby("episodio").agg(
        ubigeo=("ubigeo", "first"), inicio=("semana_inicio", "min"),
        fin=("semana_inicio", "max"), semanas_brote=("semana_inicio", "size")).reset_index(drop=True)
    previous_end = eps.groupby("ubigeo").fin.shift()
    eps["semanas_previas_sin_brote"] = ((eps.inicio - previous_end).dt.days / 7 - 1).fillna(np.inf)
    return eps


def episode_lead_time(data: pd.DataFrame, labels: pd.DataFrame, alerts: list[str],
                         previous: int = ADJACENCY_WINDOW) -> pd.DataFrame:
    """Lead time of the first relevant alert per episode starting in the block.

    Only alerts of the same block are used; an episode starting in the first
    weeks may lose alerts issued in the previous block.
    """
    eps = episodes(labels)
    rows = []
    for (h, block), g in data.groupby(["horizonte", "bloque"]):
        weeks = g.semana_inicio
        inside = eps[eps.inicio.between(weeks.min(), weeks.max())]
        by_district = {u: gg.set_index("semana_inicio") for u, gg in g.groupby("ubigeo")}
        for ep in inside.itertuples(index=False):
            series = by_district.get(ep.ubigeo)
            row = {"horizonte": h, "bloque": block, "ubigeo": ep.ubigeo,
                    "inicio": ep.inicio, "semanas_brote": ep.semanas_brote,
                    "semanas_previas_sin_brote": ep.semanas_previas_sin_brote}
            window = series.loc[ep.inicio - previous * WEEK: ep.fin] if series is not None else None
            for alert in alerts:
                active = window.index[window[alert].to_numpy(bool)] if window is not None else []
                if len(active):
                    w = active.min()
                    row[alert] = h - (w - ep.inicio).days // 7
                else:
                    row[alert] = np.nan
            rows.append(row)
    return pd.DataFrame(rows)


def lead_time_summary(table: pd.DataFrame, alerts: list[str],
                       no_previous_outbreak: int = 0) -> pd.DataFrame:
    """Detection and lead time per alert rule, horizon and block.

    With ``no_previous_outbreak = k`` only "clean" onsets count: episodes without
    ``brote`` weeks in the district's ``k`` previous weeks, where an early alert
    cannot be a carry-over of the previous episode.
    """
    rows = []
    table = table[table.semanas_previas_sin_brote >= no_previous_outbreak]
    for (h, block), g in table.groupby(["horizonte", "bloque"]):
        for alert in alerts:
            a = g[alert]
            rows.append({
                "horizonte": h, "bloque": block, "alerta": alert, "episodios": len(g),
                "detectados": float(a.notna().mean()),
                "antes_del_inicio": float((a >= 1).mean()),
                "antelacion_2_o_mas": float((a >= 2).mean()),
                "antelacion_mediana": float(a.median()) if a.notna().any() else np.nan,
            })
    return pd.DataFrame(rows)


def error_concentration(data: pd.DataFrame, n_districts: int = 5) -> pd.DataFrame:
    """Share of the absolute and squared error contributed by 2023 and the largest districts."""
    rows = []
    for h, g in data.groupby("horizonte"):
        top = g.groupby("ubigeo").casos_Dengue.sum().nlargest(n_districts).index
        for name, col in (("modelo", "casos_predichos"), ("persistencia", "persistencia")):
            ea = (g[col] - g.casos_Dengue).abs()
            ec = (g[col] - g.casos_Dengue) ** 2
            for group, mask in (("temporada_2023", g.bloque.eq("temporada_2023")),
                                   (f"top{n_districts}_distritos", g.ubigeo.isin(top)),
                                   ("ambos", g.bloque.eq("temporada_2023") & g.ubigeo.isin(top))):
                rows.append({
                    "horizonte": h, "pronostico": name, "grupo": group,
                    "fraccion_filas": float(mask.mean()),
                    "fraccion_casos": float(g.casos_Dengue[mask].sum() / g.casos_Dengue.sum()),
                    "fraccion_error_absoluto": float(ea[mask].sum() / ea.sum()),
                    "fraccion_error_cuadratico": float(ec[mask].sum() / ec.sum()),
                })
    return pd.DataFrame(rows)


def to_json(table: pd.DataFrame) -> list[dict]:
    """Convert a table to JSON records with native numbers and dates as text."""
    return json.loads(table.to_json(orient="records", date_format="iso", force_ascii=False))


def save_metrics_section(path: Path, section: str, content: dict) -> Path:
    """Write or replace a section of the study's metrics JSON."""
    path = Path(path)
    actual = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    actual[section] = content
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(actual, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path


# ---------------------------------------------------------------------------
# Figures
# ---------------------------------------------------------------------------

def save_figure(fig, folder: Path, name: str) -> Path:
    """Save the figure as PNG in ``folder`` and close it."""
    import matplotlib.pyplot as plt

    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"{name}.png"
    fig.savefig(path, dpi=130, bbox_inches="tight")
    plt.close(fig)
    return path


def errors_figure(table: pd.DataFrame, column: str, title: str):
    """MAE and RMSE bars of the model and of persistence per group and horizon."""
    import matplotlib.pyplot as plt

    horizons = sorted(table.horizonte.unique())
    fig, axes = plt.subplots(2, len(horizons), figsize=(5.5 * len(horizons), 7), squeeze=False)
    for j, h in enumerate(horizons):
        t = table[table.horizonte.eq(h)]
        x = np.arange(len(t))
        for i, metric in enumerate(("mae", "rmse")):
            ax = axes[i, j]
            ax.bar(x - 0.2, t[f"{metric}_modelo"], 0.4, label="XGBoost (log1p)")
            ax.bar(x + 0.2, t[f"{metric}_persistencia"], 0.4, label="Persistencia")
            ax.set_xticks(x, t[column].astype(str))
            ax.set_ylabel(f"{metric.upper()} (casos)")
            ax.set_title(f"h={h}: {metric.upper()}")
    axes[0, 0].legend()
    fig.suptitle(title)
    fig.tight_layout()
    return fig


def reliability_figure(data: pd.DataFrame, n_bins: int = 10):
    """Reliability diagram per horizon and block."""
    import matplotlib.pyplot as plt

    horizons = sorted(data.horizonte.unique())
    fig, axes = plt.subplots(1, len(horizons), figsize=(5.5 * len(horizons), 5), squeeze=False)
    for j, h in enumerate(horizons):
        ax = axes[0, j]
        ax.plot([0, 1], [0, 1], color="grey", linestyle="--", label="Calibración perfecta")
        for block, g in data[data.horizonte.eq(h)].groupby("bloque"):
            c = reliability_curve(g.brote, g.probabilidad_brote, n_bins)
            brier = np.mean((g.probabilidad_brote - g.brote) ** 2)
            ax.plot(c.prob_media, c.frecuencia_observada, marker="o",
                    label=f"{block.replace('temporada_', 'temp. ')} (Brier {brier:.3f})")
        ax.axvline(0.5, color="black", linewidth=0.8)
        ax.set_xlabel("Probabilidad predicha de brote")
        ax.set_ylabel("Frecuencia observada de brote")
        ax.set_title(f"h={h}")
        ax.legend(fontsize=8)
    fig.suptitle("Diagrama de fiabilidad del clasificador (base_6 + población 2017)")
    fig.tight_layout()
    return fig


def false_positives_figure(table: pd.DataFrame):
    """Stacked bars of adjacent and isolated false positives."""
    import matplotlib.pyplot as plt

    fig, ax = plt.subplots(figsize=(11, 4.5))
    labels = [f"h={r.horizonte} {r.bloque[-4:]}\n{r.alerta.replace('alerta_', '')}" for r in table.itertuples()]
    x = np.arange(len(table))
    ax.bar(x, table.adyacentes, label="Adyacentes a una racha (±2 semanas)")
    ax.bar(x, table.aislados, bottom=table.adyacentes, label="Aislados")
    ax.set_xticks(x, labels, fontsize=7)
    ax.set_ylabel("Falsos positivos (distrito-semanas)")
    ax.legend()
    fig.tight_layout()
    return fig


def lead_time_figure(table: pd.DataFrame, alerts: list[str]):
    """Distribution of the first alert's lead time per rule and horizon."""
    import matplotlib.pyplot as plt

    horizons = sorted(table.horizonte.unique())
    fig, axes = plt.subplots(1, len(horizons), figsize=(6 * len(horizons), 4.5), squeeze=False)
    for j, h in enumerate(horizons):
        ax = axes[0, j]
        t = table[table.horizonte.eq(h)]
        values = sorted(set(np.concatenate([t[a].dropna().to_numpy() for a in alerts])))
        x = np.arange(len(values) + 1)
        width = 0.8 / len(alerts)
        for k, alert in enumerate(alerts):
            count = [int(t[alert].eq(v).sum()) for v in values] + [int(t[alert].isna().sum())]
            ax.bar(x + k * width, count, width, label=alert.replace("alerta_", ""))
        ax.set_xticks(x + 0.4 - width / 2, [f"{int(v)}" for v in values] + ["sin\nalerta"])
        ax.set_xlabel("Antelación de la primera alerta (semanas antes del inicio)")
        ax.set_ylabel("Episodios")
        ax.set_title(f"h={h}, temporadas 2022–2024")
        ax.legend(fontsize=8)
    fig.tight_layout()
    return fig
