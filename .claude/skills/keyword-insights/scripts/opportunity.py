"""Where to win: insights shaped like opportunities, not statistics.

Everything the skill said before this layer was a true statement about a
corpus — which topic names brands, how intent is mixed, where a click is
dearer. A critique of the `cad to bim` report found its top three insights
were a tautology (definitions do not name brands), a price gradient resting
on ten searches a month, and the tautology again from the other side. The
tests could not help: they check that a statement is true and specific, and
all of those were.

The people who are good at this do not start from statistics. They start
from where someone could win, and each has a heuristic for it:

- **Grow and Convert, Pain Point SEO** — value demand by who is ready to
  buy, not by volume: their bottom-of-funnel content converted at 4.78%
  against 0.19% for top-of-funnel, twenty-five times the rate.
- **Weak-spot SERP analysis** (Glen Allsopp at Detailed; Semrush, Ahrefs) —
  a first page carrying forum threads, social posts or off-target pages is
  a door left open; one of household names is a fight.
- **SERP clustering** (Keyword Insights, SE Ranking) — searches that share
  three of their top ten results are one page's worth of work: Google has
  already decided they want the same thing.
- **Ahrefs** — rank by traffic value and difficulty together, never by
  volume alone.
- **Geoffrey Moore's beachhead** — start where you can win outright, then
  move out from it.
- **Brian Balfour, channel–model fit** — what a customer costs in a channel
  has to fit what the business earns from one.
- **Les Binet (IPA), share of search** — a brand's share of its category's
  searches tracks its market share and leads it by six to twelve months.
- **Bob Moesta, Jobs to be Done** — people switch only when the push away
  from what they have beats the habit of keeping it; "alternatives to X" is
  that push, measured.
- **Eli Schwartz, product-led SEO** — a repeatable keyword pattern answered
  by one template (Zapier's "connect A to B") beats pages written one at a
  time.
- **"Why now"** — demand that did not exist a few years ago is the opening
  incumbents have not built for.

Each becomes a family here. Code does what code can: sums, clusters, the
click split by position, the premise each sentence rests on. Jev does what
it can: what a page on Google is, whether a search is about this market at
all, whether a set of words are the same kind of thing, and — in the same
tests as every other finding — whether the statement holds and what it is
worth to the reader.
"""

from __future__ import annotations

import statistics
from collections import Counter
from dataclasses import dataclass, field
from typing import Sequence

import kgraph as K
import serp as S
from insights import _examples, money0, n, pct, usd
from judge import Claim

# Grow and Convert's measured conversion of bottom-of-funnel visitors into
# leads (trials, demos, sales enquiries): 1,348 of 28,190. Cited, not tuned.
BOFU_LEAD_RATE = 1348 / 28190

# How the clicks from one page one are split between its ten positions:
# First Page Sage's blended organic CTR by position, March–August 2026,
# 3.67 billion impressions. Used only as relative weights — the level
# differs by study and year (27.6% at position one in Backlinko's, 7.1% in
# this one, after AI overviews), the shape much less: the top three take
# about three quarters of what page one sends.
CTR_BY_POSITION = (7.1, 3.0, 1.7, 1.1, 0.7, 0.6, 0.4, 0.3, 0.2, 0.2)

# SE Ranking's grouping level: two searches belong on one page when three
# of their top-ten results are the same URL. The common default.
SHARED_RESULTS = 3

# What on page one a new, built-for-purpose page can take clicks from:
# pages that are not trying to answer the search. Directories, articles,
# specialists and household names are all trying.
WEAK = ("community", "off_target")

# Not businesses selling here, whatever they rank for: read so by Jev on
# page one, or — for a domain no page one showed — the hosts that rank
# everywhere and sell nothing.
NOT_SELLING = ("community", "off_target", "publication")

# The words that say someone is weighing up, or leaving, what they have.
SWITCHING = frozenset({"alternative", "alternatives", "competitor",
                       "competitors", "vs", "versus", "replacement",
                       "instead", "cheaper", "switch", "migrate", "similar"})

_WEAK_SPOT = ("Weak-spot SERP analysis (Glen Allsopp at Detailed; Semrush): "
              "a first page carrying forum threads, social posts or off-target "
              "pages is a door left open; one held by businesses built for the "
              "search is a fight.")
_SHARE = ("Share of voice: who takes the clicks this market's buyers send — "
          "and so who you would be taking them from.")

