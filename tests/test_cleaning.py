"""Cleaning rules from docs/analysis_spec.md section 5.

Unit tests build single synthetic plays. Integration tests check data/processed/plays.parquet
and are skipped until `python -m src.clean` has been run.
"""

from datetime import date

import pandas as pd
import pytest

from src import config
from src.clean import add_flags, recover_play_family

PROCESSED = config.PROCESSED_DIR / "plays.parquet"


def play(**overrides) -> dict:
    base = {
        "play_type": "Rush", "play_text": "J.Cobb rush middle for 4 yards", "rush": 1, "pass": 0, "sack": 0,
        "int": 0, "fumble_vec": 0, "turnover": 0,
        "penalty_flag": False, "penalty_declined": False, "penalty_offset": False, "penalty_no_play": False,
        "period": 1, "TimeSecsRem": 900.0, "down": 1.0, "distance": 10.0, "yards_to_goal": 75.0,
        "pos_score_diff_start": 0.0, "Goal_To_Go": False, "ppa": 0.1, "yards_gained": 4.0,
        "pos_team": "Auburn", "home_team": "Auburn", "neutral_site": False, "home_spread": -7.0,
    }
    base.update(overrides)
    return base


def flags(*rows) -> pd.DataFrame:
    return add_flags(pd.DataFrame(list(rows)))


def one(**overrides) -> pd.Series:
    return flags(play(**overrides)).iloc[0]


# ---------------------------------------------------------------- play family and exclusions

def test_normal_run_is_in_both_samples():
    p = one()
    assert p.play_family == "run" and p.in_model_sample and p.in_team_profile


def test_sack_counts_as_pass():
    p = one(play_type="Sack", play_text="B.Brown sacked for 7 yard loss", rush=0, **{"pass": 1}, sack=1, yards_gained=-7.0)
    assert p.play_family == "pass" and p.is_sack and p.in_model_sample


def test_no_play_and_offsetting_penalties_are_removed():
    assert not one(penalty_flag=True, penalty_no_play=True).in_model_sample
    assert not one(penalty_flag=True, penalty_offset=True).in_model_sample


def test_accepted_penalty_removed_but_declined_penalty_kept():
    accepted = one(penalty_flag=True)
    declined = one(penalty_flag=True, penalty_declined=True)
    assert accepted.is_accepted_penalty and not accepted.in_model_sample
    assert not declined.is_accepted_penalty and declined.in_model_sample


@pytest.mark.parametrize("text, period, seconds, yards, expected", [
    ("(00:34) Kneel down by CORDEIRO at SDS22 (team loss of 2)", 4, 34, -2, True),
    ("D. Finn takes a knee", 2, 20, -1, True),
    ("TEAM run for a loss of 1 yard to the Clem 29", 4, 45, -1, True),      # 2021-style kneel
    ("TEAM run for a loss of 1 yard to the Clem 29", 3, 45, -1, False),     # not late in a half
    ("TEAM run for a loss of 9 yards TEAM fumbled", 1, 800, -9, False),     # botched snap early
    ("Marshawn Kneeland run for 1 yd for a TD", 4, 30, 1, False),           # surname, and a gain
    ("I.Daniels rushed for 0 yards. Tackled by M.Kneeland", 4, 30, 0, False),
])
def test_kneel_detection(text, period, seconds, yards, expected):
    assert one(play_text=text, period=period, TimeSecsRem=float(seconds), yards_gained=float(yards)).is_kneel == expected


@pytest.mark.parametrize("text, expected", [
    ("(00:03) Shotgun #10 B.Hayes pass incomplete, Spike", True),
    ("Quarterback spiked the ball to stop the clock", True),
    ("Walker Harris pass incomplete to Chauncey Spikes", False),
])
def test_spike_detection(text, expected):
    p = one(play_type="Pass Incompletion", play_text=text, rush=0, **{"pass": 1}, yards_gained=0.0)
    assert p.is_spike == expected


def test_overtime_removed():
    assert not one(period=5).in_model_sample


@pytest.mark.parametrize("overrides", [
    {"down": 0.0}, {"distance": 0.0}, {"yards_to_goal": 0.0}, {"distance": 12.0, "yards_to_goal": 8.0},
    {"TimeSecsRem": 2820.0}, {"pos_score_diff_start": float("nan")},
])
def test_invalid_state_removed(overrides):
    p = one(**overrides)
    assert not p.valid_state and not p.in_model_sample


def test_missing_outcomes_removed():
    assert not one(ppa=float("nan")).in_model_sample
    assert not one(yards_gained=float("nan")).in_model_sample


# ---------------------------------------------------------------- definitions

@pytest.mark.parametrize("period, margin, expected", [(1, 43, False), (1, 44, True), (2, 38, True),
                                                      (3, 27, False), (4, 22, False), (4, -23, True)])
def test_garbage_time_thresholds(period, margin, expected):
    p = one(period=period, pos_score_diff_start=float(margin))
    assert p.is_garbage_time == expected
    assert p.in_team_profile == (not expected)


@pytest.mark.parametrize("down, distance, expected", [(1, 20, False), (2, 7, False), (2, 8, True),
                                                      (3, 4, False), (3, 5, True), (4, 5, True)])
def test_passing_downs(down, distance, expected):
    assert one(down=float(down), distance=float(distance), yards_to_goal=75.0).is_passing_down == expected


