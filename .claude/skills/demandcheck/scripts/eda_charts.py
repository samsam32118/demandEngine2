#!/usr/bin/env python3
"""eda_charts.py — render the demandcheck EDA chart set from clean/*.csv.

Reads the canonical tables (schemas: references/traversal.md) and writes PNGs
into <run>/charts/. Every chart is optional: missing tables, missing columns,
or fewer than 3 data points skip that chart with a stderr note instead of
failing the run — a thin survey produces a thin report, never a crash.

Usage:
    python3 .claude/skills/demandcheck/scripts/eda_charts.py --run research/demandcheck/<slug>

Needs matplotlib (the repo's one deliberate non-stdlib exception):
    python3 -m pip install matplotlib reportlab
"""

import argparse
import csv
import json
import os
import re
import sys
from collections import Counter, defaultdict

try:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.ticker import FuncFormatter
except ImportError:
    print("error: matplotlib is not installed.\n"
          "fix:   python3 -m pip install matplotlib reportlab", file=sys.stderr)
    sys.exit(3)

DPI = 150

# Palette shared with build_pdf.py. The four demand-class hues were checked
# with the dataviz skill's validator (scripts/validate_palette.js, --pairs all,
# light mode): every pair clears the colour-vision-deficiency and
# normal-vision separation floors, so the charts stay readable for readers who
# cannot rely on hue. Every series also carries a direct label or an axis
# label, which is the relief the validator's contrast warning asks for.
CLASS_COLORS = {
    "direct": "#2a78d6", "indirect": "#4a3aa7", "latent": "#1baf7a",
    "urgent": "#eb6834", "unclear": "#9aa1ad",
}
CLASS_ORDER = ["direct", "indirect", "latent", "urgent", "unclear"]
INK = "#14161c"
MUTED = "#6b7280"
NEUTRAL = "#c9ccd1"
ACCENT = "#2a78d6"
GOOD = "#1baf7a"
GRID = "#e6e8ec"

plt.rcParams.update({
    "figure.facecolor": "white", "axes.facecolor": "white",
    "font.size": 9, "text.color": INK,
    "axes.labelcolor": MUTED, "axes.labelsize": 8.5, "axes.edgecolor": "#c3c7ce",
    "axes.titlesize": 11, "axes.titlecolor": INK,
    "xtick.color": MUTED, "ytick.color": MUTED,
    "xtick.labelsize": 8, "ytick.labelsize": 8,
    "legend.fontsize": 8, "savefig.facecolor": "white",
})

STOPWORDS = set("""a an and are as at be by for from get has have how in is it
of on or our the this to with you your what when where why will can up off do
does its more most all any new now""".split())

_num_fmt = FuncFormatter(lambda x, _: f"{x:,.0f}")
_usd_fmt = FuncFormatter(lambda x, _: f"${x:,.2f}")


def skip(name: str, why: str):
    print(f"skip {name}: {why}", file=sys.stderr)


def read_csv(run: str, table: str):
    path = os.path.join(run, "clean", f"{table}.csv")
    if not os.path.isfile(path):
        return []
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def fnum(row, col):
    """Float from a CSV cell; None when empty/absent/unparsable."""
    v = (row.get(col) or "").strip().replace("$", "").replace(",", "")
    try:
        return float(v)
    except ValueError:
        return None


def truthy(row, col):
    return (row.get(col) or "").strip().lower() in ("true", "1", "yes", "y")


