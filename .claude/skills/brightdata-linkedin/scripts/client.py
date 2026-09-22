"""Shared HTTP client for Bright Data's LinkedIn Web Scraper APIs.

Skill scripts import these helpers and stay task-oriented. The base URL,
Bearer auth, retries, and the async trigger/poll/download loop are hidden
here so SKILL.md prose doesn't have to repeat Bright Data specifics.

All requests go to Bright Data's Web Scraper API (the pay-as-you-go SKU).
The four LinkedIn dataset ids are exposed as constants and grouped under
`DATASETS` so callers can resolve them by a short `kind` string.
"""
from __future__ import annotations

import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

_BASE = "https://api.brightdata.com"

# LinkedIn Web Scraper API dataset ids (stable Bright Data identifiers).
LINKEDIN_PEOPLE_DATASET_ID = "gd_l1viktl72bvl7bjuj0"
LINKEDIN_COMPANY_DATASET_ID = "gd_l1vikfnt1wgvvqz95w"
LINKEDIN_JOBS_DATASET_ID = "gd_lpfll7v5hcqtkxl6l"
LINKEDIN_POSTS_DATASET_ID = "gd_lyy3tktm25m4avu764"

DATASETS: dict[str, str] = {
    "people": LINKEDIN_PEOPLE_DATASET_ID,
    "company": LINKEDIN_COMPANY_DATASET_ID,
    "jobs": LINKEDIN_JOBS_DATASET_ID,
    "posts": LINKEDIN_POSTS_DATASET_ID,
}

# Transient HTTP statuses we retry on. 202 means "still running" for
# /progress and is handled by the caller, not here.
_RETRY_STATUSES = {429, 500, 502, 503, 504}


def resolve_dataset(kind: str) -> str:
    """Map a short kind ('people'|'company'|'jobs'|'posts') to dataset id."""
    try:
        return DATASETS[kind]
    except KeyError:
        raise SystemExit(
            f"error: unknown kind {kind!r}; expected one of {sorted(DATASETS)}"
        )


def _token() -> str:
    tok = os.environ.get("BRIGHTDATA_API_TOKEN")
    if not tok:
        sys.stderr.write(
            "error: missing API token. Set BRIGHTDATA_API_TOKEN to a Bright Data "
            "API token with the LinkedIn Web Scraper APIs enabled.\n"
        )
        sys.exit(2)
    return tok


def _headers() -> dict[str, str]:
    return {
        "Authorization": f"Bearer {_token()}",
        "Accept": "application/json",
        "User-Agent": "rivas-brightdata-linkedin-skill/1.0",
    }


def _request(
    method: str,
    path: str,
    *,
    params: dict[str, Any] | None = None,
    body: Any = None,
) -> tuple[int, bytes]:
    """Execute one HTTP request with retries. Returns (status, raw bytes).

    Retries transient errors (429, 5xx, network) with exponential backoff
    up to 5 attempts. Non-transient errors raise RuntimeError with the
    server body so callers can show the user a useful message.
    """
    clean = {k: v for k, v in (params or {}).items() if v is not None and v != ""}
    url = f"{_BASE}{path}"
    if clean:
        url += "?" + urllib.parse.urlencode(clean)

    data: bytes | None = None
    headers = _headers()
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        headers["Content-Type"] = "application/json"

    delay = 1.0
    last_err: str = ""
    for attempt in range(5):
        req = urllib.request.Request(url, data=data, headers=headers, method=method)
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                return resp.status, resp.read()
        except urllib.error.HTTPError as e:
            raw = e.read() or b""
            if e.code in _RETRY_STATUSES and attempt < 4:
                time.sleep(delay)
                delay *= 2
                continue
            # 202 is a successful "still running" for /progress — surface it.
            if e.code == 202:
                return 202, raw
            # 409 is "snapshot not ready yet" for /snapshot — surface it.
            if e.code == 409:
                return 409, raw
            msg = raw.decode("utf-8", errors="replace")
            # Friendlier hint when an account lacks a specific discovery
            # collector. Bright Data returns a bare "Incorrect discovery
            # collector id Available types:" with no extras on 400.
            if e.code == 400 and "discovery collector" in msg.lower():
                msg = (
                    f"{msg.strip()} "
                    "(this discover_by mode is not enabled on your Bright "
                    "Data account — toggle the collector in the dashboard "
                    "under LinkedIn Web Scraper APIs, or use a different "
                    "lookup path)"
                )
            raise RuntimeError(f"HTTP {e.code} {method} {path}: {msg}") from None
        except urllib.error.URLError as e:
            last_err = str(e)
            if attempt < 4:
                time.sleep(delay)
                delay *= 2
                continue
            raise RuntimeError(f"network error {method} {path}: {last_err}") from None
    raise RuntimeError(f"request failed after retries: {method} {path}: {last_err}")


def _json(raw: bytes) -> Any:
    if not raw:
        return None
    return json.loads(raw.decode("utf-8"))


