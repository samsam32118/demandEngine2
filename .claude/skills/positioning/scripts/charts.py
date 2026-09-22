#!/usr/bin/env python3
"""charts.py — the positioning visuals, rendered from report-manifest.json.

This report is meant to be read by looking, not by reading, so each of April
Dunford's steps gets one picture that carries the whole finding. The manifest
is the single source of truth: `make_manifest.py` computes every number in it
from the collected corpus, the analyst supplies judgement (which attribute is
unique, which segment cares), and this script only draws what is there. That
split is deliberate — a chart script that recomputes numbers is a second place
for them to disagree with the tables.

Usage:
    charts.py --run research/positioning/<slug>              # every chart
    charts.py --run <run> --only frame_quadrant,value_flow   # a subset

Every chart is optional: missing or too-thin data skips that chart with a note
on stderr rather than failing the run, because a study that could only reach
half its instruments should still produce the half it earned.

Needs matplotlib:  python3 -m pip install matplotlib reportlab pillow
"""

import argparse
import json
import math
import os
import sys
import textwrap

try:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.path import Path
    from matplotlib.patches import PathPatch, FancyBboxPatch, Rectangle, Circle
    from matplotlib.colors import LinearSegmentedColormap
except ImportError:
    print("error: matplotlib is not installed.\n"
          "fix:   python3 -m pip install matplotlib reportlab pillow", file=sys.stderr)
    sys.exit(3)

DPI = 200

# assets/DESIGN.md is the source of truth; theme.py transcribes it.
# Run `python3 theme.py` to audit contrast after any change.
import theme as T
from theme import (INK, INK_SOFT, MUTED, FAINT, HAIR, RULE, PAPER, SAND, SURFACE,
                   YOU, YOU_EDGE, YOU_TINT, ON_YOU,
                   LANE_COLORS, LANE_LABELS, LANE_ORDER,
                   VERDICT_STYLE, VERDICT_COLORS, VERDICT_LABELS,
                   HEAT_STOPS, SERIES, ink_on, contrast, c, size, tracking)

_FONT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "assets", "fonts")
_inter = os.path.join(_FONT_DIR, "Inter-Regular.ttf")
if os.path.isfile(_inter):
    # Lausanne is proprietary; the spec names Inter 400 as the substitute and
    # warns that system-ui defaults break the brand's print-like density.
    matplotlib.font_manager.fontManager.addfont(_inter)

HEAT = LinearSegmentedColormap.from_list("heat", HEAT_STOPS)
GRID = HAIR
RIVAL = LANE_COLORS["direct"]
DIRECT, ADJACENT, DIY, NOTHING = (LANE_COLORS[k] for k in LANE_ORDER)
BLAZE = c("blaze")
TILE_R = T.ROUNDED["lg"] / 100.0     # 12px expressed for rounding_size

plt.rcParams.update({
    # The page is sand; a chart is a white tile floating on it. That contrast
    # is the system's entire elevation model — there is no shadow tier.
    "figure.facecolor": PAPER, "axes.facecolor": PAPER, "savefig.facecolor": PAPER,
    "font.family": "sans-serif",
    "font.sans-serif": T.FONT_STACK,
    "font.weight": T.weight(),
    "font.size": size("body-sm") * 0.62,
    "text.color": INK,
    "axes.labelcolor": MUTED, "axes.labelsize": size("caption") * 0.66,
    "axes.edgecolor": HAIR, "axes.linewidth": 1.0,
    "axes.titlecolor": INK, "axes.titleweight": T.weight(),
    "xtick.color": MUTED, "ytick.color": MUTED,
    "xtick.labelsize": size("caption") * 0.63, "ytick.labelsize": size("caption") * 0.63,
    "legend.fontsize": size("body-sm") * 0.6, "legend.frameon": False,
    "figure.dpi": DPI,
})


def skip(name, why, run=None):
    """A deliberate skip: this chart's data is absent or too thin to draw.

    Also clears any PNG a previous run left behind. Without that, build_pdf.py
    places a stale image and the deck looks complete while showing last week's
    numbers — which is strictly worse than a missing page.
    """
    print(f"skip {name}: {why}", file=sys.stderr)
    if run:
        stale = os.path.join(run, "charts", f"{name}.png")
        if os.path.isfile(stale):
            os.remove(stale)
            print(f"      removed stale charts/{name}.png", file=sys.stderr)
    return None


def wrap(text, width=22):
    return "\n".join(textwrap.wrap(str(text), width)) or str(text)


def short(text, n=30):
    text = str(text)
    return text if len(text) <= n else text[:n - 1].rstrip() + "…"


def human(n):
    """Search volumes are read at a glance, not audited — 14k beats 14,800."""
    try:
        n = float(n)
    except (TypeError, ValueError):
        return "—"
    if n >= 1_000_000:
        return f"{n/1_000_000:.1f}M".replace(".0M", "M")
    if n >= 1_000:
        return f"{n/1_000:.1f}k".replace(".0k", "k")
    return f"{n:.0f}"


def clean_axes(ax, keep=()):
    for side in ("top", "right", "left", "bottom"):
        ax.spines[side].set_visible(side in keep)
    for side in keep:
        ax.spines[side].set_color(c("ink-mute-2"))


def finish(fig, run, name):
    out = os.path.join(run, "charts", f"{name}.png")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    fig.savefig(out, dpi=DPI, bbox_inches="tight", pad_inches=0.22, facecolor=PAPER)
    plt.close(fig)
    print(f"wrote charts/{name}.png")
    return out


