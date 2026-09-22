"""Shared HTTP client for Bright Data's ZoomInfo Web Scraper API.

Skill scripts import these helpers and stay task-oriented. The base URL,
Bearer auth, retries, and the scrape/trigger/poll/download patterns are
hidden here so SKILL.md prose doesn't have to repeat Bright Data
specifics.

Primary path for lookups: scrape() — synchronous, blocks until data is ready.
Async path (used by discover, available for lookups via --no-wait):
    trigger() + wait_for_snapshot().

The single ZoomInfo dataset id is exposed as ZOOMINFO_DATASET_ID. The
discovery collector for this dataset is `search_url` only — there is no
free-text keyword discovery.
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
ZOOMINFO_DATASET_ID = "gd_m0ci4a4ivx3j5l6nx"

# Transient HTTP statuses we retry on.
_RETRY_STATUSES = {429, 500, 502, 503, 504}


def _token() -> str:
    tok = os.environ.get("BRIGHTDATA_API_TOKEN")
    if not tok:
        sys.stderr.write(
            "error: missing API token. Set BRIGHTDATA_API_TOKEN to a Bright Data "
            "API token with the ZoomInfo Web Scraper API enabled.\n"
        )
        sys.exit(2)
    return tok


def _headers() -> dict[str, str]:
    return {
        "Authorization": f"Bearer {_token()}",
        "Accept": "application/json",
        "User-Agent": "rivas-brightdata-zoominfo-skill/1.0",
    }


def _request(
    method: str,
    path: str,
    *,
    params: dict[str, Any] | None = None,
    body: Any = None,
    timeout: float = 120.0,
) -> tuple[int, bytes]:
    """Execute one HTTP request with retries. Returns (status, raw bytes).

    Retries transient errors (429, 5xx, network) with exponential backoff
    up to 5 attempts. Non-transient errors raise RuntimeError.
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
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return resp.status, resp.read()
        except urllib.error.HTTPError as e:
            raw = e.read() or b""
            if e.code in _RETRY_STATUSES and attempt < 4:
                time.sleep(delay)
                delay *= 2
                continue
            # 202 means "still running" for /progress — surface it.
            if e.code == 202:
                return 202, raw
            # 409 means "snapshot not ready yet" for /snapshot — surface it.
            if e.code == 409:
                return 409, raw
            msg = raw.decode("utf-8", errors="replace")
            # Friendlier hint when the discovery collector is wrong. Bright
            # Data's ZoomInfo collector only supports `search_url`.
            if e.code == 400 and "discovery collector" in msg.lower():
                msg = (
                    f"{msg.strip()} "
                    "(this discover_by mode is not supported on the ZoomInfo "
                    "dataset — only `search_url` is available; pass a "
                    "https://www.zoominfo.com/companies-search/... URL)"
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


def _parse_rows(raw: bytes) -> list[dict[str, Any]]:
    """Parse the response body as a JSON array or newline-delimited JSON."""
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


def scrape(
    dataset_id: str,
    inputs: list[dict[str, Any]],
    *,
    custom_output_fields: list[str] | None = None,
    include_errors: bool = True,
    scrape_timeout: float = 300.0,
    poll_interval: float = 10.0,
    poll_timeout: float = 600.0,
) -> list[dict[str, Any]]:
    """POST /datasets/v3/scrape?notify=false. Synchronous — blocks until done.

    Returns the list of result rows directly. The body format wraps inputs
    in {"input": [...]} per the ZoomInfo API.

    Bright Data will return HTTP 202 with a snapshot_id when the scrape
    takes longer than its internal sync threshold; in that case this
    function transparently falls through to polling that snapshot via
    /progress + /snapshot, so callers still get rows back without
    plumbing the async path themselves.

    scrape_timeout: seconds to wait for the blocking HTTP response (default
    300s). Increase for large multi-URL batches.
    poll_interval / poll_timeout: used only on the 202 fallback path.
    """
    params: dict[str, Any] = {
        "dataset_id": dataset_id,
        "notify": "false",
        "include_errors": "true" if include_errors else "false",
    }
    if custom_output_fields:
        params["custom_output_fields"] = "|".join(custom_output_fields)
    body = {"input": inputs}
    status, raw = _request(
        "POST", "/datasets/v3/scrape", params=params, body=body, timeout=scrape_timeout
    )
    if status == 200:
        return _parse_rows(raw)
    if status == 202:
        data = _json(raw) or {}
        snap = data.get("snapshot_id")
        if not snap:
            raise RuntimeError(
                f"scrape returned 202 but no snapshot_id: {raw[:500]!r}"
            )
        return wait_for_snapshot(
            snap, poll_interval=poll_interval, timeout=poll_timeout
        )
    raise RuntimeError(f"scrape returned HTTP {status}: {raw[:500]!r}")


def trigger(
    dataset_id: str,
    inputs: list[dict[str, Any]],
    *,
    discover_by: str | None = None,
    limit_per_input: int | None = None,
    custom_output_fields: list[str] | None = None,
    include_errors: bool = True,
) -> str:
    """POST /datasets/v3/trigger. Returns the snapshot_id.

    discover_by: if set ("search_url" for ZoomInfo), switches to discover-new
        mode. Pure URL-lookup leaves this None.
    limit_per_input: cap returned records per input (critical for cost
        control in discover mode; ignored in pure URL lookup mode).
    custom_output_fields: return only these column names instead of all 39.
        Reduces payload size; does not reduce billing.
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

    Status values: starting | running | ready | failed.
    """
    status, raw = _request("GET", f"/datasets/v3/progress/{snapshot_id}")
    data = _json(raw) or {}
    if status == 202 and not data.get("status"):
        data["status"] = "running"
    return data


def download(snapshot_id: str, *, format: str = "json") -> list[dict[str, Any]]:
    """GET /datasets/v3/snapshot/{id}. Returns the list of result rows.

    Raises RuntimeError with a clear message if the snapshot isn't ready
    yet (HTTP 409). Use wait_for_snapshot() to poll first.
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
    return _parse_rows(raw)


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

    Only needed when using the trigger() async path. The scrape() function
    returns rows directly without polling.
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
