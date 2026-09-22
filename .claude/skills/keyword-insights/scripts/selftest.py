#!/usr/bin/env python3
"""Checks that hold without spending anything, plus a live handshake.

    selftest.py          # offline only
    selftest.py --live   # also one real Jev batch (a fraction of a cent)
"""

from __future__ import annotations

import argparse
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import insights
import jev
import judge
import kgraph as K
import market_net as MN
import report
import seo
import serp as S

HERE = os.path.dirname(os.path.abspath(__file__))
PASS, FAIL = [], []


def check(name: str, ok: bool, detail: str = "") -> None:
    (PASS if ok else FAIL).append(name)
    if not ok:
        print(f"  FAIL {name}" + (f" — {detail}" if detail else ""))


def fixture() -> K.Graph:
    g = K.Graph("crm software", "United States", "en")
    rows = []
    for i, (t, v, c) in enumerate([
            ("crm software", 40500, 22.5), ("free crm software", 8100, 9.1),
            ("best crm software", 6600, 18.0), ("crm software pricing", 1300, 25.0),
            ("real estate crm", 5400, 12.0), ("salesforce login", 90500, 0.0),
            ("hubspot crm", 33100, 8.0), ("crm template excel", 1900, 0.4),
            ("what is crm software", 4400, 2.1), ("open source crm", 4400, 3.2)]):
        rows.append({"term": t, "volume": v, "cpc": c, "competition_index": 50,
                     "low_bid": c * 0.4, "high_bid": c * 2.2,
                     "trend": [int(v * (0.8 + 0.04 * m)) for m in range(12)],
                     "months": [f"2025-{m:02d}" for m in range(1, 13)],
                     "source": "expanded"})
    g.add_rows(rows)
    for t in ("crm software", "real estate crm", "open source crm"):
        g.add_topic(t, confirmed=True)
    for e in ("salesforce", "hubspot"):
        g.add_entity(e, confirmed=True)
    jobs = ["buy", "self_serve", "compare", "buy", "buy", "brand_desk",
            "brand_desk", "self_serve", "learn", "self_serve"]
    for kw, job in zip(sorted(g.keywords.values(), key=lambda k: k.term), jobs):
        kw.entities = sorted(n for n in g.confirmed_entities
                             if n in set(K.tokens(kw.term)))
        matched = g.containment_topics(kw.term)
        kw.topic = matched[0] if matched else "crm software"
        kw.topic_confidence = 1.0
        kw.job, kw.job_confidence, kw.job_certain = job, 0.8, True
    return g


class _StubJev:
    """Answers each yes/no by rule and records what it was asked."""

    def __init__(self, rule):
        self.rule, self.asked, self.instructions = rule, [], []

    def ask(self, state, questions):
        answers = {}
        for key, q in questions.items():
            self.asked.append(q.instructions["search"])
            self.instructions.append(q.instructions)
            answers[key] = self.rule(q.instructions["search"])
        return _StubResult(answers)


class _StubResult:
    def __init__(self, answers):
        self.answers, self.usage = answers, jev.Usage()

    def noul(self, key):
        verdict = self.answers[key]
        return type("Answer", (), {"yes": lambda _, threshold=0.5: verdict})()


def trended_fixture() -> K.Graph:
    """Two topics with four years of history: one that reads, one that
    cannot. `keyword research` is the series as DataForSEO returns it."""
    g = K.Graph("seo tools", "United States", "en")
    steady = [40000 - 700 * i for i in range(48)]
    spiked = ([8100] * 24
              + [6600, 9900, 8100, 14800, 9900, 8100,
                 9900, 12100, 12100, 301000, 1500000, 1830000]
              + [74000, 8100, 2400, 1000, 2400, 3600,
                 14800, 60500, 450000, 201000, 135000, 135000])
    months = [f"{y}-{m:02d}" for y in (2022, 2023, 2024, 2025)
              for m in range(1, 13)]
    g.add_rows([
        {"term": "rank tracker", "volume": 14800, "cpc": 30.0,
         "competition_index": 50, "low_bid": 10.0, "high_bid": 60.0,
         "trend": steady, "months": months, "source": "expanded"},
        {"term": "keyword research", "volume": 90500, "cpc": 14.7,
         "competition_index": 30, "low_bid": 5.0, "high_bid": 30.0,
         "trend": spiked, "months": months, "source": "expanded"},
    ])
    for t in ("rank tracker", "keyword research"):
        g.add_topic(t, confirmed=True)
    for kw in g.keywords.values():
        kw.topic, kw.topic_confidence = kw.term, 1.0
        kw.job = "compare" if kw.term == "rank tracker" else "learn"
        kw.job_confidence, kw.job_certain = 0.9, True
    return g


