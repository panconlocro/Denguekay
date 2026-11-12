"""Score NB2 count intervals and chronological PIT recalibration."""

from concurrent.futures import ThreadPoolExecutor, as_completed
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats

from denguekay.evaluation.protocol import block_cutoff
from denguekay.model.probabilistic_output import negative_binomial_dispersion_detail
from denguekay.serving.predictors.v2_e3_s4 import interval as serving_interval
from run_contribution import training_data
import run_spatial_controls as spatial


archive = spatial.archive
OUTPUT = archive.OUTPUT / "intervalos_revision"
STUDY = "v3_confirmados_intervalos_revision"
MODELS = archive.OUTPUT / "ajuste_simetrico" / "evaluacion"
BENCH = archive.OUTPUT / "comparadores_revision"
LEVELS = np.array([0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 0.95, 0.98])
ALPHAS = 1 - LEVELS
QUANTILES = np.r_[ALPHAS[::-1] / 2, 0.5, 1 - ALPHAS / 2]
GRID = np.linspace(0, 1, 201)
REPORT_LEVELS = (0.5, 0.8, 0.95)
DECISIVE = {f"temporada_{year}" for year in spatial.DECIDING}
KEY = ["bloque", "horizonte", "ubigeo", "semana_inicio", "origen_cierre",
       "brote", "casos_Dengue", "umbral_brote_casos", "persistencia"]
DATE_FIELDS = ["semana_inicio", "origen_cierre"]
VARIANTS = {"persistencia_nb2": "persistencia", "estacional_nb2": "estacional"}


def nb_params(mu, alpha):
    r = 1 / np.asarray(alpha, float)
    return r, r / (r + np.maximum(np.asarray(mu, float), 1e-9))


def bounds_for_pit(y, r, p):
    return stats.nbinom.cdf(y - 1, r, p), stats.nbinom.cdf(y, r, p)


def pit_histogram(lo, hi, grid):
    """Exact mass per bin of the mixture of uniform PIT intervals."""
    lo, hi = np.asarray(lo, float), np.asarray(hi, float)
    if len(lo) == 0 or not (np.isfinite(lo).all() and np.isfinite(hi).all()) or (lo > hi).any():
        raise ValueError("Intervalos PIT inválidos")
    bins = len(grid) - 1
    point = hi - lo <= 1e-12
    located = np.minimum(np.searchsorted(grid, lo[point], side="right") - 1, bins - 1)
    mass = np.bincount(located, minlength=bins).astype(float)
    lo, hi = lo[~point], hi[~point]
    first = np.searchsorted(grid, lo, side="right") - 1
    last = np.searchsorted(grid, hi, side="left") - 1
    same = first == last
    mass += np.bincount(first[same], minlength=bins)
    a, b = first[~same], last[~same]
    lo, hi = lo[~same], hi[~same]
    width = hi - lo
    mass += np.bincount(a, weights=(grid[a + 1] - lo) / width, minlength=bins)
    mass += np.bincount(b, weights=(hi - grid[b]) / width, minlength=bins)
    interior = b > a + 1
    rate = 1 / width[interior]
    steps = (np.bincount(a[interior] + 1, weights=rate, minlength=bins)
             - np.bincount(b[interior], weights=rate, minlength=bins))
    mass += np.maximum(np.cumsum(steps), 0) * np.diff(grid)
    return mass


def fit_map(lo, hi):
    mass = pit_histogram(lo, hi, GRID)
    np.testing.assert_allclose(mass.sum(), len(lo), rtol=0, atol=1e-7)
    cdf = 0.95 * np.r_[0, np.cumsum(mass)] / mass.sum() + 0.05 * GRID
    cdf[-1] = 1.0
    if not (np.diff(cdf) > 0).all():
        raise ValueError("Mapa PIT no invertible")
    return cdf


def levels(mu):
    return np.searchsorted([1.0, 5.0], np.asarray(mu), side="right")


def maps_for_block(past, mu_column, pit_lo, pit_hi):
    i = past.index
    global_map = fit_map(pit_lo[i], pit_hi[i])
    fitted = {}
    for group in range(3):
        local = i[levels(past[mu_column]) == group]
        weight = len(local) / (len(local) + 500)
        mapping = global_map if not len(local) else (1 - weight) * global_map + weight * fit_map(pit_lo[local], pit_hi[local])
        fitted[group] = (len(local), mapping)
    return global_map, fitted


