"""Static figures for the public write-up. Reads only outputs/tables/ and writes PNGs to outputs/figures/.

Run from the project root (after src.matchup):
    .venv/bin/python -m src.visuals

Writes each figure with the exact numbers drawn on it:
    v1_auburn_offense_ppa.png     (+ _data.csv)  Auburn offense PPA over expected, down x distance x run/pass
    v2_florida_defense_ppa.png    (+ _data.csv)  Florida defense PPA allowed over expected, same layout
    v3_explosive_plays.png        (+ _data.csv)  explosive-play rate, observed vs. expected, both teams
    v4_opportunity_map.png        (+ _data.csv)  all eight matchup findings (hero)
    v5_two_game_reliability.png   (+ _data.csv)  how weakly two games predict the rest of a season

Color direction is fixed from Auburn's perspective in every figure: blue means more than the situation
normally produces for Auburn's offense (or allows for Florida's defense), red means less. Reliability and
other non-directional marks are neutral gray. Definitions are in docs/analysis_spec.md sections 6-8.
"""

import math
import re
from datetime import date

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.colors import LinearSegmentedColormap, Normalize, to_hex, to_rgb
from matplotlib.lines import Line2D
from matplotlib.patches import Rectangle
from matplotlib.transforms import blended_transform_factory

from src import config
from src.matchup import tier

# ---------------------------------------------------------------- style

# Reference data-viz palette, light surface. The blue/red poles pass the lightness, chroma, CVD
# (worst protan dE 21.6), and 3:1 contrast checks; text always uses the ink tokens.
SURFACE, INK, INK_2, MUTED, GRID, AXIS = "#fcfcfb", "#0b0b0b", "#52514e", "#898781", "#e1e0d9", "#c3c2b7"
FAVORABLE, UNFAVORABLE, NEUTRAL = "#2a78d6", "#e34948", "#f0efec"  # more for Auburn, less for Auburn, zero
DIRECTION_CMAP = LinearSegmentedColormap.from_list("auburn_perspective", [UNFAVORABLE, NEUTRAL, FAVORABLE])
PPA_COLOR_LIMIT = 0.025  # PPA per play at the ends of the V1/V2 color scale
DPI = 200
FIG_WIDTH = 12.0
MINUS = "−"

STYLE = {
    "font.family": ["Helvetica Neue", "Helvetica", "Arial", "DejaVu Sans"],  # resolved at save time, so named directly
    "figure.facecolor": SURFACE, "axes.facecolor": SURFACE, "savefig.facecolor": SURFACE,
    "text.color": INK, "axes.labelcolor": INK_2, "xtick.color": INK_2, "ytick.color": INK_2,
    "axes.edgecolor": AXIS, "xtick.major.size": 0, "ytick.major.size": 0,
}

AP_MONTHS = {1: "Jan.", 2: "Feb.", 3: "March", 4: "April", 5: "May", 6: "June", 7: "July",
             8: "Aug.", 9: "Sept.", 10: "Oct.", 11: "Nov.", 12: "Dec."}
CUTOFF = date.fromisoformat(config.ANALYSIS_CUTOFF)
CUTOFF_TEXT = f"Data through {AP_MONTHS[CUTOFF.month]} {CUTOFF.day}, {CUTOFF.year}"
DISCLAIMER = ("Independent analysis using public play-by-play data. Not affiliated with Auburn or Florida athletics. "
              "It does not account for private film, personnel, injury, or play-call information.")
PPA_NOTE = "PPA = predicted points added (CollegeFootballData, via SportsDataverse cfbfastR play-by-play)."
BYLINE = ""  # personal branding line; left blank until the author provides one

# ---------------------------------------------------------------- cells and labels

TEAMS = {"Auburn": "offense", "Florida": "defense"}
FAMILIES = ["run", "pass"]
DOWNS = ["1st", "2nd", "3rd/4th"]
DISTANCES = ["short 1-3", "medium 4-7", "long 8+"]
ROLLUP_CELLS = [("run", "standard downs"), ("run", "passing downs"), ("pass", "standard downs"), ("pass", "passing downs")]
DOWN_LABELS = {"1st": "1st down", "2nd": "2nd down", "3rd/4th": "3rd/4th down"}
DISTANCE_LABELS = {"short 1-3": "Short (1–3 yds)", "medium 4-7": "Medium (4–7)", "long 8+": "Long (8+)"}
FAMILY_NAMES = {"run": "Runs", "pass": "Passes"}
PASSING_DOWNS_NOTE = "Passing downs: 2nd and 8+, or 3rd/4th and 5+."


def signed(x: float, digits: int) -> str:
    """+0.012 / −0.012, with a true minus sign; values that round to zero print unsigned."""
    text = f"{x:+.{digits}f}"
    return f"{0:.{digits}f}" if float(text) == 0 else text.replace("-", MINUS)


def plays_text(n: int) -> str:
    return f"{n} play" if n == 1 else f"{n} plays"


def status_text(n: int) -> str:
    return {"hidden": f"hidden: under {config.MIN_PLAYS_DISPLAY} plays", "limited": "limited sample", "eligible": ""}[tier(n)]


def direction_fill(value: float) -> str:
    return to_hex(DIRECTION_CMAP(Normalize(-PPA_COLOR_LIMIT, PPA_COLOR_LIMIT)(value)))


def direction_color(value: float) -> str:
    return FAVORABLE if value > 0 else UNFAVORABLE if value < 0 else MUTED


def contrast(a: str, b: str) -> float:
    def luminance(color):
        rgb = np.array(to_rgb(color))
        rgb = np.where(rgb <= 0.03928, rgb / 12.92, ((rgb + 0.055) / 1.055) ** 2.4)
        return 0.2126 * rgb[0] + 0.7152 * rgb[1] + 0.0722 * rgb[2]
    hi, lo = sorted((luminance(a), luminance(b)), reverse=True)
    return (hi + 0.05) / (lo + 0.05)


def text_on(fill: str) -> str:
    return INK if contrast(INK, fill) >= contrast("#ffffff", fill) else "#ffffff"


