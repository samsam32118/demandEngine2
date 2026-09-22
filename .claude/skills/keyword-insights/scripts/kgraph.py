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
import statistics
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

# What the person expects to find at the end of the search: the third axis.
# `job` says what they are doing; this says what kind of answer would
# satisfy them. `bim modeling services` and `bim software` are both people
# shopping — one for a firm to do the work, one for a tool to do it
# themselves — and on `cad to bim` a click on the first cost $72 against $8
# for the second. That contrast was found by hand, after a run, because the
# skill had no way to see it: two searchers doing the same job were the same
# searcher. Fixed and universal, like the jobs, for the same reason: a
# taxonomy mined per run could always be made to flatter the data.
OFFERINGS: dict[str, str] = {
    "service": "Someone to do it for them — a firm, agency, contractor, "
               "consultant, freelancer or provider who does the work",
    "software": "A tool to use themselves — software, an app, a platform, a "
                "plugin or an online tool",
    "product": "A physical thing to buy and own — goods, equipment, a kit, "
               "materials or supplies",
    "information": "Knowledge — an explanation, definition, guide, tutorial, "
                   "course, example or the answer to a question",
}
# How each reads in a sentence: "the money is in services, not software".
OFFERING_NOUNS: dict[str, str] = {
    "service": "services", "software": "software",
    "product": "physical products", "information": "information",
}

# The jobs that make a search worth bidding on: someone buying, comparing,
# or looking for a supplier nearby. The closing forecast is priced on
# exactly this set, and the "buying or comparing" share in every topic row
# is the same set, so a reader can put the two side by side.
BIDDABLE = ("buy", "compare", "local")

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
    # The third axis, read the same way: kept only where one answer is
    # clearly ahead of the runner-up.
    offering: str | None = None
    offering_confidence: float = 0.0
    offering_certain: bool = False
    entities: list[str] = field(default_factory=list)
    # Competition, from DataForSEO Labs where it has been asked: how hard
    # the first page is to reach (0-100, logarithmic), the head term of the
    # synonym cluster this search belongs to (Ahrefs calls it the parent
    # topic), Labs' own reading of intent, and how strong the pages already
    # on page one are. `None` means not measured, which is not the same as
    # easy.
    difficulty: int | None = None
    # The spellings Google counts as this same search (see `add_rows`).
    aliases: list[str] = field(default_factory=list)
    parent_topic: str = ""
    labs_intent: str = ""
    top10_domain_rank: float | None = None
    top10_referring_domains: float | None = None

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


@dataclass
class Site:
    """A business that ranks for this market, and what harvesting it gave.

    A site is a different kind of seed from a word. A word expands off its
    own breadth, so a niche phrase returns almost nothing. A site expands
    off what a live business is about — and a business that has invested in
    ranking is evidence that somebody is selling here, which an invented
    keyword never is.
    """

    domain: str
    title: str = ""
    snippet: str = ""
    rank: int = 0
    kind: str = ""
    harvested: int = 0
    volume: int = 0


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


def growth(trend: Sequence[int]) -> float | None:
    """The most recent twelve months against the twelve before them.

    Both windows are complete seasonal cycles, so the season cancels
    exactly and what is left is the change in level between years. This
    needs twenty-four months; with twelve there is no honest answer, and an
    earlier version of this function invented one by dividing the last
    quarter of the window by the first — June-July-August against
    September-October-November, nine months apart. On `garden rooms` that
    reported a market shrinking to 0.88x when September is the highest month
    of the year, which would have told a builder demand was falling as they
    bought ads into the peak.

    The fix was not arithmetic. It was asking DataForSEO for the history it
    gives away free: `date_from` returns forty-eight months for the price of
    twelve. See `seo.history_start`.

    **Each window is compared by its median month, not its total.** Google
    Keyword Planner emits occasional single-month spikes and DataForSEO
    passes them through verbatim: `keyword research` sits between 6k and 14k
    for thirty-three months, then reads 301k, 1.5M and 1.83M in three
    consecutive ones. A ratio of sums has no defence against that — those
    three months land in the denominator and report the market at 0.29x,
    a 71% collapse, while the typical month was going up. A ratio of medians
    answers the same question and cannot be moved by fewer than six bad
    months in a window.

    Measured across 754 keywords at 1,000+/mo drawn from four markets: 9%
    carry a month at 10x their own median, 3% at 50x, and on the largest
    terms the two methods disagree about the *direction* of the year —
    `keyword research` 0.29x against 3.42x, `content marketing` 0.32x
    against 2.96x, `ai influencer generator` 90.13x against 0.77x. The
    median is not a refinement here; it is the difference between a true
    statement and a false one.
    """
    if len(trend) < 24:
        return None
    recent = statistics.median(trend[-12:])
    prior = statistics.median(trend[-24:-12])
    if prior <= 0:
        return None
    return recent / prior


