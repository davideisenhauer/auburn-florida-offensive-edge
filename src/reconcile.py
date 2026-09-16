"""Reconcile the four 2026 matchup games across play-by-play, CFBD, and official team box scores.

Run from the project root (after src.clean):
    .venv/bin/python -m src.reconcile

Writes outputs/tables/reconciliation_2026.csv, one row per offense, game, and statistic.
Official box scores follow NCAA scoring: sacks count as rushes, and plays = rushes + pass attempts.
"""

import io
import json
import re

import pandas as pd

from src import config
from src.ingest import cfbd_dest, matchup_games_through_cutoff, norm

# Absolute difference from the official figure that counts as minor rather than needing investigation
TOLERANCE = {"yards": 15}
DEFAULT_COUNT_TOLERANCE = 2
MIN_PPA_MATCH_SHARE = 0.99
POSSESSION_CHANGE_PATTERN = r"intercept|fumble|turnover on downs"


def pbp_team_stats(plays: pd.DataFrame, game_id: int, offense: str) -> dict:
    """Box-score-style totals from every snap that counted (no-play and offsetting penalties removed)."""
    snaps = plays[(plays.game_id == game_id) & (plays.pos_team == offense) & ~plays.is_no_play & ~plays.is_offsetting]
    runs, passes = snaps[snaps.play_family == "run"], snaps[snaps.play_family == "pass"]
    sacks = passes[passes.is_sack]
    return {
        "plays": len(snaps),
        "rushes (incl. sacks)": len(runs) + len(sacks),
        "pass attempts (excl. sacks)": len(passes) - len(sacks),
        "total yards": snaps.yards_gained.sum(),
        "interceptions thrown": int((snaps.is_giveaway & snaps.play_text.str.contains("intercept", case=False, na=False)).sum()),
        "fumbles lost": int((snaps.is_giveaway & ~snaps.play_text.str.contains("intercept", case=False, na=False)).sum()),
        "sacks allowed": len(sacks),
        "accepted penalty snaps (info)": int(snaps.is_accepted_penalty.sum()),
        # yards_gained on these snaps can include the penalty yardage; they are outside the model sample
        "yards on accepted penalty snaps (info)": snaps.yards_gained[snaps.is_accepted_penalty].sum(),
        "ppa_total (info)": snaps.ppa.sum(),
    }


def ppa_match(plays: pd.DataFrame, game_id: int, offense: str) -> dict:
    """Share of plays whose frozen PPA equals CFBD's live /plays PPA, split by possession change.

    CFBD revalued possession-change plays after the play-by-play file was built, so only the
    other plays are expected to match exactly.
    """
    live = []
    for team in (config.OFFENSE_TEAM, config.DEFENSE_TEAM):
        for week in config.CURRENT_WEEKS:
            live += json.loads(cfbd_dest("plays", {"year": config.CURRENT_SEASON, "week": week, "team": team}).read_bytes())
    live = pd.DataFrame(live).drop_duplicates("id")
    live = live[(live.gameId == game_id) & (live.offense == offense)]
    snaps = plays[(plays.game_id == game_id) & (plays.pos_team == offense) & plays.ppa.notna()]
    m = snaps.merge(live[["playText", "ppa"]].rename(columns={"playText": "play_text", "ppa": "cfbd_ppa"}), on="play_text")
    m["cfbd_ppa"] = pd.to_numeric(m.cfbd_ppa, errors="coerce")
    m["same"] = (m.ppa - m.cfbd_ppa).abs() < 0.001
    change = m.play_text.str.contains(POSSESSION_CHANGE_PATTERN, case=False, na=False)
    return {
        "ppa matches CFBD, other plays (share)": round(m.same[~change].mean(), 4),
        "ppa matches CFBD, possession-change plays (share, info)": round(m.same[change].mean(), 4) if change.any() else None,
        "plays matched to CFBD /plays (info)": len(m),
    }


