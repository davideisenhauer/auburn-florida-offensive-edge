"""Verify the local environment before any data work.

Run from the project root:
    .venv/bin/python -m src.check_env

Uses at most two CFBD API calls: /info and /games for Auburn 2026.
"""

import importlib
import subprocess
import sys

from src import config

REQUIRED_PACKAGES = [
    "pandas", "numpy", "pyarrow", "duckdb", "sklearn", "xgboost",
    "matplotlib", "seaborn", "cfbd", "dotenv", "requests", "pytest",
]


def check(label: str, ok: bool, detail: str = "") -> bool:
    print(f"[{'PASS' if ok else 'FAIL'}] {label}" + (f": {detail}" if detail else ""))
    return ok


def main() -> int:
    results = []

    v = sys.version_info
    results.append(check("Python 3.12", (v.major, v.minor) == (3, 12), sys.version.split()[0]))

    for name in REQUIRED_PACKAGES:
        try:
            importlib.import_module(name)
            results.append(check(f"import {name}", True))
        except Exception as exc:  # xgboost raises XGBoostError, not ImportError
            results.append(check(f"import {name}", False, str(exc).splitlines()[0]))

    results.append(check(".env exists", config.ENV_FILE.exists(), str(config.ENV_FILE)))

    ignored = subprocess.run(
        ["git", "check-ignore", "-q", str(config.ENV_FILE)],
        cwd=config.PROJECT_ROOT, capture_output=True,
    ).returncode == 0
    results.append(check(".env is git-ignored", ignored))

    try:
        key = config.get_cfbd_api_key()
        results.append(check("CFBD_API_KEY is set", True, f"...{key[-4:]}"))
    except RuntimeError as exc:
        results.append(check("CFBD_API_KEY is set", False, str(exc)))
        return summarize(results)

    import cfbd

    with cfbd.ApiClient(config.cfbd_configuration()) as client:
        try:
            info = cfbd.InfoApi(client).get_user_info()
            results.append(check(
                "CFBD key accepted", True,
                f"tier={info.tier_name}, remaining={info.remaining_calls}/{info.monthly_limit}, "
                f"resets {info.reset_at}",
            ))
            if info.tier_name.lower() != "academic":
                print("       Note: tier is not Academic. Register with your auburn.edu email for 3,000 calls/month.")
        except cfbd.ApiException as exc:
            results.append(check("CFBD key accepted", False, f"HTTP {exc.status} {exc.reason}"))
            return summarize(results)

        games = cfbd.GamesApi(client).get_games(year=config.CURRENT_SEASON, team=config.OFFENSE_TEAM)
        rows = sorted(games, key=lambda g: g.start_date)
        results.append(check("CFBD /games returns Auburn 2026", len(rows) > 0, f"{len(rows)} games"))
        for g in rows:
            if g.completed:
                print(f"       wk{g.week} {g.away_team} {g.away_points} @ {g.home_team} {g.home_points}")

    return summarize(results)


def summarize(results: list[bool]) -> int:
    failed = results.count(False)
    print(f"\n{len(results) - failed} passed, {failed} failed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
