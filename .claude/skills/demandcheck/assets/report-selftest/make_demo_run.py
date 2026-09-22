#!/usr/bin/env python3
"""Build a small synthetic run directory so the report template can be checked.

Everything here is *invented* — fake brands, fake numbers, ad images drawn on
the spot. Nothing is scraped and nothing is a claim about any real market. The
point is to exercise the whole report path end to end on a machine, in about
ten seconds and for $0.00:

    python3 .claude/skills/demandcheck/assets/report-selftest/make_demo_run.py \
        --out /tmp/dc-demo
    python3 .claude/skills/demandcheck/scripts/eda_charts.py   --run /tmp/dc-demo
    python3 .claude/skills/demandcheck/scripts/make_manifest.py --run /tmp/dc-demo
    python3 .claude/skills/demandcheck/scripts/build_pdf.py    --run /tmp/dc-demo

Run this after changing build_pdf.py, make_manifest.py or eda_charts.py, then
open the PDF and look at it. Needs Pillow.
"""

import argparse
import csv
import json
import os
import random

from PIL import Image, ImageDraw, ImageFont

FONTS = ["/usr/share/fonts/truetype/liberation/LiberationSans-{}.ttf",
         "/usr/share/fonts/truetype/dejavu/DejaVuSans{}.ttf"]

BRANDS = [
    ("Northwind Recovery", "northwindrecovery.com", "AR1000000000000000001", "#0b3d2e", "#34d399"),
    ("Barrel & Co", "barrelandco.com", "AR1000000000000000002", "#1e293b", "#38bdf8"),
    ("Tundra Home", "tundrahome.com", "AR1000000000000000003", "#3b1d2e", "#fb7185"),
    ("Coldwell Labs", "coldwelllabs.com", "AR1000000000000000004", "#1c1917", "#fbbf24"),
]
HEADLINES = [
    ("Recover Like A Pro Athlete", "Cold therapy tubs built for daily use. Free shipping.", "Shop Now"),
    ("Your Daily Reset", "Ice bath therapy at home, no plumbing required.", "Learn More"),
    ("Train Hard. Recover Harder.", "Chiller cools to 39F in under an hour.", "See Models"),
    ("Cold Plunge, Warm Price", "Financing from $59/mo. 30 day home trial.", "Get Pricing"),
    ("Built For Small Spaces", "Fits a balcony. Ships flat. Sets up in an hour.", "Compare"),
    ("The Routine Athletes Keep", "Used by 40+ college programs.", "Read More"),
]
TERMS = [
    # keyword, volume, cpc, class
    ("cold plunge tub", 9900, 1.42, "direct"), ("cold plunge", 74000, 1.10, "direct"),
    ("ice bath tub", 12100, 0.98, "direct"), ("cold plunge tub for sale", 3600, 2.05, "direct"),
    ("best cold plunge", 8100, 2.40, "direct"), ("plunge tub price", 1300, 1.85, "direct"),
    ("cold plunge chiller", 5400, 1.75, "direct"), ("portable ice bath", 6600, 0.86, "direct"),
    ("buy cold plunge", 880, 2.90, "direct"), ("cold plunge tub with chiller", 2400, 2.20, "direct"),
    ("ice bath benefits", 60500, 0.31, "latent"), ("cold exposure therapy", 18100, 0.28, "latent"),
    ("how cold should a cold plunge be", 6600, 0.22, "latent"),
    ("cold plunge before or after workout", 8100, 0.19, "latent"),
    ("diy cold plunge", 14800, 0.24, "latent"), ("ice bath for beginners", 4400, 0.18, "latent"),
    ("cold plunge benefits for men", 9900, 0.33, "latent"),
    ("wim hof method", 33100, 0.26, "latent"), ("cold shower vs ice bath", 2900, 0.21, "latent"),
    ("contrast therapy", 12100, 0.74, "indirect"), ("sauna and cold plunge", 22200, 0.88, "indirect"),
    ("muscle recovery tools", 5400, 1.21, "indirect"), ("infrared sauna at home", 18100, 1.64, "indirect"),
    ("cold plunge repair near me", 320, 3.40, "urgent"),
    ("chiller not cooling fix", 210, 2.95, "urgent"),
    ("emergency ice bath rental", 140, 3.80, "urgent"),
    ("cold plunge maintenance", 590, 1.05, "unclear"), ("plunge login", 1600, 0.0, "unclear"),
]


def font(size, bold=False):
    for pat in FONTS:
        styles = (("Bold",) if bold else ("Regular",)) if "Liberation" in pat \
            else (("-Bold",) if bold else ("",))
        for style in styles:
            path = pat.format(style)
            if os.path.isfile(path):
                return ImageFont.truetype(path, size)
    return ImageFont.load_default()


def wrap(draw, text, f, max_w):
    words, lines, cur = text.split(), [], ""
    for w in words:
        trial = f"{cur} {w}".strip()
        if draw.textlength(trial, font=f) <= max_w:
            cur = trial
        else:
            lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    return lines


