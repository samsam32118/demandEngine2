#!/usr/bin/env python3
"""Look up Crunchbase company profiles by organization URL.

Triggers Bright Data's Crunchbase Web Scraper API with one or more
Crunchbase organization URLs and (by default) waits for the snapshot
to complete, then emits the rows.

Each input URL bills as one record on the pay-as-you-go plan, so this
is the cheap path. Prefer it over discover mode when the user already
knows the company.
"""
from __future__ import annotations

import argparse
import sys

from client import (
    CRUNCHBASE_DATASET_ID,
    emit,
    trigger,
    wait_for_snapshot,
)


def _parse_fields(raw: str | None) -> list[str] | None:
    if not raw:
        return None
    return [f.strip() for f in raw.split(",") if f.strip()]


def main() -> None:
    ap = argparse.ArgumentParser(
        description="Look up Crunchbase company profiles by URL."
    )
    ap.add_argument(
        "--url",
        action="append",
        required=True,
        help="Crunchbase org URL, e.g. https://www.crunchbase.com/organization/apple. "
        "Pass --url multiple times for multiple companies.",
    )
    ap.add_argument(
        "--fields",
        help="Comma-separated subset of output fields (e.g. "
        "'name,url,founded_date,num_employees'). Defaults to the full record.",
    )
    ap.add_argument(
        "--no-wait",
        action="store_true",
        help="Return the snapshot_id immediately without polling. Use "
        "get_snapshot.py later to fetch results.",
    )
    ap.add_argument(
        "--timeout",
        type=float,
        default=600.0,
        help="Seconds to wait for the snapshot before giving up (default: 600).",
    )
    ap.add_argument(
        "--poll-interval",
        type=float,
        default=10.0,
        help="Seconds between /progress polls (default: 10).",
    )
    args = ap.parse_args()

    inputs = [{"url": u} for u in args.url]
    try:
        snapshot_id = trigger(
            CRUNCHBASE_DATASET_ID,
            inputs,
            custom_output_fields=_parse_fields(args.fields),
            include_errors=True,
        )
    except RuntimeError as e:
        sys.stderr.write(f"error: {e}\n")
        sys.exit(1)

    if args.no_wait:
        emit({"snapshot_id": snapshot_id, "status": "triggered", "inputs": len(inputs)})
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

    emit({"snapshot_id": snapshot_id, "status": "ready", "rows": rows})


if __name__ == "__main__":
    main()
