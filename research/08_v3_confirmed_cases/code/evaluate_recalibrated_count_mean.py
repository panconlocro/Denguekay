"""Evaluate the mean implied by the already archived PIT-recalibrated distributions."""

from concurrent.futures import ThreadPoolExecutor, as_completed
import json
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import special, stats

from evaluate_count_intervals import (
    DECISIVE, GRID, KEY, MODELS, OUTPUT, archive, levels, nb_params, point_diagnostics,
    read_prediction, strata_for,
)
from denguekay.evaluation.protocol import SEEDS


CORE = ("b3_obs", "d3_obs", "historia_geo")
DESTINATION = OUTPUT / "media_recalibrada"
GROUPS = ["variante", "horizonte", "estrato"]
METRICS = ["mae", "rmse", "mae_log1p", "sesgo", "razon_pronosticada_observada"]


def quantile_integral(r, p):
    """Integral of the NB2 quantile function from 0 to each PIT grid node."""
    mu = r * (1 - p) / p
    integral = np.zeros((len(r), len(GRID)))
    integral[:, -1] = mu
    nodes = GRID[1:-1]
    row, col = np.nonzero(nodes > np.exp(r[:, None] * np.log(p[:, None])))
    probability, size, success = nodes[col], r[row], p[row]
    k = stats.nbinom.ppf(probability, size, success)
    if not np.isfinite(k).all() or (k < 0).any():
        raise ValueError("Cuantil interior NB2 inválido")
    previous_cdf = np.zeros(len(k))
    positive = k > 0
    previous_cdf[positive] = special.betainc(size[positive], k[positive], success[positive])
    fraction_at_k = np.maximum(probability - previous_cdf, 0)
    truncated = np.zeros(len(k))
    above_one = k > 1
    truncated[above_one] = mu[row[above_one]] * special.betainc(
        size[above_one] + 1, k[above_one] - 1, success[above_one])
    integral[row, col + 1] = truncated + k * fraction_at_k
    mass = np.diff(integral, axis=1)
    if (mass < -1e-10 * np.maximum(1, mu[:, None])).any():
        raise ValueError("La integral cuantílica no es creciente")
    return mass


def checked_map(group, level):
    curve = group.loc[group.nivel.eq(str(level))].sort_values("pit")
    np.testing.assert_allclose(curve.pit, GRID, atol=1e-15, rtol=0)
    cdf = curve.cdf.to_numpy()
    if not np.isclose(cdf[0], 0, atol=1e-14) or not np.isclose(cdf[-1], 1, atol=1e-14):
        raise ValueError(f"Mapa PIT inválido para el nivel {level}")
    slope = np.diff(cdf) / np.diff(GRID)
    if (slope <= 0).any():
        raise ValueError(f"Mapa PIT no monótono para el nivel {level}")
    return slope


def recalibrated_means(part, maps):
    mu = part.conteo_publicado.to_numpy()
    r, p = nb_params(mu, part.alpha_usada)
    integrals = quantile_integral(r, p)
    np.testing.assert_allclose(integrals.sum(axis=1), mu, atol=1.1e-9, rtol=1e-12)
    global_mean = integrals @ checked_map(maps, "global")
    group = levels(mu)
    local_slopes = np.vstack([checked_map(maps, j) for j in range(3)])
    local_mean = np.einsum("ij,ij->i", integrals, local_slopes[group])
    if not (np.isfinite(global_mean).all() and np.isfinite(local_mean).all()
            and (global_mean >= 0).all() and (local_mean >= 0).all()):
        raise ValueError("Media recalibrada inválida")
    return global_mean, local_mean


def evaluate_one(variant, seed, path, map_rows, reference):
    data = read_prediction(path, [*KEY, "conteo_publicado", "alpha_usada"])
    data = data.loc[data.bloque.isin(DECISIVE)].reset_index(drop=True)
    pd.testing.assert_frame_equal(data[KEY], reference[KEY])
    rows, forecasts = [], []
    blocks = {(block, int(h)): group for (block, h), group in map_rows.groupby(["bloque", "horizonte"])}
    for (block, h), part in data.groupby(["bloque", "horizonte"]):
        global_mean, level_mean = recalibrated_means(part, blocks[(block, h)])
        forecasts.append(part.assign(media_pit_global=global_mean, media_pit_por_nivel=level_mean))
        variants = {"publicado": part.conteo_publicado, "media_pit_global": global_mean,
                    "media_pit_por_nivel": level_mean}
        for stratum, mask in strata_for(part):
            if not mask.any():
                continue
            for name, mu in variants.items():
                rows.append({"variante": variant, "semilla": seed, "bloque": block, "horizonte": h,
                             "estrato": stratum, "conteo": name, "filas": int(mask.sum()),
                             **point_diagnostics(part, mask, mu)})
    pd.concat(forecasts).sort_index().to_csv(DESTINATION / f"{variant}_s{seed}.csv.gz", index=False)
    print(f"{variant} s{seed}: {len(data)} medias evaluadas.", flush=True)
    return pd.DataFrame(rows)


