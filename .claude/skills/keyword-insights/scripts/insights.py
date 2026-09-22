"""Candidate claims, and the two ways of choosing between them.

Generation here is *exhaustive and structural*. A template fires wherever
the graph has the shape it describes — two jobs present, a trend measured,
a pair of topics compared — and never because a number crossed a line the
author drew. Complementary claims ("this market is already branded" and
"this market is unbranded") are both generated on purpose, so that the
selection step, not the generator, decides which is true.

Two selectors are provided so the difference can be measured rather than
asserted:

    code  — the conventional way: hand-tuned thresholds and a weighted score
    jev   — every kept/dropped and the whole ordering comes from Jev

`code` exists as the control arm. Its constants are set to the values an
experienced practitioner would pick, and they are exactly what is under test.
"""

from __future__ import annotations

import json
import os
from collections import Counter
from dataclasses import dataclass
from typing import Sequence

import kgraph as K
from judge import Claim

# Google Ads accepts at most 20 seeds per expansion.
K_MAX_SEEDS = 20

# What each kind of follow-up has actually returned, measured rather than
# assumed. Seeded from 33 probes across the markets in evals/LEDGER.md and
# added to on every run, so the estimate sharpens with use.
#
# The spread is not subtle. `diy` and `money` price facet combinations
# against vocabulary the market really uses and land every time; `brands`
# priced `<brand> vs / pricing` combinations that Google barely holds, and
# is now superseded by harvesting that brand's site for the same $0.09 and
# twenty times the rows.
_SEED_RECORD = {
    "diy": [5, 0], "money": [5, 0], "minority": [1, 0], "growth": [1, 0],
    "outlier": [2, 2], "adjacent": [1, 2], "movers": [1, 7],
    "brands": [0, 5], "vocabulary": [0, 1],
}
_RECORD_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    ".cache", "probe_record.json")


def _load_record() -> dict[str, list[int]]:
    try:
        with open(_RECORD_PATH, encoding="utf-8") as fh:
            stored = json.load(fh)
    except (OSError, ValueError):
        stored = {}
    record = {k: list(v) for k, v in _SEED_RECORD.items()}
    for tag, pair in stored.items():
        if isinstance(pair, list) and len(pair) == 2:
            record[tag] = pair
    return record


def hit_rate(tag: str) -> float:
    """How often this kind of follow-up has returned anything usable.

    Laplace-smoothed, so a kind nobody has tried sits at even odds rather
    than at zero or one — a uniform prior, not a number picked to make the
    arithmetic come out.
    """
    paid, dead = _load_record().get(tag, [0, 0])
    return (paid + 1) / (paid + dead + 2)


def record_probe(tag: str, paid_off: bool) -> None:
    """Add one observation. The record is the point of keeping it."""
    record = _load_record()
    entry = record.setdefault(tag, [0, 0])
    entry[0 if paid_off else 1] += 1
    try:
        os.makedirs(os.path.dirname(_RECORD_PATH), exist_ok=True)
        tmp = _RECORD_PATH + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(record, fh, indent=1, sort_keys=True)
        os.replace(tmp, _RECORD_PATH)
    except OSError:
        pass

# --------------------------------------------------------------------------
# Control-arm constants. Every one of these is a number someone invented.
# They are gathered here, rather than scattered through the generator, so
# that the thing being tested is visible in one place.
# --------------------------------------------------------------------------

CODE_ARM = {
    "branded_share_high": 0.40,
    "branded_share_low": 0.20,
    "growth_up": 1.30,
    "growth_down": 0.77,
    "seasonality": 2.00,
    "self_serve_share": 0.25,
    "job_dominance": 0.45,
    "cpc_spread": 3.00,
    "cell_premium": 2.00,
    "gradient_lift": 1.50,
}


def n(value: float) -> str:
    return f"{int(round(value)):,}"


# DataForSEO returns Google Ads click prices as bare numbers — the response
# carries no currency field of any kind. Their documented behaviour is US
# dollars, but printing a symbol the source never stated is the sort of
# confidently-wrong number this whole method exists to avoid, so the symbol
# is settable and the report says where it came from.
_CURRENCY = "$"


def set_currency(symbol: str) -> None:
    global _CURRENCY
    _CURRENCY = symbol or "$"


def usd(value: float) -> str:
    return f"{_CURRENCY}{value:,.2f}"


def pct(value: float) -> str:
    return f"{value * 100:.0f}%"


def _examples(keywords: Sequence[K.Keyword], limit: int = 6) -> list[str]:
    top = sorted(keywords, key=lambda k: -k.volume)[:limit]
    return [f"{k.term} ({n(k.volume)}/mo, {usd(k.cpc)} a click)" for k in top]


