"""Who actually ranks for a search — the bridge from a word to a business.

The most valuable thing this skill can do with $0.09 is spend it on
`for-site` against a company that is already selling into the market,
rather than on `for-keywords` against a string. Measured on the same
market, at the same price:

    expand "epcr"          ->    31 keywords,   2,100 searches a month
    for-site eso.com       ->   619 keywords, 367,940 searches a month

One hundred and seventy-five times the searching, and it surfaces terms no
expansion could reach — `electronic health records software` at 40,500 a
month, which is the market ambulance software actually sits inside and is
not a phrase anyone would have thought to seed.

The reason is not a quirk of the API. `for-keywords` expands off the
*breadth of a string*, so a niche phrase returns almost nothing —
`investtech` gave 18 rows, `ambulance software` 25. `for-site` expands off
what a live business is *about*, and a business that has invested in
ranking is evidence that someone is selling here. Invented keywords are
hypotheses; harvested ones are observed commercial vocabulary.

So the seed should be a business, not a word. This module finds the
businesses.

Stdlib only. The SERP zone in use ignores `brd_json=1` and returns Google's
rendered page as markdown regardless, so the organic results are recovered
from that rather than from structured JSON.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import ssl
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Sequence

BASE = "https://api.brightdata.com/request"
DEFAULT_ZONE = "serp_api1"
TOKEN_ENV = "BRIGHTDATA_API_TOKEN"

# A Google results page is tens of kilobytes. Anything under this is the
# vendor having failed with a 200, not a page with no results on it.
MIN_BODY = 500
ZONE_ENV = "BRIGHTDATA_SERP_ZONE"

# Hosts that rank for commercial terms without selling anything. Excluded
# before Jev sees them, because paying a model to tell you Wikipedia is not
# a vendor is paying for something a list already knows. Anything not on the
# list still goes to Jev — this is a shortcut, not the judgment.
NON_VENDOR = frozenset({
    "wikipedia.org", "youtube.com", "reddit.com", "quora.com", "facebook.com",
    "linkedin.com", "twitter.com", "x.com", "instagram.com", "pinterest.com",
    "amazon.com", "ebay.com", "indeed.com", "glassdoor.com", "tiktok.com",
    "medium.com", "substack.com", "github.com", "stackoverflow.com",
})


class SerpError(RuntimeError):
    pass


class SerpOffline(SerpError):
    """Offline and the query is not cached."""


@dataclass
class Result:
    rank: int
    title: str
    domain: str
    url: str
    snippet: str
    kind: str = ""            # filled by judge.pick_sellers
    kind_confidence: float = 0.0

    def as_dict(self) -> dict:
        return {"rank": self.rank, "title": self.title, "domain": self.domain,
                "url": self.url, "snippet": self.snippet, "kind": self.kind,
                "kind_confidence": round(self.kind_confidence, 3)}


def token() -> str:
    value = (os.environ.get(TOKEN_ENV) or "").strip()
    if not value:
        raise SerpError(f"missing {TOKEN_ENV}")
    return value


def available() -> bool:
    try:
        token()
        return True
    except SerpError:
        return False


def _registrable(host: str) -> str:
    """Strip www and a leading subdomain that carries no identity."""
    host = host.lower().strip().rstrip("/")
    for prefix in ("www.", "m.", "en."):
        if host.startswith(prefix):
            host = host[len(prefix):]
    return host


# Google renders each organic result as a `###` heading, then the source
# name, then a `https://domain › path › crumb` breadcrumb, then the snippet.
_CRUMB = re.compile(r"^https://([A-Za-z0-9.\-]+\.[A-Za-z]{2,})(?:\s*›.*)?$")
_HEADING = re.compile(r"^#{2,4}\s+(.+?)\s*$")


def parse_markdown(markdown: str, *, limit: int = 10) -> list[Result]:
    """Recover organic results from Google's rendered page.

    Keyed on the breadcrumb line, which is the one element every organic
    result has and no other block reliably does. The nearest heading above
    it is the title; the first substantial line below it is the snippet.
    """
    lines = markdown.splitlines()
    out: list[Result] = []
    seen: set[str] = set()
    for i, line in enumerate(lines):
        crumb = _CRUMB.match(line.strip())
        if not crumb:
            continue
        domain = _registrable(crumb.group(1))
        if not domain or domain in seen:
            continue

        title = ""
        for back in range(i - 1, max(i - 14, -1), -1):
            head = _HEADING.match(lines[back].strip())
            if head:
                title = head.group(1)
                break
        snippet = ""
        for fwd in range(i + 1, min(i + 12, len(lines))):
            text = lines[fwd].strip()
            if (len(text) < 40 or text.startswith(("[", "!", "#", "http"))
                    or "](" in text):
                continue
            snippet = re.sub(r"[_*`]", "", text)[:320]
            break
        if not title and not snippet:
            continue
        seen.add(domain)
        out.append(Result(len(out) + 1, title[:180], domain,
                          f"https://{domain}", snippet))
        if len(out) >= limit:
            break
    return out


class Serp:
    """A cached Bright Data SERP client."""

    def __init__(self, *, cache_dir: str, offline: bool = False,
                 timeout: int = 120) -> None:
        self.cache_dir = cache_dir
        self.offline = offline
        self.timeout = timeout
        self.calls = 0
        self.cached = 0

    def _key(self, payload: dict) -> str:
        blob = json.dumps(payload, sort_keys=True)
        return hashlib.sha256(blob.encode("utf-8")).hexdigest()

    def _read(self, key: str) -> str | None:
        path = os.path.join(self.cache_dir, key + ".json")
        if not os.path.exists(path):
            return None
        try:
            with open(path, encoding="utf-8") as fh:
                body = json.load(fh).get("markdown")
            return body if body and len(body) >= MIN_BODY else None
        except (OSError, ValueError):
            return None

    def _write(self, key: str, markdown: str) -> None:
        try:
            os.makedirs(self.cache_dir, exist_ok=True)
            path = os.path.join(self.cache_dir, key + ".json")
            tmp = path + ".tmp"
            with open(tmp, "w", encoding="utf-8") as fh:
                json.dump({"markdown": markdown}, fh)
            os.replace(tmp, path)
        except OSError:
            pass

    def results(self, query: str, *, country: str | None = None,
                hl: str = "en", num: int = 10,
                limit: int = 10) -> list[Result]:
        params = {"q": query, "hl": hl, "num": str(num)}
        if country:
            params["gl"] = country.lower()
        url = "https://www.google.com/search?" + urllib.parse.urlencode(params)
        payload = {"zone": os.environ.get(ZONE_ENV, DEFAULT_ZONE),
                   "url": url, "format": "raw", "data_format": "markdown"}
        if country:
            payload["country"] = country.lower()

        key = self._key(payload)
        cached = self._read(key)
        if cached is not None:
            self.cached += 1
            return parse_markdown(cached, limit=limit)
        if self.offline:
            raise SerpOffline(f"offline: no cached SERP for {query!r}")

        body = json.dumps(payload).encode("utf-8")
        request = urllib.request.Request(
            BASE, data=body, method="POST",
            headers={"Authorization": f"Bearer {token()}",
                     "Content-Type": "application/json"})
        delay = 1.0
        last = ""
        for attempt in range(1, 5):
            try:
                with urllib.request.urlopen(
                        request, timeout=self.timeout,
                        context=ssl.create_default_context()) as response:
                    markdown = response.read().decode("utf-8", "replace")
                self.calls += 1
                # An empty body is a failure the vendor returns with a 200.
                # Caching it turns one bad response into a permanent one:
                # `keyword research tool` returned nothing, was cached, and
                # every retry replayed the emptiness rather than asking
                # again. Only a page with something on it is worth keeping.
                if len(markdown) < MIN_BODY:
                    last = f"empty body ({len(markdown)} bytes)"
                    if attempt == 4:
                        raise SerpError(last) from None
                    time.sleep(delay)
                    delay *= 2
                    continue
                self._write(key, markdown)
                return parse_markdown(markdown, limit=limit)
            except urllib.error.HTTPError as exc:
                last = f"HTTP {exc.code}: {exc.read().decode('utf-8','replace')[:200]}"
                if exc.code not in (429, 500, 502, 503, 504) or attempt == 4:
                    raise SerpError(last) from None
            except (urllib.error.URLError, TimeoutError, ssl.SSLError) as exc:
                last = f"network error: {exc}"
                if attempt == 4:
                    raise SerpError(last) from None
            time.sleep(delay)
            delay *= 2
        raise SerpError(last or "serp failed")


def plausible_vendors(results: Sequence[Result]) -> list[Result]:
    """Drop the hosts that rank everywhere and sell nothing."""
    return [r for r in results
            if not any(r.domain == bad or r.domain.endswith("." + bad)
                       for bad in NON_VENDOR)]
