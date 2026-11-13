"""Audit the common season calendar and the confirmed-case inputs for the paper."""

import pandas as pd

import run_experiment as previous
from denguekay.config.paths import BRONZE_EPI_CSV, DISTRICT_BOUNDARIES, SILVER_CHIRPS_PRECIP, SILVER_ENSO
from denguekay.data.processing.epi_cases import build_weekly_cases, load_raw
from denguekay.evaluation.protocol import block_cutoff
from denguekay.features.long_history import piura_ubigeos, week_grid
from denguekay.model import horizon_strategies as strategy
from denguekay.model.train import SEASON_START_WEEK
from run_contribution import training_data

OUTPUT = previous.OUTPUT / "revision_protocolo"
HORIZONS = previous.HORIZONS
FIRST_SEASON = previous.original.p1.FIRST_BLOCK_SEASON_LONG
LAST_COMPLETE_SEASON = 2026
BLOCKS = [(f"temporada_{season}", "temporada", season)
          for season in range(FIRST_SEASON, LAST_COMPLETE_SEASON + 1)]
PARTIAL_BLOCK = ("posterior_2026", "temporada", LAST_COMPLETE_SEASON + 1)
KEY = ["ubigeo", "anio", "semana"]
DAYS_6 = pd.Timedelta(days=6)


def audit_sources(cases):
    """Compare the two data sources over the 53 covered weeks in 2025."""
    raw = load_raw(BRONZE_EPI_CSV)
    calendar = week_grid(2025, 2025)
    raw_weeks = raw.loc[raw.ano.eq("2025"), "semana"].astype(int)
    if set(raw_weeks) != set(calendar.semana):
        raise ValueError("La cobertura nacional del CSV en 2025 difiere del calendario MMWR")
    counts = build_weekly_cases(raw)
    sala = pd.read_csv(previous.SALA, dtype={"ubigeo": "string"})
    if not sala.tipo_dx.eq("C").all():
        raise ValueError("La Sala tiene diagnósticos distintos de confirmado")
    grid = calendar.merge(pd.DataFrame({"ubigeo": piura_ubigeos()}), how="cross")
    merged = grid.merge(counts[counts.anio.eq(2025)], on=KEY, how="outer", validate="one_to_one")
    if merged.semana_inicio.isna().any():
        raise ValueError("El CSV tiene una semana de 2025 fuera de la grilla")
    merged["casos_csv"] = merged.pop("casos_Dengue").fillna(0).astype(int)
    overlap = merged.merge(sala.loc[sala.anio.eq(2025), KEY + ["casos_Dengue"]], on=KEY,
                           how="outer", validate="one_to_one").rename(columns={"casos_Dengue": "casos_sala"})
    if overlap[["casos_csv", "casos_sala"]].isna().any().any():
        raise ValueError("Cobertura incompleta en el solape CSV–Sala")
    same = overlap.casos_csv.eq(overlap.casos_sala)
    recent = cases[cases.anio.ge(2025)].merge(sala[KEY + ["casos_Dengue"]], on=KEY, how="left",
                                              suffixes=("", "_sala"), validate="one_to_one")
    if not recent.casos_Dengue.eq(recent.casos_Dengue_sala).all():
        raise ValueError("La serie reciente del modelo difiere de la Sala")
    return overlap, {
        "distritos": int(overlap.ubigeo.nunique()), "semanas": int(overlap.semana.nunique()),
        "pares": len(overlap), "iguales": int(same.sum()), "distintos": int((~same).sum()),
        "pares_con_casos": int((overlap.casos_csv.gt(0) | overlap.casos_sala.gt(0)).sum()),
        "casos_csv": int(overlap.casos_csv.sum()), "casos_sala": int(overlap.casos_sala.sum()),
        "diferencia_absoluta_total": int((overlap.casos_csv - overlap.casos_sala).abs().sum()),
    }


