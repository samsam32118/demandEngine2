"""The deliverable: the insights, most valuable first — and the data, beside it.

The report is one thing. Every finding that survived testing, ranked by the
judgment model's answer to "which of these would change what the reader does
the most?", each led by its point in a few words, then the numbers, then the
searches it rests on. When nothing survived, it says so and stops: padding a
report with the statements that failed would be the same mistake as hiding
them, made in the other direction.

Everything else is written beside it as files, because the report's job is
to say what matters and the files' job is to let anyone check it: every
keyword with its three axes, every topic and kind of offering, every
statement tested with each test's score and why it fell, every probe bought
or declined, the market network, the forecast, and the run itself. What used
to be sections of the report — the trail, the rejections, the shape of the
market, the network's conclusions — are rows in those files now.
"""

from __future__ import annotations

import csv
import datetime as _dt
import json
import os
from dataclasses import asdict
from typing import Sequence

import insights
import judge
import market_net as MN
import kgraph as K
import opportunity as O

n, usd, pct, money0 = insights.n, insights.usd, insights.pct, insights.money0

# Why a statement fell, in words, for `tested.csv`.
REJECTION_GLOSS = {
    "kept": "survived every test",
    "misread": "the numbers were right but the reading of them was not",
    "the data supports the opposite": "the rival account fits the "
                                      "measurements better",
    "the data does not settle it": "the measurements do not choose between "
                                   "it and its rival",
    "would fit any market": "it survived having its subject swapped for an "
                            "unrelated one, so it was never about this market",
    "knowable without data": "it follows from the market's name alone",
    "changes nothing": "true, specific, and of no consequence to the reader",
    "background": "true and specific, but more likely to fill in the picture "
                  "than to change a decision",
    "below threshold": "a measured value did not clear the control arm's "
                       "cut-off",
}

# Evidence worth showing under an insight, when present, and what to call
# it. Everything else in `evidence` is in `tested.csv`.
DETAIL_KEYS = {
    "rising": "Rising", "falling": "Falling",
    "also_rising": "Also rising", "also_falling": "Also falling",
    "too_erratic_to_read": "Too erratic to read",
    "topics_against_the_grain": "Against the grain",
    "brands_in_topic": "Companies named",
}

# Each offering insight shows the columns it is about, and no others: the
# same five-column table printed under three insights said nothing new the
# second and third time.
OFFERING_COLUMNS = {
    "offer_money": (("searches", "searches/mo"),
                    ("share_of_searching", "of the searching"),
                    ("share_of_ad_spend", "of the ad spend"),
                    ("click_price", "click price")),
    "offer_growth": (("searches", "searches/mo"),
                     ("year_on_year", "year on year")),
    "offer_open": (("shopping_searches", "shopping searches/mo"),
                   ("shoppers_naming_a_company", "of them naming a company")),
}


def data_dir_for(report_path: str) -> str:
    """Where a report's data goes: beside it, named after it."""
    return os.path.splitext(report_path)[0] + "-data"


# --------------------------------------------------------------------------
# The report
# --------------------------------------------------------------------------

