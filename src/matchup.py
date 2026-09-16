"""Auburn offense and Florida defense residual profiles, shrinkage, robustness checks, and go/no-go gates.

Run from the project root (after src.models):
    .venv/bin/python -m src.matchup

Writes:
    outputs/tables/shrinkage_k.csv          reliability-based k, with the 2026 cross-team check
    outputs/tables/team_cells_fine.csv      down x distance x play family profiles (supporting heatmaps)
    outputs/tables/team_cells_rollup.csv    standard/passing downs x play family profiles (main map)
    outputs/tables/matchup_findings.csv     one row per rollup cell and metric, with labels
    outputs/tables/robustness_checks.csv    every check for every finding
    outputs/tables/go_no_go.csv             the five gates, the no-claims triggers, and the decision

Definitions are in docs/analysis_spec.md sections 6-9.
"""

import json

import numpy as np
import pandas as pd

from src import config
from src.ingest import cfbd_dest

METRICS = {"value": ("ppa", "PPA per play"), "explosive": ("explosive", "explosive rate")}
SIDES = {"offense": ("pos_team", config.OFFENSE_TEAM), "defense": ("def_pos_team", config.DEFENSE_TEAM)}
ROLLUP = ["play_family", "down_group"]
FINE = ["play_family", "down_bin", "distance_bin"]
K_GRID = np.unique(np.round(np.logspace(0, 4, 161), 2))
BOOTSTRAP_REPS = 4000
INTERVAL = 0.90
SEED = 20260917
LABEL_RANK = {"strongest signal": 0, "possible signal": 1, "no clear signal": 2}


# ---------------------------------------------------------------- data

def load() -> tuple[pd.DataFrame, dict]:
    plays = pd.read_parquet(config.PROCESSED_DIR / "plays.parquet")
    preds = pd.read_parquet(config.INTERIM_DIR / "predictions.parquet")
    data = plays.merge(preds, on="play_key", how="left")
    data["down_group"] = np.where(data.is_passing_down, "passing downs", "standard downs")
    selection = json.loads((config.OUTPUTS_DIR / "models" / "model_selection.json").read_text())
    return data, selection


def early_season(frame: pd.DataFrame) -> pd.Series:
    """Regular-season Weeks 1-2. The play-by-play also numbers every bowl and playoff game week 1 (change log #15)."""
    return frame.week.isin(config.CURRENT_WEEKS) & frame.game_season_type.eq("regular")


def shrink_factor(n: float, k: float) -> float:
    return 0.0 if not np.isfinite(k) or n == 0 else n / (n + k)


# ---------------------------------------------------------------- shrinkage constant k

def best_k(early: np.ndarray, n_early: np.ndarray, late: np.ndarray, n_late: np.ndarray) -> tuple[float, float, float]:
    """k minimizing the late-play-weighted squared error of predicting late means from shrunk early means."""
    losses = [np.sum(n_late * (late - n_early / (n_early + k) * early) ** 2) for k in K_GRID]
    no_trust = np.sum(n_late * late ** 2)
    i = int(np.argmin(losses))
    return (float(K_GRID[i]), float(losses[i]), float(no_trust)) if losses[i] < no_trust else (np.inf, float(no_trust), float(no_trust))


