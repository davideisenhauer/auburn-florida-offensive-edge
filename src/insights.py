"""League-wide context for the write-up: what two games of data can and cannot tell you.

Run from the project root (after src.models):
    .venv/bin/python -m src.insights

Writes:
    outputs/tables/insight_reliability.csv     how much of a two-game measure carries to the rest of the season (2021-2025)
    outputs/tables/insight_prediction.csv      raw vs. adjusted vs. shrunk early numbers as predictors (leave one season out)
    outputs/tables/insight_rank_intervals.csv  2026 FBS offenses: shrunk estimates and 90% rank intervals
    outputs/tables/insight_pairings.csv        matchup edges across every 2026 FBS offense-defense pairing

Supporting analysis only (docs/analysis_spec.md change log #16). It is league-wide and descriptive, it reuses
the frozen samples, models, and shrinkage, and it cannot change a frozen rule, finding, label, or the decision.
The Auburn-Florida pairing is recomputed here and checked against outputs/tables/matchup_findings.csv.
"""

import json

import numpy as np
import pandas as pd

from src import config
from src.ingest import cfbd_dest
from src.matchup import METRICS, ROLLUP, SIDES, best_k, early_season, k_lookup, shrink_factor

SEED = 20260918
RANK_DRAWS = 4000
INTERVAL = 0.90


# ---------------------------------------------------------------- data and measures

def load() -> pd.DataFrame:
    plays = pd.read_parquet(config.PROCESSED_DIR / "plays.parquet")
    preds = pd.read_parquet(config.INTERIM_DIR / "predictions.parquet")
    data = plays.merge(preds, on="play_key", how="left")
    data["down_group"] = np.where(data.is_passing_down, "passing downs", "standard downs")
    return data


def fbs_by_season() -> dict[int, set[str]]:
    return {s: {t["school"] for t in json.loads(cfbd_dest("teams_fbs", {"year": s}).read_bytes())} for s in config.ALL_SEASONS}


def success_rate(d: pd.DataFrame) -> pd.Series:
    """Bill Connelly's success rule: half the distance on 1st down, 70% on 2nd, all of it on 3rd and 4th."""
    needed = np.select([d.down == 1, d.down == 2], [0.5, 0.7], default=1.0) * d.distance
    return (d.yards_gained >= needed).astype(float)


# name, family, subset of plays, value per play
MEASURES = [
    ("Pass rate", "identity", None, lambda d: d.is_pass.astype(float)),
    ("Pass rate, standard downs", "identity", lambda d: ~d.is_passing_down, lambda d: d.is_pass.astype(float)),
    ("Pass rate, passing downs", "identity", lambda d: d.is_passing_down, lambda d: d.is_pass.astype(float)),
    ("Sack rate allowed", "efficiency", lambda d: d.is_pass, lambda d: d.is_sack.astype(float)),
    ("Yards per play", "efficiency", None, lambda d: d.yards_gained.astype(float)),
    ("Success rate", "efficiency", None, success_rate),
    ("Explosive-play rate (20+ yards)", "efficiency", None, lambda d: d.explosive.astype(float)),
    ("PPA per play", "efficiency", None, lambda d: d.ppa.astype(float)),
    ("PPA over expected", "adjusted", None, lambda d: d.ppa.astype(float) - d.value_crossfit),
    ("Explosive rate over expected", "adjusted", None, lambda d: d.explosive.astype(float) - d.explosive_crossfit),
]


def team_period_means(data: pd.DataFrame, team_col: str, fbs: dict, value, subset=None) -> pd.DataFrame:
    """Early and rest-of-season means per team-season, centered on the league average for that season and period."""
    d = data if subset is None else data[subset(data)]
    d = d[[team in fbs[season] for season, team in zip(d.season, d[team_col])]].copy()
    d["value"] = value(d)
    d = d[d.value.notna()]
    d["value"] -= d.groupby(["season", "period"]).value.transform("mean")
    agg = (d.groupby(["season", team_col, "period"])
           .agg(mean=("value", "mean"), plays=("value", "size"), games=("game_id", "nunique"))
           .unstack("period").dropna())
    return agg


# ---------------------------------------------------------------- 1. reliability by measure

