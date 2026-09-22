"""Shared HTTP client for DataForSEO's Apple App Data API.

Two request shapes live behind one client:

* **Task-based** (`app_searches` / `app_info` / `app_reviews` / `app_list`):
  POST a task to `.../task_post`, get back a task `id`, then poll
  `.../task_get/advanced/{id}` until the task reports Ok (20000). Polling
  task_get is free — you are billed once for the task itself — so we can poll
  patiently with a backoff that stays well under the rate limits.
* **Live** (`app_listings/search/live`): POST and read the result straight
  back in the same response, exactly like the Keywords API.

Auth is HTTP Basic with base64(login:password) — the same credentials you'd
get from https://app.dataforseo.com/api-access. Credentials come from the
environment (DATA_FOR_SEO_LOGIN / DATA_FOR_SEO_PASSWORD), falling back to a
.env in the working directory.

Stdlib-only (no .venv) to match the house style of the sibling
`dataforseo-keywords` skill.
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

# --- DataForSEO task status codes (see /v3/appendix/errors) -----------------
# The API reports status at two levels: a top-level `status_code` for the HTTP
# call itself, and a per-task `status_code` for the work. A task_get call can
# succeed at the top level (20000) while the task is still cooking (40602).
OK = 20000          # task finished, `result` is populated
CREATED = 20100     # task_post accepted and queued
NO_RESULTS = 40102  # task finished but nothing matched — empty, NOT an error
# Codes that mean "still cooking, poll again" rather than "give up":
IN_PROGRESS = {20100, 40100, 40101, 40103, 40601, 40602}


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
    """POST a single task object to a `task_post` or `.../live` endpoint.

    `endpoint` is the path after `/v3/`, e.g.
    "app_data/apple/app_searches/task_post". The DataForSEO wire format wraps
    the task in a JSON array, so callers pass one plain dict and we do the
    wrapping. Returns the parsed top-level response dict (tasks array intact).

    Retries 429 and 5xx with exponential backoff up to 5 attempts.
    """
    body = json.dumps([task]).encode("utf-8")
    headers = {
        "Authorization": _auth_header(),
        "Content-Type": "application/json",
        "User-Agent": "james-dataforseo-appstore-skill/1.0",
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
    """GET a task_get / tasks_ready / reference endpoint. No task body."""
    headers = {
        "Authorization": _auth_header(),
        "User-Agent": "james-dataforseo-appstore-skill/1.0",
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


def task_status(response: dict) -> tuple[int, str, dict]:
    """Return (task_status_code, status_message, task) for the first task.

    Raises if the top-level call failed or carried no tasks — those are real
    transport/API failures, not task states. The per-task status_code is left
    for the caller to interpret (Ok / in-progress / fatal).
    """
    top = response.get("status_code")
    if top != OK:
        raise RuntimeError(f"API error {top}: {response.get('status_message')}")
    tasks = response.get("tasks") or []
    if not tasks:
        raise RuntimeError("API returned no tasks")
    task = tasks[0]
    return task.get("status_code"), task.get("status_message"), task


def unwrap_task(response: dict) -> dict:
    """Return the first task, raising unless it's Ok (20000) or empty (40102).

    For Live endpoints and free reference lookups the result is immediate, so
    anything other than Ok / No-Results is a genuine error worth surfacing.
    """
    code, msg, task = task_status(response)
    if code in (OK, NO_RESULTS):
        return task
    raise RuntimeError(f"task error {code}: {msg}")


def poll_advanced(base: str, task_id: str, *, max_wait: float = 300.0,
                  on_wait=None) -> dict:
    """Poll `{base}/task_get/advanced/{id}` until Ok, a fatal error, or timeout.

    `base` is the endpoint stem, e.g. "app_data/apple/app_searches". Returns
    the completed task dict. Cadence backs off (3,5,8,12,18, then 20s) so even
    a long-running Standard-queue task stays far under the 2000 calls/min cap.

    `max_wait=0` means a single shot: fetch once, return if ready, else raise
    TimeoutError immediately (useful for `get` when you just want to check).
    On timeout the error names the id so the task — retrievable for ~3 days —
    can be collected later.
    """
    endpoint = f"{base}/task_get/advanced/{task_id}"
    waited = 0.0
    delays = [3, 5, 8, 12, 18]
    i = 0
    while True:
        code, msg, task = task_status(get(endpoint))
        if code in (OK, NO_RESULTS):
            return task
        if code not in IN_PROGRESS:
            raise RuntimeError(f"task {task_id} failed: {code} {msg}")
        if waited >= max_wait:
            raise TimeoutError(
                f"task {task_id} not ready after {int(waited)}s "
                f"(status {code}: {msg}). It stays retrievable for ~3 days — "
                f"fetch it later with:  appstore.py get {task_id}")
        delay = delays[i] if i < len(delays) else 20
        i += 1
        if on_wait:
            on_wait(int(waited), code, msg)
        time.sleep(delay)
        waited += delay
