#!/usr/bin/env python3
"""make_manifest.py — scaffold (or check) the report manifest for a run.

The analyst should never face a blank page, and should never retype a number
it could get wrong. This reads state.json and clean/*.csv and writes a
report-manifest.json that already contains:

  * title, seed, geo and date — from state.json
  * the cover's key numbers, computed from the corpus
  * the demand-mix table, the top-terms table, the capture table — computed
  * four stack-ranked paths forward, ready to be argued
  * the charts that actually exist, placed in the chapter each belongs to
  * the ad creatives worth showing (longest-running with readable copy),
    referenced by id so the builder pulls image + wording from the corpus
  * the appendix tables that actually exist
  * a default glossary

…and TODO markers everywhere prose is required. The analyst replaces every
TODO with its own writing and may add, drop or reorder any block.

Usage:
    python3 scripts/make_manifest.py --run research/demandcheck/<slug>
    python3 scripts/make_manifest.py --run <run> --check     # audit an existing one

Stdlib only.
"""

import argparse
import csv
import datetime
import json
import os
import re
import sys

TODO = "TODO"


# --------------------------------------------------------------------- helpers

def die(msg, code=2):
    print(f"error: {msg}", file=sys.stderr)
    sys.exit(code)


def read_rows(run, table):
    path = os.path.join(run, "clean", f"{table}.csv")
    if not os.path.isfile(path):
        return []
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def fnum(row, col):
    v = str(row.get(col) or "").strip().replace("$", "").replace(",", "")
    try:
        return float(v)
    except ValueError:
        return None


