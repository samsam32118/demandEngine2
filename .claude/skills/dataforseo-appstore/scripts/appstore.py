#!/usr/bin/env python3
"""DataForSEO Apple App Data — App Store research, one CLI.

Task-based ops (POST a task, poll until ready, print results):

  search    app_data/apple/app_searches   apps ranking for a keyword (ASO / competitive intel)
  info      app_data/apple/app_info        full details for one app (by numeric id or App Store URL)
  reviews   app_data/apple/app_reviews     user reviews for one app (voice-of-customer mining)
  list      app_data/apple/app_list        top-chart apps by collection + category

Live op (instant, no polling):

  listings  app_data/apple/app_listings/search/live   search DataForSEO's App Store DB
            by title / description / category / numeric filters

Detached retrieval (the Standard queue can lag; --async posts without waiting):

  get ID    fetch a previously-posted task's advanced result (polls until ready)
  ready     list finished tasks awaiting collection (tasks_ready)

Free reference lookups:

  categories / locations / languages

Each posted task is ONE billable request; Standard queue is cheap but can lag
(usually seconds, up to ~45 min), --priority high is 2x cost but ~1 min. `depth`
multiplies cost: searches/list bill per 100 items, reviews per 25. Results are
cached on disk keyed by the request, so re-running an identical query is free.
Defaults are tuned for the James ICP: US (location_code 2840), English (en).
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import math
import os
import re
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import client  # noqa: E402

_CACHE_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".cache")
_LEDGER = os.path.join(_CACHE_DIR, "tasks_ledger.json")

# Endpoint stems for the task-based ops. `get`/`ready` map back through these.
_BASE = {
    "search": "app_data/apple/app_searches",
    "info": "app_data/apple/app_info",
    "reviews": "app_data/apple/app_reviews",
    "list": "app_data/apple/app_list",
}
_LIVE_LISTINGS = "app_data/apple/app_listings/search/live"

# Billing granularity per op: (unit_size, human label). depth/unit → billable units.
_BILL_UNIT = {"search": (100, "100 items"), "list": (100, "100 items"),
              "reviews": (25, "25 reviews"), "info": (1, "app")}

# Columns shown in table/CSV output, per op. --raw keeps everything.
_APP_COLS = ["rank_absolute", "app_id", "title", "developer", "rating",
             "reviews_count", "price", "url"]
_REVIEW_COLS = ["rating", "title", "review_text", "profile_name", "version", "timestamp"]
_LISTINGS_COLS = ["app_id", "title", "developer", "rating", "reviews_count",
                  "price", "minimum_os_version", "url"]
# app_info is one rich record — shown as a key/value block, not a wide table.
_INFO_FIELDS = ["title", "app_id", "url", "developer", "developer_id", "main_category",
                "categories", "rating", "reviews_count", "price", "size", "version",
                "minimum_os_version", "last_update_date", "advisories", "languages",
                "description", "similar_apps", "more_apps_by_developer", "images"]

_COLLECTIONS = ["top_free_ios", "top_paid_ios", "top_grossing_ios",
                "new_ios", "new_free_ios", "new_paid_ios"]


# --------------------------------------------------------------------------
# App-id parsing (accept a bare id OR an App Store URL)
# --------------------------------------------------------------------------

def _parse_app_id(raw: str) -> str:
    """Apple app ids are the digits after 'id' in an App Store URL. Accept
    either the bare number ("835599320") or a full URL and pull the id out."""
    raw = raw.strip()
    if raw.isdigit():
        return raw
    m = re.search(r"id(\d{3,})", raw)
    if m:
        return m.group(1)
    m = re.search(r"(\d{5,})", raw)
    if m:
        return m.group(1)
    _die(f"could not find a numeric app id in {raw!r} "
         "(pass e.g. 835599320 or an apps.apple.com/...id835599320 URL)")


# --------------------------------------------------------------------------
# Task building
# --------------------------------------------------------------------------

def _add_locale(task: dict, args) -> None:
    """Location + language, shared by the task-based ops (listings is US-only)."""
    if getattr(args, "location_name", None):
        task["location_name"] = args.location_name
    elif getattr(args, "location_code", None) is not None:
        task["location_code"] = args.location_code
    if getattr(args, "language_name", None):
        task["language_name"] = args.language_name
    elif getattr(args, "language_code", None):
        task["language_code"] = args.language_code


def _priority(args) -> int:
    return 2 if getattr(args, "priority", "standard") == "high" else 1


def _build_task(op: str, args) -> tuple[str, dict]:
    """Return (endpoint_base, task-dict) for a task-based op."""
    if op == "search":
        task: dict = {"keyword": args.keyword, "depth": args.depth}
    elif op == "info":
        task = {"app_id": _parse_app_id(args.app_id)}
    elif op == "reviews":
        task = {"app_id": _parse_app_id(args.app_id), "depth": args.depth,
                "sort_by": args.sort_by}
    elif op == "list":
        task = {"app_collection": args.collection, "depth": args.depth}
        if args.category:
            task["app_category"] = args.category
    else:
        _die(f"unknown op {op!r}")
    _add_locale(task, args)
    task["priority"] = _priority(args)
    if getattr(args, "tag", None):
        task["tag"] = args.tag
    return _BASE[op], task


def _build_listings(args) -> tuple[str, dict]:
    task: dict = {"limit": args.limit, "offset": args.offset}
    if args.title:
        task["title"] = args.title
    if args.description:
        task["description"] = args.description
    if args.category:
        task["categories"] = args.category  # repeatable -> list
    filters = _listings_filters(args)
    if filters:
        task["filters"] = filters
    if args.order_by:
        task["order_by"] = [_prefix_item(r) for r in args.order_by]
    if getattr(args, "tag", None):
        task["tag"] = args.tag
    return _LIVE_LISTINGS, task


def _prefix_item(rule: str) -> str:
    """Listings sort/filter fields live under the nested `item` object, so
    DataForSEO requires an `item.` prefix (e.g. `item.rating.value,desc`).
    Add it when the caller left it off; leave already-prefixed rules alone."""
    rule = rule.strip()
    return rule if rule.startswith("item.") else "item." + rule


def _listings_filters(args):
    """Build the DataForSEO `filters` array from convenience flags, or accept a
    raw JSON array via --filters-json. Multiple conditions are AND-joined.
    Field names are `item.`-prefixed because listings nest the app under `item`."""
    if args.filters_json:
        try:
            return json.loads(args.filters_json)
        except json.JSONDecodeError as e:
            _die(f"--filters-json is not valid JSON: {e}")
    conds = []
    if args.min_rating is not None:
        conds.append(["item.rating.value", ">=", args.min_rating])
    if args.min_reviews is not None:
        conds.append(["item.rating.votes_count", ">=", args.min_reviews])
    out = []
    for i, c in enumerate(conds):
        if i:
            out.append("and")
        out.append(c)
    return out


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
        "app_id": first.get("app_id"),
        "se_results_count": first.get("se_results_count"),
        "total_count": first.get("total_count"),
        "items_count": first.get("items_count"),
        "datetime": first.get("datetime"),
    }


def _fmt_price(item: dict) -> str:
    if item.get("is_free") is True:
        return "Free"
    p = item.get("price")
    if isinstance(p, dict):
        cur = p.get("current")
        if cur in (0, 0.0):
            return "Free"
        if cur is None:
            return _fmt(p.get("displayed_price"))
        return f"{cur} {p.get('currency') or ''}".strip()
    return _fmt(p)


def _flatten_app(item: dict) -> dict:
    """Flatten an app item (search / list / listings) into scalar columns."""
    r = dict(item)
    rating = item.get("rating")
    if isinstance(rating, dict):
        r["rating"] = rating.get("value")
        if item.get("reviews_count") is None:
            r["reviews_count"] = rating.get("votes_count")
    dev = item.get("developer")
    if isinstance(dev, dict):
        r["developer"] = dev.get("name") or dev.get("title")
    r["price"] = _fmt_price(item)
    return r


def _flatten_review(item: dict) -> dict:
    r = dict(item)
    rating = item.get("rating")
    if isinstance(rating, dict):
        r["rating"] = rating.get("value")
    # The reviewer name is nested under user_profile (Apple obfuscates it).
    prof = item.get("user_profile")
    if isinstance(prof, dict):
        r["profile_name"] = prof.get("profile_name")
    return r


def _norm_rows(op: str, items: list[dict]) -> list[dict]:
    if op == "reviews":
        return [_flatten_review(i) for i in items]
    if op == "listings":
        # Live listings wrap the actual app under a nested `item` key.
        return [_flatten_app((i.get("item") if isinstance(i.get("item"), dict) else i))
                for i in items]
    return [_flatten_app(i) for i in items]


def _cols_for(op: str) -> list[str]:
    if op == "reviews":
        return list(_REVIEW_COLS)
    if op == "listings":
        return list(_LISTINGS_COLS)
    return list(_APP_COLS)


# --------------------------------------------------------------------------
# Caching + async ledger
# --------------------------------------------------------------------------

# Fields that don't change the *result*, only how/when it's run — excluded from
# the cache key so 'standard' and 'high' priority share one cached answer.
_VOLATILE = {"priority", "tag", "postback_url", "postback_data", "pingback_url"}


def _cache_key(endpoint: str, task: dict) -> str:
    stable = {k: v for k, v in task.items() if k not in _VOLATILE}
    blob = json.dumps({"endpoint": endpoint, "task": stable}, sort_keys=True)
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


def _ledger_record(task_id: str, op: str, base: str, summary: str) -> None:
    os.makedirs(_CACHE_DIR, exist_ok=True)
    led = _ledger_load()
    led[task_id] = {"op": op, "base": base, "summary": summary,
                    "posted_at": int(time.time())}
    with open(_LEDGER, "w", encoding="utf-8") as fh:
        json.dump(led, fh, indent=2)


# --------------------------------------------------------------------------
# Output
# --------------------------------------------------------------------------

def _fmt(v) -> str:
    return "" if v is None else str(v)


def _cell(v, width: int | None) -> str:
    """One table cell: strip newlines, optionally truncate for readability."""
    s = _fmt(v).replace("\n", " ").replace("\r", " ").replace("|", "\\|")
    if width and len(s) > width:
        s = s[: width - 1] + "…"
    return s


def _markdown_table(rows: list[dict], cols: list[str], width: int | None = 80) -> str:
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
    cols = _cols_for(op)

    # Drop columns that are empty for EVERY row so the view stays readable:
    # app_searches / app_list don't return `developer`, so that column would
    # otherwise be pure noise there (it IS populated for listings).
    if rows:
        cols = [c for c in cols if any(r.get(c) not in (None, "") for r in rows)]

    # CSV file always gets the FULL result set — nothing lost to --limit.
    if getattr(args, "csv", None):
        with open(args.csv, "w", encoding="utf-8", newline="") as fh:
            fh.write(_csv_string(rows, cols))
        meta["csv_path"] = os.path.abspath(args.csv)

    limit_out = getattr(args, "limit_out", None)
    shown = rows if limit_out is None else rows[: limit_out]
    meta["total_returned"] = len(rows)
    meta["shown"] = len(shown)
    if limit_out is not None and len(rows) > limit_out:
        meta["truncated"] = True

    if args.format == "table":
        print(_markdown_table(shown, cols))
        print(f"\n_{meta['shown']} of {meta['total_returned']} rows"
              f" · cost ${meta.get('cost')}"
              + (f" · full CSV: {meta['csv_path']}" if meta.get("csv_path") else "")
              + (" · cached (free)" if meta.get("from_cache") else "") + "_")
    elif args.format == "csv":
        sys.stdout.write(_csv_string(shown, cols))
    else:  # json
        print(json.dumps({"meta": meta, "items": shown}, indent=2, ensure_ascii=False))


def _emit_info(item: dict, meta: dict, args) -> None:
    """app_info is a single rich record — render a readable key/value block in
    table mode, full JSON otherwise. Arrays collapse to counts + a preview."""
    if getattr(args, "raw", None):
        pass  # raw already dumped upstream
    if args.format == "json":
        print(json.dumps({"meta": meta, "app": item}, indent=2, ensure_ascii=False))
        return
    if args.format == "csv":
        flat = _flatten_app(item)
        cols = ["app_id", "title", "developer", "rating", "reviews_count",
                "price", "version", "size", "minimum_os_version", "last_update_date"]
        sys.stdout.write(_csv_string([flat], cols))
        return

    flat = _flatten_app(item)
    lines = []
    for f in _INFO_FIELDS:
        v = flat.get(f)
        if f in ("similar_apps", "more_apps_by_developer", "images", "categories",
                 "languages", "advisories"):
            if isinstance(v, list):
                preview = ", ".join(str(x.get("title") if isinstance(x, dict) else x)
                                    for x in v[:5])
                v = f"{len(v)} [{preview}{'…' if len(v) > 5 else ''}]" if v else "0"
        elif f == "description":
            v = _cell(v, 400)
        else:
            v = _fmt(v)
        lines.append(f"{f:>22}: {v}")
    print("\n".join(lines))
    print(f"\n_cost ${meta.get('cost')}"
          + (" · cached (free)" if meta.get("from_cache") else "") + "_")


# --------------------------------------------------------------------------
# Runners
# --------------------------------------------------------------------------

def _est_units(op: str, args) -> int:
    unit = _BILL_UNIT.get(op, (1, ""))[0]
    depth = getattr(args, "depth", 1) or 1
    return max(1, math.ceil(depth / unit))


def _dry_run(op: str, endpoint: str, task: dict, is_cached: bool, args) -> None:
    note = ("already cached — running this is FREE" if is_cached else
            "not cached — running this is 1 billable request")
    out = {"dry_run": True, "endpoint": endpoint, "request_body": [task],
           "billable": not is_cached}
    if op in _BILL_UNIT:
        units = _est_units(op, args)
        out["billing"] = (f"~{units}× ({units} × {_BILL_UNIT[op][1]})"
                          f"{' at 2× high priority' if _priority(args) == 2 else ''}")
    out["note"] = note
    print(json.dumps(out, indent=2, ensure_ascii=False))


def _run_task(op: str, args) -> None:
    base, task = _build_task(op, args)
    endpoint = f"{base}/task_post"
    key = _cache_key(base, task)
    cached = _cache_get(key)

    if getattr(args, "dry_run", False):
        _dry_run(op, endpoint, task, cached is not None, args)
        return

    from_cache = False
    cost = None
    if not args.no_cache and cached is not None:
        t, from_cache, cost = cached["task"], True, 0.0
    else:
        resp = client.post(endpoint, task)
        code, msg, posted = client.task_status(resp)
        task_id = posted.get("id")
        if code not in (client.CREATED, client.OK) or not task_id:
            _die(f"task_post failed: {code} {msg}")
        cost = resp.get("cost")

        if getattr(args, "async_", False):
            summary = task.get("keyword") or task.get("app_id") or task.get("app_collection") or ""
            _ledger_record(task_id, op, base, str(summary))
            print(json.dumps({
                "posted": True, "op": op, "task_id": task_id, "cost": cost,
                "note": ("task queued (not waiting). Retrieve when ready with: "
                         f"appstore.py get {task_id}   ·   list ready tasks: appstore.py ready"),
            }, indent=2, ensure_ascii=False))
            return

        sys.stderr.write(f"· task {task_id} posted, polling for results…\n")
        t = client.poll_advanced(
            base, task_id, max_wait=args.max_wait,
            on_wait=lambda w, c, m: sys.stderr.write(f"  … still {m.lower()} ({w}s)\n"))
        _cache_put(key, t, cost)

    _finish(op, t, {"from_cache": from_cache, "cost": cost, "endpoint": base}, args)


def _run_listings(args) -> None:
    endpoint, task = _build_listings(args)
    key = _cache_key(endpoint, task)
    cached = _cache_get(key)

    if getattr(args, "dry_run", False):
        _dry_run("listings", endpoint, task, cached is not None, args)
        return

    from_cache = False
    if not args.no_cache and cached is not None:
        t, from_cache, cost = cached["task"], True, 0.0
    else:
        resp = client.post(endpoint, task)
        t = client.unwrap_task(resp)
        cost = resp.get("cost")
        _cache_put(key, t, cost)

    _finish("listings", t, {"from_cache": from_cache, "cost": cost, "endpoint": endpoint}, args)


def _run_get(args) -> None:
    op, base = args.type, None
    led = _ledger_load().get(args.id)
    if op:
        base = _BASE[op]
    elif led:
        op, base = led["op"], led["base"]
    else:
        op, base = "search", _BASE["search"]
        sys.stderr.write("· unknown task type; assuming 'search'. Pass --type to override.\n")
    t = client.poll_advanced(base, args.id, max_wait=args.max_wait,
                             on_wait=lambda w, c, m: sys.stderr.write(f"  … {m.lower()} ({w}s)\n"))
    _finish(op, t, {"from_cache": False, "cost": t.get("cost"), "endpoint": base}, args)


def _finish(op: str, task: dict, meta: dict, args) -> None:
    if getattr(args, "raw", None):
        with open(args.raw, "w", encoding="utf-8") as fh:
            json.dump(task.get("result") or [], fh, indent=2)
        meta["raw_path"] = os.path.abspath(args.raw)
    meta.update({"operation": op, **{k: v for k, v in _result_meta(task).items() if v is not None}})

    if op == "info":
        items = _items(task)
        _emit_info(items[0] if items else {}, meta, args)
        return
    _emit(op, _norm_rows(op, _items(task)), meta, args)


def _run_ready(args) -> None:
    # Generic app_data tasks_ready covers every apple endpoint at once.
    resp = client.get("app_data/tasks_ready")
    t = client.unwrap_task(resp)
    rows = t.get("result") or []
    slim = [{"id": r.get("id"), "tag": r.get("tag"), "date_posted": r.get("date_posted"),
             "endpoint_advanced": r.get("endpoint_advanced")} for r in rows]
    print(json.dumps(slim[: args.limit] if args.limit else slim, indent=2, ensure_ascii=False))


def _run_lookup(op: str, args) -> None:
    resp = client.get(f"app_data/apple/{op}")
    t = client.unwrap_task(resp)
    items = t.get("result") or []
    needle = (args.contains or "").lower()

    # `categories` returns ONE object holding a flat list of category ids;
    # `locations`/`languages` return a list of {code, name} objects. Flatten
    # categories so --contains filters the ids themselves, not the whole blob.
    if op == "categories":
        cats = items[0].get("categories") if items else []
        cats = cats or []
        if needle:
            cats = [c for c in cats if needle in str(c).lower()]
        print(json.dumps(cats[: args.limit] if args.limit else cats, indent=2, ensure_ascii=False))
        return

    if needle:
        items = [i for i in items if any(needle in str(v).lower() for v in i.values())]
    print(json.dumps(items[: args.limit] if args.limit else items, indent=2, ensure_ascii=False))


def _die(msg: str) -> None:
    sys.stderr.write("error: " + msg + "\n")
    sys.exit(1)


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------

def _add_locale_args(p: argparse.ArgumentParser) -> None:
    loc = p.add_argument_group("location / language (defaults: US, English)")
    loc.add_argument("--location-code", type=int, default=2840,
                     help="location code (default 2840 = United States)")
    loc.add_argument("--location-name",
                     help="e.g. 'United Kingdom' (overrides --location-code)")
    loc.add_argument("--language-code", default="en", help="e.g. en, de, fr (default en)")
    loc.add_argument("--language-name", help="e.g. 'English' (overrides --language-code)")


def _add_output_args(p: argparse.ArgumentParser, with_limit: bool = True) -> None:
    out = p.add_argument_group("output")
    out.add_argument("--format", choices=["json", "table", "csv"], default="json",
                     help="stdout format (default json)")
    out.add_argument("--csv", metavar="PATH",
                     help="also write the FULL result set to a CSV file (ignores --limit)")
    out.add_argument("--raw", metavar="PATH",
                     help="dump the complete raw API result to a JSON file (nothing dropped)")
    # listings owns --limit as its API page size, so it skips this stdout cap
    # (it already bounds the fetch itself) — everything it fetched is shown.
    if with_limit:
        out.add_argument("--limit", dest="limit_out", type=int, default=100,
                         help="cap rows printed to stdout (default 100; 0 = all). --csv always gets everything.")


def _add_run_args(p: argparse.ArgumentParser) -> None:
    """Shared knobs for the task-based ops."""
    _add_locale_args(p)
    _add_output_args(p)
    run = p.add_argument_group("run / cost control")
    run.add_argument("--priority", choices=["standard", "high"], default="standard",
                     help="'high' is 2x cost but ~1 min; 'standard' is cheap but can lag (default)")
    run.add_argument("--async", dest="async_", action="store_true",
                     help="POST the task and print its id WITHOUT waiting (retrieve later with `get`)")
    run.add_argument("--max-wait", type=float, default=300.0,
                     help="seconds to poll before giving up (default 300; the task stays retrievable ~3 days)")
    run.add_argument("--tag", help="user label echoed back on the task (max 255 chars)")
    run.add_argument("--no-cache", action="store_true", help="force a fresh paid call")
    run.add_argument("--dry-run", action="store_true",
                     help="print the exact request + billing estimate without calling (free)")


def _post_parse(args) -> None:
    if getattr(args, "limit_out", None) == 0:
        args.limit_out = None


def main(argv=None) -> None:
    parser = argparse.ArgumentParser(
        prog="appstore.py", description="DataForSEO Apple App Data (App Store research).")
    sub = parser.add_subparsers(dest="op", required=True)

    # search
    ps = sub.add_parser("search", help="apps ranking for a keyword (ASO / competitive)")
    ps.add_argument("keyword", help="search phrase, e.g. 'sales coach'")
    ps.add_argument("--depth", type=int, default=100,
                    help="apps to return, 1-700 (default 100; bills per 100)")
    _add_run_args(ps)

    # info
    pi = sub.add_parser("info", help="full details for one app (id or App Store URL)")
    pi.add_argument("app_id", help="numeric id (835599320) or apps.apple.com/...id835599320 URL")
    _add_run_args(pi)

    # reviews
    pr = sub.add_parser("reviews", help="user reviews for one app")
    pr.add_argument("app_id", help="numeric id or App Store URL")
    pr.add_argument("--depth", type=int, default=100,
                    help="reviews to return, 25-500 (default 100; bills per 25)")
    pr.add_argument("--sort-by", choices=["most_helpful", "most_recent"],
                    default="most_helpful", help="review ordering (default most_helpful)")
    _add_run_args(pr)

    # list
    pl = sub.add_parser("list", help="top-chart apps by collection + category")
    pl.add_argument("--collection", choices=_COLLECTIONS, required=True,
                    help="chart type, e.g. top_free_ios")
    pl.add_argument("--category", help="category id (see `categories`), e.g. business")
    pl.add_argument("--depth", type=int, default=100,
                    help="apps to return, 1-1000 (default 100; bills per 100)")
    _add_run_args(pl)

    # listings (LIVE)
    plg = sub.add_parser("listings", help="search DataForSEO's App Store DB (live, US-only)")
    plg.add_argument("--title", help="keywords in the app title (<=200 chars)")
    plg.add_argument("--description", help="keywords in the app description (<=200 chars)")
    plg.add_argument("--category", action="append",
                     help="category id to filter by (repeatable, up to 10)")
    plg.add_argument("--min-rating", type=float, help="only apps with rating >= this (0-5)")
    plg.add_argument("--min-reviews", type=int, help="only apps with >= this many ratings")
    plg.add_argument("--order-by", action="append",
                     help="sort rule, e.g. 'rating.value,desc' (repeatable, up to 3)")
    plg.add_argument("--filters-json",
                     help="raw DataForSEO filters array as JSON (overrides --min-*)")
    plg.add_argument("--limit", type=int, default=100, help="max results, 1-1000 (default 100)")
    plg.add_argument("--offset", type=int, default=0, help="results offset (default 0)")
    plg.add_argument("--tag")
    plg.add_argument("--no-cache", action="store_true", help="force a fresh paid call")
    plg.add_argument("--dry-run", action="store_true",
                     help="print the request without calling (free)")
    _add_output_args(plg, with_limit=False)

    # get (retrieve a posted task)
    pg = sub.add_parser("get", help="fetch a previously-posted task by id (polls until ready)")
    pg.add_argument("id", help="task UUID from an --async post or `ready`")
    pg.add_argument("--type", choices=list(_BASE),
                    help="which endpoint the task was posted to (auto-detected from the ledger if omitted)")
    pg.add_argument("--max-wait", type=float, default=300.0,
                    help="seconds to poll (default 300; use 0 for a single ready/not-ready check)")
    _add_output_args(pg)

    # ready (list collectable tasks)
    prd = sub.add_parser("ready", help="list finished tasks awaiting collection")
    prd.add_argument("--limit", type=int, default=100)

    # reference lookups (free)
    for name, ex in (("categories", "business"), ("locations", "United Kingdom"),
                     ("languages", "English")):
        pref = sub.add_parser(name, help=f"list App Store {name} (free)")
        pref.add_argument("--contains", help=f"filter by substring, e.g. '{ex}'")
        pref.add_argument("--limit", type=int, default=100)

    args = parser.parse_args(argv)

    try:
        if args.op in ("search", "info", "reviews", "list"):
            _post_parse(args)
            _run_task(args.op, args)
        elif args.op == "listings":
            _post_parse(args)
            _run_listings(args)
        elif args.op == "get":
            _post_parse(args)
            _run_get(args)
        elif args.op == "ready":
            _run_ready(args)
        elif args.op in ("categories", "locations", "languages"):
            _run_lookup(args.op, args)
        else:
            _die(f"unknown operation {args.op!r}")
    except (RuntimeError, TimeoutError) as e:
        _die(str(e))


if __name__ == "__main__":
    main()
