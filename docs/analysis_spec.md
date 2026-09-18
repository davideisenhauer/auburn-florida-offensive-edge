# Analysis specification

**Status:** Frozen Wednesday, September 16, 2026, before any Auburn or Florida outcome was examined
**Code:** Every value here is set in [`src/config.py`](../src/config.py) and enforced by [`src/clean.py`](../src/clean.py) and the tests in [`tests/`](../tests/)
**Changes after this date:** Record them in the change log at the end, with the reason, before looking at the affected results

## 1. Question

> **In the 2026 season so far, where has Auburn's offense under Alex Golesh produced more value than the situation normally produces, where has Florida's defense under Jon Sumrall allowed more than the situation normally allows, and where do those two patterns overlap?**

We measure value two ways:

1. **PPA**, CFBD's predicted points added on the play (section 4 explains why not EPA)
2. **Explosive-play rate**, meaning gains of 20 or more yards

This is a description of two 2026 teams through two games each. It is not a score prediction, a play-calling recommendation, or a causal claim.

## 2. 2026 comes first

Both programs changed head coaches after 2025, and Auburn's offense changed almost completely. The 2026 teams are treated as new teams.

| Context (CFBD, as of September 16) | Auburn | Florida |
|---|---|---|
| Head coach | Alex Golesh, hired November 30, 2025 (first season) | Jon Sumrall, hired November 30, 2025 (first season) |
| 2025 head coaches | Hugh Freeze (fired midseason), D.J. Durkin (interim) | Billy Napier (fired midseason), Billy Gonzales (interim) |
| Returning offensive production (share of 2025 PPA) | 14.4%, 110th of 136 FBS teams | 69.1%, 23rd |
| Returning passing production | 0% | 94.3% |
| Incoming transfers, all positions | 39 (11th most in FBS) | 27 (40th) |
| Incoming transfers on the side that matters here | 27 offensive (2nd most in FBS; FBS median 10) | 8 defensive (74th; FBS median 9) |

For this matchup, Auburn's offense is nearly a new unit in both staff and personnel. Florida's defense has a new head coach and staff, but its transfer intake was about average. CFBD does not publish defensive returning production, so we cannot say more about Florida's defensive roster from this data.

### How older seasons are used

| Allowed | Not allowed |
|---|---|
| Learning the league-wide baseline, meaning what a down, distance, field position, score, clock, venue, and spread normally produce | Any 2025-or-earlier Auburn or Florida statistic in a team profile, prior, or chart |
| Measuring how much two games of team data can be trusted (section 7.4) | Year-over-year comparisons such as "Auburn improved from 2025" |
| Testing the baseline on 2025 before it touches 2026 | Assuming scheme, roster, or coaching continuity |

Older data teaches the league's rules of thumb; it never describes these teams. Because even the league's rules of thumb can drift, the baseline is checked against other 2026 games before it is used (section 7.3).

## 3. Data and cutoff

| Role | Data |
|---|---|
| Baseline training | FBS-involved games, 2021–2024 |
| Untouched test (used once) | 2025 |
| Final baseline | Selected specification refit on 2021–2025 (section 7.2) |
| 2026 environment check | Every other 2026 FBS-involved game through the cutoff |
| Team profiles | Auburn offensive snaps (134 outside garbage time) and Florida defensive snaps (95), 2026 Weeks 1–2 |
| Cutoff | Games on or before September 12, 2026 (US Central) |

**The four matchup games:**
- Auburn 17, Baylor 16 (neutral site, Atlanta)
- Auburn 43, Southern Miss 8
- Florida 66, Florida Atlantic 21
- Florida 52, Campbell 3 (Campbell is FCS)

Sources, hashes, and coverage are documented in [`data_sources.md`](data_sources.md).

## 4. Value metric: CFBD PPA, not cfbfastR EPA

The plan's rule is that one expected-points model must cover every season, and that if cfbfastR EPA fails, the whole analysis moves to CFBD PPA with no splicing. The data audit found that cfbfastR EPA fails.

**Evidence.** Identical pre-snap situations should have identical values under one model:

| Check | 2021 | 2022 | 2023 | 2024 | 2025 | 2026 |
|---|---:|---:|---:|---:|---:|---:|
| cfbfastR EP, 1st and 10 at own 25, 1st quarter, tied | 0.90 | 0.93 | 0.89 | 0.88 | 0.92 | **0.79** |
| cfbfastR EPA, incompletion on 1st and 10 at own 25 | −0.94 | −0.96 | −0.93 | −0.93 | −0.96 | **−0.74** |
| cfbfastR EPA, incompletion on 1st and 10 at midfield | −0.79 | −0.79 | −0.80 | −0.79 | −0.78 | **−0.38** |
| CFBD PPA, incompletion on 1st and 10 at own 25 | −0.703 | −0.703 | −0.703 | −0.703 | −0.703 | −0.703 |
| CFBD PPA, incompletion on 1st and 10 at midfield | −1.114 | −1.114 | −1.114 | −1.114 | −1.114 | −1.114 |
| CFBD PPA, turnover on downs at opponent 2 | −4.149 | −4.149 | −4.149 | −4.149 | −4.149 | −4.149 |

The 2026 file was built on September 14 with cfbfastR's new 3.0 expected-points model; 2021–2025 used the previous model. The cfbfastR win-probability model changed too. A home team favored by 7 starts at 49% in 2021–2025, which ignores the spread, and at 58% in 2026.

**Decision:**
- The value metric is the `ppa` column of the frozen play-by-play files for every season.
- cfbfastR EPA and WP are not used anywhere.
- CFBD's live API has since revalued possession-change plays. The frozen PPA matches CFBD's live `/plays` exactly on every other play in the four games, but not on interceptions, lost fumbles, or turnovers on downs. CFBD's live aggregates are therefore approximate cross-checks only, and live CFBD play data is never mixed into the frozen table.

## 5. Cleaning rules

Implemented in `src/clean.py` and tested in `tests/test_cleaning.py`. The counts removed by each rule, by season, are in `outputs/tables/cleaning_waterfall.csv`.

**Games**
1. Keep completed regular-season and postseason games involving at least one FBS team, using CFBD's game classification. For 2026, keep only games on or before the cutoff.

**Rows**

2. **Remove duplicate rows.** A duplicate matches another row on game, quarter, clock, offense, down, distance, yards to goal, play type, and play text. `id_play` is stored as a floating-point number and loses precision, so it is not a valid key. The replacement key is `play_key`, built from the game ID and the row's position in the raw file.
3. **Snaps** are plays flagged as run or pass. Sacks count as passes.
4. **Recover unflagged snaps.** If cfbfastR typed a real snap as a fumble, safety, or post-play penalty and set neither flag, run or pass is read from the play text. This mostly affects the 2025 and 2026 builds; 297 snaps in 2026 Weeks 1–2 would otherwise disappear, including lost fumbles. The rule excludes no-plays and kicking plays.

**Exclusions from the model sample**

5. No-play penalties and offsetting penalties.
6. **Accepted penalties on a snap.** In these rows, `yards_gained` and PPA can include the penalty. Declined penalties stay.
7. **Kneels.** Either explicit wording ("kneel", "takes a knee"), or an unnamed or TEAM rusher in the last two minutes of the 2nd or 4th quarter, which is how 2021–2022 text records kneels. In both cases the run must gain zero yards or lose yards.
   - Detection is about 17 per 1,000 runs from 2023 on, but 10–12 per 1,000 in 2021–2022. A few hundred kneels likely remain in each of those two training seasons.
   - The 2023–2025 sensitivity baseline excludes those seasons.
8. **Spikes,** by explicit wording only. Text from 2021–2024 does not identify spikes, so roughly 70 per season remain in training data (the 2025 rate). 2026 text does identify them.
9. **Overtime.**
10. **Invalid pre-snap state:** down outside 1–4, distance under 1, yards to goal outside 1–99, distance greater than yards to goal, clock outside 0–1,800 seconds in the half, or missing score.
11. **Missing PPA or yards gained.**

**Flags that stay on the play**

12. **Giveaways** are interceptions and lost fumbles. Turnovers on downs are not giveaways.
13. **Garbage time** follows CFBD and Bill Connelly: the score margin at the snap exceeds 43 points in the 1st quarter, 37 in the 2nd, 27 in the 3rd, or 22 in the 4th. This replaces the plan's win-probability filter because the WP model changed (section 4).
14. **Spread** comes from the play-by-play file. If it's missing, the median CFBD line for that game is used. If both are missing, `spread_missing` is set.

