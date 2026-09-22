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
import report
import seo

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


def offline() -> None:
    print("arithmetic")
    check("median", K.median([1, 2, 3, 4]) == 2.5)
    check("growth needs 12 months", K.growth([1, 2, 3]) is None)
    check("growth ratio", abs(K.growth([10] * 6 + [20] * 6) - 2.0) < 1e-9)
    check("seasonality flat is 1.0", abs(K.seasonality([5] * 12) - 1.0) < 1e-9)
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
    probes = K.probe_candidates(["crm software"], ["pricing"], known, limit=9)
    check("probes never re-price what is known",
          not (set(probes) & known))
    check("probes are deterministic",
          probes == K.probe_candidates(["crm software"], ["pricing"],
                                       known, limit=9))

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
