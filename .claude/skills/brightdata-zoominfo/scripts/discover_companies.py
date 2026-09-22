#!/usr/bin/env python3
"""Discover ZoomInfo companies by ZoomInfo search-result URL.

Triggers Bright Data's ZoomInfo Web Scraper API in discover-new mode
with one or more search URLs and (by default) waits for the snapshot.

The ZoomInfo discovery collector only accepts `search_url` — there is
no free-text keyword discovery. Build a URL of the form
`https://www.zoominfo.com/companies-search/<filters>` (e.g.
`location-usa-industry-software-employees-50-200`) and pass it via
--search-url.

This path bills per returned record, so --limit-per-input is REQUIRED.
A broad search URL can return hundreds of rows at ~$0.001-$0.0015 each.
"""
from __future__ import annotations

import argparse
import sys

from client import (
    ZOOMINFO_DATASET_ID,
    emit,
    parse_fields,
    trigger,
    wait_for_snapshot,
)


def main() -> None:
    ap = argparse.ArgumentParser(
        description="Discover ZoomInfo companies by search-result URL.",
    )
    ap.add_argument(
        "--search-url",
        action="append",
        required=True,
        help=(
            "ZoomInfo search-results URL, e.g. "
            "https://www.zoominfo.com/companies-search/location-usa-"
            "industry-software. Pass --search-url multiple times for "
            "multiple searches."
        ),
    )
    ap.add_argument(
        "--limit-per-input",
        type=int,
        required=True,
        help=(
            "Max records returned per search URL. REQUIRED — this is the "
            "main cost guard. Start small (e.g. 25) and expand if needed."
        ),
    )
    ap.add_argument(
        "--fields",
        help=(
            "Comma-separated subset of output fields. Defaults to the "
            "full record. Run describe_fields.py --names-only for the list."
        ),
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

    inputs = [{"url": u} for u in args.search_url]
    expected_max = len(inputs) * args.limit_per_input

    try:
        snapshot_id = trigger(
            ZOOMINFO_DATASET_ID,
            inputs,
            discover_by="search_url",
            limit_per_input=args.limit_per_input,
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
            "search_urls": args.search_url,
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
        "search_urls": args.search_url,
        "limit_per_input": args.limit_per_input,
        "expected_max_records": expected_max,
        "returned": len(rows),
        "rows": rows,
    })


if __name__ == "__main__":
    main()