# How to say each framework's point under the insight it produced. Written
# once, by hand, like the templates: the reader should know which heuristic
# found this and why it is worth acting on.
FRAMES = {
    "start_here": "Pain Point SEO (Grow and Convert), Ahrefs' difficulty and "
                  "Moore's beachhead: start where buyers already search, the "
                  "money is real and the first page can be beaten — one page's "
                  "worth of searches, by SERP clustering.",
    "open_door": _WEAK_SPOT,
    "weak_open": _WEAK_SPOT,
    "weak_closed": _WEAK_SPOT,
    "customer_cost": "Channel–model fit (Brian Balfour): what a customer costs "
                     "in a channel has to fit what the business earns from "
                     "one.",
    "who_owns": _SHARE,
    "who_owns_not": _SHARE,
    "share_of_search": "Share of search (Les Binet, IPA): a brand's share of its "
                       "category's searches tracks its market share and leads it "
                       "by six to twelve months.",
    "switching": "Jobs to be Done (Bob Moesta): people switch only when the push "
                 "away from what they have beats the habit of keeping it. These "
                 "searches are that push, measured.",
    "pattern": "Product-led SEO (Eli Schwartz): a repeatable pattern answered by "
               "one template — Zapier's “connect A to B” pages — beats "
               "pages written one at a time.",
    "new_demand": "Why now: demand that did not exist a few years ago is the "
                  "opening incumbents have not built for.",
    "offer_money": "Where the money is: click prices are what advertisers already "
                   "pay to reach these people.",
    "offer_growth": "Where demand is moving, by the kind of answer people want.",
    "offer_open": "Where buyers have not picked a supplier yet.",
    "topic_growth": "Which of the market's names is growing, and which is dying.",
}


def frame(kind: str) -> str:
    return FRAMES.get(kind, "")


# --------------------------------------------------------------------------
# The arithmetic
# --------------------------------------------------------------------------

def buying_core(graph: K.Graph) -> list[K.Keyword]:
    """Searches whose intent read clearly as buying, comparing or finding a
    supplier — Grow and Convert's bottom of the funnel."""
    return [k for k in graph.certain if k.job in K.BIDDABLE and k.volume > 0]


def click_weight(rank: int) -> float:
    """The weight of one position in page one's clicks."""
    return CTR_BY_POSITION[rank - 1] if 1 <= rank <= len(CTR_BY_POSITION) \
        else 0.0


def click_split(page: Sequence[dict]) -> dict[str, float]:
    """Where page one's clicks go, by kind of page, as shares of one.

    Weighted by position and taken over the results actually there: a page
    one with seven results after the ads and boxes sends its clicks to
    those seven.
    """
    weights: dict[str, float] = {}
    for r in page:
        kind = r.get("kind") or ""
        if kind:
            weights[kind] = weights.get(kind, 0.0) + click_weight(r["rank"])
    total = sum(weights.values())
    return {k: v / total for k, v in weights.items()} if total else {}


@dataclass
class Cluster:
    """Buying searches one page could rank for: Google shows the same pages
    for them. Named for the one worth most, whose page one this is."""

    keywords: list[K.Keyword]
    page: list[dict] = field(default_factory=list)   # organic, kinds by Jev
    features: dict = field(default_factory=dict)
    urls: set = field(default_factory=set)

    @property
    def anchor(self) -> K.Keyword:
        return self.keywords[0]

    @property
    def topic(self) -> str:
        return self.anchor.topic

    @property
    def offering(self) -> str:
        known = Counter()
        for k in self.keywords:
            if k.offering_certain and k.offering:
                known[k.offering] += k.volume
        return known.most_common(1)[0][0] if known else ""

    @property
    def buyers(self) -> int:
        return sum(k.volume for k in self.keywords)

    @property
    def prize(self) -> float:
        """What these searches' clicks cost a month at today's prices —
        Ahrefs' and Semrush's "traffic value"."""
        return sum(k.money for k in self.keywords)

    @property
    def click_price(self) -> float:
        return self.prize / self.buyers if self.buyers else 0.0

    @property
    def difficulty(self) -> float | None:
        measured = [k for k in self.keywords if k.difficulty is not None]
        vol = sum(k.volume for k in measured)
        if not measured or vol <= 0:
            return None
        return sum(k.difficulty * k.volume for k in measured) / vol

    @property
    def growth(self) -> float | None:
        trend = K.weighted_trend(self.keywords)
        return K.growth(trend) if K.growth_readable(trend) else None

    @property
    def split(self) -> dict[str, float]:
        return click_split(self.page)

    @property
    def weak_share(self) -> float:
        """The share of page one's clicks that go to pages not built to
        answer these searches."""
        split = self.split
        return sum(split.get(k, 0.0) for k in WEAK)

    @property
    def open_prize(self) -> float:
        """The buyer money in searches that name no company. A search that
        names one is looking for that company, and no one else's page
        answers it: on `cad to bim` the first "start here" was `revit
        price` — people pricing Autodesk's own product (it-23)."""
        return sum(k.money for k in self.keywords if not k.entities)

    @property
    def open_value(self) -> float:
        """The buyer money a newcomer could answer whose first page is held
        by pages not built for it: the unbranded prize, times the share of
        page one's clicks those pages sit on."""
        return self.open_prize * self.weak_share

    @property
    def weak_results(self) -> list[dict]:
        return [r for r in self.page if r.get("kind") in WEAK]

    def row(self) -> dict:
        split = self.split
        return {"start_with": self.anchor.term, "topic": self.topic,
                "offering": self.offering, "searches": len(self.keywords),
                "also": "; ".join(k.term for k in self.keywords[1:8]),
                "buyer_searches_a_month": self.buyers,
                "prize_a_month": round(self.prize, 2),
                "click_price": round(self.click_price, 2),
                "difficulty": (None if self.difficulty is None
                               else round(self.difficulty, 1)),
                "year_on_year": (None if self.growth is None
                                 else round(self.growth, 3)),
                "naming_no_company_a_month": round(self.open_prize, 2),
                "clicks_to_weak_pages": round(self.weak_share, 3),
                "open_value_a_month": round(self.open_value, 2),
                "clicks_by_kind": {k: round(v, 3) for k, v in
                                   sorted(split.items(),
                                          key=lambda kv: -kv[1])},
                "page_one": "; ".join(f"{r['rank']}. {r['domain']} "
                                      f"({r.get('kind') or '?'})"
                                      for r in self.page),
                "ads": self.features.get("ads"),
                "ai_overview": self.features.get("ai_overview")}