def draw_ad(path, brand, headline, desc, cta, size, ink, accent):
    w, h = size
    im = Image.new("RGB", size, "white" if w > 500 else ink)
    d = ImageDraw.Draw(im)
    dark = w <= 500
    fg = "white" if dark else "#111827"
    sub = "#e5e7eb" if dark else "#4b5563"
    pad = int(w * 0.06)
    hs = max(14, int(min(w / 14 if w > 500 else w / 11, h / 6.5)))
    f_h, f_b, f_s = font(hs, True), font(max(11, int(hs * 0.52))), font(max(10, int(hs * 0.42)))
    y = pad
    if not dark:
        d.rectangle([0, 0, w - 1, h - 1], outline="#dadce0")
        d.text((pad, y), "Ad ·", font=f_s, fill="#202124")
        d.text((pad + d.textlength("Ad · ", font=f_s), y), brand[1], font=f_s, fill="#202124")
        y += int(hs * 1.1)
    for line in wrap(d, headline, f_h, w - 2 * pad)[:3]:
        d.text((pad, y), line, font=f_h, fill=(fg if dark else "#1a0dab"))
        y += int(hs * 1.15)
    y += int(hs * 0.35)
    for line in wrap(d, desc, f_b, w - 2 * pad)[:3]:
        d.text((pad, y), line, font=f_b, fill=sub)
        y += int(hs * 0.66)
    y += int(hs * 0.4)
    if y > h - int(hs * 1.5):          # no room left for the button: leave it off
        im.save(path)
        return
    if dark:
        bw = int(d.textlength(cta, font=f_b)) + 2 * pad
        d.rectangle([pad, y, min(pad + bw, w - pad), y + int(hs * 1.15)], fill=accent)
        d.text((pad + int(pad * 0.6), y + int(hs * 0.22)), cta, font=f_b, fill=ink)
    else:
        d.text((pad, y), cta, font=f_b, fill="#1a73e8")
    im.save(path)