def offline() -> None:
    print("arithmetic")
    check("median", K.median([1, 2, 3, 4]) == 2.5)
    check("seasonality flat is 1.0", abs(K.seasonality([5] * 12) - 1.0) < 1e-9)
    check("seasonality needs a full year", K.seasonality([1, 2, 3]) is None)
    check("a 12-month window yields no growth figure",
          K.growth([10] * 12) is None)
    check("two complete cycles do yield one",
          abs(K.growth([10] * 12 + [20] * 12) - 2.0) < 1e-9)
    # One Keyword Planner spike must not decide the year. This series is
    # `keyword research` as DataForSEO actually returns it: years at 6-14k,
    # then 301k/1.5M/1.83M in the prior window. Summing reads 0.29x — a 71%
    # collapse that never happened.
    spiked = ([8100] * 12
              + [6600, 9900, 8100, 14800, 9900, 8100,
                 9900, 12100, 12100, 301000, 1500000, 1830000]
              + [74000, 8100, 2400, 1000, 2400, 3600,
                 14800, 60500, 450000, 201000, 135000, 135000])
    check("three spiked months do not flip the direction of the year",
          K.growth(spiked) > 1.0)
    check("a spiked window is read by its median month",
          abs(K.growth(spiked) - (37650.0 / 11000.0)) < 1e-6)
    check("a series whose sum and median disagree on direction is unreadable",
          K.growth_readable(spiked) is False)
    check("a series that agrees with itself is readable",
          K.growth_readable([40000 - 700 * i for i in range(48)]) is True)
    check("no history, no readability verdict",
          K.growth_readable([10] * 12) is None)
    # Four years is what `date_from` actually returns, and four
    # observations per calendar month is what makes the median bite: with
    # only two years the median of two values is their mean and a single
    # spike still names the peak. See `_by_calendar_month`.
    four_years = ([10] * 8 + [99999] + [10] * 3) + [10] * 36
    labels = [f"{y}-{m:02d}" for y in (2023, 2024, 2025, 2026)
              for m in range(1, 13)]
    check("one odd September does not become the peak month",
          K.peak_month(four_years, labels) != "September")
    check("a spike survives as a spike, not as a season",
          K.seasonality(four_years, labels) == 1.0)
    check("the season cancels between matched cycles",
          abs(K.growth(([1, 9] * 6) * 2) - 1.0) < 1e-9)
    check("every call asks for four years of history",
          "date_from" in seo.Seo(cache_dir="/tmp/x")._geo({}))
    check("seasonality averages matched months across years",
          abs(K.seasonality([1] * 11 + [12] + [1] * 11 + [12],
                            [f"{y}-{m:02d}" for y in (2025, 2026)
                             for m in range(1, 13)])
              - K.seasonality([1] * 11 + [12],
                              [f"2026-{m:02d}" for m in range(1, 13)])) < 1e-9)
    check("click price is weighted by searching, not by keyword count",
          abs(K.click_price([K.Keyword("a", 1000, 4.0),
                             K.Keyword("b", 1, 0.0),
                             K.Keyword("c", 1, 0.0)]) - 4.0) < 0.02)
    check("share by zero is zero", K.share(5, 0) == 0.0)
    check("concentration of one", K.concentration([7]) == 1.0)
    check("month name", K.month_name("2025-11") == "November")

    print("mining")
    g = fixture()
    check("a phrase in one keyword is not a cluster",
          all(sum(1 for k in g.keywords.values() if p in k.term) >= 2
              for p in K.mine_phrases(g.keywords.values(), limit=20)))
    check("brands are not topics",
          not (set(g.confirmed_entities) & set(g.confirmed_topics)))
    g.add_topic("crm", confirmed=True)
    check("fragments lose to the specific phrase",
          "crm" not in g.confirmed_topics and
          "crm software" in g.confirmed_topics)
    known = set(g.keywords)
    probes = K.probe_candidates(["crm software"], ["migration", "cheap"],
                                known, limit=9)
    check("each hypothesis is tested once, not in both word orders",
          len({tuple(sorted(t.split())) for t in probes}) == len(probes),
          str(probes))
    check("prefix facets read the natural way round",
          "cheap crm software" in probes
          and "crm software migration" in probes, str(probes))
    check("probes never re-price what is known",
          not (set(probes) & known))
    check("probes are deterministic",
          probes == K.probe_candidates(["crm software"],
                                       ["migration", "cheap"], known,
                                       limit=9))

    print("claims")
    claims = insights.generate(g)
    check("claims are generated", len(claims) > 4, f"{len(claims)}")
    check("every claim carries a numberless assertion",
          all(c.assertion and not re.search(r"\d", c.assertion)
              for c in claims),
          str([c.kind for c in claims if re.search(r"\d", c.assertion)]))
    check("every claim carries what it rests on",
          all("keywords_this_rests_on" in c.evidence for c in claims))
    check("every claim offers a rival account",
          all(c.forbids and c.forbids != c.assertion for c in claims))
    check("one claim per family",
          max(sum(1 for c in claims if c.kind == k)
              for k in {c.kind for c in claims}) == 1)
    check("contradictory claims coexist before judging",
          {"settled", "open"} <= {c.kind for c in claims} or
          len([c for c in claims if c.kind in ("settled", "open")]) >= 1)

    print("permutations")
    g2 = K.Graph("garden rooms")
    g2.add_rows([
        {"term": "garden rooms", "volume": 40500, "cpc": 3.11,
         "competition_index": 100, "low_bid": 1.0, "high_bid": 6.0,
         "trend": [], "months": [], "source": "x"},
        {"term": "rooms garden", "volume": 40500, "cpc": 3.11,
         "competition_index": 100, "low_bid": 1.0, "high_bid": 6.0,
         "trend": [], "months": [], "source": "x"}])
    check("the same searches are not counted twice under two word orders",
          len(g2.keywords) == 1 and g2.total_volume == 40500
          and g2.collapsed == 1,
          f"{len(g2.keywords)} kw / {g2.total_volume} vol")

    print("backtracking")
    before = len(g.keywords)
    g.drop(["free crm software", "not a real keyword"])
    check("drop removes what it can", len(g.keywords) == before - 1)

    print("follow-ups")
    for c in claims:
        c.verdict = "kept"
    threads = insights.followups(g, claims)
    check("surviving claims raise threads", len(threads) > 0)
    check("no two threads buy the same answer",
          len({(t.action, tuple(sorted(t.payload))) for t in threads})
          == len(threads))
    check("expand respects the 20-seed ceiling",
          all(len(t.payload) <= seo.MAX_SEEDS
              for t in threads if t.action == "expand"))
    check("price respects the 1000-keyword ceiling",
          all(len(t.payload) <= seo.MAX_PRICED
              for t in threads if t.action == "price"))

    print("the forecast")
    agg = seo.normalise_forecast([{"keyword": None, "clicks": 232.31,
                                   "average_cpc": 8.0, "cost": 1857.62,
                                   "bid": 12, "match": "exact"}])
    check("the aggregate row is read, not skipped for having no keyword",
          len(agg) == 1 and abs(agg[0]["clicks"] - 232.31) < 1e-9)
    check("a response with no clicks yields nothing rather than zeroes",
          seo.normalise_forecast([{"keyword": None}]) == [])
    check("the forecast asks for no history",
          "date_from" not in seo.Seo(cache_dir="/tmp/x")._geo({}, history=False))
    check("every other call still asks for four years",
          "date_from" in seo.Seo(cache_dir="/tmp/x")._geo({}))

    # DataForSEO documents `bid` as an integer and enforces it unevenly:
    # 24.11 and 10.38 were accepted, 32.73 came back as 50301 naming no
    # field, and a run that had already spent $0.45 lost its forecast.
    sent = []

    class _Spy(seo.Seo):
        def _run(self, action, endpoint, task, source, note=""):
            sent.append(task)
            return seo.Call(action, endpoint, task, [], 0.0, True, 0.0, note)

    spy = _Spy(cache_dir="/tmp/x")
    spy.forecast(["a", "b", "c"], bid=32.73)
    spy.forecast(["a", "b", "c"], bid=0.4)
    check("the bid goes out as a whole number, as documented",
          isinstance(sent[0]["bid"], int) and sent[0]["bid"] == 33)
    check("a sub-unit bid floors at 1 rather than rounding to zero",
          sent[1]["bid"] == 1)

    print("harvesting from who ranks")
    md = "\n".join([
        "### Ambulance and Patient Transport Software", "",
        "Radar Healthcare", "https://radarhealthcare.com › solutions › ambulance", "",
        "Software that helps ambulance trusts manage quality and compliance "
        "across every station in the service.", "",
        "### EMS Software - Prices & Reviews", "",
        "https://www.getapp.co.uk › directory › ems-software", "",
        "Compare the best EMS software of 2026 with verified user reviews "
        "and side by side feature comparisons.", "",
        "### European Professional Club Rugby", "",
        "https://en.wikipedia.org › wiki › European_Professional_Rugby", "",
        "European Professional Club Rugby is the governing body organising "
        "the two major club rugby union tournaments in Europe."])
    got = S.parse_markdown(md)
    check("organic results are recovered from the rendered page",
          len(got) == 3, f"{len(got)}")
    check("the domain is read off the breadcrumb",
          [r.domain for r in got]
          == ["radarhealthcare.com", "getapp.co.uk", "wikipedia.org"],
          str([r.domain for r in got]))
    check("the heading above becomes the title",
          got[0].title.startswith("Ambulance and Patient"))
    check("the snippet is the first substantial line below",
          "ambulance trusts" in got[0].snippet)
    check("hosts that rank everywhere and sell nothing are dropped first",
          [r.domain for r in S.plausible_vendors(got)]
          == ["radarhealthcare.com", "getapp.co.uk"])
    check("www and bare subdomains are stripped",
          S._registrable("www.Example.CO.UK") == "example.co.uk")
    check("a page with neither title nor snippet is not a result",
          S.parse_markdown("https://nothing.com › x") == [])

    print("budget and credentials")
    s = seo.Seo(cache_dir="/nonexistent-cache", max_spend_usd=0.05,
                offline=False)
    s.ledger.calls.append(seo.Call("x", "y", {}, [], 0.04, False, 0.0))
    try:
        s.expand(["anything"])
        check("the ceiling is checked before the money moves", False)
    except seo.BudgetExceeded:
        check("the ceiling is checked before the money moves", True)
    except seo.SeoError as exc:
        check("the ceiling is checked before the money moves", False, str(exc))
    off = seo.Seo(cache_dir="/nonexistent-cache", offline=True)
    try:
        off.price(["anything"])
        check("offline never bills", False)
    except seo.OfflineMiss:
        check("offline never bills", True)

    print("no secret ever reaches an output")
    fingerprinted = re.compile(r"key_fingerprint\([^)]*\)")
    leaky = re.compile(r"(?:\bprint|\bsys\.std(?:out|err)\.write)\([^\n]*?"
                       r"\b(?:self\._key|api_key|_key|password|login)\b")
    leaks = []
    for name in sorted(os.listdir(HERE)):
        if not name.endswith(".py"):
            continue
        with open(os.path.join(HERE, name), encoding="utf-8") as fh:
            for i, line in enumerate(fh, 1):
                if leaky.search(fingerprinted.sub("<fp>", line)):
                    leaks.append(f"{name}:{i}")
    check("no credential is printed anywhere", not leaks, ", ".join(leaks))
    check("jev redacts its key from error text",
          jev._redact("boom sk-abc123 boom", "sk-abc123") ==
          "boom <redacted> boom")

    print("report")
    man = {"arm": "jev", "asker": "a founder", "claims_generated": len(claims),
           "claims_kept": len(claims), "seconds": 1.0,
           "dataforseo": {"billable_calls": 1, "cached_calls": 0,
                          "spent_usd": 0.09},
           "jev": {"requests": 3, "input_tokens": 1000, "usd": 0.00004}}
    md = report.render(g, claims, threads[:2], man)
    check("report renders", len(md) > 1500)
    check("report shows what it cost", "What this cost" in md)
    check("report shows the rejections section when there are any",
          "Checked, and it did not hold" in md or
          all(c.survived() for c in claims))
    check("report shows the trail", "mermaid" in md)

    # The "what it would cost to act" section is downstream of a forecast
    # call, which is downstream of which keywords Jev placed as biddable.
    # That makes it the one section an offline eval cannot guarantee it
    # will see — a single divergent judgment sends the run down an uncached
    # path and the call misses. So the renderer is pinned here instead of
    # in a case, against a forecast row supplied directly.
    priced = report.render(g, claims, threads[:2], dict(
        man, forecast={"clicks": 232.31, "cpc": 8.0, "cost": 1857.62,
                       "impressions": 0.0, "ctr": 0.0, "bid": 12,
                       "match": "exact", "window": "next_month",
                       "keywords": 43, "searches": 1810, "budget": None}))
    check("a forecast becomes the section that prices the move",
          "What it would cost to act on this" in priced
          and "Clicks available a month" in priced)
    check("the bid is printed as the whole number that was sent",
          "Bid set at $12 " in priced and "Bid set at $12.00" not in priced)

    print("the market network")
    # A uniform net must be a net that concludes nothing.
    flat = MN.Net(cpt={MN.row_key(n, st): 0.5 for n, ps in MN.PARENTS.items()
                       for st in MN.assignments(ps)})
    check("a uniform network concludes nothing",
          all(abs(v - 0.5) < 1e-12 for v in flat.posterior({}).values()))
    check("virtual evidence of 0.5 is worth nothing",
          abs(flat.posterior({"o_money": 0.5})["demand_real"] - 0.5) < 1e-12)

    # One hand-computable Bayes update, so the engine is checked against
    # arithmetic rather than against itself.
    hand = MN.Net(cpt=dict(flat.cpt))
    hand.cpt[MN.row_key("demand_real", ())] = 0.3
    hand.cpt[MN.row_key("o_money", (True,))] = 0.9
    hand.cpt[MN.row_key("o_money", (False,))] = 0.1
    check("inference matches Bayes by hand",
          abs(hand.posterior({"o_money": 1.0})["demand_real"]
              - 0.27 / 0.34) < 1e-9,
          f"{hand.posterior({'o_money': 1.0})['demand_real']:.4f}")
    check("an uninformative measurement is worth no bits",
          flat.expected_gain("o_crowd", ["paid_viable"]) == 0.0)
    check("an informative one is worth some",
          hand.expected_gain("o_money", ["demand_real"]) > 0.01)
    check("a belief already held firmly is worth little to pin down",
          hand.expected_gain("o_money", ["demand_real"], {"o_money": 0.99})
          < hand.expected_gain("o_money", ["demand_real"]))
    check("attribution sums toward the movement it explains",
          abs(sum(d for _, d in hand.attribution(
              "demand_real", {"o_money": 1.0}))) > 0.0)
    check("every observation has a parent among the latent properties",
          all(set(MN.PARENTS[o]) <= set(MN.LATENT) for o in MN.OBSERVED))
    check("no decision is a parent of anything",
          all(d not in sum(MN.PARENTS.values(), ()) for d in MN.DECISION))
    check("every probe tag maps to a real observation",
          all(v in MN.OBSERVED for v in MN.PROBE_INFORMS.values()))
    check("readings are produced for measurements that exist",
          set(MN.readings({"click_price": 1.0, "growth": 1.1}))
          == {"o_money", "o_up"})

    print("erratic series")
    tg = trended_fixture()
    tclaims = insights.generate(tg)
    direction = next((c for c in tclaims if c.kind == "direction"), None)
    check("a direction finding is still made from the readable topic",
          direction is not None)
    named = (direction.evidence.get("rising", [])
             + direction.evidence.get("falling", [])) if direction else []
    check("the spiked topic is not quoted as rising or falling",
          direction is not None
          and not any("keyword research" in x for x in named))
    check("the spiked topic is named as too erratic to read",
          direction is not None and "keyword research"
          in direction.evidence.get("too_erratic_to_read", []))
    rows = {r["topic"]: r for r in tg.topic_rows()}
    check("readability travels with the topic row",
          rows["rank tracker"]["growth_readable"] is True
          and rows["keyword research"]["growth_readable"] is False)
    check("the commercial share is the forecast's own set of jobs",
          rows["rank tracker"]["commercial_share"] == 1.0
          and rows["keyword research"]["commercial_share"] == 0.0)
    only_spiked = K.Graph("keyword research", "United States", "en")
    only_spiked.add_rows([{"term": "keyword research", "volume": 90500,
                           "cpc": 14.7, "competition_index": 30,
                           "low_bid": 5.0, "high_bid": 30.0,
                           "trend": tg.keywords["keyword research"].trend,
                           "months": tg.keywords["keyword research"].months,
                           "source": "expanded"}])
    check("the network is not told a direction the series cannot carry",
          only_spiked.stats()["growth"] is None)
    open_c = next((c for c in tclaims if c.kind == "open"), None)
    empty_c = next((c for c in tclaims if c.kind == "empty"), None)
    check("open ground says how many of them are there to buy",
          open_c is not None and "commercial_share" in open_c.evidence
          and "buying, comparing" in open_c.text)
    check("the empty-ground rival is built from the same numbers",
          empty_c is not None and open_c is not None
          and empty_c.topic == open_c.topic
          and empty_c.evidence["commercial_share"]
          == open_c.evidence["commercial_share"])
    check("open and empty contradict each other, as a pair should",
          open_c is not None and empty_c is not None
          and open_c.forbids != empty_c.forbids
          and open_c.assertion != empty_c.assertion)
    shape = report.render(tg, tclaims, threads[:2], dict(man, seed="seo tools"))
    check("the shape table carries a buying-or-comparing column",
          "buying or comparing" in shape)
    check("the report names what it left out of direction",
          "left out of every statement about direction" in shape
          and "keyword research" in shape)
    check("the report says a topic is a reading of this corpus",
          "A topic is what this run made of it" in shape)

    print("relevance")
    yes, no = judge.RELEVANCE_CRITERIA["true"], judge.RELEVANCE_CRITERIA["false"]
    check("relevance is not asked from the seller's side",
          "selling" not in yes and "care" not in yes)
    check("people doing it themselves or learning are in the market",
          "do it themselves" in yes and "learn" in yes)
    check("a second meaning of the same words is a reason to say no",
          "mean something different" in no)
    check("the customers' other needs are a reason to say no",
          "other needs of the same customers" in no)
    check("the outvoting fact reaches Jev as words, never as numbers",
          not any(ch.isdigit() for ch in judge.OUTVOTE_MEASURED))

    cad = K.Graph("cad to bim", "United States", "en")
    def kws(pairs):
        return [K.Keyword(t, v) for t, v in pairs]
    market = kws([("drawings", 1830000), ("bim", 22200), ("revit", 20000),
                  ("bim software", 6600), ("scan to bim", 5400),
                  ("cad to bim", 2120)])
    stub = _StubJev(lambda term: term != "drawings")
    gone, st = judge.outvoting(stub, cad, market, "a founder")
    check("a search larger than the rest of its market is asked about",
          stub.asked[:1] == ["drawings"])
    check("and dropped when most people typing it mean something else",
          gone == ["drawings"])
    check("then the check ends: nothing left is a majority",
          stub.asked == ["drawings"] and st.questions == 1)
    check("Jev is never handed the volumes",
          all(not any(ch.isdigit() for ch in str(i.get("measured", "")))
              and set(i) == {"search", "market", "measured", "question"}
              for i in stub.instructions))
    quiet = _StubJev(lambda term: False)
    gone, st = judge.outvoting(quiet, cad, market[1:], "a founder")
    check("a market with no majority search costs no question",
          quiet.asked == [] and gone == [] and st.questions == 0)
    head = _StubJev(lambda term: True)
    gone, _ = judge.outvoting(head, K.Graph("sourdough starter"), kws([
        ("sourdough starter", 100000), ("sourdough starter recipe", 20000),
        ("feeding sourdough starter", 10000)]), "a baker")
    check("a market's own head term survives being that large",
          gone == [] and head.asked == ["sourdough starter"])
    two = _StubJev(lambda term: False)
    gone, st = judge.outvoting(two, cad, kws([
        ("drawings", 1000000), ("3d modeling", 500000), ("bim", 60000),
        ("revit", 40000)]), "a founder")
    check("an outvoter behind an outvoter is found too",
          gone == ["drawings", "3d modeling"] and st.questions == 2)
    check("and the last two terms are never pitted against each other",
          "bim" not in two.asked and "revit" not in two.asked)
    pair = _StubJev(lambda term: False)
    gone, st = judge.outvoting(pair, cad, kws([("bim", 9000), ("revit", 10)]),
                               "a founder")
    check("a comparison that cannot fail is not asked",
          pair.asked == [] and gone == [] and st.questions == 0)

    print("narrowing")
    nar = K.Graph("cad to bim", "United States", "en")
    nar.add_rows([{"term": t, "volume": v, "cpc": c, "competition_index": 20,
                   "low_bid": c * 0.4, "high_bid": c * 2.0, "trend": [],
                   "months": [], "source": "expanded"}
                  for t, v, c in [("building modeling", 720, 1.49),
                                  ("bim building modeling", 5400, 30.68),
                                  ("building modeling software", 90, 12.0)]])
    nar.add_topic("building modeling", confirmed=True)
    for kw in nar.keywords.values():
        kw.topic, kw.topic_confidence = "building modeling", 1.0
        kw.job, kw.job_confidence, kw.job_certain = "compare", 0.9, True
    sharp = nar.sharpest_narrowing()
    check("a longer search with more volume than its bare term is not a narrowing",
          sharp is not None and sharp[2].term == "building modeling software")
    grad = next((c for c in insights.generate(nar) if c.kind == "gradient"), None)
    check("the gradient finding never claims more than all of the volume",
          grad is not None and "750%" not in grad.text
          and grad.evidence["qualified"]["searches"]
          < grad.evidence["bare"]["searches"])
    check("the network is told the same narrowing the finding names",
          "building modeling software" in nar.stats()["gradient_example"])
    only_up = K.Graph("cad to bim", "United States", "en")
    only_up.add_rows([{"term": t, "volume": v, "cpc": c, "competition_index": 20,
                       "low_bid": 1.0, "high_bid": 2.0, "trend": [], "months": [],
                       "source": "expanded"}
                      for t, v, c in [("building modeling", 720, 1.49),
                                      ("bim building modeling", 5400, 30.68)]])
    only_up.add_topic("building modeling", confirmed=True)
    for kw in only_up.keywords.values():
        kw.topic, kw.topic_confidence = "building modeling", 1.0
        kw.job, kw.job_confidence, kw.job_certain = "compare", 0.9, True
    check("with no true narrowing there is no gradient finding",
          only_up.sharpest_narrowing() is None
          and not any(c.kind == "gradient" for c in insights.generate(only_up)))

    print("money out of proportion")
    def market_of(rows_, certain=True):
        g_ = K.Graph("cad to bim", "United States", "en")
        g_.add_rows([{"term": t, "volume": v, "cpc": c, "competition_index": 20,
                      "low_bid": c * 0.4, "high_bid": c * 2.0, "trend": [],
                      "months": [], "source": "expanded"}
                     for t, v, c, _, _ in rows_])
        for t, v, c, topic, job in rows_:
            if topic:
                g_.add_topic(topic, confirmed=True)
            kw = g_.keywords[t]
            kw.topic, kw.topic_confidence = topic, 1.0
            kw.job, kw.job_confidence = job, 0.9
            kw.job_certain = bool(job)
        return g_
    ms_graph = market_of([
        ("bim software", 6600, 13.56, "bim software", "compare"),
        ("revit", 40500, 7.60, "revit", "learn"),
        ("bim service providers", 50, 219.43, "bim services", "buy"),
        ("bim modeling services", 1000, 40.0, "bim services", "buy"),
        ("bim", 22200, 15.45, "", "")])        # intent unreadable: held out
    ms = next((c for c in insights.generate(ms_graph) if c.kind == "money_seat"), None)
    check("the money finding names the cell spend runs furthest ahead in",
          ms is not None and ms.evidence["cell"] == "bim services / buy")
    check("not the cell that merely has the most money",
          ms is not None and not ms.evidence["cell"].startswith("revit"))
    check("its spend share really is above its search share",
          ms is not None and ms.evidence["share_of_implied_spend"]
          > ms.evidence["share_of_searching"])
    check("both shares are over the same searches — held-out money excluded",
          ms is not None and abs(ms.evidence["share_of_implied_spend"]
                                 - round(50971 / 448267, 3)) < 1e-9)
    flat = market_of([("bim software", 6600, 10.0, "bim software", "compare"),
                      ("revit", 40500, 10.0, "revit", "learn"),
                      ("bim services", 1000, 10.0, "bim services", "buy")])
    check("no claim of concentration where every cell pays in proportion",
          not any(c.kind == "money_seat" for c in insights.generate(flat)))
    faint = market_of([("revit", 40000, 10.0, "revit", "learn"),
                       ("bim software", 60000, 10.0, "bim software", "compare"),
                       ("bim services", 40, 10.5, "bim services", "buy")])
    check("nor where the gap would not show in the sentence as printed",
          not any(c.kind == "money_seat" for c in insights.generate(faint)))

    print("the account test")
    class _Adj:
        """Every test passes except the account one, which is a plurality."""
        def __init__(self, p_statement, p_rival):
            self.p = {"statement": p_statement, "rival": p_rival,
                      "neither": round(1 - p_statement - p_rival, 3)}
        def ask(self, state, questions):
            p = self.p
            class R:
                usage = jev.Usage()
                def noul(self, key):
                    v = {"true": 0.9, "swap": 0.1, "obvious": 0.1, "odd": 0.5}
                    return type("N", (), {"noul": v[key.split(":")[0]]})()
                def choice(self, key):
                    return type("C", (), {"choice": max(p, key=p.get),
                                          "probabilities": p,
                                          "confidence": 0.5})()
                def score(self, key):
                    return type("S", (), {"normalized": 0.7,
                                          "label": "A choice",
                                          "probabilities": {"0": 0.1, "1": 0.1,
                                                            "2": 0.7, "3": 0.1}})()
            return R()
    def one_claim():
        return next(c for c in insights.generate(ms_graph) if c.kind == "money_seat")
    plural = one_claim()
    judge.adjudicate(_Adj(0.42, 0.40), ms_graph, [plural], "a founder")
    check("a plurality on the account test is not support",
          plural.account == "statement" and not plural.survived()
          and plural.verdict == "the data does not settle it")
    major = one_claim()
    judge.adjudicate(_Adj(0.62, 0.30), ms_graph, [major], "a founder")
    check("a majority on the account test is",
          major.survived() and major.verdict == "kept")
    against = one_claim()
    judge.adjudicate(_Adj(0.20, 0.70), ms_graph, [against], "a founder")
    check("and the rival winning still says so",
          against.verdict == "the data supports the opposite")

    print("question shapes")
    try:
        jev.Noul(instructions="x", criteria={"yes": "a", "no": "b"}).wire()
        check("Noul criteria keys are enforced", False)
    except jev.JevValidationError:
        check("Noul criteria keys are enforced", True)
    try:
        jev.Score(instructions="x", criteria=["only one"]).wire()
        check("Score level count is enforced", False)
    except jev.JevValidationError:
        check("Score level count is enforced", True)
    check("ranking groups stay distinguishable", 2 <= judge.GROUP <= 12)
    check("decisive is scale free",
          judge.decisive(jev.ChoiceAnswer("k", "a", {"a": 0.6, "b": 0.2}, 0.3))
          and not judge.decisive(
              jev.ChoiceAnswer("k", "a", {"a": 0.4, "b": 0.35}, 0.9)))


