"""Shared HTTP client for DataForSEO's Google Ads Keywords Data API (Live).

One shape for every call: POST a JSON array of one task object to a
`.../live` endpoint under `keywords_data/google_ads/`, and read back a
`tasks` array. Auth is HTTP Basic with base64(login:password) — the same
credentials you'd get from https://app.dataforseo.com/api-access.

Stdlib-only (no .venv) to match the house style. Credentials come from the
environment: DATA_FOR_SEO_LOGIN and DATA_FOR_SEO_PASSWORD.
"""
from __future__ import annotations

import base64
import json
import os
import sys
import time
import urllib.error
import urllib.request

_BASE = "https://api.dataforseo.com/v3"
_RETRY_STATUSES = {429, 500, 502, 503, 504}

# DataForSEO status codes. 20000 = success. The 40000-range are per-task
# errors (bad params, no data, etc.); 20000 is the only "all good" code.
_OK = 20000


def _creds() -> tuple[str, str]:
    login = os.environ.get("DATA_FOR_SEO_LOGIN")
    password = os.environ.get("DATA_FOR_SEO_PASSWORD")
    if not login or not password:
        # Fall back to a .env in the working dir, mirroring the other
        # credentialed skills in this repo.
        env_path = os.path.join(os.getcwd(), ".env")
        if os.path.exists(env_path):
            with open(env_path, encoding="utf-8") as fh:
                for line in fh:
                    line = line.strip()
                    if not line or line.startswith("#") or "=" not in line:
                        continue
                    k, v = line.split("=", 1)
                    v = v.strip().strip('"').strip("'")
                    if k.strip() == "DATA_FOR_SEO_LOGIN" and not login:
                        login = v
                    elif k.strip() == "DATA_FOR_SEO_PASSWORD" and not password:
                        password = v
    if not login or not password:
        sys.stderr.write(
            "error: missing credentials. Set DATA_FOR_SEO_LOGIN and "
            "DATA_FOR_SEO_PASSWORD (from https://app.dataforseo.com/api-access).\n"
        )
        sys.exit(2)
    return login, password


def _auth_header() -> str:
    login, password = _creds()
    raw = f"{login}:{password}".encode("utf-8")
    return "Basic " + base64.b64encode(raw).decode("ascii")


def post(endpoint: str, task: dict, *, timeout: int = 120) -> dict:
    """POST a single task object to a `.../live` endpoint.

    `endpoint` is the path after `/v3/`, e.g.
    "keywords_data/google_ads/keywords_for_keywords/live".

    The DataForSEO wire format wraps the task in a JSON array, so callers
    pass one plain dict and we do the wrapping. Returns the parsed
    top-level response dict (with the `tasks` array intact).

    Retries 429 and 5xx with exponential backoff up to 5 attempts. HTTP
    errors and network errors raise RuntimeError with the server body so the
    caller can surface a useful message.
    """
    body = json.dumps([task]).encode("utf-8")
    headers = {
        "Authorization": _auth_header(),
        "Content-Type": "application/json",
        "User-Agent": "james-dataforseo-keywords-skill/1.0",
    }
    url = f"{_BASE}/{endpoint.lstrip('/')}"

    delay = 2.0
    last_err = ""
    for attempt in range(5):
        req = urllib.request.Request(url, data=body, headers=headers, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return json.loads(resp.read().decode("utf-8", errors="replace"))
        except urllib.error.HTTPError as e:
            raw = (e.read() or b"").decode("utf-8", errors="replace")
            if e.code in _RETRY_STATUSES and attempt < 4:
                time.sleep(delay)
                delay *= 2
                continue
            raise RuntimeError(f"HTTP {e.code} POST {endpoint}: {raw[:500]}") from None
        except urllib.error.URLError as e:
            last_err = str(e)
            if attempt < 4:
                time.sleep(delay)
                delay *= 2
                continue
            raise RuntimeError(f"network error POST {endpoint}: {last_err}") from None
    raise RuntimeError(f"request failed after retries: {last_err}")


def get(endpoint: str, *, timeout: int = 60) -> dict:
    """GET a helper endpoint (locations, languages, status). No task body."""
    headers = {
        "Authorization": _auth_header(),
        "User-Agent": "james-dataforseo-keywords-skill/1.0",
    }
    url = f"{_BASE}/{endpoint.lstrip('/')}"
    delay = 2.0
    last_err = ""
    for attempt in range(5):
        req = urllib.request.Request(url, headers=headers, method="GET")
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return json.loads(resp.read().decode("utf-8", errors="replace"))
        except urllib.error.HTTPError as e:
            raw = (e.read() or b"").decode("utf-8", errors="replace")
            if e.code in _RETRY_STATUSES and attempt < 4:
                time.sleep(delay)
                delay *= 2
                continue
            raise RuntimeError(f"HTTP {e.code} GET {endpoint}: {raw[:500]}") from None
        except urllib.error.URLError as e:
            last_err = str(e)
            if attempt < 4:
                time.sleep(delay)
                delay *= 2
                continue
            raise RuntimeError(f"network error GET {endpoint}: {last_err}") from None
    raise RuntimeError(f"request failed after retries: {last_err}")


def unwrap_task(response: dict) -> dict:
    """Pull the single task out of a response, raising on any error status.

    DataForSEO returns errors at two levels: a top-level `status_code` and a
    per-task `status_code`. A request can succeed at the top level (20000)
    while the task fails (e.g. 40501 invalid field). We check both so the
    caller always gets either a clean task or a clear exception.
    """
    top = response.get("status_code")
    if top != _OK:
        raise RuntimeError(
            f"API error {top}: {response.get('status_message')}"
        )
    tasks = response.get("tasks") or []
    if not tasks:
        raise RuntimeError("API returned no tasks")
    task = tasks[0]
    tstatus = task.get("status_code")
    if tstatus != _OK:
        raise RuntimeError(
            f"task error {tstatus}: {task.get('status_message')}"
        )
    return task
