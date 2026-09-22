#!/usr/bin/env python3
"""keyword-insights — one keyword and an effort in, insights out.

Nothing in this program writes prose about what it found. Sentences come
from templates filled with measured numbers; every judgment — whether a
search belongs to the market, what it is about, what the person wants, what
kind of answer and who they are, whether a business here could sell to
them, whether a statement holds and what it is worth — comes from Jev.
There is no language model in the loop, which is what makes a run
reproducible and an eval meaningful.

It is a graph search, ranked the way practitioners rank keywords:

    COLLECT     the businesses ranking for the seed, harvested, and
                Google's ideas around the seed
    PLACE       every search gets every column — measured by DataForSEO,
                judged by Jev
    RANK        the stack: what a seller here could sell to first, by the
                money in its clicks, then everything else
    EXPAND      the top of the stack not yet explored, one call per unit of
                effort — then place and rank again; stop when the best of
                what is left brings back nothing a newcomer could sell to
    READ        page one for the top of the stack, and the insights the
                ranked table supports, each tested and ranked by value

Usage:
    loop.py run "crm software" --effort 3 --for "a founder choosing what to build"
    loop.py run "crm software" --dry-run
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import insights
import jev
import judge
import kgraph as K
import market_net as MN
import report as report_mod
import seo
import serp as S
import opportunity as O
import stackrank

HERE = os.path.dirname(os.path.abspath(__file__))
SKILL = os.path.dirname(HERE)
SEO_CACHE = os.path.join(SKILL, ".cache", "dataforseo")
JEV_CACHE = os.path.join(SKILL, ".cache", "jev")

# How many times the top of the stack is expanded when no effort says so.
DEFAULT_ITERATIONS = 3

# A harvest costs $0.09 whether or not anyone reads it, and vetting one
# keyword for belonging to this market costs about a hundred-thousandth of
# a cent. Throwing away 1,467 rows you already bought, unread, to save
# $0.016 of judgment is backwards, so this is not an effort knob: it is set
# high enough to read whatever a site harvest returns. A harvest larger
# than this loses its thinnest tail, and the run says so.
RELEVANCE_CAP = 2500

# A page one takes five to fifteen seconds to come back, and a run at
# effort 5 reads up to a hundred and ten: nearly a quarter of an hour one at
# a time. Eight at once, each still through the run's own client, cache and
# ledger. The budget is checked for the whole batch before any is sent.
PAGE_WORKERS = 8
PAGE_COST = 0.0025

# How many pages the head may take in a run, as a multiple of its size.
GROUND_READS = 4

# --------------------------------------------------------------------------
# Effort
#
# One dial instead of many. Effort is how far the graph search goes: how
# many ranking businesses get harvested at the start, how many times the
# top of the stack is expanded (`iterations`, one $0.09 call each, up to
# twenty seeds), how many first pages are read — the market's largest
# searches held to what Google shows (`ground`) and the top of the stack
# read for where someone could win (`pages`), both at $0.002 a page — how
# many searches Labs is asked the difficulty of, how many statements get
# tested, and the ceiling on spend.
#
# Every search collected is placed: judging one costs about a thousandth of
# a cent, so the stack is the whole market, not its head.
#
# Effort is a **ceiling, not a target**. The search stops when the best of
# what is left on the stack brings back nothing a newcomer could sell to, so
# effort 5 does not mean eight expansions; it means up to eight. A market
# with nothing in it costs the same at every setting.
EFFORT = {
    1: {"name": "glance", "sites": 1, "iterations": 1, "max_claims": 60,
        "max_spend": 0.40, "competition": 150, "ground": 10, "pages": 10},
    2: {"name": "quick", "sites": 1, "iterations": 2, "max_claims": 80,
        "max_spend": 0.60, "competition": 250, "ground": 15, "pages": 20},
    3: {"name": "normal", "sites": 2, "iterations": 3, "max_claims": 90,
        "max_spend": 0.90, "competition": 400, "ground": 25, "pages": 30},
    4: {"name": "deep", "sites": 3, "iterations": 5, "max_claims": 120,
        "max_spend": 1.40, "competition": 550, "ground": 40, "pages": 45},
    5: {"name": "exhaustive", "sites": 4, "iterations": 8, "max_claims": 160,
        "max_spend": 2.20, "competition": 700, "ground": 50, "pages": 60},
}
EFFORT_NAMES = {v["name"]: k for k, v in EFFORT.items()}
DEFAULT_EFFORT = 3


def _effort_label(level: int) -> str:
    return f"{level} ({EFFORT[level]['name']})"


def resolve_effort(args) -> dict:
    """Fill in whatever the caller did not set. Explicit always wins."""
    level = EFFORT[args.effort]
    for key in ("sites", "iterations", "max_claims", "max_spend"):
        if getattr(args, key, None) is None:
            setattr(args, key, level[key])
    return level

def frontier(graph: K.Graph, limit: int = seo.MAX_SEEDS) -> list:
    """The next nodes of the graph search: the top of the stack not yet
    expanded — searches a seller here could sell to, most valuable first,
    as many as one expansion takes."""
    return [k for k in graph.stack() if k.sellable and not k.expanded][:limit]


DEFAULT_ASKER = ("someone deciding whether and how to enter this market, "
                 "who has not worked in it before")


class Run:
    def __init__(self, args) -> None:
        self.args = args
        self.graph = K.Graph(args.keyword, args.location, args.language)
        # The forecast is the one call that answers what the reader came
        # with, and it runs last. Reserving its money up front stops a run
        # spending everything on probes and then being unable to afford the
        # answer.
        reserve = 0.0 if args.no_forecast else 0.10
        self.seo = seo.Seo(cache_dir=SEO_CACHE, location=args.location,
                           language=args.language,
                           max_spend_usd=max(args.max_spend - reserve, 0.10),
                           offline=args.offline)
        self.reserve = reserve
        self.client = jev.Client(cache_dir=JEV_CACHE,
                                 use_cache=not args.no_jev_cache)
        self.serp = S.Serp(self.seo)
        # Every page one read this run, by search, as DataForSEO typed it.
        self.pages: dict[str, list[dict]] = {}
        self.unreadable: set[str] = set()
        self.grounded: set[str] = set()
        self.ground_reads = 0
        self.opportunities: list = []
        self.share_of_voice: list = []
        self.stages: list[judge.Stage] = []
        self.trail: list[insights.Thread] = []
        self.claims: list[judge.Claim] = []
        self.net: MN.Net | None = None
        self.evidence: dict[str, float] = {}
        self.verdict: dict[str, float] = {}
        self.prior: dict[str, float] = {}
        self.forecast: dict | None = None
        self.ranked: list = []
        self.log: list[str] = []
        self.oriented_at = -1
        self.started = time.time()

    # -- plumbing --------------------------------------------------------

    def say(self, text: str) -> None:
        self.log.append(text)
        if not self.args.quiet:
            print(text, flush=True)

    def stage(self, st: judge.Stage) -> judge.Stage:
        self.stages.append(st)
        for note in st.notes:
            self.say(f"      · {note}")
        return st

    @property
    def jev_usage(self) -> jev.Usage:
        total = jev.Usage()
        for st in self.stages:
            total.add(st.usage)
        return total

    # -- OBSERVE ---------------------------------------------------------

    def observe(self, action: str, payload: list[str], why: str) -> list[str]:
        self.say(f"  OBSERVE  {action}: {why}")
        if action == "expand":
            call = self.seo.expand(payload)
        elif action == "price":
            call = self.seo.price(payload)
        else:
            call = self.seo.site(payload[0])
        before = set(self.graph.keywords)
        added = self.graph.add_rows(call.rows)
        self.say(f"      · {len(call.rows):,} rows, {added:,} new"
                 f" · ${call.cost_usd:.4f}"
                 f"{' (cached)' if call.from_cache else ''}")
        fresh = [self.graph.keywords[t] for t in self.graph.keywords
                 if t not in before]
        gone = set(self.vet(fresh))
        if gone:
            self.say(f"      · {len(gone):,} of them are not in this "
                     f"market — dropped before they can outvote it")
        return [k.term for k in fresh if k.term not in gone]

    def vet(self, fresh: list) -> list[str]:
        """Drop everything in `fresh` that does not belong to this market.

        A business is wider than its market, and so is Google's idea list
        for a word. Harvesting Radar Healthcare for `ambulance software`
        brought in 503,680 searches a month of which 680 were ambulances;
        expanding around a keyword-research tool brought in
        `adwords for google` at 550,000 a month, which is people looking
        for Google Ads. Topics are mined by volume, so left in, the
        largest intruder outvotes the market's own vocabulary and the
        report comes out about the wrong thing.

        Two rules, both learned the expensive way.

        **An unvetted row is not evidence.** The filter reads the biggest
        terms first and used to admit everything below the cap without
        asking. Sorting by volume means the terms it checks are the
        incumbent's largest pages — the ones most likely to be its *other*
        business — so it was fair to wonder whether the tail was cleaner
        than the head. It is not: of 200 sampled from Radar Healthcare's
        1,467 unchecked keywords, 17% belonged to this market, against 18%
        of the 400 that were checked.

        **Every path in, not just the ones you thought of.** This ran on
        site harvests only, which was a guess about where intruders come
        from and it was wrong. On `answerthepublic.com` the site harvests
        were clean and 71% of the corpus volume arrived through probe
        expansions, unvetted, led by a 550,000-a-month search for a
        different product. A filter that covers one of two doors is not a
        filter.

        **Then the whole market is checked for a search larger than the
        rest of it combined** — `drawings`, admitted to `cad to bim` at
        1.83 million a month because the relevance question reads a word
        in the market's sense. See `judge.outvoting`.
        """
        if not fresh:
            return []
        ranked = sorted(fresh, key=lambda k: -k.volume)
        candidates = ranked[:self.args.relevance_cap]
        unread = [k.term for k in ranked[self.args.relevance_cap:]]
        drop, stage = judge.keep_relevant(
            self.client, self.graph, candidates, self.args.asker)
        self.stage(stage)
        if unread:
            self.say(f"      · {len(unread):,} below the "
                     f"{self.args.relevance_cap:,} the cap pays to read — "
                     f"not vetted, so not admitted")
        gone = list(drop) + unread
        # The whole market, not just this batch: a search is only an
        # outvoter against everything already admitted, and a batch of
        # seventeen always has a majority term.
        leaving = set(gone)
        admitted = [k for k in self.graph.keywords.values()
                    if k.term not in leaving]
        invented, st = judge.invented_giants(self.client, self.graph,
                                             admitted, self.args.asker)
        if st.questions:
            self.stage(st)
        leaving |= set(invented)
        admitted = [k for k in admitted if k.term not in leaving]
        outvoted, st = judge.outvoting(self.client, self.graph, admitted,
                                       self.args.asker)
        if st.questions:
            self.stage(st)
        gone += invented + outvoted
        if gone:
            self.graph.drop(gone)
        # And last, the only check that does not read words or compare
        # sizes: what Google shows for the searches that carry the market.
        return gone + self.ground()

    # -- page one --------------------------------------------------------

    def prefetch(self, terms: list[str]) -> None:
        """Buy page one for several searches at once, in the order given."""
        todo = [t for t in dict.fromkeys(terms)
                if t not in self.pages and t not in self.unreadable]
        room = int((self.seo.max_spend_usd - self.seo.ledger.spent_usd)
                   / PAGE_COST)
        todo = todo[:max(room, 0)]
        if len(todo) < 2:
            return

        def fetch(term: str):
            try:
                return self.serp.page(term), None
            except S.SerpError as exc:
                return None, exc
        with ThreadPoolExecutor(max_workers=PAGE_WORKERS) as pool:
            for term, (rows, exc) in zip(todo, pool.map(fetch, todo)):
                if rows is not None:
                    self.pages[term] = rows
                    continue
                self.unreadable.add(term)
                if len(self.unreadable) == 1:
                    self.say(f"      · page one not read: {exc}")

    def read_page(self, term: str) -> list[dict] | None:
        """Page one for a search, once per run; None if it cannot be had."""
        if term in self.pages:
            return self.pages[term]
        if term in self.unreadable:
            return None
        try:
            rows = self.serp.page(term)
        except S.SerpError as exc:
            self.unreadable.add(term)
            if len(self.unreadable) == 1:
                self.say(f"      · page one not read: {exc}")
            return None
        self.pages[term] = rows
        return rows

    def ground(self, terms: list[str] | None = None) -> list[str]:
        """Hold the market's largest searches to what Google shows for them.

        The N largest searches are each read against their first page, and
        whatever is about something else leaves. Dropping one lets the next
        largest into the head, so it repeats until the head is all read.
        Every harvest and probe brings its own newcomers to the head, so the
        run may read four times N pages in all: at twice N, `cad to bim`
        spent the whole allowance on its four harvests, and the probes after
        them went unread (it-23). Given `terms`, those are read instead:
        pages already bought for another reason cost nothing to check.
        """
        n = EFFORT[self.args.effort]["ground"]
        if self.args.no_ground or n <= 0:
            return []
        cap = GROUND_READS * n
        gone: list[str] = []
        while True:
            if terms is None:
                if self.ground_reads >= cap:
                    break
                head = sorted((k for k in self.graph.keywords.values()
                               if k.volume > 0),
                              key=lambda k: (-k.volume, k.term))[:n]
                todo = [k.term for k in head if k.term not in self.grounded
                        and k.term not in self.unreadable]
                todo = todo[:cap - self.ground_reads]
            else:
                todo = [t for t in terms if t in self.graph.keywords
                        and t not in self.grounded and t in self.pages]
            if not todo:
                break
            self.prefetch(todo)
            pages = {}
            for term in todo:
                rows = self.read_page(term)
                if rows is None:
                    continue
                self.grounded.add(term)
                pages[term] = S.organic_rows(rows)
            if terms is None:
                self.ground_reads += len(todo)
            if not pages:
                break
            drop, st = judge.ground(self.client, self.graph, pages,
                                    self.args.asker)
            self.stage(st)
            if drop:
                self.graph.drop(drop)
                gone += drop
            if terms is not None or not drop:
                break
        return gone

    def harvest(self, query: str) -> int:
        """Turn a word into the businesses selling behind it, then harvest.

        This is the opening move because it is worth far more than the
        alternative. Measured on one market at the same $0.09:

            expand "epcr"      ->    31 keywords,   2,100 searches a month
            for-site eso.com   ->   619 keywords, 367,940 searches a month

        `for-keywords` expands off the breadth of a string, so a niche
        phrase returns almost nothing: `investtech` gave 18 rows,
        `ambulance software` 25. A site expands off what a live business is
        about, and a business that has paid to rank is evidence somebody is
        selling here. Invented keywords are hypotheses; harvested ones are
        observed commercial vocabulary.

        Finding nobody who sells is not a failure of the move. It is the
        most decisive thing this loop can learn about a market, and it
        falls through to expansion saying so.
        """
        self.say(f"  HARVEST  who is actually selling behind “{query}”")
        try:
            found = self.serp.results(
                query, country=_country_code(self.args.location),
                hl=self.args.language, limit=10)
        except S.SerpError as exc:
            self.say(f"      . no search results: {exc}")
            return 0
        plausible = S.plausible_vendors(found)
        self.say(f"      . {len(found)} results, {len(plausible)} could be "
                 f"a business")
        sellers, stage = judge.pick_sellers(self.client, self.graph,
                                            plausible, self.args.asker)
        self.stage(stage)
        self.ranked = found
        if not sellers:
            return 0

        # One site at a time, and as many as effort asks for.
        #
        # An earlier version stopped as soon as the corpus was big enough to
        # analyse, which was a sensible way to save $0.09 and a silent
        # override of the caller: asked for four sources at effort 5 it
        # bought two, because two had produced enough keywords, and the
        # dial's top half bought nothing.
        #
        # The mistake was treating a harvest as a way to get keywords. It is
        # a way to get *a view of the market*. Two sellers agreeing about
        # vocabulary is evidence; one seller is an anecdote, and no quantity
        # of keywords from that one seller makes it two. Measured across
        # the dial, what the extra sellers buy is coverage — the share of
        # the searching whose intent is resolved — 25% at one site, 50% at
        # two, 57% at four.
        added = 0
        for site in sellers[:self.args.sites]:
            try:
                call = self.seo.site(site.domain)
            except (seo.BudgetExceeded, seo.OfflineMiss, seo.SeoError) as exc:
                self.say(f"      . stopped harvesting: {exc}")
                break
            before = set(self.graph.keywords)
            self.graph.add_rows(call.rows)
            fresh = [self.graph.keywords[t] for t in self.graph.keywords
                     if t not in before]

            # A business is wider than its market. Harvesting Radar
            # Healthcare for `ambulance software` brought in 503,680
            # searches a month of which 680 were ambulances. Topics are
            # mined by volume, so left in, the incumbent's other business
            # outvotes this market's own vocabulary and the report comes
            # out about the wrong thing.
            #
            # The filter reads the biggest terms first and used to admit
            # everything below the cap without asking. Sorting by volume
            # means the terms it checks are the incumbent's largest pages —
            # the ones most likely to be its *other* business — so it was
            # fair to wonder whether the tail was cleaner than the head.
            # It is not: of 200 sampled from Radar Healthcare's 1,467
            # unchecked keywords, 17% belonged to this market, against 18%
            # of the 400 that were checked. The cap was admitting roughly
            # 1,200 off-market terms into a 1,648-term corpus.
            #
            # So an unchecked keyword is not admitted. The corpus is what
            # was vetted, and the cap is what the caller is willing to vet.
            # It costs 5% of the harvested volume and removes four fifths
            # of the terms, because the tail is long and thin by
            # construction.
            self.vet(fresh)

            kept = [t for t in self.graph.keywords
                    if self.graph.keywords[t].source == f"site:{site.domain}"]
            volume = sum(self.graph.keywords[t].volume for t in kept)
            self.graph.sites[site.domain] = K.Site(
                domain=site.domain, title=site.title, snippet=site.snippet,
                rank=site.rank, kind=site.kind, harvested=len(kept),
                volume=volume)
            added += len(kept)
            self.say(f"      . {site.domain}: {len(call.rows):,} rows -> "
                     f"{len(kept):,} in this market, {volume:,} searches/mo"
                     f" - ${call.cost_usd:.4f}")
        return added

    # -- ORIENT ----------------------------------------------------------

    def orient(self) -> None:
        """Place every search not yet placed: every judged column."""
        self.say("  PLACE    every search, every column")
        g = self.graph

        phrases = [p for p in K.mine_phrases(g.keywords.values(), limit=40)
                   if p not in g.topics]
        if phrases:
            self.stage(judge.confirm_phrases(self.client, g, phrases,
                                             self.args.asker))
        tokens = [t for t in K.mine_entities(g.keywords.values(), limit=30)
                  if t not in g.entities]
        if tokens:
            self.stage(judge.confirm_entities(self.client, g, tokens,
                                              self.args.asker))

        unjudged = sorted((k for k in g.keywords.values() if not k.judged),
                          key=lambda k: (-k.volume, k.term))
        if self.args.judge_cap:
            unjudged = unjudged[:self.args.judge_cap]
        if unjudged:
            self.stage(judge.assign(self.client, g, unjudged, self.args.asker))
        self.oriented_at = len(g.keywords)
        covered = K.share(g.certain_volume, g.total_volume)
        sellable = sum(1 for k in g.keywords.values() if k.sellable)
        self.say(f"      · {len(g.judged):,} searches placed; {len(g.certain):,} "
                 f"revealed what the person wanted ({covered * 100:.0f}% of the "
                 f"searching); {sellable:,} are people a newcomer could sell "
                 f"to")

    def infer(self) -> None:
        """One request supplies every table and reads every measurement.

        After this, any posterior is arithmetic. That is the whole point:
        the loop re-infers on every iteration, and on every re-inference
        after the first the tables come from cache, so updating the whole
        picture with new evidence costs nothing.
        """
        readings = MN.readings(self.graph.stats())
        questions = {**MN.cpt_questions(), **MN.observation_questions(readings)}
        result = self.client.ask(
            {"domain": "commercial markets people search for on Google"},
            questions)
        self.stage(judge.Stage(
            "infer", len(questions), result.usage,
            [f"{len(MN.cpt_questions())} table rows, "
             f"{len(readings)} measurements read"]))
        self.net = MN.build(result)
        self.evidence = MN.read_evidence(result, list(readings))
        self.prior = self.net.posterior({})
        self.verdict = self.net.posterior(self.evidence)
        for name in MN.DECISION:
            self.say(f"      · P({name}) "
                     f"{self.prior[name]:.2f} \u2192 {self.verdict[name]:.2f}")

    def find_claims(self) -> list[judge.Claim]:
        self.say("  DECIDE   testing every claim the data could support")
        candidates = insights.generate(self.graph) + stackrank.claims(
            self.graph)
        if self.args.max_claims:
            candidates = candidates[:self.args.max_claims]
        if not candidates:
            return []
        if self.args.arm == "code":
            insights.select_by_code(self.graph, candidates)
            kept = [c for c in candidates if c.survived()]
            self.say(f"      · {len(kept)}/{len(candidates)} passed the "
                     f"threshold arm")
        else:
            self.stage(judge.adjudicate(self.client, self.graph, candidates,
                                        self.args.asker))
            kept = [c for c in candidates if c.survived()]
            self.stage(judge.rank(self.client, self.graph, candidates,
                                  self.args.asker))
        self.claims = candidates
        return kept

    # -- the loop --------------------------------------------------------

    def go(self) -> None:
        a = self.args
        self.say(f"seed “{a.keyword}” · {a.location} · up to "
                 f"{a.iterations} expansion(s) of the stack · ceiling "
                 f"${a.max_spend:.2f}")
        self.say(f"asking on behalf of: {a.asker}")

        harvested = 0
        if not a.no_harvest:
            harvested = self.harvest(a.keyword)
        if not harvested:
            # Either nobody selling ranks here, or harvesting was declined.
            # Google's own idea list is the fallback, and on a niche seed it
            # returns very little, which is itself worth reporting.
            self.say("  OBSERVE  falling back to Google's idea list")
        try:
            self.observe("expand", [a.keyword], f"what surrounds “{a.keyword}”")
        except (seo.BudgetExceeded, seo.OfflineMiss) as exc:
            self.say(f"      · not bought: {exc}")
        seed = self.graph.keywords.get(a.keyword.strip().lower())
        if seed is not None:
            seed.expanded = True

        # The graph search, best first. Every search is placed and ranked;
        # then, as far as effort allows, the top of the stack not yet
        # explored is expanded — Google's own ideas around the searches
        # worth most — and what comes back is vetted, grounded, placed and
        # ranked again. It goes deeper where the value is. It replaced a
        # loop that chased questions raised by findings and priced template
        # guesses to answer them — `top modelling` was one of those guesses
        # (it-23): expanding real searches brings back real searches.
        self.orient()
        for depth in range(1, a.iterations + 1):
            nodes = frontier(self.graph)
            if not nodes:
                self.say("  STOP     nothing on the stack left to explore")
                break
            if not self.expand(nodes, depth):
                break

        if len(self.graph.keywords) != self.oriented_at:
            self.orient()
        # Page one for the top of the stack, before anything is read off it:
        # nothing below rests on a search Google shows to be about
        # something else.
        self.read_top_pages()
        self.graph.stack()
        self.infer()
        self.find_claims()
        self.find_opportunities()
        if not self.args.no_forecast:
            # Release the reserve now that the search has had its turn.
            self.seo.max_spend_usd += self.reserve
            self.price_the_move()
        kept = [c for c in self.claims if c.survived()]
        self.say(f"\n{len(kept)} finding(s) survived · "
                 f"{self.seo.ledger.line()} · {self.jev_usage.line()}")

    def expand(self, frontier: list, depth: int) -> bool:
        """One step of the graph search: Google's ideas around the top of
        the stack. False when the search should stop."""
        seeds = [k.term for k in frontier]
        for kw in frontier:
            kw.expanded = True
        thread = insights.Thread(
            key=f"depth:{depth}",
            question=(f"What surrounds the top of the stack — "
                      f"“{seeds[0]}”"
                      + (f" and {len(seeds) - 1} more" if len(seeds) > 1
                         else "") + "?"),
            action="expand", payload=seeds, depth=depth, status="chasing")
        self.trail.append(thread)
        self.say(f"\ndepth {depth}/{self.args.iterations}")
        self.say(f"  EXPAND   {thread.question}")
        before = {k.term for k in self.graph.keywords.values() if k.sellable}
        try:
            fresh = self.observe("expand", seeds, thread.question)
        except (seo.BudgetExceeded, seo.OfflineMiss) as exc:
            thread.status, thread.note = "unfunded", str(exc)
            self.say(f"  STOP     {exc}")
            return False
        for term in fresh:
            if term in self.graph.keywords:
                self.graph.keywords[term].depth = depth
        self.orient()
        found = [k for k in self.graph.keywords.values()
                 if k.sellable and k.term not in before]
        worth = sum(k.money for k in found)
        thread.status = "paid_off" if found else "dead_end"
        thread.note = (f"{len(fresh):,} new searches in this market; "
                       f"{len(found):,} of them people a newcomer could sell "
                       f"to, worth {insights.money0(worth)} a month")
        self.say(f"      · {thread.note}")
        if not found:
            self.say("  STOP     the best of what is left brought back nothing "
                     "a newcomer could sell to")
            return False
        return True

    # -- where someone could win -------------------------------------------

    def read_top_pages(self) -> list[str]:
        """Page one for the top of the stack, bought once and used twice:
        each is held to the same test as the market's head — is this
        search, as Google reads it, about this market? — before anything is
        read off the stack, and then read for where someone could win.

        The top of the stack is small next to the head, so the grounding by
        size never reaches most of it, and it is where the report's money
        is: `top modelling` read as a buying search and sat among the
        buyers of `cad to bim`, pulling its average buyer click down to
        $8.33 (it-23).
        """
        level = EFFORT[self.args.effort]
        top = [k for k in self.graph.stack() if k.sellable][:level["pages"]]
        self.prefetch([k.term for k in top])
        got = [k.term for k in top if self.read_page(k.term) is not None]
        if not got:
            return []
        self.say(f"  PAGE ONE read for the top {len(got)} of the stack")
        return self.ground(got)

    def find_opportunities(self) -> None:
        """The practitioners' questions, asked of the market the loop built.

        How hard is each buying search to win (Labs difficulty); which of
        them one page could answer (SERP clustering: three shared results
        in the top ten); what holds each group's first page (each result
        read by Jev) and so how much of the buyer money behind it sits on
        pages not built for it; who takes the clicks (share of voice); who
        is being left (switching searches, bought for the brands found);
        and then the opportunity-shaped findings, tested and ranked like
        every other.
        """
        a, level = self.args, EFFORT[self.args.effort]
        self.say("  WHERE    where someone could win")
        g = self.graph

        # How hard: the buying core first, then the largest searches.
        core = sorted(O.buying_core(g), key=lambda k: (-k.money, k.term))
        biggest = sorted(g.keywords.values(), key=lambda k: -k.volume)
        ask = list(dict.fromkeys([k.term for k in core]
                                 + [k.term for k in biggest]))
        ask = ask[:level["competition"]]
        if ask:
            try:
                call = self.seo.competition(ask)
                placed = g.set_competition(call.rows)
                self.say(f"      · difficulty and page-one strength for "
                         f"{placed:,} searches · ${call.cost_usd:.4f}")
            except (seo.OfflineMiss, seo.BudgetExceeded, seo.SeoError) as exc:
                self.say(f"      · difficulty not measured: {exc}")

        # Who is being left: "alternatives to X" for the names found.
        brands = g.confirmed_entities[:5]
        if brands and a.effort >= 3:
            terms = [t for b in brands for t in (
                f"{b} alternative", f"{b} alternatives",
                f"alternatives to {b}", f"{b} competitors", f"{b} vs")]
            before = set(g.keywords)
            try:
                call = self.seo.price(terms)
                g.add_rows(call.rows)
                fresh = [g.keywords[t] for t in g.keywords if t not in before]
                gone = set(self.vet(fresh))
                names = set(g.confirmed_entities)
                for kw in fresh:
                    if kw.term not in gone and kw.term in g.keywords:
                        kw.entities = sorted(n for n in names
                                             if n in set(K.tokens(kw.term)))
                self.say(f"      · switching searches for {len(brands)} "
                         f"name(s): {len(fresh) - len(gone)} found · "
                         f"${call.cost_usd:.4f}")
            except (seo.OfflineMiss, seo.BudgetExceeded, seo.SeoError) as exc:
                self.say(f"      · switching not measured: {exc}")

        # Which buyers at the top of the stack one page could answer, and
        # what holds that page. Buyers only: the families below speak of
        # buying searches, and with learners among them "start with “as
        # builts”" called 7,280 people learning what an as-built is "people
        # buying or comparing" (it-24).
        core = [k for k in g.stack() if K.tier(k) == 0
                and k.term in self.pages]
        organic = {k.term: S.organic_rows(self.pages[k.term]) for k in core}
        features = {k.term: S.features(self.pages[k.term]) for k in core}
        groups = O.serp_clusters(core, organic, features)
        for c in groups:
            self.stage(judge.read_page_one(self.client, g, c.anchor.term,
                                           c.page, a.asker))
        # The file reads as "where the buyer money is", most first — the
        # same order as the line under the report's title.
        self.opportunities = sorted(groups, key=lambda c: (
            -c.open_prize, -c.prize, c.anchor.term))
        if groups:
            covered = K.share(sum(c.prize for c in groups),
                              sum(k.money for k in g.keywords.values()
                                  if K.tier(k) == 0))
            self.say(f"      · the top {len(core)} buyers on the stack fall "
                     f"into {len(groups)} page(s)' worth of work, carrying "
                     f"{covered:.0%} of the money a newcomer could reach "
                     f"from buyers")

        # Who takes the clicks.
        shares = []
        buyers = [k.term for k in sorted(O.buying_core(g),
                                         key=lambda k: (-k.money, k.term))]
        if buyers and a.effort >= 2:
            try:
                call = self.seo.share_of_voice(buyers[:200])
                shares = call.rows
                self.say(f"      · share of voice across "
                         f"{min(len(buyers), 200)} buying searches · "
                         f"${call.cost_usd:.4f}")
            except (seo.OfflineMiss, seo.BudgetExceeded, seo.SeoError) as exc:
                self.say(f"      · share of voice not measured: {exc}")
        self.share_of_voice = shares

        # One template, many searches: the broadest patterns, checked.
        found = []
        for skeleton, kws, fillers in sorted(
                O.patterns(g), key=lambda x: (-len(x[2]),
                                              -sum(k.volume for k in x[1])))[:3]:
            ok, st = judge.same_kind(self.client, g, skeleton, fillers,
                                     a.asker)
            self.stage(st)
            if ok:
                found += O.pattern_claim(g, skeleton, kws, fillers)
                break

        # Where to start: the genuine trade-offs, then Jev's pick.
        front = O.pareto(O.candidates(groups))
        chosen = front[0] if len(front) == 1 else None
        if len(front) > 1:
            pick, st = judge.pick_start(self.client, g, O.rank_words(front),
                                        a.asker)
            self.stage(st)
            chosen = next((c for c in front if c.anchor.term == pick), None)

        claims = (O.start_here(g, chosen, front, groups)
                  + O.open_door(g, groups, chosen)
                  + O.who_answers(g, groups)
                  + O.customer_cost(g)
                  + O.who_owns(g, shares, O.domain_kinds(groups))
                  + O.share_of_search(g) + O.switching(g) + found
                  + O.new_demand(g))
        if not claims:
            return
        if a.arm == "code":
            insights.select_by_code(g, claims)
        else:
            self.stage(judge.adjudicate(self.client, g, claims, a.asker))
        kinds = {c.kind for c in claims}
        self.claims = [c for c in self.claims if c.kind not in kinds] + claims
        if a.arm != "code":
            self.stage(judge.rank(self.client, g, self.claims, a.asker))
        kept = sum(1 for c in claims if c.survived())
        self.say(f"      · {kept}/{len(claims)} opportunity finding(s) "
                 f"survived")

    # -- what it would cost to act on any of this -------------------------

    # Which searchers you would actually bid on. Not everyone who searches:
    # someone reading a definition or hunting a job is not a click worth
    # buying, and including them would forecast a market that does not
    # exist.
    BIDDABLE = K.BIDDABLE  # one definition, shared with the topic rows

    def price_the_move(self) -> None:
        """One call that turns the whole report into a decision.

        Search volume says how many people look. This says how many of them
        can actually be bought and what they would cost — Google's own
        forecast rather than volume multiplied by a headline click price.
        The difference matters: a market with 165,000 searches a month can
        have 232 clicks available at a bid worth making, and knowing that
        before committing a budget is most of the value of the exercise.

        The bid is derived, not invented: the median top-of-page bid already
        measured on the very keywords being forecast.
        """
        targets = sorted(
            (k for k in self.graph.certain
             if k.job in self.BIDDABLE and k.volume > 0 and k.high_bid > 0),
            key=lambda k: -k.volume)[:seo.MAX_FORECAST]
        if len(targets) < 3:
            self.say("      · too few biddable searches to forecast")
            return
        bid = K.median([k.high_bid for k in targets])
        if bid <= 0:
            return
        self.say(f"  PRICE    what it costs to reach the "
                 f"{len(targets):,} searches worth bidding on")
        try:
            call = self.seo.forecast([k.term for k in targets], bid=bid)
        except (seo.BudgetExceeded, seo.OfflineMiss, seo.SeoError) as exc:
            self.say(f"      · not priced: {exc}")
            return
        if not call.rows:
            return
        row = dict(call.rows[0])
        row["keywords"] = len(targets)
        row["searches"] = sum(k.volume for k in targets)
        row["budget"] = self.args.budget
        self.forecast = row
        self.say(f"      · {row['clicks']:,.0f} clicks/month at "
                 f"${row['cpc']:.2f} each = ${row['cost']:,.0f}/month "
                 f"(bid ${row['bid']:,.0f})")

    # -- output ----------------------------------------------------------

    def manifest(self) -> dict:
        return {
            "seed": self.args.keyword,
            "location": self.args.location,
            "language": self.args.language,
            "asker": self.args.asker,
            "arm": self.args.arm,
            "effort": _effort_label(self.args.effort),
            "currency": self.args.currency,
            "iterations_requested": self.args.iterations,
            "seconds": round(time.time() - self.started, 1),
            "dataforseo": self.seo.ledger.as_dict(),
            "jev": self.jev_usage.as_dict(),
            "stages": [{"name": s.name, "questions": s.questions,
                        "usd": round(s.usage.usd, 6), "notes": s.notes}
                       for s in self.stages],
            "keywords_measured": len(self.graph.keywords),
            "keywords_placed": len(self.graph.judged),
            "keywords_certain": len(self.graph.certain),
            "volume_measured": self.graph.total_volume,
            "volume_placed": self.graph.judged_volume,
            "volume_certain": self.graph.certain_volume,
            "claims_generated": len(self.claims),
            "claims_kept": sum(1 for c in self.claims if c.survived()),
            "verdict": {k: round(v, 3) for k, v in self.verdict.items()},
            "prior": {k: round(v, 3) for k, v in self.prior.items()},
            "evidence": {k: round(v, 3) for k, v in self.evidence.items()},
            "readings": MN.readings(self.graph.stats()),
            "attribution": {
                d: [(n, round(x, 3)) for n, x in
                    (self.net.attribution(d, self.evidence) if self.net else [])]
                for d in MN.DECISION},
            "unsplittable_rows": (self.net.low_confidence if self.net else []),
            "forecast": self.forecast,
            "ranked_for_seed": [r.as_dict() for r in self.ranked],
            "harvested_from": [
                {"domain": x.domain, "kind": x.kind, "rank": x.rank,
                 "keywords": x.harvested, "searches": x.volume}
                for x in self.graph.sites.values()],
            "trail": [asdict(t) for t in self.trail],
        }


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------

def cmd_run(args) -> int:
    if args.dry_run:
        return plan(args)
    insights.set_currency(args.currency)
    run = Run(args)
    try:
        run.go()
    except seo.SeoError as exc:
        sys.stderr.write(f"error: {exc}\n")
        return 1
    except jev.JevError as exc:
        sys.stderr.write(f"error: jev: {exc}\n")
        return 1

    out = args.out or f"insights-{_slug(args.keyword)}.md"
    data_dir = report_mod.data_dir_for(out)
    manifest = run.manifest()
    extra = {"opportunities": run.opportunities, "pages": run.pages,
             "shares": run.share_of_voice}
    text = report_mod.render(run.graph, run.claims, run.trail, manifest,
                             data_dir, extra)
    with open(out, "w", encoding="utf-8") as fh:
        fh.write(text)
    files = report_mod.write_data(data_dir, run.graph, run.claims, run.trail,
                                  manifest, extra)
    if args.json:
        with open(args.json, "w", encoding="utf-8") as fh:
            json.dump({"manifest": run.manifest(),
                       "graph": run.graph.to_dict(),
                       "claims": [asdict(c) for c in run.claims]}, fh, indent=2)
    print(f"\nwrote {out}\n      and {len(files)} data files in "
          f"{data_dir}/")
    return 0


def plan(args) -> int:
    """What a run would cost, without spending anything."""
    per_call = 0.09
    level = EFFORT[args.effort]
    harvest = (0 if args.no_harvest else args.sites)
    calls = harvest + 1 + args.iterations + (0 if args.no_forecast else 1)
    pages = 0 if args.no_ground else 4 * level["ground"] + level["pages"]
    labs = 0.012 + 0.00012 * level["competition"] + 0.03
    print(json.dumps({
        "seed": args.keyword,
        "location": args.location,
        "effort": _effort_label(args.effort),
        "buys": (f"{harvest} site harvest(s), the seed's ideas, up to "
                 f"{args.iterations} expansion(s) of the top of the stack, up "
                 f"to {pages} first page(s), Labs difficulty and share of "
                 f"voice, and the closing forecast"),
        "dataforseo_ceiling_usd": round(min(
            calls * per_call + pages * PAGE_COST + labs, args.max_spend), 2),
        "jev_estimate_usd": "about a thousandth of a cent a search placed",
        "note": "A keyword call bills the same for one keyword or a "
                "thousand. The search stops early when the top of the stack "
                "brings back nothing a newcomer could sell to; cached calls "
                "are free and do not count.",
    }, indent=2))
    return 0


_COUNTRIES = {"united states": "us", "united kingdom": "gb", "norway": "no",
              "sweden": "se", "denmark": "dk", "finland": "fi",
              "germany": "de", "france": "fr", "netherlands": "nl",
              "spain": "es", "italy": "it", "canada": "ca",
              "australia": "au", "ireland": "ie", "india": "in"}


def _country_code(location) -> str | None:
    """Google's country code, or nothing — which searches without one."""
    return _COUNTRIES.get(str(location).strip().lower())