def from_mapping(part, r, p, lo, hi, global_map=None, local_maps=None):
    q = np.broadcast_to(QUANTILES, (len(part), len(QUANTILES))).copy()
    lo, hi = lo.copy(), hi.copy()
    group = levels(part.conteo_publicado)
    if global_map is not None:
        for level in range(3):
            mask = group == level
            mapping = global_map if local_maps is None else local_maps[level][1]
            q[mask] = np.interp(QUANTILES, mapping, GRID)
            lo[mask] = np.interp(lo[mask], GRID, mapping)
            hi[mask] = np.interp(hi[mask], GRID, mapping)
    values = stats.nbinom.ppf(q, r[:, None], p[:, None])
    if not np.isfinite(values).all() or (values < 0).any() or (np.diff(values, axis=1) < 0).any():
        raise ValueError("Cuantiles de conteo inválidos")
    return values, lo, hi


def score_count_distribution(y, quantiles):
    n = len(LEVELS)
    median = quantiles[:, n]
    low = quantiles[:, :n][:, ::-1]
    high = quantiles[:, n + 1:]
    width = high - low
    below = np.maximum(low - y[:, None], 0)
    above = np.maximum(y[:, None] - high, 0)
    normalizer = n + 0.5
    dispersion = width @ (ALPHAS / 2) / normalizer
    overprediction = (below.sum(axis=1) + np.maximum(median - y, 0) / 2) / normalizer
    underprediction = (above.sum(axis=1) + np.maximum(y - median, 0) / 2) / normalizer
    result = {"wis": dispersion + overprediction + underprediction, "wis_ancho": dispersion,
              "wis_sobreprediccion": overprediction, "wis_subprediccion": underprediction}
    for level in REPORT_LEVELS:
        index = int(np.flatnonzero(np.isclose(LEVELS, level))[0])
        tag = f"{level:.0%}".rstrip("%")
        result.update({f"cobertura_{tag}": (below[:, index] == 0) & (above[:, index] == 0),
                       f"ancho_{tag}": width[:, index], f"debajo_{tag}": below[:, index] > 0,
                       f"encima_{tag}": above[:, index] > 0})
    return pd.DataFrame(result)


def point_diagnostics(group, indices, mu):
    y = group.casos_Dengue.to_numpy()[indices]
    count = np.asarray(mu)[indices]
    error = count - y
    return {
        "mae": np.abs(error).mean(), "rmse": np.sqrt(np.mean(error ** 2)),
        "mae_log1p": np.abs(np.log1p(count) - np.log1p(y)).mean(), "sesgo": error.mean(),
        "suma_pronosticada": count.sum(), "suma_observada": y.sum(),
        "razon_pronosticada_observada": count.sum() / y.sum() if y.sum() else np.nan,
    }


def strata_for(part):
    cases = part.casos_Dengue.to_numpy()
    labels = part.brote.to_numpy(bool)
    return [
        ("todas", np.ones(len(part), dtype=bool)), ("sin_brote", ~labels), ("brote", labels),
        ("cero_casos", cases == 0), ("1_a_4_casos", (cases >= 1) & (cases < 5)),
        ("5_a_19_casos", (cases >= 5) & (cases < 20)), ("20_o_mas_casos", cases >= 20),
    ]


def with_baseline_dispersion(frame, count):
    result = frame.assign(mu_modelo=frame[count], conteo_publicado=frame[count], alpha_usada=np.nan)
    result["media_nb2"] = result[count].clip(lower=0.5)
    audit = []
    for h, group in result.groupby("horizonte"):
        for block, part in group.groupby("bloque"):
            cutoff = block_cutoff(part)
            past = group.loc[group.bloque.lt(block) & (group.semana_inicio + pd.Timedelta(days=6)).le(cutoff)]
            if past.empty:
                continue
            fit = negative_binomial_dispersion_detail(past.media_nb2, past.casos_Dengue)
            if not fit["convergio"]:
                raise ValueError(f"Dispersión de referencia no convergió en {block}, h{h}")
            result.loc[part.index, "alpha_usada"] = fit["alpha"]
            audit.append({"bloque": block, "horizonte": h, "corte": cutoff, "filas": len(past),
                          "ultimo_cierre": past.semana_inicio.max() + pd.Timedelta(days=6), **fit})
    return result, audit