def serp_clusters(keywords: Sequence[K.Keyword],
                  pages: dict[str, Sequence[dict]],
                  features: dict[str, dict] | None = None) -> list[Cluster]:
    """Group searches Google answers with the same pages.

    Taken in the order given — most valuable first — each search joins the
    first group whose own page one shares three of its top-ten URLs, or
    starts a group of its own. What is being grouped is Google's judgment
    of what the searches want, not the words in them: `cad to bim
    services` and `bim modeling services` can be one page's work and
    `bim services` another's, whatever the strings suggest.
    """
    out: list[Cluster] = []
    for kw in keywords:
        rows = pages.get(kw.term)
        if not rows:
            continue
        urls = {r["url"] for r in rows if r.get("url")}
        home = next((c for c in out
                     if len(urls & c.urls) >= SHARED_RESULTS), None)
        if home is not None:
            home.keywords.append(kw)
            continue
        out.append(Cluster([kw], page=[dict(r) for r in rows],
                           features=dict((features or {}).get(kw.term, {})),
                           urls=urls))
    return out


def by_open_value(clusters: Sequence[Cluster]) -> list[Cluster]:
    return sorted(clusters, key=lambda c: (-c.open_value, -c.prize,
                                           c.anchor.term))


def market_split(clusters: Sequence[Cluster]) -> dict[str, float]:
    """Where the buyers' page-one clicks go across the market, each group
    weighted by what its searches are worth."""
    weighted: dict[str, float] = {}
    total = 0.0
    for c in clusters:
        split = c.split
        if not split or c.prize <= 0:
            continue
        total += c.prize
        for kind, share in split.items():
            weighted[kind] = weighted.get(kind, 0.0) + c.prize * share
    return {k: v / total for k, v in weighted.items()} if total else {}


def page_one_words(c: Cluster) -> str:
    """What is on page one, in a phrase: counted by code, kinds read by Jev."""
    names = {"specialist": ("specialist firm", "specialist firms"),
             "major_brand": ("household name", "household names"),
             "list": ("directory or review site", "directories or review sites"),
             "publication": ("article or guide", "articles or guides"),
             "community": ("forum, social or press-release page",
                           "forum, social or press-release pages"),
             "off_target": ("off-target page", "off-target pages")}
    counts = Counter(r.get("kind") for r in c.page if r.get("kind"))
    parts = []
    for kind in ("specialist", "major_brand", "list", "publication",
                 "community", "off_target"):
        if counts.get(kind):
            one, many = names[kind]
            parts.append(f"{counts[kind]} {one if counts[kind] == 1 else many}")
    if not parts:
        return "unread"
    return ", ".join(parts[:-1]) + (" and " if len(parts) > 1 else "") \
        + parts[-1]


def domain_kinds(clusters: Sequence[Cluster]) -> dict[str, str]:
    """Each domain's kind, as page one read it most often."""
    seen: dict[str, Counter] = {}
    for c in clusters:
        for r in c.page:
            if r.get("kind") and r.get("domain"):
                seen.setdefault(r["domain"], Counter())[r["kind"]] += 1
    return {d: cnt.most_common(1)[0][0] for d, cnt in seen.items()}


# --------------------------------------------------------------------------
# The claims
# --------------------------------------------------------------------------

def _claim(graph: K.Graph, key: str, kind: str, headline: str, text: str,
           assertion: str, rival: str, evidence: dict,
           examples: list[str], topic: str = "") -> Claim:
    basis = {"keywords_this_rests_on": len(graph.certain),
             "monthly_searches_this_rests_on": graph.certain_volume}
    return Claim(key=key, text=text, assertion=assertion, forbids=rival,
                 evidence={**evidence, **basis}, examples=examples,
                 topic=topic, kind=kind, headline=headline)


def _weak_list(c: Cluster, limit: int = 3) -> str:
    return ", ".join(f"{r['domain']} at {r['rank']}"
                     for r in c.weak_results[:limit])


def candidates(clusters: Sequence[Cluster]) -> list[Cluster]:
    """Groups a newcomer could answer: buyer money in searches naming no
    company."""
    return [c for c in clusters if c.open_prize > 0 and c.page]