def _slug(text: str) -> str:
    return "-".join("".join(c if c.isalnum() else " "
                            for c in text.lower()).split())[:60] or "run"


def _quiet_broken_pipe() -> None:
    try:
        import signal
        signal.signal(signal.SIGPIPE, signal.SIG_DFL)
    except (ImportError, AttributeError, ValueError):
        pass


def main(argv=None) -> int:
    p = argparse.ArgumentParser(
        prog="loop.py", description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)

    r = sub.add_parser("run", help="run the loop and write a report")
    r.add_argument("keyword", help="the seed keyword")
    r.add_argument("--effort", default=str(DEFAULT_EFFORT),
                   help="how far the graph search goes, 1 to 5 (or glance, "
                        "quick, normal, deep, exhaustive): sites harvested, "
                        "expansions of the top of the stack, first pages "
                        "read. A ceiling, not a target: the search stops "
                        "when the top of the stack brings back nothing a "
                        "newcomer could sell to")
    r.add_argument("--iterations", type=int, default=None,
                   help="override how many times the top of the stack may be "
                        "expanded at this effort level")
    r.add_argument("--for", dest="asker", default=DEFAULT_ASKER,
                   help="who is asking — the value of a finding is relative "
                        "to them, so this changes what survives")
    r.add_argument("--location", default="United States")
    r.add_argument("--language", default="en")
    r.add_argument("--currency", default="$",
                   help="symbol for click prices. DataForSEO returns them "
                        "unlabelled and documents them as US dollars; set "
                        "this if your Google Ads account bills otherwise")
    r.add_argument("--budget", type=float,
                   help="what you could spend a month. Given one, the "
                        "report says what it buys and whether the market "
                        "can absorb it")
    r.add_argument("--max-spend", type=float, default=None,
                   help="hard ceiling in USD, checked before each call")
    r.add_argument("--sites", type=int, default=None,
                   help="override how many ranking businesses to harvest "
                        "keywords from on the opening move")
    r.add_argument("--no-harvest", action="store_true",
                   help="seed from the keyword alone. On a niche seed that "
                        "returns very little")
    r.add_argument("--relevance-cap", type=int, default=RELEVANCE_CAP,
                   help="override how many harvested searches get checked "
                        "for belonging to this market (by volume)")
    r.add_argument("--judge-cap", type=int, default=None,
                   help="place only this many searches, largest first. By "
                        "default every search collected is placed")
    r.add_argument("--max-claims", type=int, default=None)
    r.add_argument("--arm", choices=("jev", "code"), default="jev",
                   help="'jev' judges every claim; 'code' is the "
                        "hand-tuned-threshold control arm")
    r.add_argument("--out", help="report path (default insights-<seed>.md); "
                                 "the data is written beside it, in "
                                 "<name>-data/")
    r.add_argument("--json", help="also dump graph, claims and ledger here")
    r.add_argument("--no-forecast", action="store_true",
                   help="skip the closing forecast call. It is the single "
                        "most useful $0.09 in the run, so skip it only when "
                        "the question is not about acquisition")
    r.add_argument("--no-ground", action="store_true",
                   help="do not read page one for the largest searches. "
                        "They are then admitted on their words alone, which "
                        "is how `top modelling` got into `cad to bim`")
    r.add_argument("--dry-run", action="store_true")
    r.add_argument("--offline", action="store_true",
                   help="replay cached responses only; a miss is an error")
    r.add_argument("--no-jev-cache", action="store_true")
    r.add_argument("--quiet", action="store_true")
    r.set_defaults(func=cmd_run)

    args = p.parse_args(argv)
    if getattr(args, "effort", None) is not None:
        key = str(args.effort).strip().lower()
        if key in EFFORT_NAMES:
            args.effort = EFFORT_NAMES[key]
        elif key.isdigit() and int(key) in EFFORT:
            args.effort = int(key)
        else:
            p.error(f"--effort must be 1-5 or one of "
                    f"{', '.join(EFFORT_NAMES)}; got {args.effort!r}")
        resolve_effort(args)
    return args.func(args)


if __name__ == "__main__":
    _quiet_broken_pipe()
    raise SystemExit(main())