def titled(fig, title, sub=None, x=0.0, y=1.0):
    """Charts travel: each one carries its own headline so a page that is
    nothing but a picture still says what the picture means."""
    h_in = fig.get_size_inches()[1]
    fig.text(x, y, title, fontsize=size("display-md") * 0.62, color=INK,
             va="top", ha="left")
    if sub:
        # 0.30in below the title, expressed as a figure fraction so a tall
        # chart does not collapse the gap and a short one does not gape.
        fig.text(x, y - 0.30 / h_in, sub, fontsize=size("body-sm") * 0.66,
                 color=MUTED, va="top", ha="left")


# ============================================================ 1. alternatives

def chart_alternatives(run, man):
    """Step 4 — the true competitive alternative set, status quo included.

    Dunford's point is that the alternative set is wider than the competitor
    set: the thing most deals are lost to is a spreadsheet or nothing at all.
    Laying the lanes out side by side, at the same scale, is what stops the
    reader mentally deleting the two lanes that have no logo.
    """
    alts = man.get("alternatives") or []
    if len(alts) < 3:
        return skip("alternatives_map", f"only {len(alts)} alternatives", run=run)

    lanes = [l for l in LANE_ORDER if any(a.get("lane") == l for a in alts)]
    fig, ax = plt.subplots(figsize=(10.6, 0.45 + 1.62 * len([l for l in LANE_ORDER
                                                            if any(a.get("lane") == l for a in alts)])))
    vols = [max(1.0, float(a.get("volume") or 0)) for a in alts]
    vmax = max(vols)

    PITCH, PAD = 1.74, 1.46
    widest = max(len([a for a in alts if a.get("lane") == l]) for l in lanes)
    span = max(4, widest) * PAD
    for li, lane in enumerate(lanes):
        rows = sorted([a for a in alts if a.get("lane") == lane],
                      key=lambda a: -float(a.get("volume") or 0))
        color = LANE_COLORS.get(lane, MUTED)
        y = (len(lanes) - li) * PITCH
        # A neutral band, not the orange surface: the accent belongs to the
        # product alone, and four warm bands would drown it.
        ax.add_patch(FancyBboxPatch((-0.30, y - 0.82), span + 0.6, 1.54,
                                    boxstyle="round,pad=0.0,rounding_size=0.06",
                                    facecolor=SAND, edgecolor="none", zorder=0))
        # A colour bar as well as a coloured label, so the lane is identifiable
        # without relying on hue alone.
        ax.add_patch(Rectangle((-0.30, y - 0.82), 0.055, 1.54,
                               facecolor=color, edgecolor="none", zorder=1))
        ax.text(-0.16, y + 0.56, LANE_LABELS.get(lane, lane).upper(), fontsize=8.4,
                fontweight=T.weight(), color=color, va="center", ha="left", zorder=3)
        offset = (span - len(rows) * PAD) / 2 if len(rows) < widest else 0.0
        for i, a in enumerate(rows):
            v = max(1.0, float(a.get("volume") or 0))
            cx = 0.42 + offset + i * PAD
            # scatter sizes in points², so area really is proportional to volume
            # and the mark is a true circle whatever the axes aspect is.
            ax.scatter([cx], [y + 0.02], s=260 + 2600 * (v / vmax),
                       facecolor=color, alpha=0.18, edgecolor=color,
                       linewidth=1.6, zorder=2)
            ax.text(cx, y + 0.02, human(v), fontsize=7.8, fontweight=T.weight(),
                    color=color, ha="center", va="center", zorder=4)
            ax.text(cx, y - 0.42, wrap(short(a.get("name", ""), 30), 16), fontsize=8.2,
                    color=INK, ha="center", va="top", zorder=4)

    ax.set_xlim(-0.35, span + 0.4)
    ax.set_ylim(PITCH - 0.92, len(lanes) * PITCH + 0.80)
    ax.set_xticks([]); ax.set_yticks([])
    clean_axes(ax)
    fig.text(0.0, 0.015, "Bubble area = monthly US searches for that alternative. "
                         "The bottom lanes have no sales team, and win the most deals.",
             fontsize=8.2, color=FAINT, ha="left")
    titled(fig, "What they would actually do instead",
           "Every route your buyer can take when they have your problem — not just the vendors with a logo.",
           y=1.06)
    return finish(fig, run, "alternatives_map")


# ============================================================ 2. attribute matrix