def pareto(cands: Sequence[Cluster]) -> list[Cluster]:
    """The candidates no other candidate beats on every count at once.

    More buyer money naming no company, easier to reach page one, more of
    its clicks on pages not built for it. Where either side lacks a
    measurement that count is left out of the comparison rather than
    guessed. What survives is a set of genuine trade-offs, and choosing
    among those is judgment — Jev's.
    """
    def dims(c: Cluster) -> list[float | None]:
        return [c.open_prize,
                None if c.difficulty is None else -c.difficulty,
                c.weak_share]

    def beats(a: Cluster, b: Cluster) -> bool:
        pairs = [(x, y) for x, y in zip(dims(a), dims(b))
                 if x is not None and y is not None]
        return (bool(pairs) and all(x >= y for x, y in pairs)
                and any(x > y for x, y in pairs))

    front = [c for c in cands
             if not any(beats(o, c) for o in cands if o is not c)]
    return sorted(front, key=lambda c: (-c.open_prize, c.anchor.term))


def _ordinal(i: int) -> str:
    return {1: "", 2: "2nd ", 3: "3rd "}.get(i, f"{i}th ")


def rank_words(cands: Sequence[Cluster]) -> dict[str, str]:
    """Each candidate described by where it stands among the others, in words.

    Jev cannot compare numbers; code can, so the comparisons are made here
    and handed over already made — "the largest prize of the 3" — with the
    figures alongside for the reader, not for the judgment.
    """
    total = len(cands)

    def place(key, reverse=True) -> dict[str, int]:
        known = [c for c in cands if key(c) is not None]
        ordered = sorted(known, key=key, reverse=reverse)
        return {c.anchor.term: ordered.index(c) + 1 for c in known}

    prize = place(lambda c: c.open_prize)
    easy = place(lambda c: c.difficulty, reverse=False)
    weak = place(lambda c: c.weak_share)
    out = {}
    for c in cands:
        h = c.anchor.term
        parts = [f"the {_ordinal(prize[h])}most buyer money of the {total} "
                 f"({money0(c.open_prize)} a month of clicks, in searches "
                 f"naming no company)"]
        if h in easy:
            parts.append(f"the {_ordinal(easy[h])}easiest of the {total} to "
                         f"reach page one for (difficulty {c.difficulty:.0f} "
                         f"of 100)")
        if c.weak_share > 0:
            parts.append(f"the {_ordinal(weak[h])}weakest first page of the "
                         f"{total}: pages not built for it sit where "
                         f"{pct(c.weak_share)} of its clicks go")
        else:
            parts.append(f"its first page is all pages built for it: "
                         f"{page_one_words(c)}")
        out[h] = "; ".join(parts)
    return out


def _group_words(c: Cluster) -> str:
    return (f"{n(len(c.keywords))} searches Google answers with the same "
            f"pages" if len(c.keywords) > 1 else "one search")


def start_here(graph: K.Graph, chosen: Cluster | None,
               front: Sequence[Cluster]) -> list[Claim]:
    """Moore's beachhead: of the genuine trade-offs, the one Jev picked.

    Code removes every group another beats on buyer money, difficulty and
    first-page weakness at once; Jev chooses among what is left, each
    option described by where it stands. A group whose buyers are looking
    for a company by name is not a candidate at any size: on `cad to bim`
    the first "start here" was `revit price` — people pricing Autodesk's
    own product (it-23).
    """
    if chosen is None:
        return []
    c, head = chosen, chosen.anchor.term
    want = {"service": "hiring someone to do it",
            "software": "choosing a tool",
            "product": "buying it"}.get(c.offering, "buying or comparing")
    parts = [f"{_group_words(c)}, {n(c.buyers)} a month from people {want}, "
             f"worth {money0(c.prize)} a month at today's click prices "
             f"({usd(c.click_price)} a click)"
             + (f", {money0(c.open_prize)} of it in searches naming no "
                f"company" if round(c.open_prize) < round(c.prize) else "")]
    if c.difficulty is not None:
        parts.append(f"difficulty {c.difficulty:.0f} of 100")
    if c.weak_results:
        parts.append(f"pages not built to answer it — {_weak_list(c)} — sit "
                     f"where {pct(c.weak_share)} of its page-one clicks go")
    else:
        parts.append(f"page one is {page_one_words(c)}")
    if c.growth is not None:
        parts.append(f"{c.growth:.2f}x the year before")
    text = f"Start with “{head}”: " + "; ".join(parts) + "."
    others = [o for o in front if o is not c][:3]
    if others:
        text += " The other choices that nothing beats outright: " + ", ".join(
            f"“{o.anchor.term}” ({money0(o.open_prize)} a month"
            + (f", difficulty {o.difficulty:.0f}" if o.difficulty is not None
               else "") + ")" for o in others) + "."
    return [_claim(
        graph, "market|start_here", "start_here",
        f"Start with “{head}”",
        text,
        f"The best first place to compete in this market is people searching "
        f"for “{head}”: they are there to buy, the money behind them is "
        f"real, and the pages answering them now can be beaten.",
        f"People searching for “{head}” are not the place to start: "
        f"there is little money behind them, or the pages answering them now "
        f"are too strong to beat.",
        {"start_with": head, **c.row(),
         "searches_in_it": [f"{k.term} ({n(k.volume)}/mo, {usd(k.cpc)})"
                            for k in sorted(c.keywords,
                                            key=lambda k: -k.money)[:8]],
         "page_one_detail": [{"rank": r["rank"], "domain": r["domain"],
                              "kind": r.get("kind", "")} for r in c.page],
         "next": [o.row() for o in others],
         "choices_nothing_beats": len(front)},
        _examples(sorted(c.keywords, key=lambda k: -k.money)[:6]),
        c.topic)]


