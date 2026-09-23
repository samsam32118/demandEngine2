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

import re
import statistics
from collections import Counter
from dataclasses import dataclass
from typing import Sequence

import kgraph as K
from judge import Claim

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
    "commercial_share_low": 0.10,
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


def money0(value: float) -> str:
    """Whole units, for monthly totals: "$308 a month", not "$308.00"."""
    return f"{_CURRENCY}{value:,.0f}"


def _headline(text: str) -> str:
    """The claim's own opening clause — the point a reader scans for.

    Findings are written "<the point>: <the numbers>", so the point is what
    comes before the first colon, dash, semicolon or full stop, with any
    bracketed figures taken out. Families whose opening clause is not the
    point pass their headline explicitly.
    """
    cuts = [i for i in (text.find(sep) for sep in (": ", " — ", "; ", ". "))
            if i > 0]
    head = text[:min(cuts)] if cuts else text
    return re.sub(r"\s*\([^)]*\)", "", head).strip().rstrip(".")


# --------------------------------------------------------------------------
# Generation
# --------------------------------------------------------------------------

def _offering_contrasts(graph: K.Graph, add) -> None:
    """Contrasts across what people want to end up with. See the comment."""
    # ---- where is the value, by what people want to end up with? --------
    #
    # "The money is in services, not software" was the most useful thing said
    # about `cad to bim`, and it was said by hand after the run: the skill
    # could not see it, because someone shopping for a firm to do the work
    # and someone shopping for a tool to do it themselves were the same
    # searcher to it. The offering axis separates them, and these families
    # state the contrasts a person draws first — where the money is, where
    # the buyers are, where the growth is, where nobody has been picked.
    #
    # Code picks the pair and checks the sentence's own premise holds as
    # printed (it-21: `gradient` and `money_seat` said things their own
    # numbers contradicted). Whether a contrast matters is the tests' call,
    # and where it ranks is the reader question in `judge.rank`. A group
    # needs two searches: one search describes itself, not a group.
    offers = [r for r in graph.offering_rows() if r["keywords"] >= 2]

    def noun(row: dict) -> str:
        return K.OFFERING_NOUNS[row["offering"]]

    def offer_table() -> list[dict]:
        return [{"offering": r["offering"], "searches": r["volume"],
                 # Unrounded, so the table prints what the sentence prints:
                 # rounding to three places first showed 76% under a
                 # sentence that said 77%.
                 "share_of_searching": r["search_share"],
                 "share_of_ad_spend": r["spend_share"],
                 "click_price": r["click_price"],
                 "buying_or_comparing": r["commercial_share"],
                 "names_a_company": r["branded_share"],
                 "shopping_searches": r["buying_volume"],
                 "shoppers_naming_a_company": r["buyers_naming_a_company"],
                 "year_on_year": (r["growth"] if r["growth_readable"]
                                  else None)}
                for r in offers]

    def offer_examples(*picks: tuple[dict, str]) -> list[str]:
        seen: list[K.Keyword] = []
        for row, key in picks:
            for term, _, _ in row[key]:
                kw = graph.keywords.get(term)
                if kw is not None and kw not in seen:
                    seen.append(kw)
        return [f"{k.term} ({n(k.volume)}/mo, {usd(k.cpc)} a click)"
                for k in seen[:6]]

    if len(offers) >= 2:
        # Where a search is worth the most, against where most searching is.
        dear = max(offers, key=lambda r: (r["click_price"], r["volume"]))
        crowd = max((r for r in offers if r is not dear),
                    key=lambda r: (r["volume"], r["offering"]))
        if (dear["click_price"] > crowd["click_price"]
                and usd(dear["click_price"]) != usd(crowd["click_price"])
                and crowd["search_share"] > dear["search_share"]
                and dear["spend_share"] > dear["search_share"]
                and pct(dear["spend_share"]) != pct(dear["search_share"])):
            a, b = noun(dear), noun(crowd)
            ratio = dear["click_price"] / max(crowd["click_price"], 0.01)
            add("market|offer_money",
                f"The money is in {a}, not {b}: people looking for {a} are "
                f"{pct(dear['search_share'])} of the searching but "
                f"{pct(dear['spend_share'])} of the ad spend, at "
                f"{usd(dear['click_price'])} a click — {ratio:.1f}x the "
                f"{usd(crowd['click_price'])} paid for people looking for "
                f"{b}, who are {pct(crowd['search_share'])} of the "
                f"searching.",
                f"Advertisers here pay far more to reach people looking for "
                f"{a} than people looking for {b}, though more of the "
                f"searching is for {b}.",
                f"Advertisers here value people looking for {a} and people "
                f"looking for {b} about the same, and the spend follows the "
                f"searching.",
                {"money_is_in": dear["offering"], "not_in": crowd["offering"],
                 "click_price_ratio": round(ratio, 2),
                 "priciest_terms": [t for t, _, _ in dear["priciest"]],
                 "every_offering": offer_table()},
                offer_examples((dear, "priciest"), (crowd, "largest")),
                "", "offer_money", headline=f"The money is in {a}, not {b}")

        # There is no "the buyers are in A, not B" here, though it was built
        # and measured: someone looking for a firm to do the work is nearly
        # always hiring, and someone looking for information nearly always
        # learning, so the contrast restates how the offering and job axes
        # overlap rather than anything about this market. Fair reading
        # rejected it at 0.30 on `cad to bim` (it-22).

        # Where searching is rising, against where it is falling — only on
        # series that can carry a direction at all (it-20).
        moving = [r for r in offers
                  if r["growth"] is not None and r["growth_readable"]]
        if len(moving) >= 2:
            up = max(moving, key=lambda r: (r["growth"], r["volume"]))
            down = min(moving, key=lambda r: (r["growth"], -r["volume"]))
            if round(up["growth"], 2) >= 1.0 > round(down["growth"], 2):
                a, b = noun(up), noun(down)
                add("market|offer_growth",
                    f"The growth is in {a}, not {b}: searches for {a} ran at "
                    f"{up['growth']:.2f}x the year before, and searches for "
                    f"{b} at {down['growth']:.2f}x.",
                    f"Searching for {a} is rising while searching for {b} "
                    f"is falling.",
                    f"Searching for {a} and searching for {b} are moving the "
                    f"same way.",
                    {"growing": up["offering"], "growing_at": up["growth"],
                     "falling": down["offering"],
                     "falling_at": down["growth"],
                     "every_offering": offer_table()},
                    offer_examples((up, "largest"), (down, "largest")),
                    "", "offer_growth",
                    headline=f"The growth is in {a}, not {b}")

        # Where the people shopping have not picked a supplier, against
        # where they have. "Open ground" means buyers with no supplier in
        # mind, so it is measured among the buyers: brand share over the
        # searches of people buying, comparing or looking for a supplier.
        # Measured over all searching instead, it named information — 4%
        # branded, 1% buying — the open ground of `cad to bim`: unclaimed
        # because unwanted, it-20's mistake at a new level. A premise check
        # that the open side "has buyers as printed" let 1% through; the
        # fix was to measure the thing the sentence is about (it-22).
        shopped = [r for r in offers if r["buying_keywords"] >= 2
                   and r["buyers_naming_a_company"] is not None]
        if len(shopped) >= 2:
            # Against where the shopping is, as the money contrast is set
            # against where the searching is. Picking the most-branded
            # offering instead set services against 200 shopping searches
            # for information, a comparison with nothing behind it.
            free = min(shopped, key=lambda r: (r["buyers_naming_a_company"],
                                               -r["buying_volume"]))
            closed = max((r for r in shopped if r is not free),
                         key=lambda r: (r["buying_volume"], r["offering"]))
            if (closed is not free
                    and closed["buyers_naming_a_company"]
                    > free["buyers_naming_a_company"]
                    and pct(closed["buyers_naming_a_company"])
                    != pct(free["buyers_naming_a_company"])):
                a, b = noun(free), noun(closed)
                add("market|offer_open",
                    f"The open ground is in {a}, not {b}: of the people "
                    f"shopping, {pct(free['buyers_naming_a_company'])} of "
                    f"those looking for {a} name a company, against "
                    f"{pct(closed['buyers_naming_a_company'])} of those "
                    f"looking for {b} ({n(free['buying_volume'])} and "
                    f"{n(closed['buying_volume'])} shopping searches a "
                    f"month).",
                    f"People shopping for {a} have not settled on a "
                    f"supplier, while people shopping for {b} already name "
                    f"theirs.",
                    f"People shopping for {a} and people shopping for {b} "
                    f"are about equally settled on their suppliers.",
                    {"open": free["offering"], "settled": closed["offering"],
                     "least_branded_share": free["buyers_naming_a_company"],
                     "most_branded_share": closed["buyers_naming_a_company"],
                     "every_offering": offer_table()},
                    offer_examples((free, "largest"), (closed, "largest")),
                    "", "offer_open",
                    headline=f"The open ground is in {a}, not {b}")


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
    market_price = graph.market_click_price
    total_money = graph.total_money
    ranked = sorted(by_topic, key=lambda t: -rows.get(t, {}).get("volume", 0))
    top_examples = _examples(by_topic[ranked[0]]) if ranked else []

    # How much searching the whole reading rests on. Carried into every
    # claim's measurements, because a reader — and a judge — cannot tell a
    # fair reading from an overreach without it. Without this, a market of
    # eleven keywords and 1,340 searches a month produced the sentence
    # "this market is shrinking" in exactly the same confident register as
    # one built on two million.
    basis = {"keywords_this_rests_on": len(graph.certain),
             "monthly_searches_this_rests_on": graph.certain_volume}

    def add(key, text, assertion, rival, evidence, examples, topic="",
            kind="", headline=""):
        claims.append(Claim(key=key, text=text, assertion=assertion,
                            forbids=rival, evidence={**evidence, **basis},
                            examples=examples, topic=topic, kind=kind,
                            headline=headline or _headline(text)))

    # The offering axis does not rest on topics, so a market in which no
    # topic was confirmed still gets its contrasts. They used to sit below
    # this return, and the selftest's topic-less fixture found them silent.
    if not by_topic:
        _offering_contrasts(graph, add)
        return claims

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
    # Only series that can carry a direction. A topic whose ratio of sums
    # and ratio of medians disagree about which way the year went is named
    # in the evidence as unreadable — not quoted as an exception at either
    # figure. `seo tips` at "23.01x" was one of those.
    unreadable = [t for t in ranked
                  if rows.get(t, {}).get("growth") is not None
                  and not rows[t].get("growth_readable")]
    trended = [(t, rows[t]["growth"]) for t in ranked
               if rows.get(t, {}).get("growth") is not None
               and rows[t].get("growth_readable")]
    if trended:
        # The median month of each topic, added up across topics — the same
        # defence `K.growth` makes one level down. Summing months here
        # instead would let a single spiked month in one topic set the
        # direction reported for the whole market, which is how this market
        # came to be described as shrinking to 0.41x while the typical month
        # in it was flat.
        recent = sum(statistics.median(K.weighted_trend(by_topic[t])[-12:])
                     for t, _ in trended)
        prior = sum(statistics.median(K.weighted_trend(by_topic[t])[-24:-12])
                    for t, _ in trended)
        overall = (recent / prior) if prior else 1.0
        # Up, down and the exceptions are all decided on the figure as
        # printed. Decided on the raw ratio, 0.996 made "this market is
        # shrinking: … 1.00x the twelve before" the lead finding of the
        # `cad to bim` report, with every exception rising (it-23).
        rising = sorted([x for x in trended if round(x[1], 2) > 1.0],
                        key=lambda x: -x[1])
        falling = sorted([x for x in trended if round(x[1], 2) < 1.0],
                         key=lambda x: x[1])
        up = round(overall, 2) > 1.0
        exceptions = (falling if up else rising)[:3]
        years = max((rows[t]["years_of_history"] for t, _ in trended),
                    default=2)
        # And only when this year's months stand apart from last year's.
        series = [K.weighted_trend(by_topic[t]) for t, _ in trended]
        market = [sum(s[-24:][m] for s in series if len(s) >= 24)
                  for m in range(24)]
        moved = K.shifted(market[:12], market[12:])
    if trended and round(overall, 2) != 1.0 and moved:
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
             "falling": [f"{t} {g:.2f}x" for t, g in falling[:5]],
             "too_erratic_to_read": unreadable[:8]},
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
        # Both sides over the searches placed on the topic. The whole was
        # the searches whose words *contain* the topic's name — a different
        # set from the ones placed on it — and "project management software
        # (121% clear)" went to the judge as a measurement (it-23), the
        # it-21 mistake of two universes in one share.
        placed = {t: sum(k.volume for k in graph.keywords.values()
                         if k.topic == t) for t in ranked[:8]}
        vague = sorted(
            ((t, K.share(sum(k.volume for k in by_topic[t]), placed[t]))
             for t in ranked[:8] if placed[t] > 0),
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
    #
    # Settled is a statement about buyers, so it is measured among the
    # people shopping in each topic, as `offer_open` is. Over all of a
    # topic's searching it was a tautology: a topic that is a definition
    # names no company because nobody is buying anything there, and
    # "“bim software” is settled and “building information management” is
    # not" led the `cad to bim` report — 0% branded, 0% shopping (it-23).
    # A topic needs two shopping searches to be a group of buyers.
    settled = []
    for t, kws in by_topic.items():
        shop = [k for k in kws if k.job in K.BIDDABLE and k.volume > 0]
        vol = sum(k.volume for k in shop)
        if len(shop) >= 2 and vol > 0:
            named = sum(k.volume for k in shop if k.entities)
            settled.append((t, K.share(named, vol), vol))
    if settled:
        most = max(settled, key=lambda x: (x[1], x[2]))
        least = min(settled, key=lambda x: (x[1], -x[2]))
        all_brands = sorted({e for k in graph.certain for e in k.entities})
        # "Settled" is a majority of the shoppers naming a company, and
        # "not" is fewer than half — the same majority every test here is
        # won by. On the AnswerThePublic space the pair was 3% against 0%,
        # and "keyword tool is settled" led the report (it-23).
        if (most[0] != least[0] and round(100 * most[1]) > 50
                and round(100 * least[1]) < 50):
            add("market|settled",
                f"\u201c{most[0]}\u201d is settled and "
                f"\u201c{least[0]}\u201d is not: {pct(most[1])} of the "
                f"people shopping for \u201c{most[0]}\u201d name a company "
                f"outright, against {pct(least[1])} of those shopping for "
                f"\u201c{least[0]}\u201d ({n(least[2])} shopping searches "
                f"a month).",
                f"Buyers have settled on who supplies \u201c{most[0]}\u201d "
                f"but not \u201c{least[0]}\u201d — the same market is "
                f"closed in one place and open in another.",
                f"Buyers are about equally settled on who supplies every "
                f"part of this market.",
                {"most_branded": {"topic": most[0],
                                  "shoppers_naming_a_company": round(
                                      most[1], 3),
                                  "shopping_searches": most[2]},
                 "least_branded": {"topic": least[0],
                                   "shoppers_naming_a_company": round(
                                       least[1], 3),
                                   "shopping_searches": least[2]},
                 "brands_found": all_brands[:10]},
                _examples([k for k in by_topic[least[0]]
                           if k.job in K.BIDDABLE]), least[0], "settled")

    # ---- where does nobody name a company? ------------------------------
    unbranded = [(t, rows[t]["branded_share"], rows[t]["volume"])
                 for t in by_topic if t in rows and rows[t]["volume"] > 0]
    if len(unbranded) >= 2:
        least = min(unbranded, key=lambda x: (x[1], -x[2]))
        # Unbranded is not the same as open. On answerthepublic.com the
        # least branded topic was "keywords" — 267,160 searches a month,
        # nobody's name on it — and 2% of those searches were anyone buying
        # or comparing; the rest were people learning what a keyword is.
        # "The open ground is keywords" was the lead finding and it was
        # backwards. So the share that is there to buy goes into the
        # sentence, the rival account is the one that actually competes
        # with it, and the mirror-image claim is built beside it so that
        # the account test decides which reading the data supports.
        com = rows.get(least[0], {}).get("commercial_share", 0.0)
        # Evidence about the subject, not the market. "Name no company at
        # all" judged next to the market's own brand list — asana, jira,
        # smartsheet — read as contradicted by it: measured fresh on
        # `pmo software` (unbranded 1.0, commercial 1.0), fair-reading
        # went 0.31-0.37 with the market list to 0.45-0.46 without. Not
        # enough on its own to clear 0.5 there, and still the right
        # evidence to show.
        own_brands = sorted({e for k in by_topic[least[0]] for e in k.entities})
        # Which of the pair is built is a comparison, so code makes it: the
        # topic's share buying against the market's own. The account test
        # was left to choose between them and chose "open ground" at 0.78
        # for "building information management" — 0% of it buying (it-23).
        # The pair keeps its mirror as the rival; only one side is said.
        certain_shop = sum(k.volume for k in graph.certain
                           if k.job in K.BIDDABLE)
        market_com = K.share(certain_shop, max(graph.certain_volume, 1))
        is_open = com > 0 and round(100 * com) >= round(100 * market_com)
    if len(unbranded) >= 2 and is_open:
        add("market|open",
            f"The open ground is \u201c{least[0]}\u201d: "
            f"{pct(1 - least[1])} of its {n(least[2])} monthly searches name "
            f"no company at all, and {pct(com)} of them are buying, "
            f"comparing or looking for a supplier.",
            f"There is a part of this market — \u201c{least[0]}\u201d — "
            f"where buyers have no supplier in mind when they search, and "
            f"a real share of them are there to buy.",
            f"The part of this market with the fewest company names — "
            f"\u201c{least[0]}\u201d — has almost nobody in it looking to "
            f"buy: there is no one there to sell to.",
            {"topic": least[0], "unbranded_share": round(1 - least[1], 3),
             "commercial_share": round(com, 3),
             "searches": least[2], "brands_in_topic": own_brands[:10],
             "market_commercial_share": round(market_com, 3)},
            _examples(by_topic[least[0]]), least[0], "open")
    if len(unbranded) >= 2 and not is_open:
        # The assertion states the conjunction and nothing more. A first
        # draft said "unbranded *because* there is nothing to sell there",
        # and fair-reading killed it on every corpus (0.17-0.48) while the
        # account test was picking its side — correctly: a mechanism is
        # not a measurement, and the test does not care whose sentence it
        # is.
        add("market|empty",
            f"\u201c{least[0]}\u201d is unclaimed, and there is almost "
            f"nobody there to sell to: {pct(1 - least[1])} of its "
            f"{n(least[2])} monthly searches name no company, and "
            f"{'only ' if com > 0 else ''}{pct(com)} of them are buying or "
            f"comparing — the rest are reading.",
            f"The part of this market with the fewest company names in its "
            f"searches — \u201c{least[0]}\u201d — is also where the fewest "
            f"people are looking to buy: it is unclaimed, and almost nobody "
            f"searching it is shopping.",
            f"The part of this market with the fewest company names — "
            f"\u201c{least[0]}\u201d — is open ground: the people "
            f"searching it are shopping and simply have no supplier in "
            f"mind yet.",
            {"topic": least[0], "unbranded_share": round(1 - least[1], 3),
             "commercial_share": round(com, 3),
             "searches": least[2], "brands_in_topic": own_brands[:10],
             "market_commercial_share": round(market_com, 3)},
            _examples(by_topic[least[0]]), least[0], "empty")

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

    # Both shares over the same searches, and the cell named is the one
    # whose spend runs furthest ahead of its searching.
    #
    # Spend used to be divided by the money in *every* keyword — including
    # the head terms held out because their intent could not be read —
    # while searching was divided by the readable ones only. Every spend
    # share came out small, and across every run on disk 43 of 51 of these
    # claims said "the money is concentrated" over numbers saying the
    # opposite: `cad to bim` put 27% of the searching against 21% of the
    # spend. Selection was the other half of it: the cell with the most
    # money is usually just the biggest cell, whose spend is in proportion
    # almost by construction. The claim is about money out of proportion,
    # so it is made only where some cell's share of spend exceeds its
    # share of searching — a sign, which is arithmetic — and whether the
    # gap matters is left to the tests.
    cells = graph.cells(min_keywords=1)
    certain_money = sum(k.money for k in graph.certain)
    richest = None
    if cells and certain_money > 0:
        def excess(c: K.Cell) -> float:
            return (K.share(c.money, certain_money)
                    - K.share(c.volume, certain_vol))
        richest = max(cells, key=lambda c: (excess(c), c.money))
        # And the gap has to show in the sentence as printed: a cell at
        # 0.1% of the searching and 0.1% of the spend is "out of
        # proportion" in the fourth decimal and reads "0% of the searching
        # but 0% of the spend".
        if pct(K.share(richest.money, certain_money)) == \
                pct(K.share(richest.volume, certain_vol)) or excess(richest) <= 0:
            richest = None
    if richest is not None:
        label = K.JOB_LABELS.get(richest.job, richest.job)
        add("market|money_seat",
            f"The money is concentrated: people searching "
            f"\u201c{richest.topic}\u201d while {label} are "
            f"{pct(K.share(richest.volume, certain_vol))} of the searching "
            f"but {pct(K.share(richest.money, certain_money))} of all the ad "
            f"spend these searches imply.",
            f"Advertiser spending in this market is concentrated on one kind "
            f"of searcher, out of proportion to how much they search.",
            f"Advertiser spending in this market is spread roughly in "
            f"proportion to how much each part of it is searched.",
            {"cell": f"{richest.topic} / {richest.job}",
             "share_of_searching": round(
                 K.share(richest.volume, certain_vol), 3),
             "share_of_implied_spend": round(
                 K.share(richest.money, certain_money), 3)},
            _examples(richest.keywords), richest.topic, "money_seat")

    # ---- is the free route the real competitor? -------------------------
    #
    # "The competitor is doing without" is a comparison, so code makes it:
    # more of the searching must be people doing it themselves than people
    # shopping. Asked of 6% self-serve against 9% shopping, the account
    # test picked "a substantial part of the demand is avoiding paying" at
    # 0.83 — a magnitude, which Jev cannot judge (it-23).
    ss_vol = mix_total.get("self_serve", 0)
    shop_vol = sum(mix_total.get(j, 0) for j in K.BIDDABLE)
    if ss_vol and ss_vol > shop_vol:
        worst = max(ranked, key=lambda t: rows[t]["job_mix"].get(
            "self_serve", 0.0))
        ss_kws = by_job.get("self_serve", [])
        add("market|selfserve",
            f"The competitor here is not a company but doing without: "
            f"{pct(K.share(ss_vol, certain_vol))} of the searching with a "
            f"clear intent is people trying to solve it without buying "
            f"anything — more than the {pct(K.share(shop_vol, certain_vol))} "
            f"who are shopping — heaviest in \u201c{worst}\u201d at "
            f"{pct(rows[worst]['job_mix'].get('self_serve', 0))}.",
            f"A substantial part of the demand in this market is people "
            f"looking for a way to avoid paying anyone for it.",
            f"People in this market accept that solving the problem means "
            f"paying somebody for it.",
            {"self_serve_share": round(K.share(ss_vol, certain_vol), 3),
             "shopping_share": round(K.share(shop_vol, certain_vol), 3),
             "heaviest_topic": worst,
             "heaviest_share": round(
                 rows[worst]["job_mix"].get("self_serve", 0), 3),
             "click_price_of_self_serve": round(K.click_price(ss_kws), 2)},
            _examples(ss_kws), worst, "selfserve")

    _offering_contrasts(graph, add)

    # ---- which topic is the growth moving to? ---------------------------
    #
    # `direction` says which way the market is going and lists exceptions;
    # this names the contrast a person acts on: the biggest topic that is
    # rising against the biggest one that is falling. On the AnswerThePublic
    # space that was "tools for seo" at 1.40x against "keyword research
    # tools" at 0.38x — the same product, and only one of its names is
    # dying. Found by hand, like the services contrast.
    readable = [t for t in ranked if rows.get(t, {}).get("growth") is not None
                and rows[t].get("growth_readable")]
    rising = [t for t in readable if round(rows[t]["growth"], 2) >= 1.0]
    falling = [t for t in readable if round(rows[t]["growth"], 2) < 1.0]
    if rising and falling:
        ta = max(rising, key=lambda t: (rows[t]["volume"], t))
        tb = max(falling, key=lambda t: (rows[t]["volume"], t))
        ra, rb = rows[ta], rows[tb]
        add("market|topic_growth",
            f"The growth is in \u201c{ta}\u201d, not \u201c{tb}\u201d: "
            f"searching for \u201c{ta}\u201d ({n(ra['volume'])} a month) ran "
            f"at {ra['growth']:.2f}x the year before, and for "
            f"\u201c{tb}\u201d ({n(rb['volume'])} a month) at "
            f"{rb['growth']:.2f}x.",
            f"Searching for \u201c{ta}\u201d is rising while searching for "
            f"\u201c{tb}\u201d is falling.",
            f"Searching for \u201c{ta}\u201d and for \u201c{tb}\u201d moves "
            f"together.",
            {"growing": {"topic": ta, "searches": ra["volume"],
                         "year_on_year": ra["growth"]},
             "falling": {"topic": tb, "searches": rb["volume"],
                         "year_on_year": rb["growth"]},
             "also_rising": [f"{t} {rows[t]['growth']:.2f}x"
                             for t in rising if t != ta][:4],
             "also_falling": [f"{t} {rows[t]['growth']:.2f}x"
                              for t in falling if t != tb][:4]},
            _examples(sorted(by_topic[ta], key=lambda k: -k.volume)[:3]
                      + sorted(by_topic[tb], key=lambda k: -k.volume)[:3]),
            ta, "topic_growth",
            headline=f"The growth is in \u201c{ta}\u201d, not "
                     f"\u201c{tb}\u201d")

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
    # A narrowing is searched less than what it narrows; see
    # `Graph.sharpest_narrowing` for the inverted pair that made this rule.
    best = graph.sharpest_narrowing()
    if best:
        lift, bare, kw = best
        facet = kw.term.replace(bare.term, "").strip()
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
            # Both halves have to hold for the sentence to mean anything:
            # one part of the market named as settled, another named as
            # open. A gap between two middling shares is not a finding.
            keep = (ev.get("most_branded", {}).get(
                        "shoppers_naming_a_company", 0.0)
                    >= C["branded_share_high"]
                    and ev.get("least_branded", {}).get(
                        "shoppers_naming_a_company", 1.0)
                    <= C["branded_share_low"])
        elif kind == "open":
            keep = ev.get("unbranded_share", 0) >= 1 - C["branded_share_low"]
        elif kind == "empty":
            keep = (ev.get("unbranded_share", 0) >= 1 - C["branded_share_low"]
                    and ev.get("commercial_share", 1.0)
                    <= C["commercial_share_low"])
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
        elif kind == "offer_money":
            keep = ev.get("click_price_ratio", 0) >= C["cpc_spread"]
        elif kind == "offer_growth":
            keep = (ev.get("growing_at", 1.0) >= C["growth_up"]
                    or ev.get("falling_at", 1.0) <= C["growth_down"])
        elif kind == "topic_growth":
            keep = (ev.get("growing", {}).get("year_on_year", 1.0)
                    >= C["growth_up"]
                    or ev.get("falling", {}).get("year_on_year", 1.0)
                    <= C["growth_down"])
        elif kind == "offer_open":
            keep = (ev.get("most_branded_share", 0.0) >= C["branded_share_high"]
                    and ev.get("least_branded_share", 1.0)
                    <= C["branded_share_low"])
        # The where-to-win families have no hand-tuned threshold to hold
        # them to: each is only built when code has checked its own premise,
        # so this arm keeps them as built.
        claim.verdict = "kept" if keep else "below threshold"
        # Rank proxy: how much of the market the claim speaks for. Several
        # families carry a list under "searches", so only a number counts.
        size = row.get("volume")
        if size is None:
            size = next((ev[k] for k in ("cell_searches", "searches",
                                         "buyer_searches_a_month",
                                         "searches_a_month",
                                         "shopping_searches")
                         if isinstance(ev.get(k), (int, float))), 0)
        claim.weight = K.share(size, total)
    return [c for c in claims if c.survived()]


def order(claims: Sequence[Claim]) -> list[Claim]:
    keepers = [c for c in claims if c.survived()]
    return sorted(keepers, key=lambda c: (-c.weight, c.key))


# --------------------------------------------------------------------------
# The trail: each step of the graph search, as it happened
# --------------------------------------------------------------------------

@dataclass
class Thread:
    """One step of the graph search: which searches were expanded, at what
    depth, and what came back — kept so a run can say honestly where it
    went and where the trail went cold."""

    key: str
    question: str
    action: str                     # expand
    payload: list[str]              # the searches expanded
    origin: str = ""
    depth: int = 0
    status: str = "open"            # chasing | paid_off | dead_end | unfunded
    gain_label: str = ""
    note: str = ""

    @property
    def label(self) -> str:
        return self.question
