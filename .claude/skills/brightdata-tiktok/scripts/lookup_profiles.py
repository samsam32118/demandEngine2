#!/usr/bin/env python3
"""Look up TikTok profiles by profile URL.

Triggers Bright Data's TikTok Profiles Web Scraper API
(gd_l1villgoiiidt09ci) with one or more profile URLs and (by default)
waits for the snapshot, then emits the rows.

Returns follower/following counts, likes, video count, biography, bio
link, verification status, and the three engagement rates (average,
comment, like) — the engagement fields are the reason to use this over
scraping a profile page yourself.

Each input URL bills as one record on the pay-as-you-go plan, so this is
the cheap, predictable path. Prefer it whenever you know the @handle.
"""
from __future__ import annotations

import argparse

from client import TIKTOK_PROFILES_DATASET_ID, prune, run_job
from common_args import add_common_args


def main() -> None:
    ap = argparse.ArgumentParser(
        description="Look up TikTok profiles by profile URL."
    )
    ap.add_argument(
        "--url",
        action="append",
        required=True,
        help="TikTok profile URL, e.g. https://www.tiktok.com/@nike. Pass "
        "--url multiple times for multiple profiles.",
    )
    ap.add_argument(
        "--country",
        default="",
        help="Two-letter proxy country code to scrape from, e.g. 'US'. "
        "Optional; affects geo-varying results.",
    )
    add_common_args(ap)
    args = ap.parse_args()

    inputs = [prune({"url": u, "country": args.country}) for u in args.url]
    run_job(
        TIKTOK_PROFILES_DATASET_ID,
        inputs,
        fields=args.fields,
        no_wait=args.no_wait,
        timeout=args.timeout,
        poll_interval=args.poll_interval,
    )


if __name__ == "__main__":
    main()