def chart_attributes(run, man):
    """Step 5 — isolate what only you have, against the real alternative set.

    The grid is the argument: a filled row across every column is table stakes
    no matter how much the marketing site loves it, and a row filled only in
    the first column is the entire basis of the positioning.
    """
    attrs = man.get("attributes") or []
    if len(attrs) < 4:
        return skip("attribute_matrix", f"only {len(attrs)} attributes", run=run)
    comp_names = []
    for a in attrs:
        for c in (a.get("competitors") or {}):
            if c not in comp_names:
                comp_names.append(c)
    if not comp_names:
        return skip("attribute_matrix", "no competitor columns", run=run)
    comp_names = comp_names[:7]

    order = {"unique": 0, "gap": 1, "table_stakes": 2}
    def rivals(a):
        return sum(1 for v in (a.get("competitors") or {}).values() if v)
    # Inside "only you", fewest rivals first (the cleanest claim leads); inside
    # "you lack it" and "table stakes", most rivals first (the loudest gap leads).
    attrs = sorted(attrs, key=lambda a: (order.get(a.get("verdict"), 3),
                                         rivals(a) if a.get("verdict") == "unique" else -rivals(a)))
    attrs = attrs[:16]
    you_label = short(man.get("product", {}).get("name", "You"), 22)
    cols = [you_label] + [short(c, 22) for c in comp_names]
    n_rows, n_cols = len(attrs), len(cols)

    head_in = 0.034 * max(len(c) for c in cols) + 0.28     # 34° rise of the longest label
    fig, ax = plt.subplots(figsize=(1.55 + 0.92 * n_cols + 2.9,
                                    0.9 + head_in + 0.42 * n_rows))
    cell_w, cell_h = 1.0, 1.0
    left = 0.0

    for j, col in enumerate(cols):
        is_you = j == 0
        ax.text(left + j + 0.42, n_rows + 0.30, col, fontsize=8.2,
                fontweight=T.weight(),
                color=INK if is_you else INK_SOFT, ha="left", va="bottom",
                rotation=34, rotation_mode="anchor")
        if is_you:
            ax.add_patch(Rectangle((left + j, 0), cell_w, n_rows, facecolor=YOU_TINT,
                                   edgecolor="none", zorder=0))

    for i, a in enumerate(attrs):
        y = n_rows - 1 - i
        verdict = a.get("verdict", "")
        vstyle = VERDICT_STYLE.get(verdict, VERDICT_STYLE["table_stakes"])
        vc = vstyle["edge"]
        ax.text(-0.28, y + 0.5, short(a.get("name", ""), 48), fontsize=8.6,
                color=INK if verdict == "unique" else MUTED,
                fontweight=T.weight(), ha="right", va="center")
        vals = [bool(a.get("you"))] + [bool((a.get("competitors") or {}).get(c)) for c in comp_names]
        for j, has in enumerate(vals):
            cx, cy = left + j + 0.5, y + 0.5
            if has:
                # Yellow is ~1.3:1 on white. The ink hairline is what makes it a
                # mark rather than a smudge — the edge is doing the work, and
                # every filled shape in this system carries one.
                fill, edge = (YOU, YOU_EDGE) if j == 0 else (INK_SOFT, INK_SOFT)
                ax.add_patch(Circle((cx, cy), 0.215, facecolor=fill, edgecolor=edge,
                                    linewidth=1.0, zorder=3))
            else:
                ax.add_patch(Circle((cx, cy), 0.19, facecolor="none", edgecolor=HAIR,
                                    linewidth=1.3, zorder=2))
        # The verdict strip on the right is the whole point of the grid.
        # Badge anatomy per DESIGN.md § Components: a fill, ink-level text and a
        # 1px edge. Colour never carries the text in this system.
        ax.add_patch(FancyBboxPatch((n_cols + 0.28, y + 0.14), 1.85, 0.72,
                                    boxstyle="round,pad=0.02,rounding_size=0.10",
                                    facecolor=vstyle["fill"], edgecolor=vstyle["edge"],
                                    linewidth=1.0, zorder=3))
        ax.text(n_cols + 1.20, y + 0.5, VERDICT_LABELS.get(verdict, "—"),
                fontsize=size("caption") * 0.62, fontweight=T.weight(),
                color=vstyle["text"], ha="center", va="center", zorder=4)
        if i % 2 == 1:
            ax.add_patch(Rectangle((-0.02, y), n_cols + 0.04, cell_h, facecolor=SAND,
                                   edgecolor="none", zorder=-1))

    n_unique = sum(1 for a in attrs if a.get("verdict") == "unique")
    ax.set_xlim(-6.2, n_cols + 2.4)
    ax.set_ylim(-0.35, n_rows + 0.30 + head_in / 0.42)
    ax.set_xticks([]); ax.set_yticks([])
    clean_axes(ax)
    titled(fig, "The only things that are actually yours",
           f"{n_unique} of {len(attrs)} capabilities survive the comparison. "
           f"The rest are the price of entry — true of everyone, so they persuade no one.",
           y=1.02)
    return finish(fig, run, "attribute_matrix")


# ============================================================ 3. value flow

def _ribbon(ax, x0, y0, x1, y1, w0, w1, color, alpha=0.42):
    """A bezier ribbon. Straight lines make a flow diagram look like a wiring
    schematic; the S-curve is what makes the eye follow one strand through."""
    cx = (x0 + x1) / 2
    verts = [(x0, y0 - w0 / 2), (cx, y0 - w0 / 2), (cx, y1 - w1 / 2), (x1, y1 - w1 / 2),
             (x1, y1 + w1 / 2), (cx, y1 + w1 / 2), (cx, y0 + w0 / 2), (x0, y0 + w0 / 2),
             (x0, y0 - w0 / 2)]
    codes = [Path.MOVETO, Path.CURVE4, Path.CURVE4, Path.CURVE4,
             Path.LINETO, Path.CURVE4, Path.CURVE4, Path.CURVE4, Path.CLOSEPOLY]
    ax.add_patch(PathPatch(Path(verts, codes), facecolor=color, edgecolor="none",
                           alpha=alpha, zorder=2))