def write_csv(path, columns, rows):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(columns)
        w.writerows(rows)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", default="/tmp/dc-demo", help="run directory to create")
    ap.add_argument("--ads", type=int, default=28, help="how many fake ads to draw")
    args = ap.parse_args()
    run = args.out.rstrip("/")
    rnd = random.Random(7)
    for sub in ("clean", "charts", "creatives", "raw"):
        os.makedirs(os.path.join(run, sub), exist_ok=True)

    # keywords
    kw_rows = []
    for i, (kw, vol, cpc, cls) in enumerate(TERMS):
        trend = ";".join(
            f"2026-{m:02d}={int(vol * (1 + 0.35 * (m in (1, 2, 12)) - 0.2 * (m in (6, 7))))}"
            for m in range(1, 13))
        markers = "buy" if any(x in kw for x in ("buy", "for sale", "price")) else (
            "how-to" if kw.startswith("how") or "diy" in kw else (
                "emergency" if "emergency" in kw or "repair" in kw else "none"))
        kw_rows.append([kw, "for-site:northwindrecovery.com" if i else "user-seed",
                        1 + i % 3, vol, f"{cpc:.2f}",
                        "high" if cpc > 1.5 else ("medium" if cpc > 0.5 else "low"),
                        int(min(100, cpc * 35)), f"{max(cpc - 0.3, 0.05):.2f}",
                        f"{cpc + 0.9:.2f}", f"{vol * cpc:.0f}", markers, cls, trend])
    write_csv(os.path.join(run, "clean", "keywords.csv"),
              ["keyword", "source", "wave", "search_volume", "cpc", "competition",
               "competition_index", "low_top_of_page_bid", "high_top_of_page_bid",
               "spend_proxy", "intent_markers", "demand_class", "monthly_trend"], kw_rows)

    # domains + advertisers
    dom_rows, adv_rows = [], []
    for i, (name, dom, aid, _ink, _acc) in enumerate(BRANDS):
        dom_rows.append([dom, "competitor", "serp:cold plunge tub", 1, 4 - i, i + 1,
                         "true", "sells tubs directly"])
        adv_rows.append([aid, name, dom, "true", 40 + 10 * i, "ads:" + dom])
    for extra in ("healthline.com", "reddit.com", "youtube.com", "wirecutter.com"):
        dom_rows.append([extra, "media", "serp:ice bath benefits", 2, 3, 2, "false",
                         "publisher capturing the practice terms"])
    write_csv(os.path.join(run, "clean", "domains.csv"),
              ["domain", "type", "discovered_via", "first_wave", "serp_appearances",
               "best_position", "is_advertiser", "notes"], dom_rows)
    write_csv(os.path.join(run, "clean", "advertisers.csv"),
              ["advertiser_id", "title", "domain", "verified", "approx_ads_count",
               "discovered_via"], adv_rows)

    # ads + creatives + ad copy
    ads_rows, copy_rows = [], []
    sizes = [(600, 260), (300, 250), (728, 200), (480, 320)]
    for i in range(args.ads):
        brand = BRANDS[i % len(BRANDS)]
        name, dom, aid, ink, accent = brand
        head, desc, cta = HEADLINES[i % len(HEADLINES)]
        cid = f"CR{7000000000 + i * 37}"
        days = int(rnd.choice([6, 14, 23, 41, 88, 120, 190, 260, 340, 412]))
        active = "true" if days > 60 or i % 3 == 0 else "false"
        size = sizes[i % len(sizes)]
        d = os.path.join(run, "creatives", dom)
        os.makedirs(d, exist_ok=True)
        png = os.path.join(d, f"{cid}.png")
        draw_ad(png, brand, head, desc, cta, size, ink, accent)
        fmt = "text" if size[0] > 500 else "image"
        ads_rows.append([cid, aid, name, fmt, "2025-09-01", "2026-08-01", days,
                         active, "png", f"https://{dom}/", f"creatives/{dom}/{cid}.png"])
        copy_rows.append([cid, name, head, desc, cta, dom, "ocr:tesseract",
                          f"{rnd.randint(78, 97)}"])
    write_csv(os.path.join(run, "clean", "ads.csv"),
              ["creative_id", "advertiser_id", "advertiser_title", "format",
               "first_shown", "last_shown", "days_running", "active", "copy_kind",
               "url", "png_path"], ads_rows)
    write_csv(os.path.join(run, "clean", "ad_copy.csv"),
              ["creative_id", "advertiser_title", "headline", "description", "cta",
               "other_text", "extraction", "ocr_conf"], copy_rows)

    # serp results
    serp_rows = []
    for q in ("cold plunge tub", "ice bath benefits"):
        for pos, (name, dom, *_rest) in enumerate(BRANDS, start=1):
            serp_rows.append([q, 1, pos, f"{name} — cold plunge tubs",
                              f"https://{dom}/shop", dom,
                              "Cold therapy tubs shipped flat.",
                              "true" if pos < 3 else "false"])
    write_csv(os.path.join(run, "clean", "serp_results.csv"),
              ["query", "wave", "position", "title", "url", "domain", "snippet",
               "is_ad"], serp_rows)

    # state.json — budget ledger + a conjecture register with one refutation
    ledger = [{"ts": f"2026-08-14T1{i//6}:{(i*7)%60:02d}:00Z",
               "instrument": ["serp", "keywords", "ads"][i % 3],
               "usd": [0.005, 0.07, 0.006][i % 3], "calls": 1,
               "cached": i % 11 == 0,
               "note": ["SERP on a harvested keyword", "for-site keyword harvest",
                        "ad library pull, depth 120"][i % 3]} for i in range(24)]
    state = {
        "seed": "cold plunge tub", "seed_kind": "keyword", "slug": "demo",
        "geo": "US", "language": "en", "location_code": 2840, "scope": "expressed",
        "budget": {"usd_cap": 5.0,
                   "spent_usd": round(sum(e["usd"] for e in ledger if not e["cached"]), 4),
                   "calls": sum(1 for e in ledger if not e["cached"]),
                   "ledger": ledger},
        "wave": 3, "waves": [], "nodes": {},
        "conjectures": {
            "C1": {"text": "Demand here is mostly latent — the pain is real but "
                           "buyers do not know the category name.",
                   "forbids": "category-name keywords above $3 with advertisers "
                              "sustaining them past 90 days",
                   "check": "3+ category terms above $3 CPC refutes this",
                   "status": "refuted", "wave": 1,
                   "history": [{"ts": "2026-08-14T12:00:00Z", "wave": 2,
                                "status": "refuted",
                                "evidence": "'cold plunge tub' prices at $1.42 on "
                                            "9,900 searches with four advertisers "
                                            "past 90 days"}]},
            "C2": {"text": "The buyers are athletes, so the ads that keep running "
                           "sell performance rather than home comfort.",
                   "forbids": "long-running creatives leading on luxury framing",
                   "check": "", "status": "survived", "wave": 1,
                   "history": [{"ts": "2026-08-14T15:00:00Z", "wave": 3,
                                "status": "survived",
                                "evidence": "11 of 14 creatives past 90 days lead "
                                            "on recovery language"}]},
        },
        "serp_daily": {"2026-08-14": 12},
    }
    with open(os.path.join(run, "state.json"), "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2)
    with open(os.path.join(run, "notebook.md"), "w", encoding="utf-8") as f:
        f.write("# Demo run notebook\n\nSynthetic fixture — no real data.\n")

    print(f"demo run written to {run}")
    print(f"  {len(kw_rows)} keywords · {len(ads_rows)} ads with images · "
          f"{len(adv_rows)} advertisers")
    print("  next: eda_charts.py --run {0} && make_manifest.py --run {0} && "
          "build_pdf.py --run {0}".format(run))


if __name__ == "__main__":
    main()