# --------------------------------------------------------------------------
# Generation
# --------------------------------------------------------------------------

def generate(graph: K.Graph) -> list[Claim]:
    """One claim per pattern, stated about the market and naming its extremes.

    An earlier version instantiated each template once per topic, which
    produced reports like *"project tracking software is moving down"*,
    *"pmo software is moving down"*, *"ms project is moving down"* — sixteen
    of twenty findings being two sentences with the nouns changed. That is
    not sixteen findings. A pattern that holds across a market's topics is
    **one** finding *about the market*, and saying it that way is both
    shorter and more informative, because the market-level version can name
    which topics break the pattern.

    So each family fires once, carries the aggregate, and names the extreme
    cases inside itself. Nothing specific is lost; the repetition is.

    Each claim is built in two forms. `text` carries the measurements and is
    what a reader sees. `assertion` is the same reading with every number
    stripped out — and that is the form the quality tests run against,
    because a sentence containing "165,000/mo at $49.28" passes any test for
    specificity on the strength of its digits alone.
    """
    claims: list[Claim] = []
    rows = {r["topic"]: r for r in graph.topic_rows()}
    by_topic: dict[str, list[K.Keyword]] = {}
    for kw in graph.certain:
        if kw.topic and kw.topic not in ("", "none"):
            by_topic.setdefault(kw.topic, []).append(kw)
    if not by_topic:
        return claims

    market_price = graph.market_click_price
    total_money = graph.total_money
    ranked = sorted(by_topic, key=lambda t: -rows.get(t, {}).get("volume", 0))
    top_examples = _examples(by_topic[ranked[0]])

    # How much searching the whole reading rests on. Carried into every
    # claim's measurements, because a reader — and a judge — cannot tell a
    # fair reading from an overreach without it. Without this, a market of
    # eleven keywords and 1,340 searches a month produced the sentence
    # "this market is shrinking" in exactly the same confident register as
    # one built on two million.
    basis = {"keywords_this_rests_on": len(graph.certain),
             "monthly_searches_this_rests_on": graph.certain_volume}

    def add(key, text, assertion, rival, evidence, examples, topic="",
            kind=""):
        claims.append(Claim(key=key, text=text, assertion=assertion,
                            forbids=rival, evidence={**evidence, **basis},
                            examples=examples, topic=topic, kind=kind))

    # ---- is there anything here at all? ---------------------------------
    #
    # Generated for every market, including the ones where it is obviously
    # false. When a seed turns up eleven keywords and 1,340 searches a
    # month, "almost nobody is looking for this" is not a caveat to bury
    # under the findings — it *is* the finding, and it answers the question
    # the reader came with. Jev rejects it out of hand for a market with
    # millions of searches, so it costs nothing to offer.
    head_kw = max(graph.certain, key=lambda k: k.volume, default=None)
    if head_kw is not None:
        top5 = sorted(graph.keywords.values(), key=lambda k: -k.volume)[:5]
        top5_share = K.share(sum(k.volume for k in top5),
                             max(graph.total_volume, 1))
        add("market|thin",
            f"There is no spread to work with here: {len(graph.keywords):,} "
            f"keywords in total carrying {n(graph.total_volume)} searches a "
            f"month, and the five largest are "
            f"{pct(top5_share)} of all of it.",
            f"Almost all of the searching in this market sits in a handful "
            f"of terms, so there are no distinct groups of searcher to tell "
            f"apart.",
            f"The searching in this market is spread across many different "
            f"terms, which can be told apart from one another.",
            {"keywords_found": len(graph.keywords),
             "total_monthly_searches": graph.total_volume,
             "top_five_share_of_all_searching": round(top5_share, 3),
             "top_five": [f"{k.term} ({k.volume:,}/mo)" for k in top5]},
            _examples(graph.certain), head_kw.topic or ranked[0], "thin")

    # ---- which way is the whole thing going? ----------------------------
    #
    # A real year-on-year comparison: the last twelve months against the
    # twelve before them. Both are complete seasonal cycles, so the season
    # cancels and what is left is the change in level. This is only
    # available because every call asks DataForSEO for four years of
    # history, which it gives away at the same price as one.
    trended = [(t, rows[t]["growth"]) for t in ranked
               if rows.get(t, {}).get("growth") is not None]
    if trended:
        recent = sum(sum(K.weighted_trend(by_topic[t])[-12:])
                     for t, _ in trended)
        prior = sum(sum(K.weighted_trend(by_topic[t])[-24:-12])
                    for t, _ in trended)
        overall = (recent / prior) if prior else 1.0
        rising = sorted([x for x in trended if x[1] >= 1.0],
                        key=lambda x: -x[1])
        falling = sorted([x for x in trended if x[1] < 1.0],
                         key=lambda x: x[1])
        up = overall >= 1.0
        exceptions = (falling if up else rising)[:3]
        years = max((rows[t]["years_of_history"] for t, _ in trended),
                    default=2)
        add("market|direction",
            f"This market is {'growing' if up else 'shrinking'}: across "
            f"{len(trended)} measured topics the last twelve months ran at "
            f"{overall:.2f}x the twelve before them"
            + (f", and the exceptions run the other way — "
               + "; ".join(f"\u201c{t}\u201d at {g:.2f}x"
                           for t, g in exceptions) + "."
               if exceptions else "."),
            f"Demand across this market as a whole is "
            f"{'rising' if up else 'falling'} year on year, and it does not "
            f"move as one — some parts run against the trend.",
            f"Demand across this market is roughly where it was a year ago, "
            f"and moves as one.",
            {"last_twelve_months_over_the_twelve_before": round(overall, 3),
             "topics_measured": len(trended),
             "years_of_history": years,
             "rising": [f"{t} {g:.2f}x" for t, g in rising[:5]],
             "falling": [f"{t} {g:.2f}x" for t, g in falling[:5]]},
            top_examples, ranked[0], "direction")

    # ---- what sets the price of a click: the topic, or the intention? ---
    by_job: dict[str, list[K.Keyword]] = {}
    for kw in graph.certain:
        by_job.setdefault(kw.job, []).append(kw)
    job_cpc = {j: K.click_price(kws)
               for j, kws in by_job.items() if len(kws) >= 2}
    topic_cpc = {t: rows[t]["click_price"] for t in ranked
                 if rows.get(t, {}).get("click_price", 0) > 0}
    if len(job_cpc) >= 2 and len(topic_cpc) >= 2:
        jv = [v for v in job_cpc.values() if v > 0]
        tv = [v for v in topic_cpc.values() if v > 0]
        if jv and tv:
            job_spread = max(jv) / max(min(jv), 0.01)
            topic_spread = max(tv) / max(min(tv), 0.01)
            intent_wins = job_spread >= topic_spread
            dear_job = max(job_cpc, key=job_cpc.get)
            cheap_job = min(job_cpc, key=job_cpc.get)
            dear_topic = max(topic_cpc, key=topic_cpc.get)
            axis = ("what the searcher wants" if intent_wins
                    else "which part of the market they are in")
            add("market|pricing_axis",
                f"In this market a click is priced by {axis}. Across "
                f"intentions the click price runs "
                f"{usd(min(jv))}\u2013{usd(max(jv))} "
                f"({job_spread:.1f}x), dearest among people "
                f"{K.JOB_LABELS.get(dear_job, dear_job)} and cheapest among "
                f"people {K.JOB_LABELS.get(cheap_job, cheap_job)}; across "
                f"topics it runs {usd(min(tv))}\u2013{usd(max(tv))} "
                f"({topic_spread:.1f}x), dearest in "
                f"\u201c{dear_topic}\u201d.",
                f"What a click costs in this market is set mainly by "
                f"{axis}.",
                f"What a click costs in this market is set mainly by "
                + ("which part of the market the searcher is in."
                   if intent_wins else "what the searcher wants."),
                {"click_price_by_intent": {j: round(v, 2)
                                          for j, v in sorted(
                                              job_cpc.items(),
                                              key=lambda x: -x[1])},
                 "spread_across_intent": round(job_spread, 2),
                 "spread_across_topic": round(topic_spread, 2),
                 "market_click_price": round(market_price, 2)},
                _examples(by_job.get(dear_job, [])), dear_topic,
                "pricing_axis")

    # ---- what are people trying to do, and where does it differ? --------
    mix_total: dict[str, int] = {}
    for kw in graph.certain:
        mix_total[kw.job] = mix_total.get(kw.job, 0) + kw.volume
    certain_vol = max(sum(mix_total.values()), 1)
    if len(mix_total) >= 2:
        order_jobs = sorted(mix_total.items(), key=lambda x: -x[1])
        (j1, v1), (j2, v2) = order_jobs[0], order_jobs[1]
        # The topic that departs furthest from the market's own mix.
        def dominant(t):
            m = rows[t]["job_mix"]
            return max(m.items(), key=lambda x: x[1]) if m else ("", 0.0)
        outliers = [(t, *dominant(t)) for t in ranked if rows.get(t)]
        odd = [o for o in outliers if o[1] and o[1] != j1]
        odd.sort(key=lambda o: -o[2])
        add("market|intent",
            f"Most of this market is people "
            f"{K.JOB_LABELS.get(j1, j1)} ({pct(K.share(v1, certain_vol))} of "
            f"{n(certain_vol)} searches where the intent is clear), ahead of "
            f"{K.JOB_LABELS.get(j2, j2)} ({pct(K.share(v2, certain_vol))})"
            + (f" — but \u201c{odd[0][0]}\u201d breaks that, running "
               f"{pct(odd[0][2])} {K.JOB_LABELS.get(odd[0][1], odd[0][1])}."
               if odd else "."),
            f"This market is mostly people {K.JOB_LABELS.get(j1, j1)}"
            + (f", except in \u201c{odd[0][0]}\u201d, where they are "
               f"{K.JOB_LABELS.get(odd[0][1], odd[0][1])} instead."
               if odd else "."),
            f"What people are trying to do is much the same across every "
            f"part of this market.",
            {"intent_mix": {j: round(K.share(v, certain_vol), 3)
                            for j, v in order_jobs},
             "searches_with_clear_intent": certain_vol,
             "topics_against_the_grain": [f"{t}: {j} {p:.0%}"
                                          for t, j, p in odd[:4]]},
            _examples(by_job.get(j1, [])), ranked[0], "intent")

    # ---- what the search itself will not tell you -----------------------
    unclear = graph.total_volume - graph.certain_volume
    if graph.total_volume > 0 and unclear > 0:
        vague = sorted(
            ((t, K.share(sum(k.volume for k in by_topic[t]),
                         sum(k.volume for k in graph.keywords.values()
                             if t in k.term) or 1)) for t in ranked[:8]),
            key=lambda x: x[1])
        add("market|ambiguity",
            f"{pct(K.share(unclear, graph.total_volume))} of this market's "
            f"{n(graph.total_volume)} monthly searches do not reveal what "
            f"the person wants — the words alone do not separate someone "
            f"comparing tools from someone looking for a job or a free "
            f"template. It is concentrated in the short, high-volume terms.",
            f"A large share of this market's searching does not reveal the "
            f"searcher's intent from the words alone, and that share sits in "
            f"the biggest terms.",
            f"Searches in this market generally make plain what the person "
            f"is trying to do.",
            {"searches_with_unclear_intent": unclear,
             "total_searches": graph.total_volume,
             "share_unclear": round(K.share(unclear, graph.total_volume), 3),
             "least_legible_topics": [f"{t} ({p:.0%} clear)"
                                      for t, p in vague[:4]]},
            top_examples, ranked[0], "ambiguity")

    # ---- how settled is this market? ------------------------------------
    settled = [(t, rows[t]["branded_share"], rows[t]["volume"])
               for t in by_topic if t in rows and rows[t]["volume"] > 0]
    if settled:
        most = max(settled, key=lambda x: (x[1], x[2]))
        least = min(settled, key=lambda x: (x[1], -x[2]))
        all_brands = sorted({e for k in graph.certain for e in k.entities})
        if most[0] != least[0]:
            add("market|settled",
                f"\u201c{most[0]}\u201d is settled and "
                f"\u201c{least[0]}\u201d is not: {pct(most[1])} of "
                f"\u201c{most[0]}\u201d searching names a company outright, "
                f"against {pct(least[1])} of \u201c{least[0]}\u201d "
                f"({n(least[2])} searches a month).",
                f"Buyers have settled on who supplies \u201c{most[0]}\u201d "
                f"but not \u201c{least[0]}\u201d — the same market is "
                f"closed in one place and open in another.",
                f"Buyers are about equally settled on who supplies every "
                f"part of this market.",
                {"most_branded": {"topic": most[0], "branded_share": most[1],
                                  "searches": most[2]},
                 "least_branded": {"topic": least[0],
                                   "branded_share": least[1],
                                   "searches": least[2]},
                 "brands_found": all_brands[:10]},
                _examples(by_topic[least[0]]), least[0], "settled")
        add("market|open",
            f"The open ground is \u201c{least[0]}\u201d: "
            f"{pct(1 - least[1])} of its {n(least[2])} monthly searches name "
            f"no company at all.",
            f"There is a part of this market — \u201c{least[0]}\u201d — "
            f"where buyers have no supplier in mind when they search.",
            f"Every part of this market already has suppliers that buyers "
            f"name for themselves.",
            {"topic": least[0], "unbranded_share": round(1 - least[1], 3),
             "searches": least[2], "brands_found": all_brands[:10]},
            _examples(by_topic[least[0]]), least[0], "open")

    # ---- is the money where the attention is? ---------------------------
    everything = [k for k in graph.certain if k.volume > 0]
    if everything:
        biggest = max(everything, key=lambda k: k.volume)
        dearest = max(everything, key=lambda k: k.cpc)
        if dearest.cpc > 0 and dearest.term != biggest.term:
            add("market|split",
                f"Attention and money are in different places here: the "
                f"most-searched term is \u201c{biggest.term}\u201d "
                f"({n(biggest.volume)}/mo at {usd(biggest.cpc)} a click), "
                f"while the dearest click is \u201c{dearest.term}\u201d "
                f"({n(dearest.volume)}/mo at {usd(dearest.cpc)}).",
                f"The busiest searches in this market are not the ones "
                f"advertisers pay most to reach.",
                f"The busiest searches in this market are also the ones "
                f"advertisers pay most to reach.",
                {"most_searched": {"term": biggest.term,
                                   "searches": biggest.volume,
                                   "cpc": biggest.cpc},
                 "dearest_click": {"term": dearest.term,
                                   "searches": dearest.volume,
                                   "cpc": dearest.cpc}},
                _examples([biggest, dearest]), biggest.topic or ranked[0],
                "split")
        add("market|head",
            f"The single largest search here is \u201c{biggest.term}\u201d "
            f"at {n(biggest.volume)}/mo, and those people are "
            f"{K.JOB_LABELS.get(biggest.job, biggest.job)}.",
            f"The largest single stream of attention in this market is "
            f"people {K.JOB_LABELS.get(biggest.job, biggest.job)}.",
            f"The largest single stream of attention in this market is "
            f"people ready to buy something.",
            {"term": biggest.term, "searches": biggest.volume,
             "cpc": biggest.cpc, "intent": biggest.job},
            _examples([biggest]), biggest.topic or ranked[0], "head")

    cells = graph.cells(min_keywords=1)
    if cells and total_money > 0:
        richest = max(cells, key=lambda c: c.money)
        label = K.JOB_LABELS.get(richest.job, richest.job)
        add("market|money_seat",
            f"The money is concentrated: people searching "
            f"\u201c{richest.topic}\u201d while {label} are "
            f"{pct(K.share(richest.volume, certain_vol))} of the searching "
            f"but {pct(K.share(richest.money, total_money))} of all the ad "
            f"spend these searches imply.",
            f"Advertiser spending in this market is concentrated on one kind "
            f"of searcher, out of proportion to how much they search.",
            f"Advertiser spending in this market is spread roughly in "
            f"proportion to how much each part of it is searched.",
            {"cell": f"{richest.topic} / {richest.job}",
             "share_of_searching": round(
                 K.share(richest.volume, certain_vol), 3),
             "share_of_implied_spend": round(
                 K.share(richest.money, total_money), 3)},
            _examples(richest.keywords), richest.topic, "money_seat")

    # ---- is the free route the real competitor? -------------------------
    ss_vol = mix_total.get("self_serve", 0)
    if ss_vol:
        worst = max(ranked, key=lambda t: rows[t]["job_mix"].get(
            "self_serve", 0.0))
        ss_kws = by_job.get("self_serve", [])
        add("market|selfserve",
            f"The competitor here is not a company but doing without: "
            f"{pct(K.share(ss_vol, certain_vol))} of the searching with a "
            f"clear intent is people trying to solve it without buying "
            f"anything, heaviest in \u201c{worst}\u201d at "
            f"{pct(rows[worst]['job_mix'].get('self_serve', 0))}.",
            f"A substantial part of the demand in this market is people "
            f"looking for a way to avoid paying anyone for it.",
            f"People in this market accept that solving the problem means "
            f"paying somebody for it.",
            {"self_serve_share": round(K.share(ss_vol, certain_vol), 3),
             "heaviest_topic": worst,
             "heaviest_share": round(
                 rows[worst]["job_mix"].get("self_serve", 0), 3),
             "click_price_of_self_serve": round(K.click_price(ss_kws), 2)},
            _examples(ss_kws), worst, "selfserve")

    # ---- is there a season? ---------------------------------------------
    seasonal = [(t, rows[t]["seasonality"]) for t in ranked
                if rows.get(t, {}).get("seasonality") is not None]
    if seasonal:
        peak_topic, peak_ratio = max(seasonal, key=lambda x: x[1])
        series = K.weighted_trend(by_topic[peak_topic])
        months = next((k.months for k in by_topic[peak_topic]
                       if len(k.months) == len(series)), [])
        peak = K.peak_month(series, months)
        add("market|season",
            f"The most seasonal part of this market is "
            f"\u201c{peak_topic}\u201d, peaking in {peak} at "
            f"{peak_ratio:.1f}x its average month; across all "
            f"{len(seasonal)} measured topics the median is "
            f"{K.median([r for _, r in seasonal]):.1f}x.",
            f"This market has a real season, concentrated around {peak} and "
            f"strongest in \u201c{peak_topic}\u201d.",
            f"This market is searched at much the same rate all year round.",
            {"most_seasonal_topic": peak_topic, "peak_month": peak,
             "peak_over_mean": round(peak_ratio, 2),
             "median_peak_over_mean_across_topics": round(
                 K.median([r for _, r in seasonal]), 2)},
            _examples(by_topic[peak_topic]), peak_topic, "season")

    # ---- what is weighed against what? ----------------------------------
    pairs: Counter[tuple[str, str]] = Counter()
    witness: dict[tuple[str, str], K.Keyword] = {}
    for kw in graph.certain:
        present = sorted(t for t in by_topic if t in kw.term)
        for i in range(len(present)):
            for j in range(i + 1, len(present)):
                a, b = present[i], present[j]
                if a in b or b in a:
                    continue
                pairs[(a, b)] += kw.volume
                if kw.volume >= getattr(witness.get((a, b)), "volume", -1):
                    witness[(a, b)] = kw
    if pairs:
        (a, b), vol = pairs.most_common(1)[0]
        kw = witness[(a, b)]
        add("market|substitute",
            f"\u201c{a}\u201d and \u201c{b}\u201d are weighed against "
            f"each other: {n(vol)} monthly searches name both at once, led "
            f"by \u201c{kw.term}\u201d.",
            f"\u201c{a}\u201d and \u201c{b}\u201d are two options in one "
            f"decision, not two separate markets.",
            f"\u201c{a}\u201d and \u201c{b}\u201d are bought by different "
            f"people, for different reasons.",
            {"searches_naming_both": vol, "example": kw.term,
             "example_cpc": kw.cpc,
             "other_pairs": [f"{x} + {y}" for (x, y), _ in
                             pairs.most_common(5)[1:]]},
            _examples([kw]), a, "substitute")

    # ---- does narrowing the search change who you reach? ----------------
    best: tuple[float, K.Keyword, K.Keyword, str] | None = None
    for topic in by_topic:
        bare = graph.keywords.get(topic)
        if not bare or bare.cpc <= 0:
            continue
        for kw in by_topic[topic]:
            if kw.term == topic or kw.cpc <= 0 or kw.volume <= 0:
                continue
            lift = kw.cpc / bare.cpc
            if best is None or lift > best[0]:
                best = (lift, bare, kw, kw.term.replace(topic, "").strip())
    if best:
        lift, bare, kw, facet = best
        add("market|gradient",
            f"Narrowing the search changes who answers it: "
            f"\u201c{bare.term}\u201d is {n(bare.volume)}/mo at "
            f"{usd(bare.cpc)} a click, while \u201c{kw.term}\u201d is "
            f"{n(kw.volume)}/mo at {usd(kw.cpc)} — {lift:.1f}x the price for "
            f"{pct(K.share(kw.volume, max(bare.volume, 1)))} of the volume.",
            f"Adding \u201c{facet}\u201d reaches a different and more "
            f"valuable searcher, not simply fewer of the same ones.",
            f"Narrowing a search in this market just gives you a smaller "
            f"slice of the same traffic at about the same price.",
            {"bare": {"term": bare.term, "searches": bare.volume,
                      "cpc": bare.cpc},
             "qualified": {"term": kw.term, "searches": kw.volume,
                           "cpc": kw.cpc},
             "cpc_ratio": round(lift, 2)},
            _examples([bare, kw]), bare.term, "gradient")

    return claims


