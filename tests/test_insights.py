"""Supporting analysis (docs/analysis_spec.md change log #16): it must reuse the frozen rules, not restate them."""

import numpy as np
import pandas as pd
import pytest

from src import config
from src.insights import success_rate

TABLES = ["insight_reliability", "insight_prediction", "insight_rank_intervals", "insight_pairings"]


@pytest.fixture(scope="module")
def tables():
    if not all((config.TABLES_DIR / f"{name}.csv").exists() for name in TABLES):
        pytest.skip("run `python -m src.insights` first")
    return {name: pd.read_csv(config.TABLES_DIR / f"{name}.csv") for name in TABLES}


def test_success_rate_follows_the_published_rule():
    plays = pd.DataFrame({"down": [1, 1, 2, 2, 3, 3, 4], "distance": [10, 10, 10, 10, 10, 10, 2],
                          "yards_gained": [5, 4, 7, 6, 10, 9, 2]})
    assert success_rate(plays).tolist() == [1, 0, 1, 0, 1, 0, 1]


def test_reliability_covers_both_sides_and_orders_sensibly(tables):
    d = tables["insight_reliability"]
    assert set(d.side) == {"offense", "defense"} and len(d) == 20
    assert (d.team_seasons > 600).all() and (d.k_plays > 0).all()
    offense = d[d.side == "offense"].set_index("measure")
    assert offense.loc["Pass rate", "k_plays"] < offense.loc["PPA per play", "k_plays"]
    assert offense.loc["PPA per play", "k_plays"] < offense.loc["Explosive rate over expected", "k_plays"]
    assert (offense.weight_after_two_games.between(0, 1)).all()


def test_shrinking_beats_taking_early_numbers_at_face_value(tables):
    d = tables["insight_prediction"]
    for (target, source), group in d.groupby(["target", "input"]):
        g = group.set_index("treatment")
        assert g.loc["shrunk", "weighted_rmse"] < g.loc["as measured", "weighted_rmse"], (target, source)
        assert g.loc["league average (no team data)", "rmse_improvement_vs_league_average"] == 0


def test_rank_intervals_are_wide_and_centered_on_the_shrunk_estimate(tables):
    d = tables["insight_rank_intervals"]
    assert len(d) > 100 and (d.posterior_sd > 0).all()
    assert (d.rank_interval_width > 1).all()
    assert (d.shrunk_ppa_over_expected.abs() <= d.raw_ppa_over_expected.abs() + 1e-12).all()
    best, worst = d.sort_values("rank_estimate").iloc[0], d.sort_values("rank_estimate").iloc[-1]
    assert best.shrunk_ppa_over_expected > worst.shrunk_ppa_over_expected


def test_pairings_reproduce_every_frozen_finding(tables):
    findings = pd.read_csv(config.TABLES_DIR / "matchup_findings.csv")
    cells = tables["insight_pairings"].query("play_family != 'any'")
    m = cells.merge(findings, on=["metric", "play_family", "down_group"], validate="one_to_one")
    assert len(m) == len(findings)
    assert np.allclose(m.auburn_florida_edge, m.edge, rtol=1e-9, atol=1e-12)
    assert (m.pairings > 10_000).all() and (m.offenses >= 100).all()