def render(graph: K.Graph, claims: Sequence[judge.Claim], trail: Sequence,
           manifest: dict, data_dir: str = "data",
           extra: dict | None = None) -> str:
    arm = manifest.get("arm", "jev")
    kept = insights.order(claims)
    today = _dt.date.today().isoformat()
    total = max(graph.total_volume, 1)
    readable = K.share(graph.certain_volume, total)
    folder = os.path.basename(data_dir.rstrip("/")) or data_dir

    L: list[str] = [f"# Insights · “{graph.seed}”", ""]
    L.append(" · ".join(x for x in (
        graph.geo or "United States", today,
        f"effort {manifest.get('effort', '')}".strip()) if x))
    L.append("")
    L.append(f"{n(len(graph.keywords))} searches measured, carrying "
             f"{n(graph.total_volume)} a month; what the person wanted was "
             f"readable for {pct(readable)} of that searching.")
    L += _paid_line(manifest.get("forecast"))
    L += _money_line((extra or {}).get("opportunities"), folder)
    L.append("")
    L += _stack_table(graph, folder)

    if kept:
        rest = len(claims) - len(kept)
        who = manifest.get("asker") or "the reader"
        order_note = ("ranked by the judgment model's answer to “which "
                      f"of these would change what {who} does the most?”"
                      if arm != "code" else
                      "ranked by how much of the market each speaks for "
                      "(threshold arm)")
        L.append(f"**{len(kept)} insight{'s' if len(kept) != 1 else ''}, "
                 f"most valuable first** — {order_note}. "
                 f"{rest} other statement{'s' if rest != 1 else ''} the data "
                 f"could support {'were' if rest != 1 else 'was'} tested and "
                 f"did not hold; each is in `{folder}/tested.csv` with the "
                 f"reason.")
        L.append("")
        for i, claim in enumerate(kept, 1):
            L += _insight(i, claim, arm)
    else:
        L.append("## No insights")
        L.append("")
        if claims:
            L.append(f"None of the {len(claims)} statement"
                     f"{'s' if len(claims) != 1 else ''} this data could "
                     f"support survived testing — each is in "
                     f"`{folder}/tested.csv` with the reason it fell. That is "
                     f"a result, not a failure: nothing the searching here "
                     f"shows would change a decision.")
        else:
            L.append("There was nothing to test: too little searching was "
                     "found to support any statement at all.")
        L.append("")

    L += _footer(graph, claims, manifest, folder, extra or {})
    return "\n".join(L).rstrip() + "\n"


def _paid_line(fc: dict | None) -> list[str]:
    """What paid search can buy here — a measurement, stated as one.

    It was briefly built as a pair of findings for the tests to choose
    between, "a small channel" or "a large one". With no reference to hold
    the number against that is a question about magnitude, which the
    judgment model cannot answer: it called $273 a month the large channel.
    A forecast is a fact, so it is reported as one; the comparison is made
    only against a number the reader supplied (it-22).
    """
    if not fc or not fc.get("clicks"):
        return []
    line = (f"All of paid search here: **{money0(fc['cost'])} a month** buys "
            f"every click worth having — {n(fc['clicks'])} clicks at "
            f"{usd(fc['cpc'])}, from the {n(fc.get('keywords') or 0)} "
            f"searches worth bidding on.")
    budget = fc.get("budget")
    if budget and fc.get("cost"):
        if budget > fc["cost"]:
            line += (f" Your {money0(budget)} is {budget / fc['cost']:.1f}x "
                     f"what that can absorb.")
        else:
            line += (f" Your {money0(budget)} buys about "
                     f"{pct(budget / fc['cost'])} of it.")
    return [line]


def _money_line(groups, folder: str) -> list[str]:
    """Where the most buyer money a newcomer could answer sits — stated, as
    the paid line is, because it is a measurement.

    Whether that is the place to *start* is a judgment, and it is tested
    as the `start_here` finding: on `cad to bim` the answer was a coin flip
    — the most money, behind a first page of specialist firms, falling to
    0.64x — and it did not survive. The measurement stands either way, and
    the reader should not have to open a file to see it (it-23).
    """
    cands = O.candidates(groups or [])
    if not cands:
        return []
    top = max(cands, key=lambda c: (c.open_prize, c.anchor.term))
    kd = (f", difficulty {top.difficulty:.0f} of 100"
          if top.difficulty is not None else "")
    grow = (f", {top.growth:.2f}x the year before"
            if top.growth is not None else "")
    return [f"Where the buyer money is: **“{top.anchor.term}”** carries the "
            f"most a newcomer could answer — {money0(top.open_prize)} a month "
            f"of clicks across {n(len(top.keywords))} "
            f"search{'es' if len(top.keywords) != 1 else ''} Google answers "
            f"with the same pages{kd}{grow}; page one is "
            f"{O.page_one_words(top)}. All {n(len(cands))} groups are in "
            f"`{folder}/opportunities.csv`."]


# How many rows of each tier the report shows. The file has every row.
STACK_ROWS = 10
NEXT_ROWS = 5
TIERS = ("a newcomer could sell to, and buying",
         "a newcomer could sell to", "other")


