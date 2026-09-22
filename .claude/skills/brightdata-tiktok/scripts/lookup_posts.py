#!/usr/bin/env python3
"""Look up TikTok posts (videos) by post URL.

Triggers Bright Data's TikTok Posts Web Scraper API
(gd_lu702nij2f790tmv9h) with one or more video URLs and (by default)
waits for the snapshot, then emits the rows.

Returns the full engagement set — play_count, digg_count (likes),
share_count, comment_count, collect_count (saves) — plus description,
hashtags, music/original_sound, video_duration, video_url, and the
author's profile block.

Each input URL bills as one record. Prefer this over discover_posts.py
whenever you already have the video URLs.
"""
from __future__ import annotations

import argparse

from client import TIKTOK_POSTS_DATASET_ID, prune, run_job
from common_args import add_common_args


def main() -> None:
    ap = argparse.ArgumentParser(
        description="Look up TikTok posts by video URL."
    )
    ap.add_argument(
        "--url",
        action="append",
        required=True,
        help="TikTok video URL, e.g. "
        "https://www.tiktok.com/@user/video/1234567890. Repeatable.",
    )
    ap.add_argument(
        "--country",
        default="",
        help="Two-letter proxy country code, e.g. 'US'. Optional.",
    )
    add_common_args(ap)
    args = ap.parse_args()

    inputs = [prune({"url": u, "country": args.country}) for u in args.url]
    run_job(
        TIKTOK_POSTS_DATASET_ID,
        inputs,
        fields=args.fields,
        no_wait=args.no_wait,
        timeout=args.timeout,
        poll_interval=args.poll_interval,
    )


if __name__ == "__main__":
    main()