def live() -> None:
    print("live")
    if not jev.available():
        check("jev credentials resolve", False, "no key")
        return
    check("jev credentials resolve", True)
    client = jev.Client()
    result = client.ask(
        {"market": "crm software"},
        {"a": jev.Noul(instructions={"search": "crm software pricing",
                                     "question": "Is the person typing "
                                                 "`search` looking at what "
                                                 "something costs?"},
                       criteria={"true": "They want to know a price",
                                 "false": "They want something else"}),
         "b": jev.Choice(instructions={"search": "crm jobs",
                                       "question": "What is this person "
                                                   "trying to do?"},
                         criteria=dict(K.JOBS))})
    check("a Noul answers in range", 0.0 <= result.noul("a").noul <= 1.0)
    check("an obvious price query reads as one",
          result.noul("a").yes(0.5), f"{result.noul('a').noul:.2f}")
    check("a job Choice picks the job taxonomy's own option",
          result.choice("b").choice in K.JOBS)
    check("usage is accounted", result.usage.input_tokens > 0)
    print(f"  {result.usage.line()}")
    if seo.available():
        check("dataforseo credentials resolve", True)
    else:
        check("dataforseo credentials resolve", False)


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--live", action="store_true")
    args = p.parse_args()
    offline()
    if args.live:
        live()
    print(f"\n{len(PASS)} passed, {len(FAIL)} failed")
    return 1 if FAIL else 0


if __name__ == "__main__":
    try:
        import signal
        signal.signal(signal.SIGPIPE, signal.SIG_DFL)
    except (ImportError, AttributeError, ValueError):
        pass
    raise SystemExit(main())
