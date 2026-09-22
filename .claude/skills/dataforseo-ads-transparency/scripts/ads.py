#!/usr/bin/env python3
"""DataForSEO Google Ads Transparency — competitor ad intel, one CLI.

Two endpoints, two questions:

  advertisers KEYWORD   serp/google/ads_advertisers
                        WHO is running Google ads for a brand/term — advertiser
                        accounts (with the advertiser_id you need next), how
                        many ads each runs, whether Google verified them, and
                        the domains associated with the term.

  ads --target/--ids    serp/google/ads_search
                        WHAT they are actually running — every creative in an
                        advertiser's public library: format, the exact ad URL,
                        and the first/last date Google showed it.

The two chain: `advertisers` gives you advertiser_ids, `ads` turns those into
creatives. `ads --advertiser-for "<name>"` does both in one command.

Detached retrieval (only relevant with --queued, where tasks sit in a queue):

  get ID    fetch a previously-posted task's advanced result (polls until ready)
  ready     list finished tasks awaiting collection (tasks_ready)

Free reference lookup:

  locations

Cost: each call is one billable request. Live (default) is ~$0.002 and returns
in seconds; --queued uses the Standard queue at ~$0.0006 but can lag ~30s+.
`ads` bills per 40 results, so --depth 120 costs 3x. Results are cached on disk
keyed by the request, so re-running an identical query is free. Defaults are
US (location_code 2840).
"""
from __future__ import annotations

import argparse
import collections
import csv
import datetime as dt
import hashlib
import io
import json
import math
import os
import re
import sys
import time
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import client  # noqa: E402

_CACHE_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".cache")
_LEDGER = os.path.join(_CACHE_DIR, "tasks_ledger.json")

# Endpoint stems. Both endpoints expose live/advanced, task_post,
# task_get/advanced/{id}, tasks_ready and locations under the same stem.
_BASE = {
    "advertisers": "serp/google/ads_advertisers",
    "ads": "serp/google/ads_search",
}

# Verified against the pricing pages and live calls (2026-08).
# `ads` additionally multiplies by ceil(depth / 40) — one SERP page = 40 ads.
_UNIT_PRICE = {"live": 0.002, "standard": 0.0006, "high": 0.0012}

_PLATFORMS = ["all", "google_play", "google_maps", "google_search",
              "google_shopping", "youtube"]
_AD_FORMATS = ["all", "text", "image", "video"]

# Columns for table/CSV output. --raw keeps every field the API returned.
_ADVERTISER_COLS = ["rank_absolute", "advertiser_id", "title", "kind", "location",
                    "verified", "approx_ads_count", "domain"]
_AD_COLS = ["rank_absolute", "advertiser_id", "title", "creative_id", "format",
            "copy", "first_shown", "last_shown", "days_running",
            "days_since_shown", "active", "verified", "url"]
# Long asset URLs would wreck the table but are the whole point of a CSV you
# intend to work from, so they ride along in the file only.
_AD_CSV_EXTRA = ["preview_image", "preview_url", "preview_width", "preview_height"]

# A creative whose last_shown is within this many days is treated as still
# live. Google's transparency feed lags by a day or two, so a small window
# avoids calling yesterday's active ads "stopped".
_ACTIVE_WINDOW_DAYS = 7


# --------------------------------------------------------------------------
# Input parsing
# --------------------------------------------------------------------------

def _parse_target(raw: str) -> str:
    """Accept a bare domain, a URL, or a www-prefixed host and return the
    registrable host DataForSEO expects (`nike.com`, not
    `https://www.nike.com/en/shoes`)."""
    t = raw.strip()
    t = re.sub(r"^[a-zA-Z][a-zA-Z0-9+.-]*://", "", t)  # strip scheme
    t = t.split("/", 1)[0].split("?", 1)[0]            # strip path/query
    t = t.split("@")[-1]                               # strip userinfo
    t = re.sub(r":\d+$", "", t)                        # strip port
    if t.lower().startswith("www."):
        t = t[4:]
    if not t or "." not in t:
        _die(f"{raw!r} does not look like a domain (expected e.g. nike.com)")
    return t.lower()


def _parse_advertiser_id(raw: str) -> str:
    """Advertiser ids look like AR13752565271262920705. Accept the bare id or
    any adstransparency.google.com URL containing one."""
    s = raw.strip()
    m = re.search(r"\bAR\d{6,}\b", s)
    if m:
        return m.group(0)
    _die(f"could not find an advertiser id (AR…) in {raw!r}")


