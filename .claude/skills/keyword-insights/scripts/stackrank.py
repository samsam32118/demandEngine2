"""Reading the stack: what the searches worth most have in common.

The stack rank is every search in the market with every column, sorted by
what it is worth to a seller (see `Graph.stack`). Practitioners read such a
table top-down, and the first thing they notice is what the top rows share
that the market as a whole does not: they are nearly all services, or all
firms buying for work, or all one topic. That is the insight this module
states, for each column Jev fills.

The top is the *head* — from the top down, the fewest buyers a newcomer
could sell to that carry half of all such buyers' money. What they are
trying to do is not read off it: they are buyers by construction. For each
judged column the value with the largest share of the head's money is
named, against its
share of all the searching in the market; the claim is built only when the
head holds more of it than the market does as printed, and when it is
ahead of the runner-up as printed. Code does those comparisons; whether the
reading holds, and what it is worth, is tested by Jev like every finding.
"""

from __future__ import annotations

from typing import Callable, Sequence

import kgraph as K
from insights import _examples, n, pct
from judge import Claim

# Each column Jev fills, how to read a keyword's value in it (empty when the
# value was held out as not clearly ahead), and how the value reads in a
# sentence.
COLUMNS: dict[str, tuple[Callable[[K.Keyword], str], Callable[[str], str]]] = {
    "offering": (lambda k: k.offering if k.offering_certain else "",
                 lambda v: f"people looking for {K.OFFERING_NOUNS.get(v, v)}"),
    "audience": (lambda k: k.audience if k.audience_certain else "",
                 lambda v: K.AUDIENCE_NOUNS.get(v, v)),
    "topic": (lambda k: k.topic if k.topic and k.topic != "none" else "",
              lambda v: f"searches about “{v}”"),
}


def _shares(keywords: Sequence[K.Keyword], read: Callable[[K.Keyword], str],
            weight: Callable[[K.Keyword], float]) -> dict[str, float]:
    totals: dict[str, float] = {}
    for kw in keywords:
        value = read(kw)
        if value:
            totals[value] = totals.get(value, 0.0) + weight(kw)
    whole = sum(totals.values())
    return {v: t / whole for v, t in totals.items()} if whole > 0 else {}


def column_claim(graph: K.Graph, column: str,
                 head: Sequence[K.Keyword]) -> list[Claim]:
    """What the top of the stack holds far more of, in one column."""
    read, phrase = COLUMNS[column]
    market = [k for k in graph.keywords.values() if k.volume > 0]
    top = _shares(head, read, lambda k: k.money)
    whole = _shares(market, read, lambda k: k.volume)
    if len(top) < 1 or not whole:
        return []
    ranked = sorted(top.items(), key=lambda kv: (-kv[1], kv[0]))
    value, share = ranked[0]
    runner = ranked[1][1] if len(ranked) > 1 else 0.0
    base = whole.get(value, 0.0)
    carriers = [k for k in head if read(k) == value]
    if (len(carriers) < 2 or round(100 * share) <= round(100 * base)
            or round(100 * share) <= round(100 * runner)):
        return []
    who = phrase(value)
    sellable = sum(1 for k in graph.keywords.values() if K.tier(k) == 0)
    text = (f"The top of the stack is {who}: of the {n(len(head))} buying "
            f"searches that carry half the money a newcomer here could reach "
            f"from buyers, {who} take {pct(share)} of it — against "
            f"{pct(base)} of all the searching in this market.")
    return [Claim(
        key=f"market|stack_{column}", kind=f"stack_{column}",
        headline=f"The top of the stack is {who}",
        text=text,
        assertion=(f"Among the buyers most worth selling to here, {who} "
                   f"carry more of the money than any other kind, and a "
                   f"larger share of it than they are of the searching as "
                   f"a whole."),
        forbids=(f"The buyers most worth selling to here look like the "
                 f"market as a whole: {who} are no more common among them "
                 f"than in the searching overall."),
        evidence={"column": column, "top_of_the_stack": value,
                  "share_of_the_top_money": round(share, 3),
                  "share_of_all_searching": round(base, 3),
                  "runner_up_share_of_the_top_money": round(runner, 3),
                  "searches_carrying_half_the_money": len(head),
                  "buyers_a_newcomer_could_sell_to": sellable,
                  "by_value": {v: {"share_of_the_top_money": round(s, 3),
                                   "share_of_all_searching":
                                       round(whole.get(v, 0.0), 3)}
                               for v, s in ranked[:6]},
                  "keywords_this_rests_on": len(graph.certain),
                  "monthly_searches_this_rests_on": graph.certain_volume},
        examples=_examples(sorted(carriers, key=lambda k: -k.money)[:6]),
        topic=value if column == "topic" else "")]


def claims(graph: K.Graph) -> list[Claim]:
    """One reading of the top of the stack per column Jev fills."""
    head = graph.head()
    if len(head) < 2:
        return []
    out: list[Claim] = []
    for column in COLUMNS:
        out += column_claim(graph, column, head)
    return out
