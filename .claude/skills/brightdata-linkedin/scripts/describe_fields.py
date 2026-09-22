#!/usr/bin/env python3
"""Print the field schema for a Bright Data LinkedIn dataset.

Calls GET /datasets/{dataset_id}/metadata to fetch the authoritative
list of fields the scraper can return. Each of the four LinkedIn
datasets has its own schema — pick one with --kind.

This endpoint is free (metadata-only, no scraping cost).
"""
from __future__ import annotations

import argparse
import sys

from client import DATASETS, emit, metadata, resolve_dataset


def main() -> None:
    ap = argparse.ArgumentParser(
        description="Describe a LinkedIn dataset field schema.",
    )
    ap.add_argument(
        "--kind",
        choices=sorted(DATASETS),
        required=True,
        help="Which LinkedIn dataset to describe: people|company|jobs|posts.",
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

    dataset_id = resolve_dataset(args.kind)
    try:
        meta = metadata(dataset_id)
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
        "kind": args.kind,
        "dataset_id": meta.get("id") or dataset_id,
        "field_count": len(fields),
        "fields": fields,
    })


if __name__ == "__main__":
    main()
