# Methodology

**As of:** Friday, September 18, 2026
**Data cutoff:** games on or before September 12, 2026 (US Central)
**Binding rules:** [`analysis_spec.md`](analysis_spec.md). This document explains the method in plain terms. Where the two differ, the spec wins.

## 1. The question and why it is framed this way

> In the 2026 season so far, where has Auburn's offense under Alex Golesh produced more value than the situation normally produces, where has Florida's defense under Jon Sumrall allowed more than the situation normally allows, and where do those two patterns overlap?

Auburn and Florida had each played two games when the data was frozen. Their opponents differed: Baylor and Southern Miss for Auburn, Florida Atlantic and FCS Campbell for Florida. Raw splits, such as "Auburn averages X on second down," would mix team ability, opponent strength, game state, and small-sample noise. The method has three layers to separate those:

1. **League baseline:** what a play normally produces, given only what was known before the snap.
2. **Team residuals:** how far Auburn's offense and Florida's defense landed above or below that baseline, by situation.
3. **Shrinkage and checks:** how much of each residual two games can support, and whether it survives robustness checks.

The project is not a score prediction, a play-calling recommendation, or a causal claim about running or passing.

## 2. Data

| Role | Data |
|---|---|
| Play-by-play | SportsDataverse `cfbfastR_cfb_pbp` release (CollegeFootballData plays processed by cfbfastR), one Parquet file per season, 2021–2026 |
| Baseline training | FBS-involved games, 2021–2024 |
| One-time test | 2025 |
| Final baseline | Same specification refit on 2021–2025 |
| 2026 environment check | Every other FBS-involved 2026 game through the cutoff (181 games) |
| Team profiles | Auburn offensive snaps (134) and Florida defensive snaps (95) from 2026 Weeks 1–2, garbage time excluded |
| Reconciliation | CFBD game and box score endpoints, plus official box scores from auburntigers.com (WMT stats feed) and floridagators.com (Sidearm) |

All 58 raw files are saved unchanged and listed with SHA-256 hashes in [`data/data_manifest.csv`](../data/data_manifest.csv). Details: [`data_sources.md`](data_sources.md).

**2026 comes first.** Both programs have first-year head coaches. Auburn's offense is nearly all new: 14% of its 2025 offensive production returns, and it added 27 offensive transfers. Older seasons are used only to learn league-wide rules of thumb and to measure how far two games can be trusted. No 2025-or-earlier Auburn or Florida number appears anywhere as a profile, prior, or comparison.

## 3. Value metric: PPA

The value measure is **PPA (predicted points added)**, CollegeFootballData's play-level expected-points change, taken from the `ppa` column of the frozen files. The plan originally called for cfbfastR EPA. The audit found that the 2026 file was built with cfbfastR's new 3.0 expected-points model while 2021–2025 used the previous one, so identical situations carry different EPA in 2026. PPA gives identical situations identical values in every season, so the whole analysis uses PPA, as the plan's fallback rule required. EPA and PPA are never mixed. Evidence: spec section 4.

The second measure is the **explosive-play rate**: the share of snaps gaining 20 or more yards.

## 4. Cleaning

Implemented in `src/clean.py`, tested in `tests/test_cleaning.py`, with counts by rule and season in `outputs/tables/cleaning_waterfall.csv`.

- Keep completed regular-season and postseason games involving an FBS team, through the cutoff.
- Remove duplicate rows. The file's play ID is stored as a floating-point number and is not a usable key, so a key is built from the game and row position.
- Keep run and pass snaps; sacks count as passes. 1,892 real snaps that cfbfastR typed as fumbles or penalties are recovered from the play text, including 297 in 2026.
- Exclude no-plays, offsetting penalties, accepted penalties on the snap (their yardage and PPA include the penalty), kneels, spikes, overtime, invalid game states, and plays missing PPA or yards.
- **Garbage time** follows CFBD and Bill Connelly: the score margin at the snap exceeds 43 points in the 1st quarter, 37 in the 2nd, 27 in the 3rd, or 22 in the 4th. Baseline training keeps these plays. Team profiles exclude them, because blowout snaps mostly measure backups against backups.

The model sample has 612,758 snaps, 23,223 of them from 2026.

## 5. League baseline models

Built in `src/models.py`; evidence in `notebooks/02_baseline_models.ipynb`.

