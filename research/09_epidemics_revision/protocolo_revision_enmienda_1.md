# Amendment 1 to `protocolo_revision.md`: onset event measures (14 November 2026)

**Why.** A second external review (`denguekay_epidemics_latex/submission_readiness_review.md`) pointed out two problems in the event summary of E11:
- it paired detection at any of the 2–4-week horizons with false alarms counted at four weeks only;
- it compared forecasts whose false-alarm rates differed by 38–50% as if those rates were similar.

**What was known.** An informal check run before this amendment was written gave the first matched-budget numbers.

**What is unchanged.** The Brier analyses of E11 (origin states, average precision) and the district example. This file is separate from the addendum, so the fingerprints of E12 and E13, which record the addendum's SHA-256, stay valid.

## Corrected event measures (E11)

| | |
|---|---|
| Alert policies | Detection and false alarms are always counted under the same policy. **Four weeks ahead:** an alert for target week *t* if the forecast issued at *t*−4 reaches the threshold. **Any of 2–4 weeks ahead:** an alert if any of the forecasts issued at *t*−4, *t*−3 or *t*−2 reaches it. |
| Fixed thresholds | 0.1 and 0.2. Under each policy: detection, and false alarms per district per 52 weeks. Under the any-horizon policy, also the warning time (longest horizon with an alert). |
| Matched false-alarm budgets | 1, 2 and 3 false alarms per district per 52 weeks over the 18 seasons. The threshold for each forecast, policy and seed is the one that meets the budget, interpolating linearly between adjacent achievable thresholds; this equals alerting on a random share of tied forecasts. Detection is measured at that budget. |
| Comparisons | Differences in detection at matched budgets: climate vs no climate, and each model vs calibrated persistence. Whole-season bootstrap (20,000 draws, random seed 20261113) with seeds and forecasts paired, re-matching the budget in every bootstrap sample. Medians over seeds. |
| No longer reported | Differences in detection at fixed thresholds between forecasts whose false-alarm rates differ. |
