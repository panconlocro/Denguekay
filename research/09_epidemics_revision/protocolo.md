# Protocol: re-analysis for the *Epidemics* revision (study 09)

Written on 13 November 2026, before any of the analyses below was run in this environment. The runners record this file's SHA-256 in their outputs, so the protocol in force for each result is traceable.

**What was already known when it was written:** the six-season results of the paper (Table II, Table S16, supplement). The authors' local archives also hold contrasts for every season (`contrastes_por_temporada.csv`); they were **not** available or consulted here. The decisions below are the defaults proposed in `Denguekay_experiment_plan.md`; the team may revise them, and any revision must be dated.

## Decisions

| | Decision | Value used |
|---|---|---|
| D1 | Margin: smallest relative change in four-week Brier worth acting on | **1%** (about the size of the historical claimed gain, −1.14%) |
| D2 | Primary aggregation | **pooled** over district-weeks; the equal-season mean is always reported alongside |
| D3 | Lag-1 arm | ERA5-Land (temperature, humidity) window ending 1 week before the origin week; CHIRPS window ending 2 weeks before; Niño 1+2 by availability date. Every value must be published by the origin close. |
| D4 | Epidemic years in the threshold sensitivity | for target year Y, a year y < Y is epidemic if Piura's annual case total in y is at or above the 75th percentile of annual totals over 2000…Y−1 (**past years only**). The reference is the 5 most recent non-epidemic years before Y, with at least 3 required (otherwise the standard rule). |
| D5 | Confirmed + probable | national-file codes C+P for 2000–2024; 2025–2026 stay as in the confirmed series (the national file has P ≈ 0 since 2021). Evaluated on the 2009–2025 seasons. |
| D6 | 8- and 12-week horizons | **not run** in this round (decide after E1–E2) |
| D7 | Regeneration route | new runner in `research/09_epidemics_revision/code/`; no edits to existing scripts |

## Data and code

- Inputs: `data/` merged from `data/data 5/`. The nine sources listed in `research/08_v3_confirmed_cases/manifiesto_b3_v4.json` must match their SHA-256 (the runner checks this).
- District geography: `lat, lon` from the confirmed panel, elevation from the Open-Meteo elevation API (Copernicus GLO-90); hash compared with the manifest's `geografia`.
- Model: the paper's fixed-hyperparameter configuration (`frozen_configs.CONFIG_2026_V1`), formulation `S4_s3`, seeds 17/29/41/53/67, the 20 blocks of `run_spatial_controls.BLOCK_LIST`.

## Reproduction check (before any new analysis)

Regenerate `historia_geo` and `b3_obs` and export the six-season bundle in the format of `predictions.csv.gz`. The check passes if `reproduce.py` reproduces every row of Table II and Table S16 at printed precision. Report the maximum |Δp| against the paper bundle. If it fails, stop.

## Leakage audit (before the experiments)

1. **Case features:** perturb every count after the origin week. Features at the origin and the thresholds of the targets t+2..t+4 must not change.
2. **Weather and ENSO:** perturb values published after the origin close. The lag-2 and lag-1 features must not change; the lag-0 (historical) features must change (positive control).
3. **Blocks:** no training or calibration label closes after the block cut-off, and no test row appears in its block's training set.

## Estimands (E1)

- **Seasons:** primary = the 18 complete seasons 2009–2026. The six decision seasons and leave-one-season-out are sensitivities.
- **Primary:** relative change in Brier, `b3_obs` vs `historia_geo`, pooled over all district-weeks, at 2, 3 and 4 weeks. Computed per seed; the reported value is the median over seeds.
- **Always reported:** the equal-season mean (relative change per season, median over seeds, mean over seasons); Brier skill vs probabilistic persistence and vs climatology; the CORP split (miscalibration / discrimination).
- **Uncertainty:** whole-season bootstrap, seeds kept paired, 20,000 draws, random seed 20261113, 95% percentile intervals.
- **Wording:** "no measurable gain from climate" if the interval excludes improvements larger than D1. Every other analysis is descriptive.

## Experiments

| | Experiment | Content |
|---|---|---|
| E2 | Weather timing | `b3_lag0_hist` (= `b3_hist_geo`), `b3_lag1` (D3), `b3_obs` (lag 2), each vs `historia_geo`; wrong-year placebos at lag 2 (`b3_placebo_t1–t3`, `b3_placebo_conjunto`) |
| E3 | Diagnostics on the fixed-hyperparameter models | CORP, calibration slope and intercept, AP, MAE/RMSE/WIS of the blended count, net benefit by relative cost |
| E4 | Calibration artefact | (i) current; (ii) out-of-sample NB2 dispersion + Platt; (iii) chronological isotonic recalibration. The b3 − historia_geo contrast under each. |
| E5 | What carries the skill | the four-arm design of `evaluate_climate_without_history.py` (S4_s2 formulation, no offset), plus probabilistic persistence and climatology, over 18 seasons |
| E6 | Data and outcome | (a) confirmed share by season; (b) confirmed+probable (D5); (c) threshold excluding epidemic years (D4); (d) incidence rule if population data are available |
| E7 | Statistical analogue | NB2 regression with the same case-history and geography terms, with and without exactly the b3 climate block (linear terms) |

## Amendments after the first run (13 November 2026)

Written after the development run of E1–E7. Nothing above was changed; the final run (`code/run_all.py`) uses this file as it stands.

1. **E6d population:** the INEI 2018–2026 file used by the paper is not in `data 5`. The incidence rule uses the panel's population (2017–2025), so it covers seasons 2019–2025 only, and 2026 is not evaluated.
2. **Equal-season means are unstable:** seasons 2019 and 2020 have about one elevated week each (0.03% prevalence), so relative Brier changes there are very large and dominate equal-season averages. The pooled estimand stays primary, as pre-specified; equal-season values are still reported.
3. **Margin D1 (1%)** is reported as fixed, even where the intervals are too wide to meet it.
4. **E8** (8- and 12-week horizons) was not run (D6).
