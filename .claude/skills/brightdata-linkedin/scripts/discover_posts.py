#!/usr/bin/env python3
"""Discover LinkedIn posts by author profile or company URL.

Triggers Bright Data's LinkedIn Posts Web Scraper API in discover-new
mode. Two modes:

  --profile-url <url>    discover_by=profile_url   (posts from a person)
  --company-url <url>    discover_by=company_url   (posts from a company page)

Pick one mode per run; mixing is not supported by the Bright Data API.

This path bills per returned post, so `--limit-per-input` is strongly
recommended — an active poster can return 50+ posts per URL.
"""
from __future__ import annotations

import argparse
import sys

from client import (
    LINKEDIN_POSTS_DATASET_ID,
    emit,
    parse_fields,
    trigger,
    wait_for_snapshot,
)


def main() -> None:
    ap = argparse.ArgumentParser(
        description="Discover LinkedIn posts by profile URL or company URL.",
    )
    group = ap.add_mutually_exclusive_group(required=True)
    group.add_argument(
        "--profile-url",
        action="append",
        help="LinkedIn person profile URL. Pulls recent posts by that person. "
        "Pass --profile-url multiple times for multiple people.",
    )
    group.add_argument(
        "--company-url",
        action="append",
        help="LinkedIn company URL. Pulls recent posts from that company page. "
        "Pass --company-url multiple times for multiple companies.",
    )
    ap.add_argument(
        "--limit-per-input",
        type=int,
        help="Max posts returned per author. Strongly recommended — active "
        "posters can return 50+ posts each. Omit to let Bright Data use its "
        "default.",
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

    if args.profile_url:
        discover_by = "profile_url"
        inputs = [{"url": u} for u in args.profile_url]
    else:
        discover_by = "company_url"
        inputs = [{"url": u} for u in args.company_url]

    try:
        snapshot_id = trigger(
            LINKEDIN_POSTS_DATASET_ID,
            inputs,
            discover_by=discover_by,
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
            "discover_by": discover_by,
            "inputs": len(inputs),
            "limit_per_input": args.limit_per_input,
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
        "discover_by": discover_by,
        "inputs": len(inputs),
        "limit_per_input": args.limit_per_input,
        "returned": len(rows),
        "rows": rows,
    })


if __name__ == "__main__":
    main()