# --------------------------------------------------------------------------
# Selection, arm A: thresholds (the control)
# --------------------------------------------------------------------------

def select_by_code(graph: K.Graph, claims: Sequence[Claim]) -> list[Claim]:
    """Keep and rank by hand-tuned constants — the conventional approach."""
    C = CODE_ARM
    rows = {r["topic"]: r for r in graph.topic_rows()}
    total = max(graph.judged_volume, 1)

    for claim in claims:
        row = rows.get(claim.topic, {})
        ev = claim.evidence
        keep = True
        kind = claim.kind
        if kind == "settled":
            # Was a price probe on `<brand> vs / alternative / pricing`
            # combinations: 0 payoffs in 5 attempts, $0.45 for nothing.
            # Google barely holds that vocabulary. Harvesting the brand's
            # own site costs the same $0.09 and returns its whole footprint
            # — which is what the question was really asking for.
            brands = ev.get("brands_found") or []
            add(claim,
                f"These searchers already name their suppliers — what is "
                f"the whole vocabulary those suppliers are built on?",
                "harvest", brands[:1], "supplier")
        elif kind == "open":
            keep = ev.get("unbranded_share", 0) >= 1 - C["branded_share_low"]
        elif kind == "direction":
            g = ev.get("last_twelve_months_over_the_twelve_before") or 1.0
            keep = g >= C["growth_up"] or g <= C["growth_down"]
        elif kind == "season":
            keep = ev.get("peak_over_mean", 0) >= C["seasonality"]
        elif kind == "selfserve":
            keep = ev.get("self_serve_share", 0) >= C["self_serve_share"]
        elif kind == "mix":
            keep = max(ev.get("job_mix", {}).values() or [0]) >= \
                C["job_dominance"]
        elif kind == "split":
            top = ev.get("most_searched", {}).get("cpc") or 0.01
            dear = ev.get("dearest_click", {}).get("cpc") or 0.0
            keep = dear / max(top, 0.01) >= C["cpc_spread"]
        elif kind == "cell_price":
            keep = ev.get("ratio", 0) >= C["cell_premium"]
        elif kind == "gradient":
            keep = ev.get("cpc_ratio", 0) >= C["gradient_lift"]
        claim.verdict = "kept" if keep else "below threshold"
        # Rank proxy: how much of the market the claim speaks for.
        claim.weight = K.share(row.get("volume", ev.get("cell_searches", 0)
                                       or ev.get("searches", 0)), total)
    return [c for c in claims if c.survived()]