def cfbd_team_stats(game_id: int, offense: str, defense: str) -> dict:
    rows = []
    for team in (config.OFFENSE_TEAM, config.DEFENSE_TEAM):
        rows += json.loads(cfbd_dest("games_teams", {"year": config.CURRENT_SEASON, "team": team}).read_bytes())
    game = next(g for g in rows if g["id"] == game_id)
    stats = {t["team"]: {s["category"]: s["stat"] for s in t["stats"]} for t in game["teams"]}
    off, dfn = stats[offense], stats[defense]
    completions, attempts = (int(x) for x in off["completionAttempts"].split("-"))
    penalties, penalty_yards = (int(x) for x in off["totalPenaltiesYards"].split("-"))
    out = {
        "points": next(t["points"] for t in game["teams"] if t["team"] == offense),
        "plays": int(off["rushingAttempts"]) + attempts,
        "rushes (incl. sacks)": int(off["rushingAttempts"]),
        "pass attempts (excl. sacks)": attempts,
        "total yards": int(off["totalYards"]),
        "interceptions thrown": int(off["interceptions"]),
        "fumbles lost": int(off["fumblesLost"]),
        "sacks allowed": int(dfn["sacks"]),
        "penalties": penalties,
        "penalty yards": penalty_yards,
    }
    for team in (config.OFFENSE_TEAM, config.DEFENSE_TEAM):
        for g in json.loads(cfbd_dest("stats_game_advanced", {"year": config.CURRENT_SEASON, "team": team}).read_bytes()):
            if g["gameId"] == game_id and g["team"] == offense:
                out["ppa_total (info)"] = g["offense"]["totalPPA"]
                out["advanced plays (info)"] = g["offense"]["plays"]
    return out


def official_wmt(game_id_date, offense: str, defense: str) -> dict | None:
    for path in (config.RAW_DIR / "official" / "auburn").glob("wmt_game_*.json"):
        game = json.loads(path.read_bytes())["data"]
        teams = {norm(c["nameTabular"]): c for c in game["competitors"]}
        if norm(offense) in teams and norm(defense) in teams and game.get("stats_finalized"):
            c = teams[norm(offense)]
            s = next(t["statistic"] for t in c["teamStats"] if t["period"] == 0)
            return {
                "points": c["score"], "plays": s.get("sPlays"), "rushes (incl. sacks)": s.get("sRushes"),
                "pass attempts (excl. sacks)": s.get("sPassAttempts"), "total yards": s.get("sTotalOffensiveYards"),
                "interceptions thrown": s.get("sPassInterceptions") or 0, "fumbles lost": s.get("sFumblesLost") or 0,
                "sacks allowed": s.get("sSacksAllowed") or 0, "penalties": s.get("sPenalties"),
                "penalty yards": s.get("sPenaltyYards"), "source": f"WMT {path.stem}",
            }
    return None


def parse_sidearm_team_stats(html: str) -> tuple[dict, dict, dict]:
    """Return (linescore totals by team, stats for the first column team, stats for the second) from a Sidearm page."""
    tables = pd.read_html(io.StringIO(html))
    linescore = tables[0]
    totals = dict(zip(linescore.iloc[:, 0].map(norm), linescore["Total"].astype(int)))
    stats_table = next(t for t in tables if t.shape[1] == 3 and t.iloc[:, 0].astype(str).str.contains("Total Offense").any())
    header = list(stats_table.columns[1:])
    section, parsed = None, {h: {} for h in header}
    for _, row in stats_table.iterrows():
        label, a, b = (str(v).strip() for v in row.values)
        if label == a == b:
            section = label
            continue
        for col, value in zip(header, (a, b)):
            parsed[col][(section, label)] = value
    return totals, header, parsed


