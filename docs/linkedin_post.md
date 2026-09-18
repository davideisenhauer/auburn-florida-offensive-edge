# LinkedIn post draft (option 2: pregame, no matchup claims)

**Status:** draft for the author to review and publish. Nothing has been posted.
**Rule it follows:** the frozen no-claims decision ([`go_no_go.md`](go_no_go.md)) and spec change log #14. The post makes no situational matchup claim. It explains what two games of data can and cannot separate.
**Adapted from:** plan section 20 (title, one-sentence explanation, disclaimer), rebuilt around the supporting analysis in [`insights.md`](insights.md).

---

## Post

**What two games of college football data can (and can't) tell you**

I went looking for where Auburn's offense might have an edge on Florida's defense on Saturday. I didn't find one. What I found instead was a measurable answer to a better question: after two games, what can you actually know?

I built a league-wide baseline from 612,758 FBS snaps (2021–2026), measured every team against it, and tested how much a team's first two games really said about the rest of that same season.

What two games CAN tell you: identity.
• After two games, the best estimate of a team's pass rate is 59% its own number and 41% league average. Its own number is worth as much as the league average after just 1.4 games.
• Auburn's: 48.5% pass overall, 42.6% on standard downs, right at league-median balance. That is a real fact about this offense.

What two games CAN'T tell you: quality.
• Explosive-play rate needs about 10 games to clear that same bar. Opponent-adjusted efficiency needs 11, adjusted explosiveness 17. After two games those estimates are still 83–89% league average.
• Right now, 124 of 138 FBS offenses could still be a top-25 offense. Auburn's own range runs from 24th to 136th. Panic and hype are equally unsupported.
• One play moves the median team's two-game average by 0.045 points per play, more than three times the largest edge I could find in this matchup.

The part that surprised me:
Two-game splits taken at face value are worse than no information at all. Tested across five seasons, they predicted the rest of the season 75% worse than simply assuming every team is league average. Shrink them toward that average and they beat it by 9%. The September stat line isn't just noisy, it's actively misleading.

And the matchup? Across all 18,906 FBS offense–defense pairings this season, Auburn–Florida's biggest situational edge is smaller than 72% of them. My rules, written down before I looked at a single Auburn or Florida result, said that meant no pregame claims. So I'm making none.

Rooting for a result makes it tempting to find one. Saying "two games can't tell you that" is part of the job.

Code, frozen data manifest, decision memo, and limitations: https://github.com/davideisenhauer/auburn-florida-offensive-edge

This is an independent analysis using public play-by-play data. It is not affiliated with Auburn Athletics or Florida Athletics, and it does not account for private film, personnel, injury, or play-call information. Data through Sept. 12, 2026.

War Eagle.

#CollegeFootball #SportsAnalytics #DataScience #Python #WarEagle

---

## Images, in order

| # | File | Alt text |
|---|---|---|
| 1 | `outputs/figures/v6_reliability_spectrum.png` | Bar chart titled "What two games can and can't tell you about an offense." Pass rate needs 1.4 games to be worth as much as the league average; success rate and PPA per play need 6.4; explosive-play rate 10.1; PPA over expected 10.7; explosive rate over expected 17.0. |
| 2 | `outputs/figures/v7_rank_intervals.png` | Every FBS offense's plausible national rank range after two games. The median line covers 118 of 138 places, 124 of 138 offenses could still be top 25, and Auburn's range runs from 24th to 136th around an estimate of 126th. |
| 3 | `outputs/figures/v8_pairing_distribution.png` | Histogram of the largest situational PPA edge for all 18,906 FBS offense–defense pairings. The median pairing is 0.017 and Auburn–Florida is 0.013, smaller than 72% of pairings. |
| 4 | `outputs/figures/v4_opportunity_map.png` | Scatter plot titled "Auburn offense vs. Florida defense: no clear signal." Four situations plotted by PPA edge and explosive-play edge, all near zero, seven of eight 90% intervals including zero. |
| 5 | `outputs/figures/v1_auburn_offense_ppa.png` | Heatmap of Auburn's 2026 offense, PPA over expected by down, distance, and run or pass. Most cells are hidden for having fewer than 8 plays; shown values after shrinkage run from −0.017 to +0.004 per play. |

LinkedIn shows the first two images largest, so lead with V6 and V7. To post fewer, keep V6 and V7 and leave the rest in the repo. V2, V3, and V5 stay in the repository as supporting detail.

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