def growth_readable(trend: Sequence[int]) -> bool | None:
    """Can this series carry a statement about direction at all?

    A median survives a spike; nothing survives a series that swings 450x
    inside the two years being compared. `keyword research` reads 0.29x by
    the sum of each window and 3.42x by the median, and a series about
    which two reasonable estimators disagree on the *sign* of the change is
    one the data cannot speak for, whichever figure gets quoted.

    That is the test, and there is no threshold in it: readable means the
    ratio of sums and the ratio of medians fall on the same side of 1.0.
    Nobody has to defend "3x is too erratic" — the series is asked whether
    it agrees with itself. `None` where there is no growth figure at all.
    """
    if len(trend) < 24:
        return None
    prior_sum = sum(trend[-24:-12])
    prior_med = statistics.median(trend[-24:-12])
    if prior_sum <= 0 or prior_med <= 0:
        return None
    by_sum = sum(trend[-12:]) / prior_sum
    by_med = statistics.median(trend[-12:]) / prior_med
    return (by_sum >= 1.0) == (by_med >= 1.0)


def years_of_history(trend: Sequence[int]) -> int:
    return len(trend) // 12


def seasonality(trend: Sequence[int], months: Sequence[str] = ()) -> float | None:
    """Peak month over mean month, averaged across every year available.

    One year of data gives one observation per month, so a single unusual
    month reads as a season. Averaging the same calendar month across four
    years separates a shape that repeats from a month that was odd once.
    """
    if len(trend) < 12:
        return None
    per_month = _by_calendar_month(trend, months)
    mean = sum(per_month) / len(per_month)
    if mean <= 0:
        return None
    return max(per_month) / mean


def _by_calendar_month(trend: Sequence[int],
                       months: Sequence[str] = ()) -> list[float]:
    """Twelve figures, one per calendar month, across every year available.

    The figure for each month is the **median** of that month across years,
    not the mean. A season is a shape that repeats; a single spiked
    September is not a season, and a mean lets one of them name the peak
    month for the whole market. Same defect as `growth`, same fix.

    This needs three or more years to bite: the median of two observations
    is their mean, so on a two-year window a lone spike still names the
    peak. Every call asks for four (`seo.history_start`), which is where
    the guarantee comes from — it is a property of the request, not of this
    function, so do not shorten that window without revisiting this.
    """
    buckets: dict[int, list[int]] = {}
    for i, value in enumerate(trend):
        if months and i < len(months):
            try:
                key = int(months[i].split("-")[1])
            except (ValueError, IndexError):
                key = i % 12 + 1
        else:
            key = i % 12 + 1
        buckets.setdefault(key, []).append(value)
    return [statistics.median(v) for _, v in sorted(buckets.items())]


