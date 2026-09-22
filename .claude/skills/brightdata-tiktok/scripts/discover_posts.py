#!/usr/bin/env python3
"""Discover TikTok posts by profile, keyword/hashtag, or discovery URL.

One script, three collectors on the TikTok Posts dataset
(gd_lu702nij2f790tmv9h) — pick exactly one mode:

  --profile-url    discover_by=profile_url
      Recent videos from a creator. Supports date range, post type,
      sort order, and a what_to_collect switch.
        python discover_posts.py --profile-url https://www.tiktok.com/@nike \
            --limit-per-input 10

  --keyword        discover_by=keyword
      Videos matching a search keyword or hashtag. Pass hashtags with or
      without the '#'.
        python discover_posts.py --keyword "sales coach" --limit-per-input 20

  --discovery-url  discover_by=url
      Videos from a TikTok /discover/ landing page.
        python discover_posts.py \
            --discovery-url https://www.tiktok.com/discover/sales-tips \
            --limit-per-input 20
      Use the /discover/<slug> shape. A /tag/<slug> hashtag URL is
      accepted by the API but comes back empty with
      error_code "dead_page" — for hashtags use --keyword instead.

TRAP: the discovery-url collector takes a CAPITAL "URL" key in the
request body and explicitly rejects lowercase "url" — the API returns
"This input should not contain a url field". This script sends the right
casing for you; if you hand-roll curl, mind it (references/curls.md).

All three bill per returned post, so --limit-per-input is required.
"""
from __future__ import annotations

import argparse

from client import TIKTOK_POSTS_DATASET_ID, prune, run_job
from common_args import add_common_args, add_limit_arg


def main() -> None:
    ap = argparse.ArgumentParser(
        description="Discover TikTok posts by profile, keyword, or discovery URL.",
    )
    mode = ap.add_mutually_exclusive_group(required=True)
    mode.add_argument(
        "--profile-url",
        action="append",
        help="Creator profile URL to pull recent videos from, e.g. "
        "https://www.tiktok.com/@nike. Repeatable.",
    )
    mode.add_argument(
        "--keyword",
        action="append",
        help="Search keyword or hashtag, e.g. 'sales coach' or '#salestips'. "
        "Repeatable.",
    )
    mode.add_argument(
        "--discovery-url",
        action="append",
        help="TikTok /discover/ page URL, e.g. "
        "https://www.tiktok.com/discover/sales-tips. Repeatable. Use "
        "--keyword for hashtags — /tag/ URLs return dead_page.",
    )

    ap.add_argument(
        "--country",
        default="",
        help="Two-letter proxy country code, e.g. 'US'. Optional, all modes.",
    )
    # profile_url-only filters
    ap.add_argument(
        "--start-date",
        default="",
        help="profile mode only. Start of the date window, MM-DD-YYYY.",
    )
    ap.add_argument(
        "--end-date",
        default="",
        help="profile mode only. End of the date window, MM-DD-YYYY.",
    )
    ap.add_argument(
        "--what-to-collect",
        default="",
        help="profile mode only. What to pull, e.g. 'Posts', "
        "'Reposts', 'Posts & Reposts'.",
    )
    ap.add_argument(
        "--post-type",
        default="",
        help="profile mode only. Filter by type, e.g. 'Video', 'Image'.",
    )
    ap.add_argument(
        "--sort-by",
        default="",
        help="profile mode only. Sort order, e.g. 'Latest', 'Popular'.",
    )

    add_limit_arg(ap)
    add_common_args(ap, timeout=900.0)
    args = ap.parse_args()

    if args.limit_per_input <= 0:
        ap.error("--limit-per-input must be >= 1")

    profile_only = {
        "--start-date": args.start_date,
        "--end-date": args.end_date,
        "--what-to-collect": args.what_to_collect,
        "--post-type": args.post_type,
        "--sort-by": args.sort_by,
    }
    used_profile_only = [flag for flag, val in profile_only.items() if val]
    if used_profile_only and not args.profile_url:
        verb = "applies" if len(used_profile_only) == 1 else "apply"
        ap.error(
            f"{', '.join(used_profile_only)} only {verb} to --profile-url "
            "mode; the keyword and discovery-url collectors ignore "
            f"{'it' if len(used_profile_only) == 1 else 'them'}"
        )

    if args.profile_url:
        discover_by = "profile_url"
        inputs = [
            prune({
                "url": u,
                "country": args.country,
                "start_date": args.start_date,
                "end_date": args.end_date,
                "what_to_collect": args.what_to_collect,
                "post_type": args.post_type,
                "sort_by": args.sort_by,
            })
            for u in args.profile_url
        ]
        described = {"mode": "profile_url", "profile_urls": args.profile_url}
    elif args.keyword:
        discover_by = "keyword"
        inputs = [
            prune({"search_keyword": k, "country": args.country})
            for k in args.keyword
        ]
        described = {"mode": "keyword", "keywords": args.keyword}
    else:
        discover_by = "url"
        # Capital "URL" is mandatory for this collector — see module docstring.
        inputs = [
            prune({"URL": u, "country": args.country})
            for u in args.discovery_url
        ]
        described = {"mode": "url", "discovery_urls": args.discovery_url}

    run_job(
        TIKTOK_POSTS_DATASET_ID,
        inputs,
        discover_by=discover_by,
        limit_per_input=args.limit_per_input,
        fields=args.fields,
        no_wait=args.no_wait,
        timeout=args.timeout,
        poll_interval=args.poll_interval,
        extra={**described, "limit_per_input": args.limit_per_input},
    )


if __name__ == "__main__":
    main()