def read_table(name: str) -> pd.DataFrame:
    return pd.read_csv(config.TABLES_DIR / name)


# ---------------------------------------------------------------- figure frame

def inches_from_top(fig, inches: float) -> float:
    return 1 - inches / fig.get_figheight()


def inches_from_bottom(fig, inches: float) -> float:
    return inches / fig.get_figheight()


def axes_rect(fig, left: float, top: float, width: float, height: float) -> list[float]:
    """Axes position from inches measured from the figure's left and top edges."""
    w, h = fig.get_size_inches()
    return [left / w, 1 - (top + height) / h, width / w, height / h]


def frame(fig, title: str, subtitle: list[str], source: str) -> None:
    left = 0.5 / FIG_WIDTH
    fig.text(left, inches_from_top(fig, 0.62), title, fontsize=22, fontweight="bold", color=INK, va="baseline")
    fig.text(left, inches_from_top(fig, 0.85), "\n".join(subtitle), fontsize=12, color=INK_2, va="top", linespacing=1.5)
    footer = [DISCLAIMER, f"{CUTOFF_TEXT} (2026 Weeks 1–2). {PPA_NOTE}", f"Source table: outputs/tables/{source}"]
    if BYLINE:
        footer.append(BYLINE)
    fig.text(left, inches_from_bottom(fig, 0.28), "\n".join(footer), fontsize=9, color=INK_2, va="bottom", linespacing=1.6)
    rule_y = inches_from_bottom(fig, 0.28 + 0.2 * len(footer) + 0.16)
    fig.add_artist(Line2D([left, 1 - left], [rule_y, rule_y], color=GRID, linewidth=1, transform=fig.transFigure))


# ---------------------------------------------------------------- V1 and V2: situation heatmaps

def heatmap_data(team: str) -> pd.DataFrame:
    """Every down x distance x play family cell for one team, including cells with no plays."""
    keys = ["play_family", "down_bin", "distance_bin"]
    fine = read_table("team_cells_fine.csv")
    fine = fine[(fine.team == team) & (fine.metric == "value")]
    grid = pd.MultiIndex.from_product([FAMILIES, DOWNS, DISTANCES], names=keys).to_frame(index=False)
    cells = grid.merge(fine, on=keys, how="left", validate="one_to_one")
    rows = []
    for c in cells.itertuples():
        n = 0 if pd.isna(c.plays) else int(c.plays)
        shown = tier(n) != "hidden"
        shrunk = c.shrunk_residual if shown else np.nan
        raw = c.raw_residual if shown else np.nan
        rows.append({
            "team": team, "side": TEAMS[team], "play_family": c.play_family, "down_bin": c.down_bin,
            "distance_bin": c.distance_bin, "plays": n, "tier": tier(n),
            "shrunk_ppa_over_expected": shrunk, "raw_ppa_over_expected": raw,
            "fill": direction_fill(shrunk) if shown else SURFACE,
            "value_text": signed(shrunk, 3) if shown else "",
            "raw_text": f"raw {signed(raw, 2)}" if shown else "",
            "plays_text": plays_text(n), "status_text": status_text(n),
        })
    return pd.DataFrame(rows)


def draw_heatmap(fig, cells: pd.DataFrame, family: str, rect: list[float], row_labels: bool) -> None:
    ax = fig.add_axes(rect)
    ax.set_xlim(0, 3)
    ax.set_ylim(3, 0)
    ax.axis("off")
    gap = 0.012
    for c in cells[cells.play_family == family].itertuples():
        col, row = DISTANCES.index(c.distance_bin), DOWNS.index(c.down_bin)
        shown = c.tier != "hidden"
        ax.add_patch(Rectangle((col + gap, row + gap), 1 - 2 * gap, 1 - 2 * gap, facecolor=c.fill,
                               edgecolor="none" if shown else GRID, linewidth=1))
        x = col + 0.5
        if shown:
            ink = text_on(c.fill)
            ax.text(x, row + 0.31, c.value_text, fontsize=18, fontweight="bold", color=ink, ha="center", va="center")
            ax.text(x, row + 0.53, c.raw_text, fontsize=10.5, color=ink, ha="center", va="center")
            ax.text(x, row + 0.70, c.plays_text, fontsize=10.5, color=ink, ha="center", va="center")
            if c.status_text:
                ax.text(x, row + 0.86, c.status_text, fontsize=10, color=ink, ha="center", va="center", fontstyle="italic")
        else:
            ax.text(x, row + 0.42, c.plays_text, fontsize=11, color=INK_2, ha="center", va="center")
            ax.text(x, row + 0.60, c.status_text, fontsize=9.5, color=INK_2, ha="center", va="center")
    for col, distance in enumerate(DISTANCES):
        ax.text(col + 0.5, -0.05, DISTANCE_LABELS[distance], fontsize=11.5, color=INK_2, ha="center", va="bottom")
    ax.text(0.012, -0.24, FAMILY_NAMES[family] + (" (sacks count as passes)" if family == "pass" else ""),
            fontsize=15, fontweight="bold", color=INK, ha="left", va="bottom")
    if row_labels:
        for row, down in enumerate(DOWNS):
            ax.text(-0.05, row + 0.5, DOWN_LABELS[down], fontsize=12.5, color=INK, ha="right", va="center")


def draw_ppa_color_key(fig, rect: list[float], title: str, left_label: str, right_label: str) -> None:
    ax = fig.add_axes(rect)
    limit = PPA_COLOR_LIMIT
    ax.imshow(np.linspace(-limit, limit, 512)[None, :], aspect="auto", cmap=DIRECTION_CMAP,
              norm=Normalize(-limit, limit), extent=(-limit, limit, 0, 1))
    ticks = [-0.02, -0.01, 0.0, 0.01, 0.02]
    ax.set_xticks(ticks, [signed(t, 2) for t in ticks])
    ax.set_yticks([])
    ax.tick_params(labelsize=10, colors=INK_2, pad=4)
    for spine in ax.spines.values():
        spine.set_visible(False)
    ax.text(0.5, 1.35, title, transform=ax.transAxes, fontsize=11.5, color=INK, ha="center", va="bottom")
    ax.text(0, 1.35, "← " + left_label, transform=ax.transAxes, fontsize=10.5, color=INK_2, ha="right", va="bottom")
    ax.text(1, 1.35, right_label + " →", transform=ax.transAxes, fontsize=10.5, color=INK_2, ha="left", va="bottom")


