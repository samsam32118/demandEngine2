#!/usr/bin/env python3
"""Smoke test for brightdata-serp.

One cheap Google query for "pizza" (matches the operator's working curl
example) — confirms the zone is wired, the token is valid, and Bright Data's
markdown transform returns something useful. Makes one paid Bright Data
call. Run manually after changing BRIGHTDATA_API_TOKEN or BRIGHTDATA_SERP_ZONE.
Not run in CI.

Usage (from repo root):

    python .claude/skills/brightdata-serp/scripts/smoke_test.py
"""
from __future__ import annotations

import sys

import search


def main() -> int:
    # use_cache=False so we actually exercise the wire instead of hitting
    # yesterday's cache hit and falsely passing.
    payload = search.run(
        "pizza",
        engine="google",
        hl="en",
        gl="us",
        num=5,
        country="us",
        fmt="markdown",
        zone=None,
        use_cache=False,
    )

    if payload.get("format") != "markdown":
        sys.stderr.write(
            f"FAIL: expected format=markdown; got {payload.get('format')!r}.\n"
        )
        return 1

    if payload.get("status_code") not in (200, None):
        sys.stderr.write(
            f"FAIL: upstream returned HTTP {payload.get('status_code')}; "
            f"expected 200.\n"
        )
        return 1

    md = payload.get("markdown") or ""
    if len(md) < 500:
        sys.stderr.write(
            f"FAIL: markdown body suspiciously short ({len(md)} chars); "
            f"expected a full SERP page. Check the zone.\n"
        )
        return 1

    print(f"OK: got {len(md)} chars of markdown for 'pizza'")
    print(f"  status_code: {payload.get('status_code')}")
    # Find the first line that looks like content (skip nav/skip-links).
    lines = [ln.strip() for ln in md.splitlines() if ln.strip()]
    for line in lines[:30]:
        if len(line) > 20 and not line.startswith("["):
            print(f"  first real line: {line[:120]!r}")
            break
    return 0


if __name__ == "__main__":
    sys.exit(main())