def chart_value_flow(run, man):
    """Step 6 — attributes become benefits become value themes.

    Features are not value, and the translation is where most positioning
    quietly fails. Drawing it as a flow forces the question the list format
    hides: which attribute feeds nothing, and which theme rests on one thin
    strand?
    """
    vf = man.get("value_flow") or {}
    links = vf.get("links") or []
    if len(links) < 3:
        return skip("value_flow", "fewer than 3 links", run=run)

    cols = [vf.get("attributes") or [], vf.get("benefits") or [], vf.get("themes") or []]
    if not all(cols):
        return skip("value_flow", "value_flow needs attributes, benefits and themes", run=run)
    labels = ["What you have", "What it does for them", "Why it matters"]

    weight = {}
    for l in links:
        weight[(l.get("from"), l.get("to"))] = weight.get((l.get("from"), l.get("to")), 0) + float(l.get("weight") or 1)
    node_w = {}
    for (a, b), w in weight.items():
        node_w[a] = node_w.get(a, 0) + w
        node_w[b] = node_w.get(b, 0) + w

    fig, ax = plt.subplots(figsize=(11.2, 0.62 * max(len(c) for c in cols) + 3.0))
    xs = [0.0, 1.0, 2.0]
    GAP, TOP = 0.32, 10.0
    pos, height = {}, {}
    for ci, col in enumerate(cols):
        tot = sum(max(node_w.get(n, 1), 0.6) for n in col)
        scale = (TOP - GAP * (len(col) - 1)) / max(tot, 0.001)
        y = TOP
        for n in col:
            h = max(node_w.get(n, 1), 0.6) * scale
            pos[(ci, n)] = y - h / 2
            height[(ci, n)] = h
            y -= h + GAP

    theme_color = {}
    ramp = SERIES
    for i, t in enumerate(cols[2]):
        theme_color[t] = ramp[i % len(ramp)]

    # Colour every strand by the theme it ends in, so the eye can trace a value
    # theme back to the one capability that earns it.
    def theme_of(node, ci):
        if ci == 2:
            return theme_color.get(node, MUTED)
        for (a, b), _ in weight.items():
            if a == node:
                return theme_of(b, ci + 1)
        return MUTED

    used_out, used_in = {}, {}
    for (a, b), w in sorted(weight.items(), key=lambda kv: -kv[1]):
        ci = 0 if a in cols[0] else 1
        if a not in cols[ci] or b not in cols[ci + 1]:
            continue
        wa = max(node_w.get(a, 1), 0.6)
        wb = max(node_w.get(b, 1), 0.6)
        h0 = height[(ci, a)] * (w / wa)
        h1 = height[(ci + 1, b)] * (w / wb)
        y0 = pos[(ci, a)] + height[(ci, a)] / 2 - used_out.get(a, 0) - h0 / 2
        y1 = pos[(ci + 1, b)] + height[(ci + 1, b)] / 2 - used_in.get(b, 0) - h1 / 2
        used_out[a] = used_out.get(a, 0) + h0
        used_in[b] = used_in.get(b, 0) + h1
        _ribbon(ax, xs[ci] + 0.055, y0, xs[ci + 1] - 0.055, y1, h0, h1,
                theme_of(b if ci == 1 else a, ci + 1 if ci == 1 else ci), alpha=0.34)

    for ci, col in enumerate(cols):
        ax.text(xs[ci], TOP + 0.75, labels[ci].upper(), fontsize=8.6, fontweight=T.weight(),
                color=MUTED, ha="left" if ci < 2 else "left", va="bottom")
        for n in col:
            y, h = pos[(ci, n)], height[(ci, n)]
            c = theme_color.get(n, YOU if ci == 0 else INK_SOFT)
            ax.add_patch(FancyBboxPatch((xs[ci] - 0.045, y - h / 2), 0.09, h,
                                        boxstyle="round,pad=0.0,rounding_size=0.02",
                                        facecolor=c, edgecolor="none", zorder=5))
            ha = "right" if ci == 0 else "left"
            dx = -0.10 if ci == 0 else 0.10
            t = ax.text(xs[ci] + dx, y, wrap(short(n, 46), 26), fontsize=8.5,
                        fontweight=T.weight(),
                        color=INK if ci == 2 else INK_SOFT, ha=ha, va="center", zorder=6)
            if ci == 1:
                t.set_bbox(dict(boxstyle="round,pad=0.22", facecolor=PAPER,
                                edgecolor="none", alpha=0.86))

    ax.set_xlim(-1.15, 3.25)
    ax.set_ylim(-0.6, TOP + 1.5)
    ax.set_xticks([]); ax.set_yticks([])
    clean_axes(ax)
    titled(fig, "Features are not value",
           "Ribbon thickness is how much evidence sits behind each translation. "
           "A capability that reaches no theme on the right is not a selling point.",
           y=1.03)
    return finish(fig, run, "value_flow")


# ============================================================ 4. segment heat