def heatmap_figure(team: str, title: str, subtitle: list[str], left_label: str, right_label: str):
    data = heatmap_data(team)
    with plt.rc_context(STYLE):
        fig = plt.figure(figsize=(FIG_WIDTH, 9.4))
        frame(fig, title, subtitle, "team_cells_fine.csv")
        for i, family in enumerate(FAMILIES):
            draw_heatmap(fig, data, family, axes_rect(fig, 1.75 + i * 5.0, 2.5, 4.6, 4.5), row_labels=i == 0)
        draw_ppa_color_key(fig, axes_rect(fig, 4.55, 7.75, 4.2, 0.2), "PPA per play over expected, after shrinkage",
                           left_label, right_label)
    return fig, data


def build_v1():
    return heatmap_figure(
        "Auburn", "Auburn offense: PPA over expected, by situation",
        ["2026 Auburn offense vs. Baylor and Southern Miss, garbage time excluded. Each play is compared with the league baseline",
         "for its down, distance, field position, score, clock, venue, and point spread. Big number and color: the estimate after",
         "two-game reliability shrinkage. Raw: the unshrunk average. Blue = more than expected for Auburn, red = less."],
        "less than expected", "more than expected")


def build_v2():
    return heatmap_figure(
        "Florida", "Florida defense: PPA allowed over expected, by situation",
        ["2026 Florida defense vs. Florida Atlantic and Campbell (FCS), garbage time excluded, compared with the same league baseline.",
         "Colors are from Auburn's perspective: blue = Florida allowed more than the situation normally allows, red = less.",
         "Big number and color: the estimate after two-game reliability shrinkage. Raw: the unshrunk average."],
        "Florida allowed less", "Florida allowed more")


# ---------------------------------------------------------------- V3: explosive plays

def explosive_data() -> pd.DataFrame:
    rollup = read_table("team_cells_rollup.csv")
    rollup = rollup[rollup.metric == "explosive"]
    rows = []
    for team, side in TEAMS.items():
        for family, group in ROLLUP_CELLS:
            c = rollup[(rollup.team == team) & (rollup.play_family == family) & (rollup.down_group == group)].iloc[0]
            n = int(c.plays)
            shown = tier(n) != "hidden"
            difference, shrunk = c.raw_residual * 100, c.shrunk_residual * 100
            rows.append({
                "team": team, "side": side, "play_family": family, "down_group": group, "plays": n, "tier": tier(n),
                "observed_pct": c.observed * 100 if shown else np.nan, "expected_pct": c.expected * 100 if shown else np.nan,
                "difference_pts": difference if shown else np.nan, "shrunk_pts": shrunk if shown else np.nan,
                "direction": ("favorable to Auburn" if difference > 0 else "unfavorable to Auburn") if shown else "",
                "observed_color": direction_color(difference) if shown else "",
                "rates_text": f"{c.observed * 100:.1f}% vs. {c.expected * 100:.1f}% expected" if shown else "",
                "difference_text": f"{signed(difference, 1)} pts" if shown else "",
                "shrunk_text": f"shrunk {signed(shrunk, 2)} pts" if shown else "",
                "plays_text": plays_text(n), "status_text": status_text(n),
            })
    return pd.DataFrame(rows)


def build_v3():
    data = explosive_data()
    x_max = 15
    with plt.rc_context(STYLE):
        fig = plt.figure(figsize=(FIG_WIDTH, 8.8))
        frame(fig, "Explosive plays (20+ yards): observed vs. expected",
              ["Share of snaps gaining 20 or more yards, 2026 Weeks 1–2, garbage time excluded. Expected = the league baseline for the",
               "same situations. Difference = observed minus expected, in percentage points. Shrunk = the difference after two-game",
               "reliability shrinkage, the number the matchup analysis uses. " + PASSING_DOWNS_NOTE],
              "team_cells_rollup.csv")
        handles = [
            Line2D([], [], linestyle="none", marker="o", markersize=9, markerfacecolor="none", markeredgecolor=INK_2, markeredgewidth=2),
            Line2D([], [], linestyle="none", marker="o", markersize=10, markerfacecolor=FAVORABLE, markeredgecolor=SURFACE, markeredgewidth=1.5),
            Line2D([], [], linestyle="none", marker="o", markersize=10, markerfacecolor=UNFAVORABLE, markeredgecolor=SURFACE, markeredgewidth=1.5),
        ]
        fig.legend(handles, ["Expected", "Observed: more than expected for Auburn (Auburn gained more, or Florida allowed more)",
                             "Observed: less than expected for Auburn"],
                   loc="upper left", bbox_to_anchor=(0.5 / FIG_WIDTH, inches_from_top(fig, 1.95)), ncol=1, frameon=False,
                   fontsize=10.5, handletextpad=0.4, labelspacing=0.35, borderaxespad=0)
        titles = {"Auburn": ("Auburn offense", "explosive-play rate"), "Florida": ("Florida defense", "explosive-play rate allowed")}
        for p, team in enumerate(TEAMS):
            ax = fig.add_axes(axes_rect(fig, 1.9 + p * 5.05, 3.55, 2.75, 3.6))
            rows = data[data.team == team].reset_index(drop=True)
            ax.set_xlim(0, x_max)
            ax.set_ylim(len(rows) - 0.5, -0.5)
            ax.set_xticks([0, 5, 10, 15], ["0%", "5%", "10%", "15%"])
            ax.set_yticks([])
            ax.grid(axis="x", color=GRID, linewidth=1)
            ax.set_axisbelow(True)
            ax.tick_params(labelsize=10.5)
            for spine in ax.spines.values():
                spine.set_visible(False)
            ax.text(0, -0.95, titles[team][0], fontsize=15, fontweight="bold", color=INK, ha="left", va="bottom")
            ax.text(0, -0.72, titles[team][1], fontsize=11, color=INK_2, ha="left", va="bottom")
            text_x = blended_transform_factory(ax.transAxes, ax.transData)
            for i, r in rows.iterrows():
                if p == 0:
                    ax.text(-0.06, i - 0.1, FAMILY_NAMES[r.play_family], transform=text_x, fontsize=12.5, fontweight="bold", ha="right", va="center")
                    ax.text(-0.06, i + 0.16, r.down_group, transform=text_x, fontsize=11, color=INK_2, ha="right", va="center")
                if r.tier == "hidden":
                    ax.text(1.05, i, f"{r.plays_text}\n{r.status_text}", transform=text_x, fontsize=10, color=INK_2, va="center")
                    continue
                ax.plot([r.expected_pct, r.observed_pct], [i, i], color=r.observed_color, linewidth=2.5, solid_capstyle="round", zorder=2)
                ax.scatter([r.observed_pct], [i], s=110, facecolor=r.observed_color, edgecolor=SURFACE, linewidth=2, zorder=4, clip_on=False)
                ax.scatter([r.expected_pct], [i], s=85, facecolor="none", edgecolor=INK_2, linewidth=2, zorder=5, clip_on=False)
                lines = [r.difference_text, r.plays_text + (f", {r.status_text}" if r.status_text else ""), r.shrunk_text]
                ax.text(1.05, i - 0.2, lines[0], transform=text_x, fontsize=12.5, fontweight="bold", color=INK, va="center")
                ax.text(1.05, i + 0.06, lines[1], transform=text_x, fontsize=10, color=INK_2, va="center")
                ax.text(1.05, i + 0.28, lines[2], transform=text_x, fontsize=10, color=INK_2, va="center")
    return fig, data


