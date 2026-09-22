#!/usr/bin/env python3
"""Run a search-engine query through Bright Data's SERP API and print results.

Three output modes, selected with --format:

    markdown (default)
        Bright Data transforms Google's SERP into markdown server-side
        (data_format=markdown) and returns it inside a JSON envelope.
        The markdown body ends up at payload.markdown — ready to feed
        straight into an LLM or a dossier.

    parsed
        Append brd_json=1 to the search URL so Bright Data returns
        structured JSON. The skill normalises it into payload.results as
        a list of {title, url, snippet, position}.

    raw
        No body transformation. Returns the proxied HTML response for
        inspection or manual parsing.

Results are cached at workspace/cache/<sha256>.json keyed on a canonical
(engine, query, hl, gl, num, country, format) tuple — identical repeat
queries return instantly without another paid call. The same cache
shape is used by the email-guesser skill.

Typical usage (from repo root):

    python .claude/skills/brightdata-serp/scripts/search.py "pizza" --num 5

The caller owns budget bookkeeping — this skill is self-contained:

    # 1. confirm today's Bright Data count is under 100, then:
    python .claude/skills/brightdata-serp/scripts/search.py "..." --num 10
    # 2. increment the count + log the query unless served from cache
"""
from __future__ import annotations

import argparse
import hashlib
import json
import pathlib
import sys
import time
import urllib.parse

import client  # local — same directory


# __file__ at .claude/skills/brightdata-serp/scripts/search.py — 4 parents up
# lands on the repo root.
REPO_ROOT = pathlib.Path(__file__).resolve().parents[4]
CACHE_DIR = REPO_ROOT / "workspace" / "cache"

FORMATS = ("markdown", "parsed", "raw")


def _engine_url(engine: str, q: str, hl: str, gl: str, num: int, parse: bool) -> str:
    """Build a search URL for the given engine.

    Only Google is implemented at launch. The --engine flag exists so adding
    Bing/Yandex later is a pure extension, not a refactor of the CLI shape.
    """
    if engine != "google":
        raise SystemExit(
            f"engine {engine!r} not supported yet. Only 'google' is wired up. "
            "Extend _engine_url() if you need Bing, Yandex, etc."
        )
    params = {"q": q, "hl": hl, "gl": gl, "num": str(num)}
    if parse:
        # Bright Data's SERP-native parser. When present, the zone returns
        # structured JSON instead of Google's HTML. Use only for --format parsed.
        params["brd_json"] = "1"
    return "https://www.google.com/search?" + urllib.parse.urlencode(params)


