"""Does an early-season matchup edge predict anything about the game itself?

Run from the project root (after src.models):
    .venv/bin/python -m src.backtest

For every FBS-vs-FBS game from 2021 to 2025, the edge is rebuilt from that season's earlier games only and
compared with what the offense actually did in that game against the frozen baseline. The same edges are then
tested against the closing point spread, which is the check that separates "my model misses this" from
"the market misses this".

Writes:
    outputs/tables/backtest_summary.csv    raw vs. shrunk edges: correlation and RMSE, with season-clustered intervals
    outputs/tables/backtest_by_games.csv   the same, split by how many games each team had played before kickoff
    outputs/tables/backtest_deciles.csv    mean edge and mean result by decile of the pre-kickoff edge
    outputs/tables/backtest_market.csv     the same edges against the market line

Supporting analysis (docs/analysis_spec.md change log #17): league-wide, uses only games played before each
kickoff, adds no matchup finding, and changes no frozen rule, label, gate, or the decision.
"""

import numpy as np
import pandas as pd

from src import config
from src.clean import load_games, load_line_spreads
from src.insights import fbs_by_season, load

SEED = 20260918
BOOTSTRAP_REPS = 2000
MIN_PRIOR_GAMES = 2  # the Auburn-Florida situation: two games each
MIN_PLAYS_IN_GAME = 20
DECILES = 10
MARKET_QUINTILES = 5


# ---------------------------------------------------------------- prior state, built only from earlier games

def residuals(data: pd.DataFrame, seasons: list[int], prediction: str, fbs: dict) -> pd.DataFrame:
    """Team-profile plays with a residual against the baseline, FBS vs FBS, centered on the season's league average."""
    d = data[data.season.isin(seasons) & data.in_team_profile].copy()
    d["residual"] = d.ppa.astype(float) - d[prediction]
    d = d[d.residual.notna()]
    d["residual"] -= d.groupby("season").residual.transform("mean")
    both_fbs = [o in fbs[s] and f in fbs[s] for s, o, f in zip(d.season, d.pos_team, d.def_pos_team)]
    return d[both_fbs]


def prior_state(plays: pd.DataFrame, team_column: str) -> pd.DataFrame:
    """Per team and game: totals from that season's earlier games only, plus what happened in this one."""
    per_game = (plays.groupby(["season", team_column, "game_id", "game_date_local"], as_index=False)
                .residual.agg(total="sum", plays="size")
                .sort_values(["season", team_column, "game_date_local"]))
    by_team = per_game.groupby(["season", team_column])
    per_game["prior_total"] = by_team.total.cumsum() - per_game.total  # excludes this game
    per_game["prior_plays"] = by_team.plays.cumsum() - per_game.plays
    per_game["prior_games"] = by_team.cumcount()
    per_game["this_game_mean"] = per_game.total / per_game.plays
    return per_game.rename(columns={team_column: "team"})


def shrink(total: pd.Series, plays: pd.Series, k: float) -> pd.Series:
    return plays / (plays + k) * (total / plays)


def team_states(plays: pd.DataFrame, k_offense: float, k_defense: float) -> pd.DataFrame:
    """One row per team per game: its offense and defense form going in, and its offensive result coming out."""
    offense = prior_state(plays, "pos_team")
    defense = prior_state(plays, "def_pos_team")[["season", "game_id", "team", "prior_total", "prior_plays", "prior_games"]]
    state = offense.merge(defense, on=["season", "game_id", "team"], suffixes=("_offense", "_defense"))
    state["offense_form"] = shrink(state.prior_total_offense, state.prior_plays_offense, k_offense)
    state["defense_form"] = shrink(state.prior_total_defense, state.prior_plays_defense, k_defense)
    state["offense_form_raw"] = state.prior_total_offense / state.prior_plays_offense
    state["defense_form_raw"] = state.prior_total_defense / state.prior_plays_defense
    return state


def matchups(state: pd.DataFrame) -> pd.DataFrame:
    """Each game seen from each offense's side: its form, its opponent's defensive form, and the result."""
    opponent = state[["season", "game_id", "team", "defense_form", "defense_form_raw", "prior_games_defense"]]
    pair = state.merge(opponent, on=["season", "game_id"], suffixes=("", "_opponent"))
    pair = pair[pair.team != pair.team_opponent]
    pair = pair[(pair.prior_games_offense >= MIN_PRIOR_GAMES) & (pair.prior_games_defense_opponent >= MIN_PRIOR_GAMES)
                & (pair.plays >= MIN_PLAYS_IN_GAME)]
    # The spec's edge is the average of the two components, so a realized result of about twice the edge is expected.
    pair["edge"] = (pair.offense_form + pair.defense_form_opponent) / 2
    pair["edge_unshrunk"] = (pair.offense_form_raw + pair.defense_form_raw_opponent) / 2
    pair["realized"] = pair.this_game_mean
    pair["prior_games"] = pair[["prior_games_offense", "prior_games_defense_opponent"]].min(axis=1)
    return pair.rename(columns={"team": "offense", "team_opponent": "defense"}).reset_index(drop=True)


