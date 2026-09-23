#!/usr/bin/env python3
"""cac.py — what a customer costs to buy, and what that buys you.

This script computes acquisition cost and lays out the trade-offs. It does
NOT grade them. There is no LTV:CAC bar here, no pass/fail verdict, and no
"this idea works" flag — LTV needs assumed churn and assumed ARPU, and a
ratio built from two guesses launders them into false precision. What the
data can actually support is: this is what a customer costs, here is what
you'd have to charge or retain for that to pay off, and here are the other
channels. The human decides whether it's worth it.

  CAC              = CPC / funnel            (funnel = P(click -> paying))
  months_to_repay  = CAC / (price * margin)  (per candidate monthly price)
  content_CAC      = cost_per_post / (median_views * view_to_visit * funnel)

Three scenarios, derived from your base inputs (funnel is the soft number,
so it swings widest):

  conservative: CPC*1.25  funnel*0.60
  base:         as given
  optimistic:   CPC*0.85  funnel*1.40

Reachable-demand ceiling (with --volume):
  clicks/mo    = volume * 0.04     (top-of-page share a new entrant can win)
  customers/mo = clicks * base funnel
  spend/mo     = clicks * CPC

Funnel presets are conservative-end category defaults — override whenever you
measured a better anchor (an ad test, the user's own funnel data), and cite
it. Prices come from P8 (observed competitor pricing) or from the user; they
are options to weigh, not a forecast of what they'll charge.

Stdlib-only.
"""

import argparse
import json
import sys

PRESETS = {
    # name: funnel (visit -> paid)
    "b2c_sub": 0.010,
    "prosumer": 0.015,
    "b2b_smb": 0.020,
    "b2b_mid": 0.005,
}

SCENARIOS = {
    "conservative": {"cpc": 1.25, "funnel": 0.60},
    "base": {"cpc": 1.00, "funnel": 1.00},
    "optimistic": {"cpc": 0.85, "funnel": 1.40},
}

ORDER = ("conservative", "base", "optimistic")
REACHABLE_CLICK_SHARE = 0.04
COHORT_SIZES = (10, 100)


def die(msg):
    print(f"error: {msg}", file=sys.stderr)
    sys.exit(2)


def rate(value, name):
    if value is None:
        return None
    if not (0 < value <= 1):
        die(f"{name} must be a fraction in (0, 1] — e.g. 0.02 means 2% (got {value})")
    return value


def compute(cpc, funnel, margin, prices=None, volume=None, ceiling=None, content=None):
    prices = prices or []
    scenarios = {}
    for name, m in SCENARIOS.items():
        s_cpc = cpc * m["cpc"]
        s_funnel = min(funnel * m["funnel"], 1.0)
        cac = s_cpc / s_funnel
        row = {
            "cpc": round(s_cpc, 2),
            "funnel": round(s_funnel, 5),
            "cac": round(cac, 2),
            "cost_per_cohort": {str(n): round(cac * n, 2) for n in COHORT_SIZES},
        }
        if content:
            visits = content["median_views"] * content["view_to_visit"]
            row["content_cac"] = round(
                content["cost_per_post"] / (visits * s_funnel), 2)
        scenarios[name] = row

    result = {
        "inputs": {
            "cpc": cpc, "funnel": funnel, "margin": margin,
            "prices": prices, "volume": volume, "ceiling": ceiling,
            "content": content,
        },
        "scenarios": scenarios,
    }

    if prices:
        result["repay"] = [
            {
                "price": p,
                "months": {
                    name: round(scenarios[name]["cac"] / (p * margin), 1)
                    for name in ORDER
                },
            }
            for p in prices
        ]

    if volume:
        clicks = volume * REACHABLE_CLICK_SHARE
        result["reachable"] = {
            "click_share_assumed": REACHABLE_CLICK_SHARE,
            "clicks_per_month": round(clicks),
            "customers_per_month": round(clicks * funnel, 1),
            "ad_spend_ceiling_per_month": round(clicks * cpc, 2),
        }

    if ceiling is not None:
        result["ceiling_check"] = {
            "user_ceiling_usd": ceiling,
            "under_ceiling": [n for n in ORDER if scenarios[n]["cac"] <= ceiling],
        }

    return result