# ---------------------------------------------------------------- V4: opportunity map (hero)

X_LIMIT, Y_LIMIT = 0.04, 0.5  # PPA per play; percentage points of explosive-play rate
MARKER_AREA_PER_PLAY = 7.0
LABEL_POSITIONS = {  # (x, y, alignment) for each situation's label, at the open end of its own interval
    ("pass", "standard downs"): (-0.0030, 0.315, "left"),
    ("run", "standard downs"): (-0.0112, 0.125, "right"),
    ("run", "passing downs"): (0.0045, 0.200, "left"),
    ("pass", "passing downs"): (-0.0140, -0.400, "right"),
}


def opportunity_data() -> pd.DataFrame:
    findings = read_table("matchup_findings.csv")
    rows = []
    for f in findings.itertuples():
        scale = 1 if f.metric == "value" else 100
        limited = min(f.auburn_plays, f.florida_plays) < config.MIN_PLAYS_ELIGIBLE
        rows.append({
            "play_family": f.play_family, "down_group": f.down_group, "metric": f.metric,
            "axis": "x" if f.metric == "value" else "y",
            "units": "PPA per play" if f.metric == "value" else "percentage points of explosive-play rate",
            "auburn_plays": int(f.auburn_plays), "florida_plays": int(f.florida_plays),
            "marker_plays": int(f.auburn_plays + f.florida_plays),
            "auburn_shrunk": f.auburn_shrunk, "florida_shrunk": f.florida_shrunk,
            "edge": f.edge, "edge_low_90": f.edge_low_90, "edge_high_90": f.edge_high_90,
            "plotted_edge": f.edge * scale, "plotted_low_90": f.edge_low_90 * scale, "plotted_high_90": f.edge_high_90 * scale,
            "checks_failed": int(f.checks_failed), "failed_checks": "" if pd.isna(f.failed_checks) else str(f.failed_checks),
            "label": f.label, "robust": bool(f.robust_eligible),
            "interval_style": "holds under every check" if f.robust_eligible else "fails a check or limited sample",
            "point_label": (f"{FAMILY_NAMES[f.play_family]}, {f.down_group}\n"
                            f"{f.auburn_plays} Auburn / {f.florida_plays} Florida plays" + ("\nlimited sample" if limited else "")),
            "influential_play": f.influential_play,
        })
    return pd.DataFrame(rows)


def opportunity_annotations(data: pd.DataFrame) -> list[dict]:
    """At most three takeaways, all computed from the findings table."""
    notes = []
    favorable = data[data.edge > 0]
    if len(favorable) == 1 and "7" in favorable.iloc[0].failed_checks.split(", "):
        f = favorable.iloc[0]
        yards = re.search(r"for (\d+) yards?", f.influential_play)
        play = ("run" if " rush " in f" {f.influential_play} " else "pass" if " pass " in f" {f.influential_play} " else "play")
        without = f"one {yards.group(1)}-yard {play}" if yards else "a single play"
        units = "PPA" if f.metric == "value" else "pts"
        explosive = data[(data.play_family == f.play_family) & (data.down_group == f.down_group) & (data.metric == "explosive")].iloc[0]
        value = data[(data.play_family == f.play_family) & (data.down_group == f.down_group) & (data.metric == "value")].iloc[0]
        notes.append({"text": f"The only edge leaning Auburn's way\n({signed(f.plotted_edge, 3)} {units}) flips without\n"
                              f"{without}, so no claim is made",
                      "xy": (value.plotted_edge, explosive.plotted_edge), "xytext": (0.0055, -0.21)})
    covers_zero = int(((data.edge_low_90 <= 0) & (data.edge_high_90 >= 0)).sum())
    notes.append({"text": f"{covers_zero} of {len(data)} intervals include zero", "xy": None, "xytext": (0.0055, -0.45)})
    robust = data[data.robust]
    if len(robust):
        ppa = robust[robust.metric == "value"].edge.abs().max()
        pts = robust[robust.metric == "explosive"].plotted_edge.abs().max()
        limits = " or ".join(part for part in (
            f"{math.ceil(ppa * 1000) / 1000:.3f} PPA" if pd.notna(ppa) else "",
            f"{math.ceil(pts * 100) / 100:.2f} pts" if pd.notna(pts) else "") if part)
        notes.append({"text": f"The {len(robust)} findings that hold under every check\nare each within {limits} of zero",
                      "xy": None, "xytext": (-0.0385, 0.465)})
    return notes[:3]