def median(xs):
    xs = sorted(xs)
    n = len(xs)
    if not n:
        return None
    return xs[n // 2] if n % 2 else (xs[n // 2 - 1] + xs[n // 2]) / 2


def new_fig(w=8.0, h=4.8, grid="y"):
    fig, ax = plt.subplots(figsize=(w, h))
    ax.spines[["top", "right"]].set_visible(False)
    ax.spines[["left", "bottom"]].set_linewidth(0.6)
    if grid:
        ax.grid(axis=grid, color=GRID, linewidth=0.6)
        ax.set_axisbelow(True)
    return fig, ax


def finish(fig, ax, run, name, title, source):
    ax.set_title(title, loc="left", fontsize=11, fontweight="bold", pad=12,
                 color=INK)
    fig.text(0.008, 0.006, source, fontsize=6.5, color="#9aa1ad")
    fig.tight_layout(rect=(0, 0.025, 1, 1))
    out = os.path.join(run, "charts", name)
    fig.savefig(out, dpi=DPI)
    plt.close(fig)
    print(f"wrote {out}")


def keyword_rows(run):
    rows = []
    for r in read_csv(run, "keywords"):
        rows.append({
            "keyword": (r.get("keyword") or "").strip(),
            "volume": fnum(r, "search_volume"),
            "cpc": fnum(r, "cpc"),
            "comp": fnum(r, "competition_index"),
            "spend": fnum(r, "spend_proxy"),
            "cls": (r.get("demand_class") or "unclear").strip().lower() or "unclear",
            "trend": (r.get("monthly_trend") or "").strip(),
        })
    return [r for r in rows if r["keyword"]]


# ------------------------------------------------------------------- charts

def chart_demand_mix(run, kws, source):
    by_cls = defaultdict(float)
    for r in kws:
        if r["volume"]:
            by_cls[r["cls"]] += r["volume"]
    classes = [c for c in CLASS_ORDER if by_cls.get(c)]
    if len(classes) < 2 or len(kws) < 3:
        return skip("demand_mix", "needs >=3 keywords across >=2 classes")
    fig, ax = new_fig()
    vals = [by_cls[c] for c in classes]
    ax.bar(classes, vals, color=[CLASS_COLORS[c] for c in classes])
    for i, v in enumerate(vals):
        ax.text(i, v, f"{v:,.0f}", ha="center", va="bottom", fontsize=9)
    ax.yaxis.set_major_formatter(_num_fmt)
    ax.set_ylabel("monthly searches")
    finish(fig, ax, run, "demand_mix.png",
           "How big each kind of demand is (monthly searches by demand class)", source)


def chart_cpc_by_class(run, kws, source):
    by_cls = defaultdict(list)
    for r in kws:
        if r["cpc"]:
            by_cls[r["cls"]].append(r["cpc"])
    classes = [c for c in CLASS_ORDER if len(by_cls.get(c, [])) >= 2]
    if len(classes) < 2:
        return skip("cpc_by_class", "needs >=2 classes with >=2 priced keywords")
    fig, ax = new_fig()
    meds, lo_err, hi_err = [], [], []
    for c in classes:
        xs = sorted(by_cls[c])
        m = median(xs)
        meds.append(m)
        lo_err.append(max(0.0, m - xs[len(xs) // 4]))
        hi_err.append(max(0.0, xs[(3 * len(xs)) // 4] - m))
    ax.bar(classes, meds, color=[CLASS_COLORS[c] for c in classes],
           yerr=[lo_err, hi_err], capsize=4, error_kw={"ecolor": "#374151", "lw": 1})
    for i, v in enumerate(meds):
        ax.text(i, v, f"${v:,.2f}", ha="center", va="bottom", fontsize=9)
    ax.yaxis.set_major_formatter(_usd_fmt)
    ax.set_ylabel("median cost per click")
    finish(fig, ax, run, "cpc_by_class.png",
           "What each kind of demand costs per click (median CPC, whiskers = middle 50%)",
           source)


def chart_demand_map(run, kws, source):
    pts = [r for r in kws if r["volume"] and r["cpc"]]
    if len(pts) < 3:
        return skip("demand_map", "needs >=3 keywords with volume and CPC")
    fig, ax = new_fig(8.0, 5.6, grid="both")
    for c in CLASS_ORDER:
        sub = [r for r in pts if r["cls"] == c]
        if sub:
            ax.scatter([r["volume"] for r in sub], [r["cpc"] for r in sub],
                       s=28, alpha=0.75, color=CLASS_COLORS[c], label=c, edgecolors="none")
    ax.set_xscale("log")
    ax.set_yscale("log")
    for r in sorted(pts, key=lambda r: -(r["spend"] or 0))[:8]:
        ax.annotate(r["keyword"], (r["volume"], r["cpc"]), fontsize=7,
                    xytext=(4, 4), textcoords="offset points", color=MUTED)
    ax.set_xlabel("monthly searches (log scale)")
    ax.set_ylabel("cost per click (log scale)")
    ax.yaxis.set_major_formatter(_usd_fmt)
    ax.xaxis.set_major_formatter(_num_fmt)
    ax.legend(frameon=False, fontsize=8)
    finish(fig, ax, run, "demand_map.png",
           "The demand landscape: every harvested keyword by size and price", source)


def chart_latent_gap(run, kws, source):
    latent = [r for r in kws if r["cls"] == "latent" and r["volume"]]
    if len(latent) < 3:
        pos = [r["cpc"] for r in kws if r["cpc"]]
        med = median(pos) or 0
        latent = [r for r in kws if r["volume"]
                  and (not r["cpc"] or r["cpc"] <= 0.4 * med)
                  and (r["comp"] is None or r["comp"] <= 33)]
    latent = sorted(latent, key=lambda r: -r["volume"])[:10]
    if len(latent) < 3:
        return skip("latent_gap", "no meaningful weak-auction cluster found")
    fig, ax = new_fig(grid="x")
    labels = [r["keyword"] for r in latent][::-1]
    vals = [r["volume"] for r in latent][::-1]
    ax.barh(labels, vals, color=CLASS_COLORS["latent"])
    for i, (v, r) in enumerate(zip(vals, latent[::-1])):
        cpc = f"${r['cpc']:,.2f}" if r["cpc"] else "no auction"
        ax.text(v, i, f" {v:,.0f} · {cpc}", va="center", fontsize=8)
    ax.xaxis.set_major_formatter(_num_fmt)
    ax.set_xlabel("monthly searches")
    finish(fig, ax, run, "latent_gap.png",
           "The biggest unpriced demand: high volume, weak ad auction", source)


def chart_seasonality(run, kws, source):
    top = [r for r in sorted(kws, key=lambda r: -(r["spend"] or 0)) if r["trend"]][:5]
    series = []
    for r in top:
        pts = []
        for part in r["trend"].split(";"):
            m = re.match(r"^(\d{4}-\d{2})=(\d+)$", part.strip())
            if m:
                pts.append((m.group(1), int(m.group(2))))
        if len(pts) >= 6:
            series.append((r["keyword"], sorted(pts)))
    if len(series) < 2:
        return skip("seasonality", "needs >=2 keywords with >=6 months of trend data")
    fig, ax = new_fig(8.0, 4.4)
    for kw, pts in series:
        ax.plot([p[0] for p in pts], [p[1] for p in pts], marker="o",
                markersize=3, linewidth=1.5, label=kw)
    ax.yaxis.set_major_formatter(_num_fmt)
    ax.set_ylabel("monthly searches")
    ax.tick_params(axis="x", labelsize=7, rotation=45)
    ax.legend(frameon=False, fontsize=8)
    finish(fig, ax, run, "seasonality.png",
           "When this demand happens: 12-month search trend of the top clusters", source)


def chart_capture_leaders(run, ads, source):
    per = defaultdict(lambda: [0, 0])  # title -> [total, active]
    for r in ads:
        t = (r.get("advertiser_title") or "").strip() or "(unknown)"
        per[t][0] += 1
        if truthy(r, "active"):
            per[t][1] += 1
    rows = sorted(per.items(), key=lambda kv: -kv[1][0])[:10]
    if len(rows) < 3:
        return skip("capture_leaders", "needs >=3 advertisers with creatives")
    fig, ax = new_fig(grid="x")
    labels = [t for t, _ in rows][::-1]
    total = [c[0] for _, c in rows][::-1]
    active = [c[1] for _, c in rows][::-1]
    ax.barh(labels, total, color=NEUTRAL, label="every ad found")
    ax.barh(labels, active, color=ACCENT, label="still running")
    for i, (t, a) in enumerate(zip(total, active)):
        ax.text(t, i, f" {t} ({a} active)", va="center", fontsize=8)
    ax.xaxis.set_major_formatter(_num_fmt)
    ax.set_xlabel("ad creatives found")
    ax.legend(frameon=False, fontsize=8, loc="lower right")
    finish(fig, ax, run, "capture_leaders.png",
           "Who pays for this demand hardest (creatives per advertiser)", source)


def chart_ad_longevity(run, ads, source):
    days = [fnum(r, "days_running") for r in ads]
    days = [d for d in days if d is not None and d >= 0]
    if len(days) < 3:
        return skip("ad_longevity", "needs >=3 creatives with run dates")
    fig, ax = new_fig()
    n, bins, patches = ax.hist(days, bins=min(24, max(6, len(days) // 4)),
                               color=NEUTRAL, edgecolor="white")
    for b, patch in zip(bins, patches):
        if b >= 90:
            patch.set_facecolor(GOOD)
    proven = sum(1 for d in days if d >= 90)
    ax.axvline(90, color=GOOD, linestyle="--", linewidth=1)
    ax.text(90, ax.get_ylim()[1] * 0.95, "  90 days = proven",
            fontsize=8, color=GOOD, va="top")
    ax.set_xlabel("days the creative has run")
    ax.set_ylabel("creatives")
    finish(fig, ax, run, "ad_longevity.png",
           f"How much of this advertising has earned its keep "
           f"({proven} of {len(days)} ads have run 90+ days)",
           source)


def _tokens(text):
    return [w for w in re.findall(r"[a-z][a-z'-]+", (text or "").lower())
            if w not in STOPWORDS and len(w) > 2]


def chart_proven_messaging(run, ads, copy_rows, source):
    days_by_id = {r.get("creative_id"): fnum(r, "days_running") or 0 for r in ads}
    active_by_id = {r.get("creative_id"): truthy(r, "active") for r in ads}
    proven_ads, other_ads = [], []
    for r in copy_rows:
        cid = r.get("creative_id")
        text = " ".join(filter(None, [r.get("headline"), r.get("description"),
                                      r.get("cta"), r.get("other_text")]))
        if "ILLEGIBLE" in text or not text.strip():
            continue
        d = days_by_id.get(cid, 0)
        (proven_ads if d >= 90 or (d >= 60 and active_by_id.get(cid)) else other_ads).append(text)
    if len(proven_ads) < 3 or len(other_ads) < 3:
        return skip("proven_messaging", "needs >=3 proven and >=3 other ads with readable copy")
    def share(corpus):
        c = Counter()
        for text in corpus:
            c.update(set(_tokens(text)))
        return {w: n / len(corpus) for w, n in c.items()}
    p_share, o_share = share(proven_ads), share(other_ads)
    top = [w for w, _ in sorted(p_share.items(), key=lambda kv: -kv[1])[:10]]
    if len(top) < 3:
        return skip("proven_messaging", "not enough distinct vocabulary")
    fig, ax = new_fig()
    import numpy as _np  # matplotlib ships numpy
    x = _np.arange(len(top))
    ax.bar(x - 0.2, [p_share[w] * 100 for w in top], width=0.4,
           color=GOOD, label=f"ads running 90+ days (n={len(proven_ads)})")
    ax.bar(x + 0.2, [o_share.get(w, 0) * 100 for w in top], width=0.4,
           color=NEUTRAL, label=f"newer ads (n={len(other_ads)})")
    ax.set_xticks(x, top, rotation=30, ha="right", fontsize=8)
    ax.set_ylabel("% of ads using the word")
    ax.legend(frameon=False, fontsize=8)
    finish(fig, ax, run, "proven_messaging.png",
           "The words that sustained ad spend uses (90+ day ad copy vs the rest)", source)


def chart_money_map(run, kws, source):
    rows = [r for r in kws if r["spend"]]
    rows = sorted(rows, key=lambda r: -r["spend"])[:15]
    if len(rows) < 3:
        return skip("money_map", "needs >=3 keywords with a spend proxy")
    fig, ax = new_fig(8.0, 5.2, grid="x")
    labels = [r["keyword"] for r in rows][::-1]
    vals = [r["spend"] for r in rows][::-1]
    ax.barh(labels, vals, color=[CLASS_COLORS.get(r["cls"], NEUTRAL) for r in rows[::-1]])
    for i, v in enumerate(vals):
        ax.text(v, i, f" ${v:,.0f}", va="center", fontsize=8)
    ax.xaxis.set_major_formatter(_usd_fmt)
    ax.set_xlabel("monthly search spend estimate (searches × price per click)")
    finish(fig, ax, run, "money_map.png",
           "Where the search spend concentrates (color = demand class)", source)


def chart_format_mix(run, ads, source):
    counts = Counter((r.get("format") or "unknown").strip().lower() for r in ads)
    counts = Counter({k: v for k, v in counts.items() if k and v})
    if sum(counts.values()) < 3 or len(counts) < 2:
        return skip("format_mix", "needs >=3 creatives across >=2 formats")
    fig, ax = new_fig(6.4, 4.2)
    labels = [k for k, _ in counts.most_common()]
    vals = [v for _, v in counts.most_common()]
    ax.bar(labels, vals, color=ACCENT)
    for i, v in enumerate(vals):
        ax.text(i, v, f"{v:,}", ha="center", va="bottom", fontsize=9)
    ax.set_ylabel("creatives")
    finish(fig, ax, run, "format_mix.png",
           "How this market advertises (creatives by format)", source)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--run", required=True, help="run directory (contains clean/ and state.json)")
    args = ap.parse_args()
    run = args.run.rstrip("/")
    if not os.path.isdir(os.path.join(run, "clean")):
        print(f"error: {run}/clean not found", file=sys.stderr)
        sys.exit(2)
    os.makedirs(os.path.join(run, "charts"), exist_ok=True)

    geo, month = "US", ""
    state_path = os.path.join(run, "state.json")
    if os.path.isfile(state_path):
        with open(state_path, encoding="utf-8") as f:
            st = json.load(f)
        geo = f"{st.get('geo', 'US')}/{st.get('language', 'en')}"
        month = (st.get("created") or "")[:7]
    source = (f"Source: Google Ads planner + Ads Transparency data via DataForSEO; "
              f"Google SERPs via Bright Data · {geo} · {month}")

    kws = keyword_rows(run)
    ads = read_csv(run, "ads")
    copy_rows = read_csv(run, "ad_copy")

    chart_demand_mix(run, kws, source)
    chart_cpc_by_class(run, kws, source)
    chart_demand_map(run, kws, source)
    chart_latent_gap(run, kws, source)
    chart_seasonality(run, kws, source)
    chart_capture_leaders(run, ads, source)
    chart_ad_longevity(run, ads, source)
    chart_proven_messaging(run, ads, copy_rows, source)
    chart_money_map(run, kws, source)
    chart_format_mix(run, ads, source)


if __name__ == "__main__":
    main()
