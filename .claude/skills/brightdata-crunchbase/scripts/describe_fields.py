#!/usr/bin/env python3
"""Print the field schema for Bright Data's Crunchbase dataset.

Calls GET /datasets/{dataset_id}/metadata to fetch the authoritative
list of ~100-124 fields the scraper can return. Use this instead of
hardcoding field names — they change over time.

This endpoint is free (metadata-only, no scraping cost).
"""
from __future__ import annotations

import argparse
import sys

from client import CRUNCHBASE_DATASET_ID, emit, metadata


def main() -> None:
    ap = argparse.ArgumentParser(
        description="Describe the Crunchbase dataset field schema.",
    )
    ap.add_argument(
        "--active-only",
        action="store_true",
        help="Only show fields marked active=true.",
    )
    ap.add_argument(
        "--names-only",
        action="store_true",
        help="Just print the field names as a JSON array.",
    )
    args = ap.parse_args()

    try:
        meta = metadata(CRUNCHBASE_DATASET_ID)
    except RuntimeError as e:
        sys.stderr.write(f"error: {e}\n")
        sys.exit(1)

    fields = meta.get("fields") or {}
    if args.active_only:
        fields = {
            name: spec
            for name, spec in fields.items()
            if isinstance(spec, dict) and spec.get("active")
        }

    if args.names_only:
        emit(sorted(fields.keys()))
        return

    emit({
        "dataset_id": meta.get("id") or CRUNCHBASE_DATASET_ID,
        "field_count": len(fields),
        "fields": fields,
    })


if __name__ == "__main__":
    main()
