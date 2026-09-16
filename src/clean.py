"""Build the cleaned play table from the frozen raw snapshot.

Run from the project root:
    .venv/bin/python -m src.clean

Writes:
    data/processed/plays.parquet            every run and pass snap, with flags, features, and bins
    outputs/tables/cleaning_waterfall.csv   plays removed by each rule, by season

Rules are defined in docs/analysis_spec.md section 5. Nothing here reads an outcome to decide
whether a play is kept, except the documented requirement that PPA and yards gained exist.
"""

import json
from datetime import date

import numpy as np
import pandas as pd
import pyarrow.parquet as pq

from src import config
from src.ingest import cfbd_dest, local_game_date

RAW_COLUMNS = [
    "game_id", "year", "week", "period", "clock_minutes", "clock_seconds", "TimeSecsRem",
    "pos_team", "def_pos_team", "pos_score_diff_start", "down", "distance", "yards_to_goal", "Goal_To_Go",
    "play_type", "play_text", "rush", "pass", "sack", "int", "fumble_vec", "turnover",
    "penalty_flag", "penalty_declined", "penalty_offset", "penalty_no_play",
    "yards_gained", "ppa", "spread",
]
DEDUPE_KEY = ["game_id", "period", "clock_minutes", "clock_seconds", "pos_team",
              "down", "distance", "yards_to_goal", "play_type", "play_text"]
# Kneels: explicit wording, or (2021-2022 style CFBD text) an unnamed or TEAM rusher in the last
# two minutes of a half. Either way the run must lose yards or gain none.
KNEEL_PATTERN = r"\bkneel(?:s|ed|ing)?\b|\bkneeldown\b|takes a knee"  # not the surname "Kneeland"
UNNAMED_RUSH_PATTERN = r"^\s*(?:team run|run for|team rush|rush for)"
KNEEL_LATE_SECONDS = 120
# Spikes: explicit wording only. 2021-2024 text does not record spikes, so a few remain in training data.
SPIKE_PATTERN = r"\bspiked?\b"  # matches "spike" and "spiked" but not the surname "Spikes"

# Real snaps that cfbfastR typed as a fumble, safety, or post-play penalty without setting rush or pass.
# Common in the 2025 and 2026 builds (lost fumbles would otherwise vanish), rare before.
FAMILY_FROM_TEXT_TYPES = {
    "Fumble", "Fumble Recovery (Own)", "Fumble Recovery (Opponent)", "Fumble Return Touchdown",
    "Fumble Recovery (Opponent) Touchdown", "Safety", "Penalty",
}
SACK_TEXT = r"\bsacked\b"
PASS_TEXT = r"\bpass(?:ed)?\b|\bsacked\b"
RUN_TEXT = r"\brush(?:es|ed)?\b|\brun\b|\bscrambles?\b|\bkneel"
NOT_SCRIMMAGE_TEXT = r"kickoff|kicks off|\bpunt|field goal|extra point|\bpat\b|two-point|two point|2pt|onside"


# ---------------------------------------------------------------- raw inputs

def load_raw_plays(seasons=config.ALL_SEASONS) -> pd.DataFrame:
    frames = []
    for season in seasons:
        path = config.RAW_DIR / "sportsdataverse" / config.SDV_PBP_RELEASE / config.SDV_PBP_ASSET.format(season=season)
        df = pq.read_table(path, columns=RAW_COLUMNS).to_pandas()
        df["season"] = season
        df["row_order"] = np.arange(len(df))  # raw file order, used for a stable play key
        frames.append(df)
    return pd.concat(frames, ignore_index=True)


def load_games(seasons=config.ALL_SEASONS) -> pd.DataFrame:
    rows = []
    for season in seasons:
        for g in json.loads(cfbd_dest("games", {"year": season, "seasonType": "both"}).read_bytes()):
            rows.append({
                "game_id": g["id"], "game_season_type": g["seasonType"], "start_date": g["startDate"],
                "game_completed": g["completed"], "neutral_site": g["neutralSite"],
                "home_team": g["homeTeam"], "away_team": g["awayTeam"],
                "home_fbs": g["homeClassification"] == "fbs", "away_fbs": g["awayClassification"] == "fbs",
                "home_points": g["homePoints"], "away_points": g["awayPoints"],
            })
    games = pd.DataFrame(rows)
    games["game_date_local"] = games.start_date.map(local_game_date)
    return games


def load_line_spreads(seasons=config.ALL_SEASONS) -> pd.Series:
    """Median home-team spread across CFBD providers, used only where the play-by-play spread is missing."""
    rows = []
    for season in seasons:
        for g in json.loads(cfbd_dest("lines", {"year": season, "seasonType": "both"}).read_bytes()):
            spreads = [ln["spread"] for ln in g["lines"] if ln.get("spread") is not None]
            if spreads:
                rows.append((g["id"], float(np.median(spreads))))
    return pd.DataFrame(rows, columns=["game_id", "cfbd_spread"]).set_index("game_id").cfbd_spread


