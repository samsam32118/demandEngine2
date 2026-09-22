#!/usr/bin/env python3
"""keyword-insights — one keyword in, a report of data-backed findings out.

Nothing in this program writes prose about what it found. Sentences come
from templates filled with measured numbers; every judgment — what a phrase
means, whether a statement holds, whether it is surprising, which thread to
chase, when to stop — comes from Jev. There is no language model in the
loop, which is what makes a run reproducible and an eval meaningful.

The loop is shaped like a person working, not like a pipeline:

    OBSERVE     measure something
    ORIENT      place it: what is this about, what are these people doing
    DECIDE      Jev: what here is out of line, and what should we ask next
    ACT         buy exactly one answer
                then: did that answer the question?
                  yes -> go deeper, its own follow-ups go on the table
                  no  -> dead end, back up and take a different thread

Usage:
    loop.py run "crm software" --iterations 3 --for "a founder choosing what to build"
    loop.py run "crm software" --dry-run
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
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

HERE = os.path.dirname(os.path.abspath(__file__))
SKILL = os.path.dirname(HERE)
SEO_CACHE = os.path.join(SKILL, ".cache", "dataforseo")
JEV_CACHE = os.path.join(SKILL, ".cache", "jev")
SERP_CACHE = os.path.join(SKILL, ".cache", "serp")

# Three probes is the smallest run that can do the thing this loop is for:
# one to see the market, one to chase what looked odd, and one to go
# somewhere else when that turns out to be a dead end. At two there is no
# backtrack, so it degenerates into a pipeline. Past four the expansions
# start returning the same keywords, because Google's idea list for any seed
# is finite — so more iterations mostly buy confirmation, which is the one
# thing the method is trying not to pay for.
DEFAULT_ITERATIONS = 3

# How many keywords get placed on the two axes per run. Search volume is
# extremely top-heavy, so a few hundred keywords carry almost all of a
# market's searching; the report states the share actually covered rather
# than implying the whole corpus was read.
DEFAULT_JUDGE_CAP = 250

# A harvest costs $0.09 whether or not anyone reads it, and vetting one
# keyword for belonging to this market costs about a hundred-thousandth of
# a cent. Throwing away 1,467 rows you already bought, unread, to save
# $0.016 of judgment is backwards, so this is not an effort knob: it is set
# high enough to read whatever a site harvest returns. A harvest larger
# than this loses its thinnest tail, and the run says so.
RELEVANCE_CAP = 2500

# --------------------------------------------------------------------------
# Effort
#
# One dial instead of five. Raising the probe count alone grows the corpus
# without growing the share of it that gets read, so coverage falls — which
# is what happened when `--iterations` was the only knob. Effort moves
# everything that has to move together: how many businesses get harvested,
# how many probes are allowed, how much of the corpus is placed on the two
# axes, how many claims are tested, and the ceiling on spend.
#
# The dial itself is the bits floor. A probe costs $0.09 and buys some
# expected reduction in uncertainty about what the reader came for, so the
# only real question is **how small an answer you will pay for**. At effort
# 1 you buy only large ones; at 5 you buy marginal ones. That also retires
# the one arbitrary constant this loop had: nobody has to pick 0.01 any
# more, because it is the caller's choice and it is stated in units they
# can argue with — hundredths of a yes/no answer.
#
# Effort is a **ceiling, not a target**. The loop already stops when nothing
# on the table clears the floor, so effort 5 does not mean eight probes; it
# means up to eight, and the measured hit rates decide. A market with
# nothing in it costs the same at every setting.
EFFORT = {
    1: {"name": "glance", "sites": 1, "iterations": 1, "judge_cap": 150,
        "max_claims": 60, "bits": 0.05, "max_spend": 0.30},
    2: {"name": "quick", "sites": 1, "iterations": 2, "judge_cap": 200,
        "max_claims": 80, "bits": 0.02, "max_spend": 0.45},
    3: {"name": "normal", "sites": 2, "iterations": 3, "judge_cap": 250,
        "max_claims": 90, "bits": 0.01, "max_spend": 0.70},
    4: {"name": "deep", "sites": 3, "iterations": 5, "judge_cap": 400,
        "max_claims": 120, "bits": 0.005, "max_spend": 1.10},
    5: {"name": "exhaustive", "sites": 4, "iterations": 8, "judge_cap": 600,
        "max_claims": 160, "bits": 0.002, "max_spend": 1.80},
}
EFFORT_NAMES = {v["name"]: k for k, v in EFFORT.items()}
DEFAULT_EFFORT = 3


def _effort_label(level: int) -> str:
    return f"{level} ({EFFORT[level]['name']})"


def resolve_effort(args) -> dict:
    """Fill in whatever the caller did not set. Explicit always wins."""
    level = EFFORT[args.effort]
    for key in ("sites", "iterations", "judge_cap", "max_claims",
                "max_spend"):
        if getattr(args, key, None) is None:
            setattr(args, key, level[key])
    if getattr(args, "min_bits", None) is None:
        args.min_bits = level["bits"]
    return level

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
        self.serp = S.Serp(cache_dir=SERP_CACHE, offline=args.offline)
        self.stages: list[judge.Stage] = []
        self.trail: list[insights.Thread] = []
        self.open: list[insights.Thread] = []
        self.chased: set[str] = set()
        self.dead_tags: set[str] = set()
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

    def sample(self, terms: list[str], limit: int = 25) -> str:
        """What a probe actually brought back, biggest searches first."""
        rows = [self.graph.keywords[t] for t in terms
                if t in self.graph.keywords]
        rows.sort(key=lambda k: -k.volume)
        if not rows:
            return "nothing: none of the searches tested have any volume"
        return "\n".join(f"{k.term} — {k.volume:,}/mo, ${k.cpc:.2f} a click"
                          for k in rows[:limit])

    def picture(self) -> str:
        """A compact rendering of what is known, for Jev to decide against.

        Kept small on purpose: accuracy falls as irrelevant state grows, so
        this is the headline shape of the market and nothing else.
        """
        rows = self.graph.topic_rows()[:8]
        if not rows:
            return "nothing measured yet"
        lines = []
        for r in rows:
            mix = ", ".join(f"{k} {int(v * 100)}%"
                            for k, v in list(r["job_mix"].items())[:3])
            lines.append(
                f"{r['topic']}: {r['volume']:,} searches/mo, "
                f"click price {r['click_price']:.2f}, "
                f"{int(r['branded_share'] * 100)}% name a brand; {mix}")
        return "\n".join(lines)

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
        outvoted, st = judge.outvoting(self.client, self.graph, admitted,
                                       self.args.asker)
        if st.questions:
            self.stage(st)
        gone += outvoted
        if gone:
            self.graph.drop(gone)
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

    def orient(self, iteration: int) -> None:
        self.say("  ORIENT   placing keywords on the two axes")
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
                          key=lambda k: -k.volume)[:self.args.judge_cap]
        if unjudged:
            self.stage(judge.assign(self.client, g, unjudged, self.args.asker))
        self.oriented_at = len(g.keywords)
        self.infer()
        covered = K.share(g.certain_volume, g.total_volume)
        self.say(f"      · {len(g.certain):,} of {len(g.judged):,} searches "
                 f"revealed what the person wanted, covering "
                 f"{covered * 100:.0f}% of measured searching")

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

    # -- DECIDE ----------------------------------------------------------

    def choose(self, offer) -> tuple[object, judge.Stage]:
        if not self.net or not offer:
            return None, judge.Stage("decide:unscoreable", 0, jev.Usage())
        targets = list(MN.DECISION)
        scored = []
        for thread in offer:
            tag = thread.key.rsplit("->", 1)[-1]
            node = MN.PROBE_INFORMS.get(tag)
            bits = (self.net.expected_gain(node, targets, self.evidence)
                    if node else 0.0)
            scored.append((bits, node, thread))
        # Expected bits *per call*, not bits. A question worth a lot that
        # usually returns nothing is worth less than a modest one that
        # always lands, and which is which is a measured fact about each
        # kind of follow-up rather than anything to judge:
        #
        #   diy, money, minority, growth   12 probes, 12 paid off
        #   movers                          8 probes,  1 paid off
        #   brands                          5 probes,  0 paid off
        #
        # Thirteen `brands` and `movers` probes cost $1.17 and produced one
        # result. The record is kept on disk and every run adds to it, so
        # the estimate sharpens with use.
        scored = [(bits * insights.hit_rate(
                       t.key.rsplit("->", 1)[-1]), bits, node, t)
                  for bits, node, t in scored]
        if not any(node for _, _, node, _ in scored):
            return None, judge.Stage("decide:unscoreable", 0, jev.Usage(),
                                     ["no open question maps to anything the "
                                      "network measures"])
        scored.sort(key=lambda x: -x[0])
        expected, bits, node, thread = scored[0]
        if expected < self.args.min_bits:
            # Deliberately not "unscoreable": the network could price this
            # and priced it at nearly nothing. Handing that to a model for a
            # second opinion is how the floor gets talked out of, and an
            # earlier version duly bought a probe worth 0.0002 bits.
            return None, judge.Stage(
                "decide:too-small", 0, jev.Usage(),
                [f"the best remaining question is worth {expected:.4f} "
                 f"expected bits, under the {self.args.min_bits} floor at "
                 f"effort {self.args.effort} — "
                 f"$0.09 for a rounding error"])
        tag = thread.key.rsplit("->", 1)[-1]
        return thread, judge.Stage(
            "decide:bits", 0, jev.Usage(),
            [f"worth {bits:.3f} bits about what the reader came for "
             f"(via {node}); this kind of question has paid off "
             f"{insights.hit_rate(tag):.0%} of the time, so "
             f"{expected:.3f} expected bits for the $0.09"])

    def find_claims(self) -> list[judge.Claim]:
        self.say("  DECIDE   testing every claim the data could support")
        candidates = insights.generate(self.graph)
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
        self.say(f"seed “{a.keyword}” · {a.location} · "
                 f"{a.iterations} probe(s) · ceiling ${a.max_spend:.2f}")
        self.say(f"asking on behalf of: {a.asker}")

        harvested = 0
        if not a.no_harvest:
            harvested = self.harvest(a.keyword)
        if not harvested:
            # Either nobody selling ranks here, or harvesting was
            # declined. Google's own idea list is the fallback, and
            # on a niche seed it returns very little, which is itself
            # worth reporting.
            self.say("  OBSERVE  falling back to Google's idea list")
        self.observe("expand", [a.keyword], f"what surrounds “{a.keyword}”")
        last_paid_off = True
        last_children: list[insights.Thread] = []

        for i in range(a.iterations):
            self.say(f"\niteration {i + 1}/{a.iterations}")
            self.orient(i)
            kept = self.find_claims()
            self.say(f"      · {len(kept)} finding(s) standing")

            children = insights.followups(self.graph, kept, depth=i)
            children = [t for t in children if t.key not in self.chased
                        and t.key.rsplit("->", 1)[-1] not in self.dead_tags]
            # Depth-first: when the last probe answered its question, its own
            # follow-ups go on the table first. When it did not, they are
            # never created — that is the backtrack.
            if last_paid_off:
                last_children = children
            self.open = self._merge(children)

            if i == a.iterations - 1 or not self.open:
                break

            offer = last_children or self.open
            offer = [t for t in offer if t.key not in self.chased] or self.open

            # Value of information, computed rather than guessed. Each open
            # question is scored by how many bits of uncertainty answering it
            # would remove from what the reader came to find out. Only when
            # nothing on the table would move the network at all does this
            # fall back to asking Jev to rate the options — the arithmetic is
            # exact where it applies, and it costs no request.
            thread, st = self.choose(offer)
            self.stage(st)
            if thread is None and st.name == "decide:unscoreable":
                thread, st = judge.decide(self.client, self.graph, offer,
                                          self.picture(), a.asker)
                self.stage(st)
            if thread is None:
                self.say("  STOP     nothing left worth buying — the "
                         "remaining budget goes unspent")
                break

            thread.status = "chasing"
            # `chased` was written, read in three places, and never added
            # to. Nothing else stops a thread being regenerated next
            # iteration, so a question that *paid off* came back and was
            # bought again: on `cad to bim tool` the same probe was bought
            # five times in a row, three of them byte-identical replays,
            # burning five of eight iterations on one question. Only a
            # dead end was ever remembered, through `dead_tags`.
            self.chased.add(thread.key)
            self.trail.append(thread)
            self.say(f"  ACT      {thread.question}")
            try:
                if thread.action == "harvest":
                    before = set(self.graph.keywords)
                    self.harvest(thread.payload[0])
                    fresh = [t for t in self.graph.keywords
                             if t not in before]
                else:
                    fresh = self.observe(thread.action, thread.payload,
                                         thread.question)
            except (seo.BudgetExceeded, seo.OfflineMiss) as exc:
                thread.status = "unfunded"
                thread.note = str(exc)
                self.say(f"  STOP     {exc}")
                break

            # What came back is the probe's own rows, not the market
            # summary. Handing it the global picture asked whether one
            # small measurement had visibly moved a whole market — which it
            # never has, so every probe read as a dead end.
            returned = self.sample(fresh)
            if not returned:
                # Nothing survived vetting, so there is nothing to judge.
                # Asking "did this bear on the question?" about an empty
                # sample is not a question, and it was answered `P=0.51`
                # — a coin flip promoted to "answered", which kept the
                # thread alive and bought it again.
                paid = False
                st = judge.Stage("assess", 0, jev.Usage(),
                                 ["nothing it brought back is in this "
                                  "market — no sample to judge"])
            else:
                paid, st = judge.assess_probe(self.client, self.graph,
                                              thread.question, returned,
                                              a.asker)
            self.stage(st)
            thread.status = "paid_off" if paid else "dead_end"
            insights.record_probe(thread.key.rsplit("->", 1)[-1], paid)
            last_paid_off = paid
            if not paid:
                # Undo the tangent, and drop every other thread that asks
                # the same kind of question. A person who finds that
                # expanding on one brand name teaches nothing does not then
                # try the next brand name.
                dropped = self.graph.drop(fresh)
                tag = thread.key.rsplit("->", 1)[-1]
                self.dead_tags.add(tag)
                killed = [t for t in self.open
                          if t.key.rsplit("->", 1)[-1] == tag]
                self.open = [t for t in self.open if t not in killed]
                thread.note = (f"discarded {dropped:,} keywords it brought "
                               f"in; dropped {len(killed)} other question(s) "
                               f"of the same kind")
                self.say(f"  BACK     dead end — discarded {dropped:,} rows "
                         f"and {len(killed)} sibling question(s)")
                last_children = []

        # Anything bought by the last probe still needs placing. When the
        # loop stopped without buying anything, re-running the whole orient
        # would re-ask questions already answered — the cache makes that
        # cheap but not free, and free is available.
        if len(self.graph.keywords) != self.oriented_at:
            self.orient(a.iterations)
            kept = self.find_claims()
        if not self.args.no_forecast:
            # Release the reserve now that the probes have had their turn.
            self.seo.max_spend_usd += self.reserve
            self.price_the_move()
        kept = [c for c in self.claims if c.survived()]
        self.say(f"\n{len(kept)} finding(s) survived · "
                 f"{self.seo.ledger.line()} · {self.jev_usage.line()}")

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

    def _merge(self, new: list[insights.Thread]) -> list[insights.Thread]:
        """The open threads: what is on the table and not yet paid for."""
        live = [t for t in self.open if t.key not in self.chased]
        seen = {t.key for t in live}
        return live + [t for t in new
                       if t.key not in seen and t.key not in self.chased]

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
    text = report_mod.render(run.graph, run.claims, run.trail, run.manifest())
    with open(out, "w", encoding="utf-8") as fh:
        fh.write(text)
    if args.json:
        with open(args.json, "w", encoding="utf-8") as fh:
            json.dump({"manifest": run.manifest(),
                       "graph": run.graph.to_dict(),
                       "claims": [asdict(c) for c in run.claims]}, fh, indent=2)
    print(f"\nwrote {out}")
    return 0


def plan(args) -> int:
    """What a run would cost, without spending anything."""
    # The harvest buys sites, the loop buys probes, and the forecast buys
    # the answer. An earlier plan counted only the probes and told the
    # caller half the truth.
    per_call = 0.09
    harvest = (0 if args.no_harvest else args.sites)
    worst = (harvest + args.iterations) * per_call
    print(json.dumps({
        "seed": args.keyword,
        "location": args.location,
        "effort": _effort_label(args.effort),
        "billable_dataforseo_calls_at_most": harvest + args.iterations
        + (0 if args.no_forecast else 1),
        "buys": (f"{harvest} site harvest(s), up to {args.iterations} "
                 f"probe(s), {args.judge_cap} searches read, and a probe is "
                 f"only bought if it is expected to be worth "
                 f"{args.min_bits} bits"),
        "dataforseo_ceiling_usd": round(
            min(worst + (0 if args.no_forecast else per_call),
                args.max_spend), 2),
        "jev_estimate_usd": round(0.01 * args.iterations, 3),
        "note": "DataForSEO bills per call regardless of how many keywords "
                "it carries; each price probe fills up to 1000 slots. "
                "Cached probes are free and do not count.",
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
                   help="how hard to look, 1 to 5 (or glance, quick, normal, "
                        "deep, exhaustive). One dial for probes, sites, how "
                        "much gets read and how small an answer is worth "
                        "buying. A ceiling, not a target: the loop still "
                        "stops when nothing left is worth the money")
    r.add_argument("--iterations", type=int, default=None,
                   help="override the probe ceiling for this effort level")
    r.add_argument("--min-bits", type=float, default=None,
                   help="override the floor: the smallest expected gain, in "
                        "bits, worth $0.09")
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
                   help="override how many searches get placed "
                        "on the two axes")
    r.add_argument("--max-claims", type=int, default=None)
    r.add_argument("--arm", choices=("jev", "code"), default="jev",
                   help="'jev' judges every claim; 'code' is the "
                        "hand-tuned-threshold control arm")
    r.add_argument("--out", help="report path (default insights-<seed>.md)")
    r.add_argument("--json", help="also dump graph, claims and ledger here")
    r.add_argument("--no-forecast", action="store_true",
                   help="skip the closing forecast call. It is the single "
                        "most useful $0.09 in the run, so skip it only when "
                        "the question is not about acquisition")
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
