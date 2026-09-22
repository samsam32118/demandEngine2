#!/usr/bin/env python3
"""Discover TikTok profiles from a TikTok search URL.

Triggers the TikTok Profiles dataset (gd_l1villgoiiidt09ci) in
discover-new mode with `discover_by=search_url`. Give it a TikTok search
results URL and it walks the accounts on that page, returning the same
full profile record `lookup_profiles.py` returns for each one.

Build the search URL on tiktok.com and copy it, e.g.
  https://www.tiktok.com/search?q=sales%20coach
  https://www.tiktok.com/search/user?q=realtor

NOTE: `country` is REQUIRED by this collector (unlike the URL-lookup
path where it's optional). The script defaults it to US.

Bills per returned profile, so --limit-per-input is required.
"""
from __future__ import annotations

import argparse

from client import TIKTOK_PROFILES_DATASET_ID, run_job
from common_args import add_common_args, add_limit_arg


def main() -> None:
    ap = argparse.ArgumentParser(
        description="Discover TikTok profiles from a TikTok search URL.",
    )
    ap.add_argument(
        "--search-url",
        action="append",
        required=True,
        help="TikTok search results URL, e.g. "
        "'https://www.tiktok.com/search?q=sales%%20coach'. Repeatable.",
    )
    ap.add_argument(
        "--country",
        default="US",
        help="Two-letter country code to scrape from (default: US). "
        "REQUIRED by this collector — don't blank it.",
    )
    add_limit_arg(ap)
    add_common_args(ap, timeout=900.0)
    args = ap.parse_args()

    if args.limit_per_input <= 0:
        ap.error("--limit-per-input must be >= 1")
    if not args.country:
        ap.error("--country is required by the search_url collector")

    inputs = [
        {"search_url": s, "country": args.country} for s in args.search_url
    ]
    run_job(
        TIKTOK_PROFILES_DATASET_ID,
        inputs,
        discover_by="search_url",
        limit_per_input=args.limit_per_input,
        fields=args.fields,
        no_wait=args.no_wait,
        timeout=args.timeout,
        poll_interval=args.poll_interval,
        extra={
            "search_urls": args.search_url,
            "country": args.country,
            "limit_per_input": args.limit_per_input,
        },
    )


if __name__ == "__main__":
    main()
