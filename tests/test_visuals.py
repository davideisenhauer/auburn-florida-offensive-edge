"""Every number on a public figure must match the analysis tables (docs/analysis_spec.md sections 6-8).

The data checks compare outputs/figures/*_data.csv, written by `python -m src.visuals`, with outputs/tables/.
Printed labels are parsed back into numbers, so a formatting bug cannot hide behind the same formatter.
The figure checks rebuild each figure and inspect its text and marks. Skipped until the tables and figures exist.
"""

import io
import re

import matplotlib
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import pytest
from matplotlib.colors import to_hex, to_rgb

from src import config

NAMES = ["v1_auburn_offense_ppa", "v2_florida_defense_ppa", "v3_explosive_plays", "v4_opportunity_map", "v5_two_game_reliability"]
SOURCES = ["team_cells_fine", "team_cells_rollup", "matchup_findings", "shrinkage_k"]
FINE_KEYS = ["play_family", "down_bin", "distance_bin"]
HEATMAPS = [("v1_auburn_offense_ppa", "Auburn", "offense"), ("v2_florida_defense_ppa", "Florida", "defense")]
RECOMMENDATION = re.compile(
    r"\b(should|recommend\w*|attack\w*|exploit\w*|target\w*|must|lean on|go-to|best bet|call more|run more|pass more)\b", re.I)


def close(a, b) -> bool:
    return np.allclose(np.asarray(a, dtype=float), np.asarray(b, dtype=float), rtol=1e-9, atol=1e-12, equal_nan=True)


def number(text: str) -> float:
    """First signed number in a label, reading the true minus sign."""
    match = re.search(r"[+−-]?\d+(?:\.\d+)?", str(text))
    assert match, f"no number in {text!r}"
    return float(match.group(0).replace("−", "-"))


@pytest.fixture(scope="module")
def tables() -> dict[str, pd.DataFrame]:
    if not all((config.TABLES_DIR / f"{name}.csv").exists() for name in SOURCES):
        pytest.skip("run `python -m src.matchup` first")
    return {name: pd.read_csv(config.TABLES_DIR / f"{name}.csv") for name in SOURCES}


@pytest.fixture(scope="module")
def saved() -> dict[str, pd.DataFrame]:
    if not all((config.FIGURES_DIR / f"{name}_data.csv").exists() for name in NAMES):
        pytest.skip("run `python -m src.visuals` first")
    return {name: pd.read_csv(config.FIGURES_DIR / f"{name}_data.csv") for name in NAMES}


@pytest.fixture(scope="module")
def built(tables):
    from src import visuals

    figures = {name: build() for name, build in visuals.FIGURE_BUILDERS.items()}
    yield figures
    for fig, _ in figures.values():
        plt.close(fig)


# ---------------------------------------------------------------- files are current

def test_every_figure_has_a_png_and_its_data(saved):
    for name in NAMES:
        png = config.FIGURES_DIR / f"{name}.png"
        assert png.exists() and png.stat().st_size > 50_000, name


def test_saved_data_matches_a_fresh_build_from_the_tables(built, saved):
    for name in NAMES:
        fresh = pd.read_csv(io.StringIO(built[name][1].to_csv(index=False)))
        pd.testing.assert_frame_equal(fresh, saved[name], check_exact=False, rtol=1e-12, obj=name)


# ---------------------------------------------------------------- V1 and V2

@pytest.mark.parametrize("name, team, side", HEATMAPS)
def test_heatmap_cells_match_team_cells_fine(name, team, side, tables, saved):
    fig_data = saved[name]
    fine = tables["team_cells_fine"]
    source = fine[(fine.team == team) & (fine.metric == "value")]
    assert len(fig_data) == 18 and not fig_data.duplicated(FINE_KEYS).any()
    assert (fig_data.team == team).all() and (fig_data.side == side).all() and (source.side == side).all()
    m = fig_data.merge(source, on=FINE_KEYS, how="left", suffixes=("", "_src"), validate="one_to_one")

    assert (m.plays == m.plays_src.fillna(0)).all()
    assert m.plays.sum() == source.plays.sum()  # every source play appears in some cell

    shown = m.plays >= config.MIN_PLAYS_DISPLAY
    assert close(m.shrunk_ppa_over_expected[shown], m.shrunk_residual[shown])
    assert close(m.raw_ppa_over_expected[shown], m.raw_residual[shown])
    assert m.loc[~shown, ["shrunk_ppa_over_expected", "raw_ppa_over_expected", "value_text", "raw_text"]].isna().all().all()