def render(result, label):
    i = result["inputs"]
    money = lambda v: "$" + format(v, ",.2f")  # noqa: E731

    print(f"acquisition cost — {label or 'unnamed node'}")
    print(
        f"inputs: CPC ${i['cpc']:.2f} · funnel {i['funnel'] * 100:.2f}% · "
        f"margin {i['margin'] * 100:.0f}%"
        + (f" · prices {', '.join('$' + format(p, 'g') for p in i['prices'])}/mo"
           if i["prices"] else "")
    )
    print()

    has_content = "content_cac" in result["scenarios"]["base"]
    head = f"{'scenario':<14}{'CPC':>8}{'funnel':>9}{'CAC':>12}"
    head += f"{'10 customers':>15}{'100 customers':>15}"
    if has_content:
        head += f"{'content CAC':>14}"
    print(head)
    for name in ORDER:
        s = result["scenarios"][name]
        line = (
            f"{name:<14}{money(s['cpc']):>8}{s['funnel'] * 100:>8.2f}%"
            f"{money(s['cac']):>12}"
            f"{money(s['cost_per_cohort']['10']):>15}"
            f"{money(s['cost_per_cohort']['100']):>15}"
        )
        if has_content:
            line += f"{money(s['content_cac']):>14}"
        print(line)
    if has_content:
        c = i["content"]
        print(
            f"  content channel assumes ${c['cost_per_post']:g}/post · "
            f"{c['median_views']:,} median views · "
            f"{c['view_to_visit'] * 100:g}% view→visit — all three are estimates, "
            f"not measurements"
        )

    if "repay" in result:
        print()
        print(f"months of retention needed to repay CAC (at {i['margin'] * 100:.0f}% margin)")
        print(f"{'price/mo':<14}" + "".join(f"{n:>15}" for n in ORDER))
        for row in result["repay"]:
            print(
                f"{'$' + format(row['price'], 'g'):<14}"
                + "".join(f"{format(row['months'][n], '.1f') + ' mo':>15}" for n in ORDER)
            )
        print("  keep a customer longer than that and acquisition pays for itself; "
              "shorter and it doesn't.")

    if "reachable" in result:
        r = result["reachable"]
        print()
        print(
            f"reach ceiling @ {r['click_share_assumed'] * 100:.0f}% click share: "
            f"~{r['clicks_per_month']:,} clicks/mo → ~{r['customers_per_month']:g} "
            f"customers/mo at ~${r['ad_spend_ceiling_per_month']:,.2f}/mo spend"
        )

    if "ceiling_check" in result:
        c = result["ceiling_check"]
        under = c["under_ceiling"]
        print()
        print(
            f"against YOUR stated ceiling of ${c['user_ceiling_usd']:,.2f}/customer: "
            + (f"under it in {', '.join(under)}" if under else "over it in every scenario")
        )

    print()
    print("no verdict here by design — CAC is measured, worth-it is yours to judge.")
    print("assumptions in play: funnel "
          + ("preset" if result.get("_preset_used") else "as passed")
          + ", scenario multipliers, margin"
          + (", 4% click share" if "reachable" in result else "")
          + (", content estimates" if has_content else "")
          + " — list them in the report's assumptions register.")
    print("options to put to the user: hold the price and test the funnel · raise the "
          "price (see the repay table) · switch channel · narrow the WHO to cheaper "
          "clicks · walk away. Numbers above, decision theirs.")


def main(argv=None):
    p = argparse.ArgumentParser(
        prog="cac.py", description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--cpc", type=float, required=True,
                   help="volume-weighted median CPC of the commercial cluster (USD)")
    p.add_argument("--funnel", type=float,
                   help="P(click->paying) as a fraction, e.g. 0.02")
    p.add_argument("--funnel-preset", choices=sorted(PRESETS),
                   help="use a category default funnel: "
                        + ", ".join(f"{k}={v:.3f}" for k, v in sorted(PRESETS.items())))
    p.add_argument("--price", type=float, action="append", metavar="USD",
                   help="candidate monthly price for the repay table (repeatable); "
                        "anchor these on P8 observed pricing, not on hope")
    p.add_argument("--margin", type=float, default=0.85,
                   help="gross margin fraction (default 0.85; lower for inference-heavy)")
    p.add_argument("--volume", type=int,
                   help="monthly commercial-intent cluster volume (enables reach ceiling)")
    p.add_argument("--ceiling", type=float, metavar="USD",
                   help="the user's own stated max CAC, if they named one — reported "
                        "as their line, never as this skill's bar")
    p.add_argument("--content-cost-per-post", type=float,
                   help="organic channel option: production cost per post (USD)")
    p.add_argument("--content-median-views", type=int,
                   help="organic channel option: median views per post (from P4)")
    p.add_argument("--content-view-to-visit", type=float, default=0.005,
                   help="organic channel option: view->visit rate (default 0.005)")
    p.add_argument("--label", help="node id + title for the header")
    p.add_argument("--json", metavar="PATH",
                   help="also bank the full result as JSON (put it in the experiment's data/)")
    args = p.parse_args(argv)

    if args.funnel is None and args.funnel_preset is None:
        die("pass --funnel or --funnel-preset")
    funnel = (rate(args.funnel, "--funnel") if args.funnel is not None
              else PRESETS[args.funnel_preset])
    rate(args.margin, "--margin")
    if args.cpc <= 0:
        die("--cpc must be positive")
    for pr in args.price or []:
        if pr <= 0:
            die("--price must be positive")
    if args.ceiling is not None and args.ceiling <= 0:
        die("--ceiling must be positive")

    content = None
    if args.content_cost_per_post or args.content_median_views:
        if not (args.content_cost_per_post and args.content_median_views):
            die("content channel needs both --content-cost-per-post and "
                "--content-median-views")
        rate(args.content_view_to_visit, "--content-view-to-visit")
        content = {
            "cost_per_post": args.content_cost_per_post,
            "median_views": args.content_median_views,
            "view_to_visit": args.content_view_to_visit,
        }

    result = compute(args.cpc, funnel, args.margin, prices=args.price,
                     volume=args.volume, ceiling=args.ceiling, content=content)
    result["_preset_used"] = bool(args.funnel_preset)
    result["label"] = args.label
    render(result, args.label)

    if args.json:
        result.pop("_preset_used", None)
        with open(args.json, "w", encoding="utf-8") as f:
            json.dump(result, f, indent=2)
            f.write("\n")
        print(f"banked: {args.json}")


def _quiet_broken_pipe() -> None:
    """Exit quietly when stdout closes early, e.g. `maze.py state | head -3`.

    Python turns SIGPIPE into BrokenPipeError and prints a traceback at
    shutdown; restoring the default handler makes these CLIs behave like any
    other command in a pipeline.
    """
    try:
        import signal
        signal.signal(signal.SIGPIPE, signal.SIG_DFL)
    except (ImportError, AttributeError, ValueError):
        pass  # not POSIX, or not on the main thread


if __name__ == "__main__":
    _quiet_broken_pipe()
    main()