def _stack_table(graph: K.Graph, folder: str) -> list[str]:
    """The top of the stack rank, as a table: the buyers most worth selling
    to, then the people a newcomer could sell to who are not buying yet —
    each row with the columns Jev and DataForSEO filled."""
    stack = graph.stack()
    buyers = [k for k in stack if K.tier(k) == 0]
    others = [k for k in stack if K.tier(k) == 1]
    if not buyers and not others:
        return []
    head = graph.head()
    bought = sum(k.money for k in buyers)
    waiting = sum(k.money for k in others)

    def read(value, certain, names):
        return names.get(value, value) if value and certain else "—"

    def row(kw) -> str:
        g = K.growth(kw.trend) if K.growth_readable(kw.trend) else None
        return (f"| {kw.rank} | {kw.term} | {n(kw.volume)} | "
                f"{money0(kw.money)} | {usd(kw.cpc)} | "
                f"{'—' if kw.difficulty is None else kw.difficulty} | "
                f"{'—' if g is None else f'{g:.2f}x'} | "
                f"{read(kw.job, kw.job_certain, K.JOB_LABELS)} | "
                f"{read(kw.offering, kw.offering_certain, K.OFFERING_NOUNS)} | "
                f"{read(kw.audience, kw.audience_certain, K.AUDIENCE_NOUNS)} |")
    header = ["| # | search | searches/mo | worth/mo | click | difficulty | "
              "year on year | trying to | wants | who |",
              "|---:|---|---:|---:|---:|---:|---:|---|---|---|"]
    rows = ["**The top of the stack** — every search ranked: people a "
            "newcomer could sell to who are buying first, then the rest a "
            "newcomer could sell to, then everyone else, each by the money in "
            f"its clicks. All {n(len(stack))}, every column, are in "
            f"`{folder}/keywords.csv`.", ""]
    if buyers:
        rows += [f"Buyers a newcomer could sell to: {n(len(buyers))} searches "
                 f"worth {money0(bought)} a month; half of it is in the top "
                 f"{n(len(head))}.", ""] + header
        rows += [row(k) for k in buyers[:STACK_ROWS]] + [""]
    if others:
        more = (" — more than every buyer above put together"
                if waiting > bought else "")
        rows += [f"Next: people a newcomer could sell to who are not buying "
                 f"yet — {n(len(others))} searches worth {money0(waiting)} a "
                 f"month{more}.", ""] + header
        rows += [row(k) for k in others[:NEXT_ROWS]] + [""]
    return rows


def _insight(i: int, claim: judge.Claim, arm: str) -> list[str]:
    L = [f"## {i}. {claim.headline or claim.text}", "", claim.text, ""]
    offers = claim.evidence.get("every_offering")
    if offers and claim.kind in OFFERING_COLUMNS:
        L += _offering_table(offers, OFFERING_COLUMNS[claim.kind])
    growing, falling = (claim.evidence.get("growing"),
                        claim.evidence.get("falling"))
    if isinstance(growing, dict) and isinstance(falling, dict):
        L += ["| topic | searches/mo | year on year |", "|---|---:|---:|",
              f"| {growing['topic']} | {n(growing['searches'])} | "
              f"{growing['year_on_year']:.2f}x |",
              f"| {falling['topic']} | {n(falling['searches'])} | "
              f"{falling['year_on_year']:.2f}x |", ""]
    L += _opportunity_table(claim)
    details = []
    for key, label in DETAIL_KEYS.items():
        value = claim.evidence.get(key)
        if isinstance(value, list) and value:
            details.append(f"{label}: {', '.join(str(v) for v in value[:6])}")
    if details:
        L += [" · ".join(details), ""]
    if claim.examples:
        L += ["Behind it: " + " · ".join(f"`{e}`" for e in claim.examples[:4]),
              ""]
    why = claim.evidence.get("frame") or O.frame(claim.kind)
    if why:
        L += [f"*Why it matters — {why}*", ""]
    L += [_scores(claim, arm), ""]
    return L