def read_prediction(path, cols):
    frame = pd.read_csv(path, usecols=cols, dtype={"ubigeo": str}, parse_dates=DATE_FIELDS,
                        float_precision="round_trip")
    return frame.loc[frame.bloque.str.startswith("temporada_")].reset_index(drop=True)


def calculate(variant, seed, source, reference):
    if variant in VARIANTS:
        frame, alpha_audit = with_baseline_dispersion(reference, VARIANTS[variant])
    else:
        frame = read_prediction(source, [*KEY, "mu_modelo", "conteo_publicado", "alpha_usada"])
        pd.testing.assert_frame_equal(frame[KEY], reference[KEY])
        frame["media_nb2"] = frame.conteo_publicado
        alpha_audit = []
    calibration_support = frame.loc[frame.bloque.ge("temporada_2009")]
    if len(calibration_support) != 183300 or not calibration_support.alpha_usada.gt(0).all():
        raise ValueError(f"Soporte o dispersión inválidos en {variant}, semilla {seed}")
    y = frame.casos_Dengue.to_numpy()
    raw_r, raw_p = nb_params(frame.mu_modelo, frame.alpha_usada)
    r, p = nb_params(frame.media_nb2, frame.alpha_usada)
    lo, hi = bounds_for_pit(y, r, p)
    metric_rows, point_rows, maps, pits, audits = [], [], [], [], []
    for h, group in calibration_support.groupby("horizonte"):
        for block, part in group.loc[group.bloque.isin(DECISIVE)].groupby("bloque"):
            cutoff = block_cutoff(part)
            past = group.loc[group.bloque.lt(block) & (group.semana_inicio + pd.Timedelta(days=6)).le(cutoff)]
            global_map, local_maps = maps_for_block(past, "conteo_publicado", lo, hi)
            info = {"variante": variant, "semilla": seed, "bloque": block, "horizonte": h}
            audits.append({**info, "corte": cutoff, "n_calibracion": len(past),
                           "ultimo_cierre": past.semana_inicio.max() + pd.Timedelta(days=6)})
            for level, (n, curve) in {"global": (len(past), global_map), **local_maps}.items():
                maps.append(pd.DataFrame({**info, "nivel": level, "n": n, "pit": GRID, "cdf": curve}))
            part_y = part.casos_Dengue.to_numpy()
            i = part.index
            distributions = ["nb2_publicada", "pit_global", "pit_por_nivel"]
            if variant not in VARIANTS:
                distributions.insert(0, "nb2_bruta")
            for name in distributions:
                if name == "nb2_bruta":
                    lo_raw, hi_raw = bounds_for_pit(part_y, raw_r[i], raw_p[i])
                    q, lo_pit, hi_pit = from_mapping(part, raw_r[i], raw_p[i], lo_raw, hi_raw)
                else:
                    q, lo_pit, hi_pit = from_mapping(
                        part, r[i], p[i], lo[i], hi[i],
                        global_map if name != "nb2_publicada" else None,
                        local_maps if name == "pit_por_nivel" else None)
                if name == "nb2_publicada" and variant not in VARIANTS:
                    ll, uu = serving_interval(part.conteo_publicado.to_numpy(), part.alpha_usada.to_numpy(), 0.8)
                    idx = int(np.flatnonzero(np.isclose(LEVELS, 0.8))[0])
                    np.testing.assert_array_equal(q[:, len(LEVELS) - 1 - idx], ll)
                    np.testing.assert_array_equal(q[:, len(LEVELS) + 1 + idx], uu)
                scores = score_count_distribution(part_y, q)
                mass = pit_histogram(lo_pit, hi_pit, np.linspace(0, 1, 11))
                pits.append(pd.DataFrame({**info, "distribucion": name, "bin": np.arange(10),
                                          "filas": len(part), "masa": mass}))
                for stratum, mask in strata_for(part):
                    if mask.any():
                        metric_rows.append({**info, "distribucion": name, "estrato": stratum, "filas": int(mask.sum()),
                                            **scores.loc[mask].mean().to_dict()})
            for col in ("mu_modelo", "conteo_publicado"):
                if variant in VARIANTS and col == "mu_modelo":
                    continue
                for stratum, mask in strata_for(part):
                    if mask.any():
                        point_rows.append({**info, "conteo": col, "estrato": stratum, "filas": int(mask.sum()),
                                           **point_diagnostics(part, mask, part[col])})
    print(f"{variant}, semilla {seed}: intervalos y PIT verificados.", flush=True)
    return [pd.DataFrame(metric_rows), pd.DataFrame(point_rows), pd.concat(maps, ignore_index=True),
            pd.concat(pits, ignore_index=True), pd.DataFrame(audits),
            pd.DataFrame(alpha_audit).assign(variante=variant, semilla=seed)]


