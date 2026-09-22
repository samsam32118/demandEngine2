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
import report as report_mod
import seo

HERE = os.path.dirname(os.path.abspath(__file__))
SKILL = os.path.dirname(HERE)
SEO_CACHE = os.path.join(SKILL, ".cache", "dataforseo")
JEV_CACHE = os.path.join(SKILL, ".cache", "jev")

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

DEFAULT_ASKER = ("someone deciding whether and how to enter this market, "
                 "who has not worked in it before")


class Run:
    def __init__(self, args) -> None:
        self.args = args
        self.graph = K.Graph(args.keyword, args.location, args.language)
        self.seo = seo.Seo(cache_dir=SEO_CACHE, location=args.location,
                           language=args.language,
                           max_spend_usd=args.max_spend,
                           offline=args.offline)
        self.client = jev.Client(cache_dir=JEV_CACHE,
                                 use_cache=not args.no_jev_cache)
        self.stages: list[judge.Stage] = []
        self.trail: list[insights.Thread] = []
        self.open: list[insights.Thread] = []
        self.chased: set[str] = set()
        self.dead_tags: set[str] = set()
        self.claims: list[judge.Claim] = []
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
        return [t for t in self.graph.keywords if t not in before]

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
        covered = K.share(g.certain_volume, g.total_volume)
        self.say(f"      · {len(g.certain):,} of {len(g.judged):,} searches "
                 f"revealed what the person wanted, covering "
                 f"{covered * 100:.0f}% of measured searching")

    # -- DECIDE ----------------------------------------------------------

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
            thread, st = judge.decide(self.client, self.graph, offer,
                                      self.picture(), a.asker)
            self.stage(st)
            if thread is None:
                self.say("  STOP     nothing left worth buying — the "
                         "remaining budget goes unspent")
                break

            thread.status = "chasing"
            self.chased.add(thread.key)
            self.trail.append(thread)
            self.say(f"  ACT      {thread.question}")
            try:
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
            paid, st = judge.assess_probe(self.client, self.graph,
                                          thread.question, returned, a.asker)
            self.stage(st)
            thread.status = "paid_off" if paid else "dead_end"
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
        kept = [c for c in self.claims if c.survived()]
        self.say(f"\n{len(kept)} finding(s) survived · "
                 f"{self.seo.ledger.line()} · {self.jev_usage.line()}")

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
    per_call = 0.09
    worst = args.iterations * per_call
    print(json.dumps({
        "seed": args.keyword,
        "location": args.location,
        "billable_dataforseo_calls_at_most": args.iterations,
        "dataforseo_ceiling_usd": round(min(worst, args.max_spend), 2),
        "jev_estimate_usd": round(0.01 * args.iterations, 3),
        "note": "DataForSEO bills per call regardless of how many keywords "
                "it carries; each price probe fills up to 1000 slots. "
                "Cached probes are free and do not count.",
    }, indent=2))
    return 0


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
    r.add_argument("--iterations", type=int, default=DEFAULT_ITERATIONS,
                   help=f"billable probes to make (default {DEFAULT_ITERATIONS})")
    r.add_argument("--for", dest="asker", default=DEFAULT_ASKER,
                   help="who is asking — the value of a finding is relative "
                        "to them, so this changes what survives")
    r.add_argument("--location", default="United States")
    r.add_argument("--language", default="en")
    r.add_argument("--currency", default="$",
                   help="symbol for click prices. DataForSEO returns them "
                        "unlabelled and documents them as US dollars; set "
                        "this if your Google Ads account bills otherwise")
    r.add_argument("--max-spend", type=float, default=1.00,
                   help="hard ceiling in USD, checked before each call")
    r.add_argument("--judge-cap", type=int, default=DEFAULT_JUDGE_CAP)
    r.add_argument("--max-claims", type=int, default=90)
    r.add_argument("--arm", choices=("jev", "code"), default="jev",
                   help="'jev' judges every claim; 'code' is the "
                        "hand-tuned-threshold control arm")
    r.add_argument("--out", help="report path (default insights-<seed>.md)")
    r.add_argument("--json", help="also dump graph, claims and ledger here")
    r.add_argument("--dry-run", action="store_true")
    r.add_argument("--offline", action="store_true",
                   help="replay cached responses only; a miss is an error")
    r.add_argument("--no-jev-cache", action="store_true")
    r.add_argument("--quiet", action="store_true")
    r.set_defaults(func=cmd_run)

    args = p.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    _quiet_broken_pipe()
    raise SystemExit(main())