def _parse_dt(value):
    """DataForSEO stamps look like '2022-11-30 14:50:01 +00:00'."""
    if not value:
        return None
    try:
        return dt.datetime.strptime(str(value), "%Y-%m-%d %H:%M:%S %z")
    except ValueError:
        return None


# --------------------------------------------------------------------------
# Task building
# --------------------------------------------------------------------------

def _add_location(task: dict, args) -> None:
    if getattr(args, "location_name", None):
        task["location_name"] = args.location_name
    elif getattr(args, "location_coordinate", None):
        task["location_coordinate"] = args.location_coordinate
    elif getattr(args, "location_code", None) is not None:
        task["location_code"] = args.location_code


def _priority(args) -> int:
    return 2 if getattr(args, "priority", "standard") == "high" else 1


def _mode(args) -> str:
    """Which billing/latency mode this call runs in."""
    if getattr(args, "queued", False) or getattr(args, "async_", False):
        return "high" if _priority(args) == 2 else "standard"
    return "live"


def _build_task(op: str, args) -> dict:
    if op == "advertisers":
        task: dict = {"keyword": args.keyword}
    else:
        task = {"depth": args.depth}
        if getattr(args, "target", None):
            task["target"] = _parse_target(args.target)
        if getattr(args, "advertiser_ids", None):
            task["advertiser_ids"] = [_parse_advertiser_id(i) for i in args.advertiser_ids]
        if args.platform and args.platform != "all":
            task["platform"] = args.platform
        if args.ad_format and args.ad_format != "all":
            task["format"] = args.ad_format
        if args.since:
            task["date_from"] = args.since
        if args.until:
            task["date_to"] = args.until
    _add_location(task, args)
    if _mode(args) != "live":
        task["priority"] = _priority(args)
    if getattr(args, "tag", None):
        task["tag"] = args.tag
    return task


# --------------------------------------------------------------------------
# Response normalization
# --------------------------------------------------------------------------

def _items(task: dict) -> list[dict]:
    result = task.get("result") or []
    first = result[0] if result else {}
    return (first.get("items") if first else None) or []


def _result_meta(task: dict) -> dict:
    result = task.get("result") or []
    first = result[0] if result else {}
    return {
        "keyword": first.get("keyword"),
        "item_types": first.get("item_types"),
        "items_count": first.get("items_count"),
        "check_url": first.get("check_url"),
        "datetime": first.get("datetime"),
    }


def _flatten_advertisers(items: list[dict]) -> list[dict]:
    """One row per usable advertiser_id.

    The API returns three shapes and only two of them carry an id you can feed
    into `ads`. The awkward one is `ads_multi_account_advertiser`: a brand that
    runs several Google Ads accounts. It has a title and a combined ad count
    but NO advertiser_id of its own — the real ids sit in a nested
    `advertisers` array. Reading only the top level of that item leaves you
    with a name and nothing to look up, so we lift each member account into its
    own row and carry the parent's title down. `ads_domain` items carry no id
    at all (just a domain), so they surface as domain rows you can pass to
    `ads --target`.
    """
    rows: list[dict] = []
    for it in items:
        kind = it.get("type")
        if kind == "ads_multi_account_advertiser":
            members = it.get("advertisers") or []
            for m in members:
                rows.append({
                    "rank_absolute": it.get("rank_absolute"),
                    "advertiser_id": m.get("advertiser_id"),
                    "title": it.get("title"),
                    "kind": "account_of_group",
                    "location": m.get("location") or it.get("location"),
                    "verified": m.get("verified"),
                    "approx_ads_count": m.get("approx_ads_count"),
                    "group_ads_count": it.get("approx_ads_count"),
                    "group_accounts": len(members),
                })
            if not members:  # defensive: a group with no accounts listed
                rows.append({
                    "rank_absolute": it.get("rank_absolute"),
                    "title": it.get("title"), "kind": "advertiser_group",
                    "location": it.get("location"),
                    "approx_ads_count": it.get("approx_ads_count"),
                })
        elif kind == "ads_advertiser":
            rows.append({
                "rank_absolute": it.get("rank_absolute"),
                "advertiser_id": it.get("advertiser_id"),
                "title": it.get("title"),
                "kind": "advertiser",
                "location": it.get("location"),
                "verified": it.get("verified"),
                "approx_ads_count": it.get("approx_ads_count"),
            })
        elif kind == "ads_domain":
            rows.append({
                "rank_absolute": it.get("rank_absolute"),
                "title": it.get("domain"),
                "kind": "domain",
                "domain": it.get("domain"),
            })
        else:  # unknown future item type — keep it rather than silently drop
            row = dict(it)
            row["kind"] = kind
            rows.append(row)
    return rows