def main():
    _, _, quality, _ = training_data()
    path = MODELS / "historia_geo_s17" / "predicciones.csv.gz"
    reference = read_prediction(path, [*KEY, "estacional"])
    if len(reference) != 193440 or reference.duplicated(archive.closure.KEY).any():
        raise ValueError("Calendario común incompleto")
    paths = sorted([*MODELS.glob("*_s*/predicciones.csv.gz"), *BENCH.glob("*_s*/predicciones.csv.gz")])
    if len(paths) != 23:
        raise ValueError("Faltan archivos de los modelos y comparadores")
    jobs = [(*source.parent.name.rsplit("_s", 1), source) for source in paths]
    jobs += [(variant, "17", path) for variant in VARIANTS]
    OUTPUT.mkdir(parents=True, exist_ok=True)
    with ThreadPoolExecutor(max_workers=4) as pool:
        futures = [pool.submit(calculate, variant, int(seed), path, reference) for variant, seed, path in jobs]
        tables = [f.result() for f in as_completed(futures)]
    names = ["distribuciones", "conteos", "mapas_pit", "histogramas_pit", "cortes_pit", "dispersion_referencias"]
    for name, batch in zip(names, zip(*tables, strict=True), strict=True):
        table = pd.concat(batch, ignore_index=True).sort_values(["variante", "semilla", "bloque", "horizonte"])
        table.to_csv(OUTPUT / f"{name}.csv.gz", index=False)
    info = {"entradas": {str(p.relative_to(archive.ROOT)): archive.sha256(p) for p in paths},
            "codigo": archive.sha256(Path(__file__)),
            "protocolo": archive.sha256(Path(__file__).resolve().parents[1] / "protocolo_intervalos_conteos.md"),
            "temporadas": sorted(DECISIVE), "niveles": LEVELS.tolist()}
    fingerprint = hashlib.sha256(json.dumps(info, sort_keys=True).encode()).hexdigest()
    path = OUTPUT / "manifiesto.json"
    archive.write_json(path, {"huella": fingerprint, **info})
    detail = pd.read_csv(OUTPUT / "distribuciones.csv.gz")
    cols = ["wis", "cobertura_80", "ancho_80"]
    scores = detail.loc[detail.estrato.eq("todas")]
    report = {"experimento": STUDY, "horizontes": {}}
    for h, group in scores.groupby("horizonte"):
        vals = group.groupby(["variante", "distribucion", "bloque"])[cols].median().groupby(
            ["variante", "distribucion"]).mean()
        report["horizontes"][str(h)] = {"variantes": {
            f"{variant}_{distribution}": {"metricas": v}
            for (variant, distribution), v in vals.to_dict("index").items()}}
    run = archive.tracking.log_report(
        STUDY, report, metrics_path=path, output_dir=OUTPUT, gold_dir=archive.GOLD, data_quality=quality,
        log_datasets=False, tracking_uri=f"sqlite:///{archive.MLFLOW_DB.as_posix()}",
        fingerprint=fingerprint, description="WIS, cobertura y recalibración PIT cronológica de conteos.",
    )
    archive.write_json(path, {"huella": fingerprint, "mlflow_run": run, **info})


if __name__ == "__main__":
    main()