**Samples**
- `in_model_sample`: rules 1–11. Baseline training and the 2026 environment check use every model-sample play, including garbage time.
- `in_team_profile`: the model sample minus garbage time. This is the primary sample for Auburn and Florida, because blowout snaps mostly measure backups against backups. Garbage time was:
  - 31% of Florida's defensive snaps against FAU and 44% against Campbell
  - 28% of Auburn's offensive snaps against Southern Miss
  - none against Baylor

## 6. Situations and publication thresholds

| Dimension | Bins |
|---|---|
| Down | 1st; 2nd; 3rd or 4th |
| Distance | short 1–3; medium 4–7; long 8+ |
| Field position (yards to goal) | own territory 51–99; midfield to opponent 21, 21–50; red zone 1–20 |
| Play family | run; pass (sacks included) |

**Cells.** Start with down × distance × play family. Add field position only where every resulting cell still meets the display threshold. The full cross-product is never built.

**Roll-up** if most cells are too thin:
- standard downs × run
- standard downs × pass
- passing downs × run
- passing downs × pass

A passing down is 2nd and 8 or more, 3rd and 5 or more, or 4th and 5 or more.

**Thresholds** (plays for one team in one cell):

| Plays | Treatment |
|---|---|
| Fewer than 8 | Hidden |
| 8–14 | "Limited sample" label, no recommendation language |
| 15 or more | Eligible for the main opportunity map, with uncertainty shown |

The roll-up decision is made from play counts alone, before any team residual is computed. The data audit notebook reports those counts.

### Binding decision (from the audit counts, September 16)

| Structure | Cells eligible (15+ plays) for both teams |
|---|---|
| Down × distance × play family | 1 of 16 (11 hidden for at least one team) |
| **Standard/passing downs × play family** | **3 of 4** (Florida has 13 run plays on passing downs: limited) |
| Play family × field position | 3 of 6 (red zone hidden for both teams) |

- **The main opportunity map uses standard/passing downs × run/pass.**
- Field position is not added.
- The fine down × distance cells appear only in the two supporting heatmaps (Visuals 1 and 2), with the display thresholds applied.

## 7. Models (built Thursday)

### 7.1 Targets and features

- **Value model:** target is `ppa`.
- **Explosive model:** target is `explosive` (gain of 20 yards or more).
- **Allowed features** (`config.PRE_SNAP_FEATURES`):
  - play family
  - down
  - distance and log distance
  - yards to goal
  - quarter
  - seconds left in the half
  - score margin
  - venue (home, away, neutral)
  - goal to go
  - offense-perspective spread and a missing-spread flag

  Limited interactions are allowed: down × distance, and play family × field position. `tests/test_no_leakage.py` guards the list.