def _flatten_ads(items: list[dict], active_days: int) -> list[dict]:
    """Flatten creatives and derive the run-duration fields.

    The API gives raw `first_shown` / `last_shown` timestamps. The question
    people actually ask is "how long has this been running, and is it still
    up?" — a creative Google has served for 18 months is a proven winner, one
    that stopped last month was cut. Deriving those two numbers here means
    every caller gets the same definition instead of re-deriving it.
    """
    now = dt.datetime.now(dt.timezone.utc)
    rows = []
    for it in items:
        r = dict(it)
        img = it.get("preview_image")
        if isinstance(img, dict):
            r["preview_image"] = img.get("url")
            r["preview_width"] = img.get("width")
            r["preview_height"] = img.get("height")
        # Where the actual ad copy lives. The API has no headline/description
        # field — `title` is the ADVERTISER's name — but Google renders most
        # text ads to a PNG that shows the full headline, description and
        # display URL. `png` means the copy is one download away; `js` means
        # the only preview is a JavaScript bundle that needs a browser, so the
        # transparency `url` is the route for a human.
        r["copy"] = "png" if r.get("preview_image") else ("js" if it.get("preview_url") else "")
        first, last = _parse_dt(it.get("first_shown")), _parse_dt(it.get("last_shown"))
        if first and last:
            r["days_running"] = max(0, (last - first).days)
        if last:
            since = max(0, (now - last).days)
            r["days_since_shown"] = since
            r["active"] = since <= active_days
        rows.append(r)
    return rows


def _download_creatives(rows: list[dict], dest: str) -> dict:
    """Download the rendered ad PNGs so the copy can actually be read.

    This is the only route to headline/description text: the API returns no
    copy field, but a text ad's `preview_image` is a PNG of the rendered ad.
    Saved as <creative_id>.png next to an index.csv, so a follow-up step can
    open them and transcribe the copy.
    """
    os.makedirs(dest, exist_ok=True)
    saved, skipped, failed = [], 0, []
    for r in rows:
        url = r.get("preview_image")
        cid = r.get("creative_id") or "unknown"
        if not url:
            skipped += 1
            continue
        path = os.path.join(dest, f"{cid}.png")
        if os.path.exists(path) and os.path.getsize(path) > 0:
            saved.append((cid, path))
            continue
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=30) as resp:
                data = resp.read()
            with open(path, "wb") as fh:
                fh.write(data)
            saved.append((cid, path))
        except Exception as e:  # noqa: BLE001 — one bad asset must not kill the run
            failed.append(f"{cid}: {e}")
    index = os.path.join(dest, "index.csv")
    by_id = {r.get("creative_id"): r for r in rows}
    with open(index, "w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["creative_id", "file", "advertiser_id", "title", "format",
                    "first_shown", "last_shown", "days_running", "url"])
        for cid, path in saved:
            r = by_id.get(cid, {})
            w.writerow([cid, os.path.basename(path), r.get("advertiser_id"),
                        r.get("title"), r.get("format"), r.get("first_shown"),
                        r.get("last_shown"), r.get("days_running"), r.get("url")])
    return {"dir": os.path.abspath(dest), "downloaded": len(saved),
            "no_png_render": skipped, "failed": failed[:5],
            "index": os.path.abspath(index),
            "note": "open the .png files to read each ad's headline and description"}


def _summarize_ads(rows: list[dict], active_days: int) -> dict:
    """The 'so what' layer over a creative dump: format mix, how much of the
    library is still live, and the longest-running creative (the strongest
    single signal of what is working for that advertiser)."""
    if not rows:
        return {}
    fmts = collections.Counter(r.get("format") for r in rows if r.get("format"))
    advertisers = collections.Counter(r.get("title") for r in rows if r.get("title"))
    active = [r for r in rows if r.get("active")]
    dated = [r for r in rows if r.get("days_running") is not None]
    longest = max(dated, key=lambda r: r["days_running"]) if dated else None
    firsts = [d for d in (_parse_dt(r.get("first_shown")) for r in rows) if d]
    out = {
        "creatives": len(rows),
        "advertiser_accounts": len(advertisers),
        "advertisers_by_creatives": dict(advertisers.most_common(10)),
        "format_mix": dict(fmts),
        "readable_copy_pngs": sum(1 for r in rows if r.get("copy") == "png"),
        "active_now": len(active),
        "active_window_days": active_days,
    }
    if longest:
        out["longest_running"] = {
            "creative_id": longest.get("creative_id"),
            "title": longest.get("title"),
            "format": longest.get("format"),
            "days_running": longest.get("days_running"),
            "url": longest.get("url"),
        }
    if firsts:
        out["oldest_first_shown"] = min(firsts).strftime("%Y-%m-%d")
        out["newest_first_shown"] = max(firsts).strftime("%Y-%m-%d")
    return out


