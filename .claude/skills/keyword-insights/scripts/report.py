"""The deliverable: a markdown report of findings that are backed by data.

Three things are here on purpose that most reports leave out.

**The trail.** How a finding was arrived at is part of the finding. A report
that shows only conclusions asks to be taken on trust; one that shows the
chase — what looked odd, what was checked next, what came back — can be
argued with, which is the only way a reader can tell whether it is any good.

**The dead ends.** A branch that was chased and went nowhere is a real
result, and an expensive one. Hiding it would make the method look cleverer
than it is and would quietly repeat the same spend next time.

**The rejections.** Every claim the data could have supported was generated
and tested. Showing the ones that failed, and why, tells the reader what was
looked for and not found — which is often more useful than what was.
"""

from __future__ import annotations

import datetime as _dt
from typing import Sequence

import insights
import judge
import market_net as MN
import kgraph as K

n, usd, pct = insights.n, insights.usd, insights.pct

REJECTION_ORDER = ("misread", "explains nothing", "would fit any market",
                   "knowable without data", "changes nothing",
                   "below threshold")

REJECTION_GLOSS = {
    "misread": "the numbers were right but the reading of them was not",
    "explains nothing": "it ruled nothing out — true either way",
    "would fit any market": "it survived having its subject swapped for an "
                            "unrelated one, so it was never about this market",
    "knowable without data": "it follows from the market's name alone",
    "changes nothing": "true, specific, and of no consequence to the reader",
    "below threshold": "a measured value did not clear the control arm's "
                       "cut-off",
}


def _evidence_lines(claim: judge.Claim) -> list[str]:
    out = []
    for key, value in claim.evidence.items():
        if isinstance(value, dict):
            inner = ", ".join(f"{k} {v}" for k, v in value.items())
            out.append(f"- **{key.replace('_', ' ')}**: {inner}")
        elif isinstance(value, list):
            if not value:
                continue
            shown = ", ".join(str(v) for v in value[:12])
            out.append(f"- **{key.replace('_', ' ')}**: {shown}")
        elif isinstance(value, float):
            out.append(f"- **{key.replace('_', ' ')}**: {value:,.2f}")
        elif isinstance(value, int):
            out.append(f"- **{key.replace('_', ' ')}**: {value:,}")
        else:
            out.append(f"- **{key.replace('_', ' ')}**: {value}")
    return out


def _confidence_line(claim: judge.Claim, arm: str) -> str:
    if arm == "code":
        return (f"*Kept by the threshold arm; speaks for "
                f"{pct(claim.weight)} of measured searching.*")
    return (f"*Jev — describes these searches: {claim.reads_true:.2f} · "
            f"rules out the alternative: {claim.forbids_p:.2f} · "
            f"would not fit another market: {1 - claim.swappable:.2f} · "
            f"not guessable without data: {1 - claim.obvious:.2f} · "
            f"out of line for this kind of market: {claim.surprising:.2f} · "
            f"for the reader this is “{claim.stakes_label}”*")


def _trail_diagram(seed: str, trail: Sequence) -> list[str]:
    if not trail:
        return []
    lines = ["```mermaid", "flowchart TD",
             f'  S["seed: {seed}"]']
    prev = "S"
    for i, thread in enumerate(trail):
        node = f"T{i}"
        question = thread.question.replace('"', "'")[:70]
        lines.append(f'  {node}["{question}"]')
        lines.append(f"  {prev} --> {node}")
        if thread.status == "paid_off":
            lines.append(f"  {node}:::hit")
            prev = node               # went deeper
        elif thread.status == "dead_end":
            lines.append(f"  {node}:::miss")
            prev = "S"                # backtracked to the top
        else:
            lines.append(f"  {node}:::open")
    lines += [
        "  classDef hit fill:#dff3e8,stroke:#1baf7a,color:#0b3b2a;",
        "  classDef miss fill:#fbe4dc,stroke:#eb6834,color:#4a1d0c;",
        "  classDef open fill:#e4edfb,stroke:#2a78d6,color:#10305c;",
        "```"]
    return lines


