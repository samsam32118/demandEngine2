#!/usr/bin/env python3
"""Look up TikTok Shop products by product URL.

Triggers Bright Data's TikTok Shop Web Scraper API
(gd_m45m1u911dsa4274pi) with one or more product URLs. Returns the full
commerce record: title, availability, currency, initial/final price and
the low/high price bands, discount_percent, units sold, colors, sizes,
shipping fee, specifications, images/videos, review count and reviews,
seller id/rating, and the store block.

Each input URL bills as one record. Use discover_shop.py when you don't
have product URLs yet.
"""
from __future__ import annotations

import argparse

from client import TIKTOK_SHOP_DATASET_ID, prune, run_job
from common_args import add_common_args


def main() -> None:
    ap = argparse.ArgumentParser(
        description="Look up TikTok Shop products by product URL."
    )
    ap.add_argument(
        "--url",
        action="append",
        required=True,
        help="TikTok Shop product URL, e.g. "
        "https://shop.tiktok.com/view/product/1234567890. Repeatable.",
    )
    ap.add_argument(
        "--category",
        default="",
        help="Optional category hint passed through to the collector.",
    )
    add_common_args(ap)
    args = ap.parse_args()

    inputs = [prune({"url": u, "category": args.category}) for u in args.url]
    run_job(
        TIKTOK_SHOP_DATASET_ID,
        inputs,
        fields=args.fields,
        no_wait=args.no_wait,
        timeout=args.timeout,
        poll_interval=args.poll_interval,
    )


if __name__ == "__main__":
    main()
