"""The keyword graph: what was measured, and what can be computed from it.

This module is deliberately judgment-free. Everything here is arithmetic —
sums, medians, ratios, slopes, counts. Not one function decides whether a
number is *high*, *interesting*, or *worth reporting*, because every such
decision is a constant someone invented, and an invented constant is the
easiest thing in a method to vary. Those decisions belong to Jev.

The shape:

    keyword --ABOUT--> topic     (a thing people search for)
    keyword --SERVES--> job      (what they are trying to do)
    keyword --NAMES--> entity    (a brand already in the sentence)

Topics are mined from the corpus, jobs come from a fixed universal taxonomy,
entities are mined and confirmed. A (topic, job) pair is a *cell*, and a cell
is the unit an insight is about: "people searching for X in order to Y".
"""

from __future__ import annotations

import json
import math
import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field, asdict
from typing import Iterable, Sequence

# --------------------------------------------------------------------------
# The job taxonomy.
#
# Fixed, small, and universal: these are the things a person can be doing at
# a search box, in any market, in any vertical. A taxonomy mined per-run
# would be easy to vary — you could always find one that flattered the data.
# This one has to survive every market it meets, which is the point.
#
# The criteria are written for a literal reader: each says what the searcher
# wants, not how the phrase is worded, because wording is the one thing that
# does not generalise across markets.
# --------------------------------------------------------------------------

JOBS: dict[str, str] = {
    "buy": "Wants to obtain the thing — looking at prices, plans, vendors, "
           "where to get it, or is ready to sign up or order",
    "compare": "Has options and is choosing between them — weighing one "
               "against another, looking for the best one, or for reviews, "
               "rankings or alternatives",
    "learn": "Wants to understand the thing — what it is, how it works, why "
             "it matters, or how to do it",
    "self_serve": "Wants to solve the problem without buying anything — a "
                  "free version, a template, a manual method, or a way to do "
                  "it themselves",
    "fix": "Something they already have is broken, failing, or behaving "
           "wrongly, and they want it working again",
    "local": "Wants a provider, supplier or premises they can physically "
             "reach — a place, an area, or someone nearby",
    "career": "Wants work, pay or credentials in this field — a job, a "
              "salary figure, a course, a certification or a qualification",
    "brand_desk": "Wants one named company's own counter — its login, its "
                  "account page, its support line, its app download, or its "
                  "official site",
}

JOB_ORDER = list(JOBS)

JOB_LABELS: dict[str, str] = {
    "buy": "shopping for it",
    "compare": "choosing between options",
    "learn": "trying to understand it",
    "self_serve": "trying to do it without buying anything",
    "fix": "fixing something that already broke",
    "local": "looking for someone nearby",
    "career": "chasing work or qualifications",
    "brand_desk": "going to one company's own front door",
}

MONTHS = ("January", "February", "March", "April", "May", "June", "July",
          "August", "September", "October", "November", "December")


def month_name(label: str) -> str:
    """'2025-11' -> 'November'. Jev reads dates as text, so code does this."""
    try:
        return MONTHS[int(label.split("-")[1]) - 1]
    except (ValueError, IndexError):
        return label

# Modifiers that exist in every English search market. These are never used to
# classify anything — they are probe candidates, the blind spots a run can pay
# one call to test. See `probe_candidates`.
UNIVERSAL_FACETS: tuple[str, ...] = (
    "pricing", "cost", "free", "cheap", "best", "top", "alternative",
    "alternatives", "vs", "review", "reviews", "comparison", "how to",
    "what is", "guide", "tutorial", "template", "examples", "software",
    "app", "tool", "online", "near me", "for small business", "enterprise",
    "for teams", "jobs", "salary", "course", "certification", "login",
    "demo", "trial", "open source", "api", "integration", "automation",
)

STOPWORDS: frozenset[str] = frozenset("""
a an the and or of for to in on at by with from is are be was were do does
did how what why when where which who whom this that these those it its as
i you your my me we our us they them he she his her not no if then than so
such can could should would will shall may might must have has had
""".split())


# --------------------------------------------------------------------------
# Nodes
# --------------------------------------------------------------------------