def open_door(graph: K.Graph, clusters: Sequence[Cluster],
              chosen: Cluster | None = None) -> list[Claim]:
    """The weak spot: the most buyer money naming no company whose first
    page is partly held by pages not built to answer it."""
    ranked = [c for c in by_open_value(candidates(clusters))
              if c.open_value > 0 and c is not chosen]
    if not ranked:
        return []
    c = ranked[0]
    head = c.anchor.term
    text = (f"The door left open is “{head}”: pages not built to answer "
            f"it — {_weak_list(c)} — sit where {pct(c.weak_share)} of its "
            f"page-one clicks go, on {money0(c.open_prize)} a month of buyer "
            f"clicks in searches naming no company ({_group_words(c)}"
            + (f", difficulty {c.difficulty:.0f} of 100" if c.difficulty
               is not None else "") + ").")
    return [_claim(
        graph, "market|open_door", "open_door",
        f"The door left open is “{head}”",
        text,
        f"People searching for “{head}” are partly answered by pages "
        f"not built for them, so a page built for them has room to take "
        f"those clicks.",
        f"Even people searching for “{head}” are answered by pages built "
        f"for them; there is no weak spot to take clicks from.",
        {"search": head, **c.row(),
         "weak_pages": [{"rank": r["rank"], "domain": r["domain"],
                         "kind": r.get("kind", "")} for r in c.weak_results],
         "page_one_detail": [{"rank": r["rank"], "domain": r["domain"],
                              "kind": r.get("kind", "")} for r in c.page]},
        _examples(sorted(c.keywords, key=lambda k: -k.money)[:6]), c.topic)]


def weak_spots(graph: K.Graph, clusters: Sequence[Cluster]) -> list[Claim]:
    """Whether buyers here are answered by pages built for them: a pair of
    readings of one measurement, left to the account test."""
    split = market_split(clusters)
    read = [c for c in clusters if c.split and c.prize > 0]
    if len(read) < 2 or not split:
        return []
    weak = sum(split.get(k, 0.0) for k in WEAK)
    spec, major = split.get("specialist", 0.0), split.get("major_brand", 0.0)
    lists, pubs = split.get("list", 0.0), split.get("publication", 0.0)
    worst = max(read, key=lambda c: (c.weak_share, c.prize))
    across = (f"across the {n(len(read))} groups of buying searches read, "
              f"weighted by what each is worth")
    rest = (f"directories and review sites {pct(lists)}, articles and "
            f"guides {pct(pubs)}")
    open_text = (f"forum threads, social posts and off-target pages sit where "
                 f"{pct(weak)} of the page-one clicks go {across}; specialist "
                 f"firms {pct(spec)}, household names {pct(major)}, {rest}")
    closed_text = (f"specialist firms and household names sit where "
                   f"{pct(spec + major)} of the page-one clicks go {across} "
                   f"({pct(spec)} and {pct(major)}); {rest}; forum threads, "
                   f"social posts and off-target pages {pct(weak)}")
    evidence = {"clicks_by_kind": {k: round(v, 3) for k, v in
                                   sorted(split.items(), key=lambda kv: -kv[1])},
                "groups_read": len(read),
                "buyer_money_read_a_month": round(sum(c.prize for c in read), 2),
                "most_exposed": {"search": worst.anchor.term,
                                 "clicks_to_weak_pages": round(
                                     worst.weak_share, 3),
                                 "weak_pages": [r["domain"] for r in
                                                worst.weak_results]}}
    examples = [f"{c.anchor.term}: {pct(c.weak_share)} to weak pages "
                f"({money0(c.prize)}/mo)"
                for c in sorted(read, key=lambda c: -c.weak_share)[:6]]
    opened = ("People searching to buy here are often answered by pages not "
              "built for them — forum threads, social posts, off-target pages "
              "— so a page built for them has room to win.")
    closed = ("People searching to buy here are answered by businesses built "
              "to serve them, so a new page has to beat an established one.")
    return [
        _claim(graph, "market|weak_open", "weak_open",
               "Buyers here are often answered by pages not built for them",
               f"Buyers here are often answered by pages not built for them: "
               f"{open_text}. Most exposed: “{worst.anchor.term}”, "
               f"{pct(worst.weak_share)}.",
               opened, closed, evidence, examples),
        _claim(graph, "market|weak_closed", "weak_closed",
               "Buyers here are answered by businesses built for them",
               f"Buyers here are answered by businesses built for them: "
               f"{closed_text}.",
               closed, opened, evidence, examples),
    ]


