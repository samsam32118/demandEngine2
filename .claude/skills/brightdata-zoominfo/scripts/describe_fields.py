#!/usr/bin/env python3
"""Describe the schema of the ZoomInfo dataset.

Calls Bright Data's free metadata endpoint and prints the field list. No
scraping, no billing — safe to run anytime to confirm what columns are
available for `--fields`.
"""
from __future__ import annotations

import argparse
import sys

from client import ZOOMINFO_DATASET_ID, emit, metadata


def main() -> None:
    ap = argparse.ArgumentParser(
        description="Describe the ZoomInfo dataset schema (free metadata call).",
    )
    ap.add_argument(
        "--names-only",
        action="store_true",
        help="Print only field names, one per line.",
    )
    ap.add_argument(
        "--active-only",
        action="store_true",
        help="Only show fields where active=true (the default-on columns).",
    )
    args = ap.parse_args()

    try:
        meta = metadata(ZOOMINFO_DATASET_ID)
    except RuntimeError as e:
        sys.stderr.write(f"error: {e}\n")
        sys.exit(1)

    fields = meta.get("fields") or {}
    if args.active_only:
        fields = {n: f for n, f in fields.items() if f.get("active")}

    if args.names_only:
        for name in sorted(fields):
            print(name)
        return

    summary = {
        "dataset_id": meta.get("id", ZOOMINFO_DATASET_ID),
        "field_count": len(fields),
        "fields": {
            name: {
                "type": f.get("type"),
                "active": f.get("active", False),
                "required": f.get("required", False),
                "description": f.get("description"),
            }
            for name, f in sorted(fields.items())
        },
    }
    emit(summary)


if __name__ == "__main__":
    main()