def cut_table(inputs):
    districts = piura_ubigeos()
    first = None
    per_horizon = {h: [] for h in HORIZONS}
    rows = []
    for block, kind, season in [*BLOCKS, PARTIAL_BLOCK]:
        tests, fit_cutoff = strategy._common_cutoffs(inputs["matrices"], kind, season)
        fit = previous.original.p3._training(inputs["origenes"], fit_cutoff)
        last_target = fit.semana_inicio_h4.max()
        if last_target + DAYS_6 > fit_cutoff:
            raise ValueError(f"Etiqueta h4 posterior al corte en {block}")
        for h, test in tests.items():
            dates = pd.DatetimeIndex(test.semana_inicio.unique()).sort_values()
            first = dates.min() if first is None else first
            want = pd.date_range(dates.min(), dates.max(), freq="W-SUN")
            if not dates.equals(want) or test.duplicated(KEY).any():
                raise ValueError(f"Llaves incompletas en {block} h{h}")
            by_week = test.groupby("semana_inicio").ubigeo.agg(lambda s: sorted(s))
            if not by_week.map(lambda s: s == districts).all():
                raise ValueError(f"Distritos incompletos en {block} h{h}")
            if h != HORIZONS[0]:
                pd.testing.assert_frame_equal(tests[HORIZONS[0]][KEY], test[KEY])
            past = pd.concat(per_horizon[h], ignore_index=True) if per_horizon[h] else test.iloc[:0]
            cutoff = block_cutoff(test)
            available = past.loc[(past.semana_inicio + DAYS_6).le(cutoff)]
            year_2025 = test.anio.ge(2025)
            rows.append({
                "bloque": block, "horizonte": h, "inicio_objetivo": dates.min(), "fin_objetivo": dates.max(),
                "semanas": len(dates), "filas": len(test), "positivos": int(test.brote.sum()),
                "casos_confirmados": int(test.casos_Dengue.sum()), "filas_sala": int(year_2025.sum()),
                "primer_origen": cutoff, "ultimo_origen": test.origen_cierre.max(),
                "corte_entrenamiento": fit_cutoff, "ultima_etiqueta_h4_entrenamiento": last_target + DAYS_6,
                "filas_entrenamiento_multisalida": len(fit),
                "filas_elegibles_calibracion": len(available), "positivos_elegibles_calibracion": int(available.brote.sum()),
                "ultima_etiqueta_calibracion": available.semana_inicio.max() + DAYS_6,
            })
            per_horizon[h].append(test[KEY + ["semana_inicio", "brote"]])
    panel = pd.concat(per_horizon[HORIZONS[0]], ignore_index=True)
    if panel.duplicated(KEY).any():
        raise ValueError("El calendario común repite semanas distritales")
    dates = pd.DatetimeIndex(panel.semana_inicio.unique()).sort_values()
    if not dates.equals(pd.date_range(first, inputs["ultima_semana"], freq="W-SUN")):
        raise ValueError("El calendario común tiene un hueco o no alcanza el último objetivo confirmado")
    return pd.DataFrame(rows), panel


def compare_archive(common):
    file = previous.OUTPUT / "l5a_s17" / "predicciones.csv.gz"
    original = pd.read_csv(file, usecols=KEY + ["semana_inicio", "horizonte"], dtype={"ubigeo": "string"},
                           parse_dates=["semana_inicio"])
    original = original[original.horizonte.eq(2)]
    if not original[KEY].merge(common[KEY], on=KEY, how="left", indicator=True).loc[
        lambda d: d._merge.ne("both")].empty:
        raise ValueError("El calendario común pierde semanas archivadas")
    delta = common.merge(original[KEY].drop_duplicates(), on=KEY, how="left", indicator=True)
    recovered = delta[delta._merge.eq("left_only")]
    duplicate = original.loc[original.duplicated(KEY)]
    return {
        "recuperadas": {"semanas": int(recovered.semana_inicio.nunique()), "filas_por_horizonte": len(recovered),
                        "inicio": recovered.semana_inicio.min().date().isoformat(),
                        "fin": recovered.semana_inicio.max().date().isoformat()},
        "duplicadas_antes": {"semanas": int(duplicate.semana_inicio.nunique()), "filas_por_horizonte": len(duplicate),
                            "inicio": duplicate.semana_inicio.min().date().isoformat(),
                            "fin": duplicate.semana_inicio.max().date().isoformat()},
    }


def main():
    previous_snapshot, handoff, quality, inputs = training_data()
    overlap, source = audit_sources(inputs["casos"])
    cuts, common = cut_table(inputs)
    fingerprints = previous_snapshot["configuracion"]["insumos"].copy()
    for path in (BRONZE_EPI_CSV, DISTRICT_BOUNDARIES, SILVER_CHIRPS_PRECIP, SILVER_ENSO):
        fingerprints[path.relative_to(previous.ROOT).as_posix()] = previous.sha256(path)
    summary = {
        "semana_inicio_temporada": SEASON_START_WEEK, "temporadas_completas": len(BLOCKS),
        "distritos": int(common.ubigeo.nunique()), "filas_por_horizonte": len(common),
        "semanas": int(common.semana_inicio.nunique()), "positivos_por_horizonte": int(common.brote.sum()),
        "diferencias_con_calendario_archivado": compare_archive(common), "solape_2025": source,
        "semanas_sala_provisionales_excluidas": inputs["semanas_provisionales"],
        "calidad": quality, "gold_filas": handoff["horizontes"]["2"]["filas"], "sha256": fingerprints,
    }
    OUTPUT.mkdir(parents=True, exist_ok=True)
    cuts.to_csv(OUTPUT / "cortes.csv", index=False)
    overlap.to_csv(OUTPUT / "solape_csv_sala_2025.csv", index=False)
    previous.write_json(OUTPUT / "manifiesto.json", summary)
    print({key: value for key, value in summary.items() if key not in {"sha256", "calidad"}})


if __name__ == "__main__":
    main()
