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
           manifest: dict, data_dir: str = "data") -> str:
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
    L.append("")

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

    L += _footer(graph, claims, manifest, folder)
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
    L += [_scores(claim, arm), ""]
    return L


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
    return (f"<sub>Worth to the reader: {claim.stakes_label or '—'} · "
            f"value weight {claim.weight:.2f} · holds up: fair "
            f"reading {claim.reads_true:.2f}, beats its rival "
            f"{claim.account_p:.2f}, specific to this market "
            f"{1 - claim.swappable:.2f}, not guessable "
            f"{1 - claim.obvious:.2f}</sub>")


def _footer(graph: K.Graph, claims: Sequence[judge.Claim], manifest: dict,
            folder: str) -> list[str]:
    rows = graph.topic_rows()
    erratic = [r["topic"] for r in rows
               if r.get("growth") is not None and not r.get("growth_readable")]
    series_rows = sum(len(k.trend) for k in graph.keywords.values())
    files = [
        ("keywords.csv", "every search measured — volume, click price, bids, "
         "competition, what it is about, what the person wants, what kind of "
         "answer, companies named, where it came from, year on year",
         len(graph.keywords)),
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

def write_data(folder: str, graph: K.Graph, claims: Sequence[judge.Claim],
               trail: Sequence, manifest: dict) -> list[str]:
    """Everything underneath the insights, as files anyone can open."""
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

    keywords = sorted(graph.keywords.values(), key=lambda k: (-k.volume, k.term))
    table("keywords.csv",
          ["term", "searches_a_month", "click_price", "low_bid", "high_bid",
           "competition", "about", "wants", "wants_readable", "answer",
           "answer_readable", "companies", "source", "year_on_year",
           "year_on_year_readable"],
          [[k.term, k.volume, round(k.cpc, 2), round(k.low_bid, 2),
            round(k.high_bid, 2),
            "" if k.competition_index is None else k.competition_index,
            k.topic or "", k.job or "", k.job_certain, k.offering or "",
            k.offering_certain, ";".join(k.entities),
            k.source, _round(K.growth(k.trend), 3),
            K.growth_readable(k.trend)]
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