- **Candidates:**
  - regularized linear or logistic regression as the transparent baseline
  - gradient-boosted trees as the flexible candidate

  The boosted model is used only if it beats the baseline on 2025 by a meaningful margin:
  - value model: at least 1% lower mean absolute error
  - explosive model: at least 1% lower Brier score (amended September 17, change log #10)

### 7.2 Validation and refit

1. Tune within 2021–2024 using season blocks, keeping every play of a game in the same fold.
2. Test once on 2025:
   - value model: MAE, RMSE, and mean error by down, distance, field position, play family, and week
   - explosive model: average precision, ROC-AUC, log loss, Brier score, and calibration by decile
3. Refit the chosen specification on 2021–2025 with the same hyperparameters. This refit is the final baseline, so the season closest to 2026 contributes.
4. Sensitivity baseline: the same specification fit on 2023–2025 only, after the 2023 clock rule change.

### 7.3 2026 environment check (before any Auburn or Florida play is scored)

Apply the final baseline to every other 2026 FBS model-sample play through the cutoff, excluding the four matchup games.

- **Value model:** if the mean residual exceeds ±0.03 PPA per play and its 95% game-clustered interval excludes zero, add a constant correction estimated from those plays.
- **Explosive model:** if observed/expected falls outside 0.90–1.10 and its 95% interval excludes 1, apply a logit offset.
- **Benchmark:** report the same residuals for 2025 Weeks 1–2, which are out of sample, so an early-season effect can be told apart from a 2026 shift.

Team profiles use the corrected baseline if a correction was triggered. The uncorrected result is reported as a sensitivity check.

### 7.4 Team residuals and shrinkage

- **Residuals.** For each Auburn offensive snap and Florida defensive snap in the team-profile sample:
  - value residual = PPA − predicted PPA
  - explosive residual = explosive − predicted probability
- **Shrinkage target.** Cell means shrink toward **zero**, meaning the 2026 league baseline, never toward a team's 2025 numbers.
- **Shrinkage strength.** `shrunk mean = n / (n + k) × raw mean residual`. The constant k is set once per play family × down group, from a within-season reliability test:
  - For every FBS team-season from 2021 to 2025, compute the Weeks 1–2 residual mean.
  - Measure how well it predicts the same team's residual for the rest of that season.
  - k is the value that makes the shrunk early mean the best predictor.

  This uses old data only to learn how far two games can be trusted. A 2026 cross-team method-of-moments estimate is reported as a consistency check. k is not adjusted to make a result more dramatic.
- **Matchup edge** in a cell = the average of Auburn's shrunk offensive residual and Florida's shrunk defensive residual allowed. Both components are shown.

### 7.5 Operational details (set September 17, before any model was fit)

These fill gaps in sections 7.1–7.4 and 9. None of them were chosen after seeing a model result.

- **Transparent baseline design:**
  - down indicators with a separate log-distance slope for each down (down × distance)
  - a cubic spline in yards to goal with a separate curve for passes (play family × field position)
  - quarter indicators
  - cubic splines in seconds left in the half, score margin (clipped to ±42), and offense spread (clipped to ±50, missing set to 0 with a flag)
  - venue indicators and the goal-to-go flag

  Every term is standardized. The value model is ridge regression; the explosive models are L2 logistic regression.
- **Boosted candidate:** XGBoost on the same pre-snap features, without splines. A missing spread is left missing.
- **Tuning:**
  - Leave one season out within 2021–2024.
  - Ridge penalty and logistic C are chosen by mean squared error and log loss.
  - XGBoost chooses among four settings (tree depth 4 or 6, crossed with light or heavy minimum leaf weight) at learning rate 0.1. Early stopping uses the held-out season.
  - The final number of trees is the mean best iteration.
- **The alternate explosive target** (robustness check 5) uses the model family chosen for the primary explosive target and is tuned the same way.
- **Naive baseline:** the 2021–2024 mean of the target (PPA per play, or explosive rate).
- **"Beats the naive baseline" (go gate 2) on 2025:**
  - The value model has lower RMSE and lower MAE than naive, and cuts the play-weighted mean absolute bias across down × distance × field position × play family groups by at least 50%.
  - The explosive model has lower Brier score and log loss than naive, ROC-AUC of at least 0.55, and the same 50% cut in group bias.
  - If a model beats naive on RMSE or Brier score but misses one of the other conditions, it "only marginally" beats naive.
- **"Reasonably calibrated" (go gate 3):** on 2025, the explosive model's observed/expected ratio is within 0.95–1.05 and its calibration slope (logistic regression of the outcome on the model's logit) is within 0.85–1.15.
- **Out-of-sample residuals for shrinkage:** 2021–2025 residuals come from leave-one-season-out predictions of the chosen specification, so no play is scored by a model that trained on it. Before team means are taken, residuals are centered on the league average for that season, period (Weeks 1–2 or Week 3 on), side, metric, and cell. A league-wide shift shared by a team's early and late games is therefore not mistaken for team skill, which would understate shrinkage.
- **Shrinkage constant k:**
  - Estimated separately for each metric (value, explosive) and each side (offense, defense), within each play family × down group. That's 16 values.
  - Early season is regular-season Weeks 1–2, and "rest of season" is every later game, postseason included. The play-by-play also numbers bowl games week 1 (change log #15). Only team-profile plays by FBS teams count.
  - k minimizes the squared error of predicting a team's rest-of-season residual mean from its shrunk early mean, weighted by the number of rest-of-season plays. It's searched over 1 to 10,000 plays, with "no trust" (shrink to zero) also allowed.
  - Fine down × distance cells use the k of the down group that holds most of the cell's plays.
- **Uncertainty:** 90% intervals come from a play-level bootstrap within each team's cell (4,000 resamples), with the shrinkage factor held fixed. They are descriptive and do not decide labels.
- **Most influential play (check 7):** the one play, from either team's cell, whose removal moves the matchup edge furthest toward the opposite sign.
- **Findings** are rollup cell × metric pairs: four cells, two metrics, eight findings.
- **Go gate 4 ("at least two matchup cells meet the sample and robustness rules"):** at least two findings with 15 or more plays for both teams that keep their direction under every applicable robustness check, whether that direction is favorable to Auburn or not.
- **Go gate 5 ("the conclusion remains clear after turnover and garbage-time checks"):** Auburn's overall run edge and overall pass edge (pooled over downs), for both metrics, keep their direction when garbage time is included and when giveaways are removed. Pooled edges combine the down-group components, each shrunk with its own k and weighted by plays.
- **Label edge case:** a finding with a favorable edge, 15 or more plays for both teams, and no failed checks, but one team component pointing the other way, is labeled "possible signal."
- **"Strongest favorable finding" (no-claims rule):** among favorable findings that meet the display threshold, rank by label (strongest, then possible, then none), then by fewest failed checks, then by edge divided by its bootstrap standard error.
- **Check 10:** uses the boosted models scored on 2026 plays, with the same environment rule applied to them.

## 8. Robustness checks and labels

A finding is a headline candidate only if it keeps its direction under every check below. A finding that fails two or more checks cannot be a headline.

1. The final baseline and the 2023–2025 sensitivity baseline agree.
2. Garbage time included (the primary analysis excludes it).
3. Accepted-penalty snaps included (PPA only, because their yardage is unreliable).
4. Giveaways removed.
5. Alternate explosive definition (pass gain of 20 or more, run gain of 10 or more).
6. **Leave one game out.** The finding holds without either game on its own. Given the teams' opponents, the most important cases are Florida without Campbell (FCS, spread −51.5) and Auburn without Southern Miss (spread −32.5).
7. Removing the single most influential play keeps the direction.
8. The 2026 environment correction, if one was applied, is removed.
9. The cell meets the display threshold.
10. **The boosted baseline agrees.** Residuals from the boosted candidate, refit on 2021–2025, keep the same direction. This was added September 17, after the 2025 test and before any team residual was computed (change log #13).

**Labels:**
- **Strongest signal:** both team components point in the favorable direction, the cell has 15 or more plays for both teams, and the finding passes every check.
- **Possible signal:** favorable direction, but it fails one check or has 8–14 plays.
- **No clear signal:** anything else.

No more than three takeaways are published.

## 9. Go and no-go

The plan's section 14 gates apply, with PPA in place of EPA and the definitions in section 7.5.

| Decision | When |
|---|---|
| **Go: full matchup release** | All five gates pass: (1) four games reconciled, (2) both models beat naive, (3) explosive model calibrated, (4) at least two robust eligible findings, (5) overall run and pass conclusions stable |
| **Simpler descriptive release** | Gates 1 and 3 pass, but a model only marginally beats naive or gate 4 fails. It shows 2026 opportunity-adjusted run and pass profiles with no rankings. |
| **No matchup claims before the game** | A game is missing or inconsistent, a model fails to beat naive at all, the strongest favorable finding fails check 7 (one play drives it), or every favorable finding has fewer than 8 plays. The project is then published after the game as a methodology build. A pregame post is allowed only if it makes no situational matchup claim (amended September 18, change log #14). |

## 10. Change log against the project plan

| # | Plan | Change | Reason | Date |
|---|---|---|---|---|
| 1 | `espn_cfb_pbp` play-by-play | `cfbfastR_cfb_pbp` | ESPN 2026 games were stale mid-game snapshots | Sept. 16 |
| 2 | cfbfastR EPA | CFBD PPA from the same files | 2026 file uses a new EP model (section 4); this is the plan's own fallback | Sept. 16 |
| 3 | Garbage time by win probability 5–95% | CFBD/Connelly score margin by quarter | cfbfastR WP model changed in 2026 | Sept. 16 |
| 4 | Scoring model trained 2021–2024 | Refit on 2021–2025 after the 2025 test | Put the closest season in the final baseline (2026 first) | Sept. 16 |
| 5 | None | 2026 environment check and correction rule | Older league norms are checked against 2026 before use | Sept. 16 |
| 6 | Shrinkage "from historical reliability tests" | Specified: toward zero, k from within-season Weeks 1–2 → rest-of-season reliability | Freeze the method before results; never shrink toward 2025 team data | Sept. 16 |
| 7 | "Early-down, passing-down" roll-up | Standard downs vs. passing downs (CFBD definition) | Remove overlap between the two groupings | Sept. 16 |
| 8 | Accepted penalties "in a sensitivity view" | Excluded from the primary analysis; included in check 3 for PPA only | Their `yards_gained` includes penalty yards | Sept. 16 |
| 9 | Leave-one-game-out mentioned in the risk table | Required robustness check 6 | Two games per team, one against an FCS opponent | Sept. 16 |
| 10 | Boosted explosive model needs 0.01 lower Brier score | 1% lower Brier score | The naive Brier score at the 6.9% training rate is 0.0646, so 0.01 would require an implausible 15% gain from pre-snap context. Set before any model was fit. | Sept. 17 |
| 11 | Gates and shrinkage described in words | Operational definitions in section 7.5 and section 9 | A go/no-go decision must not depend on interpretation after results. Set before any model was fit. | Sept. 17 |
| 12 | Shrinkage k "per play family × down group" | Also separate by metric and by side (offense, defense) | Explosive plays and PPA have different noise, and offense and defense reliability can differ. Set before any model was fit. | Sept. 17 |
| 13 | Nine robustness checks | Added check 10: the boosted baseline must agree | The frozen rule chose ridge regression (the boosted MAE gain was 0.44%, below the 1% bar), but on 2025 ridge left more situation bias (0.078 vs. 0.028 PPA per play across groups). The check can only remove findings, never add them. Set after the 2025 test, before any team residual was computed. | Sept. 17 |
| 14 | A no-claims outcome is published after the game as a methodology build (section 9) | A pregame post is also allowed if it makes no situational matchup claim. It may report what two games can and cannot separate: the reliability result, and all eight findings with their frozen labels. The methodology build is still published. | The plan's risk table allows "publish the honest result and focus on what the data can and cannot separate." The no-claims rule exists to stop pregame matchup claims, not to withhold the reliability result. Chosen by the project owner after the Thursday decision was known. It changes publication timing only, not any rule, threshold, label, or result. | Sept. 18 |
| 15 | Section 7.5: "Early season is Weeks 1–2 and 'rest of season' is Week 3 on" | No rule change; the code now follows the rule. Early season means **regular-season** Weeks 1–2. Every other game in that season, postseason included, is rest of season. The same fix applies to the 2025 Weeks 1–2 environment benchmark, the 2025 error-by-week table (postseason shown separately), and the audit notebook's early-season table. | A Sept. 18 code review found that the play-by-play numbers every bowl and playoff game as week 1, so 38–46 postseason games per season were counted as early season in the shrinkage reliability test and the 2025 benchmark. That contradicts the frozen definition. This entry was written before any corrected output was computed. Every downstream result (k, shrunk components, edges, intervals, checks, labels, gates, decision, figures) is regenerated under otherwise unchanged rules and reported whichever way it comes out. Pre-fix and corrected results are compared in `go_no_go.md`. | Sept. 18 |
| 16 | None: supporting analysis added after the decision | `src/insights.py`, league-wide and descriptive: (a) how reliable each early-season measure is, from tendencies to efficiency, over 2021–2025 team-seasons; (b) a leave-one-season-out test of raw vs. opponent- and situation-adjusted early numbers as predictors of the rest of the season; (c) empirical-Bayes rank intervals for every 2026 FBS offense through the cutoff; (d) the distribution of matchup edges across every 2026 FBS offense–defense pairing. | The pregame post has to say what two games *can* tell you, not only what they cannot. These use the frozen samples, models, and shrinkage machinery without altering them. They add no matchup finding and change no threshold, label, gate, or the decision; Auburn and Florida appear only as two of the FBS teams in league-wide summaries, and (d) can only contextualize the no-claims decision, never overturn it. Logged before any of these results were computed. | Sept. 18 |