def build_v4():
    data = opportunity_data()
    all_clear = (data.label == "no clear signal").all()
    title = ("Auburn offense vs. Florida defense: no clear signal" if all_clear
             else "Auburn offense vs. Florida defense: matchup findings")
    strong = {"color": INK, "linewidth": 2.4, "solid_capstyle": "round", "zorder": 3}
    weak = {"color": MUTED, "linewidth": 1.4, "solid_capstyle": "round", "zorder": 2}
    with plt.rc_context(STYLE):
        fig = plt.figure(figsize=(FIG_WIDTH, 10.6))
        frame(fig, title,
              [f"All {len(data)} findings (4 situations × 2 measures) carry the frozen label “{data.label.iloc[0]}.”" if all_clear
               else f"{len(data)} findings (4 situations × 2 measures).",
               "Edge = average of Auburn's offense and Florida's defense, each measured against the league baseline after two-game",
               "reliability shrinkage. Right and up = better for Auburn. Lines show 90% intervals. " + PASSING_DOWNS_NOTE],
              "matchup_findings.csv")
        ax = fig.add_axes(axes_rect(fig, 1.25, 2.2, 7.1, 6.45))
        ax.set_xlim(-X_LIMIT, X_LIMIT)
        ax.set_ylim(-Y_LIMIT, Y_LIMIT)
        xticks, yticks = np.round(np.arange(-0.04, 0.0401, 0.01), 3), np.round(np.arange(-0.5, 0.501, 0.25), 2)
        ax.set_xticks(xticks, [signed(t, 2) for t in xticks])
        ax.set_yticks(yticks, [signed(t, 2) for t in yticks])
        ax.tick_params(labelsize=10.5, pad=8)
        ax.grid(color=GRID, linewidth=1)
        ax.set_axisbelow(True)
        for spine in ax.spines.values():
            spine.set_visible(False)
        ax.axhline(0, color=AXIS, linewidth=1.3, zorder=1)
        ax.axvline(0, color=AXIS, linewidth=1.3, zorder=1)
        key = {"linewidth": 5, "solid_capstyle": "butt", "clip_on": False, "zorder": 6}
        ax.plot([-X_LIMIT, 0], [-Y_LIMIT, -Y_LIMIT], color=UNFAVORABLE, **key)
        ax.plot([0, X_LIMIT], [-Y_LIMIT, -Y_LIMIT], color=FAVORABLE, **key)
        ax.plot([-X_LIMIT, -X_LIMIT], [-Y_LIMIT, 0], color=UNFAVORABLE, **key)
        ax.plot([-X_LIMIT, -X_LIMIT], [0, Y_LIMIT], color=FAVORABLE, **key)
        ax.set_xlabel("PPA edge per play   (← less for Auburn  ·  more for Auburn →)", fontsize=11.5, labelpad=10)
        ax.set_ylabel("Explosive-play edge, percentage points   (← less  ·  more →)", fontsize=11.5, labelpad=10)

        for family, group in ROLLUP_CELLS:
            cell = data[(data.play_family == family) & (data.down_group == group)].set_index("metric")
            value, explosive = cell.loc["value"], cell.loc["explosive"]
            x, y = value.plotted_edge, explosive.plotted_edge
            ax.plot([value.plotted_low_90, value.plotted_high_90], [y, y], marker="|", markersize=8, **(strong if value.robust else weak))
            ax.plot([x, x], [explosive.plotted_low_90, explosive.plotted_high_90], marker="_", markersize=8, **(strong if explosive.robust else weak))
            both = value.robust and explosive.robust
            ax.scatter([x], [y], s=value.marker_plays * MARKER_AREA_PER_PLAY, facecolor=INK_2 if both else SURFACE,
                       edgecolor=SURFACE if both else INK_2, linewidth=2, zorder=5)
            label_x, label_y, align = LABEL_POSITIONS.get((family, group), (x, y, "left"))
            ax.annotate(value.point_label, (x, y), xytext=(label_x, label_y), textcoords="data",
                        fontsize=10.5, color=INK, ha=align, va="center", linespacing=1.35, zorder=7, gid="point_label",
                        arrowprops={"arrowstyle": "-", "color": MUTED, "linewidth": 0.8, "shrinkA": 3, "shrinkB": 7,
                                    "relpos": (1, 0.5) if align == "right" else (0, 0.5)})

        for note in opportunity_annotations(data):
            arrow = {"arrowstyle": "-|>", "color": INK_2, "linewidth": 1, "shrinkA": 4, "shrinkB": 9, "mutation_scale": 10}
            ax.annotate(note["text"], note["xy"] or note["xytext"], xytext=note["xytext"], textcoords="data",
                        fontsize=10.5, fontweight="bold", color=INK, ha="left", va="center", linespacing=1.35, zorder=8,
                        gid="annotation", arrowprops=arrow if note["xy"] else None)

        legend_x = 8.85 / FIG_WIDTH
        fig.text(legend_x, inches_from_top(fig, 2.25), "How to read", fontsize=13, fontweight="bold", color=INK, va="top")
        handles = [
            Line2D([], [], **{k: v for k, v in strong.items() if k != "zorder"}),
            Line2D([], [], **{k: v for k, v in weak.items() if k != "zorder"}),
            Line2D([], [], linestyle="none", marker="o", markersize=13, markerfacecolor=INK_2, markeredgecolor=SURFACE, markeredgewidth=2),
            Line2D([], [], linestyle="none", marker="o", markersize=13, markerfacecolor=SURFACE, markeredgecolor=INK_2, markeredgewidth=2),
            Line2D([], [], linestyle="none", marker="o", markersize=math.sqrt(30 * MARKER_AREA_PER_PLAY), markerfacecolor=SURFACE, markeredgecolor=MUTED),
            Line2D([], [], linestyle="none", marker="o", markersize=math.sqrt(90 * MARKER_AREA_PER_PLAY), markerfacecolor=SURFACE, markeredgecolor=MUTED),
        ]
        labels = ["Holds its direction under every\nrobustness check, 15+ plays\nfor each team",
                  "Fails at least one check,\nor limited sample",
                  "Both measures hold", "At least one measure does not",
                  "30 plays", "90 plays (Auburn offense +\nFlorida defense)"]
        fig.legend(handles, labels, loc="upper left", bbox_to_anchor=(legend_x, inches_from_top(fig, 2.7)), frameon=False,
                   fontsize=10.5, labelspacing=1.3, handlelength=2.6, handletextpad=0.9, borderaxespad=0, borderpad=0)
        fig.text(legend_x, inches_from_top(fig, 7.35),
                 "Blue and red rules on the axes mark\nthe direction: blue = better for Auburn.\n\n"
                 "Robustness checks: other baselines,\ngarbage time, penalties, giveaways,\nalternate explosive definition, each\n"
                 "game left out, most influential play.",
                 fontsize=10, color=INK_2, va="top", linespacing=1.45)
    return fig, data