# What each kind of opportunity finding shows beneath its sentence: the
# rows the sentence was chosen from, so a reader can see the runners-up and
# the evidence for the pick without opening a file.
KIND_NAMES = {"specialist": "specialist firms", "major_brand": "household names",
              "list": "directories and review sites",
              "publication": "articles and guides",
              "community": "forum, social and press pages",
              "off_target": "off-target pages"}


def _opportunity_table(claim: judge.Claim) -> list[str]:
    ev = claim.evidence
    if claim.kind in ("start_here", "open_door"):
        rows = [ev] + list(ev.get("next") or [])
        out = []
        if claim.kind == "start_here":
            out = ["| start with | searches | buyer searches/mo | buyer "
                   "clicks worth/mo | naming no company | difficulty | "
                   "page-one clicks to weak pages |",
                   "|---|---:|---:|---:|---:|---:|---:|"]
            for r in rows:
                kd = r.get("difficulty")
                out.append(f"| {r['start_with']} | {r['searches']} | "
                           f"{n(r['buyer_searches_a_month'])} | "
                           f"{money0(r['prize_a_month'])} | "
                           f"{money0(r['naming_no_company_a_month'])} | "
                           f"{'—' if kd is None else f'{kd:.0f}'} | "
                           f"{pct(r['clicks_to_weak_pages'])} |")
            out.append("")
        page = ev.get("page_one_detail") or []
        if page:
            out.append("Page one for “" + ev["start_with"] + "”: "
                       + " · ".join(f"{r['rank']}. {r['domain']} "
                                    f"({KIND_NAMES.get(r['kind'], r['kind'] or '?')})"
                                    for r in page))
        return out + [""]
    if claim.kind == "who_answers":
        split = ev.get("clicks_by_kind") or {}
        if not split:
            return []
        return (["| what holds page one | share of buyers' page-one clicks |",
                 "|---|---:|"]
                + [f"| {k} | {pct(v)} |" for k, v in split.items()] + [""])
    if claim.kind == "customer_cost" and len(ev.get("by_offering") or []) >= 2:
        return (["| wants | buying searches/mo | average click | cost of a "
                 "lead |", "|---|---:|---:|---:|"]
                + [f"| {K.OFFERING_NOUNS.get(r['offering'], r['offering'])} | "
                   f"{n(r['buyer_searches_a_month'])} | "
                   f"{usd(r['average_click'])} | "
                   f"{money0(r['cost_per_lead'])} |"
                   for r in ev["by_offering"]] + [""])
    if claim.kind in ("who_owns", "who_owns_not"):
        firms = ev.get("businesses") or []
        if not firms:
            return []
        return (["| business | share of buyer clicks |", "|---|---:|"]
                + [f"| {f['domain']} | {pct(f['share'])} |" for f in firms[:6]]
                + [""])
    return []


def _offering_table(rows: Sequence[dict],
                    columns: Sequence[tuple[str, str]]) -> list[str]:
    def cell(key: str, value) -> str:
        if value is None:
            return "\u2014"
        if key == "click_price":
            return usd(value)
        if key == "year_on_year":
            return f"{value:.2f}x"
        if key in ("searches", "shopping_searches"):
            return n(value)
        return pct(value)
    out = ["| wants | " + " | ".join(label for _, label in columns) + " |",
           "|---|" + "---:|" * len(columns)]
    for r in rows:
        out.append(f"| {K.OFFERING_NOUNS.get(r['offering'], r['offering'])} | "
                   + " | ".join(cell(k, r.get(k)) for k, _ in columns) + " |")
    return out + [""]


def _scores(claim: judge.Claim, arm: str) -> str:
    if arm == "code":
        return "<sub>Kept by the threshold arm.</sub>"
    return (f"<sub>Worth to the reader: {claim.stakes_label or '—'} "
            f"({pct(claim.decides)} likely to change a decision) · "
            f"value weight {claim.weight:.2f} · holds up: fair "
            f"reading {claim.reads_true:.2f}, beats its rival "
            f"{claim.account_p:.2f}, specific to this market "
            f"{1 - claim.swappable:.2f}, not guessable "
            f"{1 - claim.obvious:.2f}</sub>")