# ---------------------------------------------------------------- rules

def in_bins(values: pd.Series, bins: dict) -> pd.Series:
    out = pd.Series(pd.NA, index=values.index, dtype="object")
    for label, (lo, hi) in bins.items():
        out[(values >= lo) & (values <= hi)] = label
    return out


def recover_play_family(plays: pd.DataFrame) -> pd.DataFrame:
    """Set rush, pass, and sack from the text for real snaps whose flags cfbfastR left at zero."""
    p = plays.copy()
    text = p.play_text.fillna("").str.lower()
    candidate = (
        p["rush"].ne(1) & p["pass"].ne(1) & p.play_type.isin(FAMILY_FROM_TEXT_TYPES)
        & ~p.penalty_no_play.fillna(False).astype(bool)
        & (text.str.contains(PASS_TEXT, regex=True) | text.str.contains(RUN_TEXT, regex=True))
        & ~text.str.contains(NOT_SCRIMMAGE_TEXT, regex=True)
    )
    is_pass = candidate & text.str.contains(PASS_TEXT, regex=True)
    p["family_from_text"] = candidate
    p.loc[is_pass, "pass"] = 1
    p.loc[candidate & ~is_pass, "rush"] = 1
    p.loc[candidate & text.str.contains(SACK_TEXT, regex=True), "sack"] = 1
    return p


def add_flags(plays: pd.DataFrame) -> pd.DataFrame:
    """Add every rule flag, feature, bin, and outcome. Pure function of the row, so it is unit-testable."""
    p = plays.copy()
    text = p.play_text.fillna("").str.lower()

    p["is_pass"] = p["pass"].eq(1)
    p["is_sack"] = p.sack.eq(1)
    p["play_family"] = np.where(p.is_pass, "pass", "run")

    p["is_no_play"] = p.penalty_no_play.fillna(False).astype(bool)
    p["is_offsetting"] = p.penalty_offset.fillna(False).astype(bool)
    p["is_accepted_penalty"] = (p.penalty_flag.fillna(False).astype(bool) & ~p.penalty_declined.fillna(False).astype(bool)
                                & ~p.is_offsetting & ~p.is_no_play)
    late_in_half = p.period.isin([2, 4]) & (p.TimeSecsRem <= KNEEL_LATE_SECONDS)
    kneel_text = text.str.contains(KNEEL_PATTERN, regex=True) | (text.str.contains(UNNAMED_RUSH_PATTERN, regex=True) & late_in_half)
    p["is_kneel"] = p["rush"].eq(1) & (p.yards_gained <= 0) & kneel_text
    p["is_spike"] = p.is_pass & ~p.is_sack & text.str.contains(SPIKE_PATTERN, regex=True)
    p["is_overtime"] = p.period >= 5
    p["is_giveaway"] = p["int"].eq(1) | (p.fumble_vec.eq(1) & p.turnover.eq(1))

    p["valid_state"] = (
        p.down.between(1, 4) & (p.distance >= 1) & p.yards_to_goal.between(1, 99)
        & (p.distance <= p.yards_to_goal) & p.TimeSecsRem.between(0, 1800)
        & p.period.between(1, 5) & p.pos_score_diff_start.notna()
    )
    p["has_ppa"] = p.ppa.notna()
    p["has_yards"] = p.yards_gained.notna()

    margin = p.pos_score_diff_start.abs()
    threshold = p.period.map(config.GARBAGE_TIME_MARGIN)
    p["is_garbage_time"] = threshold.notna() & (margin > threshold)

    min_dist = p.down.map(config.PASSING_DOWN_MIN_DISTANCE)
    p["is_passing_down"] = min_dist.notna() & (p.distance >= min_dist)

    p["explosive"] = p.yards_gained >= config.EXPLOSIVE_YARDS
    p["explosive_alt"] = np.where(p.is_pass, p.yards_gained >= config.EXPLOSIVE_ALT_PASS_YARDS,
                                  p.yards_gained >= config.EXPLOSIVE_ALT_RUSH_YARDS)

    # Pre-snap features (config.PRE_SNAP_FEATURES)
    offense_is_home = p.pos_team.eq(p.home_team)
    p["venue"] = np.where(p.neutral_site, "neutral", np.where(offense_is_home, "home", "away"))
    p["offense_spread"] = np.where(offense_is_home, p.home_spread, -p.home_spread)  # negative: offense favored
    p["spread_missing"] = p.home_spread.isna()
    p["log_distance"] = np.log(p.distance.clip(lower=1))
    p["half_seconds_remaining"] = p.TimeSecsRem
    p["score_diff"] = p.pos_score_diff_start
    p["goal_to_go"] = p.Goal_To_Go.fillna(False).astype(bool)

    p["down_bin"] = in_bins(p.down, config.DOWN_BINS)
    p["distance_bin"] = in_bins(p.distance, config.DISTANCE_BINS)
    p["field_bin"] = in_bins(p.yards_to_goal, config.FIELD_POSITION_BINS)

    p["in_model_sample"] = (
        ~p.is_no_play & ~p.is_offsetting & ~p.is_accepted_penalty & ~p.is_kneel & ~p.is_spike
        & ~p.is_overtime & p.valid_state & p.has_ppa & p.has_yards
    )
    p["in_team_profile"] = p.in_model_sample & ~p.is_garbage_time
    return p


