# Study 09 · Results (13 November 2026; E9–E13 added 14 November 2026, E11 event measures corrected the same day)

Full tables: [RESULTS_TABLES.md](RESULTS_TABLES.md), generated from the CSV outputs by `code/write_results.py`. Notebooks: `notebooks/00`–`15`.

**Conventions:** 18 complete seasons (2009–2026); pooled over district-weeks; median over the five seeds; 95% whole-season bootstrap intervals (20,000 draws). A negative Brier change favours the model with climate. "b3" is the paper's climate-augmented model; "history+geography" is the same model without climate.

## Checks done before any result

| Check | Outcome |
|---|---|
| Inputs | All 10 match the paper's V4 manifest by SHA-256, including the rebuilt district geography |
| Leakage audit (notebook 00) | Every count after the origin was replaced with random values at 8 origins (2008–2026): case predictors, outbreak thresholds and persistence did not change. The same test on weather: the lag-1 and lag-2 inputs and Niño 1+2 did not change. Positive control: the historical lag-0 alignment changed in all 65 districts at every origin (look-ahead) |
| Training and calibration windows (notebook 01) | Every block, both arms: no label closes after the cut-off; Platt parameters and blend weights refit to within 2e-14 |
| Reproduction (notebook 01) | Regenerated probabilities match the paper's bundle to 2e-15; Table II, Table S16 and the +1.49% sensitivity are reproduced exactly by the paper's `reproduce.py` |
| Determinism | A second from-scratch run reproduced all 19 result files exactly (maximum difference 0) |

## Main findings

1. **Over 18 seasons, climate gives no consistent improvement on average (E1).**

   | | 2 weeks | 3 weeks | 4 weeks |
   |---|---|---|---|
   | Pooled Brier change (95% interval) | −0.43% (−1.46 to +0.37) | −0.28% (−1.89 to +0.87) | +0.04% (−2.31 to +1.70) |
   | Seasons where climate helped | 10 of 18 | 10 of 18 | 10 of 18 |

   - The paper's six-season penalty does not generalise: pooled at four weeks it is +1.57% on the six seasons, +0.04% on all 18.
   - The 1% margin fixed in the protocol is **not** met: four-week gains of up to about 2% cannot be excluded, so the protocol's wording "no measurable gain" does not apply. What the intervals do exclude are gains larger than 1.5%, 1.9% and 2.3% at two, three and four weeks.
   - Equal-season averages lean towards climate (about −1.2%). They are dominated by seasons with almost no elevated weeks (2019 and 2020 have about one each), which is why the pooled estimand is primary.