def estimate_k(data: pd.DataFrame) -> pd.DataFrame:
    hist = data[data.season.isin(config.HISTORICAL_SEASONS) & data.in_team_profile].copy()
    hist["period_group"] = np.where(early_season(hist), "early", "late")
    fbs = {s: {t["school"] for t in json.loads(cfbd_dest("teams_fbs", {"year": s}).read_bytes())} for s in config.HISTORICAL_SEASONS}
    rows = []
    for metric, (column, _) in METRICS.items():
        hist["res"] = hist[column].astype(float) - hist[f"{metric}_crossfit"]
        hist["res"] -= hist.groupby(["season", "period_group"] + ROLLUP).res.transform("mean")
        for side, (team_col, _) in SIDES.items():
            team_fbs = [team in fbs[season] for season, team in zip(hist.season, hist[team_col])]
            d = hist[team_fbs]
            agg = d.groupby(["season", team_col] + ROLLUP + ["period_group"]).res.agg(["mean", "size"]).unstack("period_group").dropna()
            for (family, group), cell in agg.groupby(level=ROLLUP):
                e, ne = cell[("mean", "early")].to_numpy(), cell[("size", "early")].to_numpy()
                l, nl = cell[("mean", "late")].to_numpy(), cell[("size", "late")].to_numpy()
                k, loss_k, loss_zero = best_k(e, ne, l, nl)
                rows.append({"metric": metric, "side": side, "play_family": family, "down_group": group, "k": k,
                             "team_seasons": len(cell), "median_early_plays": float(np.median(ne)),
                             "shrink_at_median_early_plays": shrink_factor(np.median(ne), k),
                             "error_reduction_vs_no_trust": 1 - loss_k / loss_zero,
                             "early_late_correlation": float(np.corrcoef(e, l)[0, 1])})
    k_table = pd.DataFrame(rows)

    # 2026 consistency check: method-of-moments k across FBS teams, same cells and weeks
    current = data[(data.season == config.CURRENT_SEASON) & data.in_team_profile].copy()
    fbs_2026 = {t["school"] for t in json.loads(cfbd_dest("teams_fbs", {"year": config.CURRENT_SEASON}).read_bytes())}
    mom = []
    for metric, (column, _) in METRICS.items():
        current["res"] = current[column].astype(float) - current[f"{metric}_final_adj"]
        current["res"] -= current.groupby(ROLLUP).res.transform("mean")
        for side, (team_col, _) in SIDES.items():
            d = current[current[team_col].isin(fbs_2026)]
            for (family, group), cell in d.groupby(ROLLUP):
                teams = cell.groupby(team_col).res.agg(["mean", "size", "var"])
                teams = teams[teams["size"] >= 5]
                within = float(np.average(teams["var"], weights=teams["size"] - 1))
                tau2 = float(teams["mean"].var() - np.mean(within / teams["size"]))
                mom.append({"metric": metric, "side": side, "play_family": family, "down_group": group,
                            "k_2026_method_of_moments": within / tau2 if tau2 > 0 else np.inf, "teams_2026": len(teams)})
    return k_table.merge(pd.DataFrame(mom), on=["metric", "side", "play_family", "down_group"], how="left")


def k_lookup(k_table: pd.DataFrame) -> dict:
    return {(r.metric, r.side, r.play_family, r.down_group): r.k for r in k_table.itertuples()}


# ---------------------------------------------------------------- team profiles

def team_sample(data: pd.DataFrame, side: str, mask_name: str = "primary") -> pd.DataFrame:
    team_col, team = SIDES[side]
    d = data[(data.season == config.CURRENT_SEASON) & (data[team_col] == team)]
    if mask_name == "primary":
        return d[d.in_team_profile]
    if mask_name == "garbage_included":
        return d[d.in_model_sample]
    if mask_name == "accepted_penalties_included":
        extra = (d.is_accepted_penalty & ~d.is_garbage_time & ~d.is_kneel & ~d.is_spike & d.has_ppa & d.valid_state)
        return d[d.in_team_profile | extra]
    if mask_name == "giveaways_removed":
        return d[d.in_team_profile & ~d.is_giveaway]
    raise ValueError(mask_name)


def cell_component(frame: pd.DataFrame, column: str, pred: str, k: float) -> dict:
    residuals = frame[column].astype(float).to_numpy() - frame[pred].to_numpy()
    n = len(residuals)
    raw = float(residuals.mean()) if n else np.nan
    factor = shrink_factor(n, k)
    return {"n": n, "k": k, "observed": float(frame[column].astype(float).mean()) if n else np.nan,
            "expected": float(frame[pred].mean()) if n else np.nan, "raw": raw, "shrink": factor,
            "shrunk": factor * raw if n else np.nan, "residuals": residuals}


