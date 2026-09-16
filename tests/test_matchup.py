"""Shrinkage, robustness helpers, and team samples (docs/analysis_spec.md sections 7.4-8)."""

import numpy as np
import pandas as pd
import pytest

from src import config
from src.matchup import best_k, bootstrap_interval, cell_component, influential_play, shrink_factor


def simulated_teams(tau: float, sigma: float = 1.5, teams: int = 20_000, seed: int = 0):
    rng = np.random.default_rng(seed)
    n_early = rng.integers(10, 60, teams)
    n_late = rng.integers(100, 300, teams)
    truth = rng.normal(0, tau, teams)
    early = truth + rng.normal(0, sigma / np.sqrt(n_early))
    late = truth + rng.normal(0, sigma / np.sqrt(n_late))
    return early, n_early, late, n_late


def test_best_k_recovers_the_true_noise_ratio():
    tau, sigma = 0.15, 1.5
    k, _, _ = best_k(*simulated_teams(tau, sigma))
    true_k = sigma ** 2 / tau ** 2  # 100 plays
    assert 0.7 * true_k < k < 1.4 * true_k


def test_best_k_gives_no_trust_when_teams_do_not_differ():
    k, loss_k, loss_zero = best_k(*simulated_teams(tau=0.0))
    assert k == np.inf or k > 2_000


def test_shrink_factor():
    assert shrink_factor(30, 30) == 0.5
    assert shrink_factor(30, np.inf) == 0.0
    assert shrink_factor(0, 10) == 0.0


def component(residuals, k):
    frame = pd.DataFrame({"y": residuals, "pred": 0.0, "play_text": [f"play {i}" for i in range(len(residuals))]})
    c = cell_component(frame, "y", "pred", k)
    c["frame"] = frame
    return c


def test_influential_play_flips_an_edge_built_on_one_play():
    comps = {"offense": component([6.0] + [-0.1] * 19, k=10), "defense": component([-0.05] * 20, k=10)}
    edge = (comps["offense"]["shrunk"] + comps["defense"]["shrunk"]) / 2
    assert edge > 0
    without, text = influential_play(comps, edge)
    assert without < 0 and text.endswith("play 0")


def test_influential_play_keeps_a_broad_edge():
    comps = {"offense": component([0.3] * 30, k=10), "defense": component([0.2] * 30, k=10)}
    edge = (comps["offense"]["shrunk"] + comps["defense"]["shrunk"]) / 2
    without, _ = influential_play(comps, edge)
    assert without > 0


def test_bootstrap_interval_brackets_the_edge():
    rng = np.random.default_rng(1)
    comps = {"offense": component(rng.normal(0.2, 1, 40), k=20), "defense": component(rng.normal(0.1, 1, 40), k=20)}
    edge = (comps["offense"]["shrunk"] + comps["defense"]["shrunk"]) / 2
    lo, hi, se = bootstrap_interval(comps)
    assert lo < edge < hi and se > 0


# ---------------------------------------------------------------- outputs

TABLES = config.TABLES_DIR


@pytest.fixture(scope="module")
def findings():
    path = TABLES / "matchup_findings.csv"
    if not path.exists():
        pytest.skip("run `python -m src.matchup` first")
    return pd.read_csv(path)


def test_findings_cover_every_rollup_cell_and_metric(findings):
    assert len(findings) == 8
    assert set(findings.metric) == {"value", "explosive"}


def test_labels_follow_the_spec(findings):
    strongest = findings[findings.label == "strongest signal"]
    assert (strongest.checks_failed == 0).all() and (strongest.edge > 0).all()
    assert ((strongest.auburn_plays >= config.MIN_PLAYS_ELIGIBLE) & (strongest.florida_plays >= config.MIN_PLAYS_ELIGIBLE)).all()
    possible = findings[findings.label == "possible signal"]
    assert (possible.edge > 0).all() and (possible.checks_failed <= 1).all()
    assert not ((findings.edge <= 0) & (findings.label != "no clear signal")).any()


def test_shrunk_components_never_exceed_raw(findings):
    for team in ("auburn", "florida"):
        assert (findings[f"{team}_shrunk"].abs() <= findings[f"{team}_raw_residual"].abs() + 1e-12).all()


def test_early_season_is_regular_season_weeks_one_and_two():
    # Bowl and playoff games are also numbered week 1 in the play-by-play (change log #15).
    from src.matchup import early_season

    games = pd.DataFrame({"week": [1, 2, 3, 1, 2, 16], "game_season_type": ["regular", "regular", "regular", "postseason", "postseason", "regular"]})
    assert early_season(games).tolist() == [True, True, False, False, False, False]