2. **The earlier "climate gain" came mostly from look-ahead (E2).** Four-week Brier change against history+geography:

   | Weather lag | 4-week change (95% interval) | Significant? |
   |---|---|---|
   | Lag 0 (historical alignment, uses weather published up to 14 days after the forecast date) | −1.73% (−3.67 to −0.22) | yes; also at 2 and 3 weeks (−1.01%, −1.49%) |
   | Lag 1 (available at the forecast date) | −0.38% | no |
   | Lag 2 (the paper's model) | +0.04% | no |

   About 80% of the apparent gain disappears once weather published after the forecast date is excluded. On the six seasons, the lag-0 equal-season figure reproduces the paper's −1.14%.

   Compared directly (E9), lag 0 beats lag 2 by 0.61%, 1.22% and 1.83% at two to four weeks, with every interval excluding zero (four weeks: 0.79% to 2.65%). In the twelve seasons not used in development, the four-week difference is 1.23% (interval −0.26% to 2.21%): same direction, not significant.

3. **Observed weather does no better than wrong-year weather (E2 placebos).**
   - Against wrong-year temperature (median of three donor calendars): +0.04%, +0.15%, +0.13%.
   - Against moving all four climate variables to a wrong year: −0.50%, −0.51%, −0.46% (not significant).

4. **Case history carries the skill (E5).**
   - Adding case history to calendar and geography cuts Brier by 58%, 51% and 45% (2, 3 and 4 weeks), in all 18 seasons.
   - Adding climate on top of case history: −0.49%, −0.78%, −1.03% (not significant).
   - Without case history, climate + calendar + geography has only about 4% skill over district climatology (geography alone: 2.5%).

5. **Calibrated persistence (two parameters per horizon) is hard to beat (E1, E5).**
   - Pooled, the climate model is 1.4%, 3.2% and 4.8% better than probabilistic persistence, with intervals that include zero.
   - With equal season weights it is 9.2%, 7.7% and 8.6% **worse**, beating persistence in only 8, 8 and 9 of 18 seasons.
   - The no-climate model behaves the same way.

6. **Climate lowers the count error on average, but not consistently (E3, E10).** At four weeks:

   | | Climate model | No-climate model |
   |---|---|---|
   | MAE of the published count | 2.56 | 2.78 |
   | MAE ratio to persistence | 0.85 | 0.92 |
   | WIS | 1.89 | 1.97 |

   - With intervals (E10), the pooled MAE change is −4.0%, −6.6% and −8.2% at two to four weeks; every interval includes zero, and climate had the lower MAE in only 9–11 of 18 seasons.
   - The gain comes from one season: without 2024 it is −0.7%, −1.1% and −0.2% (four weeks: −5.1% to +3.9%). In 2024 climate lowered the four-week MAE by 35.5%.

7. **Calibration (E3, E4).**
   - Over 18 seasons the climate model is **not** more miscalibrated than the no-climate one; it is worse in only 8 of 18 seasons. The six-season pattern does not hold.
   - Chronological isotonic recalibration lowers both models' four-week Brier by about 3% (b3: 0.0356 to 0.0344).
   - Under isotonic recalibration the climate contrast is −0.67%; with out-of-sample NB2 dispersion it is −1.10%. Neither is significant.

8. **The conclusions hold under other case and outcome definitions (E6).**

   | Variant | Climate effect at 2 / 3 / 4 weeks | Notes |
   |---|---|---|
   | Confirmed + probable cases (2009–2025) | −0.72% / −0.83% / −0.83% | not significant |
   | Threshold without epidemic years | −0.63% / −0.59% / −0.38% | not significant; prevalence 10.8% vs 7.6% |
   | Incidence ≥ 10/100,000 (2019–2025) | +0.84% / +1.58% / +2.30% | not significant; climate helped in 1 of 7 seasons |

9. **Confirmed share of notifications (E6a).** Only 2.8% of notifications were confirmed in season 2001 (371 vs 12,675 probable). The share was 3–34% in 2000–2005, 100% in 2008–2014 and 80–96% in 2015–2018. The confirmed-only series therefore under-represents early epidemics, which feeds into the early thresholds.

10. **A statistical model gives the same answer (E7).** In NB2 regression, adding exactly the same climate block changes Brier by +3.0%, +3.5% and +3.6% (not significant). NB2 is 1.5–6.4% worse than XGBoost with the same predictors.

11. **Longer horizons don't change the answer for elevated weeks (E8; separate two-output model, `protocolo_e8.md`).**

    | | 8 weeks | 12 weeks |
    |---|---|---|
    | Brier change from climate (95% interval) | −0.05% (−4.71 to +3.22) | −0.54% (−5.06 to +2.71) |
    | Seasons where climate helped | 8 of 18 | 10 of 18 |
    | Skill over climatology, history+geography / b3 | 33% / 33% | 24% / 24% |
    | Skill over climatology, probabilistic persistence | 29% | 17% |
    | Count MAE ratio to persistence, b3 / history+geography | 0.79 / 0.83 | 0.74 / 0.83 |

    - Case-history models keep their skill over climatology at both horizons.
    - Pooled, they also beat probabilistic persistence (by about 7–8%, not significant). With equal season weights, persistence is far better: it wins in the low-activity seasons.
    - Count MAE is 4.8% lower with climate at 8 weeks and 10.3% lower at 12 weeks, but both intervals include zero (E10). Without 2024 the changes are +0.7% and +0.6%.
    - The intervals are wider than at 2–4 weeks, so gains of up to about 5% can't be excluded at these horizons.

## Checks requested by external feedback (E9–E13, `protocolo_revision.md`; exploratory)

12. **The seasons used in development pull the climate estimate down, not up (E9).** Four-week Brier change from climate (lag 2):

    | Seasons | Change (95% interval) | Seasons where climate helped |
    |---|---|---|
    | All 18 | +0.04% (−2.31 to +1.70) | 10 of 18 |
    | The 6 on which the b3 block was chosen (2010, 2015, 2016, 2022, 2023, 2026) | +1.57% (+0.30 to +2.45) | 2 of 6 |
    | The other 12 | −1.50% (−6.27 to +1.62) | 8 of 12 |

    The manuscript's claim that selecting the block on six of the evaluation seasons "would favour climate" is contradicted: climate does worst in exactly those seasons. In the other twelve seasons, which were not used to choose the climate block (though earlier development stages may have used them), the estimate exceeds the 1% margin in climate's favour, with a wide interval.

13. **Onset vs continuation (E11).**
    - Origins in quiet districts (no elevated week in the four weeks up to the origin) are 88.6% of district-weeks but only 23% of the elevated weeks at four weeks.
    - Climate effect: quiet −1.1% to −1.5% (not significant; climate better in 11–13 of 18 seasons); active +0.1% to +1.1% (not significant).
    - 527 onset weeks. Event measures follow amendment 1 (`protocolo_revision_enmienda_1.md`), which corrected a summary that paired detection at any horizon with false alarms at four weeks only. Detection and false alarms are now counted under the same alert policy.
    - At threshold 0.1 with alerts from any of the three horizons, alerts preceded 76.5% (climate), 77.0% (no climate) and 53.5% (persistence) of onsets, at 7.1, 7.3 and 4.2 false alarms per district-year.
    - At matched budgets of 1–3 false alarms per district-year, the models detected 2–8 percentage points more onsets than persistence. The intervals exclude zero only at 3 false alarms with alerts four weeks ahead (+5.3, 1.4 to 12.5) and at 2 with alerts from any horizon (+7.1, 1.5 to 11.1). No forecast detected more than 42% of onsets at these budgets.
    - Climate did not improve onset detection: −1.3 to +0.8 points at matched budgets, every interval including zero.
    - Calibrated persistence is strongest during continuation: in Piura district during the established 2023 epidemic it gave 0.88–1.00, against 0.74–0.90 for the models.

14. **Simulated reporting delays (E12).** At issue time the origin week shows 60% (moderate) or 30% (severe) of its final count.
    - The climate effect at four weeks moves from +0.04% (final counts) to −0.41% (moderate) and −0.90% (severe); none is significant.
    - Delays cost the model without climate 1.8–3.1% (moderate) and 5.5–9.5% (severe), and calibrated persistence 5.9–8.3% and 17–29%. Under severe delays both models beat persistence by 14–16% at every horizon (significant).
    - So persistence's strength depends on complete counts. The finalised data favour persistence more than they disfavour climate.

15. **A direct classifier gives the same answer (E13).** With a multi-output classifier instead of the NB2 exceedance, the climate effect is +0.30%, −0.12% and −0.34% (not significant), and the classifier matches NB2 within ±1.5%. The probability null is not an artefact of the NB2 conversion.

16. **Where the count gains are (E10).** The four-week count gain is concentrated in districts already active at the origin (−9.9%, not significant) and in the 2024 season.

## What this means for the manuscript

- Make the 18-season pooled comparison primary. Do not write "no measurable skill": the margin is not met. Write "no consistent improvement; gains larger than about 2% at two to four weeks are excluded, and up to about 5% remain possible at eight and twelve weeks".
- Lead with the look-ahead result, now with the direct alignment contrasts (E2, E9), case history carrying the skill (E5) and the calibrated persistence benchmark, with its dependence on complete counts (E12).
- Report the development-season split (E9) and remove any claim about the direction of selection bias.
- Report the count change with its intervals and the 2024 dependence (E10); don't present it as a consistent benefit.
- Add the onset analysis (E11) and the district example; frame the study as a retrospective evaluation with finalised counts and assumed publication delays (E12).
- Use E8 for the obvious reviewer question about longer horizons, and E13 for the NB2-conversion question.
- Move E4, E6, E7 and the details of E12 and E13 into the supplement.

## Not done

- **E9–E13** were specified after E1–E8, in response to external feedback (`protocolo_revision.md`); they are exploratory. The first numbers of E9 and E10 came from an informal check run before the addendum was written.
- E12 assumes the delay distribution: the surveillance file has no notification dates.
- **E8** was decided after E1–E7 (addendum `protocolo_e8.md`), so its reading is descriptive.
- **E6d** uses the panel's population (2017–2025) because the INEI 2018–2026 file is not in `data 5`, so 2026 is not evaluated.