def chart_segments(run, man):
    """Step 7 — who cares a lot.

    Positioning gets easier the narrower the target, and the grid shows why:
    the right segment is the row that is hot all the way across, not the row
    with the largest population.
    """
    sv = man.get("segment_value") or {}
    segs, themes, scores = sv.get("segments") or [], sv.get("themes") or [], sv.get("scores") or []
    if len(segs) < 2 or len(themes) < 2 or len(scores) != len(segs):
        return skip("segment_heat", "need ≥2 segments × ≥2 themes with a score matrix", run=run)

    totals = [sum(r) for r in scores]
    order = sorted(range(len(segs)), key=lambda i: -totals[i])
    segs = [segs[i] for i in order]; scores = [scores[i] for i in order]; totals = [totals[i] for i in order]
    best = 0

    fig, ax = plt.subplots(figsize=(2.6 + 1.42 * len(themes) + 3.0, 2.1 + 0.62 * len(segs)))
    vmax = max(max(r) for r in scores) or 1
    for i, seg in enumerate(segs):
        y = len(segs) - 1 - i
        for j, _ in enumerate(themes):
            v = scores[i][j]
            ax.add_patch(FancyBboxPatch((j + 0.06, y + 0.10), 0.88, 0.80,
                                        boxstyle="round,pad=0.0,rounding_size=0.06",
                                        facecolor=HEAT(v / vmax), edgecolor="none", zorder=2))
            ax.text(j + 0.5, y + 0.5, f"{v:.0f}", fontsize=9.2, fontweight=T.weight(),
                    color=ink_on(matplotlib.colors.to_hex(HEAT(v / vmax))),
                    ha="center", va="center", zorder=3)
        ax.text(-0.22, y + 0.5, short(seg, 34), fontsize=9.2,
                fontweight=T.weight(),
                color=INK if i == best else INK_SOFT, ha="right", va="center")
        # Row total as a bar: the "cares a lot" score in one glance.
        bw = 1.9 * totals[i] / max(totals)
        ax.add_patch(FancyBboxPatch((len(themes) + 0.42, y + 0.28), max(bw, 0.06), 0.44,
                                    boxstyle="round,pad=0.0,rounding_size=0.08",
                                    facecolor=YOU if i == best else c("solar"),
                                    edgecolor="none", zorder=2))
        ax.text(len(themes) + 0.42 + max(bw, 0.06) + 0.10, y + 0.5, f"{totals[i]:.0f}",
                fontsize=8.6, fontweight=T.weight(),
                color=INK if i == best else MUTED, ha="left", va="center")

    ax.add_patch(Rectangle((0.02, len(segs) - 1 + 0.04), len(themes) - 0.04, 0.92,
                           facecolor="none", edgecolor=INK, linewidth=1.6, zorder=5,
                           joinstyle="round"))
    for j, t in enumerate(themes):
        ax.text(j + 0.5, len(segs) + 0.16, wrap(short(t, 34), 12), fontsize=7.8,
                color=MUTED, ha="center", va="bottom")
    ax.text(len(themes) + 0.42, len(segs) + 0.16, "Cares\nhow much", fontsize=7.8,
            color=MUTED, ha="left", va="bottom")

    ax.set_xlim(-5.0, len(themes) + 3.0)
    ax.set_ylim(-0.25, len(segs) + 1.15)
    ax.set_xticks([]); ax.set_yticks([])
    clean_axes(ax)
    titled(fig, f"The segment that cares most: {short(segs[best], 42)}",
           "How much each kind of buyer values each thing you are best at — 0 (indifferent) to 5 (it is why they buy).",
           y=1.03)
    return finish(fig, run, "segment_heat")


# ============================================================ 5. vocabulary

def chart_vocabulary(run, man):
    """Step 3 — align on vocabulary.

    A dumbbell rather than paired bars, because the finding is the *distance*:
    the gap between the word a company chose and the word its buyers type is
    the thing that has to shrink, and the eye reads a gap better than it reads
    two bar lengths.
    """
    rows = [r for r in (man.get("vocabulary") or []) if r.get("yours") and r.get("theirs")]
    if len(rows) < 3:
        return skip("vocabulary_gap", f"only {len(rows)} vocabulary pairs", run=run)
    rows = sorted(rows, key=lambda r: -(float(r.get("their_volume") or 0) -
                                        float(r.get("your_volume") or 0)))[:10]
    rows = rows[::-1]

    fig, ax = plt.subplots(figsize=(10.6, 1.6 + 0.66 * len(rows)))
    mx = max(max(float(r.get("their_volume") or 0), float(r.get("your_volume") or 0))
             for r in rows) or 1
    # sqrt scale: search volumes span orders of magnitude and a linear axis
    # flattens every row but the biggest into an invisible stub.
    def px(v):
        return math.sqrt(max(float(v or 0), 0) / mx)

    for i, r in enumerate(rows):
        y = i
        a, b = px(r.get("your_volume")), px(r.get("their_volume"))
        ax.plot([a, b], [y, y], color=RULE, linewidth=3.2, solid_capstyle="round", zorder=1)
        # Circle for your word, square for theirs — shape carries the series,
        # colour only reinforces it.
        ax.scatter([a], [y], s=125, marker="o", facecolor=YOU, zorder=3,
                   edgecolor=YOU_EDGE, linewidth=1.5)
        ax.scatter([b], [y], s=115, marker="s", facecolor=RIVAL, zorder=3,
                   edgecolor=PAPER, linewidth=1.4)
        ax.text(a - 0.018, y, f"{short(r['yours'], 26)}  ", fontsize=8.8, color=c("ink"),
                fontweight=T.weight(), ha="right", va="center")
        ax.text(b + 0.018, y, f"  {short(r['theirs'], 30)}", fontsize=8.8, color=RIVAL,
                fontweight=T.weight(), ha="left", va="center")
        ax.text(b + 0.018, y - 0.34, f"  {human(r.get('their_volume'))} searches/mo",
                fontsize=7.6, color=FAINT, ha="left", va="center")
        ax.text(a - 0.018, y - 0.34, f"{human(r.get('your_volume'))} searches/mo  ",
                fontsize=7.6, color=FAINT, ha="right", va="center")

    ax.set_xlim(-0.62, 1.44)
    ax.set_ylim(-0.75, len(rows) - 0.25)
    ax.set_xticks([]); ax.set_yticks([])
    clean_axes(ax)
    for dx, swatch, mark, lab in ((0.0, YOU, "\u25cf", "the word your site uses"),
                                  (0.30, RIVAL, "\u25a0", "the word your buyers type into Google")):
        fig.text(dx + 0.012, 0.012, mark, fontsize=9.5, color=swatch, ha="left")
        fig.text(dx + 0.032, 0.012, lab, fontsize=8.4, color=MUTED, ha="left")
    titled(fig, "You and your buyers are using different words",
           "Each line is one idea. The distance is the demand you are invisible to.",
           y=1.045)
    return finish(fig, run, "vocabulary_gap")


# ============================================================ 6. frame quadrant

