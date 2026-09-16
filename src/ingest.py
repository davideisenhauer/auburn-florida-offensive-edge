"""Download and freeze every raw data source, recording each file in data/data_manifest.csv.

Run from the project root:
    .venv/bin/python -m src.ingest                   # all sources, then verify
    .venv/bin/python -m src.ingest --only cfbd       # one source (pbp, cfbd, official, verify)
    .venv/bin/python -m src.ingest --refresh         # re-download and re-hash frozen files

Raw files are saved byte-for-byte under data/raw/. A file already in the manifest with a
matching SHA-256 is frozen and never re-downloaded unless --refresh is passed, so later
upstream corrections cannot silently change the analysis.
"""

import argparse
import csv
import hashlib
import io
import json
import re
from datetime import date, datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd
import pyarrow.parquet as pq
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from src import config

MANIFEST_COLUMNS = [
    "source", "dataset", "season", "url", "params", "local_path", "downloaded_at_utc",
    "bytes", "sha256", "remote_updated_at", "required", "notes",
]
CUTOFF = date.fromisoformat(config.ANALYSIS_CUTOFF)
TEAMS = (config.OFFENSE_TEAM, config.DEFENSE_TEAM)


class IngestError(RuntimeError):
    pass


# ---------------------------------------------------------------- manifest and HTTP helpers

def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def rel(path: Path) -> str:
    return path.relative_to(config.PROJECT_ROOT).as_posix()


class Manifest:
    def __init__(self, path: Path, refresh: bool = False):
        self.path = path
        self.refresh = refresh
        self.rows: dict[str, dict] = {}
        if path.exists():
            with open(path, newline="") as fh:
                self.rows = {row["local_path"]: row for row in csv.DictReader(fh)}

    def is_frozen(self, dest: Path, refresh: bool) -> bool:
        row = self.rows.get(rel(dest))
        if refresh or row is None or not dest.exists():
            return False
        if sha256_file(dest) != row["sha256"]:
            raise IngestError(f"{rel(dest)} no longer matches its manifest hash. Re-run with --refresh.")
        return True

    def record(self, dest: Path, **fields) -> None:
        """Add a downloaded file. A file already in the manifest must come back byte for byte unless refreshing."""
        previous = self.rows.get(rel(dest))
        if previous is not None and not self.refresh:
            if sha256_file(dest) != previous["sha256"]:
                raise IngestError(f"{rel(dest)} was downloaded again but no longer matches its manifest hash, so the "
                                  "source has changed since the snapshot. Re-run with --refresh to accept the new version.")
            return  # identical to the frozen file: keep the original row and download time
        row = {col: "" for col in MANIFEST_COLUMNS}
        row.update({k: ("" if v is None else v) for k, v in fields.items()})
        row.update(
            local_path=rel(dest),
            downloaded_at_utc=datetime.now(timezone.utc).isoformat(timespec="seconds"),
            bytes=dest.stat().st_size,
            sha256=sha256_file(dest),
        )
        self.rows[rel(dest)] = row
        self.save()

    def save(self) -> None:
        ordered = sorted(self.rows.values(), key=lambda r: (r["source"], r["dataset"], r["season"], r["local_path"]))
        with open(self.path, "w", newline="") as fh:
            writer = csv.DictWriter(fh, fieldnames=MANIFEST_COLUMNS)
            writer.writeheader()
            writer.writerows(ordered)


def make_session() -> requests.Session:
    session = requests.Session()
    retry = Retry(total=4, backoff_factor=2, status_forcelist=[429, 500, 502, 503, 504], allowed_methods=["GET"])
    session.mount("https://", HTTPAdapter(max_retries=retry))
    session.headers["User-Agent"] = config.HTTP_USER_AGENT
    return session


