"""Shared HTTP client for Bright Data's SERP API.

One endpoint, one shape: POST https://api.brightdata.com/request with a JSON
body of {zone, url, format}. Bright Data proxies the request through its SERP
infrastructure and returns the response body (HTML by default; parsed JSON if
the URL contains brd_json=1). We stay stdlib-only to match the house style
(stdlib-only) — no .venv needed for this skill.
"""
from __future__ import annotations

import json
import os
import sys
import time
import urllib.error
import urllib.request

_BASE = "https://api.brightdata.com"
_DEFAULT_ZONE = "serp_api1"
_RETRY_STATUSES = {429, 500, 502, 503, 504}


def _token() -> str:
    tok = os.environ.get("BRIGHTDATA_API_TOKEN")
    if not tok:
        sys.stderr.write(
            "error: missing API token. Set BRIGHTDATA_API_TOKEN to a Bright Data "
            "API token with a SERP API zone enabled.\n"
        )
        sys.exit(2)
    return tok


def _zone(override: str | None = None) -> str:
    if override:
        return override
    return os.environ.get("BRIGHTDATA_SERP_ZONE", _DEFAULT_ZONE)


def fetch(
    url: str,
    *,
    fmt: str = "raw",
    zone: str | None = None,
    country: str | None = None,
    method: str = "GET",
    data_format: str | None = None,
    timeout: int = 60,
) -> str:
    """POST /request. Returns the response body as text.

    fmt: Bright Data's "format" field. "raw" returns the proxied page body
        verbatim (HTML for Google, JSON if the URL has brd_json=1). "json"
        wraps the body in a {status_code, headers, body} envelope — required
        when using data_format to ask Bright Data to transform the body.
    zone: override the SERP zone. Defaults to $BRIGHTDATA_SERP_ZONE, then
        "serp_api1" (matches the operator's working example).
    country: geolocation hint (e.g. "us", "de"). Passed through to Bright
        Data's proxy pool selection.
    method: HTTP method the proxy should send to the target. Always "GET"
        for Google search; exposed for completeness.
    data_format: Bright Data-side body transformer. "markdown" returns the
        page as markdown (with fmt="json" so it rides inside the envelope).
        Omit to get the page body verbatim.

    Retries 429 and 5xx with exponential backoff up to 5 attempts. Non-
    transient errors raise RuntimeError with the server body so the caller
    can show the user a useful message.
    """
    payload: dict = {"zone": _zone(zone), "url": url, "format": fmt}
    if method and method != "GET":
        payload["method"] = method
    elif method == "GET":
        # Bright Data accepts method both ways; include it so captured
        # payloads are self-describing.
        payload["method"] = "GET"
    if country:
        payload["country"] = country
    if data_format:
        payload["data_format"] = data_format
    body = json.dumps(payload).encode("utf-8")
    headers = {
        "Authorization": f"Bearer {_token()}",
        "Content-Type": "application/json",
        "User-Agent": "rivas-brightdata-serp-skill/1.0",
    }

    delay = 1.0
    last_err = ""
    for attempt in range(5):
        req = urllib.request.Request(
            f"{_BASE}/request", data=body, headers=headers, method="POST"
        )
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return resp.read().decode("utf-8", errors="replace")
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
