#!/usr/bin/env python3
"""Look up PitchBook company profiles by PitchBook URL.

Uses Bright Data's PitchBook Web Scraper API (/datasets/v3/scrape) which
is synchronous — the call blocks until the data is ready. No polling needed.

One billable record per URL on the pay-as-you-go plan.

STEP 1 — resolve the PitchBook URL (if you only have a company name):
    Run brightdata-serp search.py "<company name> pitchbook" and find the URL
    matching pitchbook.com/profiles/company/<id> in the results.

STEP 2 — scrape the profile:
    python scripts/lookup_company.py --url https://pitchbook.com/profiles/company/<id>
"""
from __future__ import annotations

import argparse
import sys

from client import (
    PITCHBOOK_DATASET_ID,
    emit,
    scrape,
)


def main() -> None:
    ap = argparse.ArgumentParser(
        description="Look up PitchBook company profiles by URL."
    )
    ap.add_argument(
        "--url",
        action="append",
        required=True,
        help=(
            "PitchBook company profile URL, e.g. "
            "https://pitchbook.com/profiles/company/467033-41. "
            "Pass --url multiple times for multiple companies."
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
    args = ap.parse_args()

    inputs = [{"url": u} for u in args.url]
    try:
        rows = scrape(
            PITCHBOOK_DATASET_ID,
            inputs,
            include_errors=True,
            scrape_timeout=args.timeout,
        )
    except RuntimeError as e:
        sys.stderr.write(f"error: {e}\n")
        sys.exit(1)

    emit({"returned": len(rows), "rows": rows})


if __name__ == "__main__":
    main()
