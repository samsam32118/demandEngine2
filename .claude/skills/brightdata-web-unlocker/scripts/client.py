"""Shared HTTP client for Bright Data's Web Unlocker API.

One endpoint, one shape: POST https://api.brightdata.com/request with a JSON
body of {zone, url, format[, method][, country]}. Bright Data routes the
request through its unlocker infrastructure (residential/mobile IPs, real
browser fingerprinting, JS-challenge and CAPTCHA solving) and hands back the
target site's response as if a normal browser had loaded it. We stay
stdlib-only to match the house style — no .venv needed for this skill.
"""
from __future__ import annotations

import json
import os
import sys
import time
import urllib.error
import urllib.request

_BASE = "https://api.brightdata.com"
_RETRY_STATUSES = {429, 500, 502, 503, 504}


def _token() -> str:
    tok = os.environ.get("BRIGHTDATA_API_TOKEN")
    if not tok:
        sys.stderr.write(
            "error: missing API token. Set BRIGHTDATA_API_TOKEN to a Bright Data "
            "API token with a Web Unlocker zone enabled.\n"
        )
        sys.exit(2)
    return tok


def fetch(
    url: str,
    *,
    zone: str,
    fmt: str = "raw",
    method: str = "GET",
    country: str | None = None,
    timeout: int = 60,
) -> tuple[int | None, str]:
    """POST /request. Returns (status_code, body_text).

    fmt: Bright Data's "format" field. "raw" returns the target page's body
        verbatim — exactly what the operator's working curl examples use.
        "json" wraps the response in a {status_code, headers, body} envelope,
        which is how you check the upstream HTTP status programmatically
        instead of guessing from the body.
    zone: which Web Unlocker zone to hit. Callers resolve the zone (default
        vs. premium) before calling this — this function just sends whatever
        it's given.
    method: HTTP method the unlocker should use against the target. Almost
        always "GET"; exposed for completeness.
    country: geolocation hint (e.g. "us", "de"). Passed through to Bright
        Data's proxy pool selection.

    Retries 429 and 5xx with exponential backoff up to 5 attempts. Non-
    transient errors raise RuntimeError with the server body (truncated) so
    the caller can show the user a useful message — this matches every other
    brightdata-* skill in this repo, so a bad token or unknown zone fails the
    same way everywhere.
    """
    payload: dict = {"zone": zone, "url": url, "format": fmt}
    if method and method != "GET":
        payload["method"] = method
    if country:
        payload["country"] = country
    body = json.dumps(payload).encode("utf-8")
    headers = {
        "Authorization": f"Bearer {_token()}",
        "Content-Type": "application/json",
        "User-Agent": "gtmdata-brightdata-web-unlocker-skill/1.0",
    }

    delay = 1.0
    last_err = ""
    for attempt in range(5):
        req = urllib.request.Request(
            f"{_BASE}/request", data=body, headers=headers, method="POST"
        )
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return resp.status, resp.read().decode("utf-8", errors="replace")
        except urllib.error.HTTPError as e:
            raw = (e.read() or b"").decode("utf-8", errors="replace")
            if e.code in _RETRY_STATUSES and attempt < 4:
                time.sleep(delay)
                delay *= 2
                continue
            raise RuntimeError(f"HTTP {e.code} POST /request: {raw[:500]}") from None
        except urllib.error.URLError as e:
            last_err = str(e)
            if attempt < 4:
                time.sleep(delay)
                delay *= 2
                continue
            raise RuntimeError(f"network error POST /request: {last_err}") from None
    raise RuntimeError(f"request failed after retries: {last_err}")