def reliability(data: pd.DataFrame, fbs: dict) -> pd.DataFrame:
    hist = data[data.season.isin(config.HISTORICAL_SEASONS) & data.in_team_profile].copy()
    hist["period"] = np.where(early_season(hist), "early", "late")
    rows = []
    for side, (team_col, _) in SIDES.items():
        for name, family, subset, value in MEASURES:
            agg = team_period_means(hist, team_col, fbs, value, subset)
            early, n_early = agg[("mean", "early")].to_numpy(), agg[("plays", "early")].to_numpy()
            late, n_late = agg[("mean", "late")].to_numpy(), agg[("plays", "late")].to_numpy()
            games_early = agg[("games", "early")].to_numpy()
            k, _, _ = best_k(early, n_early, late, n_late)
            plays_per_game = float(np.median(n_early / games_early))
            median_early = float(np.median(n_early))
            rows.append({
                "side": side, "measure": name, "family": family, "team_seasons": len(agg),
                "median_early_plays": median_early, "plays_per_game": plays_per_game,
                "k_plays": k, "weight_after_two_games": shrink_factor(median_early, k),
                "games_to_half_weight": k / plays_per_game if np.isfinite(k) else np.inf,
                "early_late_correlation": float(np.corrcoef(early, late)[0, 1]),
            })
    return pd.DataFrame(rows)


# ---------------------------------------------------------------- 2. do adjusted early numbers predict better?

def prediction_test(data: pd.DataFrame, fbs: dict) -> pd.DataFrame:
    hist = data[data.season.isin(config.HISTORICAL_SEASONS) & data.in_team_profile].copy()
    hist["period"] = np.where(early_season(hist), "early", "late")
    inputs = {
        "raw two-game PPA per play": lambda d: d.ppa.astype(float),
        "adjusted two-game PPA over expected": lambda d: d.ppa.astype(float) - d.value_crossfit,
    }
    frames = {name: team_period_means(hist, "pos_team", fbs, value) for name, value in inputs.items()}
    rows = []
    for target_name, target in inputs.items():
        actual = frames[target_name]
        for input_name, frame in frames.items():
            joined = frame.join(actual, lsuffix="_in", rsuffix="_out", how="inner")
            early = joined[("mean_in", "early")].to_numpy()
            n_early = joined[("plays_in", "early")].to_numpy()
            late = joined[("mean_out", "late")].to_numpy()
            weight = joined[("plays_out", "late")].to_numpy()
            seasons = joined.index.get_level_values("season").to_numpy()
            shrunk = np.full(len(joined), np.nan)
            for season in config.HISTORICAL_SEASONS:  # k fitted without the season it is scored on
                other = seasons != season
                k, _, _ = best_k(early[other], n_early[other], late[other], joined[("plays_out", "late")].to_numpy()[other])
                shrunk[~other] = shrink_factor_array(n_early[~other], k) * early[~other]
            for predictor, prediction in (("league average (no team data)", np.zeros(len(early))),
                                          ("as measured", early), ("shrunk", shrunk)):
                error = prediction - late
                rmse = float(np.sqrt(np.average(error ** 2, weights=weight)))
                rows.append({
                    "target": f"rest-of-season {target_name.split('two-game ')[1]}",
                    "input": input_name, "treatment": predictor, "team_seasons": len(joined),
                    "weighted_rmse": rmse, "correlation_with_actual": float(np.corrcoef(prediction, late)[0, 1]) if prediction.std() else np.nan,
                })
    baseline = {t: next(r["weighted_rmse"] for r in rows if r["target"] == t and r["treatment"] == "league average (no team data)")
                for t in {r["target"] for r in rows}}
    for r in rows:
        r["rmse_improvement_vs_league_average"] = 1 - r["weighted_rmse"] / baseline[r["target"]]
    return pd.DataFrame(rows)


def shrink_factor_array(n: np.ndarray, k: float) -> np.ndarray:
    return np.zeros_like(n, dtype=float) if not np.isfinite(k) else n / (n + k)


# ---------------------------------------------------------------- 3. how well can two games rank a team?