# ---------------------------------------------------------------- V5: two-game reliability

def reliability_data() -> pd.DataFrame:
    k = read_table("shrinkage_k.csv")
    rows = []
    for metric, metric_name in (("value", "PPA"), ("explosive", "Explosive plays")):
        for side, side_name in (("offense", "offenses"), ("defense", "defenses")):
            for family, group in ROLLUP_CELLS:
                r = k[(k.metric == metric) & (k.side == side) & (k.play_family == family) & (k.down_group == group)].iloc[0]
                rows.append({
                    "metric": metric, "side": side, "play_family": family, "down_group": group,
                    "group_label": f"{metric_name}, {side_name}", "row_label": f"{FAMILY_NAMES[family]}, {group}",
                    "k": r.k, "team_seasons": int(r.team_seasons), "median_early_plays": r.median_early_plays,
                    "weight_pct": r.shrink_at_median_early_plays * 100, "early_late_correlation": r.early_late_correlation,
                    "weight_text": f"{r.shrink_at_median_early_plays * 100:.0f}%",
                    "plays_text": f"{r.median_early_plays:.0f}", "correlation_text": f"{r.early_late_correlation:.2f}".replace("-", MINUS),
                })
    return pd.DataFrame(rows)


def build_v5():
    data = reliability_data()
    low, high = data.weight_pct.min(), data.weight_pct.max()
    seasons = f"{min(config.HISTORICAL_SEASONS)}–{max(config.HISTORICAL_SEASONS)}"
    with plt.rc_context(STYLE):
        fig = plt.figure(figsize=(FIG_WIDTH, 10.75))
        frame(fig, "Two games are mostly noise",
              [f"For each of {data.team_seasons.max()} FBS team-seasons ({seasons}), how much weight did a team's Weeks 1–2 result in a situation",
               "(vs. the league baseline) deserve when predicting its result in that situation for the rest of the season?",
               f"At a typical two-game sample, the best weight was {low:.0f}% to {high:.0f}%. Older seasons are used only for this test, never",
               "to describe the 2026 teams. The same reliability estimates set how far the 2026 Auburn and Florida numbers are shrunk."],
              "shrinkage_k.csv")
        top, row_h, group_gap = 3.3, 0.3, 0.42
        positions, y = [], 0.0
        for i in range(len(data)):
            if i and i % 4 == 0:
                y += group_gap
            positions.append(y)
            y += row_h
        ax = fig.add_axes(axes_rect(fig, 3.2, top, 5.2, y))
        ax.set_xlim(0, 100)
        ax.set_ylim(y - row_h / 2, -row_h / 2)
        ax.set_xticks([0, 25, 50, 75, 100], ["0%", "25%", "50%", "75%", "100%"])
        ax.xaxis.tick_top()
        ax.set_yticks([])
        ax.tick_params(labelsize=10.5, pad=6)
        ax.grid(axis="x", color=GRID, linewidth=1)
        ax.set_axisbelow(True)
        for spine in ax.spines.values():
            spine.set_visible(False)
        ax.axvline(0, color=AXIS, linewidth=1.3, zorder=1)
        label_x = blended_transform_factory(ax.transAxes, ax.transData)
        for i, (r, pos) in enumerate(zip(data.itertuples(), positions)):
            if i % 4 == 0:
                ax.text(-0.52, pos - 0.3, r.group_label, transform=label_x, fontsize=12.5, fontweight="bold", color=INK, va="center")
            ax.text(-0.5, pos, r.row_label, transform=label_x, fontsize=11, color=INK, va="center")
            ax.scatter([r.weight_pct], [pos], s=80, facecolor=INK_2, edgecolor=SURFACE, linewidth=2, zorder=4)
            ax.text(r.weight_pct + 2.2, pos, r.weight_text, fontsize=11, fontweight="bold", color=INK, va="center")
            ax.text(1.1, pos, r.plays_text, transform=label_x, fontsize=11, color=INK_2, ha="center", va="center")
            ax.text(1.42, pos, r.correlation_text, transform=label_x, fontsize=11, color=INK_2, ha="center", va="center")
        header_y = -row_h / 2 - 0.55
        ax.text(0, header_y, "Weight a two-game result deserves", transform=label_x, fontsize=11.5, fontweight="bold", color=INK, va="bottom")
        ax.text(1.1, header_y, "Typical plays\nin two games", transform=label_x, fontsize=10.5, color=INK, ha="center", va="bottom")
        ax.text(1.42, header_y, "Correlation, Weeks 1–2\nvs. rest of season", transform=label_x, fontsize=10.5, color=INK, ha="center", va="bottom")
        ax.annotate("100% = taking two games at face value", (100, positions[0]), xytext=(97.5, positions[0]),
                    fontsize=10.5, color=INK_2, ha="right", va="center", gid="annotation",
                    bbox={"facecolor": SURFACE, "edgecolor": "none", "pad": 3})
    return fig, data


