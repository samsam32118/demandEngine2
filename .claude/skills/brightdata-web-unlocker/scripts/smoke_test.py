#!/usr/bin/env python3
"""Smoke test for brightdata-web-unlocker.

One cheap call against Bright Data's own test endpoint (matches the
operator's working curl examples) — confirms the token and the default zone
(web_unlocker1) are wired correctly. Pass --premium to test the
web_unlocker_premium zone instead. Makes one billable Bright Data call per
run. Run manually after changing BRIGHTDATA_API_TOKEN or either zone env
var. Not run in CI.

Usage (from repo root):

    python .claude/skills/brightdata-web-unlocker/scripts/smoke_test.py
    python .claude/skills/brightdata-web-unlocker/scripts/smoke_test.py --premium
"""
from __future__ import annotations

import argparse
import sys

import unlock
from premium_domains import DEFAULT_ZONE, PREMIUM_ZONE

TEST_URL = "https://geo.brdtest.com/welcome.txt?product=unlocker&method=api"


def main(argv: list[str]) -> int:
    p = argparse.ArgumentParser()
    p.add_argument(
        "--premium",
        action="store_true",
        help="test web_unlocker_premium instead of web_unlocker1",
    )
    args = p.parse_args(argv)

    zone = PREMIUM_ZONE if args.premium else DEFAULT_ZONE
    # use_cache=False so this actually exercises the wire instead of a stale hit.
    payload = unlock.run(
        TEST_URL, zone=zone, fmt="raw", method="GET", country=None, use_cache=False
    )

    body = payload.get("body") or ""
    if not body.strip():
        sys.stderr.write(f"FAIL: empty body back from zone {zone!r}.\n")
        return 1

    print(f"OK: {zone} returned {len(body)} chars, status_code={payload.get('status_code')}")
    print("--- body ---")
    print(body)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