def rank_intervals(data: pd.DataFrame, fbs: dict, k: float) -> pd.DataFrame:
    current = data[(data.season == config.CURRENT_SEASON) & data.in_team_profile]
    current = current[current.pos_team.isin(fbs[config.CURRENT_SEASON])].copy()
    current["residual"] = current.ppa.astype(float) - current.value_final_adj
    current["residual"] -= current.residual.mean()  # this season's league average through the cutoff
    g = current.groupby("pos_team").residual.agg(["mean", "size", "var"])
    within_team_variance = float(np.average(g["var"], weights=g["size"] - 1))

    # Empirical Bayes: true skill ~ N(0, sigma^2 / k), so the posterior mean is the shrunk mean.
    posterior_mean = g["size"] / (g["size"] + k) * g["mean"]
    posterior_sd = np.sqrt(within_team_variance / (g["size"] + k))
    rng = np.random.default_rng(SEED)
    draws = rng.normal(posterior_mean.to_numpy(), posterior_sd.to_numpy(), size=(RANK_DRAWS, len(g)))
    ranks = (-draws).argsort(axis=1).argsort(axis=1) + 1  # rank 1 = most PPA over expected
    alpha = (1 - INTERVAL) / 2

    one_play = current.groupby("pos_team").residual.agg(lambda r: float((r - r.mean()).abs().max() / (len(r) - 1)))
    out = pd.DataFrame({
        "team": g.index, "plays": g["size"].to_numpy(),
        "raw_ppa_over_expected": g["mean"].to_numpy(), "shrunk_ppa_over_expected": posterior_mean.to_numpy(),
        "posterior_sd": posterior_sd.to_numpy(),
        "rank_estimate": (-posterior_mean.to_numpy()).argsort().argsort() + 1,
        "rank_low_90": np.quantile(ranks, alpha, axis=0), "rank_high_90": np.quantile(ranks, 1 - alpha, axis=0),
        "one_play_swing_in_raw_mean": one_play.to_numpy(),
    })
    out["rank_interval_width"] = out.rank_high_90 - out.rank_low_90 + 1
    return out.sort_values("rank_estimate").reset_index(drop=True)


# ---------------------------------------------------------------- 4. every FBS pairing, not just this one

def pairings(data: pd.DataFrame, fbs: dict, ks: dict) -> tuple[pd.DataFrame, pd.DataFrame]:
    current = data[(data.season == config.CURRENT_SEASON) & data.in_team_profile]
    teams = fbs[config.CURRENT_SEASON]
    shrunk = {}
    for metric, (column, _) in METRICS.items():
        for side, (team_col, _) in SIDES.items():
            d = current[current[team_col].isin(teams)]
            g = (d.assign(residual=d[column].astype(float) - d[f"{metric}_final_adj"])
                 .groupby([team_col] + ROLLUP).residual.agg(["mean", "size"]).reset_index())
            g = g[g["size"] >= config.MIN_PLAYS_DISPLAY]
            g["shrunk"] = [shrink_factor(n, ks[(metric, side, fam, grp)]) * m
                           for n, m, fam, grp in zip(g["size"], g["mean"], g.play_family, g.down_group)]
            shrunk[(metric, side)] = g.rename(columns={team_col: "team"})

    rows, summaries = [], []
    for metric in METRICS:
        for family, group in [(f, g) for f in ("run", "pass") for g in ("standard downs", "passing downs")]:
            offense = shrunk[(metric, "offense")].query("play_family == @family and down_group == @group")
            defense = shrunk[(metric, "defense")].query("play_family == @family and down_group == @group")
            pair = offense.merge(defense, how="cross", suffixes=("_offense", "_defense"))
            pair = pair[pair.team_offense != pair.team_defense]
            pair["edge"] = (pair.shrunk_offense + pair.shrunk_defense) / 2
            pair = pair.assign(metric=metric, play_family=family, down_group=group)
            rows.append(pair[["metric", "play_family", "down_group", "team_offense", "team_defense", "edge"]])
            matchup = pair[(pair.team_offense == config.OFFENSE_TEAM) & (pair.team_defense == config.DEFENSE_TEAM)]
            edge = float(matchup.edge.iloc[0]) if len(matchup) else np.nan
            summaries.append({
                "metric": metric, "play_family": family, "down_group": group, "pairings": len(pair),
                "offenses": offense.team.nunique(), "defenses": defense.team.nunique(),
                "median_abs_edge": float(pair.edge.abs().median()), "p90_abs_edge": float(pair.edge.abs().quantile(0.90)),
                "largest_abs_edge": float(pair.edge.abs().max()),
                "auburn_florida_edge": edge,
                "auburn_florida_abs_percentile": float((pair.edge.abs() <= abs(edge)).mean() * 100) if np.isfinite(edge) else np.nan,
            })
    all_pairs = pd.concat(rows, ignore_index=True)

    # How unusual is the biggest edge either way in a pairing? Compare like with like across pairings.
    for metric in METRICS:
        m = all_pairs[all_pairs.metric == metric]
        biggest = m.assign(abs_edge=m.edge.abs()).groupby(["team_offense", "team_defense"]).abs_edge.max()
        matchup_value = float(biggest.loc[(config.OFFENSE_TEAM, config.DEFENSE_TEAM)])
        summaries.append({
            "metric": metric, "play_family": "any", "down_group": "largest of the four situations",
            "pairings": len(biggest), "offenses": np.nan, "defenses": np.nan,
            "median_abs_edge": float(biggest.median()), "p90_abs_edge": float(biggest.quantile(0.90)),
            "largest_abs_edge": float(biggest.max()), "auburn_florida_edge": matchup_value,
            "auburn_florida_abs_percentile": float((biggest <= matchup_value).mean() * 100),
        })
    return all_pairs, pd.DataFrame(summaries)


