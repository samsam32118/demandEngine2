#!/usr/bin/env python3
"""Discover TikTok Shop products by keyword, category URL, or shop URL.

One script, three collectors on the TikTok Shop dataset
(gd_m45m1u911dsa4274pi) — pick exactly one mode:

  --keyword       discover_by=keyword
      Product search by free text.
        python discover_shop.py --keyword "running shoes" --limit-per-input 20

  --category-url  discover_by=category
      Everything under a TikTok Shop category page.
        python discover_shop.py \
            --category-url https://shop.tiktok.com/category/... \
            --limit-per-input 20

  --shop-url      discover_by=shop
      A single seller's catalogue. Note this collector takes the plain
      "url" key, not "shop_url".
        python discover_shop.py \
            --shop-url https://shop.tiktok.com/@someseller \
            --limit-per-input 20

All three bill per returned product, so --limit-per-input is required.
"""
from __future__ import annotations

import argparse

from client import TIKTOK_SHOP_DATASET_ID, run_job
from common_args import add_common_args, add_limit_arg


def main() -> None:
    ap = argparse.ArgumentParser(
        description="Discover TikTok Shop products by keyword, category, or shop.",
    )
    mode = ap.add_mutually_exclusive_group(required=True)
    mode.add_argument(
        "--keyword",
        action="append",
        help="Product search keyword, e.g. 'running shoes'. Repeatable.",
    )
    mode.add_argument(
        "--category-url",
        action="append",
        help="TikTok Shop category page URL. Repeatable.",
    )
    mode.add_argument(
        "--shop-url",
        action="append",
        help="TikTok Shop seller/store URL. Repeatable.",
    )
    add_limit_arg(ap)
    add_common_args(ap, timeout=900.0)
    args = ap.parse_args()

    if args.limit_per_input <= 0:
        ap.error("--limit-per-input must be >= 1")

    if args.keyword:
        discover_by = "keyword"
        inputs = [{"keyword": k} for k in args.keyword]
        described = {"mode": "keyword", "keywords": args.keyword}
    elif args.category_url:
        discover_by = "category"
        inputs = [{"category_url": c} for c in args.category_url]
        described = {"mode": "category", "category_urls": args.category_url}
    else:
        discover_by = "shop"
        # The shop collector keys off "url", not "shop_url".
        inputs = [{"url": s} for s in args.shop_url]
        described = {"mode": "shop", "shop_urls": args.shop_url}

    run_job(
        TIKTOK_SHOP_DATASET_ID,
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
