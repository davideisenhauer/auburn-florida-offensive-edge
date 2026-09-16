"""Project paths, frozen study constants, and secret loading.

Secrets live in the git-ignored .env file at the project root. See .env.example.
"""

import os
from pathlib import Path

from dotenv import load_dotenv

# Paths
PROJECT_ROOT = Path(__file__).resolve().parents[1]
ENV_FILE = PROJECT_ROOT / ".env"
DATA_DIR = PROJECT_ROOT / "data"
RAW_DIR = DATA_DIR / "raw"
INTERIM_DIR = DATA_DIR / "interim"
PROCESSED_DIR = DATA_DIR / "processed"
MANIFEST_PATH = DATA_DIR / "data_manifest.csv"
OUTPUTS_DIR = PROJECT_ROOT / "outputs"
FIGURES_DIR = OUTPUTS_DIR / "figures"
TABLES_DIR = OUTPUTS_DIR / "tables"

# Seasons and cutoff (docs/analysis_spec.md sections 2 and 3)
# 2026 is the subject. Earlier seasons only teach the league baseline; they never describe Auburn or Florida.
TRAIN_SEASONS = [2021, 2022, 2023, 2024]
TEST_SEASON = 2025
CURRENT_SEASON = 2026
HISTORICAL_SEASONS = TRAIN_SEASONS + [TEST_SEASON]
SENSITIVITY_SEASONS = [2023, 2024, 2025]  # post-2023 clock rules
ALL_SEASONS = HISTORICAL_SEASONS + [CURRENT_SEASON]
ANALYSIS_CUTOFF = "2026-09-12"  # date of the last completed games included (US Central)
CURRENT_WEEKS = [1, 2]
CUTOFF_TIMEZONE = "America/Chicago"

# ---------------------------------------------------------------- Frozen analysis definitions
# Frozen September 16, 2026, before any Auburn or Florida outcome was examined. Changing any
# value below requires an entry in the change log of docs/analysis_spec.md.

# Value metric. cfbfastR EPA was rejected: the 2026 file uses a new EP model (spec section 4).
VALUE_METRIC = "ppa"  # CFBD predicted points added, one model across 2021-2026
EXPLOSIVE_YARDS = 20
EXPLOSIVE_ALT_PASS_YARDS = 20  # sensitivity definition
EXPLOSIVE_ALT_RUSH_YARDS = 10

# Garbage time (CFBD / Bill Connelly): absolute score margin at the snap greater than this, by quarter.
# Replaces the plan's win-probability filter because the cfbfastR WP model also changed in 2026.
GARBAGE_TIME_MARGIN = {1: 43, 2: 37, 3: 27, 4: 22}

# Passing downs (CFBD / Connelly); every other down is a standard down.
PASSING_DOWN_MIN_DISTANCE = {2: 8, 3: 5, 4: 5}

# Situation bins (plan section 10). Intervals are inclusive.
DOWN_BINS = {"1st": (1, 1), "2nd": (2, 2), "3rd/4th": (3, 4)}
DISTANCE_BINS = {"short 1-3": (1, 3), "medium 4-7": (4, 7), "long 8+": (8, 99)}
FIELD_POSITION_BINS = {"own territory": (51, 99), "midfield to opp 21": (21, 50), "red zone": (1, 20)}  # yards to goal

# Publication thresholds for a team's plays in one cell
MIN_PLAYS_DISPLAY = 8  # fewer: hidden
MIN_PLAYS_ELIGIBLE = 15  # 8-14: "limited sample"; 15+: eligible for the main map

# 2026 environment check: recalibrate the baseline on other 2026 FBS plays when it misses by more than this
RECALIBRATE_PPA_MEAN_RESIDUAL = 0.03  # points per play, and the 95% interval must exclude zero
RECALIBRATE_EXPLOSIVE_RATIO = (0.90, 1.10)  # observed / expected, and the 95% interval must exclude 1

# Pre-snap predictors the baseline models may use (columns of data/processed/plays.parquet). Nothing else may enter.
PRE_SNAP_FEATURES = [
    "is_pass", "down", "distance", "log_distance", "yards_to_goal", "period", "half_seconds_remaining",
    "score_diff", "venue", "goal_to_go", "offense_spread", "spread_missing",
]

# Pre-snap, outcome, and cleaning fields every play-by-play season must carry (plan section 6)
REQUIRED_PBP_COLUMNS = [
    "game_id", "id_play", "year", "week", "season_type", "start_date", "completed",
    "pos_team", "def_pos_team", "home", "away", "neutral_site",
    "down", "distance", "yards_to_goal", "period", "TimeSecsRem", "pos_score_diff_start",
    "Goal_To_Go", "spread", "play_type", "rush", "pass", "sack",
    "penalty_flag", "penalty_declined", "penalty_offset", "penalty_no_play", "turnover", "int", "fumble_vec",
    "ppa", "EPA", "ep_before", "wp_before", "yards_gained", "play_text", "clock_minutes", "clock_seconds",
]

# Matchup
OFFENSE_TEAM = "Auburn"
DEFENSE_TEAM = "Florida"
EXPECTED_2026_OPPONENTS = {
    "Auburn": {"Baylor", "Southern Miss"},
    "Florida": {"Florida Atlantic", "Campbell"},
}

# Sources (see docs/data_sources.md for why each was chosen or rejected)
SDV_REPO = "sportsdataverse/sportsdataverse-data"
# Primary play-by-play: CFBD-sourced plays processed by cfbfastR. The ESPN-sourced
# espn_cfb_pbp release was rejected because its 2026 games are stale mid-game snapshots.
SDV_PBP_RELEASE = "cfbfastR_cfb_pbp"
SDV_PBP_ASSET = "play_by_play_{season}.parquet"
SDV_DATA_DICTIONARY_URL = (
    "https://raw.githubusercontent.com/sportsdataverse/cfbfastR-cfb-data/main/DATASETS.md"
)
CFBD_HOST = "https://api.collegefootballdata.com"
AUBURN_SCHEDULE_URL = "https://auburntigers.com/sports/football/schedule?print=true"
AUBURN_BOXSCORE_URL = "https://auburntigers.com/boxscore/{boxscore_id}"
WMT_GAME_API_URL = "https://api.wmt.games/api/statistics/games/{wmt_id}"
FLORIDA_SCHEDULE_URL = f"https://floridagators.com/sports/football/schedule/{CURRENT_SEASON}?print=true"
FLORIDA_SITE = "https://floridagators.com"
HTTP_USER_AGENT = "auburn-florida-offensive-edge/1.0 (student research project)"

load_dotenv(ENV_FILE)


def get_cfbd_api_key() -> str:
    """Return the CFBD API key from the environment, failing loudly if it is missing."""
    key = os.getenv("CFBD_API_KEY", "").strip()
    if key.lower().startswith("bearer "):
        key = key[len("bearer ") :].strip()
    if not key:
        raise RuntimeError(
            f"CFBD_API_KEY is not set. Add it to {ENV_FILE} "
            "(get a key at https://collegefootballdata.com/key)."
        )
    return key


def cfbd_configuration():
    """Build an authenticated configuration for the official cfbd client."""
    import cfbd

    return cfbd.Configuration(host=CFBD_HOST, access_token=get_cfbd_api_key())