# ---------------------------------------------------------------- scoring

def weighted_rmse(prediction: np.ndarray, actual: np.ndarray, weight: np.ndarray) -> float:
    return float(np.sqrt(np.average((prediction - actual) ** 2, weights=weight)))


def score(frame: pd.DataFrame, column: str) -> dict:
    prediction, actual, weight = frame[column].to_numpy(), frame.realized.to_numpy(), frame.plays.to_numpy()
    rmse = weighted_rmse(prediction, actual, weight)
    baseline = weighted_rmse(np.zeros_like(actual), actual, weight)  # predict the league average
    return {"games": len(frame), "correlation": float(np.corrcoef(prediction, actual)[0, 1]), "rmse": rmse,
            "rmse_no_information": baseline, "rmse_improvement": 1 - rmse / baseline}


def season_clustered_interval(frame: pd.DataFrame, statistic, level: float = 0.95, reps: int = BOOTSTRAP_REPS) -> tuple[float, float]:
    """Resample whole seasons, since games within a season share teams and a baseline."""
    rng = np.random.default_rng(SEED)
    groups = [np.asarray(index) for index in frame.groupby("season").indices.values()]
    draws = []
    for _ in range(reps):
        rows = np.concatenate([rng.choice(index, len(index), replace=True) for index in groups])
        draws.append(statistic(frame.iloc[rows]))
    alpha = (1 - level) / 2
    return float(np.quantile(draws, alpha)), float(np.quantile(draws, 1 - alpha))


def correlation_of(column: str):
    return lambda frame: float(np.corrcoef(frame[column], frame.realized)[0, 1])


# ---------------------------------------------------------------- the market test