def tier(n: int) -> str:
    return "hidden" if n < config.MIN_PLAYS_DISPLAY else "limited" if n < config.MIN_PLAYS_ELIGIBLE else "eligible"


def profiles(data: pd.DataFrame, ks: dict, keys: list[str]) -> pd.DataFrame:
    rows = []
    for side in SIDES:
        frame = team_sample(data, side)
        for metric, (column, _) in METRICS.items():
            for cell_key, cell in frame.groupby(keys):
                cell_key = dict(zip(keys, cell_key if isinstance(cell_key, tuple) else (cell_key,)))
                group = cell.down_group.mode().iloc[0]  # majority down group decides k for fine cells
                c = cell_component(cell, column, f"{metric}_final_adj", ks[(metric, side, cell_key["play_family"], group)])
                rows.append(cell_key | {"side": side, "team": SIDES[side][1], "metric": metric, "plays": c["n"], "tier": tier(c["n"]),
                                        "observed": c["observed"], "expected": c["expected"], "raw_residual": c["raw"],
                                        "shrink_factor": c["shrink"], "shrunk_residual": c["shrunk"] if c["n"] >= config.MIN_PLAYS_DISPLAY else np.nan})
    return pd.DataFrame(rows)


# ---------------------------------------------------------------- findings and robustness

def edge_components(data, ks, family, group, metric, column=None, pred_suffix="final_adj", masks=("primary", "primary"),
                    drop_game=None, k_metric=None):
    comps = {}
    for side, mask_name in zip(SIDES, masks):
        frame = team_sample(data, side, mask_name)
        if drop_game is not None:
            frame = frame[frame.game_id != drop_game]
        cell = frame[(frame.play_family == family) & (frame.down_group == group)]
        comps[side] = cell_component(cell, column or METRICS[metric][0], f"{metric}_{pred_suffix}", ks[(k_metric or metric, side, family, group)])
        comps[side]["frame"] = cell
    edge = (comps["offense"]["shrunk"] + comps["defense"]["shrunk"]) / 2
    return edge, comps


def influential_play(comps: dict, edge: float) -> tuple[float, str]:
    """Edge after removing the single play (from either team) that moves it furthest toward the other sign."""
    best_edge, best_play = edge, ""
    for side, other in (("offense", "defense"), ("defense", "offense")):
        c, o = comps[side], comps[other]
        r, n = c["residuals"], c["n"]
        if n < 2:
            continue
        shrunk_without = shrink_factor(n - 1, c["k"]) * (r.sum() - r) / (n - 1)
        edges = (o["shrunk"] + shrunk_without) / 2
        i = int(np.argmin(np.sign(edge) * edges))
        if np.sign(edge) * edges[i] < np.sign(edge) * best_edge:
            best_edge = float(edges[i])
            best_play = f"{SIDES[side][1]} {'offense' if side == 'offense' else 'defense'}: {c['frame'].play_text.iloc[i][:110]}"
    return best_edge, best_play


def bootstrap_interval(comps: dict) -> tuple[float, float, float]:
    rng = np.random.default_rng(SEED)
    draws = []
    for side in SIDES:
        c = comps[side]
        idx = rng.integers(0, c["n"], size=(BOOTSTRAP_REPS, c["n"]))
        draws.append(c["shrink"] * c["residuals"][idx].mean(axis=1))
    edges = (draws[0] + draws[1]) / 2
    alpha = (1 - INTERVAL) / 2
    lo, hi = np.quantile(edges, [alpha, 1 - alpha])
    return float(lo), float(hi), float(edges.std())


