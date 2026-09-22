#!/usr/bin/env python3
"""Smoke test — exercises every Apple App Data endpoint once.

Live mode posts + polls the four task-based endpoints (search / info / reviews
/ list), hits the live listings endpoint, and reads a free reference lookup —
roughly 5 billable requests plus a couple minutes of polling on the Standard
queue. Run after any change to credentials or client.py.

Pass --dry-run to validate auth + request-building WITHOUT spending anything
(no calls made) — useful when the account balance is low.
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import client  # noqa: E402

DRY_RUN = "--dry-run" in sys.argv

# A stable, always-present app to probe info/reviews with: TikTok (835599320).
_TIKTOK = "835599320"
_US = {"location_code": 2840, "language_code": "en"}


def _post_poll(name: str, base: str, task: dict, expect_min: int, why: str) -> bool:
    """POST a task-based op, poll to completion, assert it returns enough items."""
    if DRY_RUN:
        try:
            client._auth_header()  # noqa: SLF001 — intentional wiring check
            print(f"  · {name}: request ready (dry-run, not sent)")
            return True
        except SystemExit:
            print(f"  ✗ {name}: missing credentials")
            return False
    try:
        resp = client.post(f"{base}/task_post", task)
        code, msg, posted = client.task_status(resp)
        tid = posted.get("id")
        if code not in (client.CREATED, client.OK) or not tid:
            print(f"  ✗ {name}: task_post failed {code} {msg}")
            return False
        t = client.poll_advanced(base, tid, max_wait=300)
        result = t.get("result") or []
        items = (result[0].get("items") if result else None) or []
        if len(items) < expect_min:
            print(f"  ✗ {name}: {len(items)} items, expected >= {expect_min} ({why})")
            return False
        print(f"  ✓ {name}: {len(items)} items, cost ${resp.get('cost')} ({why})")
        return True
    except Exception as e:  # noqa: BLE001
        print(f"  ✗ {name}: {e}")
        return False


def _live_listings() -> bool:
    if DRY_RUN:
        print("  · listings (live): request ready (dry-run, not sent)")
        return True
    try:
        resp = client.post(_LISTINGS, {"description": "meditation", "limit": 10})
        t = client.unwrap_task(resp)
        result = t.get("result") or []
        items = (result[0].get("items") if result else None) or []
        ok = len(items) >= 1
        print(f"  {'✓' if ok else '✗'} listings (live): {len(items)} items, cost ${resp.get('cost')}")
        return ok
    except Exception as e:  # noqa: BLE001
        print(f"  ✗ listings (live): {e}")
        return False


def _reference() -> bool:
    if DRY_RUN:
        print("  · categories (free lookup): request ready (dry-run, not sent)")
        return True
    try:
        t = client.unwrap_task(client.get("app_data/apple/categories"))
        n = len(t.get("result") or [])
        ok = n >= 1
        print(f"  {'✓' if ok else '✗'} categories (free lookup): {n} categories")
        return ok
    except Exception as e:  # noqa: BLE001
        print(f"  ✗ categories (free lookup): {e}")
        return False


_LISTINGS = "app_data/apple/app_listings/search/live"
_CASES = [
    ("search", "app_data/apple/app_searches",
     {**_US, "keyword": "meditation", "depth": 10}, 3,
     "a common keyword ranks several apps"),
    ("info", "app_data/apple/app_info",
     {**_US, "app_id": _TIKTOK}, 1, "one app record"),
    ("reviews", "app_data/apple/app_reviews",
     {**_US, "app_id": _TIKTOK, "depth": 25}, 5, "a popular app has reviews"),
    ("list", "app_data/apple/app_list",
     {**_US, "app_collection": "top_free_ios", "depth": 10}, 5,
     "the top-free chart is populated"),
]


def main() -> None:
    mode = "dry-run, no spend" if DRY_RUN else "~5 live calls + polling"
    print(f"DataForSEO Apple App Data — smoke test ({mode})")
    ok = all([_post_poll(*c) for c in _CASES])
    ok &= _live_listings()
    ok &= _reference()
    print("PASS" if ok else "FAIL")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