# ---------------------------------------------------------------- V6: what two games can and cannot tell you

RELIABILITY_FAMILIES = {"identity": "What the offense chooses to do", "efficiency": "How well it is going",
                        "adjusted": "How well it is going, adjusted for opponent and situation"}
SEASON_GAMES = 12


def reliability_spectrum_data() -> pd.DataFrame:
    d = read_table("insight_reliability.csv")
    d = d[d.side == "offense"].copy()
    d["family_label"] = d.family.map(RELIABILITY_FAMILIES)
    d = d.sort_values("games_to_half_weight").reset_index(drop=True)
    d["games_text"] = d.games_to_half_weight.map(lambda g: f"{g:.1f} games")
    d["weight_text"] = (d.weight_after_two_games * 100).map(lambda w: f"{w:.0f}%")
    d["correlation_text"] = d.early_late_correlation.map(lambda c: f"{c:.2f}".replace("-", MINUS))
    return d[["side", "measure", "family", "family_label", "team_seasons", "median_early_plays", "plays_per_game",
              "k_plays", "weight_after_two_games", "games_to_half_weight", "early_late_correlation",
              "games_text", "weight_text", "correlation_text"]]


def build_v6():
    data = reliability_spectrum_data()
    with plt.rc_context(STYLE):
        fig = plt.figure(figsize=(FIG_WIDTH, 9.0))
        frame(fig, "What two games can and can't tell you about an offense",
              ["FBS offenses, 2021\u20132025. For each measure: how many games it takes before a team's own number deserves as much weight as the",
               "league average, learned by testing how well each team's early-season number predicted the rest of that same season.",
               "Play-calling settles almost immediately. How well it is going takes most of a season, and longer once opponent and situation are removed."],
              "insight_reliability.csv")
        ax = fig.add_axes(axes_rect(fig, 3.55, 2.95, 4.5, 4.3))
        limit = max(18.0, float(data.games_to_half_weight.max()) * 1.05)
        ax.set_xlim(0, limit)
        ax.set_ylim(len(data) - 0.5, -0.5)
        ax.set_xticks([0, 2, 4, 6, 8, 10, 12, 14, 16, 18])
        ax.set_yticks([])
        ax.grid(axis="x", color=GRID, linewidth=1)
        ax.set_axisbelow(True)
        ax.tick_params(labelsize=10.5)
        for spine in ax.spines.values():
            spine.set_visible(False)
        label_x = blended_transform_factory(ax.transAxes, ax.transData)
        for i, r in data.iterrows():
            ax.plot([0, r.games_to_half_weight], [i, i], color=INK_2, linewidth=7, solid_capstyle="butt", alpha=0.9, zorder=3)
            ax.text(r.games_to_half_weight + limit * 0.012, i, r.games_text, fontsize=11, color=INK, va="center", zorder=5,
                    bbox={"facecolor": SURFACE, "edgecolor": "none", "pad": 1.5})
            ax.text(-0.03, i, r.measure, transform=label_x, fontsize=11.5, color=INK, ha="right", va="center")
            ax.text(1.30, i, r.weight_text, transform=label_x, fontsize=11, color=INK_2, ha="center", va="center")
            ax.text(1.52, i, r.correlation_text, transform=label_x, fontsize=11, color=INK_2, ha="center", va="center")
        identity_rows = int((data.family == "identity").sum())
        if 0 < identity_rows < len(data):
            ax.axhline(identity_rows - 0.5, color=GRID, linewidth=1, zorder=1)
        for x, label in ((2, "two games in"), (SEASON_GAMES, "a full regular season")):
            ax.axvline(x, color=INK_2, linewidth=1.2, zorder=2)
            ax.text(x, -0.85, label, fontsize=10.5, color=INK_2, ha="center", va="bottom")
        ax.text(0.5, -1.45, "Games needed before a team's own number is worth as much as the league average",
                transform=ax.transAxes, fontsize=11.5, color=INK, ha="center", va="bottom")
        header_y = -1.45
        ax.text(1.30, header_y, "Weight after\ntwo games", transform=label_x, fontsize=10.5, color=INK, ha="center", va="bottom")
        ax.text(1.52, header_y, "Early vs. rest\nof season", transform=label_x, fontsize=10.5, color=INK, ha="center", va="bottom")
    return fig, data


# ---------------------------------------------------------------- V7: two games cannot rank an offense

def rank_interval_data() -> pd.DataFrame:
    d = read_table("insight_rank_intervals.csv").sort_values("rank_estimate").reset_index(drop=True)
    d["could_be_top_25"] = d.rank_low_90 <= 25
    d["interval_text"] = [f"{int(lo)}th to {int(hi)}th" for lo, hi in zip(d.rank_low_90, d.rank_high_90)]
    return d