def evaluate_findings(data: pd.DataFrame, ks: dict, selection: dict) -> tuple[pd.DataFrame, pd.DataFrame]:
    findings, checks = [], []
    corrections_applied = any(v != 0 for v in selection["environment_corrections"]["final"].values())
    auburn_games = sorted(team_sample(data, "offense").game_id.unique())
    florida_games = sorted(team_sample(data, "defense").game_id.unique())
    names = (data[data.season == config.CURRENT_SEASON].groupby("game_id")[["home_team", "away_team"]].first()
             .apply(lambda r: f"{r.away_team} at {r.home_team}", axis=1).to_dict())

    for family in ("pass", "run"):
        for group in ("standard downs", "passing downs"):
            for metric in METRICS:
                edge, comps = edge_components(data, ks, family, group, metric)
                a, f = comps["offense"], comps["defense"]
                lo, hi, se = bootstrap_interval(comps)
                direction = np.sign(edge)
                results = []

                def record(number, name, variant_edge, note=""):
                    applicable = variant_edge is not None and not (isinstance(variant_edge, float) and np.isnan(variant_edge))
                    kept = bool(np.sign(variant_edge) == direction) if applicable else None
                    results.append(kept)
                    checks.append({"play_family": family, "down_group": group, "metric": metric, "check": number, "name": name,
                                   "edge": variant_edge if applicable else np.nan, "primary_edge": edge, "kept_direction": kept, "note": note})

                record(1, "2023-2025 sensitivity baseline", edge_components(data, ks, family, group, metric, pred_suffix="sensitivity_adj")[0])
                record(2, "garbage time included", edge_components(data, ks, family, group, metric, masks=("garbage_included",) * 2)[0])
                if metric == "value":
                    record(3, "accepted-penalty snaps included", edge_components(data, ks, family, group, metric, masks=("accepted_penalties_included",) * 2)[0])
                else:
                    record(3, "accepted-penalty snaps included", None, "not applicable: yardage unreliable")
                record(4, "giveaways removed", edge_components(data, ks, family, group, metric, masks=("giveaways_removed",) * 2)[0])
                if metric == "explosive":
                    record(5, "alternate explosive definition", edge_components(
                        data, ks, family, group, "explosive_alt", column="explosive_alt", k_metric="explosive")[0])
                else:
                    record(5, "alternate explosive definition", None, "not applicable to PPA")
                logo = [(g, edge_components(data, ks, family, group, metric, drop_game=g)[0]) for g in auburn_games + florida_games]
                for g, variant in logo:
                    record(6, f"without {names[g]}", variant)
                influential_edge, influential_text = influential_play(comps, edge)
                record(7, "most influential play removed", influential_edge, influential_text)
                record(8, "environment correction removed",
                       edge_components(data, ks, family, group, metric, pred_suffix="final")[0] if corrections_applied else None,
                       "" if corrections_applied else "not applicable: no correction was triggered")
                display_ok = a["n"] >= config.MIN_PLAYS_DISPLAY and f["n"] >= config.MIN_PLAYS_DISPLAY
                results.append(display_ok)
                checks.append({"play_family": family, "down_group": group, "metric": metric, "check": 9, "name": "display threshold",
                               "edge": np.nan, "primary_edge": edge, "kept_direction": display_ok, "note": f"{a['n']} and {f['n']} plays"})
                record(10, "boosted baseline", edge_components(data, ks, family, group, metric, pred_suffix="boosted_final_adj")[0])

                # LOGO counts as one check (spec check 6): it passes only if every game-out variant keeps direction
                by_check = pd.DataFrame(checks)
                mine = by_check[(by_check.play_family == family) & (by_check.down_group == group) & (by_check.metric == metric)]
                per_check = mine.dropna(subset=["kept_direction"]).groupby("check").kept_direction.all()
                failed = int((~per_check.astype(bool)).sum())
                eligible = a["n"] >= config.MIN_PLAYS_ELIGIBLE and f["n"] >= config.MIN_PLAYS_ELIGIBLE
                favorable = edge > 0
                both_favorable = a["shrunk"] > 0 and f["shrunk"] > 0
                if favorable and both_favorable and eligible and failed == 0:
                    label = "strongest signal"
                elif favorable and display_ok and failed <= 1:
                    label = "possible signal"
                else:
                    label = "no clear signal"
                findings.append({
                    "play_family": family, "down_group": group, "metric": metric,
                    "auburn_plays": a["n"], "florida_plays": f["n"],
                    "auburn_observed": a["observed"], "auburn_expected": a["expected"], "auburn_raw_residual": a["raw"],
                    "auburn_shrink": a["shrink"], "auburn_shrunk": a["shrunk"],
                    "florida_allowed_observed": f["observed"], "florida_allowed_expected": f["expected"], "florida_raw_residual": f["raw"],
                    "florida_shrink": f["shrink"], "florida_shrunk": f["shrunk"],
                    "edge": edge, "edge_low_90": lo, "edge_high_90": hi, "edge_se": se,
                    "checks_failed": failed, "failed_checks": ", ".join(str(c) for c, ok in per_check.items() if not ok),
                    "influential_play": influential_text, "label": label,
                    "headline_candidate": failed == 0 and favorable, "robust_eligible": failed == 0 and eligible,
                })
    return pd.DataFrame(findings), pd.DataFrame(checks)


