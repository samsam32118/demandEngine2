#!/usr/bin/env python3
"""Look up LinkedIn people profiles by profile URL.

Triggers Bright Data's LinkedIn People Profile Web Scraper API with one
or more LinkedIn profile URLs and (by default) waits for the snapshot to
complete, then emits the rows.

Each input URL bills as one record on the pay-as-you-go plan, so this
is the cheap path. Prefer it over discover_people.py when the user
already knows the handle.
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


def main() -> None:
    ap = argparse.ArgumentParser(
        description="Look up LinkedIn people profiles by profile URL."
    )
    ap.add_argument(
        "--url",
        action="append",
        required=True,
        help="LinkedIn profile URL, e.g. https://www.linkedin.com/in/johndoe. "
        "Pass --url multiple times for multiple profiles.",
    )
    ap.add_argument(
        "--fields",
        help="Comma-separated subset of output fields (e.g. "
        "'name,headline,experience,education'). Defaults to the full record.",
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
            LINKEDIN_PEOPLE_DATASET_ID,
            inputs,
            custom_output_fields=parse_fields(args.fields),
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
