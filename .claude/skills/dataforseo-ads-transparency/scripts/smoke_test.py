#!/usr/bin/env python3
"""Smoke test — exercises every Ads Transparency endpoint once.

Live mode makes ~4 billable requests (~$0.007): both live endpoints, one
queued task through post+poll, plus a free locations lookup. It also asserts
the three things this skill depends on and that would fail silently if Google
changed the response: that advertiser lookups hand back usable advertiser_ids
(including the ones nested inside a multi-account group), that ad results carry
the first/last-shown timestamps the run-length fields are derived from, and
that a creative's PNG render still downloads — the only route to ad copy, since
the API has no headline field.

Pass --dry-run to validate auth + request-building WITHOUT spending anything
(no calls made) — useful when the account balance is low.
"""
from __future__ import annotations

import os
import sys
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import client  # noqa: E402

DRY_RUN = "--dry-run" in sys.argv

_ADVERTISERS = "serp/google/ads_advertisers"
_ADS = "serp/google/ads_search"
_US = {"location_code": 2840}

# "nike" reliably returns a multi-account advertiser group, which is the shape
# the flattener exists for — if this stops nesting, the flattener needs a look.
_MULTI_ACCOUNT_KEYWORD = "nike"


def _items(task: dict) -> list:
    result = task.get("result") or []
    return ((result[0].get("items") if result else None) or [])


def _skip(name: str) -> bool:
    try:
        client._auth_header()  # noqa: SLF001 — intentional wiring check
        print(f"  · {name}: request ready (dry-run, not sent)")
        return True
    except SystemExit:
        print(f"  ✗ {name}: missing credentials")
        return False


def _live_advertisers() -> bool:
    """Live advertiser lookup + the nested-id assertion."""
    if DRY_RUN:
        return _skip("advertisers (live)")
    try:
        resp = client.post(f"{_ADVERTISERS}/live/advanced",
                           {**_US, "keyword": _MULTI_ACCOUNT_KEYWORD})
        items = _items(client.unwrap_task(resp))
        flat_ids = [i.get("advertiser_id") for i in items if i.get("advertiser_id")]
        nested = [m.get("advertiser_id")
                  for i in items if i.get("type") == "ads_multi_account_advertiser"
                  for m in (i.get("advertisers") or [])]
        ok = bool(flat_ids or nested)
        print(f"  {'✓' if ok else '✗'} advertisers (live): {len(items)} items, "
              f"{len(flat_ids)} direct + {len(nested)} nested advertiser_ids, "
              f"cost ${resp.get('cost')}")
        if not nested:
            print(f"    ! no multi-account group for {_MULTI_ACCOUNT_KEYWORD!r} — "
                  "the flattener's nested-id path went unexercised")
        return ok
    except Exception as e:  # noqa: BLE001
        print(f"  ✗ advertisers (live): {e}")
        return False


def _live_ads() -> bool:
    """Live ad search by domain + the timestamp assertion."""
    if DRY_RUN:
        return _skip("ads (live, --target)")
    try:
        resp = client.post(f"{_ADS}/live/advanced",
                           {**_US, "target": "nike.com", "depth": 40})
        items = _items(client.unwrap_task(resp))
        dated = [i for i in items if i.get("first_shown") and i.get("last_shown")]
        # The PNG render is the ONLY route to ad copy — the API has no headline
        # field — so losing it would silently gut --download-creatives.
        pngs = [i for i in items if (i.get("preview_image") or {}).get("url")]
        ok = len(items) >= 5 and len(dated) >= 1 and len(pngs) >= 1
        print(f"  {'✓' if ok else '✗'} ads (live, --target): {len(items)} creatives, "
              f"{len(dated)} with first/last_shown, {len(pngs)} with a copy-bearing "
              f"PNG render, cost ${resp.get('cost')}")
        if pngs:
            url = pngs[0]["preview_image"]["url"]
            try:
                req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
                with urllib.request.urlopen(req, timeout=30) as r:
                    ct, n = r.headers.get("Content-Type", ""), len(r.read())
                good = ct.startswith("image/") and n > 1000
                print(f"  {'✓' if good else '✗'} creative render downloads: {ct}, {n} bytes (free)")
                ok &= good
            except Exception as e:  # noqa: BLE001
                print(f"  ✗ creative render downloads: {e}")
                ok = False
        return ok
    except Exception as e:  # noqa: BLE001
        print(f"  ✗ ads (live, --target): {e}")
        return False


def _live_ads_by_id() -> bool:
    """The chaining path: advertiser_ids straight into ads_search."""
    if DRY_RUN:
        return _skip("ads (live, --advertiser-ids)")
    try:
        resp = client.post(f"{_ADS}/live/advanced",
                           {**_US, "advertiser_ids": ["AR16735076323512287233"],
                            "depth": 40})
        items = _items(client.unwrap_task(resp))
        ok = len(items) >= 1
        print(f"  {'✓' if ok else '✗'} ads (live, --advertiser-ids): {len(items)} "
              f"creatives, cost ${resp.get('cost')}")
        return ok
    except Exception as e:  # noqa: BLE001
        print(f"  ✗ ads (live, --advertiser-ids): {e}")
        return False


def _queued_task() -> bool:
    """The --queued path: task_post then poll task_get/advanced."""
    if DRY_RUN:
        return _skip("advertisers (queued task_post + poll)")
    try:
        resp = client.post(f"{_ADVERTISERS}/task_post", {**_US, "keyword": "hubspot"})
        code, msg, posted = client.task_status(resp)
        tid = posted.get("id")
        if code not in (client.CREATED, client.OK) or not tid:
            print(f"  ✗ advertisers (queued): task_post failed {code} {msg}")
            return False
        items = _items(client.poll_advanced(_ADVERTISERS, tid, max_wait=300))
        ok = len(items) >= 1
        print(f"  {'✓' if ok else '✗'} advertisers (queued task_post + poll): "
              f"{len(items)} items, cost ${resp.get('cost')}")
        return ok
    except Exception as e:  # noqa: BLE001
        print(f"  ✗ advertisers (queued): {e}")
        return False


def _locations() -> bool:
    if DRY_RUN:
        return _skip("locations (free lookup)")
    try:
        t = client.unwrap_task(client.get(f"{_ADVERTISERS}/locations"))
        n = len(t.get("result") or [])
        ok = n >= 1
        print(f"  {'✓' if ok else '✗'} locations (free lookup): {n} locations")
        return ok
    except Exception as e:  # noqa: BLE001
        print(f"  ✗ locations (free lookup): {e}")
        return False


def main() -> None:
    mode = "dry-run, no spend" if DRY_RUN else "~4 billable calls (~$0.007) + polling"
    print(f"DataForSEO Google Ads Transparency — smoke test ({mode})")
    ok = _live_advertisers()
    ok &= _live_ads()
    ok &= _live_ads_by_id()
    ok &= _queued_task()
    ok &= _locations()
    print("PASS" if ok else "FAIL")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