@pytest.mark.parametrize("value, column, expected", [
    (3, "distance", "short 1-3"), (4, "distance", "medium 4-7"), (7, "distance", "medium 4-7"), (8, "distance", "long 8+"),
    (51, "yards_to_goal", "own territory"), (50, "yards_to_goal", "midfield to opp 21"),
    (21, "yards_to_goal", "midfield to opp 21"), (20, "yards_to_goal", "red zone"),
])
def test_bin_boundaries(value, column, expected):
    overrides = {column: float(value)}
    if column == "distance":
        overrides["yards_to_goal"] = 75.0
    else:
        overrides["distance"] = 1.0
    p = one(**overrides)
    assert (p.distance_bin if column == "distance" else p.field_bin) == expected


def test_down_bins():
    assert [one(down=float(d)).down_bin for d in (1, 2, 3, 4)] == ["1st", "2nd", "3rd/4th", "3rd/4th"]


def test_explosive_definitions():
    assert one(yards_gained=20.0).explosive and not one(yards_gained=19.0).explosive
    assert one(yards_gained=10.0).explosive_alt  # run: 10+
    assert not one(play_type="Pass Reception", rush=0, **{"pass": 1}, yards_gained=19.0).explosive_alt  # pass: 20+


def test_spread_is_from_offense_perspective():
    home = one(pos_team="Auburn", home_team="Auburn", home_spread=-7.0)
    away = one(pos_team="Florida", home_team="Auburn", home_spread=-7.0)
    assert home.offense_spread == -7.0 and home.venue == "home"
    assert away.offense_spread == 7.0 and away.venue == "away"
    assert one(neutral_site=True).venue == "neutral"
    assert one(home_spread=float("nan")).spread_missing


def test_giveaways_exclude_turnover_on_downs():
    assert one(int=1, turnover=1).is_giveaway
    assert one(fumble_vec=1, turnover=1).is_giveaway
    assert not one(fumble_vec=1, turnover=0).is_giveaway  # fumble recovered by the offense
    assert not one(turnover=1).is_giveaway  # turnover on downs


# ---------------------------------------------------------------- run or pass read from text

def recovered(**overrides) -> pd.Series:
    return recover_play_family(pd.DataFrame([play(rush=0, **overrides)])).iloc[0]


def test_fumble_typed_run_is_recovered_as_run():
    p = recovered(play_type="Fumble Recovery (Opponent)", play_text="J.Cobb rush middle for 19 yards gain fumbled by J.Cobb recovered by USM")
    assert p.family_from_text and p["rush"] == 1 and p["pass"] == 0


def test_fumble_typed_sack_is_recovered_as_pass_and_sack():
    p = recovered(play_type="Fumble Recovery (Own)", play_text="B.Brown sacked by K.Reed for 8 yards loss fumbled recovered by AUB")
    assert p["pass"] == 1 and p.sack == 1


@pytest.mark.parametrize("overrides", [
    {"play_type": "Fumble", "play_text": "C.Gibbs punt 41 yards fumbled by returner"},
    {"play_type": "Penalty", "play_text": "B.Brown pass complete PENALTY Holding", "penalty_no_play": True},
    {"play_type": "Kickoff", "play_text": "rush of kickoff coverage"},
])
def test_non_snaps_are_not_recovered(overrides):
    p = recovered(**overrides)
    assert not p.family_from_text and p["rush"] == 0 and p["pass"] == 0


# ---------------------------------------------------------------- processed table

@pytest.fixture(scope="module")
def processed() -> pd.DataFrame:
    if not PROCESSED.exists():
        pytest.skip("run `python -m src.clean` first")
    return pd.read_parquet(PROCESSED)


def test_play_key_is_unique(processed):
    assert processed.play_key.is_unique


def test_model_sample_obeys_every_rule(processed):
    s = processed[processed.in_model_sample]
    for flag in ["is_no_play", "is_offsetting", "is_accepted_penalty", "is_kneel", "is_spike", "is_overtime"]:
        assert not s[flag].any(), flag
    assert s.valid_state.all() and s.ppa.notna().all() and s.yards_gained.notna().all()
    assert not processed[processed.in_team_profile].is_garbage_time.any()


def test_pre_snap_features_are_complete_in_model_sample(processed):
    s = processed[processed.in_model_sample]
    for feature in config.PRE_SNAP_FEATURES:
        missing = s[feature].isna()
        if feature == "offense_spread":
            missing &= ~s.spread_missing
        assert not missing.any(), feature


def test_2026_is_limited_to_the_cutoff(processed):
    current = processed[processed.season == config.CURRENT_SEASON]
    assert (current.game_date_local <= date.fromisoformat(config.ANALYSIS_CUTOFF)).all()
    assert set(current.week) <= set(config.CURRENT_WEEKS)


def test_matchup_teams_have_exactly_the_expected_2026_games(processed):
    current = processed[processed.season == config.CURRENT_SEASON]
    auburn = current[current.pos_team == config.OFFENSE_TEAM]
    florida = current[current.def_pos_team == config.DEFENSE_TEAM]
    assert set(auburn.def_pos_team) == config.EXPECTED_2026_OPPONENTS[config.OFFENSE_TEAM]
    assert set(florida.pos_team) == config.EXPECTED_2026_OPPONENTS[config.DEFENSE_TEAM]
    assert auburn.game_id.nunique() == 2 and florida.game_id.nunique() == 2