def chart_frames(run, man):
    """Step 8 — pick the market frame that makes your strengths obvious.

    The same product is a leader in one category and an also-ran in another,
    and that choice is free. Plotting demand against how favourable each frame
    is turns a taste argument into a reading off a chart.
    """
    frames = man.get("frames") or []
    if len(frames) < 3:
        return skip("frame_quadrant", f"only {len(frames)} candidate frames", run=run)

    fig, ax = plt.subplots(figsize=(10.8, 7.3))
    dem = [max(float(f.get("demand") or 1), 1) for f in frames]
    fav = [float(f.get("favorability") or 0) for f in frames]
    dens = [float(f.get("density") or 1) for f in frames]
    xs = [math.log10(d) for d in dem]
    x0, x1 = min(xs) - 0.42, max(xs) + 0.52
    xmid = (x0 + x1) / 2

    ri = next((i for i, f in enumerate(frames) if f.get("recommended")), None)
    if ri is not None:
        qx = (xmid, x1) if xs[ri] >= xmid else (x0, xmid)
        qy = (50, 105) if fav[ri] >= 50 else (-5, 50)
        ax.add_patch(Rectangle((qx[0], qy[0]), qx[1] - qx[0], qy[1] - qy[0],
                               facecolor=YOU_TINT, edgecolor="none", zorder=0))
    ax.axvline(xmid, color=HAIR, linewidth=1.1, zorder=1)
    ax.axhline(50, color=HAIR, linewidth=1.1, zorder=1)
    for tx, ty, label, ha, va in [
        (x1 - 0.03, 103, "STRONG POSITION, REAL DEMAND", "right", "top"),
        (x0 + 0.03, 103, "STRONG POSITION, SMALL POND", "left", "top"),
        (x1 - 0.03, -3, "BIG POND, YOU LOOK ORDINARY", "right", "bottom"),
        (x0 + 0.03, -3, "NEITHER", "left", "bottom"),
    ]:
        ax.text(tx, ty, label, fontsize=7.6, fontweight=T.weight(), color=FAINT, ha=ha, va=va, zorder=2)

    dmax = max(dens) or 1
    ax.set_xlim(x0, x1)
    ax.set_ylim(-9, 109)
    fig.canvas.draw()      # limits must be final before transData is queried
    placed = []                             # display-space boxes already taken

    ax_x0, ax_y0, ax_x1, ax_y1 = ax.bbox.extents

    def free(x_disp, y_disp, half_w, h):
        if y_disp - h < ax_y0 + 2 or y_disp > ax_y1 - 2:
            return False                      # never let a label leave the plot
        if x_disp - half_w < ax_x0 - 30 or x_disp + half_w > ax_x1 + 30:
            return False
        return not any(abs(x_disp - px) < (half_w + phw) * 0.94 and
                       y_disp > pbot - 3 and y_disp - h < ptop + 3
                       for px, ptop, pbot, phw in placed)

    def slot(x_disp, y_below, y_above, half_w, h):
        """Find clear space for a label around its bubble.

        Bubble charts label badly by default, and an unreadable frame name
        costs more than the nudge does — this is the one chart the whole
        market-frame decision is read from. Candidates run below the mark
        first (the convention readers expect), then above, then sideways;
        anything leaving the axes is rejected outright, because a label under
        the x-axis title is worse than a slightly offset one.
        """
        cands = [(x_disp, y_below), (x_disp, y_above + h)]
        for step in (1, 2, 3):
            cands += [(x_disp, y_below - step * (h + 5)),
                      (x_disp, y_above + h + step * (h + 5))]
        # Sideways is the last resort but needs real reach: in a tight cluster
        # a nudge of one label-width still lands on the neighbouring bubble.
        for side in (1.2, 1.8, 2.5):
            for step in (0, 1, -1):
                cands += [(x_disp - half_w * side, y_below - step * (h + 5)),
                          (x_disp + half_w * side, y_below - step * (h + 5)),
                          (x_disp - half_w * side, y_above + h + step * (h + 5)),
                          (x_disp + half_w * side, y_above + h + step * (h + 5))]
        for cx_, cy_ in cands:
            if free(cx_, cy_, half_w, h):
                placed.append((cx_, cy_, cy_ - h, half_w))
                return cx_, cy_
        placed.append((x_disp, y_below, y_below - h, half_w))
        return x_disp, y_below

    px_per_pt = fig.dpi / 72.0
    marks = []
    for idx in range(len(frames)):
        f, x, y, d = frames[idx], xs[idx], fav[idx], dens[idx]
        rec = bool(f.get("recommended"))
        size = 260 + 1500 * (d / dmax)
        ax.scatter([x], [y], s=size, facecolor=YOU if rec else c("hairline"),
                   alpha=0.85 if rec else 0.55, edgecolor=YOU_EDGE if rec else c("ink-mute-2"),
                   linewidth=2.0 if rec else 1.0, zorder=4)
        if rec:
            ax.scatter([x], [y], s=size + 2600, facecolor="none", edgecolor=INK,
                       linewidth=1.4, linestyle=(0, (3, 3)), zorder=3)
        ax.annotate(f"{human(f.get('demand'))}/mo", (x, y), xytext=(0, 0),
                    textcoords="offset points", fontsize=7.8, fontweight=T.weight(),
                    color=ON_YOU if rec else INK_SOFT, ha="center", va="center", zorder=6)
        cx, cy = ax.transData.transform((x, y))
        r_pt = math.sqrt((size + (2600 if rec else 0)) / math.pi)
        # The bubble and the volume printed inside it are obstacles too.
        placed.append((cx, cy + r_pt * px_per_pt, cy - r_pt * px_per_pt,
                       max(r_pt, 26) * px_per_pt))
        marks.append((idx, x, y, rec, r_pt, cx, cy))

    for idx, x, y, rec, r_pt, cx, cy in sorted(marks, key=lambda m: (not m[3], -m[4])):
        f = frames[idx]
        label = wrap(short(f.get("name", ""), 44), 15)
        lines = label.count("\n") + 1
        widest = max(len(ln) for ln in label.split("\n"))
        half_w = widest * 0.25 * 8.2 * px_per_pt + 5
        # The marker radius is exactly sqrt(area/pi) in points, and the dashed
        # ring on the recommended frame is drawn from a larger area still.
        lx, ly = slot(cx, cy - (r_pt + 9) * px_per_pt, cy + (r_pt + 9) * px_per_pt,
                      half_w, 11.0 * lines * px_per_pt)
        ax.annotate(label, (x, y),
                    xytext=((lx - cx) / px_per_pt, (ly - cy) / px_per_pt),
                    textcoords="offset points",
                    fontsize=8.2, fontweight=T.weight(),
                    color=INK if rec else INK_SOFT, ha="center", va="top", zorder=6)

    ax.set_xlabel("How many people are looking  →   (monthly searches, log scale)")
    ax.set_ylabel("How good you look here  →   (share of your strengths that differentiate)")
    ax.set_xticks([]); ax.set_yticks([0, 25, 50, 75, 100])
    ax.set_yticklabels(["0%", "25%", "50%", "75%", "100%"])
    clean_axes(ax, keep=("left", "bottom"))
    ax.grid(False)
    rec = next((f for f in frames if f.get("recommended")), None)
    fig.text(0.0, 0.005, "Bubble size = how crowded that category already is.",
             fontsize=8.2, color=FAINT, ha="left")
    titled(fig, f"Compete as: {short((rec or {}).get('name', 'see chart'), 46)}",
           "The same product is a leader in one category and an also-ran in another. This is that choice, priced.",
           y=1.05)
    return finish(fig, run, "frame_quadrant")