def check_against_frozen_findings(summary: pd.DataFrame) -> None:
    """The Auburn-Florida pairing computed here must reproduce the frozen findings exactly."""
    findings = pd.read_csv(config.TABLES_DIR / "matchup_findings.csv")
    merged = summary.merge(findings, on=["metric", "play_family", "down_group"], validate="one_to_one")
    assert len(merged) == len(findings), "every frozen finding must appear among the pairings"
    difference = (merged.auburn_florida_edge - merged.edge).abs().max()
    assert difference < 1e-12, f"pairing edges disagree with matchup_findings.csv by {difference}"
    print(f"  Auburn-Florida pairing matches the frozen findings (largest difference {difference:.1e})")


# ---------------------------------------------------------------- main

def main() -> None:
    data = load()
    fbs = fbs_by_season()
    print("Measuring how much of an early-season number carries to the rest of the season", flush=True)
    reliability_table = reliability(data, fbs)
    print("Testing raw vs. adjusted early numbers as predictors", flush=True)
    prediction_table = prediction_test(data, fbs)
    k_team = float(reliability_table.query("side == 'offense' and measure == 'PPA over expected'").k_plays.iloc[0])
    print(f"Ranking 2026 FBS offenses with k = {k_team:.0f} plays", flush=True)
    ranks = rank_intervals(data, fbs, k_team)
    print("Comparing every 2026 FBS offense-defense pairing", flush=True)
    ks = k_lookup(pd.read_csv(config.TABLES_DIR / "shrinkage_k.csv"))
    all_pairs, pairing_summary = pairings(data, fbs, ks)
    check_against_frozen_findings(pairing_summary)

    config.TABLES_DIR.mkdir(parents=True, exist_ok=True)
    value_pairs = all_pairs[all_pairs.metric == "value"]
    largest = (value_pairs.assign(abs_edge=value_pairs.edge.abs())
               .groupby(["team_offense", "team_defense"], as_index=False).abs_edge.max()
               .rename(columns={"abs_edge": "largest_abs_edge"}))
    largest.to_csv(config.TABLES_DIR / "insight_pairings_value.csv", index=False)
    reliability_table.to_csv(config.TABLES_DIR / "insight_reliability.csv", index=False)
    prediction_table.to_csv(config.TABLES_DIR / "insight_prediction.csv", index=False)
    ranks.to_csv(config.TABLES_DIR / "insight_rank_intervals.csv", index=False)
    pairing_summary.to_csv(config.TABLES_DIR / "insight_pairings.csv", index=False)

    offense = reliability_table[reliability_table.side == "offense"]
    print("\nOffense, how long until a measure is worth half its face value:")
    print(offense[["measure", "family", "early_late_correlation", "weight_after_two_games", "games_to_half_weight"]]
          .round(3).to_string(index=False))
    print("\nPredicting the rest of the season:")
    print(prediction_table[["target", "input", "treatment", "weighted_rmse", "rmse_improvement_vs_league_average",
                            "correlation_with_actual"]].round(4).to_string(index=False))
    print(f"\n2026 offenses: median 90% rank interval spans {ranks.rank_interval_width.median():.0f} of {len(ranks)} places")
    print(ranks.head(5).round(4).to_string(index=False))
    print(ranks[ranks.team.isin([config.OFFENSE_TEAM, config.DEFENSE_TEAM])].round(4).to_string(index=False))
    print("\nEvery 2026 FBS pairing:")
    print(pairing_summary.round(4).to_string(index=False))


if __name__ == "__main__":
    main()
