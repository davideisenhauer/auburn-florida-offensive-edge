"""The backtest must use only games played before kickoff, and must never pair a team with itself.

Unit tests build small synthetic seasons. Table tests read what `python -m src.backtest` wrote.
"""

import numpy as np
import pandas as pd
import pytest

from src import config
from src.backtest import MIN_PRIOR_GAMES, matchups, prior_state, score, team_states

TABLES = ["backtest_summary", "backtest_by_games", "backtest_deciles", "backtest_market"]


PLAYS_PER_GAME = 25  # above the per-game minimum, so the filters do not empty the frame


def synthetic_season(plays_per_game: int = PLAYS_PER_GAME) -> pd.DataFrame:
    """Auburn and Alabama each play two tune-ups, then meet, so both arrive with prior games."""
    rows = []
    for game, (date, home, away, home_res, away_res) in enumerate([
        ("2021-09-04", "Auburn", "Georgia", 1.0, 0.0),
        ("2021-09-11", "Auburn", "Vanderbilt", 3.0, 0.0),
        ("2021-09-04", "Alabama", "Tennessee", -1.0, 0.5),
        ("2021-09-11", "Alabama", "Kentucky", -2.0, 0.5),
        ("2021-09-18", "Auburn", "Alabama", 5.0, 2.0),
    ], start=1):
        for offense, defense, residual in ((home, away, home_res), (away, home, away_res)):
            rows += [{"season": 2021, "game_id": game, "game_date_local": date, "pos_team": offense,
                      "def_pos_team": defense, "residual": residual}] * plays_per_game
    return pd.DataFrame(rows)


def test_prior_state_excludes_the_game_being_scored():
    state = prior_state(synthetic_season(), "pos_team")
    auburn = state[state.team == "Auburn"].sort_values("game_date_local")
    assert auburn.prior_games.tolist() == [0, 1, 2]
    assert auburn.prior_plays.tolist() == [0, PLAYS_PER_GAME, 2 * PLAYS_PER_GAME]
    assert auburn.prior_total.tolist() == [0.0, 25.0, 100.0]   # 25 x 1.0, then also 25 x 3.0
    assert auburn.this_game_mean.tolist() == [1.0, 3.0, 5.0]   # never inside prior_total


def test_a_team_is_never_matched_against_its_own_defense():
    state = team_states(synthetic_season(), k_offense=10.0, k_defense=10.0)
    pairs = matchups(state)
    assert len(pairs) > 0, "the synthetic season must reach the matchup stage"
    assert (pairs.offense != pairs.defense).all()
    assert not pairs.duplicated(["game_id", "offense"]).any()
    assert (pairs.groupby("game_id").size() <= 2).all()


def test_matchups_require_prior_games_for_both_teams():
    state = team_states(synthetic_season(), k_offense=10.0, k_defense=10.0)
    pairs = matchups(state)
    assert (pairs.prior_games_offense >= MIN_PRIOR_GAMES).all()
    assert (pairs.prior_games_defense_opponent >= MIN_PRIOR_GAMES).all()


def test_score_rewards_a_useful_prediction():
    frame = pd.DataFrame({"realized": [0.2, -0.2, 0.4, -0.4], "good": [0.1, -0.1, 0.2, -0.2],
                          "useless": [0.9, 0.9, -0.9, -0.9], "plays": [50, 50, 50, 50]})
    assert score(frame, "good")["rmse_improvement"] > 0
    assert score(frame, "useless")["rmse_improvement"] < 0


# ---------------------------------------------------------------- what the module wrote

@pytest.fixture(scope="module")
def tables():
    if not all((config.TABLES_DIR / f"{name}.csv").exists() for name in TABLES):
        pytest.skip("run `python -m src.backtest` first")
    return {name: pd.read_csv(config.TABLES_DIR / f"{name}.csv") for name in TABLES}


def test_the_edge_predicts_the_offense_result(tables):
    summary = tables["backtest_summary"]
    main = summary[summary["sample"].str.startswith("2021") & (summary.edge == "shrunk")].iloc[0]
    assert main.games > 5_000
    assert main.correlation > 0.15
    assert main.correlation_ci_low > 0          # the interval excludes no signal at all
    assert main.rmse_improvement > 0
    forward = summary[summary["sample"].str.contains("prospective") & (summary.edge == "shrunk")].iloc[0]
    assert forward.correlation > 0.15           # holds when the baseline never saw the season


def test_shrinking_is_what_makes_an_early_edge_usable(tables):
    by_games = tables["backtest_by_games"].pivot(index="prior_games", columns="edge", values="rmse_improvement")
    early = by_games.loc[MIN_PRIOR_GAMES]
    assert early["as measured"] < 0 < early["shrunk"], "raw early edges should be worse than no information"
    assert (by_games["shrunk"] > 0).all()


def test_deciles_are_ordered_and_scaled_as_the_definition_implies(tables):
    d = tables["backtest_deciles"].sort_values("decile")
    assert len(d) == 10 and d.mean_edge.is_monotonic_increasing
    assert d.mean_realized.iloc[0] < 0 < d.mean_realized.iloc[-1]
    assert np.corrcoef(d.mean_edge, d.mean_realized)[0, 1] > 0.95
    slope = d.slope.iloc[0]
    assert 1.5 < slope < 3.0, "the edge averages two components, so the realized result should be about twice it"


def test_the_edge_says_nothing_against_the_market(tables):
    market = tables["backtest_market"]
    overall = market[market.row == "overall"].iloc[0]
    assert overall.games > 2_000
    assert overall.ci_low < 0 < overall.ci_high, "the interval must include zero for a null result"
    assert abs(overall.correlation_lean_vs_result_against_line) < 0.05
    quintiles = market[market.row == "quintile"]
    assert len(quintiles) == 5
    assert quintiles.beat_the_line_rate.between(0.40, 0.60).all()