def _footer(graph: K.Graph, claims: Sequence[judge.Claim], manifest: dict,
            folder: str, extra: dict) -> list[str]:
    rows = graph.topic_rows()
    erratic = [r["topic"] for r in rows
               if r.get("growth") is not None and not r.get("growth_readable")]
    series_rows = sum(len(k.trend) for k in graph.keywords.values())
    files = [
        ("keywords.csv", "the stack rank: every search, most worth selling "
         "to first — whether a seller here could sell to it and how surely, "
         "volume, click price, what it is worth, difficulty, year on year, "
         "what it is about, what the person is trying to do, what kind of "
         "answer, who is searching, companies named, where the graph search "
         "found it", len(graph.keywords)),
        ("offerings.csv", "each kind of answer people want — a service, "
         "software, a product, information — and what it is worth",
         len(graph.offering_rows())),
        ("topics.csv", "each thing people search about, and what it is worth",
         len(rows)),
        ("tested.csv", "every statement the data could support, each test's "
         "score, the verdict and why", len(claims)),
        ("series.csv", "searches a month for every keyword, month by month",
         series_rows),
        ("trail.csv", "every question the loop chased — what it bought, what "
         "came back", len(manifest.get("trail") or [])),
        ("opportunities.csv", "each group of buying searches one page could "
         "answer — what it is worth, how hard, and what holds its first page",
         len(extra.get("opportunities") or [])),
        ("page_one.csv", "every first page read — each result, what kind of "
         "page it is, and whether the search stayed in the market",
         sum(len(_organic(rows)) for rows in
             (extra.get("pages") or {}).values())),
        ("share_of_voice.csv", "which sites take the clicks the buying "
         "searches send", len(extra.get("shares") or [])),
        ("network.json", "the market network: what it believed before "
         "measuring, after, and what moved it", None),
        ("forecast.json", "Google's forecast for the searches worth bidding on",
         None),
        ("run.json", "seed, effort, reader, and what every stage cost", None),
    ]
    L = ["---", "", f"**The data** — in `{folder}/`:", "",
         "| file | what is in it | rows |", "|---|---|---:|"]
    for name, what, count in files:
        L.append(f"| `{name}` | {what} | "
                 f"{n(count) if count is not None else '—'} |")
    L.append("")
    note = (f"**About the numbers.** Search volumes and click prices are Google "
            f"Ads figures for {graph.geo or 'the United States'}, from "
            f"DataForSEO. Its responses carry no currency, and it documents "
            f"them as US dollars, so they are shown with "
            f"`{manifest.get('currency') or '$'}`; convert before budgeting "
            f"in another. A topic or a kind of offering is a reading of this "
            f"run's searches, not a fixed property of a phrase — the keyword "
            f"series underneath are.")
    if erratic:
        named = ", ".join(f"“{t}”" for t in erratic[:4])
        note += (f" {len(erratic)} topic{'s were' if len(erratic) != 1 else ' was'}"
                 f" left out of every statement about direction ({named}"
                 f"{' and others' if len(erratic) > 4 else ''}): "
                 f"{'their' if len(erratic) != 1 else 'its'} monthly figures "
                 f"swing so widely that the year's total and the median month "
                 f"disagree about which way it went.")
    L += [note, ""]
    seo_led, jev_led = manifest.get("dataforseo") or {}, manifest.get("jev") or {}
    L.append(
        f"Every sentence above was assembled by code from those numbers; every "
        f"judgment — what a search is about, what the person wants, what "
        f"kind of answer, whether a statement holds, what it is worth — was "
        f"made by TypeSafe's Jev. No language model wrote any of it. "
        f"Cost: ${seo_led.get('spent_usd', 0):.2f} of search data, "
        f"${jev_led.get('usd', 0):.4f} of judgment"
        + (f", {manifest['seconds']:.0f}s" if manifest.get("seconds") else "")
        + ".")
    return L


# --------------------------------------------------------------------------
# The data
# --------------------------------------------------------------------------

def _organic(rows) -> list[dict]:
    import serp as S
    return S.organic_rows(rows or [])