@dataclass
class Keyword:
    term: str
    volume: int = 0
    cpc: float = 0.0
    competition_index: int | None = None
    low_bid: float = 0.0
    high_bid: float = 0.0
    trend: list[int] = field(default_factory=list)
    months: list[str] = field(default_factory=list)
    source: str = ""
    # Assigned during Orient. `None` means not yet judged, which is different
    # from judged-and-unassignable ("" / "none").
    topic: str | None = None
    topic_confidence: float = 0.0
    job: str | None = None
    job_confidence: float = 0.0
    # Judged *and* distinguishable. A head term like "project management
    # software" genuinely does not reveal what the searcher wants, and the
    # model says so by returning low confidence. Building cells on those
    # assignments would launder that uncertainty into a confident-looking
    # number, so they are kept, reported, and left out of the analysis.
    job_certain: bool = False
    entities: list[str] = field(default_factory=list)

    @property
    def money(self) -> float:
        """Monthly advertiser spend implied if every search were bought once.

        Not a forecast — a comparable. Volume alone ranks attention; this
        ranks where attention is already being paid for.
        """
        return self.volume * self.cpc

    @property
    def judged(self) -> bool:
        return self.job is not None


@dataclass
class Topic:
    name: str
    kind: str = "mined"          # seed | mined | probed
    confirmed: bool = False      # Jev said this names a thing, not a modifier


@dataclass
class Entity:
    name: str
    confirmed: bool = False


# --------------------------------------------------------------------------
# Arithmetic helpers — the whole vocabulary of this module
# --------------------------------------------------------------------------

def median(values: Sequence[float]) -> float:
    vals = sorted(v for v in values if v is not None)
    if not vals:
        return 0.0
    mid = len(vals) // 2
    if len(vals) % 2:
        return float(vals[mid])
    return (vals[mid - 1] + vals[mid]) / 2.0


def share(part: float, whole: float) -> float:
    return (part / whole) if whole else 0.0


def direction_is_unmeasurable() -> str:
    """Why this module offers no growth figure.

    DataForSEO returns exactly twelve months, and for this account they run
    September to August. So the "last quarter" is June-July-August and the
    "first quarter" is September-October-November: different parts of the
    year, nine months apart, not the same quarter a year earlier.

    A ratio between them is a seasonal comparison wearing the clothes of a
    trend. On `garden rooms` it read as a market shrinking to 0.88x, when
    September is the highest month of the entire series — the builder would
    have been told demand was falling as they bought ads in the peak month.

    Twelve months of data cannot separate trend from season: one full cycle
    gives you the shape of the year and nothing about the level between
    years, and a least-squares slope over exactly one period still varies
    with where in the cycle the window happens to start. There is no fix
    inside this data, so there is no growth claim. `seasonality` below is
    what twelve months *can* honestly support.
    """
    return ("A twelve-month window shows the shape of a year, not the "
            "change between years, so no growth figure is reported.")


def seasonality(trend: Sequence[int]) -> float | None:
    """Peak month over mean month. 1.0 is flat; 3.0 means a real season."""
    if len(trend) < 12:
        return None
    mean = sum(trend) / len(trend)
    if mean <= 0:
        return None
    return max(trend) / mean


def concentration(values: Sequence[float]) -> float:
    """Herfindahl index over a set of shares: 1.0 = one node holds it all."""
    total = sum(values)
    if total <= 0:
        return 0.0
    return sum((v / total) ** 2 for v in values)


def click_price(keywords: Sequence[Keyword]) -> float:
    """What a click costs here, weighted by how often each term is searched.

    A plain median over the keywords answers the wrong question. "garden
    studios" had 62 of its 81 keywords at no cost — long-tail terms nobody
    bids on — so its median click read $0.00 while its head term, carrying
    most of the searching, went for $3.80. Weighting by volume gives the
    number an advertiser is actually exposed to.
    """
    total = sum(k.volume for k in keywords)
    if total <= 0:
        return median([k.cpc for k in keywords])
    return sum(k.volume * k.cpc for k in keywords) / total


def weighted_trend(keywords: Sequence[Keyword]) -> list[int]:
    """Volume-weighted 12-month series for a group, as absolute searches."""
    series = [k.trend for k in keywords if len(k.trend) == 12]
    if not series:
        return []
    return [sum(col) for col in zip(*series)]


# --------------------------------------------------------------------------
# Mining: proposing candidates, never selecting them
# --------------------------------------------------------------------------

def tokens(term: str) -> list[str]:
    return [t for t in re.split(r"[^a-z0-9+#]+", term.lower()) if t]