def download(session: requests.Session, url: str, dest: Path, **kwargs) -> requests.Response:
    """Stream a URL to dest atomically. Raises on any non-200 response."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    part = dest.with_name(dest.name + ".part")
    with session.get(url, stream=True, timeout=120, **kwargs) as resp:
        if resp.status_code != 200:
            raise IngestError(f"HTTP {resp.status_code} for {resp.url}: {resp.text[:200]}")
        with open(part, "wb") as fh:
            for chunk in resp.iter_content(chunk_size=1 << 20):
                fh.write(chunk)
    part.replace(dest)
    return resp


def local_game_date(iso_timestamp: str) -> date:
    ts = datetime.fromisoformat(iso_timestamp.replace("Z", "+00:00"))
    return ts.astimezone(ZoneInfo(config.CUTOFF_TIMEZONE)).date()


# ---------------------------------------------------------------- SportsDataverse play-by-play

def release_assets(session: requests.Session) -> dict[str, dict]:
    """Asset metadata (size, updated_at) from the GitHub API, or {} if the API is rate limited.

    The API allows 60 unauthenticated calls per hour. Downloads do not use it, so a
    rate limit only drops the remote_updated_at column from the manifest.
    """
    url = f"https://api.github.com/repos/{config.SDV_REPO}/releases/tags/{config.SDV_PBP_RELEASE}"
    resp = session.get(url, timeout=60)
    if resp.status_code != 200:
        print(f"  note: GitHub API returned HTTP {resp.status_code}; continuing without release timestamps")
        return {}
    return {a["name"]: a for a in resp.json()["assets"]}


def ingest_pbp(session: requests.Session, manifest: Manifest, refresh: bool) -> None:
    out_dir = config.RAW_DIR / "sportsdataverse" / config.SDV_PBP_RELEASE
    base = f"https://github.com/{config.SDV_REPO}/releases/download/{config.SDV_PBP_RELEASE}"
    pending = [s for s in config.ALL_SEASONS
               if not manifest.is_frozen(out_dir / config.SDV_PBP_ASSET.format(season=s), refresh)]
    assets = release_assets(session) if pending else {}

    for season in config.ALL_SEASONS:
        name = config.SDV_PBP_ASSET.format(season=season)
        dest, url = out_dir / name, f"{base}/{name}"
        if season not in pending:
            print(f"  frozen   {rel(dest)}")
            continue
        print(f"  download {name}")
        resp = download(session, url, dest)
        expected = assets.get(name, {}).get("size") or int(resp.headers.get("Content-Length", 0))
        if expected and dest.stat().st_size != expected:
            raise IngestError(f"{name}: got {dest.stat().st_size} bytes, expected {expected}")
        manifest.record(
            dest, source="sportsdataverse", dataset=config.SDV_PBP_RELEASE, season=season,
            url=url, remote_updated_at=assets.get(name, {}).get("updated_at"), required=True,
        )

    dest = config.RAW_DIR / "sportsdataverse" / "reference" / "cfbfastR_DATASETS.md"
    if not manifest.is_frozen(dest, refresh):
        download(session, config.SDV_DATA_DICTIONARY_URL, dest)
        manifest.record(dest, source="sportsdataverse", dataset="data_dictionary",
                        url=config.SDV_DATA_DICTIONARY_URL, required=False)


# ---------------------------------------------------------------- CollegeFootballData API

def cfbd_requests() -> list[tuple[str, str, dict, bool]]:
    """(dataset, path, params, required). About 35 calls, well inside the 3,000/month Academic tier."""
    reqs = []
    for season in config.ALL_SEASONS:
        reqs += [
            ("games", "/games", {"year": season, "seasonType": "both"}, True),
            ("teams_fbs", "/teams/fbs", {"year": season}, True),
            ("lines", "/lines", {"year": season, "seasonType": "both"}, False),
        ]
    y = config.CURRENT_SEASON
    for team in TEAMS:
        reqs += [
            ("games_teams", "/games/teams", {"year": y, "team": team}, True),
            ("stats_game_advanced", "/stats/game/advanced", {"year": y, "team": team}, True),
            ("drives", "/drives", {"year": y, "team": team}, False),
            ("passing_plays", "/passing/plays", {"year": y, "team": team}, False),
            ("rushing_plays", "/rushing/plays", {"year": y, "team": team}, False),
        ]
        reqs += [("plays", "/plays", {"year": y, "week": w, "team": team}, False) for w in config.CURRENT_WEEKS]
        # 2026 context: how new each program is (descriptive only, never a model input)
        reqs.append(("coaches", "/coaches", {"team": team, "minYear": min(config.ALL_SEASONS), "maxYear": y}, False))
    reqs += [
        ("calendar", "/calendar", {"year": y}, False),
        ("ratings_sp", "/ratings/sp", {"year": y - 1}, False),
        ("ratings_sp", "/ratings/sp", {"year": y}, False),
        ("returning_production", "/player/returning", {"year": y}, False),
        ("transfer_portal", "/player/portal", {"year": y}, False),
    ]
    return reqs


def cfbd_dest(dataset: str, params: dict) -> Path:
    slug = "_".join(f"{k}-{v}" for k, v in sorted(params.items())).replace(" ", "-")
    return config.RAW_DIR / "cfbd" / dataset / f"{slug}.json"


def fetch_cfbd(session, manifest, refresh, dataset, path, params, required, failures) -> Path | None:
    dest = cfbd_dest(dataset, params)
    if manifest.is_frozen(dest, refresh):
        print(f"  frozen   {rel(dest)}")
        return dest
    headers = {"Authorization": f"Bearer {config.get_cfbd_api_key()}", "Accept": "application/json"}
    try:
        resp = download(session, config.CFBD_HOST + path, dest, params=params, headers=headers)
    except IngestError as exc:
        if required:
            raise
        failures.append(f"optional CFBD {path} {params}: {exc}")
        print(f"  SKIPPED  {path} {params}: {exc}")
        return None
    records = json.loads(dest.read_bytes())
    remaining = resp.headers.get("X-CallLimit-Remaining", "")
    print(f"  saved    {rel(dest)} ({len(records) if isinstance(records, list) else 1} records"
          + (f", {remaining} calls left)" if remaining else ")"))
    manifest.record(dest, source="cfbd", dataset=dataset, season=params.get("year") or params.get("id", ""),
                    url=config.CFBD_HOST + path, params=json.dumps(params, sort_keys=True), required=required,
                    notes=f"records={len(records) if isinstance(records, list) else 1}")
    return dest


def matchup_games_through_cutoff(games_path: Path) -> list[dict]:
    games = json.loads(games_path.read_bytes())
    return [
        g for g in games
        if (g["homeTeam"] in TEAMS or g["awayTeam"] in TEAMS)
        and g["completed"] and local_game_date(g["startDate"]) <= CUTOFF
    ]


def ingest_cfbd(session: requests.Session, manifest: Manifest, refresh: bool, failures: list) -> None:
    config.get_cfbd_api_key()  # fail before any request if the key is missing
    for dataset, path, params, required in cfbd_requests():
        fetch_cfbd(session, manifest, refresh, dataset, path, params, required, failures)

    games_path = cfbd_dest("games", {"year": config.CURRENT_SEASON, "seasonType": "both"})
    for game in matchup_games_through_cutoff(games_path):
        fetch_cfbd(session, manifest, refresh, "game_box_advanced", "/game/box/advanced",
                   {"id": game["id"]}, True, failures)


# ---------------------------------------------------------------- Official team box scores

def fetch_page(session, manifest, refresh, url, dest, dataset, notes="") -> str:
    if manifest.is_frozen(dest, refresh):
        print(f"  frozen   {rel(dest)}")
    else:
        download(session, url, dest)
        manifest.record(dest, source="official", dataset=dataset, season=config.CURRENT_SEASON,
                        url=url, required=True, notes=notes)
        print(f"  saved    {rel(dest)}")
    return dest.read_text(encoding="utf-8", errors="replace").replace("\\u002F", "/")


def ingest_official(session: requests.Session, manifest: Manifest, refresh: bool) -> None:
    season = config.CURRENT_SEASON

    # Auburn: auburntigers.com box score pages point to WMT, which serves the finalized stats as JSON.
    aub_dir = config.RAW_DIR / "official" / "auburn"
    schedule = fetch_page(session, manifest, refresh, config.AUBURN_SCHEDULE_URL,
                          aub_dir / f"schedule_{season}.html", "auburn_schedule")
    boxscore_ids = sorted(set(re.findall(r'href="/boxscore/(\d+)"', schedule)))
    if not boxscore_ids:
        raise IngestError("No box score links found on the Auburn schedule page")
    for box_id in boxscore_ids:
        page = fetch_page(session, manifest, refresh, config.AUBURN_BOXSCORE_URL.format(boxscore_id=box_id),
                          aub_dir / f"boxscore_{box_id}.html", "auburn_boxscore_page")
        wmt_ids = set(re.findall(r"wmt\.games/auburn/stats/match(?:/full)?/(\d+)", page))
        if len(wmt_ids) != 1:
            raise IngestError(f"Auburn box score {box_id}: expected one WMT match id, found {sorted(wmt_ids)}")
        wmt_id = wmt_ids.pop()
        fetch_page(session, manifest, refresh, config.WMT_GAME_API_URL.format(wmt_id=wmt_id),
                   aub_dir / f"wmt_game_{wmt_id}.json", "auburn_wmt_game", notes=f"boxscore_id={box_id}")

    # Florida: floridagators.com Sidearm box score pages carry the team stats as HTML tables.
    fla_dir = config.RAW_DIR / "official" / "florida"
    schedule = fetch_page(session, manifest, refresh, config.FLORIDA_SCHEDULE_URL,
                          fla_dir / f"schedule_{season}.html", "florida_schedule")
    links = sorted(set(re.findall(rf"/sports/football/stats/{season}/[a-z0-9-]+/boxscore/\d+", schedule)))
    if not links:
        raise IngestError("No box score links found on the Florida schedule page")
    for link in links:
        slug, box_id = re.search(r"/([a-z0-9-]+)/boxscore/(\d+)$", link).groups()
        fetch_page(session, manifest, refresh, config.FLORIDA_SITE + link,
                   fla_dir / f"boxscore_{box_id}_{slug}.html", "florida_boxscore_page", notes=f"opponent={slug}")


# ---------------------------------------------------------------- Verification

def norm(name: str) -> str:
    return re.sub(r"[^a-z0-9]", "", name.lower())


def verify(manifest: Manifest) -> list[str]:
    problems = []
    pbp_dir = config.RAW_DIR / "sportsdataverse" / config.SDV_PBP_RELEASE

    print("\nPlay-by-play seasons")
    for season in config.ALL_SEASONS:
        path = pbp_dir / config.SDV_PBP_ASSET.format(season=season)
        if not path.exists():
            problems.append(f"missing pbp {season}")
            continue
        meta = pq.read_metadata(path)
        missing = sorted(set(config.REQUIRED_PBP_COLUMNS) - set(meta.schema.names))
        games = pq.read_table(path, columns=["game_id"]).column("game_id").unique()
        print(f"  {season}: {meta.num_rows:>7,} plays  {len(games):>4} games  {meta.num_columns} columns"
              + (f"  MISSING {missing}" if missing else ""))
        if missing:
            problems.append(f"pbp {season} missing required columns {missing}")

    games_path = cfbd_dest("games", {"year": config.CURRENT_SEASON, "seasonType": "both"})
    if not games_path.exists():
        return problems + ["CFBD 2026 games not downloaded"]
    games = matchup_games_through_cutoff(games_path)

    pbp = pd.read_parquet(pbp_dir / config.SDV_PBP_ASSET.format(season=config.CURRENT_SEASON),
                          columns=["game_id", "period", "completed", "pos_team"])
    wmt = [json.loads(p.read_bytes())["data"] for p in (config.RAW_DIR / "official" / "auburn").glob("wmt_game_*.json")]
    sidearm = {p.stem.split("_", 2)[2]: p for p in (config.RAW_DIR / "official" / "florida").glob("boxscore_*.html")}

    print(f"\n2026 matchup games through {config.ANALYSIS_CUTOFF}")
    for team in TEAMS:
        team_games = [g for g in games if team in (g["homeTeam"], g["awayTeam"])]
        opponents = {g["awayTeam"] if g["homeTeam"] == team else g["homeTeam"] for g in team_games}
        if opponents != config.EXPECTED_2026_OPPONENTS[team]:
            problems.append(f"{team} opponents {sorted(opponents)} != expected")
        for g in sorted(team_games, key=lambda g: g["startDate"]):
            opp = g["awayTeam"] if g["homeTeam"] == team else g["homeTeam"]
            team_pts = g["homePoints"] if g["homeTeam"] == team else g["awayPoints"]
            opp_pts = g["awayPoints"] if g["homeTeam"] == team else g["homePoints"]
            plays = pbp[pbp.game_id == g["id"]]
            pbp_ok = len(plays) > 0 and plays.period.max() >= 4 and bool(plays.completed.all())

            official = official_score(team, opp, wmt, sidearm)
            score_ok = official == (team_pts, opp_pts)
            print(f"  wk{g['week']} {team} {team_pts}-{opp_pts} {opp:<17} game {g['id']}  "
                  f"pbp rows={len(plays):<4} {'OK' if pbp_ok else 'INCOMPLETE'}  "
                  f"official score={official} {'MATCH' if score_ok else 'MISMATCH'}")
            if not pbp_ok:
                problems.append(f"pbp incomplete for game {g['id']}")
            if not score_ok:
                problems.append(f"official score mismatch for {team} vs {opp}")
    return problems


def official_score(team: str, opp: str, wmt: list[dict], sidearm: dict[str, Path]):
    if team == config.OFFENSE_TEAM:
        for game in wmt:
            names = {norm(c["nameTabular"]): c["score"] for c in game["competitors"]}
            if norm(team) in names and norm(opp) in names and game.get("stats_finalized"):
                return names[norm(team)], names[norm(opp)]
    else:
        path = sidearm.get(opp.lower().replace(" ", "-"))
        if path:
            linescore = pd.read_html(io.StringIO(path.read_text(encoding="utf-8", errors="replace")))[0]
            totals = dict(zip(linescore.iloc[:, 0].map(norm), linescore["Total"].astype(int)))
            team_pts = totals.pop(norm(team), None)
            if team_pts is not None and len(totals) == 1:
                return team_pts, totals.popitem()[1]
    return None


# ---------------------------------------------------------------- CLI

def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--only", nargs="+", choices=["pbp", "cfbd", "official", "verify"])
    parser.add_argument("--refresh", action="store_true", help="re-download files that are already frozen")
    args = parser.parse_args()
    steps = args.only or ["pbp", "cfbd", "official", "verify"]

    session, manifest, failures = make_session(), Manifest(config.MANIFEST_PATH, refresh=args.refresh), []
    if "pbp" in steps:
        print("SportsDataverse play-by-play")
        ingest_pbp(session, manifest, args.refresh)
    if "cfbd" in steps:
        print("CollegeFootballData API")
        ingest_cfbd(session, manifest, args.refresh, failures)
    if "official" in steps:
        print("Official box scores")
        ingest_official(session, manifest, args.refresh)
    if "verify" in steps:
        failures += verify(manifest)

    print(f"\nManifest: {rel(config.MANIFEST_PATH)} ({len(manifest.rows)} files)")
    for failure in failures:
        print(f"  PROBLEM: {failure}")
    print("All sources imported and verified." if not failures else f"{len(failures)} problem(s) found.")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
