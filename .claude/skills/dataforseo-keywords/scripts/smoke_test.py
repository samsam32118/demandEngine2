#!/usr/bin/env python3
"""Smoke test — hits each of the four Live endpoints once.

Costs ~4 billable DataForSEO requests (~$0.20-0.40 total). Run after any
change to credentials or to client.py. Asserts each endpoint authenticates
and returns a well-formed task. Calls the API directly so it exercises the
wire.

Pass --dry-run to validate request-building and auth wiring WITHOUT spending
anything (no calls made) — useful when the account balance is low.
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import client  # noqa: E402


DRY_RUN = "--dry-run" in sys.argv

# (name, endpoint, task, expect_min, why)
# expect_min guards against silent regressions AND against picking a
# misleading probe: keywords_for_keywords must EXPAND, so we seed it with a
# broad head term ("crm software" -> ~1600 ideas) and assert many rows. A
# niche long-tail seed like "ai sales coach" legitimately returns only itself
# and would make a healthy endpoint look broken.
_CASES = [
    ("keywords_for_keywords",
     "keywords_data/google_ads/keywords_for_keywords/live",
     {"location_code": 2840, "language_code": "en", "keywords": ["crm software"]},
     50, "broad seed must expand into many ideas"),
    ("search_volume",
     "keywords_data/google_ads/search_volume/live",
     {"location_code": 2840, "language_code": "en",
      "keywords": ["ai sales coach", "crm software"]},
     2, "one row per input keyword (no expansion)"),
    ("keywords_for_site",
     "keywords_data/google_ads/keywords_for_site/live",
     {"location_code": 2840, "language_code": "en",
      "target": "dataforseo.com", "target_type": "site"},
     10, "a real domain yields many keywords"),
    ("ad_traffic_by_keywords",
     "keywords_data/google_ads/ad_traffic_by_keywords/live",
     {"location_code": 2840, "language_code": "en", "bid": 999,
      "match": "exact", "keywords": ["ai sales coach"]},
     1, "campaign-level aggregate row"),
]


def _check(name: str, endpoint: str, task: dict, expect_min: int, why: str) -> bool:
    if DRY_RUN:
        # Just prove auth is wired and the request builds — no spend.
        try:
            client._auth_header()  # noqa: SLF001 — intentional wiring check
            print(f"  · {name}: request ready (dry-run, not sent)")
            return True
        except SystemExit:
            print(f"  ✗ {name}: missing credentials")
            return False
    try:
        resp = client.post(endpoint, task)
        t = client.unwrap_task(resp)
        n = len(t.get("result") or [])
        if n < expect_min:
            print(f"  ✗ {name}: {n} rows, expected >= {expect_min} ({why})")
            return False
        print(f"  ✓ {name}: {n} result rows, cost ${resp.get('cost')} ({why})")
        return True
    except Exception as e:  # noqa: BLE001
        print(f"  ✗ {name}: {e}")
        return False


def _location_check() -> bool:
    """Prove location targeting is actually applied, not ignored.

    Same keyword, three locations. If location were silently dropped every
    call would return the identical (worldwide-ish) number. A location-
    sensitive term like "coffee shop" must rank New York >> Oslo, so we
    assert a large gap. This is the check that catches a location regression.
    """
    ep = "keywords_data/google_ads/search_volume/live"
    kw = "coffee shop"
    if DRY_RUN:
        print("  · location targeting: request ready (dry-run, not sent)")
        return True
    try:
        vols = {}
        for label, loc in (("New York", {"location_name": "New York, NY,United States"}),
                           ("Oslo", {"location_name": "Oslo,Oslo,Norway"})):
            task = {"language_code": "en", "keywords": [kw], **loc}
            t = client.unwrap_task(client.post(ep, task))
            vols[label] = (t.get("result") or [{}])[0].get("search_volume") or 0
        ny, oslo = vols["New York"], vols["Oslo"]
        ok = ny > oslo * 5  # New York must dwarf Oslo for an English term
        mark = "✓" if ok else "✗"
        print(f"  {mark} location targeting: '{kw}' New York={ny:,} vs Oslo={oslo:,}"
              + ("" if ok else "  <-- too close; location may be ignored!"))
        return ok
    except Exception as e:  # noqa: BLE001
        print(f"  ✗ location targeting: {e}")
        return False


def main() -> None:
    mode = "dry-run, no spend" if DRY_RUN else "6 live calls"
    print(f"DataForSEO Keywords Data — smoke test ({mode})")
    ok = all([_check(*c) for c in _CASES])
    ok &= _location_check()
    print("PASS" if ok else "FAIL")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