def ngrams(term: str, lo: int = 1, hi: int = 3) -> list[str]:
    toks = tokens(term)
    out = []
    for n in range(lo, hi + 1):
        for i in range(len(toks) - n + 1):
            gram = toks[i:i + n]
            if gram[0] in STOPWORDS or gram[-1] in STOPWORDS:
                continue
            out.append(" ".join(gram))
    return out


def mine_phrases(keywords: Iterable[Keyword], *, limit: int = 40) -> list[str]:
    """Volume-weighted n-gram candidates, most-searched first.

    These are *candidates*. Whether a phrase names a thing people want or
    merely narrows one is a question about meaning, so Jev answers it.
    """
    weight: Counter[str] = Counter()
    docs: Counter[str] = Counter()
    for kw in keywords:
        seen = set(ngrams(kw.term))
        for gram in seen:
            weight[gram] += max(kw.volume, 1)
            docs[gram] += 1
    # A phrase appearing in exactly one keyword describes that keyword, not a
    # group, so it cannot be a cluster. This is a structural fact, not a
    # tuned threshold.
    ranked = [g for g, _ in weight.most_common() if docs[g] >= 2]
    return ranked[:limit]


def mine_entities(keywords: Iterable[Keyword], *, limit: int = 30) -> list[str]:
    """Single tokens that look like they might name a company.

    Deliberately over-inclusive: recall here is cheap and precision is Jev's
    job. Anything that is a dictionary-common word across many unrelated
    keywords is still offered — Jev will reject it.
    """
    weight: Counter[str] = Counter()
    for kw in keywords:
        for tok in tokens(kw.term):
            if tok in STOPWORDS or len(tok) < 3 or tok.isdigit():
                continue
            weight[tok] += max(kw.volume, 1)
    return [t for t, _ in weight.most_common(limit * 3)][:limit]


# Facets that read naturally in front of a phrase. Which side a modifier
# goes is irrelevant to the answer — Google normalises word order and
# returns identical metrics for "garden rooms pricing" and "pricing garden
# rooms" — but it is not irrelevant to the bill. Emitting both spent half of
# every thousand-slot probe asking the same question twice.
PREFIX_FACETS = frozenset({
    "best", "top", "free", "cheap", "how to", "what is", "open source",
    "diy", "manual", "bespoke", "enterprise",
})


def probe_candidates(topics: Sequence[str], facets: Sequence[str],
                     known: set[str], *, limit: int = 1000) -> list[str]:
    """Topic x facet combinations nobody has measured yet.

    This is the cheapest hypothesis test in the whole method: up to a
    thousand guesses about what people search, answered for the price of
    one. Each pair is emitted once — see PREFIX_FACETS — so the slots go to
    a thousand different questions rather than five hundred asked twice.

    Ordering is deterministic so a repeat run hits the cache.
    """
    out: list[str] = []
    seen: set[str] = set()
    for topic in topics:
        for facet in facets:
            if facet in topic:
                continue
            term = (f"{facet} {topic}" if facet in PREFIX_FACETS
                    else f"{topic} {facet}")
            term = " ".join(term.split()).lower()
            if term in known or term in seen:
                continue
            seen.add(term)
            out.append(term)
            if len(out) >= limit:
                return out
    return out


# --------------------------------------------------------------------------
# The graph
# --------------------------------------------------------------------------

def K_tokens(term: str) -> list[str]:
    return tokens(term)


@dataclass
class Cell:
    """People searching for `topic` in order to `job`. The unit of insight."""

    topic: str
    job: str
    keywords: list[Keyword]

    @property
    def volume(self) -> int:
        return sum(k.volume for k in self.keywords)

    @property
    def money(self) -> float:
        return sum(k.money for k in self.keywords)

    @property
    def click_price(self) -> float:
        return click_price(self.keywords)

    @property
    def max_cpc(self) -> float:
        return max((k.cpc for k in self.keywords), default=0.0)

    @property
    def max_bid(self) -> float:
        return max((k.high_bid for k in self.keywords), default=0.0)

    @property
    def branded(self) -> int:
        return sum(1 for k in self.keywords if k.entities)

    @property
    def branded_volume(self) -> int:
        return sum(k.volume for k in self.keywords if k.entities)

    def top(self, n: int = 5) -> list[Keyword]:
        return sorted(self.keywords, key=lambda k: -k.volume)[:n]