def peak_month(trend: Sequence[int], months: Sequence[str]) -> str:
    """Which calendar month peaks, across every year available."""
    per_month = _by_calendar_month(trend, months)
    if not per_month:
        return "one month"
    return MONTHS[per_month.index(max(per_month))]


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
    """Volume-weighted monthly series for a group, as absolute searches.

    The length is whatever most of these keywords carry, not a fixed twelve.
    Asking DataForSEO for four years of history turned every series into
    forty-eight months, and a hardcoded `== 12` here silently matched none
    of them — so trend and season stopped being generated at all rather
    than failing loudly. Series of other lengths are left out of the sum
    because adding a short one to a long one shifts every month it touches.
    """
    lengths = Counter(len(k.trend) for k in keywords if k.trend)
    if not lengths:
        return []
    span, _ = lengths.most_common(1)[0]
    series = [k.trend for k in keywords if len(k.trend) == span]
    return [sum(col) for col in zip(*series)]


# --------------------------------------------------------------------------
# Mining: proposing candidates, never selecting them
# --------------------------------------------------------------------------

def stem(token: str) -> str:
    """A crude stem: enough to see that `modelling` and `models` are `model`.

    Only used to decide whether two searches Google already reports with the
    same numbers are spellings of one another, so it needs to be generous,
    not correct.
    """
    for suffix in ("ings", "ing", "ers", "er", "ed", "es", "s"):
        if token.endswith(suffix) and len(token) - len(suffix) >= 3:
            token = token[: -len(suffix)]
            break
    token = re.sub(r"(.)\1$", r"\1", token)
    # `service` and `services` must meet: the plural lost "es", so the
    # singular loses its final "e".
    return token[:-1] if token.endswith("e") and len(token) > 4 else token


def stems(term: str) -> frozenset[str]:
    return frozenset(stem(t) for t in tokens(term))