def summarize(scores):
    scores.to_csv(DESTINATION / "metricas_por_temporada_y_semilla.csv", index=False)
    keys = [*GROUPS, "conteo"]
    season = scores.groupby([*keys, "bloque"], as_index=False).median(numeric_only=True).drop(columns="semilla")
    season.to_csv(DESTINATION / "metricas_por_temporada.csv", index=False)
    season.groupby(keys, as_index=False).mean(numeric_only=True).to_csv(DESTINATION / "resumen.csv", index=False)
    index = [*GROUPS, "bloque", "semilla"]
    wide = scores.pivot(index=index, columns="conteo", values=METRICS)
    contrasts = []
    for adjusted in ("media_pit_global", "media_pit_por_nivel"):
        change = wide.xs(adjusted, level="conteo", axis=1) - wide.xs("publicado", level="conteo", axis=1)
        change["mae_relativo"] = change.mae / wide[("mae", "publicado")].replace(0, np.nan)
        contrasts.append(change.reset_index().assign(ajuste=adjusted))
    detail = pd.concat(contrasts, ignore_index=True).groupby([*GROUPS, "bloque", "ajuste"], as_index=False).median(
        numeric_only=True).drop(columns="semilla")
    detail.to_csv(DESTINATION / "cambios_pareados_por_temporada.csv", index=False)
    detail.groupby([*GROUPS, "ajuste"], as_index=False).agg(
        **{metric: (metric, "mean") for metric in [*METRICS, "mae_relativo"]},
        temporadas=("mae", "size"), temporadas_mejora_mae=("mae", lambda s: int(s.lt(0).sum())),
    ).to_csv(DESTINATION / "resumen_cambios_pareados.csv", index=False)


def main():
    source_manifest = OUTPUT / "manifiesto.json"
    manifest = json.loads(source_manifest.read_text())
    maps_path = OUTPUT / "mapas_pit.csv.gz"
    cutoffs = pd.read_csv(OUTPUT / "cortes_pit.csv.gz", parse_dates=["corte", "ultimo_cierre"])
    if not cutoffs.ultimo_cierre.le(cutoffs.corte).all():
        raise ValueError("El mapa de calibración incluye semanas todavía abiertas")
    maps = pd.read_csv(maps_path, dtype={"nivel": str}, float_precision="round_trip")
    maps = maps.loc[maps.variante.isin(CORE)]
    expected = {(model, seed) for model in CORE for seed in SEEDS}
    if set(maps.groupby(["variante", "semilla"]).groups) != expected:
        raise ValueError("Faltan mapas de los XGBoost")
    if not maps.groupby(["variante", "semilla", "bloque", "horizonte", "nivel"]).size().eq(len(GRID)).all():
        raise ValueError("Mapa de calibración incompleto")
    paths = {(variant, seed): MODELS / f"{variant}_s{seed}" / "predicciones.csv.gz"
             for variant, seed in expected}
    hashes = {str(path.relative_to(archive.ROOT)): archive.sha256(path) for path in paths.values()}
    if any(manifest["entradas"].get(path) != digest for path, digest in hashes.items()):
        raise ValueError("Un archivo de pronósticos cambió desde la evaluación de intervalos")
    ref = read_prediction(paths[("historia_geo", 17)], KEY)
    ref = ref.loc[ref.bloque.isin(DECISIVE)].reset_index(drop=True)
    if not ref.groupby("horizonte").size().eq(20410).all():
        raise ValueError("Soporte decisivo inesperado")
    DESTINATION.mkdir(exist_ok=True)
    with ThreadPoolExecutor(max_workers=4) as pool:
        jobs = [pool.submit(evaluate_one, variant, seed, paths[(variant, seed)], group, ref)
                for (variant, seed), group in maps.groupby(["variante", "semilla"])]
        scores = pd.concat([job.result() for job in as_completed(jobs)], ignore_index=True)
    summarize(scores)
    archive.write_json(DESTINATION / "manifiesto.json", {
        "pronosticos": hashes, "mapas_pit_sha256": archive.sha256(maps_path),
        "intervalos_huella": manifest["huella"], "codigo": archive.sha256(Path(__file__)),
        "bloques": sorted(DECISIVE), "semillas": SEEDS,
    })


if __name__ == "__main__":
    main()