def customer_cost(graph: K.Graph) -> list[Claim]:
    """What a lead costs through search, by what the buyer wants: the
    channel–model fit check, where the channel's price differs by offer."""
    core = [k for k in buying_core(graph) if k.cpc > 0]
    vol = sum(k.volume for k in core)
    if len(core) < 2 or vol <= 0:
        return []
    by_offer: dict[str, list[K.Keyword]] = {}
    for k in core:
        if k.offering_certain and k.offering in K.OFFERING_NOUNS:
            by_offer.setdefault(k.offering, []).append(k)
    rows = []
    for offer, kws in by_offer.items():
        v = sum(k.volume for k in kws)
        if len(kws) >= 2 and v > 0:
            cpc = sum(k.money for k in kws) / v
            rows.append({"offering": offer, "searches": len(kws),
                         "buyer_searches_a_month": v,
                         "average_click": round(cpc, 2),
                         "cost_per_lead": round(cpc / BOFU_LEAD_RATE, 2),
                         "dearest": max(kws, key=lambda k: (k.cpc, k.volume)
                                        ).term})
    rows.sort(key=lambda r: -r["cost_per_lead"])
    cpc = sum(k.money for k in core) / vol
    per_lead = cpc / BOFU_LEAD_RATE
    clicks = 1 / BOFU_LEAD_RATE
    dearest = max(core, key=lambda k: (k.cpc, k.volume))
    rate = (f"at the {BOFU_LEAD_RATE:.2%} rate at which bottom-of-funnel "
            f"visitors became leads in Grow and Convert's measurements, it "
            f"takes about {clicks:.0f} clicks to win one")
    evidence = {"lead_rate": round(BOFU_LEAD_RATE, 4),
                "clicks_per_lead": round(clicks, 1),
                "average_buyer_click": round(cpc, 2),
                "cost_per_lead_overall": round(per_lead, 2),
                "by_offering": rows,
                "dearest_click": {"term": dearest.term,
                                  "cpc": round(dearest.cpc, 2)},
                "buying_searches": len(core), "buyer_searches_a_month": vol}
    examples = _examples(sorted(core, key=lambda k: -k.money)[:6])
    if len(rows) >= 2:
        hi, lo = rows[0], rows[-1]
        noun = lambda r: K.OFFERING_NOUNS[r["offering"]]
        ratio = hi["cost_per_lead"] / lo["cost_per_lead"] \
            if lo["cost_per_lead"] else 0.0
        if ratio >= 1.5:
            return [_claim(
                graph, "market|customer_cost", "customer_cost",
                f"A lead for {noun(hi)} costs {money0(hi['cost_per_lead'])} "
                f"through search; for {noun(lo)}, "
                f"{money0(lo['cost_per_lead'])}",
                f"Through search, a lead from someone looking for "
                f"{noun(hi)} costs about {money0(hi['cost_per_lead'])} and "
                f"one looking for {noun(lo)} about "
                f"{money0(lo['cost_per_lead'])}: their clicks average "
                f"{usd(hi['average_click'])} and {usd(lo['average_click'])} "
                f"({n(hi['buyer_searches_a_month'])} and "
                f"{n(lo['buyer_searches_a_month'])} buying searches a month), "
                f"and {rate}.",
                f"Buying a customer through search costs several times more "
                f"here for someone who wants {noun(hi)} than for someone who "
                f"wants {noun(lo)}, so only one of those offers can easily "
                f"afford to advertise.",
                f"A customer costs about the same to buy through search here "
                f"whatever kind of offer they want.",
                evidence, examples)]
    return [_claim(
        graph, "market|customer_cost", "customer_cost",
        f"A lead costs about {money0(per_lead)} to buy through search here",
        f"A lead bought through search costs about {money0(per_lead)} here: "
        f"buyers' clicks cost {usd(cpc)} on average across {n(len(core))} "
        f"buying searches (up to {usd(dearest.cpc)} for "
        f"“{dearest.term}”), and {rate}.",
        "Only an offer that earns a lot from each customer can afford to buy "
        "customers through search here.",
        "Customers here are cheap enough to buy through search that even a "
        "low-priced offer could afford them.",
        evidence, examples)]


