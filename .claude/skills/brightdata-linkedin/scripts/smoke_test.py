#!/usr/bin/env python3
"""Cheap smoke test for the brightdata-linkedin skill.

Verifies auth + network by calling the free metadata endpoint for each
of the four LinkedIn datasets (people, company, jobs, posts) and
asserting each returns a non-empty field set. Does NOT run a real
trigger (which would cost money).

If BRIGHTDATA_API_TOKEN is unset, prints a SKIP line and exits 0 so
unauthenticated CI doesn't fail.
"""
from __future__ import annotations

import os
import sys

from client import DATASETS, metadata


def main() -> int:
    if not os.environ.get("BRIGHTDATA_API_TOKEN"):
        print("SKIP: BRIGHTDATA_API_TOKEN not set")
        return 0

    for kind, ds_id in DATASETS.items():
        meta = metadata(ds_id)
        fields = meta.get("fields") or {}
        assert fields, f"{kind}: expected non-empty fields, got {meta!r}"
        print(f"OK: {kind} ({ds_id}) returned {len(fields)} fields.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
