"""DataForSEO Google Ads keyword data, with a ledger that never guesses.

Three things this module exists to get right:

1. **Actual cost, not estimated cost.** Every DataForSEO response carries a
   `cost` field — what they really billed. A ledger built from guesses is
   worse than no ledger, because it reads as authoritative. We record the
   number the vendor sent.
2. **Lists stay in Python.** Keyword lists are never rendered into a shell
   string on the way to the API. Word-splitting a multi-word keyword bills
   in full and returns garbage, and the failure is silent.
3. **One call, filled to the brim.** A request bills the same for 1 keyword
   or 1000, so batching is not an optimisation — it is the difference
   between $0.09 and $90.

Stdlib only.
"""

from __future__ import annotations

import base64
import datetime
import hashlib
import json
import os
import ssl
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from typing import Any, Iterable, Sequence

BASE = "https://api.dataforseo.com/v3"
OK = 20000
RETRY_STATUSES = {429, 500, 502, 503, 504}
MAX_ATTEMPTS = 5

# Hard limits imposed by the Google Ads API behind DataForSEO.
MAX_SEEDS = 20          # keywords_for_keywords
MAX_PRICED = 1000       # search_volume
MAX_FORECAST = 1000     # ad_traffic_by_keywords

CRED_ENV = ("DATA_FOR_SEO_LOGIN", "DATA_FOR_SEO_PASSWORD")

# Google Ads keeps four years of monthly history, and DataForSEO returns as
# much of it as `date_from` asks for **at no extra cost** — the same $0.09
# whether the response carries twelve months or forty-eight.
#
# This is not a nicety. With twelve months you cannot separate a trend from
# a season: the window runs September to August, so "the last quarter
# against the first" compares summer to autumn. With forty-eight you can
# compare one complete cycle to the one before it, and the season cancels
# exactly. Not asking for the history was the difference between a real
# growth figure and a seasonal artefact presented as one.
HISTORY_YEARS = 4


def history_start(today: datetime.date | None = None) -> str:
    day = (today or datetime.date.today()).replace(day=1)
    try:
        return day.replace(year=day.year - HISTORY_YEARS).isoformat()
    except ValueError:                       # 29 February
        return day.replace(year=day.year - HISTORY_YEARS, day=28).isoformat()

ENDPOINTS = {
    "expand": "keywords_data/google_ads/keywords_for_keywords/live",
    "price": "keywords_data/google_ads/search_volume/live",
    "site": "keywords_data/google_ads/keywords_for_site/live",
    "forecast": "keywords_data/google_ads/ad_traffic_by_keywords/live",
}

# Exact match, because it is the only honest default. Broad match forecasts
# a much larger click volume by counting searches that merely resemble the
# keyword, which is how a budget that looks like three months of traffic
# turns out to be four days of it.
DEFAULT_MATCH = "exact"


class SeoError(RuntimeError):
    pass


class BudgetExceeded(SeoError):
    """Raised before a call that would breach the run's spend ceiling."""


class OfflineMiss(SeoError):
    """Raised when offline mode is on and the response is not in the cache.

    Evals replay frozen fixtures through this path, so a miss means the
    fixture set is incomplete — never that the eval should quietly bill.
    """


# ------------------------------------------------------------------ credentials

