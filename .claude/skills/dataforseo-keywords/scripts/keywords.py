#!/usr/bin/env python3
"""DataForSEO Google Ads Keywords Data — Live endpoints, one CLI.

Three keyword operations plus two lookups:

  for-site      keywords_data/google_ads/keywords_for_site/live
                keywords a domain/page already ranks or bids for
  for-keywords  keywords_data/google_ads/keywords_for_keywords/live
                keyword ideas expanded from up to 20 seed terms
  ad-traffic    keywords_data/google_ads/ad_traffic_by_keywords/live
                forecast clicks / CPC / spend for a bid + match type
  locations     keywords_data/google_ads/locations   (find a location_code)
  languages     keywords_data/google_ads/languages   (find a language_code)

Each keyword call is one billable DataForSEO request (~$0.05-0.10). Live
endpoints are capped at 12 requests/minute per account. Results are cached
on disk keyed by the full request, so re-running an identical query is free —
pass --no-cache to force a fresh paid call.

Defaults are tuned for the James ICP (US market, English): location_code
2840, language_code en. Override per call or pass --worldwide.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import client  # noqa: E402

_CACHE_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".cache")

# Columns shown in table/CSV output, per operation.
_KW_COLS = [
    "keyword", "search_volume", "competition", "competition_index",
    "cpc", "low_top_of_page_bid", "high_top_of_page_bid",
]
# search-volume returns the same metrics plus a `spell` correction field.
_SV_COLS = ["keyword", "spell"] + _KW_COLS[1:]
_TRAFFIC_COLS = ["keyword", "clicks", "average_cpc", "cost", "match", "bid"]

# Operations that return per-keyword metric rows (as opposed to the
# campaign-level ad-traffic aggregate). These carry monthly_searches trends.
_METRIC_OPS = {"for-site", "for-keywords", "search-volume"}
# Columns that are meaningful only sometimes; drop them when every row is
# null so the table/CSV stays readable (ad-traffic keyword, sv spell).
_DROP_IF_ALL_NULL = {"keyword", "spell"}


def _cols_for(op: str) -> list[str]:
    if op == "ad-traffic":
        return list(_TRAFFIC_COLS)
    if op == "search-volume":
        return list(_SV_COLS)
    return list(_KW_COLS)


# --------------------------------------------------------------------------
# Task building
# --------------------------------------------------------------------------

def _add_common(task: dict, args) -> None:
    """Location, language, sort, dates, tag — shared by the keyword ops."""
    if getattr(args, "worldwide", False):
        pass  # omit location entirely -> worldwide results
    elif getattr(args, "location_name", None):
        task["location_name"] = args.location_name
    elif getattr(args, "location_code", None) is not None:
        task["location_code"] = args.location_code

    if getattr(args, "language_name", None):
        task["language_name"] = args.language_name
    elif getattr(args, "language_code", None):
        task["language_code"] = args.language_code

    if getattr(args, "sort_by", None):
        task["sort_by"] = args.sort_by
    if getattr(args, "search_partners", False):
        task["search_partners"] = True
    if getattr(args, "date_from", None):
        task["date_from"] = args.date_from
    if getattr(args, "date_to", None):
        task["date_to"] = args.date_to
    if getattr(args, "tag", None):
        task["tag"] = args.tag


def _build_task(op: str, args) -> tuple[str, dict]:
    """Return (endpoint, task-dict) for the given operation."""
    if op == "for-site":
        task: dict = {"target": args.target, "target_type": args.target_type}
        _add_common(task, args)
        if args.include_adult:
            task["include_adult_keywords"] = True
        return "keywords_data/google_ads/keywords_for_site/live", task

    if op == "for-keywords":
        kws = _clean_keywords(args.keywords)
        if not 1 <= len(kws) <= 20:
            _die("for-keywords takes 1-20 seed keywords (Google Ads limit).")
        task = {"keywords": kws}
        _add_common(task, args)
        if args.include_adult:
            task["include_adult_keywords"] = True
        return "keywords_data/google_ads/keywords_for_keywords/live", task

    if op == "search-volume":
        kws = _clean_keywords(args.keywords)
        if not 1 <= len(kws) <= 1000:
            _die("search-volume takes 1-1000 keywords.")
        task = {"keywords": kws}
        _add_common(task, args)
        if args.include_adult:
            task["include_adult_keywords"] = True
        return "keywords_data/google_ads/search_volume/live", task

    if op == "ad-traffic":
        kws = _clean_keywords(args.keywords)
        if not 1 <= len(kws) <= 1000:
            _die("ad-traffic takes 1-1000 keywords.")
        task = {"keywords": kws, "bid": args.bid, "match": args.match}
        _add_common(task, args)
        if args.date_interval and not (args.date_from and args.date_to):
            task["date_interval"] = args.date_interval
        return "keywords_data/google_ads/ad_traffic_by_keywords/live", task

    _die(f"unknown operation {op!r}")


def _clean_keywords(raw: list[str]) -> list[str]:
    """Lowercase, strip, drop blanks/dupes. Google lowercases anyway."""
    seen: set[str] = set()
    out: list[str] = []
    for k in raw:
        k = k.strip().lower()
        if k and k not in seen:
            seen.add(k)
            out.append(k)
    return out


# --------------------------------------------------------------------------
# Response normalization
# --------------------------------------------------------------------------

def _norm_rows(op: str, results: list[dict]) -> list[dict]:
    cols = _cols_for(op)
    rows = []
    for r in results or []:
        row = {c: r.get(c) for c in cols}
        if op in _METRIC_OPS:
            # Keep the full 12-month trend — we paid for it, don't discard it.
            row["monthly_searches"] = r.get("monthly_searches")
        rows.append(row)
    return rows


def _trend_str(monthly: list[dict] | None) -> str:
    """Compact the monthly_searches trend into one CSV/table-safe cell."""
    if not monthly:
        return ""
    return ";".join(
        f"{m.get('year')}-{int(m.get('month') or 0):02d}={m.get('search_volume')}"
        for m in monthly
    )


# --------------------------------------------------------------------------
# Caching
# --------------------------------------------------------------------------

def _cache_key(endpoint: str, task: dict) -> str:
    blob = json.dumps({"endpoint": endpoint, "task": task}, sort_keys=True)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def _cache_get(key: str):
    path = os.path.join(_CACHE_DIR, key + ".json")
    if os.path.exists(path):
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    return None


def _cache_put(key: str, response: dict) -> None:
    os.makedirs(_CACHE_DIR, exist_ok=True)
    with open(os.path.join(_CACHE_DIR, key + ".json"), "w", encoding="utf-8") as fh:
        json.dump(response, fh)


# --------------------------------------------------------------------------
# Output
# --------------------------------------------------------------------------

def _fmt(v) -> str:
    return "" if v is None else str(v)


def _markdown_table(rows: list[dict], cols: list[str]) -> str:
    lines = ["| " + " | ".join(cols) + " |",
             "|" + "|".join("---" for _ in cols) + "|"]
    for r in rows:
        lines.append("| " + " | ".join(_fmt(r.get(c)) for c in cols) + " |")
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
    # Drop always-null "sometimes" columns so the view stays readable:
    #   - ad-traffic keyword is null post-June-2024 (campaign-level aggregate)
    #   - search-volume spell is null unless a term was misspelled
    # Keep them if any row is populated (older/edge behavior).
    if rows:
        cols = [c for c in cols
                if c not in _DROP_IF_ALL_NULL
                or any(r.get(c) is not None for r in rows)]

    # --monthly folds the 12-month trend into a cell so it survives to CSV/table
    # (the trend is always present in the JSON output regardless).
    if getattr(args, "monthly", False) and op in _METRIC_OPS:
        cols = cols + ["monthly_trend"]
        for r in rows:
            r["monthly_trend"] = _trend_str(r.get("monthly_searches"))

    # CSV file always gets the FULL result set — nothing is lost to --limit.
    if getattr(args, "csv", None):
        with open(args.csv, "w", encoding="utf-8", newline="") as fh:
            fh.write(_csv_string(rows, cols))
        meta["csv_path"] = os.path.abspath(args.csv)

    shown = rows if args.limit is None else rows[: args.limit]
    meta["total_returned"] = len(rows)
    meta["shown"] = len(shown)
    if args.limit is not None and len(rows) > args.limit:
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
        print(json.dumps({"meta": meta, "keywords": shown}, indent=2))


def _die(msg: str) -> None:
    sys.stderr.write("error: " + msg + "\n")
    sys.exit(1)


# --------------------------------------------------------------------------
# Operations
# --------------------------------------------------------------------------

def _run_keyword_op(op: str, args) -> None:
    endpoint, task = _build_task(op, args)
    key = _cache_key(endpoint, task)
    is_cached = _cache_get(key) is not None

    # --dry-run: show exactly what would be sent without paying. Also reports
    # whether the answer is already cached (so running it would be free).
    if getattr(args, "dry_run", False):
        print(json.dumps({
            "dry_run": True,
            "endpoint": endpoint,
            "request_body": [task],
            "billable": not is_cached,
            "note": ("already cached — running this is FREE"
                     if is_cached else
                     "not cached — running this is 1 billable request"),
        }, indent=2))
        return

    from_cache = False
    if not args.no_cache and is_cached:
        response, from_cache = _cache_get(key), True
    else:
        response = client.post(endpoint, task)
        _cache_put(key, response)

    t = client.unwrap_task(response)

    # --raw: dump the complete task result to a file so nothing the source
    # returned (annotations, concepts, full monthly history) is ever lost.
    if getattr(args, "raw", None):
        with open(args.raw, "w", encoding="utf-8") as fh:
            json.dump(t.get("result") or [], fh, indent=2)

    rows = _norm_rows(op, t.get("result") or [])

    meta = {
        "operation": op,
        "endpoint": endpoint,
        "location_code": task.get("location_code"),
        "location_name": task.get("location_name"),
        "language_code": task.get("language_code"),
        "language_name": task.get("language_name"),
        "cost": 0.0 if from_cache else response.get("cost"),
        "from_cache": from_cache,
    }
    if op == "for-site":
        meta["target"] = args.target
        meta["target_type"] = args.target_type
    if op == "ad-traffic":
        meta["bid"] = args.bid
        meta["match"] = args.match
        meta["date_interval"] = task.get("date_interval", "next_month")
    if getattr(args, "raw", None):
        meta["raw_path"] = os.path.abspath(args.raw)
    _emit(op, rows, meta, args)


def _run_lookup(op: str, args) -> None:
    endpoint = f"keywords_data/google_ads/{'locations' if op == 'locations' else 'languages'}"
    response = client.get(endpoint)
    t = client.unwrap_task(response)
    items = t.get("result") or []
    needle = (args.contains or "").lower()
    if needle:
        if op == "locations":
            items = [i for i in items if needle in (i.get("location_name") or "").lower()]
        else:
            items = [i for i in items
                     if needle in (i.get("language_name") or "").lower()
                     or needle in (i.get("language_code") or "").lower()]
    print(json.dumps(items[: args.limit] if args.limit else items, indent=2))


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------

def _add_common_args(p: argparse.ArgumentParser) -> None:
    loc = p.add_argument_group("location / language (defaults: US, English)")
    loc.add_argument("--location-code", type=int, default=2840,
                     help="search-engine location code (default 2840 = United States)")
    loc.add_argument("--location-name", help="e.g. 'London,England,United Kingdom' (overrides --location-code)")
    loc.add_argument("--worldwide", action="store_true", help="omit location -> worldwide results")
    loc.add_argument("--language-code", default="en", help="e.g. en, de, fr (default en)")
    loc.add_argument("--language-name", help="e.g. 'English' (overrides --language-code)")

    out = p.add_argument_group("output")
    out.add_argument("--format", choices=["json", "table", "csv"], default="json",
                     help="stdout format (default json)")
    out.add_argument("--csv", metavar="PATH",
                     help="also write the FULL result set to a CSV file (ignores --limit)")
    out.add_argument("--raw", metavar="PATH",
                     help="dump the complete raw API result to a JSON file "
                          "(annotations, concepts, full monthly history — nothing dropped)")
    out.add_argument("--monthly", action="store_true",
                     help="include the 12-month search-volume trend as a column in table/CSV")
    out.add_argument("--limit", type=int, default=100,
                     help="cap rows printed to stdout (default 100; use 0 for all). "
                          "--csv always gets everything.")

    cost = p.add_argument_group("cost control")
    cost.add_argument("--no-cache", action="store_true", help="force a fresh paid call")
    cost.add_argument("--dry-run", action="store_true",
                      help="print the exact request without calling (free); "
                           "reports whether it's already cached")


def _post_parse_limit(args) -> None:
    if getattr(args, "limit", None) == 0:
        args.limit = None


def main(argv=None) -> None:
    parser = argparse.ArgumentParser(
        prog="keywords.py",
        description="DataForSEO Google Ads Keywords Data (Live).")
    sub = parser.add_subparsers(dest="op", required=True)

    # for-site
    ps = sub.add_parser("for-site", help="keywords for a domain or page")
    ps.add_argument("target", help="domain (e.g. example.com) or page URL")
    ps.add_argument("--target-type", choices=["site", "page"], default="site",
                    help="'site' = whole domain, 'page' = one URL (default site)")
    ps.add_argument("--sort-by",
                    choices=["relevance", "search_volume", "competition_index",
                             "low_top_of_page_bid", "high_top_of_page_bid"],
                    help="sort order (default relevance)")
    ps.add_argument("--search-partners", action="store_true")
    ps.add_argument("--include-adult", action="store_true")
    ps.add_argument("--date-from", help="yyyy-mm-dd (default: past 12 months)")
    ps.add_argument("--date-to", help="yyyy-mm-dd")
    ps.add_argument("--tag")
    _add_common_args(ps)

    # for-keywords
    pk = sub.add_parser("for-keywords", help="keyword ideas from 1-20 seed terms")
    pk.add_argument("keywords", nargs="+", help="1-20 seed keywords")
    pk.add_argument("--sort-by",
                    choices=["relevance", "search_volume", "competition_index",
                             "low_top_of_page_bid", "high_top_of_page_bid"],
                    help="sort order (default relevance)")
    pk.add_argument("--search-partners", action="store_true")
    pk.add_argument("--include-adult", action="store_true")
    pk.add_argument("--date-from", help="yyyy-mm-dd (default: past 12 months)")
    pk.add_argument("--date-to", help="yyyy-mm-dd")
    pk.add_argument("--tag")
    _add_common_args(pk)

    # search-volume — cheapest exact metrics for a KNOWN list (up to 1000/call)
    pv = sub.add_parser("search-volume",
                        help="exact search volume + CPC for a known list of up to 1000 keywords (one call)")
    pv.add_argument("keywords", nargs="+", help="1-1000 keywords you already know")
    pv.add_argument("--sort-by",
                    choices=["relevance", "search_volume", "competition_index",
                             "low_top_of_page_bid", "high_top_of_page_bid"],
                    help="sort order (default relevance)")
    pv.add_argument("--search-partners", action="store_true")
    pv.add_argument("--include-adult", action="store_true")
    pv.add_argument("--date-from", help="yyyy-mm-dd (default: past 12 months; up to 4 years back)")
    pv.add_argument("--date-to", help="yyyy-mm-dd (Google returns no data for the current month)")
    pv.add_argument("--tag")
    _add_common_args(pv)

    # ad-traffic
    pt = sub.add_parser("ad-traffic", help="forecast clicks/CPC/spend for keywords")
    pt.add_argument("keywords", nargs="+", help="1-1000 keywords")
    pt.add_argument("--bid", type=int, required=True,
                    help="max bid (USD). Higher bid -> higher projected metrics. Use a high bid (e.g. 999) to level account factors.")
    pt.add_argument("--match", choices=["exact", "broad", "phrase"], required=True)
    pt.add_argument("--date-interval", choices=["next_week", "next_month", "next_quarter"],
                    default="next_month", help="forecast window (default next_month)")
    pt.add_argument("--date-from", help="yyyy-mm-dd (future). Use with --date-to instead of --date-interval.")
    pt.add_argument("--date-to", help="yyyy-mm-dd (future)")
    pt.add_argument("--sort-by",
                    choices=["relevance", "impressions", "ctr", "average_cpc", "cost", "clicks"],
                    help="sort order (default relevance)")
    pt.add_argument("--tag")
    _add_common_args(pt)

    # locations / languages
    pl = sub.add_parser("locations", help="find a location_code")
    pl.add_argument("--contains", help="filter by substring, e.g. 'United States'")
    pl.add_argument("--limit", type=int, default=50)

    pg = sub.add_parser("languages", help="find a language_code")
    pg.add_argument("--contains", help="filter by substring, e.g. 'English'")
    pg.add_argument("--limit", type=int, default=50)

    args = parser.parse_args(argv)

    try:
        if args.op in ("locations", "languages"):
            _run_lookup(args.op, args)
        else:
            _post_parse_limit(args)
            _run_keyword_op(args.op, args)
    except RuntimeError as e:
        _die(str(e))


if __name__ == "__main__":
    main()
