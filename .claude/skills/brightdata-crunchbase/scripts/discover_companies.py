#!/usr/bin/env python3
"""Discover Crunchbase companies by free-text keyword.

Triggers Bright Data's Crunchbase Web Scraper API in discover-new mode
with one or more keywords and (by default) waits for the snapshot.

This path bills per returned record, so --limit-per-input is REQUIRED.
A broad keyword like "AI" can return thousands of rows at ~$0.001-
$0.0015 each, which is how users accidentally burn through their
Bright Data credit.
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
        description="Discover Crunchbase companies by keyword.",
    )
    ap.add_argument(
        "--keyword",
        action="append",
        required=True,
        help="Free-text keyword to search. Pass --keyword multiple times "
        "for multiple searches.",
    )
    ap.add_argument(
        "--limit-per-input",
        type=int,
        required=True,
        help="Max records returned per keyword. REQUIRED — this is the "
        "main cost guard. Start small (e.g. 25) and expand if needed.",
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

    if args.limit_per_input <= 0:
        ap.error("--limit-per-input must be >= 1")

    inputs = [{"keyword": k} for k in args.keyword]
    expected_max = len(inputs) * args.limit_per_input

    try:
        snapshot_id = trigger(
            CRUNCHBASE_DATASET_ID,
            inputs,
            discover_by="keyword",
            limit_per_input=args.limit_per_input,
            custom_output_fields=_parse_fields(args.fields),
            include_errors=True,
        )
    except RuntimeError as e:
        sys.stderr.write(f"error: {e}\n")
        sys.exit(1)

    if args.no_wait:
        emit({
            "snapshot_id": snapshot_id,
            "status": "triggered",
            "keywords": args.keyword,
            "limit_per_input": args.limit_per_input,
            "expected_max_records": expected_max,
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
        "keywords": args.keyword,
        "limit_per_input": args.limit_per_input,
        "expected_max_records": expected_max,
        "returned": len(rows),
        "rows": rows,
    })


if __name__ == "__main__":
    main()
