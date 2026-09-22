#!/usr/bin/env python3
"""Scrape the comments on TikTok videos.

Triggers Bright Data's TikTok Comments Web Scraper API
(gd_lkf2st302ap89utw5k) with one or more video URLs. Returns one row per
comment: comment_text, num_likes, num_replies, date_created, the
commenter (user name, id, profile URL), and — when --collect-replies is
set — the nested reply thread.

This dataset is URL-collection only; it has no discovery mode. The input
is the VIDEO url, not a comment url.

Billing note: this is the one scraper where a single input can bill many
records — you pay per COMMENT returned, not per video. A viral video can
carry thousands. Use --num-of-comments to cap it; it is a real
standalone cap (verified: 30 requested on a 166-comment video with no
limit_per_input returned exactly 30).

Ordering: rows come back in TikTok's own relevance order — NOT sorted by
likes and not by date, and there is no sort input on this collector. In
practice a cap is still a good "top N" pull (a cap of 20 captured 90% of
the true top-20 by likes in testing). For a strict ranking, over-pull
and sort on num_likes yourself.
"""
from __future__ import annotations

import argparse

from client import TIKTOK_COMMENTS_DATASET_ID, prune, run_job
from common_args import add_common_args


def main() -> None:
    ap = argparse.ArgumentParser(
        description="Scrape comments from TikTok videos by video URL."
    )
    ap.add_argument(
        "--url",
        action="append",
        required=True,
        help="TikTok video URL to pull comments from, e.g. "
        "https://www.tiktok.com/@user/video/1234567890. Repeatable.",
    )
    ap.add_argument(
        "--collect-replies",
        action="store_true",
        help="Also collect threaded replies to each comment. Increases the "
        "record count (and the bill).",
    )
    ap.add_argument(
        "--num-of-comments",
        type=int,
        help="Cap the comments pulled per video. Strongly recommended — "
        "without it a viral video can return thousands of billable rows.",
    )
    ap.add_argument(
        "--limit-per-input",
        type=int,
        help="Hard server-side cap on records per video. Belt-and-braces "
        "alongside --num-of-comments.",
    )
    add_common_args(ap, timeout=900.0)
    args = ap.parse_args()

    inputs = [
        prune({
            "url": u,
            # Only send the flag when set; the collector defaults it off.
            "collect_replies": True if args.collect_replies else None,
            "num_of_comments": args.num_of_comments,
        })
        for u in args.url
    ]
    run_job(
        TIKTOK_COMMENTS_DATASET_ID,
        inputs,
        limit_per_input=args.limit_per_input,
        fields=args.fields,
        no_wait=args.no_wait,
        timeout=args.timeout,
        poll_interval=args.poll_interval,
        extra={
            "videos": len(inputs),
            "collect_replies": args.collect_replies,
            "num_of_comments": args.num_of_comments,
        },
    )


if __name__ == "__main__":
    main()