def median(xs):
    xs = sorted(x for x in xs if x is not None)
    n = len(xs)
    if not n:
        return None
    return xs[n // 2] if n % 2 else (xs[n // 2 - 1] + xs[n // 2]) / 2


def truthy(v):
    return str(v or "").strip().lower() in ("true", "1", "yes", "y")


def usd(v, places=2):
    return f"${v:,.{places}f}" if v is not None else "—"


def num(v):
    return f"{v:,.0f}" if v is not None else "—"


def chart_exists(run, name):
    return os.path.isfile(os.path.join(run, "charts", name))


def charts_for(run, names):
    """[{file, caption}] for the charts that were actually rendered."""
    out = []
    for name, caption in names:
        if chart_exists(run, name):
            out.append({"type": "chart", "file": name, "caption": caption})
    return out


# ------------------------------------------------------------------- the corpus

class Corpus:
    def __init__(self, run):
        self.run = run
        self.keywords = read_rows(run, "keywords")
        self.domains = read_rows(run, "domains")
        self.advertisers = read_rows(run, "advertisers")
        self.ads = read_rows(run, "ads")
        self.ad_copy = read_rows(run, "ad_copy")
        self.serp = read_rows(run, "serp_results")
        self.copy_by_id = {(r.get("creative_id") or "").strip(): r
                           for r in self.ad_copy}

    # -- keywords ---------------------------------------------------------

    def priced(self):
        return [r for r in self.keywords if fnum(r, "cpc")]

    def total_volume(self):
        return sum(fnum(r, "search_volume") or 0 for r in self.keywords)

    def by_class(self):
        out = {}
        for r in self.keywords:
            cls = (r.get("demand_class") or "unclear").strip().lower() or "unclear"
            b = out.setdefault(cls, {"terms": 0, "volume": 0.0, "cpcs": []})
            b["terms"] += 1
            b["volume"] += fnum(r, "search_volume") or 0
            c = fnum(r, "cpc")
            if c:
                b["cpcs"].append(c)
        return out

    def top_by(self, col, n=12, where=None):
        rows = [r for r in self.keywords if fnum(r, col) is not None]
        if where:
            rows = [r for r in rows if where(r)]
        rows.sort(key=lambda r: -(fnum(r, col) or 0))
        return rows[:n]

    # -- ads --------------------------------------------------------------

    def with_images(self):
        return [r for r in self.ads if (r.get("png_path") or "").strip()]

    def proven(self, days=90):
        rows = [r for r in self.ads if (fnum(r, "days_running") or 0) >= days]
        rows.sort(key=lambda r: -(fnum(r, "days_running") or 0))
        return rows

    def legible(self, rows):
        out = []
        for r in rows:
            cp = self.copy_by_id.get((r.get("creative_id") or "").strip(), {})
            h = (cp.get("headline") or "").strip()
            if h and h.upper() != "ILLEGIBLE":
                out.append((r, h))
        return out

    def advertiser_counts(self):
        counts = {}
        for r in self.ads:
            name = (r.get("advertiser_title") or "").strip() or "unknown"
            b = counts.setdefault(name, {"ads": 0, "live": 0, "longest": 0.0})
            b["ads"] += 1
            if truthy(r.get("active")):
                b["live"] += 1
            b["longest"] = max(b["longest"], fnum(r, "days_running") or 0)
        return sorted(counts.items(), key=lambda kv: -kv[1]["ads"])


# ------------------------------------------------------------------ scaffolding

def key_numbers(c):
    out = []
    vol = c.total_volume()
    if vol:
        out.append({"value": num(vol), "label": "searches a month",
                    "note": f"across {len(c.keywords):,} measured search terms"})
    cpcs = [fnum(r, "cpc") for r in c.priced()]
    med = median(cpcs)
    if med:
        lo, hi = min(cpcs), max(cpcs)
        out.append({"value": usd(med), "label": "typical price per click",
                    "note": f"range {usd(lo)} to {usd(hi)}"})
    advs = c.advertiser_counts()
    if advs:
        out.append({"value": f"{len(advs):,}", "label": "companies buying ads here",
                    "note": f"{len(c.ads):,} individual ads collected"})
    proven = c.proven()
    if proven:
        top = proven[0]
        out.append({"value": f"{fnum(top, 'days_running') or 0:,.0f} days",
                    "label": "longest-running ad",
                    "note": f"{(top.get('advertiser_title') or 'unknown').strip()}"
                            f" — {len(proven):,} ads have run 90+ days"})
    return out[:4]


def demand_mix_table(c):
    by = c.by_class()
    order = ["direct", "indirect", "latent", "urgent", "unclear"]
    rows = []
    for cls in order:
        b = by.get(cls)
        if not b:
            continue
        rows.append([cls, f"{b['terms']:,}", num(b["volume"]),
                     usd(median(b["cpcs"])) if b["cpcs"] else "—"])
    if not rows:
        return None
    return {"type": "table", "title": "The demand mix, measured",
            "columns": ["kind of demand", "search terms",
                        "searches per month", "typical price per click"],
            "rows": rows,
            "note": f"{TODO} — one sentence saying what this split means for the "
                    f"reader. Counted from the {len(c.keywords):,} terms in the "
                    f"appendix; “typical” is the middle value."}


def top_terms_table(c, n=12):
    rows = c.top_by("spend_proxy", n) or c.top_by("search_volume", n)
    if len(rows) < 3:
        return None
    return {"type": "table", "title": "Where the money is, term by term",
            "columns": ["search term", "searches per month", "price per click",
                        "kind of demand"],
            "rows": [[r.get("keyword", ""), num(fnum(r, "search_volume")),
                      usd(fnum(r, "cpc")), (r.get("demand_class") or "").strip()]
                     for r in rows],
            "note": "Ranked by searches multiplied by click price — what the "
                    "clicks on each term would cost to buy in a month."}


def latent_table(c, n=10):
    rows = [r for r in c.keywords
            if (fnum(r, "search_volume") or 0) >= 100 and (fnum(r, "cpc") or 0) < 0.5]
    rows.sort(key=lambda r: -(fnum(r, "search_volume") or 0))
    rows = rows[:n]
    if len(rows) < 3:
        return None
    return {"type": "table", "title": "Big audiences almost nobody is paying for",
            "columns": ["search term", "searches per month", "price per click"],
            "rows": [[r.get("keyword", ""), num(fnum(r, "search_volume")),
                      usd(fnum(r, "cpc"))] for r in rows],
            "note": f"{TODO} — say whether this is opportunity or noise, and why."}


def capture_table(c, n=10):
    advs = c.advertiser_counts()[:n]
    if len(advs) < 2:
        return None
    return {"type": "table", "title": "Who is advertising here, and how hard",
            "columns": ["advertiser", "ads found", "still running",
                        "longest ad (days)"],
            "rows": [[name, f"{b['ads']:,}", f"{b['live']:,}",
                      f"{b['longest']:,.0f}"] for name, b in advs],
            "note": "An ad that has run for months is an ad that pays for "
                    "itself — advertisers cut losing ads in weeks."}


def creative_exhibits(c, limit=6):
    """Ids for the chapter-3 gallery: longest-running ads whose copy was read."""
    pairs = c.legible(c.proven())
    if len(pairs) < 3:
        pairs = c.legible(sorted(c.ads,
                                 key=lambda r: -(fnum(r, "days_running") or 0)))
    ids, seen_adv = [], {}
    for r, _h in pairs:  # spread across advertisers before doubling up
        adv = (r.get("advertiser_title") or "").strip()
        if seen_adv.get(adv, 0) >= 2:
            continue
        seen_adv[adv] = seen_adv.get(adv, 0) + 1
        ids.append((r.get("creative_id") or "").strip())
        if len(ids) >= limit:
            break
    return [i for i in ids if i]


def quote_blocks(c, ids, n=2):
    out = []
    for cid in ids[:n]:
        out.append({"type": "quote", "creative_id": cid})
    return out


def glossary(c):
    g = [
        {"term": "search volume",
         "plain": "how many times a phrase is typed into Google in an average "
                  "month, in the market this report covers"},
        {"term": "CPC (cost per click)",
         "plain": "the price an advertiser pays Google each time someone clicks "
                  "their ad"},
        {"term": "top-of-page bid",
         "plain": "what Google estimates an advertiser must bid to appear above "
                  "the search results rather than below them"},
        {"term": "creative",
         "plain": "one individual ad — its wording and its artwork"},
        {"term": "search spend estimate",
         "plain": "a term's monthly searches multiplied by its price per click: "
                  "what buying every click would cost in a month"},
        {"term": "direct demand",
         "plain": "people searching for the thing itself, usually with buying "
                  "intent"},
        {"term": "latent demand",
         "plain": "people searching around a problem that few businesses are "
                  "paying to answer yet"},
    ]
    if any((r.get("demand_class") or "").strip().lower() == "urgent"
           for r in c.keywords):
        g.append({"term": "urgent demand",
                  "plain": "searches phrased as needing help now — they cost more "
                           "per click because they buy sooner"})
    if any((r.get("demand_class") or "").strip().lower() == "indirect"
           for r in c.keywords):
        g.append({"term": "indirect demand",
                  "plain": "people searching for a neighbouring problem that leads "
                           "to this one"})
    return g


APPENDIX_DESCRIPTIONS = [
    ("keywords", "All harvested search terms",
     "Every search term measured, with its monthly searches, click price and "
     "the kind of demand it was classed as."),
    ("domains", "Websites found",
     "Every website that appeared in the searches, what kind of site it is, and "
     "whether it also buys ads."),
    ("advertisers", "Advertisers",
     "Every company found buying ads in this market, with the size of its ad "
     "library."),
    ("ads", "Ad creatives",
     "Every individual ad collected, how long it ran, and whether it is still "
     "running."),
    ("ad_copy", "Ad wording, read from the pictures",
     "The exact words on each ad, read off the ad images reproduced in "
     "Appendix A."),
    ("serp_results", "Search results",
     "What Google actually returned for each search this survey ran, including "
     "which results were paid ads."),
]


def appendix_tables(run):
    out = []
    for table, title, what in APPENDIX_DESCRIPTIONS:
        if os.path.isfile(os.path.join(run, "clean", f"{table}.csv")):
            out.append({"title": title, "csv": f"clean/{table}.csv",
                        "what_it_is": what})
    return out


def paths_scaffold():
    """Four routes in, stack-ranked. The reader's actual decision."""
    hints = [
        "the strongest route the evidence supports",
        "the cheapest route to a first customer",
        "the route that trades cost for defensibility",
        "the contrarian route, and the condition that makes it right",
    ]
    return [{
        "rank": i + 1,
        "name": f"{TODO} — name the route ({h})",
        "thesis": f"{TODO} — what it is, in one or two sentences a reader could "
                  f"act on tomorrow.",
        "evidence": f"{TODO} — the rows from this report that put it at rank "
                    f"{i + 1}: named terms, volumes, prices, ads.",
        "tradeoff": f"{TODO} — what it costs: money, time, and what you give up "
                    f"by choosing it.",
        "best_if": f"{TODO} — the reader this route is right for.",
        "first_step": f"{TODO} — the first concrete move, this week.",
    } for i, h in enumerate(hints)]


def build_manifest(run, state, c):
    seed = state.get("seed", "")
    geo = f"{state.get('geo', 'US')} ({state.get('language', 'en')})"
    today = datetime.date.today().isoformat()
    ids = creative_exhibits(c)
    n_img = len(c.with_images())

    ch1 = [
        {"type": "paragraph", "lead": True,
         "text": f"{TODO} — open with the answer, in plain words: does demand "
                 f"exist, how much of it, and of what kind. Numbers in sentences."},
        {"type": "paragraph",
         "text": f"{TODO} — the shape of the mix, and what each kind means here."},
    ]
    t = demand_mix_table(c)
    if t:
        ch1.append(t)
    ch1 += charts_for(run, [
        ("demand_mix.png", f"{TODO} — one sentence on what this chart shows."),
        ("demand_map.png", f"{TODO} — one sentence: each dot is a search term; "
                           f"say where the interesting corner is."),
    ])
    ch1.append({"type": "callout", "variant": "plain",
                "title": "In plain English",
                "text": f"{TODO} — restate the finding for a reader who has "
                        f"never bought an ad. No jargon at all in this box."})

    ch2 = [
        {"type": "paragraph", "lead": True,
         "text": f"{TODO} — who currently owns this demand, and how you can tell."},
    ]
    for tbl in (top_terms_table(c), capture_table(c)):
        if tbl:
            ch2.append(tbl)
    ch2 += charts_for(run, [
        ("capture_leaders.png", f"{TODO} — one sentence."),
        ("latent_gap.png", f"{TODO} — one sentence."),
        ("seasonality.png", f"{TODO} — one sentence on timing."),
    ])
    t = latent_table(c)
    if t:
        ch2.append(t)
    ch2.append({"type": "callout", "variant": "takeaway",
                "text": f"{TODO} — the gap in one sentence: demand that exists "
                        f"and nobody is currently paying to capture."})

    ch3 = [
        {"type": "paragraph", "lead": True,
         "text": f"{TODO} — what this market's advertising actually says, and "
                 f"why the long-running ads are the ones to read."},
    ]
    ch3 += quote_blocks(c, ids)
    if ids:
        ch3.append({
            "type": "creatives", "ids": ids, "columns": 3,
            "title": "The ads that have earned their keep",
            "intro": f"{TODO} — one sentence on what these have in common.",
            "caption": "Each ad is shown exactly as its advertiser runs it, with "
                       "how long it has been running. Wording below each picture "
                       "was read from the picture itself."})
    ch3 += charts_for(run, [
        ("proven_messaging.png", f"{TODO} — one sentence."),
        ("ad_longevity.png", f"{TODO} — one sentence."),
    ])
    ch3.append({"type": "paragraph",
                "text": f"{TODO} — the phrasings searchers use that no ad uses "
                        f"(open messaging territory), cited to real rows."})

    ch4 = [
        {"type": "paragraph", "lead": True,
         "text": f"{TODO} — what it costs to buy attention here, and where the "
                 f"price is highest and lowest."},
    ]
    ch4 += charts_for(run, [
        ("cpc_by_class.png", f"{TODO} — one sentence."),
        ("money_map.png", f"{TODO} — one sentence."),
        ("format_mix.png", f"{TODO} — one sentence."),
    ])
    ch4.append({"type": "callout", "variant": "watch-out",
                "title": "Worth knowing",
                "text": f"{TODO} — the honest caveat on these prices (planner "
                        f"estimates, thin-volume noise, geography)."})

    man = {
        "title": f"DemandCheck: {seed}",
        "seed": seed,
        "geo": geo,
        "date": today,
        "verdict_line": f"{TODO} — one plain sentence, on the cover: does the "
                        f"demand exist, how big, what kind, at what price.",
        "key_numbers": key_numbers(c),
        "key_terms": {"limit": 15},
        "summary_deck": f"{TODO} — one line under the ‘short version’ heading.",
        "executive_summary": [
            f"{TODO} — paragraph 1: the verdict and the size of the demand.",
            f"{TODO} — paragraph 2: who captures it now, and the gap.",
            f"{TODO} — paragraph 3: the strongest messaging finding, with a "
            f"verbatim quote and how long that ad has run.",
        ],
        "highlights": [
            {"variant": "takeaway", "title": "The finding that matters most",
             "text": f"{TODO} — one sentence."},
            {"variant": "good-news", "title": "What is working",
             "text": f"{TODO} — the categorically-working messaging, in one "
                     f"sentence with a real quote."},
            {"variant": "watch-out", "title": "What would give you trouble",
             "text": f"{TODO} — the hardest fact in this corpus for an entrant."},
        ],
        "chapters": [
            {"heading": "Is there demand, and what shape is it?",
             "kicker": "Chapter 1",
             "takeaway": f"{TODO} — the chapter's answer in one line.",
             "blocks": ch1},
            {"heading": "How it shows up, and who captures it",
             "kicker": "Chapter 2",
             "takeaway": f"{TODO} — one line.",
             "blocks": ch2},
            {"heading": "How this market talks — and what is earning its keep",
             "kicker": "Chapter 3",
             "takeaway": f"{TODO} — one line.",
             "blocks": ch3},
            {"heading": "What it costs",
             "kicker": "Chapter 4",
             "takeaway": f"{TODO} — one line.",
             "blocks": ch4},
        ],
        "explanations": [
            {"name": f"{TODO} — name the mechanism driving this market",
             "premises": [f"{TODO} — the first thing that has to be true …",
                          f"{TODO} — and the second …"],
             "evidence": f"{TODO} — the rows that carry it: named terms, "
                         f"volumes, prices, ads and run lengths.",
             "alternative": f"{TODO} — the other way to read the same numbers, "
                            f"and why it does not hold here."},
            {"name": f"{TODO} — second mechanism",
             "premises": [f"{TODO} …"],
             "evidence": f"{TODO}",
             "alternative": f"{TODO}"},
        ],
        "paths_forward": paths_scaffold(),
        "paths_lead": f"{TODO} — one sentence framing the choice the reader is "
                      f"actually making.",
        "paths_close": f"{TODO} — if they do one thing, this is it.",
        "glossary": glossary(c),
        "appendix_tables": appendix_tables(run),
    }
    man["_scaffold_notes"] = [
        f"Scaffolded from the corpus: {len(c.keywords):,} keywords, "
        f"{len(c.ads):,} ads ({n_img:,} with images), "
        f"{len(c.advertisers):,} advertisers, {len(c.domains):,} domains.",
        "Replace every TODO. Delete this key when done.",
    ]
    return man


# ----------------------------------------------------------------------- check

def walk_strings(obj, path="$"):
    if isinstance(obj, dict):
        for k, v in obj.items():
            yield from walk_strings(v, f"{path}.{k}")
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            yield from walk_strings(v, f"{path}[{i}]")
    elif isinstance(obj, str):
        yield path, obj


BANNED = re.compile(r"\b(proven|validated|confirmed|guarantee[sd]?)\b", re.I)
# Language that narrates the process instead of reporting the finding. The
# reader bought conclusions and evidence, not a lab notebook.
PROCESS = re.compile(
    r"\b(conjecture|hypothes[ei]s|falsif\w*|refut\w*|our (method|process|"
    r"approach|survey|run)|we (expected|assumed|predicted|set out|collected|"
    r"spent)|this (survey|run) (expected|believed|spent)|wave \d|data budget|"
    r"billable call)\b", re.I)
REQUIRED = ["title", "seed", "geo", "date", "verdict_line", "key_numbers",
            "executive_summary", "chapters", "explanations", "paths_forward",
            "glossary", "appendix_tables"]


def check(run, man, c):
    problems, notes = [], []
    for f in REQUIRED:
        if not man.get(f):
            problems.append(f"missing or empty: {f}")
    todos = [p for p, s in walk_strings(man) if TODO in s]
    if todos:
        problems.append(f"{len(todos)} TODO markers still in the manifest "
                        f"(first: {todos[0]})")
    if man.get("_scaffold_notes"):
        problems.append("_scaffold_notes is still present — delete it when the "
                        "manifest is finished")
    paths = man.get("paths_forward") or []
    if paths and len(paths) != 4:
        problems.append(f"paths_forward has {len(paths)} routes — the chapter is "
                        f"four, stack-ranked")
    for i, p in enumerate(paths, 1):
        for f in ("name", "thesis", "evidence", "tradeoff"):
            if not p.get(f):
                problems.append(f"paths_forward[{i}] is missing `{f}`")
    for dead in ("conjectures", "next_tests", "blind_spots", "not_covered",
                 "methodology_notes"):
        if man.get(dead):
            notes.append(f"`{dead}` is set but is not rendered — the report "
                         f"carries findings, the evidence for them, and the "
                         f"routes forward, and nothing else")
    banned = [(p, t) for p, t in walk_strings(man) if BANNED.search(t)]
    for p, t in banned[:5]:
        notes.append(f"language check at {p}: “{BANNED.search(t).group(0)}” — "
                     f"state what the data shows, do not claim proof "
                     f"(references/report-spec.md)")
    # the four kinds of demand are defined on the orientation page, which the
    # cover and the summary come before
    early = [man.get("verdict_line", "")]
    early += man.get("executive_summary", []) or []
    early += [h.get("text", "") for h in (man.get("highlights") or [])
              if isinstance(h, dict)]
    jargon = re.compile(r"\b(direct|indirect|latent|urgent) demand\b", re.I)
    for t in early:
        m = jargon.search(t or "")
        if m:
            notes.append(f"“{m.group(0)}” appears on the cover or in the summary, "
                         f"which the reader meets before those words are defined "
                         f"— say it in plain words there "
                         f"(e.g. “people who aren't looking for the product yet”)")
            break
    leaks = [(p, t) for p, t in walk_strings(man) if PROCESS.search(t)]
    for p, t in leaks[:5]:
        notes.append(f"process language at {p}: “{PROCESS.search(t).group(0)}” — "
                     f"the report reports findings; it does not narrate how the "
                     f"work was done")
    shown = set()
    for ch in man.get("chapters", []):
        for b in ch.get("blocks", []) or []:
            if isinstance(b, dict):
                if b.get("type") in ("creatives", "ads", "gallery"):
                    shown.update(b.get("ids") or [])
                if b.get("type") == "quote" and b.get("creative_id"):
                    shown.add(b["creative_id"])
    if c.with_images() and not shown:
        problems.append(f"{len(c.with_images()):,} ad images were collected but "
                        f"no chapter shows one — add a `creatives` block")
    known = {(r.get("creative_id") or "").strip() for r in c.ads}
    for cid in shown:
        if cid not in known:
            problems.append(f"creative id not in clean/ads.csv: {cid}")
    for ch in man.get("chapters", []):
        for b in ch.get("blocks", []) or []:
            if isinstance(b, dict) and b.get("type") == "chart":
                if not chart_exists(run, b.get("file", "")):
                    problems.append(f"chart referenced but not rendered: "
                                    f"{b.get('file')}")
    return problems, notes


# ------------------------------------------------------------------------ main

def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--run", required=True, help="run directory")
    ap.add_argument("--out", help="output path (default <run>/report-manifest.json)")
    ap.add_argument("--force", action="store_true",
                    help="overwrite an existing manifest")
    ap.add_argument("--check", action="store_true",
                    help="audit the existing manifest instead of writing one")
    args = ap.parse_args()
    run = args.run.rstrip("/")
    if not os.path.isdir(run):
        die(f"no such run directory: {run}")
    state = {}
    sp = os.path.join(run, "state.json")
    if os.path.isfile(sp):
        with open(sp, encoding="utf-8") as f:
            state = json.load(f)
    else:
        print("warning: no state.json — the seed, market and date will be "
              "blank", file=sys.stderr)
    c = Corpus(run)
    out = args.out or os.path.join(run, "report-manifest.json")

    if args.check:
        if not os.path.isfile(out):
            die(f"nothing to check: {out} does not exist")
        with open(out, encoding="utf-8") as f:
            man = json.load(f)
        problems, notes = check(run, man, c)
        for n in notes:
            print(f"note:    {n}")
        for p in problems:
            print(f"PROBLEM: {p}")
        if not problems:
            print(f"{out} looks complete — "
                  f"{len(man.get('chapters', []))} chapters, "
                  f"{len(man.get('explanations', []))} explanations, "
                  f"{len(man.get('paths_forward', []))} paths forward.")
        sys.exit(1 if problems else 0)

    if os.path.isfile(out) and not args.force:
        die(f"{out} already exists — pass --force to overwrite it, or --check "
            f"to audit it")
    if not c.keywords and not c.ads:
        print("warning: clean/ is empty — scaffolding a manifest with no "
              "computed numbers", file=sys.stderr)
    man = build_manifest(run, state, c)
    with open(out, "w", encoding="utf-8") as f:
        json.dump(man, f, indent=2, ensure_ascii=False)
        f.write("\n")
    todos = sum(1 for _p, s in walk_strings(man) if TODO in s)
    print(f"wrote {out}")
    print(f"  computed: {len(man.get('key_numbers', []))} cover numbers, "
          f"{sum(len(ch.get('blocks', [])) for ch in man['chapters'])} blocks "
          f"across {len(man['chapters'])} chapters, "
          f"{len(man['paths_forward'])} paths forward to argue")
    galleries = [b for ch in man["chapters"] for b in ch.get("blocks", [])
                 if b.get("type") in ("creatives", "quote")]
    print(f"  ad evidence placed in the chapters: {len(galleries)} blocks "
          f"({len(c.with_images()):,} ad images available in total)")
    print(f"  {todos} TODO markers for the analyst to replace")
    print(f"  next: fill it in, then `make_manifest.py --run {run} --check`")


if __name__ == "__main__":
    main()