def who_owns(graph: K.Graph, shares: Sequence[dict],
             kinds: dict[str, str] | None = None) -> list[Claim]:
    """Share of voice among the businesses selling here, as a pair of
    readings. Forums, social sites and articles take clicks too, and are
    counted in the whole, but they are not who a newcomer competes with for
    a sale."""
    kinds = kinds or {}
    merged: dict[str, float] = {}
    counts: dict[str, int] = {}
    for s in shares:
        dom = S._registrable(s.get("domain") or "")
        if dom and s.get("etv", 0) > 0:
            merged[dom] = merged.get(dom, 0.0) + s["etv"]
            counts[dom] = max(counts.get(dom, 0), s.get("keywords") or 0)
    total = sum(merged.values())
    if total <= 0:
        return []

    def selling(dom: str) -> bool:
        if dom in kinds:
            return kinds[dom] not in NOT_SELLING
        return not any(dom == bad or dom.endswith("." + bad)
                       for bad in S.NON_VENDOR)

    firms = sorted((d for d in merged if selling(d)),
                   key=lambda d: (-merged[d], d))
    others = sorted((d for d in merged if not selling(d)),
                    key=lambda d: (-merged[d], d))
    if len(firms) < 2:
        return []
    top, share = firms[0], merged[firms[0]] / total
    next4 = sum(merged[d] for d in firms[1:5]) / total
    rest = sum(merged[d] for d in others) / total
    numbers = (f"the largest, “{top}”, takes {pct(share)} of the clicks "
               f"the buying searches send and the next four businesses "
               f"{pct(next4)} between them"
               + (f"; sites that sell nothing — "
                  f"{', '.join(others[:3])} — take {pct(rest)}"
                  if others else ""))
    evidence = {"leader": top, "leader_share": round(share, 3),
                "next_four_share": round(next4, 3),
                "not_selling_share": round(rest, 3),
                "businesses": [{"domain": d, "share": round(merged[d] / total, 3),
                                "kind": kinds.get(d, ""),
                                "searches_ranked_for": counts.get(d)}
                               for d in firms[:10]],
                "not_selling": [{"domain": d,
                                 "share": round(merged[d] / total, 3),
                                 "kind": kinds.get(d, "")}
                                for d in others[:6]]}
    examples = [f"{d} ({pct(merged[d] / total)})" for d in firms[:6]]
    owned = (f"One business already takes more of the traffic from people "
             f"shopping in this market than its nearest competitors do "
             f"together.")
    spread = (f"No business takes a commanding share of the traffic from "
              f"people shopping in this market; it is spread across several.")
    return [
        _claim(graph, "market|who_owns", "who_owns",
               f"“{top}” owns buyer search here",
               f"“{top}” owns buyer search here: {numbers}.",
               owned, spread, evidence, examples),
        _claim(graph, "market|who_owns_not", "who_owns_not",
               "No business owns buyer search here",
               f"No business owns buyer search here: {numbers}.",
               spread, owned, evidence, examples),
    ]


def share_of_search(graph: K.Graph) -> list[Claim]:
    """Binet's share of search: which named brand is gaining on which."""
    series = {}
    for brand in graph.confirmed_entities:
        kws = [k for k in graph.keywords.values()
               if brand in k.entities and len(k.trend) >= 24]
        trend = K.weighted_trend(kws)
        if len(trend) >= 24 and K.growth_readable(trend):
            series[brand] = (statistics.median(trend[-24:-12]),
                             statistics.median(trend[-12:]))
    before = sum(b for b, _ in series.values())
    now = sum(a for _, a in series.values())
    if len(series) < 2 or before <= 0 or now <= 0:
        return []
    moves = {b: (x / before, y / now) for b, (x, y) in series.items()}
    gainer = max(moves, key=lambda b: (moves[b][1] - moves[b][0], b))
    loser = min(moves, key=lambda b: (moves[b][1] - moves[b][0], b))
    (g0, g1), (l0, l1) = moves[gainer], moves[loser]
    if gainer == loser or not (round((g1 - g0) * 100) > 0 > round((l1 - l0) * 100)):
        return []
    return [_claim(
        graph, "market|share_of_search", "share_of_search",
        f"“{gainer}” is taking share of search from “{loser}”",
        f"“{gainer}” is taking share of search from "
        f"“{loser}”: of the searches naming a company here, "
        f"“{gainer}” went from {pct(g0)} to {pct(g1)} in a year and "
        f"“{loser}” from {pct(l0)} to {pct(l1)}.",
        f"“{gainer}” is gaining ground on “{loser}” among "
        f"the companies people search for by name here.",
        f"The companies people search for by name here are holding their "
        f"positions.",
        {"gaining": gainer, "losing": loser,
         "shares": {b: {"a_year_ago": round(x, 3), "now": round(y, 3)}
                    for b, (x, y) in sorted(moves.items(),
                                            key=lambda kv: -kv[1][1])}},
        _examples(sorted((k for k in graph.keywords.values()
                          if gainer in k.entities or loser in k.entities),
                         key=lambda k: -k.volume)[:6]), gainer)]


def switching(graph: K.Graph) -> list[Claim]:
    """Moesta's push, measured: searches for a way out of a named company."""
    by_brand: dict[str, list[K.Keyword]] = {}
    for k in graph.keywords.values():
        if k.volume <= 0 or not k.entities:
            continue
        if SWITCHING & set(K.tokens(k.term)):
            for brand in k.entities:
                by_brand.setdefault(brand, []).append(k)
    ranked = sorted(((b, ks) for b, ks in by_brand.items() if len(ks) >= 2),
                    key=lambda x: -sum(k.volume for k in x[1]))
    if not ranked:
        return []
    brand, kws = ranked[0]
    vol = sum(k.volume for k in kws)
    top = max(kws, key=lambda k: k.volume)
    trend = K.weighted_trend(kws)
    g = K.growth(trend) if K.growth_readable(trend) else None
    return [_claim(
        graph, "market|switching", "switching",
        f"People are looking for a way out of “{brand}”",
        f"People are looking for a way out of “{brand}”: "
        f"{n(vol)} searches a month ask for alternatives to it or weigh it "
        f"against others, led by “{top.term}” ({n(top.volume)} a "
        f"month)" + (f", and they ran at {g:.2f}x the year before."
                     if g is not None else "."),
        f"A real number of people who use or have considered "
        f"“{brand}” are looking for something else.",
        f"Almost nobody is looking to replace “{brand}”.",
        {"brand": brand, "searches_a_month": vol,
         "year_on_year": None if g is None else round(g, 3),
         "searches": [f"{k.term} ({n(k.volume)}/mo)" for k in
                      sorted(kws, key=lambda k: -k.volume)[:10]],
         "other_brands": {b: sum(k.volume for k in ks)
                          for b, ks in ranked[1:6]}},
        _examples(sorted(kws, key=lambda k: -k.volume)[:6]), brand)]