def _summarize_advertisers(rows: list[dict]) -> dict:
    ided = [r for r in rows if r.get("advertiser_id")]
    counts = [r.get("approx_ads_count") or 0 for r in ided]
    return {
        "rows": len(rows),
        "advertiser_ids": len(ided),
        "verified": sum(1 for r in ided if r.get("verified")),
        "domains": sum(1 for r in rows if r.get("kind") == "domain"),
        "total_approx_ads": sum(counts),
        "biggest_advertiser": (max(ided, key=lambda r: r.get("approx_ads_count") or 0)
                               .get("title") if ided else None),
    }


def _norm_rows(op: str, items: list[dict], args) -> list[dict]:
    if op == "advertisers":
        rows = _flatten_advertisers(items)
        if getattr(args, "sort_by", "rank") == "ads":
            rows.sort(key=lambda r: r.get("approx_ads_count") or -1, reverse=True)
        return rows
    return _flatten_ads(items, getattr(args, "active_days", _ACTIVE_WINDOW_DAYS))


# --------------------------------------------------------------------------
# Caching + async ledger
# --------------------------------------------------------------------------

# Fields that change how/when a call runs, not what it returns — excluded from
# the cache key so a live call and a queued call share one cached answer.
_VOLATILE = {"priority", "tag", "postback_url", "postback_data", "pingback_url"}


def _cache_key(base: str, task: dict) -> str:
    stable = {k: v for k, v in task.items() if k not in _VOLATILE}
    blob = json.dumps({"endpoint": base, "task": stable}, sort_keys=True)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def _cache_get(key: str):
    path = os.path.join(_CACHE_DIR, key + ".json")
    if os.path.exists(path):
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    return None


def _cache_put(key: str, task: dict, cost) -> None:
    os.makedirs(_CACHE_DIR, exist_ok=True)
    with open(os.path.join(_CACHE_DIR, key + ".json"), "w", encoding="utf-8") as fh:
        json.dump({"task": task, "cost": cost}, fh)


def _ledger_load() -> dict:
    if os.path.exists(_LEDGER):
        try:
            with open(_LEDGER, encoding="utf-8") as fh:
                return json.load(fh)
        except (json.JSONDecodeError, OSError):
            return {}
    return {}


def _ledger_record(task_id: str, op: str, summary: str) -> None:
    os.makedirs(_CACHE_DIR, exist_ok=True)
    led = _ledger_load()
    led[task_id] = {"op": op, "base": _BASE[op], "summary": summary,
                    "posted_at": int(time.time())}
    with open(_LEDGER, "w", encoding="utf-8") as fh:
        json.dump(led, fh, indent=2)


# --------------------------------------------------------------------------
# Output
# --------------------------------------------------------------------------

def _fmt(v) -> str:
    return "" if v is None else str(v)


def _cell(v, width: int | None) -> str:
    s = _fmt(v).replace("\n", " ").replace("\r", " ").replace("|", "\\|")
    if width and len(s) > width:
        s = s[: width - 1] + "…"
    return s


def _markdown_table(rows: list[dict], cols: list[str], width: int | None = 60) -> str:
    lines = ["| " + " | ".join(cols) + " |",
             "|" + "|".join("---" for _ in cols) + "|"]
    for r in rows:
        lines.append("| " + " | ".join(_cell(r.get(c), width) for c in cols) + " |")
    return "\n".join(lines)


def _csv_string(rows: list[dict], cols: list[str]) -> str:
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=cols, extrasaction="ignore")
    w.writeheader()
    for r in rows:
        w.writerow({c: _fmt(r.get(c)) for c in cols})
    return buf.getvalue()