@pytest.mark.parametrize("name, team, side", HEATMAPS)
def test_heatmap_labels_follow_the_display_thresholds(name, team, side, tables, saved):
    d = saved[name]
    expected_tier = np.select([d.plays < config.MIN_PLAYS_DISPLAY, d.plays < config.MIN_PLAYS_ELIGIBLE],
                              ["hidden", "limited"], "eligible")
    assert (d.tier == expected_tier).all()
    source = tables["team_cells_fine"]
    source = source[(source.team == team) & (source.metric == "value")]
    agree = d.merge(source[FINE_KEYS + ["tier"]], on=FINE_KEYS, suffixes=("", "_src"))
    assert (agree.tier == agree.tier_src).all()

    assert (d.plays_text.map(number) == d.plays).all()  # a play count in every cell
    assert (d.status_text.fillna("").eq("limited sample") == (d.tier == "limited")).all()
    assert d.loc[d.tier == "hidden", "status_text"].str.startswith("hidden").all()

    shown = d[d.tier != "hidden"]
    assert all(abs(number(t) - v) <= 0.0005 + 1e-9 for t, v in zip(shown.value_text, shown.shrunk_ppa_over_expected))
    assert all(abs(number(t) - v) <= 0.005 + 1e-9 for t, v in zip(shown.raw_text, shown.raw_ppa_over_expected))


@pytest.mark.parametrize("name, team, side", HEATMAPS)
def test_heatmap_colors_run_from_auburns_perspective(name, team, side, saved):
    from src import visuals

    d = saved[name]
    shown = d[d.tier != "hidden"]
    assert (shown.shrunk_ppa_over_expected.abs() <= visuals.PPA_COLOR_LIMIT).all()  # nothing clipped
    assert to_hex(visuals.DIRECTION_CMAP(1.0)) == visuals.FAVORABLE and to_hex(visuals.DIRECTION_CMAP(0.0)) == visuals.UNFAVORABLE
    for value, fill in zip(shown.shrunk_ppa_over_expected, shown.fill):
        assert fill == visuals.direction_fill(value)
        r, _, b = to_rgb(fill)
        if value >= 0.001:
            assert b > r, (value, fill)
        elif value <= -0.001:
            assert r > b, (value, fill)
        assert visuals.contrast(visuals.text_on(fill), fill) >= 4.5
    assert (d.loc[d.tier == "hidden", "fill"] == visuals.SURFACE).all()  # hidden cells are blank, not "zero"


# ---------------------------------------------------------------- V3

def test_explosive_rates_match_team_cells_rollup(tables, saved):
    d = saved["v3_explosive_plays"]
    rollup = tables["team_cells_rollup"]
    source = rollup[rollup.metric == "explosive"]
    assert len(d) == 8
    m = d.merge(source, on=["team", "side", "play_family", "down_group"], how="left", suffixes=("", "_src"), validate="one_to_one")
    assert (m.plays == m.plays_src).all()
    assert close(m.observed_pct, m.observed * 100)
    assert close(m.expected_pct, m.expected * 100)
    assert close(m.difference_pts, m.raw_residual * 100)
    assert close(m.difference_pts, m.observed_pct - m.expected_pct)
    assert close(m.shrunk_pts, m.shrunk_residual * 100)
    assert (m.tier == m.tier_src).all()


def test_explosive_labels_and_colors(saved):
    from src import visuals

    d = saved["v3_explosive_plays"]
    for r in d.itertuples():
        assert abs(number(r.difference_text) - r.difference_pts) <= 0.05 + 1e-9
        assert abs(number(r.shrunk_text) - r.shrunk_pts) <= 0.005 + 1e-9
        observed, expected = (float(x) for x in re.findall(r"(\d+(?:\.\d+)?)%", r.rates_text))
        assert abs(observed - r.observed_pct) <= 0.05 + 1e-9 and abs(expected - r.expected_pct) <= 0.05 + 1e-9
        assert number(r.plays_text) == r.plays
        assert ("limited sample" == r.status_text) == (r.tier == "limited")
        favorable = r.difference_pts > 0  # positive = Auburn gained more, or Florida allowed more
        assert r.direction == ("favorable to Auburn" if favorable else "unfavorable to Auburn")
        assert r.observed_color == (visuals.FAVORABLE if favorable else visuals.UNFAVORABLE)


# ---------------------------------------------------------------- V4