def fingerprint(row: dict) -> tuple | None:
    """What Google reports for a close-variant cluster, when it identifies one.

    Google Keyword Planner gives every close variant of a search — plural,
    misspelling, synonym — the whole cluster's numbers. Across 48 months a
    varying series matching exactly is a fingerprint no coincidence produces;
    a flat one ("10 every month") matches by chance, so it identifies
    nothing.
    """
    trend = row.get("trend") or []
    if len(trend) < 24 or len(set(trend[-24:])) < 2:
        return None
    return (int(row.get("volume") or 0), tuple(trend[-24:]))


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
        self.sites: dict[str, Site] = {}
        self.iterations: list[dict] = []
        self.collapsed = 0
        self.variants_collapsed = 0
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
        by_print: dict[tuple, list[str]] = {}
        for term, kw in self.keywords.items():
            by_shape.setdefault(tuple(sorted(term.split())), term)
            fp = fingerprint({"trend": kw.trend, "volume": kw.volume})
            if fp is not None:
                by_print.setdefault(fp, []).append(term)
        for row in rows:
            term = row["term"]
            shape = tuple(sorted(term.split()))
            kept = by_shape.get(shape)
            if kept is not None and kept != term:
                self.collapsed += 1
                continue
            # The same collapse for close variants. Google reports
            # `project management software`, `project tracking software`,
            # `project planning software` and `program management software`
            # with one identical 48-month series, because they are one
            # cluster to it; counting each made 43-56% of every market's
            # volume a double count (it-23). One stem apart and the same
            # fingerprint is the same search.
            fp = fingerprint(row)
            if fp is not None and term not in self.keywords:
                mine = stems(term)
                twin = next((t for t in by_print.get(fp, [])
                             if len(stems(t) ^ mine) <= 2
                             and len(stems(t) & mine) >= len(mine) - 1),
                            None)
                if twin is not None:
                    self.variants_collapsed += 1
                    if term not in self.keywords[twin].aliases:
                        self.keywords[twin].aliases.append(term)
                    continue
            by_shape.setdefault(shape, term)
            if fp is not None:
                by_print.setdefault(fp, []).append(term)
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

    def set_competition(self, rows: Iterable[dict]) -> int:
        """Lay competition measurements onto keywords already here.

        Kept apart from `add_rows` on purpose: competition is asked about
        searches the market already holds, and must never add one.
        """
        placed = 0
        for row in rows:
            kw = self.keywords.get(row.get("term", ""))
            if kw is None:
                continue
            for key in ("difficulty", "parent_topic", "labs_intent",
                        "top10_domain_rank", "top10_referring_domains"):
                if row.get(key) not in (None, ""):
                    setattr(kw, key, row[key])
            placed += 1
        return placed

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
            tmonths = next((k.months for k in kws
                            if len(k.months) == len(trend)), [])
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
                "growth": (round(growth(trend), 3)
                           if growth(trend) is not None else None),
                "growth_readable": growth_readable(trend),
                "commercial_share": round(share(
                    sum(v for j, v in job_vol.items() if j in BIDDABLE),
                    vol), 3),
                "years_of_history": years_of_history(trend),
                "seasonality": (round(seasonality(trend, tmonths), 2)
                                if seasonality(trend, tmonths) is not None
                                else None),
            })
        return sorted(rows, key=lambda r: -r["volume"])

    def sharpest_narrowing(self) -> tuple[float, "Keyword", "Keyword"] | None:
        """The qualifier that raises the click price most: (lift, bare, narrowed).

        A narrowing is a longer search inside a topic whose bare name is
        itself a keyword — and it is searched *less* than the search it
        narrows. One that is searched more is not a narrowing; it is a
        different cluster that happens to contain the words. On `cad to
        bim`, `bim building modeling` carries the whole BIM cluster's 5,400
        a month through Google's close-variant grouping, against 720 for
        `building modeling`, and the finding read "20.6x the price for 750%
        of the volume" — a premise its own numbers contradict, and one no
        judgment could catch, because the test reads the assertion with the
        digits taken out.

        One definition for both callers: the finding, and the network's
        evidence. They were two copies of the same loop, and the network's
        iterated a set, so which pair it named on a tie changed between
        runs.

        And it is searched at least as often as the market's typical
        search. The dearest narrowing is almost always one nobody types —
        `bim drawing software` at 10 a month — and a price that ten people
        a month meet is a curiosity, not a second kind of buyer: the
        critique of the `cad to bim` report named exactly that finding
        (it-23). The bar is the market's own median, not a number chosen
        here.
        """
        sizes = [k.volume for k in self.keywords.values() if k.volume > 0]
        typical = median(sizes) if sizes else 0
        by_topic: dict[str, list[Keyword]] = defaultdict(list)
        for kw in self.certain:
            if kw.topic and kw.topic not in ("", "none"):
                by_topic[kw.topic].append(kw)
        best: tuple[float, Keyword, Keyword] | None = None
        for topic, kws in by_topic.items():
            bare = self.keywords.get(topic)
            if not bare or bare.cpc <= 0 or bare.volume <= 0:
                continue
            for kw in kws:
                if (kw.term == topic or kw.cpc <= 0 or kw.volume <= 0
                        or kw.volume >= bare.volume or kw.volume < typical):
                    continue
                lift = kw.cpc / bare.cpc
                if best is None or lift > best[0]:
                    best = (lift, bare, kw)
        return best

    def offering_rows(self) -> list[dict]:
        """One row per kind of offering: the arithmetic, and nothing more.

        Over the searches whose offering read clearly. Shares of searching
        and of spend are taken over those same searches — dividing spend by
        a wider set is how `money_seat` came to say "concentrated" over
        numbers saying the opposite (it-21). What share is buying is taken
        over the ones whose intent also read clearly, because a job the
        model could not tell apart is not evidence about buying.
        """
        placed = [k for k in self.keywords.values()
                  if k.offering_certain and k.offering in OFFERINGS
                  and k.volume > 0]
        total_volume = sum(k.volume for k in placed)
        total_money = sum(k.money for k in placed)
        out = []
        for offering in OFFERINGS:
            kws = [k for k in placed if k.offering == offering]
            if not kws:
                continue
            vol = sum(k.volume for k in kws)
            money = sum(k.money for k in kws)
            read = [k for k in kws if k.job_certain]
            read_vol = sum(k.volume for k in read)
            buying = [k for k in read if k.job in BIDDABLE]
            trend = weighted_trend(kws)
            g = growth(trend)
            out.append({
                "offering": offering,
                "keywords": len(kws),
                "volume": vol,
                "money": round(money, 2),
                "search_share": round(share(vol, total_volume), 4),
                "spend_share": round(share(money, total_money), 4),
                "click_price": round(click_price(kws), 2),
                "commercial_share": (round(share(
                    sum(k.volume for k in buying), read_vol), 3)
                    if read_vol else None),
                "branded_share": round(share(
                    sum(k.volume for k in kws if k.entities), vol), 3),
                # Among the people shopping: what "open ground" means.
                "buying_keywords": len(buying),
                "buying_volume": sum(k.volume for k in buying),
                "buyers_naming_a_company": (round(share(
                    sum(k.volume for k in buying if k.entities),
                    sum(k.volume for k in buying)), 3)
                    if sum(k.volume for k in buying) else None),
                "growth": round(g, 3) if g is not None else None,
                "growth_readable": growth_readable(trend),
                "priciest": [(k.term, k.volume, round(k.cpc, 2)) for k in
                             sorted(kws, key=lambda k: (-k.cpc, -k.volume,
                                                        k.term))[:3]],
                "largest": [(k.term, k.volume, round(k.cpc, 2)) for k in
                            sorted(kws, key=lambda k: (-k.volume, k.term))[:3]],
            })
        return sorted(out, key=lambda r: (-r["volume"], r["offering"]))

    def stats(self) -> dict:
        """Everything the network's observed nodes are evidence about.

        Arithmetic only. Whether any of these numbers is large is a question
        about the wider world, and this module has measured one market.
        """
        rows = self.topic_rows()
        certain = self.certain
        priced = [k for k in self.keywords.values() if k.volume > 0]
        comp = [k.competition_index for k in priced
                if k.competition_index is not None]
        vol = max(self.total_volume, 1)
        clear = max(self.certain_volume, 1)
        top5 = sorted(self.keywords.values(), key=lambda k: -k.volume)[:5]

        trend = weighted_trend(priced)
        ss = sum(k.volume for k in certain if k.job == "self_serve")

        sharp = self.sharpest_narrowing()
        best_lift = sharp[0] if sharp else 0.0
        example = (f"\u201c{sharp[1].term}\u201d at ${sharp[1].cpc:.2f} "
                   f"against \u201c{sharp[2].term}\u201d at "
                   f"${sharp[2].cpc:.2f}") if sharp else ""
        return {
            "click_price": round(click_price(priced), 2) if priced else None,
            "max_cpc": round(max((k.cpc for k in priced), default=0.0), 2),
            "competition": (sum(comp) / len(comp)) if comp else None,
            "paid_share": share(sum(1 for k in priced if k.cpc > 0),
                                len(priced)) if priced else None,
            "branded_share": share(
                sum(k.volume for k in certain if k.entities), clear),
            "brands": self.confirmed_entities[:8],
            "self_serve_share": share(ss, clear),
            "unclear_share": share(vol - self.certain_volume, vol),
            # A direction the market's own series cannot carry is not
            # evidence. The node goes unobserved rather than misinformed.
            "growth": growth(trend) if growth_readable(trend) else None,
            "topics": len(rows) or None,
            "top5_share": share(sum(k.volume for k in top5), vol),
            "gradient": round(best_lift, 2) if best_lift > 0 else None,
            "gradient_example": example,
        }

    # -- persistence ------------------------------------------------------

    def to_dict(self) -> dict:
        return {
            "seed": self.seed,
            "geo": self.geo,
            "language": self.language,
            "keywords": [asdict(k) for k in self.keywords.values()],
            "topics": [asdict(t) for t in self.topics.values()],
            "entities": [asdict(e) for e in self.entities.values()],
            "sites": [asdict(s) for s in self.sites.values()],
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
        for st in data.get("sites", []):
            g.sites[st["domain"]] = Site(**st)
        g.iterations = data.get("iterations", [])
        return g

    def save(self, path: str) -> None:
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(self.to_dict(), fh, indent=2)

    @classmethod
    def load(cls, path: str) -> "Graph":
        with open(path, encoding="utf-8") as fh:
            return cls.from_dict(json.load(fh))