def _emit(op: str, rows: list[dict], meta: dict, args) -> None:
    cols = list(_ADVERTISER_COLS if op == "advertisers" else _AD_COLS)
    # Drop columns empty for EVERY row so the view stays readable — e.g.
    # `domain` is only populated when the keyword surfaced domain items.
    if rows:
        cols = [c for c in cols if any(r.get(c) not in (None, "") for r in rows)]

    if getattr(args, "csv", None):  # CSV file always gets the FULL set
        # The CSV is what you actually work from, so it keeps the asset URLs
        # the table drops for width.
        csv_cols = cols + [c for c in (_AD_CSV_EXTRA if op == "ads" else [])
                           if any(r.get(c) not in (None, "") for r in rows)]
        with open(args.csv, "w", encoding="utf-8", newline="") as fh:
            fh.write(_csv_string(rows, csv_cols))
        meta["csv_path"] = os.path.abspath(args.csv)

    if op == "ads" and getattr(args, "download_creatives", None):
        meta["creatives"] = _download_creatives(rows, args.download_creatives)

    limit_out = getattr(args, "limit_out", None)
    shown = rows if limit_out is None else rows[: limit_out]
    meta["total_returned"] = len(rows)
    meta["shown"] = len(shown)
    if limit_out is not None and len(rows) > limit_out:
        meta["truncated"] = True

    summary = (_summarize_advertisers(rows) if op == "advertisers"
               else _summarize_ads(rows, getattr(args, "active_days", _ACTIVE_WINDOW_DAYS)))
    if summary:
        meta["summary"] = summary

    if args.format == "table":
        print(_markdown_table(shown, cols, width=46 if op == "ads" else 60))
        if summary:
            print()
            for k, v in summary.items():
                print(f"{k:>22}: {json.dumps(v) if isinstance(v, (dict, list)) else v}")
        if meta.get("creatives"):
            c = meta["creatives"]
            print(f"\n{c['downloaded']} rendered ad PNGs → {c['dir']}"
                  f" ({c['no_png_render']} had no PNG render; open the files to "
                  f"read each ad's headline and description)")
        print(f"\n_{meta['shown']} of {meta['total_returned']} rows"
              f" · cost ${meta.get('cost')}"
              + (f" · full CSV: {meta['csv_path']}" if meta.get("csv_path") else "")
              + (" · cached (free)" if meta.get("from_cache") else "") + "_")
    elif args.format == "csv":
        sys.stdout.write(_csv_string(shown, cols))
    elif args.format == "ids":
        # Bare advertiser ids, newline-separated — the chaining format.
        for r in shown:
            if r.get("advertiser_id"):
                print(r["advertiser_id"])
    else:  # json
        print(json.dumps({"meta": meta, "items": shown}, indent=2, ensure_ascii=False))


# --------------------------------------------------------------------------
# Runners
# --------------------------------------------------------------------------

def _billable_units(op: str, args) -> int:
    """`ads` bills per SERP page of 40 creatives; `advertisers` is flat."""
    if op != "ads":
        return 1
    return max(1, math.ceil((getattr(args, "depth", 40) or 40) / 40))


def _est_cost(op: str, args) -> float:
    return round(_UNIT_PRICE[_mode(args)] * _billable_units(op, args), 6)


def _dry_run(op: str, endpoint: str, task: dict, is_cached: bool, args) -> None:
    units = _billable_units(op, args)
    print(json.dumps({
        "dry_run": True,
        "endpoint": endpoint,
        "request_body": [task],
        "mode": _mode(args),
        "billable": not is_cached,
        "billing": (f"{units} × ${_UNIT_PRICE[_mode(args)]} "
                    f"({'per 40 creatives' if op == 'ads' else 'flat per call'})"
                    f" ≈ ${_est_cost(op, args)}"),
        "note": ("already cached — running this is FREE" if is_cached else
                 "not cached — running this costs the estimate above"),
    }, indent=2, ensure_ascii=False))


def _fetch(op: str, args) -> tuple[dict, dict]:
    """Run one op and return (completed_task, meta). Shared by every path so
    caching, dry-run, live-vs-queued and polling live in exactly one place."""
    base = _BASE[op]
    task = _build_task(op, args)
    mode = _mode(args)
    endpoint = f"{base}/live/advanced" if mode == "live" else f"{base}/task_post"

    key = _cache_key(base, task)
    cached = _cache_get(key)

    if getattr(args, "dry_run", False):
        _dry_run(op, endpoint, task, cached is not None, args)
        return {}, {"dry_run": True}

    if not getattr(args, "no_cache", False) and cached is not None:
        return cached["task"], {"from_cache": True, "cost": 0.0, "mode": "cache",
                                "endpoint": base}

    resp = client.post(endpoint, task)
    cost = resp.get("cost")

    if mode == "live":
        t = client.unwrap_task(resp)
        _cache_put(key, t, cost)
        return t, {"from_cache": False, "cost": cost, "mode": mode, "endpoint": base}

    code, msg, posted = client.task_status(resp)
    task_id = posted.get("id")
    if code not in (client.CREATED, client.OK) or not task_id:
        _die(f"task_post failed: {code} {msg}")

    if getattr(args, "async_", False):
        summary = task.get("keyword") or task.get("target") or ",".join(
            task.get("advertiser_ids") or [])
        _ledger_record(task_id, op, str(summary))
        print(json.dumps({
            "posted": True, "op": op, "task_id": task_id, "cost": cost,
            "note": ("task queued (not waiting). Retrieve when ready with: "
                     f"ads.py get {task_id}   ·   list ready tasks: ads.py ready"),
        }, indent=2, ensure_ascii=False))
        return {}, {"posted_only": True}

    sys.stderr.write(f"· task {task_id} posted to the {mode} queue, polling…\n")
    t = client.poll_advanced(
        base, task_id, max_wait=args.max_wait,
        on_wait=lambda w, c, m: sys.stderr.write(f"  … still {m.lower()} ({w}s)\n"))
    _cache_put(key, t, cost)
    return t, {"from_cache": False, "cost": cost, "mode": mode, "endpoint": base}