def build_v7():
    data = rank_interval_data()
    teams = len(data)
    auburn = data[data.team == config.OFFENSE_TEAM].iloc[0]
    with plt.rc_context(STYLE):
        fig = plt.figure(figsize=(FIG_WIDTH, 9.4))
        frame(fig, "Two games cannot rank an offense",
              [f"Every FBS offense, 2026 through the cutoff. Each line is the range of national ranks consistent with that team's two games,",
               f"after adjusting for opponent, situation, and point spread, and after discounting for how little two games settle.",
               f"The median line covers {data.rank_interval_width.median():.0f} of {teams} places. Teams are ordered by their two-game estimate, best at the top."],
              "insight_rank_intervals.csv")
        ax = fig.add_axes(axes_rect(fig, 1.5, 2.7, 7.1, 5.6))
        ax.set_xlim(0.5, teams + 0.5)
        ax.set_ylim(teams + 0.5, -0.5)
        ax.set_xticks([1, 25, 50, 75, 100, 125, teams], ["1st", "25th", "50th", "75th", "100th", "125th", f"{teams}th"])
        ax.set_yticks([])
        ax.grid(axis="x", color=GRID, linewidth=1)
        ax.set_axisbelow(True)
        ax.tick_params(labelsize=10.5)
        ax.xaxis.tick_top()
        for spine in ax.spines.values():
            spine.set_visible(False)
        for i, r in data.iterrows():
            is_auburn = r.team == config.OFFENSE_TEAM
            ax.plot([r.rank_low_90, r.rank_high_90], [i, i], color=INK if is_auburn else MUTED,
                    linewidth=2.6 if is_auburn else 1.1, alpha=1.0 if is_auburn else 0.55,
                    solid_capstyle="round", zorder=4 if is_auburn else 2)
            ax.scatter([r.rank_estimate], [i], s=26 if is_auburn else 4, color=INK if is_auburn else MUTED,
                       zorder=5 if is_auburn else 3, linewidths=0)
        ax.annotate(f"{config.OFFENSE_TEAM}: two games say {int(auburn.rank_estimate)}th,\nbut the data supports {auburn.interval_text}",
                    (100, data.index[data.team == config.OFFENSE_TEAM][0]), xytext=(0.34, 0.80),
                    textcoords="axes fraction", fontsize=11, fontweight="bold", color=INK, ha="left", va="center",
                    linespacing=1.35, zorder=6, gid="annotation", bbox={"facecolor": SURFACE, "edgecolor": "none", "pad": 4},
                    arrowprops={"arrowstyle": "-|>", "color": INK_2, "linewidth": 1, "shrinkA": 6, "shrinkB": 4, "mutation_scale": 10})
        ax.text(0.02, 0.06, f"{int(data.could_be_top_25.sum())} of {teams} offenses could still be a top-25 offense.",
                transform=ax.transAxes, fontsize=11, fontweight="bold", color=INK, ha="left", va="center", gid="annotation",
                bbox={"facecolor": SURFACE, "edgecolor": "none", "pad": 4})
        ax.set_xlabel("National rank in PPA over expected, 2026 through the cutoff", fontsize=11.5, labelpad=10)
        ax.xaxis.set_label_position("top")
    return fig, data


# ---------------------------------------------------------------- V8: every FBS pairing, not just this one

def pairing_data() -> pd.DataFrame:
    return read_table("insight_pairings.csv")


def build_v8():
    summary = pairing_data()
    row = summary[(summary.metric == "value") & (summary.play_family == "any")].iloc[0]
    pairs = pd.read_csv(config.TABLES_DIR / "insight_pairings_value.csv")
    with plt.rc_context(STYLE):
        fig = plt.figure(figsize=(FIG_WIDTH, 7.6))
        frame(fig, "The edge in this matchup is an ordinary one",
              [f"Every 2026 FBS offense paired with every 2026 FBS defense ({int(row.pairings):,} pairings), scored with the same method as Auburn\u2013Florida:",
               "the largest PPA edge either way across the four situations, after shrinking each team's two games toward the league average.",
               f"Auburn\u2013Florida's largest edge is smaller than {100 - row.auburn_florida_abs_percentile:.0f}% of them."],
              "insight_pairings.csv")
        ax = fig.add_axes(axes_rect(fig, 1.3, 2.6, 8.0, 3.3))
        ax.hist(pairs.largest_abs_edge, bins=60, color=MUTED, alpha=0.55, zorder=2)
        ax.set_xlim(0, float(pairs.largest_abs_edge.max()) * 1.02)
        ax.set_yticks([])
        ax.grid(axis="x", color=GRID, linewidth=1)
        ax.set_axisbelow(True)
        ax.tick_params(labelsize=10.5)
        for spine in ax.spines.values():
            spine.set_visible(False)
        top = ax.get_ylim()[1]
        matchup_edge = abs(row.auburn_florida_edge)
        for value, label, color, weight in ((row.median_abs_edge, f"Median pairing\n{row.median_abs_edge:.3f}", INK_2, "normal"),
                                            (matchup_edge, f"Auburn\u2013Florida\n{matchup_edge:.3f}", INK, "bold")):
            side = "right" if value <= matchup_edge else "left"  # keep the two labels apart
            pad = -1 if side == "right" else 1
            ax.axvline(value, color=color, linewidth=2, zorder=4)
            ax.text(value + pad * float(pairs.largest_abs_edge.max()) * 0.006, top * 0.97, label, fontsize=11, color=color,
                    fontweight=weight, ha=side, va="top", linespacing=1.35, zorder=5, gid="annotation",
                    bbox={"facecolor": SURFACE, "edgecolor": "none", "pad": 2})
        ax.set_xlabel("Largest PPA edge per play in any of the four situations, either direction", fontsize=11.5, labelpad=10)
    return fig, summary


# ---------------------------------------------------------------- main

FIGURE_BUILDERS = {
    "v1_auburn_offense_ppa": build_v1,
    "v2_florida_defense_ppa": build_v2,
    "v3_explosive_plays": build_v3,
    "v4_opportunity_map": build_v4,
    "v5_two_game_reliability": build_v5,
    "v6_reliability_spectrum": build_v6,
    "v7_rank_intervals": build_v7,
    "v8_pairing_distribution": build_v8,
}


def figure_text(fig) -> str:
    """Every string drawn on a figure, including legends (used by tests)."""
    return "\n".join(t.get_text() for t in fig.findobj(matplotlib.text.Text) if t.get_text())


def main() -> None:
    config.FIGURES_DIR.mkdir(parents=True, exist_ok=True)
    for name, build in FIGURE_BUILDERS.items():
        fig, data = build()
        fig.savefig(config.FIGURES_DIR / f"{name}.png", dpi=DPI, metadata={"Software": None})
        data.to_csv(config.FIGURES_DIR / f"{name}_data.csv", index=False)
        plt.close(fig)
        print(f"Wrote outputs/figures/{name}.png and {name}_data.csv ({len(data)} rows)")


if __name__ == "__main__":
    main()
