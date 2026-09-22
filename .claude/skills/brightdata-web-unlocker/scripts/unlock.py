#!/usr/bin/env python3
"""Fetch a URL through Bright Data's Web Unlocker API and print the response.

Two output formats, selected with --format:

    raw (default)
        The target page's body, verbatim — matches the operator's working
        curl examples exactly. Simplest option; use this by default.

    json
        Bright Data wraps the response in a {status_code, headers, body}
        envelope. Use this when you need to check the upstream HTTP status
        programmatically instead of guessing from the body.

The zone (web_unlocker1 vs. web_unlocker_premium) is auto-detected from the
URL's hostname via premium_domains.zone_for_url() — see that module for the
domain list. Pass --zone to override.

Results are cached at workspace/cache/<sha256>.json keyed on a canonical
(url, zone, format, method, country) tuple — re-fetching the same URL
returns instantly without another billable call.

Typical usage (from repo root):

    python .claude/skills/brightdata-web-unlocker/scripts/unlock.py "https://example.com"
    python .claude/skills/brightdata-web-unlocker/scripts/unlock.py "https://www.target.com/s/..." --save page.html
"""
from __future__ import annotations

import argparse
import hashlib
import json
import pathlib
import sys
import time

import client
from premium_domains import zone_for_url

# __file__ at .claude/skills/brightdata-web-unlocker/scripts/unlock.py —
# 4 parents up lands on the repo root.
REPO_ROOT = pathlib.Path(__file__).resolve().parents[4]
CACHE_DIR = REPO_ROOT / "workspace" / "cache"

FORMATS = ("raw", "json")


def _cache_key(url: str, zone: str, fmt: str, method: str, country: str | None) -> str:
    canonical = json.dumps(
        {
            "src": "web_unlocker",
            "url": url,
            "zone": zone,
            "format": fmt,
            "method": method,
            "country": country,
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


def run(
    url: str,
    *,
    zone: str | None,
    fmt: str,
    method: str,
    country: str | None,
    use_cache: bool,
) -> dict:
    if fmt not in FORMATS:
        raise SystemExit(f"unknown --format {fmt!r}; choose from {FORMATS}")

    resolved_zone = zone or zone_for_url(url)
    key = _cache_key(url, resolved_zone, fmt, method, country)
    if use_cache:
        hit = _cache_read(key)
        if hit is not None:
            hit["_from_cache"] = True
            return hit

    retrieved_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    status, body = client.fetch(
        url, zone=resolved_zone, fmt=fmt, method=method, country=country
    )

    if fmt == "json":
        try:
            envelope = json.loads(body)
        except json.JSONDecodeError:
            payload = {
                "url": url,
                "zone": resolved_zone,
                "format": "json",
                "note": "expected JSON envelope but got plain text; returning as-is",
                "body": body,
                "retrieved_at": retrieved_at,
            }
        else:
            payload = {
                "url": url,
                "zone": resolved_zone,
                "format": "json",
                "status_code": envelope.get("status_code", status),
                "headers": envelope.get("headers"),
                "body": envelope.get("body", ""),
                "retrieved_at": retrieved_at,
            }
    else:  # fmt == "raw"
        payload = {
            "url": url,
            "zone": resolved_zone,
            "format": "raw",
            "status_code": status,
            "body": body,
            "retrieved_at": retrieved_at,
        }

    _cache_write(key, payload)
    return payload


def main(argv: list[str]) -> int:
    p = argparse.ArgumentParser(
        description="Fetch a URL through Bright Data's Web Unlocker API."
    )
    p.add_argument("url", help="the target URL to fetch")
    p.add_argument(
        "--zone",
        default=None,
        help="override zone auto-detection (default: auto-detect web_unlocker1 vs. web_unlocker_premium from the URL)",
    )
    p.add_argument(
        "--format",
        dest="fmt",
        choices=FORMATS,
        default="raw",
        help="raw (default, verbatim body) or json (status_code/headers/body envelope)",
    )
    p.add_argument(
        "--method",
        default="GET",
        help="HTTP method the unlocker sends to the target (default: GET)",
    )
    p.add_argument(
        "--country", default=None, help="Bright Data proxy country hint, e.g. us, de"
    )
    p.add_argument(
        "--save",
        default=None,
        metavar="PATH",
        help=(
            "write the fetched body to PATH instead of printing it, and print a "
            "short JSON summary instead. Use this for anything that isn't a "
            "small page — full HTML can be hundreds of KB."
        ),
    )
    p.add_argument(
        "--stdout",
        choices=("json", "body"),
        default="json",
        help=(
            "stdout shape when not using --save. json (default) prints the full "
            "payload; body prints just the fetched body."
        ),
    )
    p.add_argument(
        "--no-cache",
        action="store_true",
        help="bypass workspace/cache/ and force a fresh billable call",
    )
    args = p.parse_args(argv)

    payload = run(
        args.url,
        zone=args.zone,
        fmt=args.fmt,
        method=args.method,
        country=args.country,
        use_cache=not args.no_cache,
    )

    if args.save:
        save_path = pathlib.Path(args.save).expanduser().resolve()
        save_path.parent.mkdir(parents=True, exist_ok=True)
        body = payload.get("body", "") or ""
        save_path.write_text(body, encoding="utf-8")
        summary = {
            "path": str(save_path),
            "bytes": len(body.encode("utf-8")),
            "status_code": payload.get("status_code"),
            "zone": payload.get("zone"),
            "retrieved_at": payload.get("retrieved_at"),
        }
        json.dump(summary, sys.stdout, ensure_ascii=False, indent=2)
        sys.stdout.write("\n")
    elif args.stdout == "body":
        sys.stdout.write(payload.get("body", "") or "")
        sys.stdout.write("\n")
    else:
        json.dump(payload, sys.stdout, ensure_ascii=False, indent=2)
        sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
