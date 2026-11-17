# Protocol addendum: E8, longer horizons (13 November 2026)

Written after E1–E7 had been run and their results were known, when the team decided to run E8 (revising decision D6 of `protocolo.md`, which had deferred it). This addendum is a separate file so the protocol and fingerprints of the completed experiments stay unchanged.

**Question.** Does the b3 climate block add skill to case history and geography at horizons longer than the weather-to-cases delay, where recent counts no longer reflect the weather of the target period?

## Design

| | |
|---|---|
| Horizons | 8 and 12 weeks after the origin week (about 2 and 3 months) |
| Model | a **separate** multi-output XGBoost with two outputs (h8, h12), so the (2, 3, 4) models of the paper and of E1–E7 stay untouched |
| Everything else | same as the primary pair: formulation S4_s3, persistence offset `log(y_origin + 0.5)`, fixed hyperparameters `CONFIG_2026_V1`, seeds 17/29/41/53/67 |
| Arms | `historia_geo_largo` (case history + calendar + geography) and `b3_obs_largo` (+ the b3 block at lag 2, published by the origin close). Predictors are taken at the origin, exactly as in `b3_obs` / `historia_geo`. |
| Targets | the outcome of the target week origin + h (same 5-year threshold rule), joined from the long label series |
| Blocks | seasons 2008–2026, assigned by the target week. Cut-off = the earliest first-test origin across the two horizons; training uses origins whose h12 target closed by the cut-off. |
| Outputs | NB2 exceedance with in-sample dispersion, chronological Platt and the count blend, both fitted on earlier blocks with labels closed by each block's cut-off |
| References | probabilistic persistence (chronological Platt on `log((y + 0.5)/(k + 0.5))`) and district climatology at h8 and h12 |

**Estimands:** as in E1 (18 seasons, pooled primary, equal-season mean, whole-season bootstrap with 20,000 draws, margin D1 = 1%). The results are read descriptively, because this addendum was written after E1–E7.

**Leakage checks:** for every block and horizon, the last training label and the last calibration label close by the cut-off, and the cut-off is at or before the first test origin.