def patterns(graph: K.Graph) -> list[tuple[str, list[K.Keyword], list[str]]]:
    """Repeatable keyword patterns: one slot, three or more fillers.

    Two is a pair; three is a pattern. Fillers that are spellings of one
    another count once.
    """
    groups: dict[str, dict[str, K.Keyword]] = {}
    for k in graph.keywords.values():
        toks = K.tokens(k.term)
        if k.volume <= 0 or len(toks) < 2:
            continue
        for i, tok in enumerate(toks):
            if len(tok) < 2:
                continue
            skeleton = " ".join(toks[:i] + ["{x}"] + toks[i + 1:])
            slot = groups.setdefault(skeleton, {})
            if K.stem(tok) not in {K.stem(t) for t in slot}:
                slot[tok] = k
    found = []
    for skeleton, slot in groups.items():
        if len(slot) >= 3:
            kws = list(slot.values())
            found.append((skeleton, kws, list(slot)))
    found.sort(key=lambda x: -sum(k.volume for k in x[1]))
    return found


def pattern_claim(graph: K.Graph, skeleton: str, kws: Sequence[K.Keyword],
                  fillers: Sequence[str]) -> list[Claim]:
    vol = sum(k.volume for k in kws)
    top = max(kws, key=lambda k: k.volume)
    shown = ", ".join(f"“{f}”" for f in fillers[:6])
    pretty = skeleton.replace("{x}", "…")
    return [_claim(
        graph, f"market|pattern|{skeleton}", "pattern",
        f"Build one page for every “{pretty}”",
        f"Build one page for every “{pretty}”: {n(len(kws))} "
        f"variants — {shown}"
        f"{' and more' if len(fillers) > 6 else ''} — draw {n(vol)} searches "
        f"a month together, the largest “{top.term}” "
        f"({n(top.volume)} a month).",
        f"Many searches here follow one pattern, “{pretty}”, so a "
        f"single kind of page repeated for each variant would answer all of "
        f"them.",
        "The searches here are each different, with no pattern one kind of "
        "page could repeat across.",
        {"pattern": pretty, "variants": len(kws), "searches_a_month": vol,
         "fillers": list(fillers)[:20],
         "searches": [f"{k.term} ({n(k.volume)}/mo)" for k in
                      sorted(kws, key=lambda k: -k.volume)[:12]]},
        _examples(sorted(kws, key=lambda k: -k.volume)[:6]))]


def new_demand(graph: K.Graph) -> list[Claim]:
    """Searches that barely existed three years ago and do now.

    "Barely existed": no month two to three years ago above 10, the
    smallest volume Google reports that is not zero — a property of the
    source, not a threshold picked here. "Do now": a typical month this
    year at least as large as the market's typical search. Without that,
    anything that went from nothing to twenty qualified, and on `cad to
    bim` the finding was led by `autodesk certified professional revit for
    architectural design` — a certificate's full name, not a new demand
    (it-23). The bar is the market's own median, so it moves with the
    market rather than with a number chosen here.
    """
    sizes = [k.volume for k in graph.keywords.values() if k.volume > 0]
    typical = statistics.median(sizes) if sizes else 0
    fresh = []
    for k in graph.keywords.values():
        s = k.trend
        if len(s) < 36 or not K.growth_readable(s):
            continue
        then, now = s[-36:-24], s[-12:]
        if (max(then) <= 10 and statistics.median(now) > max(then)
                and statistics.median(now) >= typical):
            fresh.append(k)
    if len(fresh) < 2:
        return []
    fresh.sort(key=lambda k: -statistics.median(k.trend[-12:]))
    vol = sum(statistics.median(k.trend[-12:]) for k in fresh)
    top = fresh[0]
    year = (top.months[-36][:4] if len(top.months) >= 36 else "three years ago")
    return [_claim(
        graph, "market|new_demand", "new_demand",
        f"New since {year}: “{top.term}”"
        + (f" and {len(fresh) - 1} more" if len(fresh) > 1 else ""),
        f"New since {year}: {n(len(fresh))} searches here had no month above "
        f"10 three years ago and now draw about {n(vol)} a month together, "
        f"led by “{top.term}” "
        f"({n(statistics.median(top.trend[-12:]))} a month).",
        "Part of this market is new: people have started searching for things "
        "here that almost nobody searched for a few years ago.",
        "What people search for here has been the same for years; nothing new "
        "has appeared.",
        {"new_searches": len(fresh), "searches_a_month_now": round(vol),
         "typical_search_here_a_month": typical,
         "searches": [f"{k.term} ({n(statistics.median(k.trend[-12:]))}/mo "
                      f"now)" for k in fresh[:10]]},
        [f"{k.term} ({n(statistics.median(k.trend[-12:]))}/mo now, "
         f"{usd(k.cpc)} a click)" for k in fresh[:6]])]
