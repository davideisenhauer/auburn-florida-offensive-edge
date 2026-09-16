# Go / no-go decision

**Date:** Thursday, September 17, 2026
**Data:** 2026 games through September 12 (Auburn: Baylor, Southern Miss; Florida: Florida Atlantic, Campbell)
**Rules applied:** [`analysis_spec.md`](analysis_spec.md) sections 7.5, 8, and 9. Every threshold was set before the result it governs; the change log records when.
**Corrected:** Friday, September 18, 2026. A code error counted bowl games as early season in the reliability test (change log #15). The numbers below are corrected, and the decision did not change. See [Correction](#correction-september-18).

## Decision: no matchup claims before the game

All five go gates pass, but one no-claims trigger fires: **the strongest favorable finding for Auburn depends on a single play.** Under the frozen rules, the project makes no pregame claim about where Auburn's offense has an edge on Florida's defense.

| Item | Result | Detail |
|---|---|---|
| Gate 1: four games reconciled | Pass | All final scores match official records; plays, pass attempts, and interceptions are within 1 |
| Gate 2: models beat the naive baseline on 2025 | Pass | PPA: lower MAE and RMSE, 61% less situational bias. Explosive: lower Brier score and log loss, ROC-AUC 0.69, 85% less bias |
| Gate 3: explosive model calibrated | Pass | Observed/expected 0.98, calibration slope 0.97 |
| Gate 4: at least two robust, well-sampled findings | Pass | Three, **all unfavorable to Auburn** |
| Gate 5: overall run and pass conclusions stable | Pass | Both lean slightly against Auburn with or without garbage time and giveaways |
| Trigger: a model fails to beat naive | No | |
| **Trigger: strongest favorable finding driven by one play** | **Yes** | Runs on passing downs (PPA) turn negative without one 12-yard B. Brown run |
| Trigger: no favorable finding meets the display threshold | No | |

## What the data shows

### 1. Two games say very little about a team in a given situation

Across every FBS team-season from 2021 to 2025, a team's Weeks 1–2 residual in a situation correlated with its rest-of-season residual at only −0.01 to 0.24. The shrinkage learned from that history keeps about 1–12% of a 2026 cell's raw signal. This is the central result: two-game situational splits, taken at face value, are mostly noise.

### 2. Auburn's offense has fallen short of what its situations and spreads normally produce

Measured outside garbage time:

| | PPA per play: actual | PPA per play: expected | Explosive rate: actual | Explosive rate: expected |
|---|---:|---:|---:|---:|
| vs. Baylor (Auburn favored by 6.5, neutral site) | 0.03 | 0.21 | 8.0% | 8.2% |
| vs. Southern Miss (Auburn favored by 32.5) | 0.30 | 0.45 | 5.1% | 9.4% |

The PPA shortfall shows up in every run/pass × down group. It is largest when passing on passing downs: 0.15 PPA per play against an expected 0.44, and 1 explosive play in 25 attempts.

### 3. Florida's defense is close to what its situations and point spreads implied

Florida allowed slightly more than expected against FAU (+0.05 PPA per play) and slightly less against Campbell (−0.08). No Florida component is large after shrinkage.

### 4. All eight findings, after shrinkage

The edge is the average of Auburn's offensive residual and Florida's defensive residual allowed. Positive favors Auburn. PPA edges are points per play; explosive edges are changes in the probability of a 20-yard play.

| Situation | Metric | Plays (AU / UF) | Edge | 90% interval | Checks failed | Label |
|---|---|---|---:|---|---|---|
| Pass, standard downs | PPA | 40 / 40 | −0.005 | −0.018 to +0.009 | 4, 6 | No clear signal |
| Pass, standard downs | Explosive | 40 / 40 | −0.000 | −0.004 to +0.004 | 4, 5, 6 | No clear signal |
| **Pass, passing downs** | PPA | 25 / 21 | **−0.013** | −0.028 to +0.004 | none | No clear signal (robust, unfavorable) |
| **Pass, passing downs** | Explosive | 25 / 21 | **−0.003** | −0.004 to −0.000 | none | No clear signal (robust, unfavorable) |
| **Run, standard downs** | PPA | 54 / 21 | **−0.010** | −0.028 to +0.006 | none | No clear signal (robust, unfavorable) |
| Run, standard downs | Explosive | 54 / 21 | −0.001 | −0.002 to +0.001 | 6 | No clear signal |
| Run, passing downs | PPA | 15 / 13 | +0.001 | −0.020 to +0.023 | 6, 7, 10 | No clear signal |
| Run, passing downs | Explosive | 15 / 13 | −0.000 | −0.002 to +0.003 | 2, 6 | No clear signal |

Check numbers:
1. 2023–2025 baseline
2. Garbage time included
3. Accepted penalties included
4. Giveaways removed
5. Alternate explosive definition
6. Leave one game out
7. Most influential play removed
8. Environment correction removed
9. Display threshold
10. Boosted baseline

**Robust** means the edge keeps its direction under every applicable check. It does not mean large or certain: two of the three robust findings have intervals that include zero, and all three are about a hundredth of a point per play.

## Caveats behind the decision

- **Early-season shift.** Early 2026 offenses league-wide run slightly below the full-season baseline: −0.016 PPA per play and 94% of expected explosive plays. The same happened in 2025 Weeks 1–2, and it stayed under the correction threshold. After shrinkage it moves each edge by about −0.001 against Auburn, a tenth of the robust findings.
- **Baseline choice.** The frozen rule kept ridge and logistic regression because boosting improved 2025 accuracy by under 1%. Ridge leaves more situational bias, so check 10 (the boosted baseline must agree) was added before any team residual existed. It flipped one finding that already failed other checks, so it changed no conclusion.
- **Spread extrapolation.** Florida's Campbell game carries a 51.5-point spread, beyond 99.6% of training plays. Leave-one-game-out (check 6) covers it.
- **Hidden context.** Public play-by-play has no formations, personnel, coverage, or injuries.

## What the rule means for Friday

The spec's consequence for this outcome is to publish the project after the game as a methodology build, not to force a pregame conclusion. The plan's risk table also allows "publish the honest result and focus on what the data can and cannot separate." A pregame post along those lines would have to make **no** situational claim about the matchup. That choice belongs to the project owner.

**Owner decision (Friday, September 18):** publish a pregame post that makes no matchup claims, built around what two games can and cannot tell you, and publish the full methodology build as well. Recorded as change log #14 in the spec; no rule, threshold, label, or result changed.

## Correction (September 18)

A Friday code review found that the play-by-play numbers every bowl and playoff game as week 1. The shrinkage reliability test selected "Weeks 1–2" by week number alone, so 38–46 postseason games per season were counted as early season. That contradicts the frozen definition (spec section 7.5). The fix restricts early season to regular-season Weeks 1–2. It was logged as change log #15 before any corrected output was computed, and everything downstream was regenerated under otherwise unchanged rules.

| | Thursday (error) | Corrected |
|---|---|---|
| Early vs. rest-of-season correlation | 0.01 to 0.25 | −0.01 to 0.24 |
| Weight two games deserve at a typical sample | 2% to 15% | 2% to 11% |
| Shrinkage constants k | about 180 to 1,800 plays | about 160 to 1,060 plays |
| Robust findings (gate 4) | 3, all unfavorable to Auburn | the same 3 |
| Only favorable finding (runs, passing downs, PPA) | +0.002, fails checks 6, 7, 10 | +0.001, fails checks 6, 7, 10 |
| Pass, standard downs: failed checks (PPA / explosive) | 4, 6, 10 / 5, 6 | 4, 6 / 4, 5, 6 |
| 2025 Weeks 1–2 benchmark | 224 games, −0.026 PPA, 94% of expected explosive plays | 179 games, −0.026 PPA, 95% |
| Gates, triggers, labels, decision | all as reported | **unchanged** |

The fitted models, predictions, cleaned plays, 2025 test, and `go_no_go.csv` are byte-identical before and after the fix. The pre-fix tables are not kept in the repository.

## Reproduce

```bash
.venv/bin/python -m src.ingest && .venv/bin/python -m src.clean && .venv/bin/python -m src.reconcile
.venv/bin/python -m src.models && .venv/bin/python -m src.matchup
.venv/bin/python -m pytest
```

Evidence: `notebooks/02_baseline_models.ipynb`, `notebooks/03_matchup_analysis.ipynb`, and `outputs/tables/`.
