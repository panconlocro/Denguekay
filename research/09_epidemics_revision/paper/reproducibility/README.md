# Reproduce the primary Denguekay results

This bundle reconstructs Table II and Supplementary Table S16 of *What Does Climate Add to Case History? A Multiseason Evaluation of District-Level Dengue Forecasts in Piura, Peru*. It also recomputes the four-week climate contrast when the 2026 season is omitted.

## Run

Use Python 3.9 or later. From this directory:

    python3 reproduce.py --out reproduced

The script writes the two LaTeX table bodies and a JSON file with full-precision statistics, including the sensitivity without 2026. If this directory accompanies the manuscript sources, you can also verify the printed rows:

    python3 reproduce.py --main-tex ../main.tex --supplement-tex ../supplement.tex

## Inputs and estimands

The compressed CSV has 61,230 district-week-horizon rows from 65 districts of Piura in the six decision seasons ending in 2010, 2015, 2016, 2022, 2023 and 2026. Each row contains the target week start, the date the forecast origin week closed, the binary elevated-week outcome, the calibrated persistence probability, and the calibrated probabilities for the two fixed-hyperparameter XGBoost arms at five seeds. District codes are geographic identifiers. The input contains district-week aggregates and model outputs. The manifest records the distributed file checksum and the checksums of its source prediction archives.

Brier is the mean squared difference between probability and binary outcome. The climate contrast is 100 times the ratio of b3 Brier to history-and-geography Brier minus 100. Skill is 100 times one minus the ratio of b3 Brier to probabilistic-persistence Brier. Contrasts are paired by season, seed and horizon. Table II uses the seed median within each season and averages six seasons equally. Its percentile intervals enumerate all 46,656 six-season draws with replacement and use linear interpolation for the 2.5th and 97.5th percentiles. Table S16 reports the paired seasonal medians.

The files reproduce the reported statistics from archived out-of-sample probabilities. Retraining the models uses the separate study protocols and upstream inputs described in the [Denguekay repository](https://github.com/panconlocro/Denguekay/tree/36e2cc62826aada83e727a2d650ef04422e9ebf3/research/08_v3_confirmed_cases).