def pooled_family_edges(data: pd.DataFrame, ks: dict) -> pd.DataFrame:
    """Auburn overall run and pass edges (pooled over down groups) under the primary sample and checks 2 and 4."""
    rows = []
    for family in ("pass", "run"):
        for metric in METRICS:
            for mask_name in ("primary", "garbage_included", "giveaways_removed"):
                pooled = {}
                for side in SIDES:
                    total, weighted = 0, 0.0
                    for group in ("standard downs", "passing downs"):
                        frame = team_sample(data, side, mask_name)
                        cell = frame[(frame.play_family == family) & (frame.down_group == group)]
                        c = cell_component(cell, METRICS[metric][0], f"{metric}_final_adj", ks[(metric, side, family, group)])
                        if c["n"]:
                            total += c["n"]
                            weighted += c["n"] * c["shrunk"]
                    pooled[side] = weighted / total if total else np.nan
                rows.append({"play_family": family, "metric": metric, "sample": mask_name,
                             "auburn_shrunk": pooled["offense"], "florida_shrunk": pooled["defense"],
                             "edge": (pooled["offense"] + pooled["defense"]) / 2})
    return pd.DataFrame(rows)


# ---------------------------------------------------------------- go / no-go

def gates(findings: pd.DataFrame, pooled: pd.DataFrame, selection: dict) -> pd.DataFrame:
    rec = pd.read_csv(config.TABLES_DIR / "reconciliation_2026.csv")
    scores = rec[rec.metric == "points"]
    counts = rec[rec.metric.isin(["plays", "pass attempts (excl. sacks)", "interceptions thrown"])]
    g1 = bool((scores.cfbd == scores.official).all() and len(scores) == 8 and (counts.diff_vs_reference.abs() <= 1).all())
    beats = {t: selection[t]["beats_naive"] for t in METRICS}
    marginal = {t: selection[t]["only_marginal"] for t in METRICS}
    g2 = all(beats.values())
    g3 = bool(selection["explosive"]["calibrated"])
    robust = findings[findings.robust_eligible]
    g4 = len(robust) >= 2
    primary = pooled[pooled["sample"] == "primary"].set_index(["play_family", "metric"]).edge
    stable = all(np.sign(r.edge) == np.sign(primary[(r.play_family, r.metric)]) for r in pooled[pooled["sample"] != "primary"].itertuples())
    g5 = bool(stable)

    favorable = findings[(findings.edge > 0) & (findings.auburn_plays >= config.MIN_PLAYS_DISPLAY) & (findings.florida_plays >= config.MIN_PLAYS_DISPLAY)].copy()
    if len(favorable):
        favorable["rank_label"] = favorable.label.map(LABEL_RANK)
        favorable["z"] = favorable.edge / favorable.edge_se
        top = favorable.sort_values(["rank_label", "checks_failed", "z"], ascending=[True, True, False]).iloc[0]
        one_play_drives = "7" in top.failed_checks.split(", ")
        top_name = f"{top.play_family} on {top.down_group}, {top.metric}"
    else:
        one_play_drives, top_name = False, "none"
    no_favorable_displayable = len(favorable) == 0
    model_fails = not all(beats[t] or marginal[t] for t in METRICS)

    if not g1 or model_fails or one_play_drives or no_favorable_displayable:
        decision = "NO MATCHUP CLAIMS BEFORE THE GAME"
    elif all([g1, g2, g3, g4, g5]):
        decision = "GO: FULL MATCHUP RELEASE"
    elif g3:
        decision = "SIMPLER DESCRIPTIVE RELEASE"
    else:
        decision = "SIMPLER DESCRIPTIVE RELEASE WITHOUT EXPLOSIVE PROBABILITIES (explosive model not calibrated)"

    rows = [
        ("gate 1", "Four 2026 games present and reconciled", g1, "scores match official records; plays, pass attempts, interceptions within 1"),
        ("gate 2", "Both models beat the naive baseline on 2025", g2, f"value: {beats['value']} (marginal {marginal['value']}); explosive: {beats['explosive']} (marginal {marginal['explosive']})"),
        ("gate 3", "Explosive model reasonably calibrated on 2025", g3, "observed/expected 0.95-1.05 and slope 0.85-1.15"),
        ("gate 4", "At least two robust eligible findings", g4, f"{len(robust)} found: " + "; ".join(f"{r.play_family} on {r.down_group} ({r.metric}, edge {'+' if r.edge > 0 else '-'})" for r in robust.itertuples())),
        ("gate 5", "Overall run and pass conclusions stable under garbage-time and giveaway checks", g5, ""),
        ("no-claims trigger", "A model fails to beat naive at all", model_fails, ""),
        ("no-claims trigger", "Strongest favorable finding driven by one play", one_play_drives, f"strongest favorable finding: {top_name}"),
        ("no-claims trigger", "No favorable finding meets the display threshold", no_favorable_displayable, ""),
        ("decision", decision, None, ""),
    ]
    return pd.DataFrame(rows, columns=["item", "description", "result", "detail"])