**Features** (pre-snap only; `tests/test_no_leakage.py` guards the list): run or pass, down, distance and log distance, yards to goal, quarter, seconds left in the half, score margin, venue, goal to go, and the offense's point spread with a missing-spread flag. Two interactions were allowed in advance: down × distance, and play family × field position.

**Candidates and selection.** Each target had a transparent model and a flexible one:

| Target | Transparent | Flexible | Rule | Result |
|---|---|---|---|---|
| PPA | Ridge regression with splines | XGBoost | Flexible must cut 2025 MAE by 1% or more | XGBoost cut MAE 0.44%; **ridge chosen** |
| Explosive play | L2 logistic regression with splines | XGBoost | Flexible must cut 2025 Brier score by 1% or more | XGBoost cut Brier 0.28%; **logistic chosen** |

Tuning used leave-one-season-out validation within 2021–2024, keeping every play of a game in the same fold. 2025 was scored once. The chosen specification was then refit on 2021–2025.

**2025 test (119,951 snaps):**

| | Naive (training mean) | Chosen model |
|---|---:|---:|
| PPA: mean absolute error | 0.944 | 0.929 |
| PPA: root mean squared error | 1.303 | 1.271 |
| PPA: average situational bias | 0.202 | 0.078 (61% lower) |
| Explosive: Brier score | 0.0634 | 0.0616 |
| Explosive: log loss | 0.248 | 0.232 |
| Explosive: ROC-AUC | | 0.69 |
| Explosive: observed / expected | | 0.98 |
| Explosive: calibration slope | | 0.97 |
| Explosive: average situational bias | 0.0364 | 0.0055 (85% lower) |

Pre-snap context explains little of any single play's PPA (R² ≈ 0.05). That is expected, because most of a play's value comes from what happens after the snap. The baseline's job is to remove situational bias, and it does. Ridge leaves more bias than XGBoost (0.078 vs. 0.028), so robustness check 10 requires every finding to hold under the XGBoost baseline as well.

**2026 environment check.** Before any Auburn or Florida play was scored, the final baseline was applied to 22,640 snaps from 181 other 2026 games. Early 2026 ran slightly below the baseline, at −0.016 PPA per play and 94% of expected explosive plays. 2025 Weeks 1–2 looked the same, and neither triggered the frozen correction rule (±0.03 PPA with an interval excluding zero; observed/expected outside 0.90–1.10 with an interval excluding 1). No correction was applied.

## 6. Team residuals, cells, and shrinkage

Built in `src/matchup.py`; evidence in `notebooks/03_matchup_analysis.ipynb`.

**Residuals.** For each Auburn offensive snap and each Florida defensive snap: PPA minus predicted PPA, and explosive (0 or 1) minus predicted probability. Positive means Auburn's offense produced more than expected, or Florida's defense allowed more. Every figure colors that direction the same way, from Auburn's perspective.

**What "expected" means.** The baseline includes each game's point spread. The spread prices in the market's view of both teams, including the offense's own strength, so "over expected" means above what plays in that situation and that game's line normally produce, not above an average offense. Auburn was a 32.5-point favorite against Southern Miss, so its expected PPA there was high. A negative residual means Auburn fell short of that expectation, not that it was below average.

**Cells.** The situations were fixed before any team result was computed:

- Down (1st; 2nd; 3rd or 4th) × distance (1–3, 4–7, 8+) × run or pass. These appear only in the two supporting heatmaps.
- The main map uses **standard downs vs. passing downs × run or pass**. A passing down is 2nd and 8 or more, or 3rd/4th and 5 or more. This roll-up was chosen from play counts alone, because only 1 of 16 fine cells had 15 or more plays for both teams.

**Display thresholds** (plays for one team in one cell): fewer than 8 are hidden; 8–14 are labeled "limited sample"; 15 or more are eligible for the main map.

**Shrinkage.** Each cell's mean residual is pulled toward zero, the league baseline, never toward a team's 2025 numbers:

`shrunk = n / (n + k) × raw mean residual`

The constant k was learned separately for each measure, side, play family, and down group (16 values). For every FBS team-season from 2021 to 2025 (664 of them), a team's regular-season Weeks 1–2 residual was used to predict its residual for the rest of that season, postseason included, and k is the value that made that prediction most accurate. Residuals came from out-of-season predictions and were centered on each season's league average, so a league-wide drift was not mistaken for team skill.

