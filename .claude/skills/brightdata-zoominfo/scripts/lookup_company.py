#!/usr/bin/env python3
"""Look up ZoomInfo company profiles by ZoomInfo URL.

Uses Bright Data's ZoomInfo Web Scraper API (/datasets/v3/scrape) which
is synchronous — the call blocks until the data is ready. No polling needed.

One billable record per URL on the pay-as-you-go plan.

STEP 1 — resolve the ZoomInfo URL (if you only have a company name):
    Run brightdata-serp search.py "<company name> zoominfo" and find the URL
    matching www.zoominfo.com/c/<company-name>/<id> in the results.

STEP 2 — scrape the profile:
    python scripts/lookup_company.py --url https://www.zoominfo.com/c/<company-name>/<id>
"""
from __future__ import annotations

import argparse
import sys

from client import (
    ZOOMINFO_DATASET_ID,
    emit,
    parse_fields,
    scrape,
    trigger,
    wait_for_snapshot,
)


def main() -> None:
    ap = argparse.ArgumentParser(
        description="Look up ZoomInfo company profiles by URL."
    )
    ap.add_argument(
        "--url",
        action="append",
        required=True,
        help=(
            "ZoomInfo company profile URL, e.g. "
            "https://www.zoominfo.com/c/walmart-inc/155353090. "
            "Pass --url multiple times for multiple companies."
        ),
    )
    ap.add_argument(
        "--fields",
        help=(
            "Comma-separated subset of output fields (e.g. "
            "'name,revenue,total_employees,headquarters'). Defaults to the "
            "full record. Run describe_fields.py --names-only for the list."
        ),
    )
    ap.add_argument(
        "--no-wait",
        action="store_true",
        help=(
            "Use the async /trigger path and return the snapshot_id "
            "immediately. Default is the synchronous /scrape path."
        ),
    )
    ap.add_argument(
        "--timeout",
        type=float,
        default=300.0,
        help=(
            "Seconds to wait for the synchronous scrape response "
            "(default: 300). Increase for multi-URL batches."
        ),
    )
    ap.add_argument(
        "--poll-interval",
        type=float,
        default=10.0,
        help="Seconds between /progress polls when not using --no-wait async (default: 10).",
    )
    args = ap.parse_args()

    for u in args.url:
        if "/p/" in u or "/people/" in u:
            sys.stderr.write(
                f"error: {u!r} looks like a ZoomInfo person URL. The "
                "Bright Data ZoomInfo dataset is company-only; person URLs "
                "are silently scraped to all-null records but still bill "
                "one chargeable record each. Pass a /c/<slug>/<id> "
                "company URL instead, then read the nested `leadership` "
                "field for people data.\n"
            )
            sys.exit(2)

    inputs = [{"url": u} for u in args.url]
    fields = parse_fields(args.fields)

    if args.no_wait:
        try:
            snapshot_id = trigger(
                ZOOMINFO_DATASET_ID,
                inputs,
                custom_output_fields=fields,
                include_errors=True,
            )
        except RuntimeError as e:
            sys.stderr.write(f"error: {e}\n")
            sys.exit(1)
        emit({"snapshot_id": snapshot_id, "status": "triggered", "inputs": len(inputs)})
        return

    try:
        rows = scrape(
            ZOOMINFO_DATASET_ID,
            inputs,
            custom_output_fields=fields,
            include_errors=True,
            scrape_timeout=args.timeout,
            poll_interval=args.poll_interval,
            poll_timeout=args.timeout * 2,
        )
    except RuntimeError as e:
        sys.stderr.write(f"error: {e}\n")
        sys.exit(1)

    emit({"returned": len(rows), "rows": rows})


if __name__ == "__main__":
    main()
