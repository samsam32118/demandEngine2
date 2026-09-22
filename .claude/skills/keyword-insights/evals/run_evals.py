#!/usr/bin/env python3
"""Measure the skill, so that changing it can be an improvement rather than
a preference.

DataForSEO responses are replayed from the cache, so the data cost of a full
eval is **$0.00**. Only genuinely new Jev questions bill — which is exactly
what changes when a rubric changes, and is what makes it affordable to
re-measure after every edit rather than at the end.

    run_evals.py                 # both arms, every case
    run_evals.py --arm jev       # one arm
    run_evals.py --case trap     # one case

Cases live in `cases/`. Each one names a market and what a good run of it
looks like — including one market that does not exist, because a method that
cannot return "there is nothing here" will return something for anything.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import re
import subprocess
import sys
import tempfile
from collections import Counter

HERE = os.path.dirname(os.path.abspath(__file__))
SKILL = os.path.dirname(HERE)
LOOP = os.path.join(SKILL, "scripts", "loop.py")
CASES = os.path.join(HERE, "cases")
RESULTS = os.path.join(HERE, "results")


def load_cases(only: str | None) -> list[dict]:
    out = []
    for name in sorted(os.listdir(CASES)):
        if not name.endswith(".json"):
            continue
        with open(os.path.join(CASES, name), encoding="utf-8") as fh:
            case = json.load(fh)
        if only and case["id"] != only:
            continue
        out.append(case)
    return out


def run_one(case: dict, arm: str, live: bool) -> dict:
    with tempfile.TemporaryDirectory() as tmp:
        js = os.path.join(tmp, "run.json")
        cmd = [sys.executable, LOOP, "run", case["seed"],
               "--iterations", str(case.get("iterations", 3)),
               "--for", case.get("asker", "someone sizing up this market"),
               "--location", case.get("location", "United States"),
               "--arm", arm, "--quiet",
               *(["--no-harvest"] if case.get("no_harvest") else []),
               "--out", os.path.join(tmp, "r.md"), "--json", js]
        if not live:
            cmd.append("--offline")
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=1200)
        if not os.path.exists(js):
            return {"error": (proc.stderr or proc.stdout)[-400:] or "no output"}
        with open(js, encoding="utf-8") as fh:
            data = json.load(fh)
        with open(os.path.join(tmp, "r.md"), encoding="utf-8") as fh:
            report = fh.read()
        files = _data_files(os.path.join(tmp, "r-data"))
    return score(case, data, report, files)


DATA_FILES = ("keywords.csv", "series.csv", "topics.csv", "offerings.csv",
              "tested.csv", "trail.csv", "network.json", "forecast.json",
              "run.json")


def _data_files(folder: str) -> dict:
    """What the run attached: each file, and its row count if a table."""
    out = {}
    for name in DATA_FILES:
        path = os.path.join(folder, name)
        if not os.path.exists(path):
            continue
        if name.endswith(".csv"):
            with open(path, encoding="utf-8", newline="") as fh:
                out[name] = max(sum(1 for _ in csv.reader(fh)) - 1, 0)
        else:
            with open(path, encoding="utf-8") as fh:
                out[name] = json.load(fh)
    return out


def score(case: dict, data: dict, report: str, files: dict | None = None
          ) -> dict:
    man, claims = data["manifest"], data["claims"]
    kept = [c for c in claims if c["verdict"] == "kept"]
    kinds = Counter(c["kind"] for c in kept)
    expect = case.get("expect", {})

    # Which gate is responsible for each rejection. A gate that never appears
    # here is decoration.
    gates = Counter(c["verdict"] for c in claims if c["verdict"] != "kept")
    total_rejected = max(sum(gates.values()), 1)

    def spread(field: str) -> dict:
        vals = [c[field] for c in claims] or [0.0]
        return {"min": round(min(vals), 2), "max": round(max(vals), 2),
                "crosses_half": round(
                    sum(1 for v in vals if v > 0.5) / len(vals), 2)}

    checks: dict[str, bool] = {}
    if "max_findings" in expect:
        checks["stays_quiet_when_there_is_nothing"] = \
            len(kept) <= expect["max_findings"]
    if "min_findings" in expect:
        checks["finds_something_when_there_is_something"] = \
            len(kept) >= expect["min_findings"]
    if "max_repeats_of_one_kind" in expect:
        checks["no_finding_repeated_as_several"] = \
            (max(kinds.values()) if kinds else 0) \
            <= expect["max_repeats_of_one_kind"]
    # Every case, whatever it expects: the report is the insights ranked by
    # value, and everything underneath is attached. These replace checks
    # that looked for the network section by its wording — the network is
    # a file now, so the check looks in the file.
    heads = re.findall(r"^## \d+\. (.+)$", report, flags=re.M)
    by_value = [c.get("headline") for c in sorted(
        kept, key=lambda c: (-c.get("weight", 0.0), c.get("key", "")))]
    checks["ranked_by_value"] = heads == by_value
    files = files or {}
    checks["attaches_the_data"] = (
        set(files) == set(DATA_FILES)
        and files.get("keywords.csv") == man["keywords_measured"]
        and files.get("tested.csv") == len(claims))
    net = files.get("network.json") or {}
    checks["network_says_its_calibration_is_unverified"] = \
        "unverified" in net.get("what_this_is", "")
    if not kept:
        checks["says_so_when_nothing_survives"] = "## No insights" in report

    for phrase in expect.get("must_mention", []):
        checks[f"mentions:{phrase}"] = phrase.lower() in report.lower()
    for phrase in expect.get("must_not_mention", []):
        checks[f"avoids:{phrase}"] = phrase.lower() not in report.lower()

    return {
        "kept": len(kept),
        "generated": len(claims),
        "kept_share": round(len(kept) / max(len(claims), 1), 2),
        "distinct_kinds": len(kinds),
        "most_repeated_kind": (max(kinds.values()) if kinds else 0),
        "gate_work": {g: round(v / total_rejected, 2)
                      for g, v in gates.most_common()},
        "discrimination": {f: spread(f) for f in
                           ("reads_true", "swappable", "obvious",
                            "surprising")},
        "coverage": round(man["volume_certain"]
                           / max(man["volume_measured"], 1), 2),
        "probes_billable": man["dataforseo"]["billable_calls"],
        "probes_total": len(man["trail"]),
        "dead_ends": sum(1 for t in man["trail"]
                         if t["status"] == "dead_end"),
        "usd_data": man["dataforseo"]["spent_usd"],
        "usd_jev": man["jev"]["usd"],
        "seconds": man["seconds"],
        "checks": checks,
        "passed": sum(1 for v in checks.values() if v),
        "of": len(checks),
    }


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--arm", choices=("jev", "code", "both"), default="both")
    p.add_argument("--case")
    p.add_argument("--live", action="store_true",
                   help="allow billable DataForSEO calls (default: replay "
                        "the frozen responses, which cost nothing)")
    p.add_argument("--save", action="store_true")
    args = p.parse_args()

    arms = ("jev", "code") if args.arm == "both" else (args.arm,)
    cases = load_cases(args.case)
    if not cases:
        sys.stderr.write("no cases found\n")
        return 1

    results: dict[str, dict] = {}
    print(f"{'case':<26s} {'arm':<5s} {'kept':>9s} {'kinds':>6s} "
          f"{'rpt':>4s} {'probes':>7s} {'dead':>5s} {'checks':>7s} "
          f"{'$data':>7s} {'$jev':>7s}")
    print("-" * 96)
    for case in cases:
        for arm in arms:
            key = f"{case['id']}/{arm}"
            r = run_one(case, arm, args.live)
            results[key] = r
            if "error" in r:
                print(f"{case['id']:<26s} {arm:<5s}   ERROR: {r['error'][:50]}")
                continue
            print(f"{case['id']:<26s} {arm:<5s} "
                  f"{r['kept']:>3d}/{r['generated']:<5d} "
                  f"{r['distinct_kinds']:>6d} {r['most_repeated_kind']:>4d} "
                  f"{r['probes_total']:>7d} {r['dead_ends']:>5d} "
                  f"{r['passed']:>3d}/{r['of']:<3d} "
                  f"{r['usd_data']:>7.3f} {r['usd_jev']:>7.4f}")

    print()
    for arm in arms:
        rows = [r for k, r in results.items()
                if k.endswith("/" + arm) and "error" not in r]
        if not rows:
            continue
        passed = sum(r["passed"] for r in rows)
        of = sum(r["of"] for r in rows)
        print(f"{arm:<5s}  checks {passed}/{of}"
              f"  ·  mean kept_share "
              f"{sum(r['kept_share'] for r in rows) / len(rows):.2f}"
              f"  ·  most-repeated kind "
              f"{max(r['most_repeated_kind'] for r in rows)}"
              f"  ·  ${sum(r['usd_data'] + r['usd_jev'] for r in rows):.4f}")

    failures = [(k, name) for k, r in results.items() if "error" not in r
                for name, ok in r["checks"].items() if not ok]
    if failures:
        print("\nfailed checks:")
        for key, name in failures:
            print(f"  {key}: {name}")

    if args.save:
        os.makedirs(RESULTS, exist_ok=True)
        import datetime
        path = os.path.join(
            RESULTS,
            datetime.datetime.now().strftime("%Y%m%d-%H%M%S") + ".json")
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(results, fh, indent=2)
        print(f"\nsaved {path}")
    return 0


if __name__ == "__main__":
    try:
        import signal
        signal.signal(signal.SIGPIPE, signal.SIG_DFL)
    except (ImportError, AttributeError, ValueError):
        pass
    raise SystemExit(main())