def order(claims: Sequence[Claim]) -> list[Claim]:
    keepers = [c for c in claims if c.survived()]
    return sorted(keepers, key=lambda c: (-c.weight, c.key))


# --------------------------------------------------------------------------
# Follow-ups: the question each kind of finding raises next
#
# This table is the skill's model of curiosity. Every finding leaves
# something unknown, and for each kind of finding there is one obvious next
# thing a person would go and check. Writing them down makes the loop
# behave like an analyst rather than a batch job — and keeps it working with
# no language model in the loop, because the question is structural even
# though answering it is not.
#
# Which thread gets chased is never decided here. This function only says
# what *could* be asked; Jev decides what is worth paying for.
# --------------------------------------------------------------------------

# Modifiers that probe a specific suspicion, rather than the generic sweep in
# kgraph.UNIVERSAL_FACETS. Each set is the vocabulary a person would reach for
# when chasing that particular oddity.
FACET_SETS: dict[str, tuple[str, ...]] = {
    "money": ("pricing", "cost", "quote", "buy", "demo", "trial",
              "for business", "enterprise", "consultant", "agency",
              "service", "provider", "company", "near me"),
    "diy": ("free", "template", "diy", "how to", "open source", "excel",
            "spreadsheet", "manual", "yourself", "checklist", "example",
            "generator"),
    "choice": ("vs", "alternative", "alternatives", "best", "top",
               "comparison", "review", "reviews", "competitors", "like"),
    "segment": ("for small business", "for enterprise", "for startups",
                "for nonprofits", "for schools", "for contractors",
                "for nurses", "for lawyers", "for restaurants",
                "for landlords", "for freelancers", "for teams"),
    "season": ("2026", "deals", "sale", "black friday", "christmas",
               "summer", "winter", "january", "end of year"),
}