def _cache_key(
    engine: str, q: str, hl: str, gl: str, num: int, country: str, fmt: str
) -> str:
    canonical = json.dumps(
        {
            "src": "serp",
            "engine": engine,
            "q": q,
            "hl": hl,
            "gl": gl,
            "num": num,
            "country": country,
            "format": fmt,
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _cache_read(key: str) -> dict | None:
    path = CACHE_DIR / f"{key}.json"
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


def _cache_write(key: str, payload: dict) -> None:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    (CACHE_DIR / f"{key}.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def _normalize_parsed(body_json: dict) -> list[dict]:
    """Flatten Bright Data's parsed SERP JSON into a normalised organic-result list.

    Bright Data's brd_json=1 output varies slightly across zones, but the
    organic results live under one of a few well-known keys. We try them in
    order and return a uniform [{title, url, snippet, position}] list.
    """
    for key in ("organic", "organic_results", "results"):
        items = body_json.get(key)
        if isinstance(items, list) and items:
            out = []
            for i, row in enumerate(items, start=1):
                if not isinstance(row, dict):
                    continue
                out.append(
                    {
                        "title": row.get("title") or row.get("name") or "",
                        "url": row.get("link") or row.get("url") or "",
                        "snippet": row.get("description")
                        or row.get("snippet")
                        or row.get("body")
                        or "",
                        "position": row.get("rank") or row.get("position") or i,
                    }
                )
            return out
    return []


def run(
    query: str,
    *,
    engine: str,
    hl: str,
    gl: str,
    num: int,
    country: str,
    fmt: str,
    zone: str | None,
    use_cache: bool,
) -> dict:
    if fmt not in FORMATS:
        raise SystemExit(f"unknown --format {fmt!r}; choose from {FORMATS}")

    key = _cache_key(engine, query, hl, gl, num, country, fmt)
    if use_cache:
        hit = _cache_read(key)
        if hit is not None:
            hit["_from_cache"] = True
            return hit

    url = _engine_url(engine, query, hl, gl, num, parse=(fmt == "parsed"))
    retrieved_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

    if fmt == "markdown":
        # Bright Data wraps the markdown in a {status_code, headers, body}
        # envelope when data_format is set and format="json". The body field
        # is the markdown we want.
        envelope_text = client.fetch(
            url,
            fmt="json",
            zone=zone,
            country=country,
            method="GET",
            data_format="markdown",
        )
        try:
            envelope = json.loads(envelope_text)
        except json.JSONDecodeError:
            payload = {
                "engine": engine,
                "query": query,
                "url": url,
                "format": "markdown",
                "markdown": envelope_text,
                "note": "expected JSON envelope but got plain text; returning as-is",
                "retrieved_at": retrieved_at,
            }
        else:
            payload = {
                "engine": engine,
                "query": query,
                "url": url,
                "format": "markdown",
                "status_code": envelope.get("status_code"),
                "markdown": envelope.get("body", ""),
                "retrieved_at": retrieved_at,
            }
    elif fmt == "parsed":
        body = client.fetch(url, fmt="raw", zone=zone, country=country, method="GET")
        try:
            parsed = json.loads(body)
        except json.JSONDecodeError:
            payload = {
                "engine": engine,
                "query": query,
                "url": url,
                "format": "parsed",
                "note": "brd_json=1 not honored by this zone; returned body as raw",
                "body": body,
                "retrieved_at": retrieved_at,
            }
        else:
            payload = {
                "engine": engine,
                "query": query,
                "url": url,
                "format": "parsed",
                "results": _normalize_parsed(parsed),
                "raw_parsed": parsed,
                "retrieved_at": retrieved_at,
            }
    else:  # fmt == "raw"
        body = client.fetch(url, fmt="raw", zone=zone, country=country, method="GET")
        payload = {
            "engine": engine,
            "query": query,
            "url": url,
            "format": "raw",
            "body": body,
            "retrieved_at": retrieved_at,
        }

    _cache_write(key, payload)
    return payload


def main(argv: list[str]) -> int:
    p = argparse.ArgumentParser(
        description=(
            "Run a Google search via Bright Data's SERP API. Billed against the "
            "shared Bright Data daily cap that the calling agent tracks."
        )
    )
    p.add_argument("query", help="the search query")
    p.add_argument("--engine", default="google", help="search engine (default: google)")
    p.add_argument("--hl", default="en", help="interface language (default: en)")
    p.add_argument(
        "--gl", default="us", help="geolocation / country code for Google (default: us)"
    )
    p.add_argument(
        "--num", type=int, default=10, help="number of results to request (default: 10)"
    )
    p.add_argument(
        "--country",
        default="us",
        help="Bright Data proxy country (default: us)",
    )
    p.add_argument(
        "--format",
        dest="fmt",
        choices=FORMATS,
        default="markdown",
        help=(
            "output format: markdown (default, Bright Data renders SERP as "
            "markdown), parsed (brd_json=1 structured JSON results), or raw "
            "(raw HTML body)."
        ),
    )
    p.add_argument(
        "--zone",
        default=None,
        help="override BRIGHTDATA_SERP_ZONE (default: serp_api1)",
    )
    p.add_argument(
        "--no-cache",
        action="store_true",
        help="bypass and do not read from workspace/cache/ — forces a fresh paid call",
    )
    p.add_argument(
        "--stdout",
        choices=("json", "markdown"),
        default="json",
        help=(
            "stdout shape. json (default) prints the full payload; markdown "
            "prints just the markdown body (only meaningful with --format markdown)."
        ),
    )
    args = p.parse_args(argv)

    payload = run(
        args.query,
        engine=args.engine,
        hl=args.hl,
        gl=args.gl,
        num=args.num,
        country=args.country,
        fmt=args.fmt,
        zone=args.zone,
        use_cache=not args.no_cache,
    )

    if args.stdout == "markdown":
        sys.stdout.write(payload.get("markdown", "") or "")
        sys.stdout.write("\n")
    else:
        json.dump(payload, sys.stdout, ensure_ascii=False, indent=2)
        sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
