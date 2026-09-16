# Data sources

**Snapshot taken:** September 16, 2026
**Analysis cutoff:** September 12, 2026 (US Central), the date of the last completed games included

Every raw file is saved unchanged under `data/raw/` and listed in [`data/data_manifest.csv`](../data/data_manifest.csv) with its source URL, request parameters, download time, byte size, and SHA-256 hash. Raw files are not committed to Git.

To recreate the snapshot:

```bash
.venv/bin/python -m src.ingest            # downloads anything not yet frozen, then verifies
.venv/bin/python -m src.ingest --refresh  # re-downloads everything and records new hashes
```

A file that is already in the manifest is never downloaded again unless `--refresh` is passed. If a frozen file's hash stops matching, the ingest fails. A listed file that is missing, as in a fresh clone, is downloaded again and must match its recorded hash too, so an upstream correction stops the ingest instead of silently changing the data.

## 1. Primary play-by-play: SportsDataverse `cfbfastR_cfb_pbp`

| | |
|---|---|
| Files | `play_by_play_{2021..2026}.parquet`, one per season |
| Origin | CollegeFootballData plays processed by cfbfastR; carries CFBD's play-level PPA plus cfbfastR EPA and win probability |
| Used for | Training (2021–2024), untouched test set (2025), matchup scoring (2026) |
| Key fields | `ppa` (the value metric), `yards_gained`, `down`, `distance`, `yards_to_goal`, `TimeSecsRem`, `pos_score_diff_start`, `spread`, `rush`, `pass`, `sack`, penalty flags, `play_text` |

### Change from the project plan

The plan linked the ESPN-sourced `espn_cfb_pbp` release. We rejected that release on September 16 because its 2026 file has stale, mid-game snapshots of the four matchup games:

| Game | `espn_cfb_pbp` 2026 | `cfbfastR_cfb_pbp` 2026 |
|---|---|---|
| Baylor vs. Auburn, Week 1 | 22 rows, stops in the 1st quarter, not completed | 217 rows, 4 quarters, completed |
| Florida Atlantic at Florida, Week 1 | 25 rows, stops in the 1st quarter, not completed | 198 rows, 4 quarters, completed |
| Campbell at Florida, Week 2 | 131 rows, stops early in the 4th quarter, not completed | 163 rows, 4 quarters, completed |
| Southern Miss at Auburn, Week 2 | Missing | 188 rows, 4 quarters, completed |

In `espn_cfb_pbp` 2026, 95 of 179 games were marked not completed. The ESPN-sourced 2026 schedule and team box score files in the same repository show the same stale snapshots, so none of the ESPN-sourced 2026 SportsDataverse files are used.

The cfbfastR release also fits the plan better. Its schema has 362 columns, close to the plan's "roughly 380 fields." The linked data dictionary also documents this release.

**Value metric: CFBD PPA, not cfbfastR EPA.** The data audit found that the 2026 file was built with cfbfastR's new 3.0 expected-points and win-probability models, while 2021–2025 used the old ones. The same situation gets a different EPA in 2026. The file's CFBD `ppa` column is identical for identical situations in every season, turnovers included. Following the plan's own fallback rule, the analysis uses `ppa` end to end, and cfbfastR EPA and WP are not used. Evidence: [`analysis_spec.md`](analysis_spec.md) section 4 and the audit notebook, section 3.

### Snapshot verification (September 16, 2026)

All six seasons have the same 362 columns, including every field in `config.REQUIRED_PBP_COLUMNS`. FBS coverage was checked against CFBD `/games`, counting completed games that involve at least one FBS team:

| Season | Plays | Games in file | Completed FBS games | FBS games in file |
|---|---:|---:|---:|---:|
| 2021 | 163,444 | 887 | 887 | 100.0% |
| 2022 | 252,307 | 1,459 | 896 | 100.0% |
| 2023 | 254,090 | 1,494 | 910 | 100.0% |
| 2024 | 277,048 | 1,609 | 919 | 100.0% |
| 2025 | 293,200 | 1,657 | 934 | 99.9% (1 missing) |
| 2026 | 58,764 | 334 | 185 | 100.0% |

2021 has fewer games only because its file excludes games between two non-FBS teams. The FBS training filter removes those games in every season anyway.

The four matchup games are complete, and their final scores match CFBD and the official team records:

| Game | Score | Play-by-play rows | Official record |
|---|---|---:|---|
| Auburn vs. Baylor (neutral site, Atlanta), Week 1 | 17–16 | 217 | Match (WMT) |
| Southern Miss at Auburn, Week 2 | 43–8 | 188 | Match (WMT) |
| Florida Atlantic at Florida, Week 1 | 66–21 | 198 | Match (Sidearm) |
| Campbell at Florida, Week 2 | 52–3 | 163 | Match (Sidearm) |