@dataclass
class Thread:
    """One open line of enquiry: a finding, and the probe it suggests.

    A thread is what a person carries in their head as "I should check
    that". It has a parent, so the trail can be read back afterwards, and a
    status, so a run can say honestly what it chased and what it dropped.
    """

    key: str
    question: str
    action: str                     # expand | price | site
    payload: list[str]
    origin: str = ""                # key of the claim that raised it
    depth: int = 0
    status: str = "open"            # open | chasing | paid_off | dead_end
    gain_label: str = ""
    note: str = ""

    @property
    def label(self) -> str:
        return self.question


def _probe_terms(graph: K.Graph, topic: str, facets: Sequence[str],
                 known: set[str], limit: int) -> list[str]:
    """Fill the call.

    A price probe bills the same for one keyword or a thousand, so a probe
    that tests 26 guesses when it could test 900 has wasted nine tenths of
    what was paid for. The suspicion that raised the thread goes first —
    its own topic, crossed with the facets that chase it — and the rest of
    the market's topics fill the remaining slots behind it.
    """
    others = [t for t in graph.confirmed_topics if t != topic]
    ordered = [topic] + sorted(
        others, key=lambda t: -sum(k.volume for k in graph.keywords.values()
                                   if t in k.term))
    wide = list(facets) + [f for f in K.UNIVERSAL_FACETS if f not in facets]
    return K.probe_candidates(ordered, wide, known, limit=limit)