def _resolve_advertiser_ids(name: str, args) -> list[str]:
    """`ads --advertiser-for "<name>"` — look the brand up first, then keep the
    top ids by ad volume. Two billable calls; the stderr note says which
    accounts were picked so a wrong match is obvious rather than silent."""
    lookup = argparse.Namespace(
        keyword=name, location_code=args.location_code,
        location_name=args.location_name, location_coordinate=args.location_coordinate,
        queued=args.queued, priority=args.priority, async_=False,
        max_wait=args.max_wait, tag=None, no_cache=args.no_cache,
        dry_run=False, sort_by="ads",
    )
    task, _ = _fetch("advertisers", lookup)
    rows = _flatten_advertisers(_items(task))
    ided = [r for r in rows if r.get("advertiser_id")]
    ided.sort(key=lambda r: r.get("approx_ads_count") or 0, reverse=True)
    picked = ided[: args.max_advertisers]
    if not picked:
        _die(f"no advertiser accounts found for {name!r}. Try `advertisers "
             f"\"{name}\"` to see what came back, or use --target <domain>.")
    sys.stderr.write("· resolved advertisers: " + "; ".join(
        f"{r['title']} ({r['advertiser_id']}, ~{r.get('approx_ads_count')} ads)"
        for r in picked) + "\n")
    return [r["advertiser_id"] for r in picked]


def _run_op(op: str, args) -> None:
    if op == "ads":
        if args.advertiser_for:
            if args.dry_run:
                # A dry run must not spend anything, and resolving the brand is
                # itself a paid call — so describe the two-call plan instead.
                print(json.dumps({
                    "dry_run": True,
                    "plan": [f"advertisers {args.advertiser_for!r} → top "
                             f"{args.max_advertisers} advertiser_ids by ad volume",
                             "ads for those ids"],
                    "billing": (f"2 calls: ${_est_cost('advertisers', args)} + "
                                f"${_est_cost('ads', args)} ≈ "
                                f"${round(_est_cost('advertisers', args) + _est_cost('ads', args), 6)}"),
                    "note": "run without --dry-run to resolve and fetch",
                }, indent=2, ensure_ascii=False))
                return
            args.advertiser_ids = _resolve_advertiser_ids(args.advertiser_for, args)
        if not args.target and not args.advertiser_ids:
            _die("`ads` needs one of --target <domain>, --advertiser-ids <AR…>, "
                 "or --advertiser-for \"<brand name>\".")
        if args.target and args.advertiser_ids:
            _die("pass either --target or --advertiser-ids, not both "
                 "(the API treats them as alternative lookups).")
        if args.advertiser_ids and len(args.advertiser_ids) > 25:
            _die(f"the API accepts at most 25 advertiser ids ({len(args.advertiser_ids)} given).")

    task, meta = _fetch(op, args)
    if meta.get("dry_run") or meta.get("posted_only"):
        return
    _finish(op, task, meta, args)


def _finish(op: str, task: dict, meta: dict, args) -> None:
    if getattr(args, "raw", None):
        with open(args.raw, "w", encoding="utf-8") as fh:
            json.dump(task.get("result") or [], fh, indent=2)
        meta["raw_path"] = os.path.abspath(args.raw)
    meta.update({"operation": op,
                 **{k: v for k, v in _result_meta(task).items() if v is not None}})
    rows = _norm_rows(op, _items(task), args)

    # An advertiser lookup that finds no IDs almost always means a category
    # phrase was passed where a company name belongs — the API matches
    # advertiser names/domains, not topics. Say so at the point of confusion
    # rather than letting an empty table read as "this brand runs no ads".
    if op == "advertisers" and not any(r.get("advertiser_id") for r in rows):
        hint = ("no advertiser accounts matched. `advertisers` searches advertiser "
                "NAMES and domains, not topics — try the company name itself "
                "(e.g. 'salesforce'), or go straight to the creatives with "
                "`ads --target <domain>`.")
        meta["hint"] = hint
        sys.stderr.write("· " + hint + "\n")

    _emit(op, rows, meta, args)