**Result:** early and late residuals correlated at only −0.01 to 0.24. At a typical two-game sample, the best-predicting weight on a team's own result was 2% to 11% (figure V5). The 2026 main-map cells keep 2% to 12% of their raw residuals.

*Correction, September 18:* the first version of this test also counted bowl and playoff games as early season, because the play-by-play numbers them week 1. That reported correlations of 0.01 to 0.25 and weights of 2% to 15%. The fix (spec change log #15) changed no gate, label, or decision; see [`go_no_go.md`](go_no_go.md#correction-september-18). This is the project's central finding: two-game situational splits are mostly noise.

## 7. Matchup edge, checks, and labels

**Edge.** In each of the four main cells, for each measure, the edge is the average of Auburn's shrunk offensive residual and Florida's shrunk defensive residual. That gives eight findings. **90% intervals** come from a play-level bootstrap within each team's cell (4,000 resamples, shrinkage factor held fixed). They are descriptive only (see limitations).

**Robustness checks.** A finding must keep its direction under each applicable check:

1. The 2023–2025 sensitivity baseline
2. Garbage time included
3. Accepted-penalty snaps included (PPA only)
4. Giveaways removed
5. Alternate explosive definition: passes of 20+ yards, runs of 10+ (explosive only)
6. Each of the four games left out
7. The single most influential play removed
8. The environment correction removed (not applicable: none was applied)
9. The display threshold met
10. The XGBoost baseline

**Labels:**
- **Strongest signal:** favorable to Auburn, both team components favorable, 15+ plays for both teams, and no failed check.
- **Possible signal:** favorable, but one failed check or 8–14 plays.
- **No clear signal:** everything else.

At most three takeaways may be published.

## 8. Go / no-go

The gates and triggers were operationalized on September 17, before any model was fit (spec sections 7.5 and 9). All five gates passed: the games reconciled, both models beat naive, the explosive model was calibrated, three findings were robust, and the overall run and pass conclusions were stable. One no-claims trigger also fired. The strongest favorable finding, runs on passing downs (PPA), rests on 15 and 13 plays and an edge of +0.001. It flips without a single 12-yard run. The frozen decision was **no matchup claims before the game**. See [`go_no_go.md`](go_no_go.md).

On September 18, the project owner chose to publish a pregame post that makes no matchup claims and explains what two games can and cannot separate. Spec change log #14 records that choice; it changed no rule, threshold, label, or result.

## 9. Public figures

`src/visuals.py` reads only `outputs/tables/` and writes each PNG together with the exact numbers drawn on it (`outputs/figures/*_data.csv`). `tests/test_visuals.py` checks those numbers against the source tables, parses every printed label back into a number, and checks that each figure carries the disclaimer, the data cutoff, PPA wording, no recommendation language, at most three takeaways on the hero map, and the same color direction.

| Figure | Shows |
|---|---|
| V1 `v1_auburn_offense_ppa.png` | Auburn offense PPA over expected by down × distance × run/pass, shrunk and raw, with play counts |
| V2 `v2_florida_defense_ppa.png` | Florida defense PPA allowed over expected, same layout and colors |
| V3 `v3_explosive_plays.png` | Explosive-play rate, observed vs. expected, for both teams in the four main cells |
| V4 `v4_opportunity_map.png` | All eight findings: PPA edge × explosive edge, 90% intervals, robustness styling |
| V5 `v5_two_game_reliability.png` | How much weight two games deserve, by situation, from 2021–2025 FBS team-seasons |
| V6 `v6_reliability_spectrum.png` | Games needed before each measure is worth as much as the league average |
| V7 `v7_rank_intervals.png` | The range of national ranks consistent with each 2026 FBS offense's two games |
| V8 `v8_pairing_distribution.png` | The largest situational edge for every 2026 FBS offense–defense pairing |

## 10. Supporting analysis

After the decision, `src/insights.py` added league-wide context: how reliable each early-season measure is, whether opponent- and situation-adjusted early numbers predict better than raw ones, empirical-Bayes rank intervals for every 2026 FBS offense, and the same matchup edge computed for all 18,906 FBS pairings. It reuses the frozen samples and shrinkage, adds no matchup finding, and reproduces the frozen Auburn–Florida edges exactly as a check. Results and caveats: [`insights.md`](insights.md); logged as change log #16.