def followups(graph: K.Graph, claims: Sequence[Claim],
              depth: int = 0) -> list[Thread]:
    """The open questions a set of findings leaves behind.

    Only claims that survived adjudication raise threads. Chasing a finding
    Jev has already rejected would be chasing our own noise.
    """
    known = set(graph.keywords)
    out: list[Thread] = []

    def add(claim: Claim, question: str, action: str, payload: Sequence[str],
            tag: str) -> None:
        payload = [p for p in payload if p]
        if not payload:
            return
        out.append(Thread(key=f"{claim.key}->{tag}", question=question,
                          action=action, payload=list(payload),
                          origin=claim.key, depth=depth))

    for claim in claims:
        if not claim.survived():
            continue
        topic = claim.topic or graph.seed
        kind = claim.kind
        ev = claim.evidence

        if kind == "direction":
            movers = (ev.get("rising") or []) + (ev.get("falling") or [])
            seeds = [" ".join(m.split(" ")[:-1]) for m in movers[:4]] or [topic]
            add(claim,
                f"Some parts of this market run against the trend — what is "
                f"inside the ones that do?",
                "expand", [x for x in seeds if x][:K_MAX_SEEDS], "movers")
        elif kind == "pricing_axis":
            add(claim,
                f"If what someone wants is what prices the click, which "
                f"wants have not been measured yet?",
                "price", _probe_terms(
                    graph, topic,
                    FACET_SETS["money"] + FACET_SETS["choice"], known, 900),
                "intents")
        elif kind == "intent":
            odd = ev.get("topics_against_the_grain") or []
            seeds = [o.split(":")[0] for o in odd[:3]] or [topic]
            add(claim,
                f"One part of this market wants something different from "
                f"the rest — what else is in it?",
                "expand", seeds[:K_MAX_SEEDS], "outlier")
        elif kind == "ambiguity":
            # The most valuable probe in the set: the head terms carry the
            # volume and reveal nothing, and the only way to find out what
            # is behind them is to price the ways they could be completed.
            add(claim,
                f"The biggest terms here do not say what the searcher "
                f"wants — what do they turn into when people say more?",
                "price", _probe_terms(
                    graph, topic,
                    FACET_SETS["money"] + FACET_SETS["diy"]
                    + FACET_SETS["choice"], known, 950),
                "resolve")
        elif kind == "settled":
            # Expanding a brand name returns that brand's own keyword
            # universe — its features, its login, its help pages — none of
            # which answer what these buyers want. The question is what
            # people put *next to* the name, so the probe prices the name
            # against the words of choosing and buying.
            brands = ev.get("brands_found") or []
            terms: list[str] = []
            for brand in brands[:8]:
                terms += K.probe_candidates(
                    [brand], list(FACET_SETS["choice"] + FACET_SETS["money"]),
                    known, limit=120)
            add(claim,
                f"These searchers already name their suppliers — are they "
                f"still choosing between them, or going to the one they "
                f"picked?",
                "price", terms[:900], "brands")
        elif kind == "open":
            add(claim,
                f"If nobody owns the words for \u201c{topic}\u201d, what "
                f"words are people reaching for instead?",
                "expand", [topic], "vocabulary")
        elif kind == "split":
            add(claim,
                f"Attention and money came apart here — what else carries a "
                f"price that high?",
                "price", _probe_terms(graph, topic, FACET_SETS["money"],
                                      known, 900), "money")
        elif kind == "head":
            add(claim,
                f"This is the biggest single search in the market — what "
                f"surrounds it?",
                "expand", [ev.get("term", topic)], "head")
        elif kind == "money_seat":
            add(claim,
                f"The spend is concentrated here — what sits next to it "
                f"that nobody has measured?",
                "expand", [topic], "adjacent")
        elif kind == "selfserve":
            add(claim,
                f"People are trying to avoid paying — what exactly are they "
                f"reaching for instead?",
                "price", _probe_terms(graph, topic, FACET_SETS["diy"], known,
                                      900), "diy")
        elif kind == "season":
            add(claim,
                f"The peak is real — does it sit in the buying half of this "
                f"market or the browsing half?",
                "price", _probe_terms(
                    graph, topic,
                    FACET_SETS["season"] + FACET_SETS["money"], known, 900),
                "season")
        elif kind == "substitute":
            others = [ev.get("example", ""), topic]
            add(claim,
                f"If these are one decision, who else is in the comparison "
                f"set?",
                "expand", [o for o in others if o][:K_MAX_SEEDS], "rivals")
        elif kind == "gradient":
            add(claim,
                f"Narrowing the search changed the price — does the lift "
                f"keep going as the audience gets more specific?",
                "price", _probe_terms(graph, topic, FACET_SETS["segment"],
                                      known, 900), "segment")

    # De-duplicate: two findings often raise the same question, and paying
    # twice for one answer is the waste this whole loop exists to avoid.
    seen: set[tuple[str, str]] = set()
    unique: list[Thread] = []
    for thread in out:
        sig = (thread.action, "|".join(sorted(thread.payload))[:400])
        if sig in seen:
            continue
        seen.add(sig)
        unique.append(thread)
    return unique