def _run_get(args) -> None:
    op = args.type
    if not op:
        led = _ledger_load().get(args.id)
        if led:
            op = led["op"]
        else:
            op = "advertisers"
            sys.stderr.write("· unknown task type; assuming 'advertisers'. "
                             "Pass --type ads to override.\n")
    t = client.poll_advanced(_BASE[op], args.id, max_wait=args.max_wait,
                             on_wait=lambda w, c, m: sys.stderr.write(f"  … {m.lower()} ({w}s)\n"))
    _finish(op, t, {"from_cache": False, "cost": t.get("cost"), "endpoint": _BASE[op]}, args)


def _run_ready(args) -> None:
    """tasks_ready is per-endpoint on the SERP API, so check both and label
    each row — otherwise you'd have to remember which queue a task went into."""
    out = []
    for op, base in _BASE.items():
        try:
            t = client.unwrap_task(client.get(f"{base}/tasks_ready"))
        except RuntimeError as e:
            sys.stderr.write(f"· {op}: {e}\n")
            continue
        for r in (t.get("result") or []):
            out.append({"op": op, "id": r.get("id"), "tag": r.get("tag"),
                        "date_posted": r.get("date_posted"),
                        "endpoint_advanced": r.get("endpoint_advanced")})
    print(json.dumps(out[: args.limit] if args.limit else out, indent=2, ensure_ascii=False))


def _run_locations(args) -> None:
    t = client.unwrap_task(client.get(f"{_BASE['advertisers']}/locations"))
    items = t.get("result") or []
    needle = (args.contains or "").lower()
    if needle:
        items = [i for i in items if any(needle in str(v).lower() for v in i.values())]
    print(json.dumps(items[: args.limit] if args.limit else items, indent=2, ensure_ascii=False))


def _die(msg: str) -> None:
    sys.stderr.write("error: " + msg + "\n")
    sys.exit(1)


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------

def _add_location_args(p: argparse.ArgumentParser) -> None:
    loc = p.add_argument_group("location (default: United States)")
    loc.add_argument("--location-code", type=int, default=2840,
                     help="location code (default 2840 = United States; see `locations`)")
    loc.add_argument("--location-name",
                     help="e.g. 'United Kingdom' (overrides --location-code)")
    loc.add_argument("--location-coordinate",
                     help="'latitude,longitude' (overrides the other two)")


def _add_output_args(p: argparse.ArgumentParser, with_ids: bool = False) -> None:
    out = p.add_argument_group("output")
    out.add_argument("--format", choices=(["json", "table", "csv", "ids"] if with_ids
                                          else ["json", "table", "csv"]),
                     default="json",
                     help="stdout format (default json)"
                          + ("; 'ids' prints bare advertiser ids for chaining into `ads`"
                             if with_ids else ""))
    out.add_argument("--csv", metavar="PATH",
                     help="also write the FULL result set to a CSV file (ignores --limit)")
    out.add_argument("--raw", metavar="PATH",
                     help="dump the complete raw API result to a JSON file (nothing dropped)")
    out.add_argument("--limit", dest="limit_out", type=int, default=100,
                     help="cap rows printed to stdout (default 100; 0 = all). "
                          "--csv always gets everything.")


def _add_run_args(p: argparse.ArgumentParser) -> None:
    run = p.add_argument_group("run / cost control")
    run.add_argument("--queued", action="store_true",
                     help="use the Standard task queue (~1/3 the price of live, "
                          "but can lag ~30s+) instead of a live call")
    run.add_argument("--priority", choices=["standard", "high"], default="standard",
                     help="queue priority when --queued: 'high' is 2x cost, ~1 min (default standard)")
    run.add_argument("--async", dest="async_", action="store_true",
                     help="queue the task and print its id WITHOUT waiting (implies --queued)")
    run.add_argument("--max-wait", type=float, default=300.0,
                     help="seconds to poll a queued task before giving up (default 300; "
                          "the task stays retrievable ~30 days)")
    run.add_argument("--tag", help="user label echoed back on the task (max 255 chars)")
    run.add_argument("--no-cache", action="store_true", help="force a fresh paid call")
    run.add_argument("--dry-run", action="store_true",
                     help="print the exact request + cost estimate without calling (free)")


