# Protocol addendum: E9–E13, checks requested by external feedback (14 November 2026)

Written after E1–E8 had been run and their results were known, in response to external feedback on the manuscript (`denguekay_epidemics_latex/review_feedback.md`). This addendum is a separate file, so the protocol and the fingerprints of the completed experiments stay unchanged. Every analysis below is **exploratory**. None changes the primary estimand, the margin D1 or the conclusions drawn from E1. Results are read descriptively, with intervals.

**What was already known when this was written.**
- The full E1–E8 results.
- An informal check run earlier the same day, with the same code conventions, which gave the first numbers of E9 and E10 at two to four weeks:
  - the direct contrasts between alignments;
  - the split into the six development seasons and the other twelve;
  - intervals for the count change at 2–4 weeks.

  E9 and E10 formalise that check without changing its definitions. E11–E13 had not been run when this was written.

Conventions are those of `protocolo.md` unless stated otherwise:
- 18 seasons (2009–2026);
- pooled primary estimand (ratio of summed losses per seed, median over seeds) and the equal-season mean alongside;
- whole-season bootstrap with seeds and arms paired, 20,000 draws, random seed 20261113;
- 95% percentile intervals;
- negative changes favour the first arm.

## E9. Weather alignments compared directly, and the seasons used in development

| | |
|---|---|
| Direct contrasts | `b3_hist_geo` (lag 0) vs `b3_obs` (lag 2), lag 0 vs `b3_lag1`, and lag 1 vs lag 2, at 2–4 weeks over 18 seasons |
| Season split | **Development seasons:** the six seasons of the earlier analysis on which the b3 block was chosen (2010, 2015, 2016, 2022, 2023, 2026; `run_spatial_controls.DECIDING`). **Other seasons:** the remaining twelve. |
| Contrasts in each subset | each alignment vs `historia_geo`, and lag 0 vs lag 2 |

## E10. Uncertainty and location of the count gains

| | |
|---|---|
| Loss | absolute error of the published count (`conteo_publicado`) against the final count of the target week |
| Estimand | pooled relative change in mean absolute error (ratio of summed absolute errors per seed, median over seeds), with the E1 bootstrap |
| Pairs | `b3_obs` vs `historia_geo` at 2–4 weeks; `b3_obs_largo` vs `historia_geo_largo` at 8 and 12 weeks; each model vs the persistence count |
| Location | the same contrast within the E11 origin-state strata, and in the development and other seasons of E9 |

## E11. Onset versus continuation

| | |
|---|---|
| Origin state | A district is **quiet** at origin *o* if none of the weeks *o*−3, …, *o* was elevated (outbreak rule, final counts). Otherwise it is **active**. Both are known at issue time in this retrospective design. |
| Brier by stratum | Within each stratum: climate vs no climate, and each model vs calibrated persistence, at 2–4 weeks. The stratum is fixed at the origin, so scoring within it remains proper. Average precision is reported by stratum. |
| Onset weeks | An elevated week *t* with none of the weeks *t*−4, …, *t*−1 elevated. |
| Alerts | The forecast for week *t* issued at origin *t*−*h* (*h* = 2, 3, 4) raises an alert if its calibrated probability is at least the alert threshold. Thresholds: 0.1 and 0.2. |
| Event measures, per model and threshold | **Detection:** the share of onset weeks with an alert at any of the three horizons, and with an alert four weeks ahead. **Warning time:** for each onset, the longest horizon with an alert. **False alarms:** alerts for non-elevated target weeks, per district per 52 weeks, at each horizon. Counts are taken per seed, then the median over seeds. |
| Uncertainty | For the difference in detection between climate and no climate, and between climate and persistence: the season bootstrap above. |
| District example | The district with the most confirmed cases in the 2023 season (the largest epidemic). Over the target weeks of that season, the figure shows cases, threshold and elevated weeks, and the four-week forecasts of the three models (median over seeds) with the alert thresholds. The rule was fixed before looking at any district. |

## E12. Reporting delays (simulation)

The surveillance file holds only the year and epidemiological week of each case, with no notification date, so reporting delays cannot be estimated. They are simulated under stated assumptions.

| | |
|---|---|
| Delay model | One multinomial draw per district-week (random seed 20261114) splits the final count into cases reported 0, 1, 2 and 3 weeks after the week closes. At origin *o*, week *o*−*j* shows the cases with delay ≤ *j*. These counts are nested: a later origin never sees fewer cases of the same week. Weeks *o*−3 and earlier are complete. |
| Scenarios | Cumulative completeness after 0, 1 and 2 weeks: **moderate** 60%, 85% and 95%; **severe** 30%, 60% and 85%. Both are complete after three weeks. These are assumptions, not estimates. |
| What changes | At every origin, including training origins: cases in the origin week and the week before, four-week mean, weeks with cases in the last four, weeks since the last case, four-week slope, the persistence offset `log(y_o + 0.5)`, the persistence term of the count blend and the calibrated persistence forecast. The previous-season total is not changed: it is complete except at the first two origins of a season. |
| What does not change | Outcomes, thresholds, weather and evaluation, all of which use final counts. |
| Arms | `historia_geo` and `b3_obs` (lag 2): five seeds, the same blocks, hyperparameters, calibration and count blend as E1. |
| Contrasts per scenario | Climate vs no climate; each model vs calibrated persistence (same scenario); no climate under delays vs no climate with final counts. |
| Question | Does the climate contrast change when case history is less complete at issue time? No direction is pre-specified. |
| Check | With completeness 100% at every delay, the recomputed predictors equal the archived ones. |

## E13. Direct classifier for elevated weeks

| | |
|---|---|
| Formulation | The project's formulation `S3`. The published count comes from the same Poisson model with the persistence offset. The probability of an elevated week comes from a multi-output XGBoost classifier (logistic loss; outputs at 2, 3 and 4 weeks), not from the NB2 exceedance. |
| Predictors of the classifier | The arm's predictors plus `log(k)` for each of the three target weeks, where *k* is the threshold count (known at issue time). The NB2 route uses *k* through the exceedance probability. |
| Settings | Fixed hyperparameters `CONFIG_2026_V1`, five seeds, the 20 blocks, chronological Platt calibration. No dispersion is fitted, so the WIS is not computed. |
| Arms | `historia_geo_clasificador` and `b3_obs_clasificador` |
| Contrasts | Climate vs no climate; classifier vs NB2 for each arm |
