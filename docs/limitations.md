# Limitations

**As of:** Friday, September 18, 2026 · **Data cutoff:** September 12, 2026

These limits apply to every number, figure, and post from this project. Each one is disclosed rather than corrected after the fact, because the rules were frozen before the results were known ([`analysis_spec.md`](analysis_spec.md)).

## 1. Sample size is the dominant limitation

- **Two games per team.** Auburn's profile rests on 134 offensive snaps and Florida's on 95 defensive snaps outside garbage time. The main-map cells hold 13 to 54 plays per team; most fine down × distance cells hold fewer than 8 and are hidden.
- **Two games predict little.** Across 664 FBS team-seasons from 2021 to 2025, a team's regular-season Weeks 1–2 residual in a situation correlated with its rest-of-season residual at −0.01 to 0.24. Shrinkage keeps about 1–12% of a 2026 cell's raw signal. Raw two-game numbers, including the "raw" values printed in figures V1–V3, are mostly noise.
- **A code error was found and fixed before publication.** The first reliability test counted bowl games, which the play-by-play numbers week 1, as early season. The fix is spec change log #15. It changed the reliability numbers but no gate, label, or decision.
- **Many comparisons.** Eight findings, each with up to 10 checks, invite a lucky pattern. The situations were fixed in advance, labels require every check to pass, and at most three takeaways may be published, but none of that makes a single finding significant.

## 2. Uncertainty is understated, not overstated

- **The 90% intervals are descriptive.** They come from a play-level bootstrap within each team's cell with the shrinkage factor held fixed. They ignore that plays within a game are correlated, uncertainty in k, and uncertainty in the baseline model. True intervals are wider. Labels never depend on them.
- **"Robust" means direction, not size.** A finding is robust if it keeps its sign under every applicable check. The three robust findings are each within 0.013 PPA per play (or 0.26 percentage points of explosive-play rate) of zero.
- **Heavy shrinkage makes every edge small.** With 2–12% of a raw residual kept, even a real two-game difference would appear as a small edge. The checks test whether a direction is stable. They cannot show that a matchup effect is large.

## 3. Opponents and context

- **"Expected" includes the betting line.** The spread prices in each team's own expected strength. A negative Auburn residual means Auburn fell short of what that game's line implied, not that its offense is below average. Florida's defensive residuals likewise measure Florida against lines that already made Florida the much stronger team (favored by 25.5 and 51.5 points).
- **Opponent strength enters only through the point spread.** The baseline uses each game's spread, venue, score, and clock, not opponent ratings. Florida's Campbell game carries a 51.5-point spread, beyond 99.6% of training plays, so the model is extrapolating there. Leave-one-game-out (check 6) is required for exactly this reason, and it removes several findings.
- **Garbage time is a rule of thumb.** The CFBD/Connelly score-margin rule removed 31% of Florida's defensive snaps against FAU, 44% against Campbell, and 28% of Auburn's against Southern Miss. Check 2 puts those plays back.
- **Hidden football context.** Public play-by-play has no formations, personnel, motion, coverage, pressure, blocking assignments, audibles, injuries, or the actual play call. Nothing here identifies why a play worked or what a coach should call.
- **Run and pass are choices.** Coaches choose them in response to the defense, score, and personnel, so residuals by play type describe associations, not the effect of calling a run or a pass.

## 4. Baseline model

- **Pre-snap context explains little of any single play** (PPA R² ≈ 0.05 on 2025). The baseline removes situational bias; it does not predict individual plays.
- **Ridge leaves some situational bias.** On 2025, the chosen ridge model's average group bias was 0.078 PPA per play, against 0.028 for XGBoost. The frozen selection rule still chose ridge because XGBoost's accuracy gain (0.44% MAE) was under the 1% bar. Check 10 requires each finding to hold under XGBoost as well.
- **Early-season drift.** League-wide, early 2026 offenses ran 0.016 PPA per play and 6% of explosive plays below the full-season baseline. 2025 Weeks 1–2 looked the same, and neither crossed the frozen correction threshold. After shrinkage, this moves each edge by about −0.001 PPA per play against Auburn, about a tenth the size of the robust findings. It is uncorrected.
- **Shrinkage history comes from other teams and staffs.** k is learned from 2021–2025 team-seasons. It assumes two early games say about as much about a 2026 team as they did about past teams. A team with a new staff and roster could be more or less predictable than that history. Fine down × distance cells borrow the k of their majority down group.

## 5. Data quality

- **Legacy text in training seasons.** Kneel detection finds 10–12 per 1,000 runs in 2021–2022 against about 17 from 2023 on, so a few hundred kneels likely remain in each of those seasons. Text before 2025 does not identify spikes, so roughly 70 per season remain. The 2023–2025 sensitivity baseline (check 1) excludes 2021–2022.
- **Yardage vs. official box scores.** Play-by-play total yards exceed official totals by 25 (Auburn) and 19 (Baylor) in Week 1 and by 32 (Southern Miss) in Week 2. Most of each gap is yards on accepted-penalty snaps, which are outside the model sample; what remains is 12 yards or less per offense. Scores, plays, pass attempts, and interceptions match official records within one.
- **CFBD has since revalued possession-change plays.** The frozen PPA matches CFBD's live `/plays` on every non-turnover play in the four games, but not on interceptions, lost fumbles, or turnovers on downs. CFBD's live PPA totals and advanced team stats will therefore differ from this project's numbers.
- **Unflagged snaps.** The 2025 and 2026 builds typed some real snaps, including lost fumbles, as fumbles or penalties with no run or pass flag. Cleaning recovers them from the play text (297 in 2026). Any it misses would be absent from the profiles.

## 6. Reproducibility

- **Raw data is not in Git.** SportsDataverse and CFBD update in season, and team websites change. The manifest records each file's source, parameters, download time, size, and SHA-256 hash.
- **A fresh clone may not be able to reproduce the snapshot exactly.** `src/ingest.py` checks every file, present or downloaded again, against its recorded SHA-256 hash and stops if one changed. If an upstream source has been corrected since September 16, the ingest fails loudly rather than silently using new data. Running it with `--refresh` accepts the new version, and results may then differ.
- **Figures depend on installed fonts.** They use Helvetica Neue where available and fall back to other sans-serif fonts. The numbers do not change, but the layout can shift slightly on other machines.

## 7. What the backtest does and does not establish

- The edge predicts the offense's result **against this project's baseline**, not against the market. On 3,189 games with a closing line, the correlation with the result relative to that line is +0.004 (interval −0.031 to +0.037).
- Predictable residuals can mean the baseline misses real team quality, or that the baseline has persistent blind spots. This analysis cannot separate the two.
- The backtest scores team-level edges pooled over all plays. The frozen matchup findings are situation-level cells of 13 to 54 plays, where the signal is weaker still.

## 8. What this project does not claim

- It does not predict the score or the winner.
- It does not say where Auburn has an edge on Florida. Under the frozen rules, no situation qualifies.
- It does not describe the 2026 teams using 2025 or earlier team data.
- It is not affiliated with Auburn Athletics or Florida Athletics, and it uses no private film, personnel, injury, or play-call information.