def trigger(
    dataset_id: str,
    inputs: list[dict[str, Any]],
    *,
    discover_by: str | None = None,
    limit_per_input: int | None = None,
    custom_output_fields: list[str] | None = None,
    include_errors: bool = True,
    endpoint: str | None = None,
) -> str:
    """POST /datasets/v3/trigger. Returns the snapshot_id.

    discover_by: if set (e.g. "name", "keyword", "profile_url",
        "company_url", "url"), switches to discover-new mode. Each dataset
        supports different discover_by values — see references/curls.md.
    limit_per_input: cap returned records per input (critical for cost
        control in discover mode; ignored in pure URL lookup mode).
    custom_output_fields: return only these column names instead of the
        full record. Reduces payload size; does not reduce billing.
    endpoint: webhook URL for async delivery instead of pull.
    """
    params: dict[str, Any] = {"dataset_id": dataset_id}
    if include_errors:
        params["include_errors"] = "true"
    if discover_by:
        params["type"] = "discover_new"
        params["discover_by"] = discover_by
    if limit_per_input is not None:
        params["limit_per_input"] = limit_per_input
    if custom_output_fields:
        params["custom_output_fields"] = "|".join(custom_output_fields)
    if endpoint:
        params["endpoint"] = endpoint

    status, raw = _request("POST", "/datasets/v3/trigger", params=params, body=inputs)
    if status != 200:
        raise RuntimeError(f"trigger returned HTTP {status}: {raw[:500]!r}")
    data = _json(raw) or {}
    snap = data.get("snapshot_id")
    if not snap:
        raise RuntimeError(f"trigger response missing snapshot_id: {data!r}")
    return snap


def progress(snapshot_id: str) -> dict[str, Any]:
    """GET /datasets/v3/progress/{id}. Returns the progress dict.

    Status values: starting | running | ready | failed. HTTP 202 is
    treated as an in-progress signal and normalized into the response.
    """
    status, raw = _request("GET", f"/datasets/v3/progress/{snapshot_id}")
    data = _json(raw) or {}
    if status == 202 and not data.get("status"):
        data["status"] = "running"
    return data


def download(snapshot_id: str, *, format: str = "json") -> list[dict[str, Any]]:
    """GET /datasets/v3/snapshot/{id}. Returns the list of result rows.

    Raises RuntimeError with a clear message if the snapshot isn't ready
    yet (HTTP 409) — callers should use wait_for_snapshot() to poll first.
    """
    status, raw = _request(
        "GET", f"/datasets/v3/snapshot/{snapshot_id}", params={"format": format}
    )
    if status == 409:
        raise RuntimeError(
            f"snapshot {snapshot_id} not ready yet (HTTP 409). "
            "Poll /progress until status=ready before downloading."
        )
    if status != 200:
        raise RuntimeError(f"download returned HTTP {status}: {raw[:500]!r}")
    text = raw.decode("utf-8").strip()
    if not text:
        return []
    if text.startswith("["):
        return json.loads(text)
    rows: list[dict[str, Any]] = []
    for line in text.splitlines():
        line = line.strip()
        if line:
            rows.append(json.loads(line))
    return rows


def list_snapshots(
    dataset_id: str | None = None,
    *,
    status: str | None = None,
    limit: int | None = None,
) -> list[dict[str, Any]]:
    """GET /datasets/v3/snapshots. Returns the raw list of snapshot dicts."""
    params: dict[str, Any] = {}
    if dataset_id:
        params["dataset_id"] = dataset_id
    if status:
        params["status"] = status
    code, raw = _request("GET", "/datasets/v3/snapshots", params=params)
    if code != 200:
        raise RuntimeError(f"list_snapshots returned HTTP {code}: {raw[:500]!r}")
    data = _json(raw) or []
    if isinstance(data, dict):
        data = data.get("snapshots") or data.get("data") or []
    if limit is not None:
        data = data[:limit]
    return data


def metadata(dataset_id: str) -> dict[str, Any]:
    """GET /datasets/{dataset_id}/metadata. Returns the field schema dict."""
    code, raw = _request("GET", f"/datasets/{dataset_id}/metadata")
    if code != 200:
        raise RuntimeError(f"metadata returned HTTP {code}: {raw[:500]!r}")
    return _json(raw) or {}


def wait_for_snapshot(
    snapshot_id: str,
    *,
    poll_interval: float = 10.0,
    timeout: float = 600.0,
) -> list[dict[str, Any]]:
    """Poll /progress until ready/failed, then download and return rows.

    Raises RuntimeError on timeout or failed status. The 10s default
    poll interval is polite — Bright Data doesn't publish a QPS limit
    but we don't want to hammer it either.
    """
    deadline = time.monotonic() + timeout
    while True:
        info = progress(snapshot_id)
        state = (info.get("status") or "").lower()
        if state == "ready":
            return download(snapshot_id)
        if state == "failed":
            raise RuntimeError(f"snapshot {snapshot_id} failed: {info!r}")
        if time.monotonic() >= deadline:
            raise RuntimeError(
                f"timed out after {timeout:.0f}s waiting for snapshot "
                f"{snapshot_id} (last status={state!r}). Re-run with "
                f"--no-wait and fetch later via get_snapshot.py."
            )
        time.sleep(poll_interval)


def emit(obj: Any) -> None:
    """Pretty-print a JSON object to stdout. Matches the house style."""
    json.dump(obj, sys.stdout, ensure_ascii=False, indent=2, default=str)
    sys.stdout.write("\n")


def parse_fields(raw: str | None) -> list[str] | None:
    """Turn a comma-separated --fields string into a list, or None."""
    if not raw:
        return None
    return [f.strip() for f in raw.split(",") if f.strip()]
