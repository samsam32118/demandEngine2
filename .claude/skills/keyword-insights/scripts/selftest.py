#!/usr/bin/env python3
"""Checks that hold without spending anything, plus a live handshake.

    selftest.py          # offline only
    selftest.py --live   # also one real Jev batch (a fraction of a cent)
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import re
import sys
import tempfile

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
    check("the least-branded topic is read one way, open or empty",
          len({"open", "empty"} & {c.kind for c in claims}) == 1)

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
    page_rows = [
        {"type": "ai_overview", "domain": "", "title": "", "url": "",
         "description": ""},
        {"type": "paid", "domain": "www.bimcorp.com", "title": "BIM",
         "url": "https://www.bimcorp.com", "description": ""},
        {"type": "organic", "domain": "www.radarhealthcare.com",
         "title": "Ambulance and Patient Safety Software",
         "url": "https://www.radarhealthcare.com/ambulance",
         "description": "Trusted by ambulance trusts across the UK"},
        {"type": "people_also_ask", "domain": "", "title": "", "url": "",
         "description": ""},
        {"type": "organic", "domain": "www.getapp.co.uk",
         "title": "EMS Software - Prices & Reviews",
         "url": "https://www.getapp.co.uk/directory/ems-software",
         "description": "Compare the best EMS software"},
        {"type": "organic", "domain": "en.wikipedia.org",
         "title": "European Professional Club Rugby", "url": "",
         "description": "The governing body"}]
    got = S.organic(page_rows)
    check("organic results are read from DataForSEO's typed page",
          [r.domain for r in got]
          == ["radarhealthcare.com", "getapp.co.uk", "wikipedia.org"],
          str([r.domain for r in got]))
    check("ranks count organic results only, from one",
          [r.rank for r in got] == [1, 2, 3])
    check("the title and snippet come with each result",
          got[0].title.startswith("Ambulance and Patient")
          and "ambulance trusts" in got[0].snippet)
    feats = S.features(page_rows)
    check("the page's ads, AI overview and question box are counted",
          feats["ads"] == 1 and feats["ai_overview"] and feats["questions"]
          and feats["advertisers"] == ["bimcorp.com"])
    check("hosts that rank everywhere and sell nothing are dropped first",
          [r.domain for r in S.plausible_vendors(got)]
          == ["radarhealthcare.com", "getapp.co.uk"])
    check("www and bare subdomains are stripped",
          S._registrable("www.Example.CO.UK") == "example.co.uk")
    check("the SERP runs on DataForSEO, not a third vendor",
          "brightdata" not in open(os.path.join(HERE, "serp.py")).read().lower()
          .replace("bright data scrape", ""))

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
    check("report renders", md.startswith("# Insights") and "The data" in md)
    check("report shows what it cost",
          "Cost: $0.09 of search data" in md)
    check("report points to the statements that did not hold",
          all(c.survived() for c in claims) or "tested.csv" in md)
    check("the report is insights and data, not method",
          "What this means" not in md and "mermaid" not in md
          and "How to read this" not in md)

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
    check("a forecast becomes the line that says what paid search can buy",
          "All of paid search here: **$1,858 a month**" in priced
          and "232 clicks at $8.00" in priced)
    budgeted = report.render(g, claims, threads[:2], dict(
        man, forecast={"clicks": 232.31, "cpc": 8.0, "cost": 1857.62,
                       "bid": 12, "keywords": 43, "budget": 10000}))
    check("a budget is set against what the market can absorb",
          "Your $10,000 is 5.4x what that can absorb" in budgeted)
    with tempfile.TemporaryDirectory() as tmp:
        report.write_data(tmp, g, claims, threads[:2], dict(
            man, forecast={"clicks": 232.31, "cpc": 8.0, "cost": 1857.62,
                           "bid": 12, "keywords": 43}))
        fc = json.load(open(os.path.join(tmp, "forecast.json")))
    check("the bid kept with the forecast is the whole number that was sent",
          fc["bid"] == 12 and isinstance(fc["bid"], int))

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
    said = open_c or empty_c
    check("unbranded ground says how many of them are there to buy",
          said is not None and "commercial_share" in said.evidence
          and ("buying, comparing" in said.text
               or "buying or comparing" in said.text))
    check("code, not the account test, decides open or empty — the topic's "
          "buying share against the market's",
          (open_c is None) != (empty_c is None) and said is not None
          and ((open_c is not None) == (
              said.evidence["commercial_share"] > 0
              and round(100 * said.evidence["commercial_share"])
              >= round(100 * said.evidence["market_commercial_share"]))))
    check("and its rival is the mirror reading",
          said is not None and (
              ("no one there to sell to" in said.forbids) if open_c else
              ("open ground" in said.forbids)))
    shape = report.render(tg, tclaims, threads[:2], dict(man, seed="seo tools"))
    with tempfile.TemporaryDirectory() as tmp:
        report.write_data(tmp, tg, tclaims, threads[:2], man)
        topics_head = next(csv.reader(open(os.path.join(tmp, "topics.csv"))))
    check("the topics file carries a buying-or-comparing column",
          "buying_or_comparing" in topics_head
          and "year_on_year_readable" in topics_head)
    check("the report names what it left out of direction",
          "left out of every statement about direction" in shape
          and "keyword research" in shape)
    check("the report says a topic is a reading of this corpus",
          "a reading of this run's searches" in shape)

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
                                  ("building modeling software", 90, 12.0),
                                  ("revit tutorial", 30, 1.0),
                                  ("ifc viewer", 40, 1.0),
                                  ("bim level 2", 50, 1.0)]])
    nar.add_topic("building modeling", confirmed=True)
    for kw in nar.keywords.values():
        kw.topic, kw.topic_confidence = "building modeling", 1.0
        kw.job, kw.job_confidence, kw.job_certain = "compare", 0.9, True
    for t in ("revit tutorial", "ifc viewer", "bim level 2"):
        nar.keywords[t].topic = "other"
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
    rare = K.Graph("cad to bim", "United States", "en")
    rare.add_rows([{"term": t, "volume": v, "cpc": c, "competition_index": 20,
                    "low_bid": 1.0, "high_bid": 2.0, "trend": [], "months": [],
                    "source": "expanded"}
                   for t, v, c in [("bim software", 6600, 13.56),
                                   ("bim drawing software", 10, 50.21),
                                   ("bim software price", 480, 20.0),
                                   ("revit", 9900, 5.0), ("ifc viewer", 20, 1),
                                   ("bim level 2", 30, 1), ("lod 300", 40, 1),
                                   ("bim execution plan", 50, 1)]])
    rare.add_topic("bim software", confirmed=True)
    for kw in rare.keywords.values():
        kw.topic, kw.topic_confidence = "bim software", 1.0
        kw.job, kw.job_confidence, kw.job_certain = "compare", 0.9, True
    for t in ("revit", "ifc viewer", "bim level 2", "lod 300",
              "bim execution plan"):
        rare.keywords[t].topic = "other"
    sharp = rare.sharpest_narrowing()
    check("a narrowing searched less than the typical search is a curiosity, "
          "not a second kind of buyer",
          sharp is not None and sharp[2].term == "bim software price")

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
                                          "legend": {"0": "Nothing",
                                                     "1": "Colour",
                                                     "2": "A choice",
                                                     "3": "A reversal"},
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
    tie = one_claim()
    judge.adjudicate(_Adj(0.50, 0.30), ms_graph, [tie], "a founder")
    check("half is not a majority",
          tie.verdict == "the data does not settle it")
    against = one_claim()
    judge.adjudicate(_Adj(0.20, 0.70), ms_graph, [against], "a founder")
    check("and the rival winning still says so",
          against.verdict == "the data supports the opposite")

    print("offerings")
    up = [100 + 5 * i for i in range(48)]
    down = [400 - 5 * i for i in range(48)]
    months48 = [f"{y}-{m:02d}" for y in (2022, 2023, 2024, 2025)
                for m in range(1, 13)]

    def offering_market(rows_):
        g_ = K.Graph("cad to bim", "United States", "en")
        g_.add_rows([{"term": t, "volume": v, "cpc": c, "competition_index": 20,
                      "low_bid": c * 0.4, "high_bid": c * 2.0,
                      "trend": list(tr) if tr else [], "months":
                      months48 if tr else [], "source": src}
                     for t, v, c, _, _, _, tr, src in rows_])
        for t, v, c, offering, job, ents, _, _ in rows_:
            kw = g_.keywords[t]
            kw.topic, kw.topic_confidence = "", 0.0
            kw.job, kw.job_confidence, kw.job_certain = job, 0.9, True
            kw.offering, kw.offering_confidence = offering, 0.9
            kw.offering_certain = bool(offering)
            kw.entities = list(ents)
        return g_

    cad = offering_market([
        ("what is bim", 20000, 2.0, "information", "learn", [], up, "expanded"),
        ("bim meaning", 10000, 1.0, "information", "learn", [], up, "expanded"),
        ("bim guide", 5000, 3.0, "information", "learn", [], up, "site:a.com"),
        ("bim software", 6000, 10.0, "software", "compare", [], up, "site:a.com"),
        ("revit pricing", 2000, 8.0, "software", "buy", ["revit"], up,
         "site:a.com"),
        ("autodesk bim software price", 1000, 9.0, "software", "buy",
         ["autodesk"], up, "site:a.com"),
        ("bim modeling services", 400, 70.0, "service", "buy", [], down,
         "site:a.com"),
        ("revit outsourcing", 100, 170.0, "service", "buy", [], down,
         "site:a.com"),
        ("a mystery search", 900, 5.0, "", "learn", [], up, "expanded"),
    ])
    rows_by = {r["offering"]: r for r in cad.offering_rows()}
    check("a search whose offering did not read is left out of the offerings",
          sum(r["keywords"] for r in rows_by.values()) == 8)
    check("shares of searching and of spend are over the same searches",
          abs(sum(r["search_share"] for r in rows_by.values()) - 1) < 1e-3
          and abs(sum(r["spend_share"] for r in rows_by.values()) - 1) < 1e-3)
    check("an offering's click price is weighted by its searching",
          abs(rows_by["service"]["click_price"] - 90.0) < 1e-6)
    check("buying share is taken over the searches whose intent read",
          rows_by["service"]["commercial_share"] == 1.0
          and rows_by["information"]["commercial_share"] == 0.0)
    check("open ground is measured among the people shopping",
          rows_by["software"]["buyers_naming_a_company"] == round(3000 / 9000, 3)
          and rows_by["service"]["buyers_naming_a_company"] == 0.0)

    cad_claims = {c.kind: c for c in insights.generate(cad)}
    om = cad_claims.get("offer_money")
    check("the money contrast names the dearest offering against the crowd",
          om is not None and om.headline == "The money is in services, "
                                            "not information")
    check("the table under a contrast prints the shares the sentence prints",
          om is not None and all(
              f"{pct_ * 100:.0f}%" in om.text or name_ not in ("information",
                                                             "service")
              for name_, pct_ in ((r["offering"], r["share_of_searching"])
                                  for r in om.evidence["every_offering"])))
    check("and its premise holds as printed",
          om is not None and om.evidence["click_price_ratio"] > 1
          and "more of the searching is for information" in om.assertion)
    og = cad_claims.get("offer_growth")
    check("the growth contrast pairs a rising offering with a falling one",
          og is not None and og.evidence["falling"] == "service"
          and og.evidence["growing_at"] >= 1.0 > og.evidence["falling_at"])
    oo = cad_claims.get("offer_open")
    check("open ground is where shoppers name no company, against the "
          "largest shopping crowd",
          oo is not None and oo.headline == "The open ground is in services, "
                                            "not software")
    big_and_dear = offering_market([
        ("bim modeling services", 20000, 90.0, "service", "buy", [], up, "site:a"),
        ("bim outsourcing", 10000, 80.0, "service", "buy", [], up, "site:a"),
        ("what is bim", 5000, 2.0, "information", "learn", [], up, "site:a"),
        ("bim meaning", 5000, 1.0, "information", "learn", [], up, "site:a")])
    check("no money contrast when the dearest offering is also the biggest",
          not any(c.kind == "offer_money"
                  for c in insights.generate(big_and_dear)))
    single = offering_market([
        ("bim modeling services", 400, 70.0, "service", "buy", [], up, "site:a"),
        ("what is bim", 5000, 2.0, "information", "learn", [], up, "site:a"),
        ("bim meaning", 5000, 1.0, "information", "learn", [], up, "site:a")])
    check("one search is not a group: no contrast rests on it",
          not any(c.kind == "offer_money" for c in insights.generate(single)))
    all_up = offering_market([
        ("bim software", 6000, 10.0, "software", "compare", [], up, "site:a"),
        ("revit pricing", 2000, 8.0, "software", "buy", [], up, "site:a"),
        ("bim modeling services", 400, 70.0, "service", "buy", [], up, "site:a"),
        ("revit outsourcing", 100, 170.0, "service", "buy", [], up, "site:a")])
    check("no growth contrast when nothing is falling",
          not any(c.kind == "offer_growth" for c in insights.generate(all_up)))

    print("headlines")
    check("a headline is the point before the numbers",
          insights._headline("The money is concentrated: people are 5% of "
                             "the searching") == "The money is concentrated")
    check("with the bracketed figures taken out",
          insights._headline("Most of this market is people trying to "
                             "understand it (89% of 256,840 searches), ahead "
                             "of shopping for it (5%) — but x")
          == "Most of this market is people trying to understand it, ahead "
             "of shopping for it")
    check("and a price is not mistaken for a full stop",
          insights._headline("It costs $1.49 a click. Then more")
          == "It costs $1.49 a click")

    print("the offering is asked")
    class _AssignJev:
        """Answers topic, job and offering Choices by rule."""
        def __init__(self, offers_):
            self.offers = offers_
        def ask(self, state, questions):
            offers_ = self.offers
            class R:
                usage = jev.Usage()
                def choice(self, key):
                    kind_, i = key.split(":")
                    if kind_ == "offer":
                        pick = offers_[int(i)]
                        probs = {pick: 0.9, judge.NONE: 0.1}
                    elif kind_ == "job":
                        pick, probs = "learn", {"learn": 0.9, "buy": 0.1}
                    else:
                        pick, probs = judge.NONE, {judge.NONE: 1.0}
                    return type("C", (), {"choice": pick, "probabilities": probs,
                                          "confidence": 0.9})()
            return R()
    probe_kws = [K.Keyword("bim modeling services", 390, 71.0),
                 K.Keyword("revit login", 900, 1.0)]
    judge.assign(_AssignJev(["service", judge.NONE]), cad, probe_kws, "a founder")
    check("assign reads the offering beside the topic and the job",
          probe_kws[0].offering == "service" and probe_kws[0].offering_certain)
    check("none of these is kept as no offering, not forced into one",
          probe_kws[1].offering == "" and not probe_kws[1].offering_certain)

    print("invented giants")
    giant_market = [
        K.Keyword("how to drawings", 301000, 3.19, source="priced"),
        K.Keyword("bim", 22200, 15.0, source="site:marsbim.com"),
        K.Keyword("revit", 40500, 7.6, source="site:tejjy.com"),
        K.Keyword("bim software", 6600, 13.0, source="expanded")]
    gstub = _StubJev(lambda term: False)
    gone, st = judge.invented_giants(gstub, cad, giant_market, "a founder")
    check("an invented search larger than anything harvested is asked about",
          gstub.asked == ["how to drawings"] and gone == ["how to drawings"])
    check("and the fact reaches Jev as words, never as numbers",
          not any(ch.isdigit() for ch in judge.INVENTED_MEASURED))
    hstub = _StubJev(lambda term: False)
    judge.invented_giants(hstub, cad, [k for k in giant_market
                                       if k.source.startswith("site:")],
                          "a founder")
    check("a harvested search is never asked by this rule", hstub.asked == [])
    nstub = _StubJev(lambda term: False)
    gone, st = judge.invented_giants(nstub, cad, [
        K.Keyword("sourdough starter", 301000, 1.0, source="expanded"),
        K.Keyword("sourdough recipe", 90000, 1.0, source="expanded")],
        "a baker")
    check("with nothing harvested there is nothing to compare against",
          nstub.asked == [] and gone == [] and st.questions == 0)
    kstub = _StubJev(lambda term: True)
    gone, _ = judge.invented_giants(kstub, cad, [
        K.Keyword("sourdough starter", 301000, 1.0, source="expanded"),
        K.Keyword("sourdough starter kit", 9000, 20.0, source="site:a.com")],
        "a baker")
    check("the market's own name survives being that large",
          kstub.asked == ["sourdough starter"] and gone == [])

    print("the ranked report")
    ranked_claims = [c for c in insights.generate(cad)
                     if c.kind in ("offer_money", "offer_growth", "offer_open")]
    for c, w in zip(ranked_claims, (0.2, 0.7, 0.1)):
        c.verdict, c.weight, c.stakes_label = "kept", w, "A choice"
    failed = judge.Claim(key="x|y", text="Something that did not hold.",
                         assertion="a", forbids="b", evidence={}, examples=[],
                         kind="thin", verdict="misread")
    ranked_md = report.render(cad, ranked_claims + [failed], [], man,
                              "/tmp/x/cad-to-bim-data")
    heads = [line for line in ranked_md.splitlines() if line.startswith("## ")]
    by_weight = sorted(ranked_claims, key=lambda c: -c.weight)
    check("insights are ranked by their value weight, best first",
          heads == [f"## {i}. {c.headline}" for i, c in
                    enumerate(by_weight, 1)])
    check("a statement that failed is not in the report",
          "Something that did not hold" not in ranked_md
          and "1 other statement the data could support was tested" in ranked_md)
    check("each offering insight shows only its own columns",
          "| wants | searches/mo | year on year |" in ranked_md
          and "| wants | shopping searches/mo | of them naming a company |"
          in ranked_md)
    check("the data folder is named by where it sits",
          "`cad-to-bim-data/tested.csv`" in ranked_md)
    quiet_md = report.render(cad, [failed], [], man, "d")
    check("with nothing kept the report says so and stops",
          "## No insights" in quiet_md and "## 1." not in quiet_md
          and "None of the 1 statement this data could support" in quiet_md)
    empty_md = report.render(K.Graph("nothing here"), [], [], man, "d")
    check("and says so when there was nothing to test at all",
          "There was nothing to test" in empty_md)

    print("the data files")
    cad.keywords["bim modeling services"].term  # noqa: B018
    comma = K.Keyword('bim "services", nyc', 10, 5.0, trend=[1, 2],
                      months=["2025-01", "2025-02"], source="site:a.com")
    cad.keywords[comma.term] = comma
    with tempfile.TemporaryDirectory() as tmp:
        files = report.write_data(tmp, cad, ranked_claims + [failed],
                                  threads[:2], dict(man, forecast={"bid": 12}))
        names = sorted(os.path.basename(f) for f in files)
        kw_rows = list(csv.DictReader(open(os.path.join(tmp, "keywords.csv"))))
        tested = list(csv.DictReader(open(os.path.join(tmp, "tested.csv"))))
        series_rows = list(csv.reader(open(os.path.join(tmp, "series.csv"))))
        trail_rows = list(csv.reader(open(os.path.join(tmp, "trail.csv"))))
        offer_rows = list(csv.DictReader(open(os.path.join(tmp, "offerings.csv"))))
        net = json.load(open(os.path.join(tmp, "network.json")))
    check("every data file is written",
          names == sorted(["keywords.csv", "series.csv", "topics.csv",
                           "offerings.csv", "tested.csv", "trail.csv",
                           "opportunities.csv", "page_one.csv",
                           "share_of_voice.csv", "network.json",
                           "forecast.json", "run.json"]))
    check("one row per keyword, with its three axes",
          len(kw_rows) == len(cad.keywords)
          and {"about", "wants", "answer"} <= set(kw_rows[0]))
    check("a term with commas and quotes survives the round trip",
          any(r["term"] == 'bim "services", nyc' for r in kw_rows))
    check("one row per statement tested, with the verdict and why",
          len(tested) == len(ranked_claims) + 1
          and any(r["verdict"] == "misread" and r["why"] for r in tested))
    check("the ranking is carried into the tested file",
          [r["rank"] for r in tested[:3]] == ["1", "2", "3"])
    check("one row per keyword-month in the series",
          len(series_rows) - 1 == sum(len(k.trend) for k in cad.keywords.values()))
    check("one row per thread in the trail",
          len(trail_rows) - 1 == len(threads[:2]))
    check("one row per offering",
          sorted(r["offering"] for r in offer_rows)
          == sorted(r["offering"] for r in cad.offering_rows()))
    check("the network file says its calibration is unverified",
          "unverified" in net["what_this_is"])

    print("close variants")
    wave = [100 + (i % 7) * 13 for i in range(24)]
    other = [300 + (i % 5) * 17 for i in range(24)]
    months24 = [f"{y}-{m:02d}" for y in (2024, 2025) for m in range(1, 13)]

    def row(term, volume, trend):
        return {"term": term, "volume": volume, "cpc": 2.0,
                "competition_index": 10, "low_bid": 1.0, "high_bid": 3.0,
                "trend": list(trend), "months": months24,
                "source": "expanded"}
    cv = K.Graph("bim services", "United States", "en")
    cv.add_rows([row("bim service", 590, wave),
                 row("bim services", 590, wave),
                 row("bim services company", 590, wave),
                 row("bim consulting", 590, other)])
    check("Google's close variants are one search, kept as an alias",
          "bim service" in cv.keywords and "bim services" not in cv.keywords
          and "bim services" in cv.keywords["bim service"].aliases)
    check("a variant one word longer is still the same search",
          "bim services company" not in cv.keywords
          and cv.variants_collapsed == 2)
    check("the same volume with a different series is a different search",
          "bim consulting" in cv.keywords)
    abbr = K.Graph("bim services", "United States", "en")
    abbr.add_rows([dict(row("bim services", 590, wave), cpc=30.02),
                   dict(row("building information modeling services", 590,
                            wave), cpc=30.02)])
    check("any wording is the same search when the price matches to the cent",
          list(abbr.keywords) == ["bim services"]
          and abbr.keywords["bim services"].aliases
          == ["building information modeling services"])
    free = K.Graph("bim services", "United States", "en")
    free.add_rows([dict(row("bim services", 590, wave), cpc=0.0),
                   dict(row("building information modeling services", 590,
                            wave), cpc=0.0)])
    check("but a price of zero matches by chance, so it identifies nothing",
          len(free.keywords) == 2)
    flat = K.Graph("x", "United States", "en")
    flat.add_rows([row("bim service", 10, [10] * 24),
                   row("bim services", 10, [10] * 24)])
    check("a flat series identifies nothing", len(flat.keywords) == 2)

    print("page one")
    rows_ = [{"type": "paid", "domain": "www.ads.com", "rank": 1},
             {"type": "organic", "domain": "www.quora.com", "url": "u1",
              "title": "Q", "description": "d1"},
             {"type": "people_also_ask", "domain": ""},
             {"type": "organic", "domain": "united-bim.com", "url": "u2",
              "title": "U", "description": "d2"}]
    org = S.organic_rows(rows_)
    check("page one's organic rows are ranked from one, without www",
          [(r["rank"], r["domain"]) for r in org]
          == [(1, "quora.com"), (2, "united-bim.com")]
          and org[0]["description"] == "d1")

    class _Ground:
        """Page one about the market for one search, about fashion for the
        other."""
        def __init__(self):
            self.asked = {}
        def ask(self, state, questions):
            self.asked = questions
            class R:
                usage = jev.Usage()
                def noul(_, key):
                    q = questions[key].instructions
                    fashion = any("models agency" in line
                                  for line in q["first_page"])
                    return type("N", (), {"noul": 0.1 if fashion else 0.9,
                                          "yes": lambda self_, t=0.5:
                                          (0.1 if fashion else 0.9) > t})()
            return R()
    fake = _Ground()
    gg = K.Graph("cad to bim", "United States", "en")
    gg.add_rows([row("top modelling", 8100, wave),
                 row("cad to bim services", 100, other)])
    drop, st = judge.ground(fake, gg, {
        "top modelling": [{"domain": "img.com", "title": "IMG models agency",
                           "description": "Top models agency in NYC"}],
        "cad to bim services": [{"domain": "united-bim.com",
                                 "title": "CAD to BIM conversion services",
                                 "description": ""}],
        "unread": []}, "a founder")
    check("a search whose first page is about something else is dropped",
          drop == ["top modelling"] and st.questions == 2)
    first = next(iter(fake.asked.values())).instructions
    check("the question carries the page, the market and the relevance "
          "criteria", first["market"] == "cad to bim"
          and first["first_page"] and "question" in first
          and next(iter(fake.asked.values())).criteria
          == judge.RELEVANCE_CRITERIA)
    check("a page with no results is not asked about", st.questions == 2)

    print("where to win")
    import opportunity as O
    check("the click weights fall with position, the top three most of it",
          O.click_weight(1) > O.click_weight(2) > O.click_weight(10) > 0
          and O.click_weight(11) == 0
          and sum(O.CTR_BY_POSITION[:3]) / sum(O.CTR_BY_POSITION) > 0.7)
    page = [{"rank": 1, "kind": "specialist"}, {"rank": 2, "kind": "community"},
            {"rank": 3, "kind": "major_brand"}]
    split = O.click_split(page)
    check("page one's clicks split by kind, weighted by position, summing "
          "to one", abs(sum(split.values()) - 1) < 1e-9
          and split["specialist"] > split["community"] > split["major_brand"])

    def buyer(term, volume, cpc, offering="service"):
        kw = K.Keyword(term, volume, cpc, trend=[], months=[],
                       source="site:a.com")
        kw.job, kw.job_certain = "buy", True
        kw.offering, kw.offering_certain = offering, True
        kw.topic = "bim services"
        return kw

    def serp(*urls):
        return [{"rank": i + 1, "domain": u.split("/")[0], "url": u,
                 "title": u, "description": ""} for i, u in enumerate(urls)]
    a_, b_, c_ = (buyer("bim modeling services", 390, 70.0),
                  buyer("bim modelling services", 90, 60.0),
                  buyer("revit families", 900, 3.0, "software"))
    pages = {a_.term: serp("x.com/1", "y.com/2", "z.com/3", "w.com/4"),
             b_.term: serp("y.com/2", "x.com/1", "z.com/3", "v.com/9"),
             c_.term: serp("x.com/1", "q.com/7", "r.com/8", "s.com/9")}
    groups = O.serp_clusters([a_, b_, c_], pages)
    check("three shared results make one page's work; one does not",
          [[k.term for k in g_.keywords] for g_ in groups]
          == [[a_.term, b_.term], [c_.term]])
    for r, kind in zip(groups[0].page, ("specialist", "community",
                                        "community", "list")):
        r["kind"] = kind
    for r, kind in zip(groups[1].page, ("major_brand", "specialist",
                                        "list", "specialist")):
        r["kind"] = kind
    check("open value is the buyer money times the clicks on weak pages",
          abs(groups[0].open_value
              - groups[0].prize * groups[0].weak_share) < 1e-9
          and groups[0].weak_share > 0 and groups[1].open_value == 0)
    wg = K.Graph("cad to bim", "United States", "en")
    for kw in (a_, b_, c_):
        wg.keywords[kw.term] = kw
    a_.difficulty, b_.difficulty, c_.difficulty = 30, 30, 5
    front = O.pareto(O.candidates(groups))
    check("the front keeps genuine trade-offs: more money against an easier "
          "page one", [c.anchor.term for c in front]
          == ["bim modeling services", "revit families"])
    c_.difficulty = 40
    check("and drops what another beats on every count",
          [c.anchor.term for c in O.pareto(O.candidates(groups))]
          == ["bim modeling services"])
    c_.difficulty = 5
    words = O.rank_words(front)
    check("each choice is described by where it stands, in words",
          "the most buyer money of the 2" in words["bim modeling services"]
          and "the easiest of the 2" in words["revit families"]
          and "all pages built for it" in words["revit families"])
    start = O.start_here(wg, front[0], front)
    check("start here names the pick and the choices nothing beats",
          len(start) == 1 and "bim modeling services" in start[0].headline
          and "y.com at 2" in start[0].text and "revit families" in
          start[0].text)
    check("start here claims only the advantages its group has",
          "more buyer money is behind them" in start[0].assertion
          and "easier to reach" not in start[0].assertion
          and "the most buyer money of the 2 groups" in start[0].text)
    easy = O.start_here(wg, front[1], front, groups)
    check("and says so when its group is the easier one",
          "easier to reach" not in easy[0].assertion
          or "lower than" in easy[0].text)
    door = O.open_door(wg, groups)
    check("the open door is the most buyer money on a weak page one",
          len(door) == 1 and "bim modeling services" in door[0].headline
          and O.open_door(wg, groups, groups[0]) == []
          and O.open_door(wg, groups[1:]) == [])
    pair = O.who_answers(wg, groups)
    check("who answers buyers first is the kind ahead of every other, with "
          "the runner-up as its rival",
          len(pair) == 1 and pair[0].kind == "who_answers"
          and pair[0].headline.endswith("specialist firms")
          and "forum threads" in pair[0].forbids
          and pair[0].evidence["frame"] == O.ANSWER_FRAMES["specialist"]
          and pair[0].assertion.endswith(O.ANSWER_MOVES["specialist"] + "."))
    # Position 2 weighs what positions 3, 4 and 9 weigh together.
    tied = O.Cluster(list(groups[0].keywords), page=[
        {"rank": 2, "kind": "list"}, {"rank": 3, "kind": "specialist"},
        {"rank": 4, "kind": "specialist"}, {"rank": 9, "kind": "specialist"}])
    check("and nothing is said when no kind is ahead as printed",
          round(100 * O.market_split([tied])["list"])
          == round(100 * O.market_split([tied])["specialist"])
          and O.who_answers(wg, [tied, tied]) == [])
    costs = O.customer_cost(wg)
    check("one kind of buyer with a single search is not split out",
          len(costs) == 1 and costs[0].headline.startswith("A lead costs")
          and [r["offering"] for r in costs[0].evidence["by_offering"]]
          == ["service"])
    d_ = buyer("revit plugins", 300, 4.0, "software")
    wg.keywords[d_.term] = d_
    costs = O.customer_cost(wg)
    check("a lead's cost is split by what the buyer wants",
          len(costs) == 1 and "services" in costs[0].headline
          and "software" in costs[0].headline
          and [r["offering"] for r in costs[0].evidence["by_offering"]]
          == ["service", "software"])
    del wg.keywords[d_.term]
    owners = O.who_owns(wg, [
        {"domain": "www.quora.com", "etv": 50.0, "keywords": 9},
        {"domain": "www.united-bim.com", "etv": 30.0, "keywords": 5},
        {"domain": "united-bim.com", "etv": 10.0, "keywords": 3},
        {"domain": "tesla-outsourcing.com", "etv": 20.0, "keywords": 4}],
        {"quora.com": "community"})
    check("share of voice merges www and names businesses, not forums",
          owners and owners[0].evidence["leader"] == "united-bim.com"
          and owners[0].evidence["leader_share"] == round(40 / 110, 3)
          and "www." not in owners[0].text)

    branded = buyer("revit price", 1000, 8.6, "software")
    branded.entities = ["revit"]
    brand_pages = {branded.term: serp("autodesk.com/p", "reddit.com/r",
                                      "g2.com/x")}
    brand_group = O.serp_clusters([branded], brand_pages)
    for r, kind in zip(brand_group[0].page, ("major_brand", "community",
                                             "list")):
        r["kind"] = kind
    check("buyers looking for a company by name are no one else's to win",
          brand_group[0].weak_share > 0 and brand_group[0].open_value == 0
          and O.candidates(brand_group) == []
          and O.open_door(wg, brand_group) == [])

    print("settled is about buyers")
    def topic_market(rows_):
        g_ = K.Graph("cad to bim", "United States", "en")
        g_.add_rows([{"term": t, "volume": v, "cpc": 5.0,
                      "competition_index": 20, "low_bid": 1.0,
                      "high_bid": 9.0, "trend": [], "months": [],
                      "source": "site:a.com"} for t, v, _, _, _ in rows_])
        for t, _, topic, job, ents in rows_:
            kw = g_.keywords[t]
            kw.topic, kw.topic_confidence = topic, 0.9
            kw.job, kw.job_confidence, kw.job_certain = job, 0.9, True
            kw.entities = list(ents)
            g_.add_topic(topic, confirmed=True)
        return g_
    defs = topic_market([
        ("revit price", 1000, "bim software", "buy", ["revit"]),
        ("buy revit", 500, "bim software", "buy", ["revit"]),
        ("bim software", 6600, "bim software", "learn", []),
        ("what is building information management", 5400,
         "building information management", "learn", []),
        ("building information management guide", 900,
         "building information management", "learn", []),
        ("bim services", 590, "bim services", "buy", []),
        ("bim modeling services", 390, "bim services", "buy", [])])
    settled = [c for c in insights.generate(defs) if c.kind == "settled"]
    check("a topic nobody shops in is not called unsettled",
          settled and "building information management" not in settled[0].text
          and "bim services" in settled[0].headline
          and "shopping" in settled[0].text)
    thin_lead = [c for c in insights.generate(topic_market([
        ("revit price", 1000, "bim software", "buy", ["revit"]),
        ("bim software", 6600, "bim software", "compare", []),
        ("buy revit", 500, "bim software", "buy", ["revit"]),
        ("bim services", 590, "bim services", "buy", []),
        ("bim modeling services", 390, "bim services", "buy", [])]))
        if c.kind == "settled"]
    check("settled needs most of the shoppers to name a company",
          thin_lead == [])
    diy = [("free bim software", 800, "bim software", "self_serve", []),
           ("revit crack", 300, "bim software", "self_serve", ["revit"])]
    base = [("revit price", 1000, "bim software", "buy", ["revit"]),
            ("bim software", 6600, "bim software", "compare", []),
            ("bim services", 590, "bim services", "buy", []),
            ("what is bim", 9000, "bim", "learn", [])]
    fewer = [c for c in insights.generate(topic_market(base + diy))
             if c.kind == "selfserve"]
    more = [c for c in insights.generate(topic_market(
        base + diy + [("bim tutorial free", 9900, "bim", "self_serve", [])]))
        if c.kind == "selfserve"]
    check("doing without is not called the competitor when fewer do it than "
          "shop", fewer == [])
    check("and is when more do", len(more) == 1
          and "more than the" in more[0].text)

    arm = start + door + pair + costs + owners + O.switching(wg) \
        + O.new_demand(wg)
    try:
        insights.select_by_code(wg, arm)
        check("the threshold arm reads the where-to-win families",
              all(c.verdict in ("kept", "below threshold") for c in arm))
    except Exception as exc:  # noqa: BLE001 — the regression is any raise
        check("the threshold arm reads the where-to-win families", False,
              repr(exc))

    money_md = report.render(wg, [], [], man, "d", {"opportunities": groups})
    check("the report says where the reachable buyer money is, as a "
          "measurement", "Where the buyer money is: **“bim modeling "
          "services”**" in money_md and "opportunities.csv" in money_md)
    check("and says nothing of it when no group was read",
          "Where the buyer money is" not in report.render(
              wg, [], [], man, "d", {"opportunities": []}))

    amb = topic_market([
        ("project management software", 1000, "project management software",
         "compare", []),
        ("pm software", 5000, "project management software", "compare", []),
        ("project management software jobs", 100,
         "project management software", "career", []),
        ("task management", 4000, "task management", "learn", []),
        ("task tracker", 3000, "task management", "compare", [])])
    amb.keywords["project management software jobs"].job_certain = False
    amb.keywords["task tracker"].job_certain = False
    ambiguity = next((c for c in insights.generate(amb)
                      if c.kind == "ambiguity"), None)
    shares = [int(x.split("(")[1].split("%")[0])
              for x in ambiguity.evidence["least_legible_topics"]] \
        if ambiguity else []
    check("a topic's clear share is over the searches placed on it, never "
          "past 100%", shares and max(shares) <= 100)

    m24 = [f"{y}-{m:02d}" for y in (2024, 2025) for m in range(1, 13)]
    flat_market = K.Graph("cad to bim", "United States", "en")
    flat_rows = []
    for t, topic, base in (("bim services", "bim services", 1000),
                           ("bim consulting", "bim services", 800),
                           ("revit", "revit", 2000),
                           ("revit price", "revit", 900)):
        series = [base + (i % 3) for i in range(12)] + \
                 [round(base * 0.996) + (i % 3) for i in range(12)]
        flat_rows.append({"term": t, "volume": base, "cpc": 5.0,
                          "competition_index": 20, "low_bid": 1.0,
                          "high_bid": 9.0, "trend": series, "months": m24,
                          "source": "site:a.com"})
    flat_market.add_rows(flat_rows)
    for t, topic in (("bim services", "bim services"),
                     ("bim consulting", "bim services"),
                     ("revit", "revit"), ("revit price", "revit")):
        kw = flat_market.keywords[t]
        kw.topic, kw.topic_confidence = topic, 0.9
        kw.job, kw.job_confidence, kw.job_certain = "compare", 0.9, True
        flat_market.add_topic(topic, confirmed=True)
    check("a market at 1.00x as printed is neither growing nor shrinking",
          not any(c.kind == "direction"
                  for c in insights.generate(flat_market)))

    import random
    rng = random.Random(7)
    lower = [1000 + rng.randint(-40, 40) for _ in range(12)]
    higher = [1400 + rng.randint(-40, 40) for _ in range(12)]
    same = [1000 + rng.randint(-40, 40) for _ in range(12)]
    check("a year that stands apart from the last is a direction",
          K.shifted(lower, higher) and K.shifted(higher, lower))
    check("a year among the last one's months is not, whatever its median",
          not K.shifted(lower, same))
    check("a spiked month cannot manufacture one",
          not K.shifted(lower, same[:11] + [90000]))

    print("the value floor")
    def _stakes(probabilities):
        class _Floor:
            def ask(self, state, questions):
                class R:
                    usage = jev.Usage()
                    def noul(self, key):
                        v = {"true": 0.9, "swap": 0.1, "obvious": 0.1,
                             "odd": 0.5}
                        return type("N", (), {"noul": v[key.split(":")[0]]})()
                    def choice(self, key):
                        return type("C", (), {
                            "choice": "statement",
                            "probabilities": {"statement": 0.8, "rival": 0.1,
                                              "neither": 0.1},
                            "confidence": 0.8})()
                    def score(self, key):
                        return type("S", (), {
                            "normalized": 0.5, "label": "Colour",
                            "legend": {"0": "Nothing", "1": "Colour",
                                       "2": "A choice", "3": "A reversal"},
                            "probabilities": probabilities})()
                return R()
        claim = next(c for c in insights.generate(ms_graph)
                     if c.kind == "money_seat")
        judge.adjudicate(_Floor(), ms_graph, [claim], "a founder")
        return claim
    spread = _stakes({"0": 0.32, "1": 0.20, "2": 0.36, "3": 0.12})
    check("a decision must win a majority, not a plurality",
          spread.verdict == "changes nothing" and spread.decides < 0.5)
    colour = _stakes({"0": 0.10, "1": 0.45, "2": 0.30, "3": 0.15})
    check("colour short of a majority for a decision is background",
          colour.verdict == "background" and not colour.survived())
    kept_ = _stakes({"0": 0.10, "1": 0.35, "2": 0.30, "3": 0.25})
    check("a majority for a decision is kept, labelled by the decision side",
          kept_.survived() and kept_.stakes_label == "A choice")

    print("decisions skip the swap test")
    class _Count:
        def __init__(self):
            self.keys = []
        def ask(self, state, questions):
            self.keys = list(questions)
            return _Floor_result()
    class _Floor_result:
        usage = jev.Usage()
        def noul(self, key):
            return type("N", (), {"noul": 0.9 if key.startswith("true")
                                  else 0.1})()
        def choice(self, key):
            return type("C", (), {"choice": "statement",
                                  "probabilities": {"statement": 0.8},
                                  "confidence": 0.8})()
        def score(self, key):
            return type("S", (), {"normalized": 0.7, "label": "A choice",
                                  "legend": {"2": "A choice"},
                                  "probabilities": {"2": 0.8}})()
    counter = _Count()
    judge.adjudicate(counter, wg, start + door + pair, "a founder")
    check("no swap question is asked of a decision-shaped claim",
          not any(k.startswith("swap:") for k in counter.keys)
          and all(c.swappable == 0.0 for c in start + door + pair))

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
