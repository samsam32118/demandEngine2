#!/usr/bin/env python3
"""Score ocr_creatives.py's field assignment against known ad copy, and time it.

The regression harness for the OCR reader. `make_bench.py` draws 18 synthetic
creatives spanning the layouts a Google ad library actually returns — search
text ads, banners in four IAB sizes, dark mode, buttons, price heroes, display
URLs, sitelinks, app-install, photo overlays, low contrast, serif, 9px type,
and a photograph with no text at all — each with its true headline,
description, CTA and other_text recorded in truth.json. This runs the reader
over them and reports per-field accuracy plus latency.

Run it after touching any heuristic in ocr_creatives.py:

    python3 -m pip install pillow          # fixtures are drawn with Pillow
    python3 .claude/skills/demandcheck/assets/ocr-benchmark/make_bench.py
    python3 .claude/skills/demandcheck/assets/ocr-benchmark/score.py

Baseline on tesseract 5.3.4 (this repo, 4 CPUs): headline 100%,
description 97%, cta 89%, other 83% — 92% overall at ~530ms per image
single-threaded. A change that drops any field materially is a regression;
`--verbose` prints every field so you can see which case moved.
"""

import argparse
import json
import os
import re
import statistics
import sys
import tempfile
import time
from collections import Counter

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "..", "scripts"))
sys.path.insert(0, os.path.abspath(os.path.join(HERE, "..", "..", "scripts")))
import ocr_creatives as O  # noqa: E402


def toks(s):
    return [t for t in re.findall(r"[a-z0-9$£€%.,]+", (s or "").lower()) if t]


def f1(a, b):
    """Token F1 — order-insensitive overlap, so a stray comma is not a fail."""
    A, B = toks(a), toks(b)
    if not A and not B:
        return 1.0
    if not A or not B:
        return 0.0
    inter = sum((Counter(A) & Counter(B)).values())
    if not inter:
        return 0.0
    p, r = inter / len(A), inter / len(B)
    return 2 * p * r / (p + r)


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--psm", default="3")
    ap.add_argument("--no-sweep", action="store_true")
    ap.add_argument("-v", "--verbose", action="store_true")
    a = ap.parse_args()
    psms = [int(x) for x in a.psm.split(",") if x]
    truth_path = os.path.join(HERE, "truth.json")
    if not os.path.isfile(truth_path):
        sys.exit(f"no truth.json — run make_bench.py first ({HERE})")
    cases = json.load(open(truth_path, encoding="utf-8"))["cases"]
    if not os.path.isdir(os.path.join(HERE, "creatives")):
        sys.exit(f"no creatives/ — run make_bench.py first ({HERE})")

    scores = {"headline": [], "description": [], "cta": [], "other": []}
    times, rows = [], []
    with tempfile.TemporaryDirectory() as td:
        for c in cases:
            path = os.path.join(HERE, "creatives", c["file"])
            t0 = time.time()
            fields, verdict, read = O.ocr_one(path, "tesseract", psms, "eng",
                                              65.0, td, 25.0, not a.no_sweep)
            times.append(time.time() - t0)
            if c.get("verdict") == "no_text":
                # A photograph with no copy: the only right answer is to say so.
                ok = 1.0 if verdict in ("no_text", "gibberish") else 0.0
                for k in scores:
                    scores[k].append(ok)
                rows.append((c["file"], times[-1], verdict, ok, fields, None))
                continue
            s = {
                "headline": f1(fields["headline"], c["headline"]),
                "description": f1(fields["description"], c["description"]),
                # The CTA is a short exact string or it is wrong.
                "cta": 1.0 if toks(fields["cta"]) == toks(c["cta"]) else 0.0,
                # Every expected extra (display URL, price, fine print) has to
                # show up in other_text.
                "other": (statistics.mean(
                    [1.0 if all(t in toks(fields["other_text"]) for t in toks(o))
                     else 0.0 for o in c["other"]]) if c["other"] else 1.0),
            }
            for k, v in s.items():
                scores[k].append(v)
            rows.append((c["file"], times[-1], verdict,
                         statistics.mean(s.values()), fields, s))

    print(f"{'case':<28}{'sec':>6}{'verdict':>11}{'score':>7}")
    for name, dt, verdict, score, fields, per in rows:
        print(f"{name:<28}{dt:>6.2f}{verdict:>11}{score:>7.2f}")
        if a.verbose or score < 0.999:
            for k in ("headline", "description", "cta", "other_text"):
                print(f"    {k:<12}: {fields[k]!r}")
            if per:
                print(f"    per-field   : { {k: round(v, 2) for k, v in per.items()} }")
    print("\n--- field accuracy ---")
    for k, v in scores.items():
        print(f"  {k:<12} {statistics.mean(v) * 100:5.1f}%   (perfect on "
              f"{sum(1 for x in v if x > 0.999)}/{len(v)})")
    print(f"  {'OVERALL':<12} "
          f"{statistics.mean([statistics.mean(v) for v in scores.values()]) * 100:5.1f}%")
    print("\n--- speed (one image at a time; the CLI runs jobs in parallel) ---")
    print(f"  mean {statistics.mean(times) * 1000:.0f} ms · median "
          f"{statistics.median(times) * 1000:.0f} ms · max {max(times) * 1000:.0f} ms")


if __name__ == "__main__":
    main()