def render(graph: K.Graph, claims: Sequence[judge.Claim],
           trail: Sequence, manifest: dict) -> str:
    arm = manifest.get("arm", "jev")
    kept = insights.order(claims)
    today = _dt.date.today().isoformat()
    seo_led = manifest["dataforseo"]
    jev_led = manifest["jev"]
    # Two different numbers, and conflating them overstates the report.
    # `judged` is everything that was asked about; `certain` is the subset
    # whose intent the words actually resolved. Every finding below is built
    # on `certain`, so that is the coverage the reader needs.
    asked = K.share(graph.judged_volume, graph.total_volume)
    covered = K.share(graph.certain_volume, graph.total_volume)

    L: list[str] = []
    L.append(f"# What people actually search around “{graph.seed}”")
    L.append("")
    L.append(f"**{graph.geo or 'United States'} · {today}**")
    L.append("")
    L.append(
        f"{len(graph.keywords):,} keywords measured, carrying "
        f"{n(graph.total_volume)} searches a month. "
        f"{len(graph.judged):,} of them — {pct(asked)} of that searching — "
        f"were put on two axes: what the search is about, and what the "
        f"person is trying to do. The words resolved the second question "
        f"for {len(graph.certain):,} of them, **{pct(covered)} of the "
        f"market's searching**, and everything below is built on that "
        f"subset alone; the rest is short head terms that do not say what "
        f"the searcher wants, and are left out rather than guessed at. "
        f"{manifest['claims_generated']} statements the data could support "
        f"were generated and tested; {manifest['claims_kept']} survived.")
    L.append("")
    L.append(f"Written for: *{manifest['asker']}*. That matters — a finding "
             f"is only valuable relative to the decision someone is about to "
             f"make, so the same data judged for a different reader would "
             f"keep a different set.")
    L.append("")

    # ---- the answer ------------------------------------------------------
    verdict = manifest.get("verdict") or {}
    prior = manifest.get("prior") or {}
    if verdict:
        L.append("## What this means")
        L.append("")
        L.append(
            "These are not summaries of the findings below. They come from a "
            "small network of the things a market can be — whether people "
            "here will pay, whether the words reveal what anyone wants, "
            "whether buyers have settled on suppliers — whose probability "
            "tables were supplied by the judgment model in a single request, "
            "and into which every measurement below enters as evidence. The "
            "numbers are what that network concludes.")
        L.append("")
        L.append("| | before measuring | after | |")
        L.append("|---|---:|---:|---|")
        for node, text in MN.DECISION.items():
            if node not in verdict:
                continue
            was, now = prior.get(node, 0.5), verdict[node]
            arrow = ("rose" if now > was + 0.02 else
                     "fell" if now < was - 0.02 else "held")
            L.append(f"| **{text.capitalize()}** | {was:.0%} | "
                     f"**{now:.0%}** | {arrow} |")
        L.append("")

        attribution = manifest.get("attribution") or {}
        readings = manifest.get("readings") or {}
        for node, text in MN.DECISION.items():
            moves = [(n, d) for n, d in attribution.get(node, [])
                     if abs(d) >= 0.01][:3]
            if not moves:
                continue
            L.append(f"**{text.capitalize()}** — what moved it:")
            L.append("")
            for name, delta in moves:
                direction = "toward" if delta > 0 else "against"
                L.append(f"- `{delta:+.2f}` {direction} — "
                         f"{readings.get(name, MN.OBSERVED.get(name, name))}")
            L.append("")

        L.append("The latent properties these rest on, as the network reads "
                 "them from the measurements:")
        L.append("")
        L.append("| property | before | after |")
        L.append("|---|---:|---:|")
        for node, text in MN.LATENT.items():
            if node in verdict:
                L.append(f"| {text.capitalize()} | {prior.get(node, 0.5):.0%} "
                         f"| {verdict[node]:.0%} |")
        L.append("")

    # ---- findings -------------------------------------------------------
    L.append("## What the data says")
    L.append("")
    if not kept:
        L.append("Nothing survived. Every statement the measurements could "
                 "support was either true of any market, guessable without "
                 "data, or of no consequence to the reader. That is a "
                 "finding in itself: this keyword's searching has no "
                 "distinctive shape at the volume measured.")
        L.append("")
    for i, claim in enumerate(kept, 1):
        L.append(f"### {i}. {claim.text}")
        L.append("")
        L.extend(_evidence_lines(claim))
        L.append("")
        L.append(f"**This rules out:** {claim.forbids}")
        L.append("")
        if claim.examples:
            L.append("Searches behind it: " +
                     "; ".join(f"`{e}`" for e in claim.examples[:6]))
            L.append("")
        L.append(_confidence_line(claim, arm))
        L.append("")

    # ---- what acting on it would cost ------------------------------------
    fc = manifest.get("forecast")
    if fc:
        cur = manifest.get("currency", "$")
        L.append("## What it would cost to act on this")
        L.append("")
        L.append(
            f"Google's own forecast for the {fc['keywords']:,} searches here "
            f"worth bidding on — the ones where someone is buying, comparing "
            f"or looking for a supplier nearby, not reading a definition or "
            f"hunting a job. Bid set at {cur}{fc['bid']:.2f}, the median "
            f"top-of-page bid already measured on those very keywords, on "
            f"exact match.")
        L.append("")
        L.append("| | |")
        L.append("|---|---:|")
        L.append(f"| Clicks available a month | **{fc['clicks']:,.0f}** |")
        L.append(f"| What each actually costs | {cur}{fc['cpc']:,.2f} |")
        L.append(f"| To take all of them | **{cur}{fc['cost']:,.0f} a month** |")
        L.append(f"| Searches behind it | {n(fc['searches'])} a month |")
        L.append("")
        if fc.get("bid", 0) > 0 and fc["cpc"] > 0 and fc["cpc"] < fc["bid"]:
            L.append(
                f"You would bid {cur}{fc['bid']:.2f} and pay "
                f"{cur}{fc['cpc']:.2f} — {1 - fc['cpc'] / fc['bid']:.0%} under "
                f"your maximum. That gap is the auction saying how much of "
                f"your bid it actually needs.")
            L.append("")
        # The ratio a reader cannot get anywhere else: what a market can
        # absorb, against what they were going to spend.
        budget = fc.get("budget")
        if budget:
            if fc["cost"] <= 0:
                covers = 1.0
            else:
                covers = min(1.0, budget / fc["cost"])
            if budget >= fc["cost"]:
                L.append(
                    f"**{cur}{budget:,.0f} a month is more than this market "
                    f"has to sell.** Taking every click worth buying costs "
                    f"{cur}{fc['cost']:,.0f}, so the constraint here is not "
                    f"your budget — it is that only {fc['clicks']:,.0f} "
                    f"people a month can be bought at this bid. Spending "
                    f"the rest means bidding on searches that are not "
                    f"buying, or finding customers somewhere other than "
                    f"search.")
            else:
                L.append(
                    f"**{cur}{budget:,.0f} a month buys about "
                    f"{fc['clicks'] * covers:,.0f} of the "
                    f"{fc['clicks']:,.0f} clicks available** — {covers:.0%} "
                    f"of what this market has to sell at this bid. There is "
                    f"room here to spend more than you planned.")
            L.append("")
        L.append(
            "A forecast is what Google expects to deliver, not a quote. It "
            "assumes you win the auctions it thinks you will win; a new "
            "account with no history usually does worse at first.")
        L.append("")

    # ---- the trail ------------------------------------------------------
    L.append("## How this was arrived at")
    L.append("")
    L.append(f"The loop makes one measurement, looks for what is out of "
             f"line, and buys one answer to the question that raises. When "
             f"an answer does not speak to the question, the branch is "
             f"abandoned and a different thread is taken up — which is why "
             f"the map below has ends that stop.")
    L.append("")
    L.extend(_trail_diagram(graph.seed, trail))
    L.append("")
    if trail:
        for i, thread in enumerate(trail, 1):
            mark = {"paid_off": "answered", "dead_end": "dead end",
                    "unfunded": "not funded", "chasing": "in flight"}.get(
                        thread.status, thread.status)
            L.append(f"{i}. **{thread.question}** → *{mark}*"
                     + (f" — {thread.note}" if thread.note else ""))
        L.append("")
    else:
        L.append("*No follow-up was bought: the first measurement was judged "
                 "sufficient to answer the question, so the remaining budget "
                 "was left unspent.*")
        L.append("")

    # ---- the map --------------------------------------------------------
    rows = graph.topic_rows()
    if rows:
        L.append("## The shape of the market")
        L.append("")
        L.append("| what people search about | searches/mo | click price | "
                 "names a brand | mostly trying to |")
        L.append("|---|---:|---:|---:|---|")
        for r in rows[:14]:
            top_job = next(iter(r["job_mix"]), "")
            L.append(
                f"| {r['topic']} | {n(r['volume'])} | "
                f"{usd(r['click_price'])} | {pct(r['branded_share'])} | "
                f"{K.JOB_LABELS.get(top_job, top_job)} |")
        L.append("")

    # ---- rejections -----------------------------------------------------
    rejected = [c for c in claims if not c.survived()]
    if rejected:
        L.append("## Checked, and it did not hold")
        L.append("")
        L.append("Every statement the shape of the data permitted was built "
                 "and tested, including ones that contradict each other. "
                 "These are the ones that failed, and why — so you can see "
                 "what was looked for as well as what was found.")
        L.append("")
        by_reason: dict[str, list[judge.Claim]] = {}
        for claim in rejected:
            by_reason.setdefault(claim.verdict, []).append(claim)
        for reason in REJECTION_ORDER:
            group = by_reason.get(reason)
            if not group:
                continue
            L.append(f"**{reason}** — {REJECTION_GLOSS.get(reason, '')}")
            L.append("")
            for claim in group[:8]:
                L.append(f"- {claim.text}")
            if len(group) > 8:
                L.append(f"- *…and {len(group) - 8} more*")
            L.append("")

    # ---- cost -----------------------------------------------------------
    L.append("## What this cost")
    L.append("")
    L.append(f"| | calls | actual |")
    L.append(f"|---|---:|---:|")
    L.append(f"| DataForSEO | {seo_led['billable_calls']} billable "
             f"(+{seo_led['cached_calls']} cached) | "
             f"${seo_led['spent_usd']:.4f} |")
    L.append(f"| Jev | {jev_led['requests']} requests, "
             f"{jev_led['input_tokens']:,} input tokens | "
             f"${jev_led['usd']:.4f} |")
    total = seo_led["spent_usd"] + jev_led["usd"]
    L.append(f"| **total** | | **${total:.4f}** |")
    L.append("")
    L.append(f"DataForSEO figures are the `cost` each response reported, not "
             f"an estimate. Run time {manifest['seconds']}s.")
    L.append("")

    # ---- method ---------------------------------------------------------
    L.append("## How to read this")
    L.append("")
    L.append(
        "Every sentence above was assembled by code from measured numbers, "
        "and every decision about it — does this describe these searches, "
        "does it rule anything out, could it have been guessed, does it "
        "matter to you — was made by a typed judgment model answering one "
        "question at a time. No language model wrote any of it, which is "
        "why the same keyword run twice returns the same report.")
    L.append("")
    unsplittable = manifest.get("unsplittable_rows") or []
    if verdict:
        L.append(
            f"The probabilities at the top come from a network of "
            f"{len(MN.LATENT)} hidden properties, {len(MN.OBSERVED)} "
            f"measurements and {len(MN.DECISION)} conclusions. Its "
            f"probability tables were supplied zero-shot by the judgment "
            f"model — no training data, no expert interviews — and its "
            f"inference is exact enumeration in code. **Its calibration is "
            f"unverified.** The model is trained for calibration, but this "
            f"network is not a published benchmark, so there is no "
            f"established answer to check against. Treat the direction and "
            f"the size of a movement as the signal, and the absolute figure "
            f"as an estimate."
            + (f" {len(unsplittable)} of its table rows came back without a "
               f"clear answer either way, and those rows sit at even odds."
               if unsplittable else ""))
        L.append("")
    L.append(
        "The two tests worth knowing about: a statement is **swapped** — its "
        "subject replaced with an unrelated one — and kept only if it then "
        "reads as false, because a statement that survives that substitution "
        "was never about this market. And it is asked whether it could be "
        "**guessed from the market's name alone**; if so, the data paid for "
        "nothing.")
    L.append("")
    L.append(f"Search volume and click prices are Google Ads figures for "
             f"{graph.geo or 'the United States'}. Volume is a monthly "
             f"average, not a forecast; click prices are what advertisers "
             f"have been paying, which is evidence that money moves — not a "
             f"quote.")
    L.append("")
    L.append(
        f"**On the currency.** DataForSEO returns click prices as bare "
        f"numbers — its response carries no currency field — and documents "
        f"them as US dollars. They are shown here with "
        f"`{manifest.get('currency', '$')}` on that basis, not because the "
        f"source said so. If your Google Ads account bills in another "
        f"currency, convert before budgeting against these figures.")
    L.append("")
    return "\n".join(L)