def write_data(folder: str, graph: K.Graph, claims: Sequence[judge.Claim],
               trail: Sequence, manifest: dict,
               extra: dict | None = None) -> list[str]:
    """Everything underneath the insights, as files anyone can open."""
    extra = extra or {}
    os.makedirs(folder, exist_ok=True)
    written = []

    def table(name: str, header: Sequence[str], rows) -> None:
        path = os.path.join(folder, name)
        with open(path, "w", encoding="utf-8", newline="") as fh:
            w = csv.writer(fh)
            w.writerow(header)
            w.writerows(rows)
        written.append(path)

    def document(name: str, payload) -> None:
        path = os.path.join(folder, name)
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(payload, fh, indent=2, default=str)
        written.append(path)

    # The stack rank: every search, every column, most worth selling to
    # first. Searches with no volume have no place and come last.
    stack = graph.stack()
    placed = {k.term for k in stack}
    keywords = stack + sorted((k for k in graph.keywords.values()
                               if k.term not in placed), key=lambda k: k.term)
    table("keywords.csv",
          ["rank", "tier", "term", "sellable", "business_potential",
           "searches_a_month", "click_price", "worth_a_month", "difficulty",
           "year_on_year", "year_on_year_readable", "about", "wants",
           "wants_readable", "answer", "answer_readable", "who",
           "who_readable", "companies", "low_bid", "high_bid", "competition",
           "source", "depth", "expanded", "also_spelled"],
          [["" if k.rank is None else k.rank, TIERS[K.tier(k)], k.term,
            k.sellable,
            _round(k.potential, 2), k.volume, round(k.cpc, 2),
            round(k.money, 2),
            "" if k.difficulty is None else k.difficulty,
            _round(K.growth(k.trend), 3), K.growth_readable(k.trend),
            k.topic or "", k.job or "", k.job_certain, k.offering or "",
            k.offering_certain, k.audience or "", k.audience_certain,
            ";".join(k.entities), round(k.low_bid, 2), round(k.high_bid, 2),
            "" if k.competition_index is None else k.competition_index,
            k.source, k.depth, k.expanded, ";".join(k.aliases)]
           for k in keywords])

    table("series.csv", ["term", "month", "searches"],
          ([k.term, month, value] for k in keywords
           for month, value in zip(k.months, k.trend)))

    table("topics.csv",
          ["topic", "keywords", "searches_a_month", "click_price",
           "names_a_company", "buying_or_comparing", "year_on_year",
           "year_on_year_readable", "seasonality", "mostly_trying_to",
           "intent_mix"],
          [[r["topic"], r["keywords"], r["volume"], r["click_price"],
            r["branded_share"], r.get("commercial_share"), r.get("growth"),
            r.get("growth_readable"), r.get("seasonality"),
            next(iter(r["job_mix"]), ""),
            "; ".join(f"{j} {v}" for j, v in r["job_mix"].items())]
           for r in graph.topic_rows()])

    table("offerings.csv",
          ["offering", "keywords", "searches_a_month", "share_of_searching",
           "share_of_ad_spend", "click_price", "buying_or_comparing",
           "names_a_company", "year_on_year", "year_on_year_readable",
           "priciest", "largest"],
          [[r["offering"], r["keywords"], r["volume"], r["search_share"],
            r["spend_share"], r["click_price"], r["commercial_share"],
            r["branded_share"], r["growth"], r["growth_readable"],
            "; ".join(f"{t} ({v}/mo, {c})" for t, v, c in r["priciest"]),
            "; ".join(f"{t} ({v}/mo, {c})" for t, v, c in r["largest"])]
           for r in graph.offering_rows()])

    ranked = {c.key: i for i, c in enumerate(insights.order(claims), 1)}
    table("tested.csv",
          ["rank", "kind", "headline", "verdict", "why", "value_weight",
           "worth_to_reader", "fair_reading", "account_chosen",
           "account_support", "specific_to_market", "not_guessable",
           "surprising", "text", "assertion", "rival", "evidence"],
          [[ranked.get(c.key, ""), c.kind, c.headline, c.verdict,
            REJECTION_GLOSS.get(c.verdict, ""), round(c.weight, 4),
            c.stakes_label, round(c.reads_true, 3), c.account,
            round(c.account_p, 3), round(1 - c.swappable, 3),
            round(1 - c.obvious, 3), round(c.surprising, 3), c.text,
            c.assertion, c.forbids, json.dumps(c.evidence, default=str)]
           for c in sorted(claims, key=lambda c: (ranked.get(c.key, 10**6),
                                                  c.kind, c.key))])

    table("trail.csv",
          ["step", "question", "action", "status", "depth", "asked_for",
           "worth", "note", "raised_by"],
          [[i, t.question, t.action, t.status, t.depth, len(t.payload),
            t.gain_label, t.note, t.origin]
           for i, t in enumerate(trail, 1)])

    groups = list(extra.get("opportunities") or [])
    table("opportunities.csv",
          ["rank", "start_with", "topic", "offering", "searches",
           "also_on_this_page", "buyer_searches_a_month",
           "buyer_clicks_worth_a_month", "click_price", "difficulty",
           "year_on_year", "worth_naming_no_company_a_month",
           "page_one_clicks_to_weak_pages", "open_value_a_month",
           "page_one_clicks_by_kind", "page_one", "ads", "ai_overview"],
          [[i, r["start_with"], r["topic"], r["offering"], r["searches"],
            r["also"], r["buyer_searches_a_month"], r["prize_a_month"],
            r["click_price"], r["difficulty"], r["year_on_year"],
            r["naming_no_company_a_month"], r["clicks_to_weak_pages"],
            r["open_value_a_month"],
            json.dumps(r["clicks_by_kind"]), r["page_one"], r["ads"],
            r["ai_overview"]]
           for i, r in enumerate((c.row() for c in groups), 1)])

    kinds = {(c.anchor.term, r["rank"]): r.get("kind", "")
             for c in groups for r in c.page}
    pages = extra.get("pages") or {}
    table("page_one.csv",
          ["search", "still_in_market", "rank", "domain", "kind", "title",
           "url"],
          [[term, term in graph.keywords, r["rank"], r["domain"],
            kinds.get((term, r["rank"]), ""), r["title"], r["url"]]
           for term in sorted(pages) for r in _organic(pages[term])])

    import serp as S
    shares = list(extra.get("shares") or [])
    total = sum(x.get("etv", 0.0) for x in shares) or 1.0
    table("share_of_voice.csv",
          ["domain", "share_of_buyer_clicks", "estimated_clicks_a_month",
           "visibility", "searches_ranked_for", "average_position"],
          [[S._registrable(x["domain"]), round(x["etv"] / total, 4),
            round(x["etv"], 1), round(x.get("visibility", 0.0), 4),
            x.get("keywords"), round(x.get("avg_position", 0.0), 1)]
           for x in sorted(shares, key=lambda x: -x.get("etv", 0.0))])

    verdict = manifest.get("verdict") or {}
    prior = manifest.get("prior") or {}
    readings = manifest.get("readings") or {}
    document("network.json", {
        "what_this_is": "A small Bayes network over what a market can be. "
                        "Its probability tables were supplied zero-shot by "
                        "the judgment model; inference is exact enumeration "
                        "in code. Its calibration is unverified: read the "
                        "direction and size of a movement, not the "
                        "absolute figure.",
        "conclusions": {text: {"before": prior.get(node), "after":
                               verdict.get(node)}
                        for node, text in MN.DECISION.items()
                        if node in verdict},
        "properties": {text: {"before": prior.get(node), "after":
                              verdict.get(node)}
                       for node, text in MN.LATENT.items() if node in verdict},
        "what_moved_each_conclusion": {
            MN.DECISION.get(node, node): [
                {"shift": delta, "measurement": readings.get(name, name)}
                for name, delta in moves]
            for node, moves in (manifest.get("attribution") or {}).items()},
        "measurements": readings,
        "rows_without_a_clear_answer": manifest.get("unsplittable_rows"),
    })
    document("forecast.json", manifest.get("forecast") or {})
    document("run.json", manifest)
    return written


def _round(value, places):
    return "" if value is None else round(value, places)
