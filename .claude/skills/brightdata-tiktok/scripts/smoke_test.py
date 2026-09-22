#!/usr/bin/env python3
"""Cheap smoke test for the brightdata-tiktok skill.

Two free checks, no real trigger (which would cost money):

1. The metadata endpoint returns a non-empty field set for each of the
   four TikTok datasets (profiles, posts, comments, shop).
2. Every discover mode this skill claims is still the set the API
   advertises. Sending a deliberately bogus discover_by makes Bright
   Data reply 400 with "Available types: ..." — free, and it catches the
   day Bright Data adds or renames a collector.

If BRIGHTDATA_API_TOKEN is unset, prints a SKIP line and exits 0 so
unauthenticated CI doesn't fail.
"""
from __future__ import annotations

import os
import re
import sys

from client import DATASETS, DISCOVER_MODES, metadata, trigger


def _advertised_modes(dataset_id: str) -> list[str]:
    """Ask the API which discover modes a dataset supports. Free (400)."""
    try:
        trigger(dataset_id, [{"url": "x"}], discover_by="__probe__")
    except RuntimeError as e:
        msg = str(e)
        if "does not support discovery" in msg:
            return []
        m = re.search(r"Available types:\s*(.+?)(?:\"|$)", msg)
        if m:
            listed = m.group(1)
            # client.py appends a human hint after the API's list; cut it
            # off so it doesn't get parsed as a mode name.
            listed = listed.split("(this discover_by")[0]
            return [t.strip() for t in listed.split(",") if t.strip()]
        raise
    raise AssertionError("bogus discover_by unexpectedly succeeded")


def main() -> int:
    if not os.environ.get("BRIGHTDATA_API_TOKEN"):
        print("SKIP: BRIGHTDATA_API_TOKEN not set")
        return 0

    failures = 0
    for kind, ds_id in DATASETS.items():
        meta = metadata(ds_id)
        fields = meta.get("fields") or {}
        assert fields, f"{kind}: expected non-empty fields, got {meta!r}"
        print(f"OK: {kind} ({ds_id}) returned {len(fields)} fields.")

        want = sorted(DISCOVER_MODES[kind])
        got = sorted(_advertised_modes(ds_id))
        if want == got:
            print(f"OK: {kind} discover modes match: {got or '(url only)'}")
        else:
            failures += 1
            print(f"FAIL: {kind} discover modes drifted — "
                  f"skill claims {want}, API advertises {got}")

    if failures:
        print(f"\n{failures} dataset(s) drifted. Update DISCOVER_MODES in client.py.")
        return 1
    n_modes = sum(len(m) for m in DISCOVER_MODES.values())
    n_collectors = len(DATASETS) + n_modes
    print(f"\nAll {len(DATASETS)} datasets and {n_modes} discover modes "
          f"verified ({n_collectors} collectors total).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