def market_test(state: pd.DataFrame, seasons: list[int]) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Does the same edge say anything about the result relative to the closing line?"""
    games = load_games(seasons)
    spreads = load_line_spreads(seasons)
    played = games[games.game_completed & games.home_fbs & games.away_fbs].copy()
    played["home_spread"] = played.game_id.map(spreads)
    played = played.dropna(subset=["home_spread", "home_points", "away_points"])

    ready = state[(state.prior_games_offense >= MIN_PRIOR_GAMES) & (state.prior_games_defense >= MIN_PRIOR_GAMES)]
    joined = ready.merge(played[["game_id", "home_team", "away_team", "home_points", "away_points", "home_spread"]], on="game_id")
    home = joined[joined.team == joined.home_team].set_index("game_id")
    away = joined[joined.team == joined.away_team].set_index("game_id")
    both = home.join(away, lsuffix="_home", rsuffix="_away", how="inner")

    both["lean_home"] = ((both.offense_form_home + both.defense_form_away) / 2
                         - (both.offense_form_away + both.defense_form_home) / 2)
    both["margin"] = both.home_points_home - both.away_points_home
    both["result_vs_line"] = both.margin + both.home_spread_home  # positive: home beat the closing line
    both["season"] = both.season_home

    statistic = lambda frame: float(np.corrcoef(frame.lean_home, frame.result_vs_line)[0, 1])
    low, high = season_clustered_interval(both.reset_index(), statistic)
    summary = pd.DataFrame([{
        "games": len(both), "seasons": f"{min(seasons)}-{max(seasons)}",
        "correlation_lean_vs_result_against_line": statistic(both),
        "ci_low": low, "ci_high": high,
        "mean_result_vs_line": float(both.result_vs_line.mean()),
    }])
    quintile = pd.qcut(both.lean_home, MARKET_QUINTILES, labels=False) + 1
    by_quintile = (both.groupby(quintile)
                   .agg(games=("result_vs_line", "size"), mean_lean=("lean_home", "mean"),
                        mean_result_vs_line=("result_vs_line", "mean"),
                        beat_the_line_rate=("result_vs_line", lambda s: float((s > 0).mean())))
                   .reset_index(names="quintile"))
    return summary, by_quintile


# ---------------------------------------------------------------- main

def build(data: pd.DataFrame, fbs: dict, seasons: list[int], prediction: str, k_offense: float, k_defense: float):
    plays = residuals(data, seasons, prediction, fbs)
    state = team_states(plays, k_offense, k_defense)
    return state, matchups(state)


def main() -> None:
    data = load()
    fbs = fbs_by_season()
    reliability = pd.read_csv(config.TABLES_DIR / "insight_reliability.csv").set_index(["side", "measure"])
    k_offense = float(reliability.loc[("offense", "PPA over expected"), "k_plays"])
    k_defense = float(reliability.loc[("defense", "PPA over expected"), "k_plays"])
    print(f"Shrinking with k = {k_offense:.0f} plays (offense) and {k_defense:.0f} (defense)", flush=True)

    state, pairs = build(data, fbs, config.HISTORICAL_SEASONS, "value_crossfit", k_offense, k_defense)
    print(f"{len(pairs):,} matchups with {MIN_PRIOR_GAMES}+ prior games for both teams", flush=True)

    rows = []
    for label, column in (("as measured", "edge_unshrunk"), ("shrunk", "edge")):
        low, high = season_clustered_interval(pairs, correlation_of(column))
        rows.append({"sample": f"{min(config.HISTORICAL_SEASONS)}-{max(config.HISTORICAL_SEASONS)}, baseline fit without the season it scores",
                     "edge": label} | score(pairs, column) | {"correlation_ci_low": low, "correlation_ci_high": high})

    # Strictly prospective check: 2025 scored by the model that only ever saw 2021-2024.
    forward_state, forward = build(data, fbs, [config.TEST_SEASON], "value_test", k_offense, k_defense)
    for label, column in (("as measured", "edge_unshrunk"), ("shrunk", "edge")):
        rows.append({"sample": f"{config.TEST_SEASON} only, baseline fit on {min(config.TRAIN_SEASONS)}-{max(config.TRAIN_SEASONS)} (strictly prospective)",
                     "edge": label} | score(forward, column) | {"correlation_ci_low": np.nan, "correlation_ci_high": np.nan})
    summary = pd.DataFrame(rows)

    by_games = []
    for games, group in pairs.groupby(pairs.prior_games.clip(upper=8)):
        if len(group) < 200:
            continue
        for label, column in (("as measured", "edge_unshrunk"), ("shrunk", "edge")):
            by_games.append({"prior_games": int(games), "edge": label} | score(group, column))
    by_games = pd.DataFrame(by_games)

    deciles = pairs.assign(decile=pd.qcut(pairs.edge, DECILES, labels=False) + 1).groupby("decile").agg(
        games=("edge", "size"), mean_edge=("edge", "mean"), mean_realized=("realized", "mean"),
        plays=("plays", "sum")).reset_index()
    slope = np.polyfit(deciles.mean_edge, deciles.mean_realized, 1)
    deciles["fitted_realized"] = np.polyval(slope, deciles.mean_edge)
    deciles.attrs["slope"] = float(slope[0])

    market, market_quintiles = market_test(state, config.HISTORICAL_SEASONS)

    config.TABLES_DIR.mkdir(parents=True, exist_ok=True)
    summary.to_csv(config.TABLES_DIR / "backtest_summary.csv", index=False)
    by_games.to_csv(config.TABLES_DIR / "backtest_by_games.csv", index=False)
    deciles.assign(slope=float(slope[0])).to_csv(config.TABLES_DIR / "backtest_deciles.csv", index=False)
    pd.concat([market.assign(row="overall"), market_quintiles.assign(row="quintile")], ignore_index=True).to_csv(
        config.TABLES_DIR / "backtest_market.csv", index=False)

    pd.set_option("display.width", 220)
    print("\nDoes the pre-kickoff edge predict what the offense did?")
    print(summary[["sample", "edge", "games", "correlation", "rmse", "rmse_no_information", "rmse_improvement"]].round(4).to_string(index=False))
    print("\nBy games played before kickoff:")
    print(by_games.pivot(index="prior_games", columns="edge", values=["correlation", "rmse_improvement"]).round(4).to_string())
    print(f"\nBy decile of the edge (fitted slope {slope[0]:.2f}; about 2 is expected, since the edge averages two components):")
    print(deciles.round(4).to_string(index=False))
    print("\nAgainst the closing line:")
    print(market.round(4).to_string(index=False))
    print(market_quintiles.round(4).to_string(index=False))


if __name__ == "__main__":
    main()
