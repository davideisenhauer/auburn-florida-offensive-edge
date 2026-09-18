# What two games can and can't tell you

**As of:** Friday, September 18, 2026 · **Data cutoff:** September 12, 2026
**Code:** [`src/insights.py`](../src/insights.py) · **Tables:** `outputs/tables/insight_*.csv` · **Figures:** V6, V7, V8

Supporting analysis, logged as change log #16 in [`analysis_spec.md`](analysis_spec.md). It is league-wide and descriptive. It reuses the frozen samples, models, and shrinkage without altering them, and it adds no matchup finding. The Auburn–Florida pairing is recomputed here from scratch and checked against the frozen `matchup_findings.csv`, which it reproduces exactly.

The matchup question ran into a wall: under the frozen rules, no situation showed a clear signal. That raises a more useful question. **After two games, what is actually knowable?**

## 1. Play-calling settles in a game and a half. Quality takes most of a season.

For every FBS team-season from 2021 to 2025, each measure's regular-season Weeks 1–2 value was tested against that team's value for the rest of that same season. The result is a single number per measure: how many games it takes before a team's own number deserves as much weight as the league average.

| Measure (offense) | Games to half weight | Weight after two games | Early vs. rest of season |
|---|---:|---:|---:|
| Pass rate | 1.4 | 59% | 0.70 |
| Pass rate, standard downs | 1.5 | 57% | 0.68 |
| Pass rate, passing downs | 2.5 | 45% | 0.59 |
| Sack rate allowed | 6.1 | 25% | 0.38 |
| Success rate | 6.4 | 24% | 0.41 |
| PPA per play | 6.4 | 24% | 0.43 |
| Yards per play | 7.2 | 22% | 0.40 |
| Explosive-play rate (20+ yards) | 10.1 | 17% | 0.32 |
| PPA over expected | 10.7 | 16% | 0.32 |
| Explosive rate over expected | 17.0 | 11% | 0.22 |

**What a team chooses to do is knowable almost immediately. How well it is going is not.** Two games is already most of the way to a reliable pass rate. It is one sixth of the way to a reliable explosive-play rate, and a fifth of the way for the opponent-adjusted version. To trust an offense's explosiveness as much as two games let you trust its pass rate, you would need about 14 games.

**Defenses are harder still.** The same test on the defensive side puts PPA over expected allowed at 15.4 games, against 10.7 for offenses. Defensive "pass rate faced" barely persists at all (0.14), which makes sense: the opponent chooses it.

**A subtlety worth naming.** Raw PPA per play looks *more* stable early (0.43) than opponent- and situation-adjusted PPA over expected (0.32). That is not because the raw number is better. It is partly because schedules repeat: a team that opens against weak opponents often keeps playing weak opponents, so the raw number partly measures the schedule, and the schedule persists. Section 3 separates the two.

## 2. Two games cannot rank a team

Using an empirical-Bayes posterior for each 2026 FBS offense (prior from the reliability test above, likelihood from its own plays):

- The median offense's 90% rank interval covers **118 of 138 places**.
- **124 of 138 offenses could still be a top-25 offense.** 114 could be both top-25 and bottom-25.
- Auburn's two games put it 126th, and the range consistent with that evidence is **24th to 136th**. Neither panic nor optimism is supported.
- Raw two-game numbers spread from −0.21 to +0.28 PPA per play (5th to 95th percentile). After discounting for reliability, the supportable spread is −0.035 to +0.039. **Two games make offenses look about seven times more different than the evidence supports.**
- For the median offense, removing its single most influential play moves its two-game average by **0.045 PPA per play**, more than three times the largest edge in the Auburn–Florida matchup.

These intervals are, if anything, too narrow. They treat plays as independent, and plays within a game are correlated.

## 3. Taking two-game numbers at face value is worse than knowing nothing

Leave-one-season-out over 2021–2025: fit the shrinkage on four seasons, predict each team's rest-of-season value in the fifth, weight by plays.

| Target | Early input | Treatment | RMSE | vs. guessing the league average |
|---|---|---|---:|---:|
| Rest-of-season PPA per play | raw two-game PPA | league average | 0.092 | — |
| | raw two-game PPA | as measured | 0.161 | **75% worse** |
| | raw two-game PPA | shrunk | 0.083 | 9% better |
| | adjusted two-game PPA over expected | shrunk | 0.086 | 7% better |
| Rest-of-season PPA over expected | adjusted | league average | 0.077 | — |
| | adjusted | as measured | 0.151 | 96% worse |
| | adjusted | shrunk | 0.073 | **5% better** |
| | raw | shrunk | 0.074 | 3% better |

Two conclusions:

1. **Unshrunk two-game splits are worse than no information.** Quoting them at face value is not a small error; it predicts the rest of the season considerably worse than assuming every team is exactly average.
2. **Adjust for what you are trying to predict.** To predict what a team will actually produce, raw early numbers carry useful schedule information. To predict team quality with opponent and situation removed, the adjusted number is the better input. Either way, shrink it.

## 4. The Auburn–Florida edge is an ordinary one

Every 2026 FBS offense was paired with every 2026 FBS defense (18,906 pairings) and scored exactly as the real matchup was: the shrunk edge in each of the four situations.

| | Largest PPA edge per play, either direction |
|---|---:|
| Median pairing | 0.017 |
| 90th percentile | 0.029 |
| Largest of all | 0.059 |
| **Auburn–Florida** | **0.013** |

Auburn–Florida's largest edge is **smaller than 72% of all FBS pairings**. The frozen decision did not fail to find something unusual; there was nothing unusual to find. This context cannot overturn the no-claims decision, and it is not used as a finding.

## 5. What this means for the matchup

Two games can support a description of what Auburn's offense chooses to do. Through the cutoff, it passed on 48.5% of its snaps outside garbage time, 72nd of 138 FBS teams, and 42.6% on standard downs (67th): close to league-median balance.

Two games cannot support a claim about how good either unit is, how they match up, or where an edge lies. That is not a limitation of this project's method. It is a property of two games, and it is measurable.

## Method notes and caveats

- **Samples.** Team-profile plays only, so garbage time is excluded. FBS teams only, by season. Early season means regular-season Weeks 1–2 (the play-by-play numbers bowl games week 1 too; change log #15).
- **Centering.** Every measure is centered on the league average for that season and period, so a league-wide drift is not mistaken for team skill.
- **The reliability constant** is fitted the same way as the frozen shrinkage: the value that minimizes play-weighted squared error when predicting a team's rest-of-season value from its shrunk early value.
- **"Games to half weight"** is that constant divided by the median plays per game for the measure. Sack rate uses pass snaps as its denominator, so its games count reflects dropbacks, not all snaps.
- **The rank posterior** assumes a normal prior and likelihood and independent plays. Game-to-game correlation would widen the intervals.
- **The prediction test** fits the shrinkage without the season it scores, but the measures and the model specification were chosen with all seasons visible. It is a fair comparison between treatments, not a forecast of future accuracy.
- **Pairings** include every FBS offense and defense with at least 8 plays in a situation, whether or not the teams ever play each other. They are a reference distribution, not predictions of games.