def test_opportunity_map_matches_matchup_findings(tables, saved):
    from src import visuals

    d = saved["v4_opportunity_map"]
    keys = ["play_family", "down_group", "metric"]
    m = d.merge(tables["matchup_findings"], on=keys, how="left", suffixes=("", "_src"), validate="one_to_one")
    assert len(m) == 8
    for column in ("auburn_plays", "florida_plays", "checks_failed", "label"):
        assert (m[column] == m[f"{column}_src"]).all(), column
    for column in ("auburn_shrunk", "florida_shrunk", "edge", "edge_low_90", "edge_high_90"):
        assert close(m[column], m[f"{column}_src"]), column
    assert close(m.edge, (m.auburn_shrunk + m.florida_shrunk) / 2)
    assert (m.robust == m.robust_eligible).all()
    assert (m.marker_plays == m.auburn_plays + m.florida_plays).all()

    scale = np.where(m.metric == "value", 1.0, 100.0)
    assert close(m.plotted_edge, m.edge * scale)
    assert close(m.plotted_low_90, m.edge_low_90 * scale) and close(m.plotted_high_90, m.edge_high_90 * scale)
    assert (m.axis == np.where(m.metric == "value", "x", "y")).all()
    limit = np.where(m.metric == "value", visuals.X_LIMIT, visuals.Y_LIMIT)
    assert (m.plotted_low_90.abs() <= limit).all() and (m.plotted_high_90.abs() <= limit).all()  # no interval cut off

    for r in m.itertuples():
        assert f"{r.auburn_plays} Auburn / {r.florida_plays} Florida plays" in r.point_label
        limited = min(r.auburn_plays, r.florida_plays) < config.MIN_PLAYS_ELIGIBLE
        assert ("limited sample" in r.point_label) == limited


def test_opportunity_map_shows_the_frozen_labels_without_recommendations(built):
    fig, data = built["v4_opportunity_map"]
    title = fig.texts[0].get_text()
    if (data.label == "no clear signal").all():
        assert "no clear signal" in title
    assert not (data.label == "strongest signal").any() or "no clear signal" not in title

    annotations = [a for a in fig.findobj(matplotlib.text.Annotation) if a.get_gid() == "annotation"]
    assert 1 <= len(annotations) <= 3
    text = "\n".join(a.get_text() for a in annotations)
    covers_zero = int(((data.edge_low_90 <= 0) & (data.edge_high_90 >= 0)).sum())
    assert f"{covers_zero} of {len(data)} intervals include zero" in text
    for value in re.findall(r"\(([+−]\d\.\d+) PPA\)", text):  # the favorable edge quoted in a takeaway
        favorable = data[(data.metric == "value") & (data.edge > 0)]
        assert len(favorable) == 1 and abs(number(value) - favorable.edge.iloc[0]) <= 0.0005


def test_opportunity_map_direction_rules_match_the_heatmaps(built):
    from src import visuals

    fig, _ = built["v4_opportunity_map"]
    ax = fig.axes[0]
    rules = [line for line in ax.get_lines() if line.get_linewidth() == 5]
    assert len(rules) == 4
    for line in rules:
        x, y = np.asarray(line.get_xdata(), float), np.asarray(line.get_ydata(), float)
        positive = (x.max() > 0) if np.ptp(x) else (y.max() > 0)
        assert to_hex(line.get_color()) == (visuals.FAVORABLE if positive else visuals.UNFAVORABLE)


# ---------------------------------------------------------------- V5

def test_reliability_panel_matches_shrinkage_k(tables, saved):
    d = saved["v5_two_game_reliability"]
    keys = ["metric", "side", "play_family", "down_group"]
    m = d.merge(tables["shrinkage_k"], on=keys, how="left", suffixes=("", "_src"), validate="one_to_one")
    assert len(m) == 16
    assert close(m.weight_pct, m.shrink_at_median_early_plays * 100)
    assert close(m.early_late_correlation, m.early_late_correlation_src)
    assert close(m.median_early_plays, m.median_early_plays_src)
    assert close(m.k, m.k_src) and (m.team_seasons == m.team_seasons_src).all()
    for r in m.itertuples():
        assert abs(number(r.weight_text) - r.weight_pct) <= 0.5 + 1e-9
        assert abs(number(r.correlation_text) - r.early_late_correlation) <= 0.005 + 1e-9


# ---------------------------------------------------------------- rules for every figure

@pytest.mark.parametrize("name", NAMES)
def test_every_figure_carries_the_disclaimer_cutoff_and_ppa_wording(name, built):
    from src import visuals

    fig, _ = built[name]
    text = visuals.figure_text(fig)
    assert "Independent analysis" in text and "Not affiliated with Auburn" in text
    assert config.ANALYSIS_CUTOFF == "2026-09-12" and "Data through Sept. 12, 2026" in text
    assert "PPA" in text
    assert not re.search(r"\bEPA\b", text)
    assert not RECOMMENDATION.search(text), RECOMMENDATION.search(text)
    assert not fig.images and not fig.findobj(matplotlib.offsetbox.AnnotationBbox)  # no logos or pasted images
