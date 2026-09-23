"""Who actually ranks for a search — the bridge from a word to a business,
and the first page a newcomer would have to beat.

Two uses.

**Finding the businesses.** The most valuable thing this skill can do with
$0.09 is spend it on `for-site` against a company that is already selling
into the market, rather than on `for-keywords` against a string. Measured on
the same market, at the same price:

    expand "epcr"          ->    31 keywords,   2,100 searches a month
    for-site eso.com       ->   619 keywords, 367,940 searches a month

`for-keywords` expands off the *breadth of a string*; `for-site` expands off
what a live business is *about*, and a business that has invested in ranking
is evidence that someone is selling here. Invented keywords are hypotheses;
harvested ones are observed commercial vocabulary.

**Reading page one.** How hard a search is to win is decided by what already
answers it. A first page of specialist firms is a fight; a first page with a
Facebook post and a press release on it is a door left open — the weak-spot
heuristic every niche builder and SERP analyst uses (it-23).

Both come from DataForSEO's SERP API through `seo.Seo`, so every page is
cached, counted in the ledger and held to the run's budget. This module used
to scrape Google's rendered page through Bright Data and parse the organic
results back out of markdown; that broke the rule that the skill runs on
Jev and DataForSEO alone, and the structured response carries what the
markdown could not — the ads, the AI overview, the forum and video blocks,
each typed.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

import seo as SEO

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
    """Replay-only mode and this page was never fetched."""


@dataclass
class Result:
    rank: int
    title: str
    domain: str
    url: str
    snippet: str
    kind: str = ""            # filled by judge.pick_sellers / read_page_one
    kind_confidence: float = 0.0

    def as_dict(self) -> dict:
        return {"rank": self.rank, "title": self.title, "domain": self.domain,
                "url": self.url, "snippet": self.snippet, "kind": self.kind,
                "kind_confidence": round(self.kind_confidence, 3)}


def _registrable(host: str) -> str:
    """Strip www and a leading subdomain that carries no identity."""
    host = host.lower().strip().rstrip("/")
    for prefix in ("www.", "m.", "en."):
        if host.startswith(prefix):
            host = host[len(prefix):]
    return host


def organic(rows: Sequence[dict], *, limit: int = 10) -> list[Result]:
    """The organic results on a page, ranked from one, as Results."""
    out: list[Result] = []
    for row in rows:
        if row.get("type") != "organic" or not row.get("domain"):
            continue
        out.append(Result(rank=len(out) + 1, title=row.get("title") or "",
                          domain=_registrable(row["domain"]),
                          url=row.get("url") or "",
                          snippet=row.get("description") or ""))
        if len(out) >= limit:
            break
    return out


def organic_rows(rows: Sequence[dict], *, limit: int = 10) -> list[dict]:
    """The organic results as plain rows — ranked from one, domains without
    `www.` — for the questions and the data files, which want dicts."""
    return [{**r.as_dict(), "description": r.snippet}
            for r in organic(rows, limit=limit)]


def features(rows: Sequence[dict]) -> dict:
    """What Google put on the page besides the organic results.

    Counted, not judged: how many ads (someone pays for this search), and
    whether an AI overview or a question box sits above the results — both
    take clicks before any result is seen.
    """
    types = [r.get("type") or "" for r in rows]
    return {"ads": sum(1 for t in types if t == "paid"),
            "ai_overview": "ai_overview" in types,
            "questions": "people_also_ask" in types,
            "video": any(t in ("video", "short_videos") for t in types),
            "forums": any(t in ("discussions_and_forums", "perspectives")
                          for t in types),
            "advertisers": sorted({_registrable(r["domain"]) for r in rows
                                   if r.get("type") == "paid"
                                   and r.get("domain")})}


class Serp:
    """Page one for a search, from DataForSEO, through the run's own client."""

    def __init__(self, client: SEO.Seo) -> None:
        self.seo = client

    def page(self, query: str) -> list[dict]:
        """Everything on page one — results, ads, features — in order."""
        try:
            return self.seo.serp(query).rows
        except SEO.OfflineMiss as exc:
            raise SerpOffline(str(exc)) from None
        except SEO.SeoError as exc:
            raise SerpError(str(exc)) from None

    def results(self, query: str, *, country: str | None = None,
                hl: str = "en", num: int = 10,
                limit: int = 10) -> list[Result]:
        """The organic results. Location and language are the run's own."""
        return organic(self.page(query), limit=limit)


def plausible_vendors(results: Sequence[Result]) -> list[Result]:
    """Drop the hosts that rank everywhere and sell nothing."""
    return [r for r in results
            if not any(r.domain == bad or r.domain.endswith("." + bad)
                       for bad in NON_VENDOR)]
