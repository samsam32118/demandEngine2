#!/usr/bin/env python3
"""Cheap smoke test for the brightdata-crunchbase skill.

Verifies auth + network by calling the free metadata endpoint and
asserting that the `name` and `url` fields exist. Does NOT run a real
trigger (which would cost money). If BRIGHTDATA_API_TOKEN is unset,
prints a SKIP line and exits 0 so unauthenticated CI doesn't fail.
"""
from __future__ import annotations

import os
import sys

from client import CRUNCHBASE_DATASET_ID, metadata


def main() -> int:
    if not os.environ.get("BRIGHTDATA_API_TOKEN"):
        print("SKIP: BRIGHTDATA_API_TOKEN not set")
        return 0

    meta = metadata(CRUNCHBASE_DATASET_ID)
    fields = meta.get("fields") or {}
    assert fields, f"expected non-empty fields, got {meta!r}"
    assert "name" in fields, f"expected 'name' field, got keys: {sorted(fields)[:20]}"
    assert "url" in fields, f"expected 'url' field, got keys: {sorted(fields)[:20]}"
    print(f"OK: {len(fields)} fields returned; 'name' and 'url' present.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