# ============================================================ 7. messaging crowd

def chart_messaging(run, man):
    """What every alternative already claims — and the claims nobody has taken.

    Positioning is competitive, so a true strength six rivals also shout is
    worth less than a smaller one that is uncontested. The short end of this
    chart is where the sales story should live.
    """
    rows = man.get("messaging_crowding") or []
    if len(rows) < 3:
        return skip("messaging_crowd", f"only {len(rows)} message themes", run=run)
    rows = sorted(rows, key=lambda r: (len(r.get("claimed_by") or []),
                                       not r.get("you")))[:14]

    fig, ax = plt.subplots(figsize=(10.6, 1.45 + 0.56 * len(rows)))
    mx = max(len(r.get("claimed_by") or []) for r in rows) or 1
    BAR = 6.2
    for i, r in enumerate(rows):
        y = len(rows) - 1 - i
        n = len(r.get("claimed_by") or [])
        contested = n >= 2                       # two rivals already own it
        mine = bool(r.get("you"))
        color = FAINT if contested else (YOU if mine else DIY)

        if n == 0:
            # badge-status-yellow: filled chip, ink text, 1px ink edge.
            ax.add_patch(FancyBboxPatch((0, y + 0.20), 1.5, 0.60,
                                        boxstyle="round,pad=0.0,rounding_size=0.08",
                                        facecolor=color if mine else SURFACE,
                                        edgecolor=INK if mine else HAIR,
                                        linewidth=1.0, zorder=2))
            ax.text(0.75, y + 0.50, "OPEN", fontsize=7.8, fontweight=T.weight(),
                    color=INK, ha="center", va="center", zorder=3)
            end, note = 1.5, "nobody else is saying this"
        else:
            w = max(n / mx * BAR, 0.34)
            ax.add_patch(FancyBboxPatch((0, y + 0.20), w, 0.60,
                                        boxstyle="round,pad=0.0,rounding_size=0.08",
                                        facecolor=color,
                                        edgecolor=INK if (mine and not contested) else "none",
                                        linewidth=1.0 if (mine and not contested) else 0,
                                        zorder=2))
            end = w
            note = f"{n} of your alternatives say this"

        ax.text(end + 0.16, y + 0.50, note, fontsize=8.0, fontweight=T.weight(),
                color=MUTED if contested else INK, ha="left", va="center")
        # A dot rather than a second line of type: the row stays one line tall.
        if mine:
            ax.add_patch(Circle((-0.20, y + 0.50), 0.058, facecolor=YOU,
                                edgecolor=INK, linewidth=0.8, zorder=3))
        ax.text(-0.36, y + 0.50, short(r.get("theme", ""), 44), fontsize=8.8,
                fontweight=T.weight(),
                color=INK if not contested else MUTED, ha="right", va="center")

    ax.set_xlim(-4.9, 9.8); ax.set_ylim(-0.15, len(rows) + 0.15)
    ax.set_xticks([]); ax.set_yticks([])
    clean_axes(ax)
    fig.text(0.0, 0.012, "\u25cf", fontsize=9.5, color=YOU, ha="left")
    fig.text(0.020, 0.012, "a claim you already make", fontsize=8.4, color=MUTED, ha="left")
    titled(fig, "What everyone already says — and what nobody has claimed",
           "Bar length is how many of your alternatives make the same promise. The short end is open ground.",
           y=1.04)
    return finish(fig, run, "messaging_crowd")


# ============================================================ 8. customers

