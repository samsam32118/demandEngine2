#!/usr/bin/env python3
"""Print the field schema for a Bright Data TikTok dataset.

Calls GET /datasets/{dataset_id}/metadata to fetch the authoritative
list of fields the scraper can return. Each of the four TikTok datasets
has its own schema — pick one with --kind.

Pass --inputs to print the request-side schema instead: which input keys
each collector requires and accepts. That half comes from the verified
registry in client.py, not from the API.

This endpoint is free (metadata-only, no scraping cost).
"""
from __future__ import annotations

import argparse
import sys

from client import DATASETS, DISCOVER_MODES, INPUT_KEYS, emit, metadata, resolve_dataset


def main() -> None:
    ap = argparse.ArgumentParser(
        description="Describe a TikTok dataset field schema.",
    )
    ap.add_argument(
        "--kind",
        choices=sorted(DATASETS),
        required=True,
        help="Which TikTok dataset to describe: profiles|posts|comments|shop.",
    )
    ap.add_argument(
        "--inputs",
        action="store_true",
        help="Show the INPUT schema (required/optional keys per collector) "
        "instead of the output field list.",
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

    if args.inputs:
        modes: list[str | None] = [None] + list(DISCOVER_MODES[args.kind])
        emit({
            "kind": args.kind,
            "dataset_id": dataset_id,
            "discover_modes": DISCOVER_MODES[args.kind],
            "collectors": {
                (m or "url_collection"): INPUT_KEYS[(args.kind, m)] for m in modes
            },
        })
        return

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