def main() -> None:
    data, selection = load()
    print("Estimating shrinkage constants from 2021-2025 within-season reliability", flush=True)
    k_table = estimate_k(data)
    ks = k_lookup(k_table)
    print("Building team profiles", flush=True)
    fine, rollup = profiles(data, ks, FINE), profiles(data, ks, ROLLUP)
    print("Evaluating findings and robustness checks", flush=True)
    findings, checks = evaluate_findings(data, ks, selection)
    pooled = pooled_family_edges(data, ks)
    decision = gates(findings, pooled, selection)

    config.TABLES_DIR.mkdir(parents=True, exist_ok=True)
    k_table.to_csv(config.TABLES_DIR / "shrinkage_k.csv", index=False)
    fine.to_csv(config.TABLES_DIR / "team_cells_fine.csv", index=False)
    rollup.to_csv(config.TABLES_DIR / "team_cells_rollup.csv", index=False)
    findings.to_csv(config.TABLES_DIR / "matchup_findings.csv", index=False)
    checks.to_csv(config.TABLES_DIR / "robustness_checks.csv", index=False)
    pooled.to_csv(config.TABLES_DIR / "pooled_family_edges.csv", index=False)
    decision.to_csv(config.TABLES_DIR / "go_no_go.csv", index=False)
    print(decision.to_string(index=False))


if __name__ == "__main__":
    main()