class Graph:
    def __init__(self, seed: str, geo: str = "", language: str = "") -> None:
        self.seed = seed.strip().lower()
        self.geo = geo
        self.language = language
        self.keywords: dict[str, Keyword] = {}
        self.topics: dict[str, Topic] = {}
        self.entities: dict[str, Entity] = {}
        self.iterations: list[dict] = []
        self.collapsed = 0
        self.add_topic(self.seed, kind="seed", confirmed=True)

    # -- mutation ---------------------------------------------------------

    def add_rows(self, rows: Iterable[dict]) -> int:
        """Merge measured rows, collapsing word-order permutations.

        Google returns "garden rooms" and "rooms garden" as separate
        keywords with identical volume and identical click price, because it
        normalises word order and reports the same aggregate for both.
        Counting both inflates a market: 16% of the `garden rooms` corpus
        and 42% of one probe's results were the same searches counted twice.

        Whichever ordering is kept, the metrics are the same, so the choice
        of survivor does not change any number — only the double-count does.
        """
        added = 0
        by_shape: dict[tuple[str, ...], str] = {}
        for term in self.keywords:
            by_shape.setdefault(tuple(sorted(term.split())), term)
        for row in rows:
            term = row["term"]
            shape = tuple(sorted(term.split()))
            kept = by_shape.get(shape)
            if kept is not None and kept != term:
                self.collapsed += 1
                continue
            by_shape.setdefault(shape, term)
            existing = self.keywords.get(term)
            if existing is None:
                self.keywords[term] = Keyword(**row)
                added += 1
            else:
                # Later measurements can carry a trend the first one lacked.
                if not existing.trend and row.get("trend"):
                    existing.trend = row["trend"]
                    existing.months = row.get("months") or []
                if existing.volume == 0 and row.get("volume"):
                    existing.volume = row["volume"]
                if existing.cpc == 0 and row.get("cpc"):
                    existing.cpc = row["cpc"]
        return added

    def drop(self, terms: Iterable[str]) -> int:
        """Undo a measurement that answered nothing.

        A branch that went nowhere is not neutral — its keywords stay in the
        corpus, crowd out the ones that matter when the next batch is
        judged, and drag the market's medians toward a market nobody asked
        about. Discarding the tangent is what a person does when a lead goes
        cold, and it is the difference between backtracking and merely
        noting that you did not like the answer.

        Keywords that were already known before the probe are kept.
        """
        gone = 0
        for term in terms:
            if self.keywords.pop(term, None) is not None:
                gone += 1
        live = {t for k in self.keywords for t in K_tokens(k)}
        for name in [e for e in self.entities if e not in live]:
            self.entities.pop(name, None)
        return gone

    def add_topic(self, name: str, *, kind: str = "mined",
                  confirmed: bool = False) -> None:
        name = " ".join(name.split()).lower()
        if not name:
            return
        node = self.topics.get(name)
        if node is None:
            self.topics[name] = Topic(name, kind, confirmed)
        else:
            node.confirmed = node.confirmed or confirmed

    def add_entity(self, name: str, *, confirmed: bool = False) -> None:
        name = name.strip().lower()
        if not name:
            return
        node = self.entities.get(name)
        if node is None:
            self.entities[name] = Entity(name, confirmed)
        else:
            node.confirmed = node.confirmed or confirmed

    # -- reading ----------------------------------------------------------

    @property
    def confirmed_topics(self) -> list[str]:
        """Confirmed topics, minus the two kinds that are not topics at all.

        **A brand is not a topic**, and neither is a phrase carrying one.
        If "asana" or "asana project management" anchors a cluster, every
        keyword in that cluster contains the word "asana", and the finding
        "this cluster's searching names a company outright" is true by
        construction. A circular finding is worse than no finding, because
        it survives every test that checks whether a claim fits its data.

        **A fragment is not a topic.** Mining n-grams turns up "management"
        and "software" alongside "task management" — the shorter phrase is
        the longer one with its meaning removed, and keeping both splits one
        cluster across two nodes. The most specific phrase wins, which is a
        fact about the strings rather than a threshold.
        """
        brands = {e.name for e in self.entities.values() if e.confirmed}
        names = [t.name for t in self.topics.values()
                 if t.confirmed and not (brands & set(tokens(t.name)))]
        return [t for t in names
                if not any(t != o and t in o for o in names)]

    @property
    def confirmed_entities(self) -> list[str]:
        return [e.name for e in self.entities.values() if e.confirmed]

    @property
    def total_volume(self) -> int:
        return sum(k.volume for k in self.keywords.values())

    @property
    def total_money(self) -> float:
        return sum(k.money for k in self.keywords.values())

    @property
    def judged(self) -> list[Keyword]:
        """Asked about — whatever the answer was."""
        return [k for k in self.keywords.values() if k.judged]

    @property
    def certain(self) -> list[Keyword]:
        """Asked about, and the answer was distinguishable.

        Everything downstream of here builds on `certain`, not `judged`.
        """
        return [k for k in self.keywords.values()
                if k.judged and k.job_certain]

    @property
    def judged_volume(self) -> int:
        return sum(k.volume for k in self.judged)

    @property
    def certain_volume(self) -> int:
        return sum(k.volume for k in self.certain)

    @property
    def market_click_price(self) -> float:
        """What a click costs across the whole market, weighted by searching."""
        return click_price([k for k in self.keywords.values() if k.volume > 0])

    def containment_topics(self, term: str) -> list[str]:
        """Topics literally present in the keyword.

        Substring containment is a fact about the string, so code settles it.
        Only the ambiguous residue — nothing matched, or several did — is a
        question about meaning, and that goes to Jev.
        """
        return [t for t in self.confirmed_topics if t and t in term]

    def cells(self, *, min_keywords: int = 1) -> list[Cell]:
        buckets: dict[tuple[str, str], list[Keyword]] = defaultdict(list)
        for kw in self.certain:
            if not kw.topic or kw.topic in ("", "none"):
                continue
            buckets[(kw.topic, kw.job)].append(kw)
        out = [Cell(t, j, kws) for (t, j), kws in buckets.items()
               if len(kws) >= min_keywords]
        return sorted(out, key=lambda c: (-c.volume, c.topic, c.job))

    def topic_rows(self) -> list[dict]:
        """One row per topic: the arithmetic, and nothing more."""
        by_topic: dict[str, list[Keyword]] = defaultdict(list)
        for kw in self.certain:
            if kw.topic and kw.topic not in ("", "none"):
                by_topic[kw.topic].append(kw)
        rows = []
        for topic, kws in by_topic.items():
            vol = sum(k.volume for k in kws)
            trend = weighted_trend(kws)
            job_vol = Counter()
            for k in kws:
                job_vol[k.job] += k.volume
            rows.append({
                "topic": topic,
                "keywords": len(kws),
                "volume": vol,
                "money": round(sum(k.money for k in kws), 2),
                "click_price": round(click_price(kws), 2),
                "max_high_bid": round(max((k.high_bid for k in kws),
                                          default=0.0), 2),
                "branded_volume": sum(k.volume for k in kws if k.entities),
                "branded_share": round(share(
                    sum(k.volume for k in kws if k.entities), vol), 3),
                "job_mix": {j: round(share(v, vol), 3)
                            for j, v in job_vol.most_common()},
                "job_concentration": round(concentration(
                    list(job_vol.values())), 3),
                "seasonality": (round(seasonality(trend), 2)
                                if seasonality(trend) is not None else None),
            })
        return sorted(rows, key=lambda r: -r["volume"])

    # -- persistence ------------------------------------------------------

    def to_dict(self) -> dict:
        return {
            "seed": self.seed,
            "geo": self.geo,
            "language": self.language,
            "keywords": [asdict(k) for k in self.keywords.values()],
            "topics": [asdict(t) for t in self.topics.values()],
            "entities": [asdict(e) for e in self.entities.values()],
            "iterations": self.iterations,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Graph":
        g = cls(data["seed"], data.get("geo", ""), data.get("language", ""))
        for k in data.get("keywords", []):
            g.keywords[k["term"]] = Keyword(**k)
        for t in data.get("topics", []):
            g.topics[t["name"]] = Topic(**t)
        for e in data.get("entities", []):
            g.entities[e["name"]] = Entity(**e)
        g.iterations = data.get("iterations", [])
        return g

    def save(self, path: str) -> None:
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(self.to_dict(), fh, indent=2)

    @classmethod
    def load(cls, path: str) -> "Graph":
        with open(path, encoding="utf-8") as fh:
            return cls.from_dict(json.load(fh))