def main(argv=None) -> None:
    parser = argparse.ArgumentParser(
        prog="ads.py",
        description="DataForSEO Google Ads Transparency — who advertises, and what they run.")
    sub = parser.add_subparsers(dest="op", required=True)

    # advertisers
    pa = sub.add_parser("advertisers",
                        help="who runs Google ads for a brand/term (gives you advertiser_ids)")
    pa.add_argument("keyword",
                    help="ADVERTISER NAME or domain, e.g. 'salesforce' (up to 700 chars). "
                         "This matches advertiser names, not topics — 'crm software' "
                         "returns nothing useful. To map a market, look up each "
                         "competitor by name or use `ads --target <domain>`.")
    pa.add_argument("--sort-by", choices=["rank", "ads"], default="rank",
                    help="'rank' keeps Google's relevance order (default); "
                         "'ads' puts the biggest ad libraries first")
    _add_location_args(pa)
    _add_output_args(pa, with_ids=True)
    _add_run_args(pa)

    # ads
    pd = sub.add_parser("ads", help="the creatives an advertiser is running")
    who = pd.add_argument_group("who to look up (pick one)")
    who.add_argument("--target", help="domain, e.g. nike.com (URLs are accepted and trimmed)")
    who.add_argument("--advertiser-ids", nargs="+", metavar="AR…",
                     help="up to 25 advertiser ids from `advertisers`")
    who.add_argument("--advertiser-for", metavar="NAME",
                     help="brand name — resolves advertiser ids first, then pulls their ads "
                          "(TWO billable calls)")
    who.add_argument("--max-advertisers", type=int, default=5,
                     help="with --advertiser-for, how many accounts to include, "
                          "biggest first (default 5, max 25)")
    filt = pd.add_argument_group("filters")
    filt.add_argument("--depth", type=int, default=40,
                      help="creatives to return (default 40; max 120 live, 700 queued). "
                           "BILLS PER 40 — depth 120 costs 3x.")
    filt.add_argument("--ad-format", choices=_AD_FORMATS, default="all", dest="ad_format",
                      help="creative type: text, image, video (default all)")
    filt.add_argument("--platform", choices=_PLATFORMS, default="all",
                      help="surface the ad ran on. NOTE: in testing this did not "
                           "actually narrow results — prefer --ad-format")
    filt.add_argument("--since", metavar="YYYY-MM-DD",
                      help="only ads shown on/after this date (min 2018-05-31)")
    filt.add_argument("--until", metavar="YYYY-MM-DD", help="only ads shown on/before this date")
    filt.add_argument("--active-days", type=int, default=_ACTIVE_WINDOW_DAYS,
                      help=f"treat a creative as still running if last_shown is within "
                           f"this many days (default {_ACTIVE_WINDOW_DAYS})")
    pd.add_argument("--download-creatives", metavar="DIR",
                    help="THE way to get ad copy. Downloads each ad's rendered PNG "
                         "(headline + description + display URL) into DIR as "
                         "<creative_id>.png with an index.csv. The API returns no "
                         "copy text — `title` is the advertiser name — so open these "
                         "images to read what the ads actually say. Free (no API calls).")
    _add_location_args(pd)
    _add_output_args(pd)
    _add_run_args(pd)

    # get
    pg = sub.add_parser("get", help="fetch a previously queued task by id (polls until ready)")
    pg.add_argument("id", help="task UUID from an --async post or `ready`")
    pg.add_argument("--type", choices=list(_BASE),
                    help="which endpoint the task went to (auto-detected from the ledger)")
    pg.add_argument("--max-wait", type=float, default=300.0,
                    help="seconds to poll (default 300; 0 = single ready/not-ready check)")
    pg.add_argument("--active-days", type=int, default=_ACTIVE_WINDOW_DAYS)
    pg.add_argument("--sort-by", choices=["rank", "ads"], default="rank")
    _add_output_args(pg)

    # ready
    pr = sub.add_parser("ready", help="list finished queued tasks awaiting collection")
    pr.add_argument("--limit", type=int, default=100)

    # locations (free)
    pl = sub.add_parser("locations", help="list supported locations (free)")
    pl.add_argument("--contains", help="filter by substring, e.g. 'United Kingdom'")
    pl.add_argument("--limit", type=int, default=100)

    args = parser.parse_args(argv)
    if getattr(args, "limit_out", None) == 0:
        args.limit_out = None
    if getattr(args, "async_", False):
        args.queued = True
    if getattr(args, "max_advertisers", 0) and args.max_advertisers > 25:
        args.max_advertisers = 25

    try:
        if args.op in ("advertisers", "ads"):
            _run_op(args.op, args)
        elif args.op == "get":
            _run_get(args)
        elif args.op == "ready":
            _run_ready(args)
        elif args.op == "locations":
            _run_locations(args)
        else:
            _die(f"unknown operation {args.op!r}")
    except (RuntimeError, TimeoutError) as e:
        _die(str(e))


if __name__ == "__main__":
    main()
