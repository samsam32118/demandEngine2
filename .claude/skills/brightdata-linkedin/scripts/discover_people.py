#!/usr/bin/env python3
"""Discover LinkedIn people profiles by name.

Triggers Bright Data's LinkedIn People Profile Web Scraper API in
discover-new mode with `discover_by=name` and one or more {first_name,
last_name} pairs. Waits for the snapshot (by default) and emits the
resulting profile rows.

This bills per returned record. Ambiguous names can match multiple
profiles — start with one or two names and confirm the right hit
before pivoting to lookup_people.py on the resolved URL.
"""
from __future__ import annotations

import argparse
import sys

from client import (
    LINKEDIN_PEOPLE_DATASET_ID,
    emit,
    parse_fields,
    trigger,
    wait_for_snapshot,
)


def _split_name(raw: str) -> dict[str, str]:
    """Turn 'First Last' (or 'First Middle Last') into {first_name, last_name}."""
    parts = raw.strip().split()
    if len(parts) < 2:
        raise SystemExit(
            f"error: --name {raw!r} must contain at least a first and last name"
        )
    return {"first_name": parts[0], "last_name": " ".join(parts[1:])}


def main() -> None:
    ap = argparse.ArgumentParser(
        description="Discover LinkedIn people profiles by name.",
    )
    ap.add_argument(
        "--name",
        action="append",
        required=True,
        help="Full name, e.g. 'Bill Gates'. Pass --name multiple times for "
        "multiple people.",
    )
    ap.add_argument(
        "--fields",
        help="Comma-separated subset of output fields. Defaults to the full record.",
    )
    ap.add_argument(
        "--no-wait",
        action="store_true",
        help="Return the snapshot_id immediately without polling.",
    )
    ap.add_argument(
        "--timeout",
        type=float,
        default=900.0,
        help="Seconds to wait for the snapshot before giving up (default: 900).",
    )
    ap.add_argument(
        "--poll-interval",
        type=float,
        default=10.0,
        help="Seconds between /progress polls (default: 10).",
    )
    args = ap.parse_args()

    inputs = [_split_name(n) for n in args.name]

    try:
        snapshot_id = trigger(
            LINKEDIN_PEOPLE_DATASET_ID,
            inputs,
            discover_by="name",
            custom_output_fields=parse_fields(args.fields),
            include_errors=True,
        )
    except RuntimeError as e:
        sys.stderr.write(f"error: {e}\n")
        sys.exit(1)

    if args.no_wait:
        emit({
            "snapshot_id": snapshot_id,
            "status": "triggered",
            "names": args.name,
        })
        return

    try:
        rows = wait_for_snapshot(
            snapshot_id,
            poll_interval=args.poll_interval,
            timeout=args.timeout,
        )
    except RuntimeError as e:
        sys.stderr.write(f"error: {e}\n")
        emit({"snapshot_id": snapshot_id, "status": "pending_or_failed"})
        sys.exit(1)

    emit({
        "snapshot_id": snapshot_id,
        "status": "ready",
        "names": args.name,
        "returned": len(rows),
        "rows": rows,
    })


if __name__ == "__main__":
    main()
