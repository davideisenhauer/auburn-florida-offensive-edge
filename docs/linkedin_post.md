# LinkedIn post draft (option 2: pregame, no matchup claims)

**Status:** draft for the author to review and publish. Nothing has been posted.
**Rule it follows:** the frozen no-claims decision ([`go_no_go.md`](go_no_go.md)) and spec change log #14. The post makes no situational matchup claim. It explains what two games of data can and cannot separate.
**Adapted from:** plan section 20 (title, one-sentence explanation, disclaimer).

---

## Post

**Looking for Auburn's offensive edge against Florida: what two games of data can (and can't) tell you**

Auburn hosts Florida on Saturday. As an Auburn student, I went looking in the play-by-play for where Alex Golesh's offense might have an edge on Jon Sumrall's defense. The most useful thing I found was how little two games can tell you.

Instead of predicting the final score, I built a league-wide baseline to find where Auburn's offense has created more value than expected, where Florida's defense has allowed more value than expected, and where those patterns overlap. Before I looked at a single Auburn or Florida result, I wrote down the rules for what would count as a finding.

What I built:
• 612,758 cleaned FBS snaps from 2021–2026, using predicted points added (PPA) and 20+ yard plays as the measures
• Pre-snap baseline models, tested once on the 2025 season before being used
• A reliability test on 664 past team-seasons: how much should two games really count?
• Up to 10 robustness checks per finding, including dropping each game and removing the single most influential play

What the data said:
1. Two games are mostly noise. A team's first two games in a situation barely predicted the rest of its season (correlations of 0.24 or less). The best prediction put only 2–11% of the weight on those two games and the rest on the league average.
2. I tested 4 broad situations, 2 ways each. None of the 8 findings showed a clear signal. The only one leaning Auburn's way disappeared when I removed one 12-yard run.
3. The patterns that held up under every check were tiny: about a hundredth of a point per play, or a quarter of a percentage point in explosive-play rate.

So my own rules say no pregame matchup claims, and I'm sticking to them. That was the hardest part. When you're rooting for a result, it's tempting to find one. The honest answer after two games is "not enough information yet," and saying that clearly is part of doing analytics well.

One more thing I'm glad I checked: a final code review caught a bug. Bowl games were being counted as early-season games. Fixing it changed the reliability numbers but not the conclusion, and the fix is documented in the repo.

The code, frozen data manifest, decision memo, and limitations are on GitHub: https://github.com/davideisenhauer/auburn-florida-offensive-edge

This is an independent analysis using public play-by-play data. It is not affiliated with Auburn Athletics or Florida Athletics, and it does not account for private film, personnel, injury, or play-call information. Data through Sept. 12, 2026.

War Eagle.

#CollegeFootball #SportsAnalytics #DataScience #Python #WarEagle

---

## Images, in order

| # | File | Alt text |
|---|---|---|
| 1 | `outputs/figures/v5_two_game_reliability.png` | Dot chart titled "Two games are mostly noise." For 16 situation types, the weight a team's first two games deserve in predicting the rest of its season ranges from 2% to 11%, far below 100%. Correlations are 0.24 or less. |
| 2 | `outputs/figures/v4_opportunity_map.png` | Scatter plot titled "Auburn offense vs. Florida defense: no clear signal." Four situations plotted by PPA edge and explosive-play edge, all clustered near zero with 90% intervals. Seven of eight intervals include zero. |
| 3 | `outputs/figures/v1_auburn_offense_ppa.png` | Heatmap of Auburn's 2026 offense, PPA over expected by down, distance, and run or pass. Most cells are hidden for having fewer than 8 plays; shown values after shrinkage range from −0.017 to +0.004 per play. |
| 4 | `outputs/figures/v2_florida_defense_ppa.png` | Heatmap of Florida's 2026 defense, PPA allowed over expected, same layout. Shown values after shrinkage range from −0.004 to +0.002 per play. |
| 5 | `outputs/figures/v3_explosive_plays.png` | Dot chart of explosive-play rates, observed vs. expected, for Auburn's offense and Florida's defense in four situations, with play counts and shrunk differences. |

LinkedIn crops single images in the feed. With five images, the first two appear largest, so lead with V5 and V4. To post fewer, keep V5 and V4 and leave the rest in the repo.

## Before posting

- [ ] Open the repository link in a private window to confirm it is public.
- [ ] Optional: cut the bug-fix paragraph if the post feels long. It is accurate, and it shows the checking process.
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
