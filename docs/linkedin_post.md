# LinkedIn post draft (option 2: pregame, no matchup claims)

**Status:** draft for the author to review and publish. Nothing has been posted.
**Rule it follows:** the frozen no-claims decision ([`go_no_go.md`](go_no_go.md)) and spec change log #14. The post makes no situational matchup claim. It explains what two games of data can and cannot separate.
**Adapted from:** plan section 20 (title, one-sentence explanation, disclaimer), rebuilt around the backtest and supporting analysis in [`insights.md`](insights.md).

---

## Post

**What two games of college football data can (and can't) tell you**

I went looking for where Auburn's offense might have an edge on Florida's defense this Saturday. The search turned into a better question: does this kind of early-season edge predict anything at all?

So I tested it. League-wide baseline built from 612,758 FBS snaps (2021–2026). Then, for every FBS-vs-FBS game from 2021 to 2025, rebuild each team's edge from that season's earlier games only and check it against what actually happened in the game.

1. The edge is real.
Sort the games into ten groups by the edge before kickoff and offenses finish in order, every group. Bottom group: 0.094 points per play below the baseline. Top group: 0.082 above. That gap is about 12 points over a full game. Correlation +0.23 across 6,368 matchup sides, and +0.24 when the baseline has never seen the season it is scoring.

2. Taken at face value, it is worse than nothing.
At two games in — exactly where we are now — the unshrunk edge predicts the game 4.4% worse than assuming every team is league average. Discount it toward the average and it turns useful (1.1% better). Same number, same direction. The scale is the whole story.

3. It tells you nothing the betting market hasn't already priced.
A 12-point effect, and the same edges against the closing spread on 3,189 games give: correlation +0.004, 95% interval −0.03 to +0.04. Beat-the-line rate by group: 47%, 49%, 50%, 51%, 48%. Whatever my model finds, the market already knew.

So what can two games actually tell you? What a team chooses to do. Pass rate is 59% settled after two games — Auburn's is 48.5%, right at league-median balance. How good a team is, they cannot tell you: 124 of 138 FBS offenses could still be a top-25 offense, and Auburn's own range runs from 24th to 136th. Panic and hype are equally unsupported.

My rules, written down before I looked at a single Auburn or Florida result, said that meant no pregame claims. The backtest says something stronger: even a well-measured edge of this kind would not be worth publishing as a prediction.

Rooting for a result makes it tempting to find one. Saying "the data cannot carry that" is the job.

Code, frozen data manifest, decision memo, and limitations: https://github.com/davideisenhauer/auburn-florida-offensive-edge

This is an independent analysis using public play-by-play data. It is not affiliated with Auburn Athletics or Florida Athletics, and it does not account for private film, personnel, injury, or play-call information. Data through Sept. 12, 2026.

War Eagle.

#CollegeFootball #SportsAnalytics #DataScience #Python #WarEagle

---

## Images, in order

| # | File | Alt text |
|---|---|---|
| 1 | `outputs/figures/v9_backtest.png` | Two panels. Left: by decile of the pre-kickoff matchup edge, what the offense actually did against the baseline, rising monotonically from −0.094 to +0.082 points per play, correlation +0.23. Right: the same edge against the result relative to the closing point spread, showing no relationship, correlation +0.004. |
| 2 | `outputs/figures/v6_reliability_spectrum.png` | Bar chart of how many games each measure needs before a team's own number is worth as much as the league average: pass rate 1.4, success rate and PPA per play 6.4, explosive-play rate 10.1, PPA over expected 10.7, explosive rate over expected 17.0. |
| 3 | `outputs/figures/v7_rank_intervals.png` | Every FBS offense's plausible national rank range after two games. The median line covers 118 of 138 places, 124 of 138 could still be top 25, and Auburn's range runs from 24th to 136th around an estimate of 126th. |
| 4 | `outputs/figures/v8_pairing_distribution.png` | Histogram of the largest situational edge across all 18,906 FBS offense–defense pairings, with Auburn–Florida at 0.013 against a median of 0.017. |
| 5 | `outputs/figures/v4_opportunity_map.png` | Auburn offense versus Florida defense: four situations by PPA edge and explosive-play edge, all near zero, seven of eight 90% intervals including zero, all labelled "no clear signal." |

LinkedIn shows the first two images largest, so lead with V9 and V6. To post fewer, keep V9 and V7. V1, V2, V3, and V5 stay in the repository as supporting detail.

## Before posting

- [ ] Open the repository link in a private window to confirm it is public.
- [ ] Optional: add a line about the bug caught in final review (bowl games counted as early-season games). It is accurate and shows the checking process, but the post is already long.
- [ ] Add your personal branding line, if you want one. It can also go in `BYLINE` in `src/visuals.py`, followed by a rerun of `python -m src.visuals`.
- [ ] Post after the final figures are regenerated. Don't edit numbers by hand.
- [ ] In comments, keep to the same rule. If someone asks where Auburn should attack, the honest answer is that two games of public play-by-play can't separate that from noise.
- [ ] Saturday: no model changes. Correct only verified factual errors.

## Why the wording avoids some phrases

| Avoided | Reason |
|---|---|
| Naming a situation as an Auburn edge or weakness | The frozen decision allows no situational matchup claims before the game |
| "Auburn's offense has struggled" | True of the raw two-game numbers, but the post's own point is that two games are mostly noise |
| "EPA" | The analysis uses CFBD PPA; cfbfastR EPA changed models in 2026 |
| "Predicts," "should," "attack," "target" | No prediction or play-calling recommendation is supported |