def _read_dotenv(names: Sequence[str]) -> dict[str, str]:
    out: dict[str, str] = {}
    path = os.path.join(os.getcwd(), ".env")
    if not os.path.exists(path):
        return out
    try:
        with open(path, encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, v = line.split("=", 1)
                k = k.strip()
                if k in names:
                    out[k] = v.strip().strip('"').strip("'")
    except OSError:
        pass
    return out


def credentials() -> tuple[str, str]:
    login = (os.environ.get(CRED_ENV[0]) or "").strip()
    password = (os.environ.get(CRED_ENV[1]) or "").strip()
    if not login or not password:
        found = _read_dotenv(CRED_ENV)
        login = login or found.get(CRED_ENV[0], "")
        password = password or found.get(CRED_ENV[1], "")
    if not login or not password:
        raise SeoError(
            "missing DataForSEO credentials: set DATA_FOR_SEO_LOGIN and "
            "DATA_FOR_SEO_PASSWORD (https://app.dataforseo.com/api-access)")
    return login, password


def available() -> bool:
    try:
        credentials()
        return True
    except SeoError:
        return False


# ------------------------------------------------------------------ the ledger

@dataclass
class Call:
    """One probe. `cost_usd` is what DataForSEO said it billed, not a guess."""

    action: str
    endpoint: str
    task: dict
    rows: list[dict]
    cost_usd: float
    from_cache: bool
    seconds: float
    note: str = ""

    def as_dict(self) -> dict:
        return {
            "action": self.action,
            "endpoint": self.endpoint,
            "inputs": (len(self.task.get("keywords") or [])
                       or (1 if self.task.get("target") else 0)),
            "rows": len(self.rows),
            "cost_usd": round(self.cost_usd, 4),
            "from_cache": self.from_cache,
            "seconds": round(self.seconds, 2),
            "note": self.note,
        }


@dataclass
class Ledger:
    calls: list[Call] = field(default_factory=list)

    @property
    def spent_usd(self) -> float:
        return sum(c.cost_usd for c in self.calls)

    @property
    def billable(self) -> int:
        return sum(1 for c in self.calls if not c.from_cache)

    @property
    def rows(self) -> int:
        return sum(len(c.rows) for c in self.calls)

    def as_dict(self) -> dict:
        return {
            "calls": [c.as_dict() for c in self.calls],
            "billable_calls": self.billable,
            "cached_calls": len(self.calls) - self.billable,
            "rows_returned": self.rows,
            "spent_usd": round(self.spent_usd, 4),
        }

    def line(self) -> str:
        return (f"dataforseo: {self.billable} billable call(s) "
                f"(+{len(self.calls) - self.billable} cached) · "
                f"{self.rows:,} rows · ${self.spent_usd:.4f} actual")


# ------------------------------------------------------------------ the client

def _clean(keywords: Iterable[str]) -> list[str]:
    """Normalise a keyword list the way Google Ads will anyway.

    Deduplicating here is free; deduplicating after the call is not.
    """
    seen: set[str] = set()
    out: list[str] = []
    for raw in keywords:
        k = " ".join(str(raw).split()).strip().lower()
        if not k or k in seen:
            continue
        seen.add(k)
        out.append(k)
    return out


def _trend(monthly: list[dict] | None) -> tuple[list[int], list[str]]:
    """The 12-month series, oldest first, with its month labels.

    The labels matter: "peaks at 3x the average" is a statistic, "peaks in
    November" is something a reader can act on, and the difference costs
    nothing to keep.
    """
    if not monthly:
        return [], []
    ordered = sorted(
        (m for m in monthly if m.get("search_volume") is not None),
        key=lambda m: (m.get("year") or 0, m.get("month") or 0))
    volumes = [int(m.get("search_volume") or 0) for m in ordered]
    labels = [f"{m.get('year')}-{int(m.get('month') or 0):02d}" for m in ordered]
    return volumes, labels


def normalise_forecast(result: list[dict] | None) -> list[dict]:
    """The one aggregate row this endpoint returns.

    Not one row per keyword — Google forecasts the campaign, not the term.
    One row carrying clicks a month, what each would actually cost, and the
    total. The gap between the bid you set and the `average_cpc` you get
    back is the auction telling you that you do not pay your maximum.
    """
    for r in result or []:
        clicks = r.get("clicks")
        if clicks is None:
            continue
        return [{
            "clicks": float(clicks),
            "cpc": float(r.get("average_cpc") or 0.0),
            "cost": float(r.get("cost") or 0.0),
            "impressions": float(r.get("impressions") or 0.0),
            "ctr": float(r.get("ctr") or 0.0),
            "bid": float(r.get("bid") or 0.0),
            "match": r.get("match") or "",
            "window": r.get("date_interval") or "next_month",
        }]
    return []


def normalise(result: list[dict] | None, source: str) -> list[dict]:
    rows = []
    for r in result or []:
        term = (r.get("keyword") or "").strip().lower()
        if not term:
            continue
        trend, months = _trend(r.get("monthly_searches"))
        rows.append({
            "term": term,
            "volume": int(r.get("search_volume") or 0),
            "cpc": float(r.get("cpc") or 0.0),
            "competition_index": r.get("competition_index"),
            "low_bid": float(r.get("low_top_of_page_bid") or 0.0),
            "high_bid": float(r.get("high_top_of_page_bid") or 0.0),
            "trend": trend,
            "months": months,
            "source": source,
        })
    return rows


class Seo:
    """A budgeted, cached DataForSEO client.

    `max_spend_usd` is checked *before* each billable call, so the ceiling is
    a promise rather than a report. Cached replays cost nothing and are never
    counted against it.
    """

    def __init__(
        self,
        *,
        cache_dir: str,
        location: str | int = "United States",
        language: str = "en",
        max_spend_usd: float = 1.00,
        offline: bool = False,
        timeout: int = 180,
    ) -> None:
        self.cache_dir = cache_dir
        self.location = location
        self.language = language
        self.max_spend_usd = max_spend_usd
        self.offline = offline
        self.timeout = timeout
        self.ledger = Ledger()
        self._auth: str | None = None

    # -- wire ------------------------------------------------------------

    def _header(self) -> str:
        if self._auth is None:
            login, password = credentials()
            self._auth = "Basic " + base64.b64encode(
                f"{login}:{password}".encode("utf-8")).decode("ascii")
        return self._auth

    def _geo(self, task: dict, *, history: bool = True) -> dict:
        # The forecast endpoint looks forward and rejects `date_from`
        # outright, which is right: there is no history to ask for in a
        # prediction. Every other keyword endpoint takes it and hands back
        # four years for the price of one.
        if history:
            task.setdefault("date_from", history_start())
        if isinstance(self.location, int):
            task["location_code"] = self.location
        elif self.location:
            task["location_name"] = self.location
        if self.language and len(self.language) <= 3:
            task["language_code"] = self.language
        elif self.language:
            task["language_name"] = self.language
        return task

    def _key(self, endpoint: str, task: dict) -> str:
        blob = json.dumps({"endpoint": endpoint, "task": task}, sort_keys=True)
        return hashlib.sha256(blob.encode("utf-8")).hexdigest()

    def _cached(self, key: str) -> dict | None:
        path = os.path.join(self.cache_dir, key + ".json")
        if not os.path.exists(path):
            return None
        try:
            with open(path, encoding="utf-8") as fh:
                return json.load(fh)
        except (OSError, ValueError):
            return None

    def _store(self, key: str, body: dict) -> None:
        try:
            os.makedirs(self.cache_dir, exist_ok=True)
            path = os.path.join(self.cache_dir, key + ".json")
            tmp = path + ".tmp"
            with open(tmp, "w", encoding="utf-8") as fh:
                json.dump(body, fh)
            os.replace(tmp, path)
        except OSError:
            pass

    def _post(self, endpoint: str, task: dict) -> dict:
        payload = json.dumps([task]).encode("utf-8")
        url = f"{BASE}/{endpoint}"
        ctx = ssl.create_default_context()
        delay = 1.0
        last = ""
        for attempt in range(1, MAX_ATTEMPTS + 1):
            req = urllib.request.Request(
                url, data=payload, method="POST",
                headers={"Authorization": self._header(),
                         "Content-Type": "application/json"})
            try:
                with urllib.request.urlopen(req, timeout=self.timeout,
                                            context=ctx) as resp:
                    return json.loads(resp.read().decode("utf-8"))
            except urllib.error.HTTPError as exc:
                body = exc.read().decode("utf-8", "replace")[:400]
                last = f"HTTP {exc.code}: {body}"
                if exc.code not in RETRY_STATUSES or attempt == MAX_ATTEMPTS:
                    raise SeoError(last) from None
            except (urllib.error.URLError, TimeoutError, ssl.SSLError) as exc:
                last = f"network error: {exc}"
                if attempt == MAX_ATTEMPTS:
                    raise SeoError(last) from None
            time.sleep(delay)
            delay = min(delay * 2, 16.0)
        raise SeoError(last or "request failed")

    @staticmethod
    def _unwrap(response: dict) -> tuple[list[dict], float]:
        """Both status levels, then the cost the vendor actually charged."""
        top = response.get("status_code")
        if top != OK:
            raise SeoError(f"api error {top}: {response.get('status_message')}")
        tasks = response.get("tasks") or []
        if not tasks:
            raise SeoError("api returned no tasks")
        task = tasks[0]
        if task.get("status_code") != OK:
            raise SeoError(
                f"task error {task.get('status_code')}: "
                f"{task.get('status_message')}")
        cost = response.get("cost")
        if cost is None:
            cost = task.get("cost")
        return (task.get("result") or []), float(cost or 0.0)

    # -- probes ----------------------------------------------------------

    def _run(self, action: str, endpoint: str, task: dict,
             source: str, note: str = "") -> Call:
        key = self._key(endpoint, task)
        started = time.time()
        cached = self._cached(key)
        shape = normalise_forecast if action == "forecast" else (
            lambda r: normalise(r, source))
        if cached is not None:
            result, billed = self._unwrap(cached)
            call = Call(action, endpoint, task, shape(result),
                        0.0, True, time.time() - started,
                        note or f"cached (would have cost ${billed:.4f})")
            self.ledger.calls.append(call)
            return call

        if self.offline:
            raise OfflineMiss(
                f"offline: no cached response for {action} "
                f"({json.dumps(task, sort_keys=True)[:160]})")

        # The ceiling is checked before the money moves, not after.
        worst_case = 0.10
        if self.ledger.spent_usd + worst_case > self.max_spend_usd:
            raise BudgetExceeded(
                f"would exceed --max-spend ${self.max_spend_usd:.2f} "
                f"(spent ${self.ledger.spent_usd:.4f}, next call up to "
                f"${worst_case:.2f})")

        response = self._post(endpoint, task)
        result, billed = self._unwrap(response)
        self._store(key, response)
        call = Call(action, endpoint, task, shape(result),
                    billed, False, time.time() - started, note)
        self.ledger.calls.append(call)
        return call

    def expand(self, seeds: Sequence[str]) -> Call:
        """Ask Google for keyword ideas around up to 20 seeds.

        Expansion scales with how *broad* the seed is: a head term returns
        thousands, a long-tail seed sometimes returns only itself. That is a
        property of Google's data, not a bug to retry around.
        """
        kws = _clean(seeds)[:MAX_SEEDS]
        if not kws:
            raise SeoError("expand needs at least one seed")
        task = self._geo({"keywords": kws})
        return self._run("expand", ENDPOINTS["expand"], task, "expanded")

    def price(self, keywords: Sequence[str]) -> Call:
        """Price up to 1000 exact terms in one billable call.

        This is the cheapest hypothesis test available: 1000 guesses about
        what people search, answered for the price of one.
        """
        kws = _clean(keywords)[:MAX_PRICED]
        if not kws:
            raise SeoError("price needs at least one keyword")
        task = self._geo({"keywords": kws})
        return self._run("price", ENDPOINTS["price"], task, "priced")

    def site(self, target: str, target_type: str = "site") -> Call:
        """Every keyword Google thinks a domain or page is relevant to."""
        target = target.strip().lower().removeprefix("https://") \
            .removeprefix("http://").removeprefix("www.").rstrip("/")
        if not target:
            raise SeoError("site needs a domain")
        task = self._geo({"target": target, "target_type": target_type})
        return self._run("site", ENDPOINTS["site"], task, f"site:{target}")

    def forecast(self, keywords: Sequence[str], *, bid: float,
                 match: str = DEFAULT_MATCH) -> Call:
        """What these keywords would actually deliver at a given bid.

        Search volume says how many people look; this says how many of them
        you could buy and what they would cost — Google's own forecast, not
        volume multiplied by a published click price. The difference is the
        gap between "there are 165,000 searches a month here" and "you can
        have 311 clicks of it".

        The bid is not invented: callers derive it from the top-of-page bids
        already measured on the keywords being forecast.
        """
        kws = _clean(keywords)[:MAX_FORECAST]
        if not kws:
            raise SeoError("forecast needs at least one keyword")
        task = self._geo({"keywords": kws, "bid": round(float(bid), 2),
                          "match": match}, history=False)
        return self._run("forecast", ENDPOINTS["forecast"], task, "forecast",
                         note=f"at ${bid:.2f} {match} match")

    # -- planning --------------------------------------------------------

    def is_cached(self, action: str, task_seed: dict) -> bool:
        endpoint = ENDPOINTS[action]
        return self._cached(self._key(endpoint, self._geo(dict(task_seed)))) is not None