**Build dates:** the seasons were built at different times: 2021 and 2022 in September 2025, 2023 in May 2026, 2024 and 2025 in July 2026, and 2026 in September 2026. That is how the EPA model change entered, and why the analysis uses PPA.

**Parsing quirks handled in cleaning:**
- `id_play` is stored as a floating-point number, so it is not a unique key.
- Some rows are exact duplicates (5,399 in 2021).
- The 2025 and 2026 builds type some real snaps, including lost fumbles, as fumbles or penalties without a run or pass flag.

## 2. Supplemental API: CollegeFootballData (Academic tier)

The key is read from `CFBD_API_KEY` in the git-ignored `.env` file. The full snapshot used 43 calls. The Academic tier allows 3,000 calls per month.

| Dataset | Endpoint | Scope | Purpose |
|---|---|---|---|
| `games` | `/games` | 2021–2026, all games | Game IDs, dates, scores, neutral sites, completion checks, and play-by-play coverage audit |
| `teams_fbs` | `/teams/fbs` | 2021–2026 | Defines which teams count as FBS for the training filter |
| `lines` | `/lines` | 2021–2026, all games | Pregame spread sensitivity check and backfill for missing spreads |
| `games_teams` | `/games/teams` | 2026 Auburn and Florida | Team box scores for reconciliation |
| `stats_game_advanced` | `/stats/game/advanced` | 2026 Auburn and Florida | Approximate cross-check only (see the note below the table) |
| `game_box_advanced` | `/game/box/advanced` | The four 2026 games | Advanced box scores for reconciliation |
| `plays` | `/plays` | 2026 Weeks 1–2, Auburn and Florida | Play-level PPA cross-check, and backup play-by-play if the primary source fails |
| `drives` | `/drives` | 2026 Auburn and Florida | Optional Drive Killer chart |
| `passing_plays`, `rushing_plays` | `/passing/plays`, `/rushing/plays` | 2026 Auburn and Florida | Optional supporting analysis (pass depth and direction, rush direction, parse status) |
| `calendar` | `/calendar` | 2026 | Week start and end dates for enforcing the cutoff |
| `ratings_sp` | `/ratings/sp` | 2025 and 2026 | Opponent-strength context for the write-up, not a model feature |
| `coaches` | `/coaches` | Auburn and Florida, 2021–2026 | Confirms first-year head coaches (context only) |
| `returning_production` | `/player/returning` | 2026, all teams | How much 2025 offensive production returns (context only) |
| `transfer_portal` | `/player/portal` | 2026, all transfers | Incoming transfers by side of the ball (context only) |

**Snapshot caveats:**
- The 2026 `lines` file reflects the market on September 16. The Auburn–Florida line will keep moving until kickoff.
- CFBD's live API has revalued interceptions, lost fumbles, and turnovers on downs since the play-by-play file was built. The frozen PPA equals CFBD's live `/plays` PPA on every other play in the four games, but CFBD's live PPA totals and advanced stats differ on possession-change plays. They are approximate cross-checks only, and live CFBD play data is never mixed into the frozen table.

## 3. Official team records

The plan requires the four games to be reconciled against official team records.

| Team | Source | Saved as |
|---|---|---|
| Auburn | `auburntigers.com` box score pages link to WMT, which serves the finalized game statistics as JSON (`api.wmt.games`) | `data/raw/official/auburn/wmt_game_*.json` |
| Florida | `floridagators.com` Sidearm box score pages with team statistics tables | `data/raw/official/florida/boxscore_*.html` |

These are public but undocumented site endpoints. The raw responses are frozen, so the reconciliation does not depend on them staying online.

## 4. Reference

- cfbfastR data dictionary (`DATASETS.md` from `sportsdataverse/cfbfastR-cfb-data`), saved to `data/raw/sportsdataverse/reference/`

## 5. Considered and not used

| Source | Reason |
|---|---|
| `espn_cfb_pbp` and the other ESPN-sourced 2026 SportsDataverse files | 2026 games are stale mid-game snapshots (see section 1) |
| cfbfastR `EPA`, `ep_before`, and `wp_before` columns | 2026 uses a different model version than 2021–2025 (see section 1) |
| SportsDataverse `cfb_crosswalk` | Not needed. The play-by-play and CFBD share game IDs and team names, and official box scores are matched by opponent. |
| `ncaa_mfb_pbp_cfbfastr` | Ends at 2025 and reaches only about 88% of games with ESPN IDs |
| CFBD `/games/weather`, `/live/plays`, and Tier 1+ adjusted metrics | Outside the plan's scope |
| ESPN FPI, team talent, recruiting | Not part of the model; SP+ is enough context for the write-up |
