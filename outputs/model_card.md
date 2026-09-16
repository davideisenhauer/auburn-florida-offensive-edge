# Model card: league baseline for PPA and explosive plays

**Version:** frozen snapshot of September 16, 2026; models fit September 17, 2026
**Data cutoff:** September 12, 2026
**Code:** `src/features.py`, `src/models.py` · **Rules:** `docs/analysis_spec.md` sections 7 and 7.5 · **Evidence:** `notebooks/02_baseline_models.ipynb`, `outputs/tables/model_*.csv`, `outputs/tables/calibration_2025.csv`

## What the models do

Two league-wide baselines estimate what an FBS offensive snap normally produces, **given only what was known before the snap**:

| Model | Target | Output |
|---|---|---|
| Value baseline | `ppa`, CollegeFootballData's predicted points added on the play | Expected PPA |
| Explosive baseline | `explosive`: 1 if the play gained 20+ yards | Probability of an explosive play |
| Alternate explosive (robustness only) | Pass gain of 20+ or run gain of 10+ | Probability |

Their only job in this project is to supply the "expected" in "over expected." Auburn's 2026 offensive snaps and Florida's 2026 defensive snaps are compared with these baselines, and the differences (residuals) are shrunk and checked before anything is published.

## Intended use and out-of-scope use

**Intended:** removing down, distance, field position, score, clock, venue, and point-spread effects before describing a team's play-by-play results. Because the spread reflects the market's view of both teams, a residual measures performance against that game's expectations, not against an average team.

**Out of scope:**
- predicting individual plays, drives, scores, or winners
- recommending play calls; the models see run or pass as an input chosen by coaches, not as a treatment
- rating players, coordinators, or teams on their own; residuals from two games are mostly noise (see "Reliability")
- CFBD's live PPA or cfbfastR EPA; the models were trained on the frozen `ppa` column and are not on the same scale as other expected-points models

## Model details

| | Value baseline | Explosive baseline |
|---|---|---|
| Family (chosen) | Ridge regression | L2-regularized logistic regression |
| Penalty (leave-one-season-out tuning, 2021–2024) | alpha = 10 | C = 1 |
| Flexible candidate (not chosen) | XGBoost, depth 6, min child weight 500, 144 trees | XGBoost, depth 4, min child weight 30, 134 trees |
| Selection rule (set before fitting) | XGBoost must cut 2025 MAE by 1% or more | XGBoost must cut 2025 Brier score by 1% or more |
| XGBoost's actual gain on 2025 | 0.44% | 0.28% |

**Features** (`config.PRE_SNAP_FEATURES`; guarded by `tests/test_no_leakage.py`):
- run or pass
- down with a separate log-distance slope per down
- a cubic spline in yards to goal, with a separate curve for passes
- quarter
- cubic splines in seconds left in the half, score margin (clipped to ±42), and offense point spread (clipped to ±50; missing set to 0 with a flag)
- venue (home, away, neutral) and goal to go

All terms are standardized. The XGBoost candidates use the same pre-snap fields without splines.

## Training and evaluation data

| Split | Seasons | Snaps |
|---|---|---:|
| Tuning (leave one season out) | 2021–2024 | 469,584 |
| One-time test | 2025 | 119,951 |
| Final refit (same hyperparameters) | 2021–2025 | 589,535 |
| Sensitivity refit (robustness check 1) | 2023–2025 | 354,616 |
| 2026 environment check (other games only) | 2026 Weeks 1–2 | 22,640 |

Snaps are FBS-involved regular-season and postseason run and pass plays, sacks included, after the cleaning rules in spec section 5. Garbage time stays in training. Source: SportsDataverse `cfbfastR_cfb_pbp`, frozen and hashed.

## Performance on the 2025 test

| Metric | Naive (2021–2024 mean) | Chosen model | XGBoost |
|---|---:|---:|---:|
| PPA mean absolute error | 0.944 | **0.929** | 0.925 |
| PPA root mean squared error | 1.303 | **1.271** | 1.256 |
| PPA R² | 0.000 | **0.049** | 0.072 |
| PPA average situational bias* | 0.202 | **0.078** | 0.028 |
| Explosive Brier score | 0.0634 | **0.0616** | 0.0614 |
| Explosive log loss | 0.248 | **0.232** | 0.231 |
| Explosive ROC-AUC | | **0.692** | 0.700 |
| Explosive average precision (base rate 6.8%) | | **0.123** | 0.128 |
| Explosive observed / expected | | **0.977** | 0.966 |
| Explosive calibration slope | | **0.970** | 0.981 |
| Explosive average situational bias* | 0.0364 | **0.0055** | 0.0047 |

\* Play-weighted mean absolute error of the average prediction across down × distance × field position × play family groups.

**Frozen gates:** both models beat naive (lower RMSE and MAE, or Brier and log loss; ROC-AUC ≥ 0.55; situational bias cut by at least 50%). The explosive model is calibrated (observed/expected within 0.95–1.05, slope within 0.85–1.15). Calibration by decile is in `outputs/tables/calibration_2025.csv`; the largest gap is the top decile, predicted 15.3% vs. observed 14.3%.

## 2026 environment check

Scored on 22,640 snaps from 181 other 2026 games before any Auburn or Florida snap:

| | Estimate | 95% interval | Correction triggered? |
|---|---:|---|---|
| PPA mean residual | −0.016 per play | −0.034 to +0.003 | No (threshold ±0.03 with interval excluding 0) |
| Explosive observed / expected | 0.94 | 0.90 to 0.99 | No (threshold outside 0.90–1.10 with interval excluding 1) |

2025 regular-season Weeks 1–2 showed the same early-season pattern (−0.026 and 0.95) under the 2021–2024 model. No correction was applied.

## Reliability of team residuals

The baseline is reliable league-wide. Team residuals from two games are not. Across 664 FBS team-seasons (2021–2025), regular-season Weeks 1–2 residuals in a situation correlated with rest-of-season residuals at −0.01 to 0.24. The shrinkage learned from that history keeps about 2–11% of a typical two-game cell's raw signal. See `outputs/tables/shrinkage_k.csv` and figure V5.

## Known limitations

- Pre-snap context explains about 5% of play-level PPA variance. The models are situational baselines, not play predictors.
- The ridge baseline leaves more situational bias than XGBoost, so robustness check 10 requires every finding to also hold under XGBoost.
- Opponent strength enters only through the point spread. Spreads beyond the training range (Florida–Campbell, 51.5 points) are extrapolations.
- 2021–2022 training data retains some undetected kneels, and pre-2025 data retains spikes. The 2023–2025 sensitivity refit excludes the kneel-heavy seasons.
- No formation, personnel, coverage, injury, or play-call information is available.

Full list: `docs/limitations.md`.

## Ethical and public-use notes

- Independent analysis of public data, not affiliated with Auburn Athletics or Florida Athletics.
- Outputs describe team units in aggregate. They are not evaluations of individual players or coaches.
- Every public figure carries the data cutoff, a disclaimer, sample sizes, and reliability labels, and the frozen decision rule allows no pregame matchup claims from these results.