def chart_customers(run, man):
    """Step 1 — the customers who already love it, and the evidence for each.

    Segments invented in a workshop all look equally plausible; segments
    stacked by how many real artefacts name them do not. Showing the evidence
    type is what keeps a segment backed by one testimonial from outranking one
    backed by forty reviews.
    """
    segs = man.get("segments") or []
    segs = [s for s in segs if (s.get("evidence_types") or {})]
    if len(segs) < 2:
        return skip("customer_evidence", "need ≥2 segments carrying evidence counts", run=run)
    kinds, seen = [], set()
    for s in segs:
        for k in (s.get("evidence_types") or {}):
            if k not in seen:
                seen.add(k); kinds.append(k)
    segs = sorted(segs, key=lambda s: -sum((s.get("evidence_types") or {}).values()))[:8]

    # Bar length is this chart's whole argument. When every segment carries the
    # same count the bars all run to full width and read as "maximal" about
    # evidence that is actually one line on a marketing page — worse than
    # drawing nothing. A young product with no review corpus should lose this
    # page and keep the honest note, not gain a chart that flatters it.
    totals_ = [sum((x.get("evidence_types") or {}).values()) for x in segs]
    if len(set(totals_)) == 1:
        return skip("customer_evidence",
                    f"all {len(segs)} segments carry identical evidence counts "
                    f"({totals_[0]}) — bar length would encode nothing. Say the "
                    f"evidence is thin in the chapter note instead.",
                    run=run)

    ramp = SERIES
    kcolor = {k: ramp[i % len(ramp)] for i, k in enumerate(kinds)}

    fig, ax = plt.subplots(figsize=(10.4, 1.9 + 0.72 * len(segs)))
    totals = [sum((s.get("evidence_types") or {}).values()) for s in segs]
    mx = max(totals) or 1
    for i, s in enumerate(segs):
        y = len(segs) - 1 - i
        x = 0.0
        for k in kinds:
            v = (s.get("evidence_types") or {}).get(k, 0)
            if not v:
                continue
            w = v / mx * 6.2
            ax.add_patch(FancyBboxPatch((x, y + 0.24), w, 0.54,
                                        boxstyle="round,pad=0.0,rounding_size=0.05",
                                        facecolor=kcolor[k], edgecolor=PAPER,
                                        linewidth=0.9, zorder=2))
            if w > 0.42:
                ax.text(x + w / 2, y + 0.51, f"{v:.0f}", fontsize=7.8,
                        color=ink_on(kcolor[k]),
                        fontweight=T.weight(), ha="center", va="center", zorder=3)
            x += w
        ax.text(-0.16, y + 0.51, short(s.get("name", ""), 34), fontsize=9.0,
                fontweight=T.weight(),
                color=INK if i == 0 else INK_SOFT, ha="right", va="center")
        why = s.get("why_they_love") or ""
        if why:
            ax.text(-0.16, y + 0.09, short(why, 52), fontsize=7.6, color=FAINT,
                    ha="right", va="center")
        ax.text(x + 0.14, y + 0.51, f"{totals[i]:.0f}", fontsize=8.6, fontweight=T.weight(),
                color=MUTED, ha="left", va="center")

    lx = 0.0
    for k in kinds:
        label = k.replace("_", " ")
        ax.add_patch(Circle((lx, len(segs) + 0.20), 0.062, facecolor=kcolor[k],
                            edgecolor="none", zorder=3))
        ax.text(lx + 0.13, len(segs) + 0.20, label, fontsize=8.0,
                color=MUTED, ha="left", va="center")
        # Advance by the label's own width, not a fixed pitch.
        lx += 0.30 + len(label) * 0.105

    ax.set_xlim(-4.9, 7.4); ax.set_ylim(-0.15, len(segs) + 0.62)
    ax.set_xticks([]); ax.set_yticks([])
    clean_axes(ax)
    titled(fig, "Who already loves it",
           "Bar length is how many real artefacts name that kind of customer — reviews, case studies, logo walls, job posts.",
           y=1.04)
    return finish(fig, run, "customer_evidence")


# ==================================================================== driver

CHARTS = {
    "customer_evidence": chart_customers,
    "vocabulary_gap": chart_vocabulary,
    "alternatives_map": chart_alternatives,
    "attribute_matrix": chart_attributes,
    "value_flow": chart_value_flow,
    "segment_heat": chart_segments,
    "frame_quadrant": chart_frames,
    "messaging_crowd": chart_messaging,
}


def main():
    p = argparse.ArgumentParser(description="render the positioning chart set")
    p.add_argument("--run", required=True)
    p.add_argument("--manifest", help="default: <run>/report-manifest.json")
    p.add_argument("--only", help="comma-separated chart names")
    a = p.parse_args()

    mpath = a.manifest or os.path.join(a.run, "report-manifest.json")
    if not os.path.isfile(mpath):
        print(f"error: no manifest at {mpath}\n"
              f"fix:   run make_manifest.py --run {a.run} first", file=sys.stderr)
        sys.exit(3)
    with open(mpath, encoding="utf-8") as f:
        man = json.load(f)

    names = [n.strip() for n in a.only.split(",")] if a.only else list(CHARTS)
    made, thin, broken = 0, [], []
    for n in names:
        fn = CHARTS.get(n)
        if not fn:
            skip(n, "no such chart")
            continue
        try:
            if fn(a.run, man):
                made += 1
            else:
                thin.append(n)
        except Exception as e:      # one bad chart must not cost the whole report,
            broken.append((n, e))   # but it must not be mistaken for thin data either
            print(f"ERROR {n}: {type(e).__name__}: {e}", file=sys.stderr)
            stale = os.path.join(a.run, "charts", f"{n}.png")
            if os.path.isfile(stale):
                os.remove(stale)
                print(f"      removed stale charts/{n}.png", file=sys.stderr)
    print(f"\n{made}/{len(names)} charts rendered into {a.run}/charts/")
    if thin:
        print(f"Thin data, nothing drawn: {', '.join(thin)} — fill the manifest "
              f"section each one names and re-run.", file=sys.stderr)
    if broken:
        print(f"\nBUG in {len(broken)} chart(s): {', '.join(n for n, _ in broken)}. "
              f"These are code faults, not missing data. Any PNG already on disk "
              f"for them is STALE and the PDF will silently use it.", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
