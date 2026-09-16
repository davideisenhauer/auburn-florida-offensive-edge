# Auburn vs. Florida: Finding the Offensive Edge

> **The analysis spec supersedes this plan.** [`docs/analysis_spec.md`](docs/analysis_spec.md) is the frozen, binding specification. Wherever the two differ, the spec wins, and its change log (section 10) records each change with its reason and date.
>
> On September 18, 2026, this plan was updated for the three largest changes: CFBD PPA replaces cfbfastR EPA throughout (reasoning in section 5), garbage time uses the CFBD/Connelly score-margin rule instead of win probability (sections 8 and 11), and the play-by-play source is the `cfbfastR_cfb_pbp` release instead of `espn_cfb_pbp` (sections 4, 7, 8, 13, and the source list). Other differences are recorded only in the spec. They include the refit on 2021–2025, the 2026 environment check, operational gate definitions, and robustness check 10.

## Final research and implementation plan

**Prepared:** September 16, 2026  
**Target release:** Friday, September 18, 2026, before the Saturday game  
**Game:** Saturday, September 19, 2026, at 6:00 p.m. CT on ESPN at Jordan-Hare Stadium  
**Project type:** Auburn football, sports analytics, and portfolio project 
(to be posted on LinkedIn) 

## 1. Final decision

We should build this project.

The final version should answer one focused question:

> **After accounting for normal game context, where has Auburn's offense created more value than expected, where has Florida's defense allowed more value than expected, and where do those two patterns overlap?**

The project will combine two outcomes:

1. Predicted points added, or PPA, on a play (CFBD's expected-points model; see section 5)
2. The probability of an explosive play of 20 or more yards

The project will not predict the final score, claim to know Auburn's playbook, or present the model as an offensive coordinator. It will identify situations that look favorable in the public play-by-play data.

That distinction is important. Public data does not include defensive coverage, personnel packages, formations, motion, blocking assignments, audibles, player health, or the actual play call. The project can find historical matchup signals, but it cannot prove that a specific play call will work.

## 2. Why the original proposal needs one improvement

Auburn and Florida have each played only two games in 2026. Raw splits such as "Auburn averages X PPA on second down" would be unstable and misleading. The opponents have also been different. Auburn has played Baylor and Southern Miss. Florida has played Florida Atlantic and Campbell. A raw comparison would mix team ability, opponent quality, game state, and small-sample noise.

The better design is a three-layer model:

1. Build a league-wide baseline for what normally happens in a given situation.
2. Measure how Auburn's offense and Florida's defense performed relative to that baseline.
3. Combine those residual patterns only when the sample is large enough to support a finding.

This creates an opponent and situation adjusted profile without pretending that two games provide certainty.

## 3. Exact scope

### Version one includes

- FBS scrimmage plays from recent seasons
- Run and pass play families
- Pre-snap game context
- PPA as the continuous outcome
- A 20-plus-yard explosive-play outcome
- Auburn's 2026 offensive plays through Week 2
- Florida's 2026 defensive plays through Week 2
- A matchup opportunity map
- Uncertainty, sample counts, and reliability labels
- Four polished graphics
- A reproducible Python repository and notebook
- A LinkedIn post and concise methodology summary

### Version one does not include

- Tempo optimization
- Live in-game recommendations
- Final-score or win prediction
- Formation, personnel, coverage, or film analysis
- Player-level matchup claims
- A large Streamlit application
- A causal claim that passing or running caused a better outcome

Tempo should remain a separate project. Auburn has only two games under Alex Golesh, and tempo introduces extra timing, clock, and substitution issues that would weaken this release.

The Drive Killer idea can appear as one optional supporting chart only if the core project is finished and validated first.

## 4. Data-source recommendation

### Best primary source: SportsDataverse cfbfastR bulk play-by-play

The strongest primary source is the [SportsDataverse `cfbfastR_cfb_pbp` play-by-play release](https://github.com/sportsdataverse/sportsdataverse-data/releases/tag/cfbfastR_cfb_pbp): CollegeFootballData plays processed by cfbfastR. The ESPN-sourced `espn_cfb_pbp` release was rejected on September 16 because its 2026 games were stale mid-game snapshots (spec change log #1; [`docs/data_sources.md`](docs/data_sources.md)). The release provides one Parquet file per season and can be loaded directly in Python without an API key.

Why it is the best fit:

- It is built for bulk analysis rather than one request at a time.
- The schema has 362 fields per play in every season from 2021 to 2026.
- It includes the pre-snap situation, run and pass flags, sacks, penalties, turnovers, CFBD's play-level PPA, and many derived football fields. It also carries cfbfastR EPA and win probability, which this project does not use (section 5).
- The 2026 Parquet file was present and refreshed before this plan was completed.
- Parquet is smaller and faster than CSV, and it supports reading only the columns we need.
- The public data pipeline and [field-level data dictionary](https://github.com/sportsdataverse/cfbfastR-cfb-data/blob/main/DATASETS.md) are visible on GitHub.

The frozen 2026 Parquet asset is about 27 MB (downloaded September 16). The release itself is updated during the season. Because the asset can change when new games or corrections arrive, we must download a local snapshot and record its timestamp, size, and SHA-256 hash before analysis.

### Best supplemental API: CollegeFootballData

[CollegeFootballData](https://api.collegefootballdata.com/getting-started) is the best supplemental API. It has official Python client documentation and covers raw plays, advanced team statistics, ratings, betting lines, weather, rosters, and newer enriched passing and rushing endpoints.

The current access options are favorable for a student project:

| Tier | Cost | Monthly calls | Relevant use |
|---|---:|---:|---|
| Free | $0 | 1,000 | Testing and core historical endpoints |
| Academic | $0 with a verified .edu email | 3,000 | Best choice for this project |
| Tier 1 | $1 per month | 5,000 | Adds opponent-adjusted metrics, weather, and live scoreboard access |
| Tier 2 | $5 per month | 30,000 | Adds live play-by-play, which version one does not need |

The current limits and benefits are listed on the [CFBD API tiers page](https://collegefootballdata.com/api-tiers).

We should request the free Academic key using the Auburn email. We do not need to pay for Tier 2.

### CFBD endpoints worth using

| Endpoint | Purpose | Required for version one? |
|---|---|---|
| [`/games`](https://api.collegefootballdata.com/api/games) | Game IDs, teams, dates, locations, and completed-game checks | Yes, as a cross-check |
| [`/plays`](https://api.collegefootballdata.com/api/plays) | Raw play-by-play with PPA | Backup only |
| [`/stats/game/advanced`](https://api.collegefootballdata.com/api/stats) | Game-level PPA, success, explosiveness, havoc, field position, and line yards | Yes, for sanity checks |
| [`/passing/plays`](https://api.collegefootballdata.com/api/passing) | Air yards, pass depth, pass direction, YAC, PPA, and parse status | Optional supporting analysis |
| [`/rushing/plays`](https://api.collegefootballdata.com/api/rushing) | Rush direction, rusher attribution, sacks, kneels, yards, PPA, and parse status | Optional supporting analysis |
| `/lines` | Pregame spread for opponent-strength and game-context checks | Optional but useful |
| `/ratings/core` or `/ratings/sp` | Team-strength context | Optional and dependent on account entitlement |
| `/games/weather` | Game weather | Not needed for version one |

CFBD reports raw play coverage from 2001 to the present and PPA coverage from 2001 to the present. The newer enriched passing and rushing fields begin in 2025. Coverage can vary by game and field, and the current season is incomplete while games are being played. Those limitations are stated in the [CFBD data-availability guide](https://api.collegefootballdata.com/data-availability).

### Sources that should not control the project

| Source | Decision | Reason |
|---|---|---|
| Direct, undocumented ESPN endpoints | Fallback only | Useful, but endpoints and schemas can change without notice |
| NCAA statistics pages | Validation fallback | Official, but awkward for reliable bulk play-by-play work |
| Kaggle datasets | Do not use as the source of truth | Freshness, lineage, and transformation quality vary by uploader |
| SportsDataIO, Sportradar, Stats Perform, PFF, or TruMedia | Not required | Potentially richer, but paid access is unnecessary for this version |
| Weather APIs | Exclude | Weather does not answer the core question and adds noise before the forecast is stable |

Paid charting or tracking data would materially improve formation, route, coverage, and pressure analysis. It is not required to produce a strong public project.

## 5. Data consistency rule

EPA and PPA are related, but they are not interchangeable. CFBD also warns that its different models should not be compared on the same scale and that model versions can affect comparisons. See the [CFBD methodology overview](https://api.collegefootballdata.com/methodology-overview).

Therefore:

- The main model uses CFBD PPA, the `ppa` column of the frozen `cfbfastR_cfb_pbp` files, for every historical and current-season play.
- cfbfastR EPA, expected points, and win probability are not used anywhere.
- CFBD's live aggregates are used only as approximate, independent sanity checks, and live CFBD play data is never mixed into the frozen table.
- EPA and PPA are never spliced together.

**Why PPA and not EPA.** This plan originally chose cfbfastR EPA and named a full rebuild on CFBD PPA as the fallback. The data audit triggered that fallback. The 2026 file was built with cfbfastR's new 3.0 expected-points model, while 2021–2025 used the previous model, so identical situations get different EPA in 2026. For example, an incompletion on 1st and 10 at midfield is worth about −0.79 EPA in 2021–2025 and −0.38 in 2026. The `ppa` column gives identical situations identical values in every season. Evidence is in spec section 4 (change log #2).

This rule prevents a subtle but serious source mismatch.

## 6. Exact data we need

### Historical training data

Use FBS regular-season and postseason scrimmage plays from 2021 through 2025.

Recommended split:

- Train: 2021 through 2024
- Final untouched test set: 2025
- Matchup scoring data: 2026 through Week 2

This is recent enough to reflect modern college football while providing far more data than the two current-season games. A sensitivity check will repeat the model using only 2023 through 2025 because the college-football clock rules changed in 2023.

### Current matchup data

- All Auburn offensive scrimmage plays from the 2026 Baylor and Southern Miss games
- All Florida defensive scrimmage plays from the 2026 Florida Atlantic and Campbell games
- The opponent, game ID, week, final score, and play count for every included game

The official [Auburn schedule](https://auburntigers.com/sports/football/schedule?print=true) confirms that Auburn is 2-0 through two games and hosts Florida on September 19. Auburn and Florida list the kickoff as 6:00 p.m. CT and 7:00 p.m. ET on ESPN. The [Auburn kickoff announcement](https://auburntigers.com/news/2026/05/27/kickoff-times-tv-networks-announced-for-first-three-games) and [Florida broadcast information](https://floridagators.com/news/2026/9/14/football-broadcast-information-florida-vs-auburn) agree.

### Required columns

Only pre-play fields may enter the predictive feature set.

| Group | Fields |
|---|---|
| Identity | `game_id`, `id`, `season`, `week`, offense team, defense team |
| Situation | down, distance, yards to end zone, period, game clock, score differential at play start |
| Context | home or away, goal-to-go, red zone, time remaining, pregame spread if available |
| Decision | run or pass play family |
| Outcomes | PPA, yards gained, explosive-play flag |
| Cleaning | scrimmage-play flag, penalty flags, no-play flag, sack, spike, kneel, turnover, duplicate flag |

Post-play score, ending field position, yards gained, completion, turnover, and next-play fields must never enter the model as predictors. They are outcomes or information that was not available before the snap.

## 7. Data collection and versioning plan

1. Download the 2021 through 2026 Parquet files from the SportsDataverse `cfbfastR_cfb_pbp` release.
2. Save the raw files unchanged under `data/raw/`.
3. Record the source URL, download time, byte size, and SHA-256 hash in `data_manifest.csv`.
4. Store the exact analysis cutoff as `2026-09-12`, the date of the last completed games included.
5. Retrieve CFBD game and advanced-stat records for the four 2026 games.
6. Save every API response as raw JSON before transformation.
7. Never commit the API key. Read it from `CFBD_API_KEY` in a local environment file that is ignored by Git.
8. Create one processed play table with a documented schema and deterministic filters.

The data manifest matters because the current-season release can be refreshed or corrected after we publish.

## 8. Data-quality gates

The modeling work cannot begin until the following checks pass.

### File and schema checks

- All six requested season files load successfully.
- Required columns exist in every season.
- Column types are consistent or deliberately coerced.
- Every record has a season, week, game ID, play ID, offense, and defense.
- Each play key is unique after the documented deduplication rule.

### Game reconciliation

- Auburn and Florida each have exactly two completed 2026 games in the cutoff.
- The four final scores match official team records.
- Team names and game IDs map correctly between the play-by-play (CFBD plays processed by cfbfastR) and CFBD.
- Play counts, turnovers, penalties, and team yardage are reasonably consistent with official box scores.
- Any discrepancy large enough to change a split is investigated before modeling.

### Play cleaning

Primary analysis should include normal offensive scrimmage plays and apply these rules:

- Remove kickoffs, punts, field goals, extra points, timeouts, quarter endings, and administrative rows.
- Remove duplicate play records.
- Remove plays explicitly marked as no-play because of a penalty.
- Keep accepted-penalty plays only in a separate sensitivity view unless the underlying action and PPA attribution are reliable.
- Treat sacks as pass plays.
- Remove quarterback kneels and intentional spikes from normal offensive efficiency.
- Keep turnovers because they are real outcomes, but report how much they influence the results.
- Require valid down, distance, field position, and PPA for the value model.
- Require valid yards gained for the 20-plus-yard explosive target.
- Flag overtime separately and exclude it from the primary model if the state representation is inconsistent.
- Flag garbage time with the CFBD/Connelly rule: the score margin at the snap exceeds 43 points in the 1st quarter, 37 in the 2nd, 27 in the 3rd, or 22 in the 4th. Baseline training keeps these plays; the Auburn and Florida team profiles exclude them (section 11).

### Missingness and parse checks

- Report missingness by field, season, and team.
- Do not convert missing PPA, success, or direction values to zero.
- Use CFBD pass and rush direction only when `parseStatus` and eligibility flags are acceptable.
- If more than 10 percent of a required current-team field is missing, drop that field from the public analysis rather than impute a result that could drive the conclusion.

## 9. Modeling design

### Model A: league expected PPA

The first model estimates the PPA normally associated with a play before the snap.

**Target**

`ppa`

**Predictors**

- Run or pass
- Down
- Distance
- Yards to the end zone
- Quarter
- Seconds remaining in the half or game
- Offense score differential before the play
- Home or away
- Goal-to-go
- Pregame spread if available
- Limited, predeclared interactions such as down by distance and play family by field position

**Models to compare**

1. Regularized linear regression as the transparent baseline
2. Gradient-boosted trees as the flexible candidate

The boosted model must beat the baseline on the untouched 2025 test set by a meaningful amount. If it does not, use the simpler model.

Recommended evaluation:

- Mean absolute error
- Root mean squared error
- Mean error by down, distance bin, field-position bin, play family, and season
- Residual plots
- Stability across 2025 weeks

### Model B: explosive-play probability

**Primary target**

`explosive_20 = 1 if yards gained >= 20, otherwise 0`

**Sensitivity target**

- Pass gain of 20 or more yards
- Rush gain of 10 or more yards

The second definition is common in football analysis, but using it only as a sensitivity check keeps the public headline easy to understand and prevents us from changing definitions after seeing results.

**Models to compare**

1. Regularized logistic regression
2. Gradient-boosted classifier

Recommended evaluation:

- Average precision and the precision-recall curve
- ROC-AUC as a secondary metric
- Log loss
- Brier score
- Calibration curve
- Observed versus predicted explosive rate by probability decile

Accuracy should not be treated as the main metric because a model can look accurate by predicting almost every play as non-explosive. Scikit-learn's [model-evaluation documentation](https://scikit-learn.org/stable/modules/model_evaluation.html) covers average precision, Brier score, and calibration-related evaluation.

### Validation design

Randomly splitting individual plays would leak information from the same games into training and testing. The split must be chronological and game-aware.

- Train on 2021 through 2024.
- Tune only inside the training period using season and week blocks.
- Test once on all 2025 games.
- Do not tune after looking at 2025 test performance.
- Keep every play from one game in the same fold.
- Use early stopping on a validation block for boosted models.
- Compare performance with and without pregame spread.

If performance varies sharply by season or the boosted model is poorly calibrated, the output will fall back to grouped descriptive estimates with shrinkage rather than forcing a machine-learning result.

## 10. Turning the models into a matchup analysis

### Step 1: Calculate expected outcomes

For every 2026 Auburn offensive play and Florida defensive play, calculate:

- Predicted PPA from the league model
- Predicted probability of a 20-plus-yard gain
- Actual PPA
- Actual explosive outcome

### Step 2: Calculate residual value

For PPA:

`PPA over expected = actual PPA - predicted PPA`

For explosive plays:

`Explosive over expected = actual explosive outcome - predicted probability`

Positive Auburn offensive residuals mean Auburn created more than the situation normally produces. Positive Florida defensive residuals mean Florida allowed more offensive value than the situation normally produces.

### Step 3: Aggregate into predeclared situation cells

Use broad cells to avoid tiny, cherry-picked splits:

| Situation dimension | Bins |
|---|---|
| Down | First, second, third or fourth |
| Distance | Short 1-3, medium 4-7, long 8-plus |
| Field position | Own territory, midfield or opponent 49-21, red zone |
| Play family | Run, pass |

Do not build every possible cross-product. Start with down and distance by play family. Add field position only when the cell has enough plays.

### Step 4: Apply shrinkage and minimum samples

Current-team cell estimates must be pulled toward zero when the sample is small. A hierarchical or empirical-Bayes shrinkage method is preferred. The exact shrinkage strength should be selected from historical reliability tests, not chosen to create a more dramatic matchup.

Publication rules:

- Fewer than 8 relevant team plays: do not display the cell.
- 8 to 14 plays: display only as "limited sample" with no recommendation language.
- 15 or more plays: eligible for the main map, still with uncertainty.
- If almost every cell is below the threshold, roll up to broader early-down, passing-down, run, and pass groups.

### Step 5: Combine Auburn and Florida without fake precision

The hero graphic should not present an invented 0-to-100 score as if it were a probability.

Use a two-dimensional opportunity map:

- Horizontal axis: matchup PPA edge
- Vertical axis: matchup explosive-play edge
- Bubble size: usable sample size
- Bubble opacity or outline: reliability tier

The matchup edge in a cell is the average of the shrunk Auburn offense residual and the shrunk Florida defense-allowed residual. Both components will also be visible in the supporting table.

Opportunity labels:

- **Strongest signal:** Auburn and Florida components point in the same favorable direction, sample threshold is met, and the result survives sensitivity checks.
- **Possible signal:** Direction is favorable, but uncertainty remains high.
- **No clear signal:** Components disagree, the interval crosses zero widely, or the sample is inadequate.

This is more honest and more interesting than a single unexplained score.

## 11. Uncertainty and robustness checks

Use game-clustered bootstrap resampling for historical validation and play-level bootstrap resampling within the four current games only as a descriptive sensitivity check. With two games per team, confidence intervals will be wide. That is an expected result, not a failure.

Every headline finding must pass these checks:

1. Same direction with the 2021-2024 model and the 2023-2025 sensitivity model
2. Same direction when garbage-time plays are included (the team profiles exclude them)
3. Same direction when accepted-penalty plays are excluded
4. Same direction with and without turnovers
5. Same direction under the alternate explosive-play definition
6. Not driven by one play alone
7. Minimum sample rule is met

Garbage time follows CFBD and Bill Connelly: the score margin at the snap exceeds 43 points in the 1st quarter, 37 in the 2nd, 27 in the 3rd, or 22 in the 4th. The Auburn and Florida team profiles exclude those plays, and check 2 reports every finding with them included, so the filter is transparent. This replaces the original win-probability filter (second-half plays below 5 percent or above 95 percent) because cfbfastR's win-probability model also changed in the 2026 file (spec change log #3).

If a finding fails two or more checks, it should not become a LinkedIn headline.

## 12. Four final visuals

### Visual 1: Auburn offense over expected

A heatmap of Auburn PPA over expected by play family and situation. Every cell includes the number of plays. Cells below the display threshold remain blank.

### Visual 2: Florida defense allowed over expected

The same structure for Florida's defense. The color direction must be written from Auburn's perspective so readers do not have to reverse the meaning.

### Visual 3: Explosive-play overlap

A comparison of Auburn's explosive rate over expected and Florida's explosive rate allowed over expected. Show observed, expected, difference, and sample size.

### Visual 4: Auburn offensive opportunity map

The hero graphic showing where the two team profiles overlap. It should contain no more than three labeled takeaways and should visibly distinguish a strong signal from a limited-sample watch area.

Optional fifth visual, only if time remains:

- Drive killers ranked by average PPA cost for Auburn, including sacks, turnovers, negative runs, and accepted penalties

## 13. What can go wrong and the response

| Risk | Why it matters | Response |
|---|---|---|
| Only two current games per team | Team splits can be random | Shrink estimates, show sample sizes, use broad cells, and refuse weak findings |
| Florida and Auburn faced different opponent quality | Raw averages are not comparable | Use league expected values, pregame spread sensitivity, and residuals |
| Both programs have new coaching contexts | Prior team seasons may be stale | Use prior seasons only to train the league baseline, not as direct 2026 team identity |
| Run and pass are chosen, not randomly assigned | The model can confuse selection with play value | Use association language, never causal play-calling language |
| Coverage, personnel, and formation are hidden | Public data omits important football information | State the limitation and avoid player or play-concept claims |
| EPA and PPA come from different models | Mixed targets corrupt comparisons | Use one metric family end to end (resolved: CFBD PPA for every season, section 5) |
| Post-play fields leak the answer | Model performance becomes fake | Maintain an approved pre-snap feature list and automated leakage test |
| Plays from one game enter multiple folds | Validation becomes optimistic | Split by season, week, and game |
| Explosive plays are uncommon | Accuracy becomes misleading | Use average precision, Brier score, and calibration |
| One turnover drives a cell | Average PPA becomes unstable | Run turnover and leave-one-game-out sensitivity checks |
| Penalties and no-plays are inconsistently coded | Team estimates can be distorted | Separate no-plays, accepted penalties, and normal snaps |
| Current release updates after download | Results cannot be reproduced | Freeze files and record hashes |
| API key or quota fails | Collection stops near the deadline | Make bulk Parquet the primary source and cache API JSON |
| API schema changes | Pipeline silently breaks | Validate required columns and fail loudly |
| Play-by-play, CFBD, and official-site identifiers differ | Joins can attach the wrong game | The `cfbfastR_cfb_pbp` files share CFBD game IDs and team names; match official box scores by opponent and reconcile scores |
| Current-season data arrives late | The most recent game may be missing | Verify four game IDs and scores before modeling |
| Multiple testing creates a lucky finding | A dramatic cell may be noise | Predeclare bins and restrict public takeaways to three |
| Model does not beat the baseline | Complexity adds no value | Publish the simpler model or grouped residual analysis |
| Model is poorly calibrated | Probabilities become misleading | Calibrate or stop calling outputs probabilities |
| Results find no strong Auburn edge | Project can feel anticlimactic | Publish the honest result and focus on what the data can and cannot separate |
| Visuals imply Auburn Athletics affiliation | Credibility and branding issue | Use Auburn colors carefully, avoid official logos, and add an independent-analysis note |
| Deadline causes rushed validation | A public error hurts more than a smaller project | Cut the optional analysis before cutting QA |

## 14. Go or no-go gates

### Go for the full matchup release if

- All four 2026 games are present and reconciled.
- The 2025 holdout performance beats the naive baseline.
- The explosive classifier is reasonably calibrated.
- At least two matchup cells meet the sample and robustness rules.
- The conclusion remains clear after turnover and garbage-time sensitivity checks.

### Release a simpler descriptive version if

- The models perform only marginally better than the baseline.
- Useful cells exist, but uncertainty is too high for rankings.

The simpler version would show opponent-adjusted PPA and explosive rates for broad run, pass, early-down, and passing-down groups.

### Do not publish matchup claims if

- A 2026 game is missing or materially inconsistent.
- One play drives the main finding.
- Results reverse under basic sensitivity checks.
- The only interesting cells have fewer than eight plays.

In that case, publish the project as a methodology build after the game rather than forcing a pregame conclusion.

## 15. Repository structure

```text
auburn-florida-offensive-edge/
├── README.md
├── requirements.txt
├── .gitignore
├── data/
│   ├── raw/
│   ├── interim/
│   ├── processed/
│   └── data_manifest.csv
├── notebooks/
│   ├── 01_data_audit.ipynb
│   ├── 02_baseline_models.ipynb
│   └── 03_matchup_analysis.ipynb
├── src/
│   ├── config.py
│   ├── ingest.py
│   ├── clean.py
│   ├── reconcile.py
│   ├── features.py
│   ├── models.py          # PPA value model and explosive-play models
│   ├── matchup.py
│   └── visuals.py
├── tests/
│   ├── test_cleaning.py
│   ├── test_features.py
│   └── test_no_leakage.py
├── outputs/
│   ├── figures/
│   ├── tables/
│   └── model_card.md
└── docs/
    ├── methodology.md
    ├── limitations.md
    └── linkedin_post.md
```

## 16. Recommended tools

- Python 3.12
- Pandas or Polars
- DuckDB for efficient Parquet queries
- PyArrow
- NumPy
- scikit-learn
- XGBoost only if it clearly beats the baseline
- Matplotlib and Seaborn for publication-quality static charts
- Plotly only if an interactive version is added later
- JupyterLab
- `cfbd` official Python package for supplemental API calls
- Pytest

DuckDB is useful because it can query selected Parquet columns without loading every field from every season into memory.

## 17. Work schedule

### Wednesday, September 16

- Freeze the project definition and situation bins.
- Create the repository and environment.
- Download and hash the six season files.
- Obtain the CFBD Academic key.
- Reconcile the four 2026 games.
- Complete the data audit and cleaning rules.

### Thursday, September 17

- Build the transparent baselines.
- Train and validate the boosted candidates.
- Score the 2026 plays.
- Create Auburn and Florida residual profiles.
- Run shrinkage, leave-one-game-out, turnover, penalty, and garbage-time checks.
- Make a go or no-go decision by Thursday night.

### Friday, September 18

- Finalize the four graphics.
- Write the README, model card, methodology, and limitations.
- Re-run the project from a clean environment.
- Verify every number in the public graphics against the exported table.
- Draft and publish the LinkedIn post Friday morning or early afternoon.

### Saturday, September 19

- No last-minute model changes.
- Correct only verified factual errors.
- Optionally share a short reminder before kickoff.

## 18. Definition of done

The project is complete only when all of the following are true:

- Raw sources are frozen and hashed.
- Data cutoff is written in the README.
- Four games are reconciled to official records.
- Cleaning rules are implemented and tested.
- No post-play fields enter the predictors.
- Validation is chronological and game-aware.
- Baseline and candidate models are compared on 2025.
- Explosive probabilities are evaluated for calibration.
- Every matchup cell shows a sample size.
- Weak cells are hidden or labeled.
- Sensitivity results are saved.
- Public findings are limited to what survives the checks.
- Four graphics use the same definitions and color direction.
- README contains sources, methods, limitations, and reproduction steps.
- Independent-analysis disclaimer is present.
- The project runs end to end from raw data to final figures.

## 19. What we need before implementation

Only one external item is required:

1. A CollegeFootballData API key, preferably the free Academic tier registered with an Auburn `.edu` email

Everything else can be built from public data and local Python tools.

Optional items:

- A GitHub repository name
- A preferred personal branding line for the graphics
- Confirmation on whether the final public title should be "Finding Auburn's Offensive Edge Against Florida" or the shorter "Auburn vs. Florida: The Offensive Edge"

## 20. Final public positioning

Recommended title:

> **Finding Auburn's Offensive Edge Against Florida With Play-by-Play Data**

Recommended one-sentence explanation:

> Instead of predicting the final score, I built a league-wide baseline to find where Auburn's offense has created more value than expected, where Florida's defense has allowed more value than expected, and where those patterns overlap.

Recommended disclaimer:

> This is an independent analysis using public play-by-play data. It is not affiliated with Auburn Athletics, and it does not account for private film, personnel, injury, or play-call information.

That framing is analytically honest, easy to understand, and strong enough to show real sports analytics work on LinkedIn.

## Source list

- [Auburn 2026 football schedule](https://auburntigers.com/sports/football/schedule?print=true)
- [Auburn kickoff and ESPN announcement](https://auburntigers.com/news/2026/05/27/kickoff-times-tv-networks-announced-for-first-three-games)
- [Florida broadcast information](https://floridagators.com/news/2026/9/14/football-broadcast-information-florida-vs-auburn)
- [CollegeFootballData getting started](https://api.collegefootballdata.com/getting-started)
- [CollegeFootballData API tiers](https://collegefootballdata.com/api-tiers)
- [CollegeFootballData play endpoint](https://api.collegefootballdata.com/api/plays)
- [CollegeFootballData passing endpoint](https://api.collegefootballdata.com/api/passing)
- [CollegeFootballData rushing endpoint](https://api.collegefootballdata.com/api/rushing)
- [CollegeFootballData advanced statistics endpoint](https://api.collegefootballdata.com/api/stats)
- [CollegeFootballData data availability](https://api.collegefootballdata.com/data-availability)
- [CollegeFootballData methodology overview](https://api.collegefootballdata.com/methodology-overview)
- [SportsDataverse cfbfastR repository](https://github.com/sportsdataverse/cfbfastR)
- [SportsDataverse cfbfastR play-by-play release](https://github.com/sportsdataverse/sportsdataverse-data/releases/tag/cfbfastR_cfb_pbp)
- [SportsDataverse field-level data dictionary](https://github.com/sportsdataverse/cfbfastR-cfb-data/blob/main/DATASETS.md)
- [Scikit-learn model evaluation documentation](https://scikit-learn.org/stable/modules/model_evaluation.html)
- [XGBoost Python documentation](https://xgboost.readthedocs.io/en/stable/python/python_intro.html)