# ---------------------------------------------------------------- pipeline

def build(seasons=config.ALL_SEASONS) -> tuple[pd.DataFrame, pd.DataFrame]:
    raw = load_raw_plays(seasons)
    games = load_games(seasons)
    steps = []

    def log(label: str, df: pd.DataFrame):
        steps.append(df.groupby("season").size().rename(label))

    log("raw rows", raw)
    plays = raw.merge(games, on="game_id", how="inner")
    log("game found in CFBD", plays)

    cutoff = date.fromisoformat(config.ANALYSIS_CUTOFF)
    plays = plays[
        plays.game_completed
        & plays.game_season_type.isin(["regular", "postseason"])
        & (plays.home_fbs | plays.away_fbs)
        & ((plays.season < config.CURRENT_SEASON) | (plays.game_date_local <= cutoff))
    ]
    log("completed FBS game, regular or postseason, within cutoff", plays)

    plays = plays.drop_duplicates(subset=DEDUPE_KEY, keep="first")
    log("after removing duplicate rows", plays)

    plays = recover_play_family(plays)
    plays = plays[plays["rush"].eq(1) | plays["pass"].eq(1)].copy()
    log("run or pass snaps (sacks count as pass)", plays)
    log("  of which run or pass was read from the play text", plays[plays.family_from_text])

    spreads = load_line_spreads(seasons)
    plays["spread_source"] = np.where(plays.spread.notna(), "play_by_play",
                                      np.where(plays.game_id.map(spreads).notna(), "cfbd_lines", "missing"))
    plays["home_spread"] = plays.spread.fillna(plays.game_id.map(spreads))
    plays["play_key"] = plays.game_id.astype(str) + "_" + plays.row_order.astype(str).str.zfill(4)

    plays = add_flags(plays)
    removal_order = [
        ("minus no-play penalties", "is_no_play"),
        ("minus offsetting penalties", "is_offsetting"),
        ("minus accepted penalties on the play", "is_accepted_penalty"),
        ("minus kneels", "is_kneel"),
        ("minus spikes", "is_spike"),
        ("minus overtime", "is_overtime"),
    ]
    remaining = plays
    for label, flag in removal_order:
        remaining = remaining[~remaining[flag]]
        log(label, remaining)
    remaining = remaining[remaining.valid_state]
    log("minus invalid down, distance, field position, clock, or score", remaining)
    remaining = remaining[remaining.has_ppa & remaining.has_yards]
    log("minus missing PPA or yards gained = model sample", remaining)
    log("model sample minus garbage time = team profile sample", remaining[~remaining.is_garbage_time])

    waterfall = pd.concat(steps, axis=1).T.fillna(0).astype(int)
    waterfall.columns = [str(c) for c in waterfall.columns]
    waterfall["total"] = waterfall.sum(axis=1)

    keep = [
        "play_key", "game_id", "season", "week", "game_season_type", "game_date_local", "period",
        "clock_minutes", "clock_seconds", "pos_team", "def_pos_team", "home_team", "away_team",
        "home_fbs", "away_fbs", "neutral_site", "play_type", "play_text",
        "down", "distance", "yards_to_goal", "home_spread", "spread_source",
        *config.PRE_SNAP_FEATURES, "play_family", "family_from_text", "is_sack", "is_passing_down",
        "down_bin", "distance_bin", "field_bin",
        "ppa", "yards_gained", "explosive", "explosive_alt", "is_giveaway",
        "is_no_play", "is_offsetting", "is_accepted_penalty", "is_kneel", "is_spike", "is_overtime",
        "valid_state", "has_ppa", "has_yards", "is_garbage_time", "in_model_sample", "in_team_profile",
    ]
    keep = list(dict.fromkeys(keep))
    plays = plays[keep].sort_values(["season", "game_id", "play_key"]).reset_index(drop=True)
    if not plays.play_key.is_unique:
        raise ValueError("play_key is not unique after cleaning")
    return plays, waterfall


def main() -> None:
    plays, waterfall = build()
    config.PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    config.TABLES_DIR.mkdir(parents=True, exist_ok=True)
    out = config.PROCESSED_DIR / "plays.parquet"
    plays.to_parquet(out, index=False)
    waterfall.to_csv(config.TABLES_DIR / "cleaning_waterfall.csv", index_label="step")
    print(waterfall.to_string())
    print(f"\nWrote {len(plays):,} snaps to {out.relative_to(config.PROJECT_ROOT)} "
          f"({int(plays.in_model_sample.sum()):,} in the model sample)")


if __name__ == "__main__":
    main()