def official_sidearm(offense: str, defense: str) -> dict | None:
    florida_is_offense = offense == config.DEFENSE_TEAM
    opponent = defense if florida_is_offense else offense
    path = next((config.RAW_DIR / "official" / "florida").glob(f"boxscore_*_{opponent.lower().replace(' ', '-')}.html"), None)
    if path is None:
        return None
    totals, header, parsed = parse_sidearm_team_stats(path.read_text(encoding="utf-8", errors="replace"))
    fla_col = next(h for h in header if h.upper() in {"FLA", "UF", "FLORIDA"})
    opp_col = next(h for h in header if h != fla_col)
    off_col, def_col = (fla_col, opp_col) if florida_is_offense else (opp_col, fla_col)
    s, d = parsed[off_col], parsed[def_col]
    lookup = lambda stats, label: next(v for (sec, lab), v in stats.items() if lab == label)
    by_section = lambda stats, section, label: stats[(section, label)]
    comp, att, ints = (int(x) for x in re.findall(r"\d+", by_section(s, "Passing", "Comp.-Att.-Int.")))
    penalties, penalty_yards = (int(x) for x in re.findall(r"\d+", lookup(s, "Penalties - Yds.")))
    fumbles, lost = (int(x) for x in re.findall(r"\d+", lookup(s, "Fumbles - Lost")))
    sacks_by_defense = int(re.findall(r"\d+", lookup(d, "Sacks: Total - Yds."))[0])
    team_points = totals.pop(norm(config.DEFENSE_TEAM))
    opp_points = next(iter(totals.values()))
    return {
        "points": team_points if florida_is_offense else opp_points,
        "plays": int(by_section(s, "Total Offense", "Plays")),
        "rushes (incl. sacks)": int(by_section(s, "Rushing", "Attempts")),
        "pass attempts (excl. sacks)": att,
        "total yards": int(by_section(s, "Total Offense", "Yards")),
        "interceptions thrown": ints, "fumbles lost": lost, "sacks allowed": sacks_by_defense,
        "penalties": penalties, "penalty yards": penalty_yards, "source": f"Sidearm {path.stem}",
    }


def status(metric: str, pbp, official) -> str:
    if metric.endswith("(share)"):
        return "match" if pbp is not None and pbp >= MIN_PPA_MATCH_SHARE else "investigate"
    if "(info)" in metric or pbp is None or official is None or pd.isna(pbp) or pd.isna(official):
        return "info"
    diff = abs(float(pbp) - float(official))
    if diff == 0:
        return "match"
    tol = TOLERANCE.get("yards" if "yards" in metric else metric, DEFAULT_COUNT_TOLERANCE)
    return "minor" if diff <= tol else "investigate"


def build() -> pd.DataFrame:
    plays = pd.read_parquet(config.PROCESSED_DIR / "plays.parquet")
    games = matchup_games_through_cutoff(cfbd_dest("games", {"year": config.CURRENT_SEASON, "seasonType": "both"}))
    rows = []
    for g in sorted(games, key=lambda g: (g["week"], g["id"])):
        for offense, defense in ((g["homeTeam"], g["awayTeam"]), (g["awayTeam"], g["homeTeam"])):
            pbp = pbp_team_stats(plays, g["id"], offense) | ppa_match(plays, g["id"], offense)
            cfbd = cfbd_team_stats(g["id"], offense, defense)
            auburn_game = config.OFFENSE_TEAM in (offense, defense)
            official = official_wmt(g["id"], offense, defense) if auburn_game else official_sidearm(offense, defense)
            official = official or {}
            metrics = list(dict.fromkeys([*cfbd.keys(), *pbp.keys()]))
            for metric in metrics:
                p, c, o = pbp.get(metric), cfbd.get(metric), official.get(metric)
                cfbd_reference = metric in ("ppa_total (info)", "advanced plays (info)")
                reference = c if cfbd_reference else o
                rows.append({
                    "game_id": g["id"], "week": g["week"], "offense": offense, "defense": defense, "metric": metric,
                    "play_by_play": p, "cfbd": c, "official": o,
                    "reference": "cfbd" if cfbd_reference else "official",
                    "diff_vs_reference": None if p is None or reference is None else round(float(p) - float(reference), 3),
                    "status": status(metric, p, reference),
                    "cfbd_vs_official": None if c is None or o is None else round(float(c) - float(o), 3),
                    "official_source": official.get("source"),
                })
    return pd.DataFrame(rows)


def main() -> None:
    table = build()
    config.TABLES_DIR.mkdir(parents=True, exist_ok=True)
    table.to_csv(config.TABLES_DIR / "reconciliation_2026.csv", index=False)
    pd.set_option("display.width", 220)
    wide = table.pivot_table(index=["metric"], columns=["week", "offense"], values="diff_vs_reference", aggfunc="first")
    print("Play-by-play minus reference (official box score; CFBD advanced for PPA)\n")
    print(wide.to_string())
    print("\nStatus counts:", table.status.value_counts().to_dict())
    flagged = table[table.status == "investigate"]
    if len(flagged):
        print("\nNeeds investigation:")
        print(flagged[["week", "offense", "metric", "play_by_play", "cfbd", "official"]].to_string(index=False))


if __name__ == "__main__":
    main()
