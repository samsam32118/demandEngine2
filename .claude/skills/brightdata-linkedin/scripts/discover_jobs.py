#!/usr/bin/env python3
"""Discover LinkedIn job postings by keyword + location.

Triggers Bright Data's LinkedIn Jobs Web Scraper API in discover-new
mode with `discover_by=keyword`. Each input is a dict of search
filters (keyword, location, country, time_range, job_type,
experience_level, remote, company).

This path bills per returned record, so --limit-per-input is REQUIRED.
A broad combo (e.g. keyword='software engineer' country='US') can
return thousands of rows at ~$0.001-$0.0015 each.
"""
from __future__ import annotations

import argparse
import sys

from client import (
    LINKEDIN_JOBS_DATASET_ID,
    emit,
    parse_fields,
    trigger,
    wait_for_snapshot,
)


def main() -> None:
    ap = argparse.ArgumentParser(
        description="Discover LinkedIn jobs by keyword + location.",
    )
    ap.add_argument(
        "--keyword",
        required=True,
        help="Job keyword, e.g. 'VP Corporate Development'.",
    )
    ap.add_argument("--location", default="", help="Geographic location, e.g. 'New York'.")
    ap.add_argument("--country", default="", help="Two-letter country code, e.g. 'US'.")
    ap.add_argument(
        "--time-range",
        default="",
        help="LinkedIn time-range label, e.g. 'Past week', 'Past 24 hours', 'Any time'.",
    )
    ap.add_argument(
        "--job-type",
        default="",
        help="Job type, e.g. 'Full-time', 'Part-time', 'Contract', 'Internship'.",
    )
    ap.add_argument(
        "--experience-level",
        default="",
        help=(
            "Experience level, e.g. 'Entry level', 'Associate', "
            "'Mid-Senior level', 'Director', 'Executive'."
        ),
    )
    ap.add_argument(
        "--remote",
        default="",
        help="Remote filter, e.g. 'Remote', 'Hybrid', 'On-site'.",
    )
    ap.add_argument(
        "--company",
        default="",
        help="Company name filter (optional).",
    )
    ap.add_argument(
        "--limit-per-input",
        type=int,
        required=True,
        help="Max records returned per search. REQUIRED — main cost guard. "
        "Start small (25) and expand if needed.",
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

    search = {
        "location": args.location,
        "keyword": args.keyword,
        "country": args.country,
        "time_range": args.time_range,
        "job_type": args.job_type,
        "experience_level": args.experience_level,
        "remote": args.remote,
        "company": args.company,
    }
    inputs = [search]

    try:
        snapshot_id = trigger(
            LINKEDIN_JOBS_DATASET_ID,
            inputs,
            discover_by="keyword",
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
            "search": search,
            "limit_per_input": args.limit_per_input,
            "expected_max_records": args.limit_per_input,
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
        "search": search,
        "limit_per_input": args.limit_per_input,
        "expected_max_records": args.limit_per_input,
        "returned": len(rows),
        "rows": rows,
    })


if __name__ == "__main__":
    main()
