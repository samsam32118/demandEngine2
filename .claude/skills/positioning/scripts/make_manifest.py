#!/usr/bin/env python3
"""make_manifest.py — scaffold the report manifest from the corpus, then audit it.

Two jobs, one file:

    make_manifest.py --run <run>            scaffold: every number computed from
                                            clean/*.csv, every judgement left TODO
    make_manifest.py --run <run> --check    audit the finished manifest

The split matters. An analyst handed a blank file retypes numbers, and retyped
numbers drift from the tables the appendix prints — so the scaffold computes
them and the analyst never touches them. What the analyst *does* own is the
part no CSV contains: which attribute is genuinely unique, which segment cares,
which frame to compete in, and how to say it.

`--check` is the other half of the contract. This report's whole premise is
that pictures carry the argument, so the audit enforces brevity as a hard
constraint rather than a style note: fields have character ceilings, and a
manifest that has grown paragraphs fails before it can reach the PDF.

Stdlib only.
"""

import argparse
import csv
import json
import os
import re
import sys
from collections import Counter, defaultdict, OrderedDict

TODO = "TODO"

# The report is read by looking. These ceilings are what keep it that way —
# each is roughly the longest a phrase can be and still be taken in at a glance
# in the slot it occupies on the page.
LIMITS = {
    "statement": 330,
    "answer.why": 230,
    "note": 190,
    "sales_story.line": 135,
    "messages.line": 75,
    "messages.proof": 90,
    "segment.why_they_love": 60,
    "key_number.label": 46,
    "canvas.item": 60,
    "frame.name": 46,
}

# Positioning reports are prone to a particular kind of puffery. These are
# claims a study like this cannot support, and hedges that waste the one line
# a page gets.
BANNED = re.compile(
    r"\b(proven|validated|confirmed|guaranteed|(?:we|it|this|they)\s+guarantees?|"
    r"best[- ]in[- ]class|"
    r"world[- ]class|revolutionary|game[- ]chang\w+|synerg\w+|"
    r"we (?:believe|think|feel)|it (?:seems|appears) that|arguably)\b", re.I)

# Sentences about the study rather than the market. The reader gets findings.
PROCESS = re.compile(
    r"\b(this (?:report|study|analysis)|we (?:ran|fetched|collected|scraped|searched)|"
    r"our (?:method|methodology|approach|research)|the data (?:was|were) (?:gathered|collected)|"
    r"in this section|as (?:mentioned|noted|discussed) (?:above|below|earlier))\b", re.I)


def read(run, table):
    path = os.path.join(run, "clean", f"{table}.csv")
    if not os.path.isfile(path):
        return []
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def num(row, col, default=None):
    v = str(row.get(col, "") or "").replace("$", "").replace(",", "").strip()
    try:
        return float(v)
    except ValueError:
        return default


def truthy(v):
    return str(v or "").strip().lower() in ("1", "true", "yes", "y", "x", "✓", "t")


def median(xs):
    xs = sorted(x for x in xs if x is not None)
    if not xs:
        return None
    n = len(xs)
    return xs[n // 2] if n % 2 else (xs[n // 2 - 1] + xs[n // 2]) / 2


def human(n):
    if n is None:
        return "—"
    if n >= 1_000_000:
        return f"{n/1_000_000:.1f}M".replace(".0M", "M")
    if n >= 1_000:
        return f"{n/1_000:.1f}k".replace(".0k", "k")
    return f"{n:,.0f}"


# ------------------------------------------------------------------ scaffold

def scaffold(run):
    state = {}
    sp = os.path.join(run, "state.json")
    if os.path.isfile(sp):
        with open(sp, encoding="utf-8") as f:
            state = json.load(f)

    alts = read(run, "alternatives")
    attrs = read(run, "attributes")
    kws = read(run, "keywords")
    frames = read(run, "frames")
    custs = read(run, "customers")
    msgs = read(run, "messaging")
    vocab = read(run, "vocabulary")

    man = OrderedDict()
    man["product"] = {
        "name": state.get("product_name") or TODO,
        "url": state.get("url", ""),
        "domain": re.sub(r"^https?://(www\.)?", "", state.get("url", "")).split("/")[0],
        "one_liner": TODO,
        "date": __import__("datetime").date.today().isoformat(),
        "geo": f"location {state.get('geo', {}).get('location_code', 2840)} / "
               f"{state.get('geo', {}).get('language_code', 'en')}",
    }
    man["statement"] = TODO

    # ---- attributes: the verdict column is the analyst's, but which rivals
    # have what is a fact already recorded, so the matrix builds itself.
    comp_cols = [c for c in (attrs[0] if attrs else {}) if c.startswith("comp_")]
    man["attributes"] = [{
        "name": a.get("attribute", ""),
        "you": truthy(a.get("you")),
        "competitors": {c[5:]: truthy(a.get(c)) for c in comp_cols},
        "verdict": a.get("verdict") or TODO,
        "evidence": a.get("evidence", ""),
    } for a in attrs]
    n_unique = sum(1 for a in man["attributes"] if a["verdict"] == "unique")

    # ---- alternatives
    man["alternatives"] = [{
        "name": a.get("name", ""),
        "lane": a.get("lane") or TODO,
        "volume": num(a, "volume", 0) or 0,
        "domain": a.get("domain", ""),
        "note": a.get("note", ""),
    } for a in alts]

    # ---- frames: favorability is a judgement about how your attributes read
    # inside each category, so it is scaffolded as TODO with the demand,
    # crowding and price already attached.
    man["frames"] = [{
        "name": f.get("frame", ""),
        "demand": num(f, "demand_volume", 0) or 0,
        "favorability": num(f, "favorability") if f.get("favorability") else TODO,
        "density": num(f, "density", 1) or 1,
        "cpc": num(f, "cpc", 0) or 0,
        "recommended": truthy(f.get("recommended")),
    } for f in frames]

    # ---- segments, from whatever named a customer type
    by_seg = defaultdict(Counter)
    praise = defaultdict(Counter)
    for c in custs:
        seg = (c.get("segment") or "").strip()
        if not seg:
            continue
        by_seg[seg][(c.get("evidence_type") or "evidence").strip()] += 1
        if c.get("praise_theme"):
            praise[seg][c["praise_theme"].strip()] += 1
    man["segments"] = [{
        "name": seg,
        "evidence_types": dict(kinds),
        "why_they_love": praise[seg].most_common(1)[0][0] if praise[seg] else TODO,
        "fit_score": TODO,
    } for seg, kinds in sorted(by_seg.items(), key=lambda kv: -sum(kv[1].values()))]

    # ---- messaging crowding: who claims each theme is countable
    theme_by = defaultdict(set)
    yours = set()
    own = man["product"]["domain"]
    for m in msgs:
        theme = (m.get("theme") or "").strip()
        who = (m.get("competitor") or "").strip()
        if not theme:
            continue
        if who and who != own:
            theme_by[theme].add(who)
        else:
            theme_by[theme]
            yours.add(theme)
    man["messaging_crowding"] = [
        {"theme": t, "claimed_by": sorted(who), "you": t in yours}
        for t, who in sorted(theme_by.items(), key=lambda kv: len(kv[1]))]

    # ---- vocabulary: the *pairing* is the analyst's ("we say X, they say Y"),
    # so the scaffold offers the priced market terms and leaves `yours` blank.
    kw_vol = {(k.get("keyword") or "").lower(): (num(k, "search_volume", 0) or 0) for k in kws}
    if vocab:
        man["vocabulary"] = [{
            "yours": v.get("yours") or TODO,
            "theirs": v.get("theirs") or "",
            "your_volume": num(v, "your_volume", 0) or kw_vol.get((v.get("yours") or "").lower(), 0),
            "their_volume": num(v, "their_volume", 0) or kw_vol.get((v.get("theirs") or "").lower(), 0),
            "note": v.get("note", ""),
        } for v in vocab]
    else:
        top = sorted(kw_vol.items(), key=lambda kv: -kv[1])[:8]
        man["vocabulary"] = [{"yours": TODO, "theirs": t, "your_volume": 0,
                              "their_volume": v, "note": ""} for t, v in top]

    # ---- the judgement sections: shaped, empty, with the vocabulary they need
    man["answer"] = {k: {"name": TODO, "why": TODO} for k in ("frame", "segment", "wedge")}
    uniq = [a["name"] for a in man["attributes"] if a["verdict"] == "unique"][:4] or [TODO]
    man["value_flow"] = {"attributes": uniq, "benefits": [TODO], "themes": [TODO],
                         "links": [{"from": uniq[0], "to": TODO, "weight": 1}]}
    man["segment_value"] = {"segments": [s["name"] for s in man["segments"][:5]] or [TODO],
                            "themes": [TODO], "scores": []}
    man["canvas"] = {
        "alternatives": [a["name"] for a in man["alternatives"][:4]] or [TODO],
        "attributes": uniq[:3],
        "value": [TODO], "segments": [s["name"] for s in man["segments"][:2]] or [TODO],
        "frame": next((f["name"] for f in man["frames"] if f["recommended"]), TODO),
        "trend": "",
    }
    man["sales_story"] = [{"beat": b, "line": TODO} for b in
                          ("The change", "What it broke", "The old fix",
                           "Why that fails", "The new way")]
    man["messages"] = [{"audience": TODO, "line": TODO, "proof": TODO}]
    man["notes"] = {k: TODO for k in
                    ("customers_note", "vocabulary_note", "alternatives_note",
                     "attributes_note", "value_note", "segments_note",
                     "frame_note", "messaging_note")}

    # ---- the cover numbers, computed
    rec = next((f for f in man["frames"] if f["recommended"]),
               max(man["frames"], key=lambda f: f["demand"]) if man["frames"] else None)
    cpc_med = median([num(k, "cpc") for k in kws]) or median([f["cpc"] for f in man["frames"]])
    not_software = sum(1 for a in man["alternatives"] if a["lane"] in ("diy", "nothing"))
    man["key_numbers"] = [
        {"value": str(n_unique) if attrs else TODO, "label": "capabilities only you have",
         "note": f"of {len(attrs)} compared" if attrs else ""},
        {"value": human(rec["demand"]) if rec else TODO,
         "label": "monthly searches in the frame you should own",
         "note": f"“{rec['name']}”" if rec else ""},
        {"value": str(len(alts)) if alts else TODO, "label": "true alternatives",
         "note": f"{not_software} of them are not software" if not_software else ""},
        {"value": f"${cpc_med:,.0f}" if cpc_med else TODO,
         "label": "what a click costs in this category", "note": "median top-of-page bid"},
    ]

    man["appendix_tables"] = [
        s for s in [
            {"title": "Every alternative, and how it was found", "csv": "clean/alternatives.csv",
             "columns": ["name", "lane", "domain", "volume", "cpc", "via"]} if alts else None,
            {"title": "The capability comparison in full", "csv": "clean/attributes.csv",
             "columns": ["attribute", "you", "verdict", "evidence"]} if attrs else None,
            {"title": "What the market actually searches for", "csv": "clean/keywords.csv",
             "columns": ["keyword", "search_volume", "cpc", "frame"]} if kws else None,
            {"title": "Who was found saying what", "csv": "clean/messaging.csv",
             "columns": ["competitor", "theme", "claim", "source"]} if msgs else None,
            {"title": "Customer evidence", "csv": "clean/customers.csv",
             "columns": ["segment", "evidence_type", "evidence", "source_url"]} if custs else None,
        ] if s]
    man["sources"] = [{"what": TODO, "where": TODO}]
    return man


# --------------------------------------------------------------------- check

def walk_strings(obj, path=""):
    if isinstance(obj, dict):
        for k, v in obj.items():
            if str(k).startswith("_"):
                continue
            yield from walk_strings(v, f"{path}.{k}" if path else k)
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            yield from walk_strings(v, f"{path}[{i}]")
    elif isinstance(obj, str):
        yield path, obj


def check(run, man):
    problems, notes = [], []

    def P(msg):
        problems.append(msg)

    def N(msg):
        notes.append(msg)

    for path, val in walk_strings(man):
        if val.strip() == TODO or val.strip().startswith(TODO):
            P(f"unfilled TODO at {path}")
        if BANNED.search(val):
            P(f"unsupportable or padded language at {path}: “{BANNED.search(val).group(0)}”")
        if PROCESS.search(val):
            P(f"narrates the study rather than the market at {path}: "
              f"“{PROCESS.search(val).group(0)}”")

    def cap(value, limit_key, where):
        lim = LIMITS[limit_key]
        if value and len(value) > lim:
            P(f"too long for the space it sits in ({len(value)} > {lim} chars): {where}")

    cap(man.get("statement", ""), "statement", "statement")
    for k, d in (man.get("answer") or {}).items():
        cap((d or {}).get("why", ""), "answer.why", f"answer.{k}.why")
        if not (d or {}).get("name"):
            P(f"answer.{k}.name is empty — the three cards are the report's headline")
    for k, v in (man.get("notes") or {}).items():
        cap(v, "note", f"notes.{k}")
    for i, b in enumerate(man.get("sales_story") or []):
        cap(b.get("line", ""), "sales_story.line", f"sales_story[{i}]")
    for i, m in enumerate(man.get("messages") or []):
        cap(m.get("line", ""), "messages.line", f"messages[{i}].line")
        cap(m.get("proof", ""), "messages.proof", f"messages[{i}].proof")
    for i, s in enumerate(man.get("segments") or []):
        cap(s.get("why_they_love", ""), "segment.why_they_love", f"segments[{i}]")
    for i, n in enumerate(man.get("key_numbers") or []):
        cap(n.get("label", ""), "key_number.label", f"key_numbers[{i}].label")
    for key in ("alternatives", "attributes", "value", "segments"):
        for i, it in enumerate((man.get("canvas") or {}).get(key) or []):
            cap(it, "canvas.item", f"canvas.{key}[{i}]")
    for i, f in enumerate(man.get("frames") or []):
        cap(f.get("name", ""), "frame.name", f"frames[{i}].name")

    # ---- shape: what each chart needs to render at all
    attrs = man.get("attributes") or []
    if len(attrs) < 4:
        P(f"only {len(attrs)} attributes — the comparison grid needs at least 4")
    verdicts = Counter(a.get("verdict") for a in attrs)
    if not verdicts.get("unique"):
        P("no attribute is marked unique — a positioning with no wedge has nothing to say")
    if not verdicts.get("table_stakes"):
        N("nothing marked table_stakes — check the comparison is honest; "
          "most capabilities are shared")
    for a in attrs:
        if a.get("you") and a.get("verdict") == "gap":
            P(f"“{a.get('name')}” is marked a gap but also marked as yours")
        if not a.get("you") and a.get("verdict") == "unique":
            P(f"“{a.get('name')}” is marked unique but you do not have it")
        rivals = sum(1 for v in (a.get("competitors") or {}).values() if v)
        if a.get("verdict") == "unique" and rivals > 1:
            P(f"“{a.get('name')}” is marked unique but {rivals} alternatives have it")

    alts = man.get("alternatives") or []
    lanes = {a.get("lane") for a in alts}
    if len(alts) < 3:
        P(f"only {len(alts)} alternatives — the map needs at least 3")
    if not (lanes & {"diy", "nothing"}):
        P("no do-it-themselves or do-nothing alternative — the status quo wins "
          "most deals and belongs in the set")
    bad = [a["name"] for a in alts if a.get("lane") not in ("direct", "adjacent", "diy", "nothing")]
    if bad:
        P(f"alternatives with no valid lane: {', '.join(bad[:4])}")

    frames = man.get("frames") or []
    if len(frames) < 3:
        P(f"only {len(frames)} candidate frames — choosing between fewer than 3 is not a choice")
    rec = [f for f in frames if f.get("recommended")]
    if len(rec) != 1:
        P(f"{len(rec)} frames marked recommended — exactly one is the decision")
    for f in frames:
        if not isinstance(f.get("favorability"), (int, float)):
            P(f"frame “{f.get('name')}” has no favorability score (0-100)")

    sv = man.get("segment_value") or {}
    segs, themes, scores = sv.get("segments") or [], sv.get("themes") or [], sv.get("scores") or []
    if len(scores) != len(segs) or any(len(r) != len(themes) for r in scores):
        P(f"segment_value scores must be {len(segs)}×{len(themes)} to match its own labels")
    if segs and len(segs) < 2:
        P("fewer than 2 segments — 'who cares a lot' is a comparison")

    vf = man.get("value_flow") or {}
    names = set(vf.get("attributes") or []) | set(vf.get("benefits") or []) | set(vf.get("themes") or [])
    for l in vf.get("links") or []:
        for end in ("from", "to"):
            if l.get(end) not in names:
                P(f"value_flow link points at “{l.get(end)}”, which is not a node")
    orphans = [a for a in (vf.get("attributes") or [])
               if not any(l.get("from") == a for l in vf.get("links") or [])]
    if orphans:
        N(f"attributes that reach no benefit: {', '.join(orphans[:3])} — "
          f"either link them or drop them")

    if len(man.get("key_numbers") or []) != 4:
        P(f"{len(man.get('key_numbers') or [])} key numbers — the cover holds exactly 4")
    if len(man.get("sales_story") or []) < 4:
        P("the sales story needs at least 4 beats to be a story")
    if not man.get("messages"):
        P("no messaging rows")
    if not man.get("appendix_tables"):
        P("no appendix tables — the report has to show its rows")

    for t in man.get("appendix_tables") or []:
        if not os.path.isfile(os.path.join(run, t.get("csv", ""))):
            P(f"appendix table points at a file that does not exist: {t.get('csv')}")

    chart_dir = os.path.join(run, "charts")
    have = {os.path.splitext(f)[0] for f in os.listdir(chart_dir)} if os.path.isdir(chart_dir) else set()
    want = {"customer_evidence", "vocabulary_gap", "alternatives_map", "attribute_matrix",
            "value_flow", "segment_heat", "frame_quadrant", "messaging_crowd"}
    if want - have:
        N(f"charts not yet rendered: {', '.join(sorted(want - have))} "
          f"(run charts.py after the manifest is filled)")
    return problems, notes


# ----------------------------------------------------------------------- cli

def main():
    p = argparse.ArgumentParser(description="scaffold or audit the positioning manifest")
    p.add_argument("--run", required=True)
    p.add_argument("--out", help="default: <run>/report-manifest.json")
    p.add_argument("--check", action="store_true", help="audit an existing manifest")
    p.add_argument("--force", action="store_true", help="overwrite an existing manifest")
    a = p.parse_args()

    out = a.out or os.path.join(a.run, "report-manifest.json")

    if a.check:
        if not os.path.isfile(out):
            print(f"error: no manifest at {out}", file=sys.stderr)
            sys.exit(3)
        with open(out, encoding="utf-8") as f:
            man = json.load(f)
        problems, notes = check(a.run, man)
        for n in notes:
            print(f"NOTE     {n}")
        for pr in problems:
            print(f"PROBLEM  {pr}")
        print(f"\n{len(problems)} problems, {len(notes)} notes")
        if problems:
            print("Clear every PROBLEM before building — each one is something the "
                  "reader would see as wrong or missing.")
            sys.exit(1)
        print("Manifest is ready to build.")
        return

    if os.path.isfile(out) and not a.force:
        print(f"error: {out} exists — pass --force to regenerate (you will lose "
              f"the analyst's work)", file=sys.stderr)
        sys.exit(2)
    man = scaffold(a.run)
    os.makedirs(os.path.dirname(out) or ".", exist_ok=True)
    with open(out, "w", encoding="utf-8") as f:
        json.dump(man, f, indent=2, ensure_ascii=False)
    todos = sum(1 for _, v in walk_strings(man) if v.strip() == TODO)
    print(json.dumps({
        "wrote": out,
        "computed": {"attributes": len(man["attributes"]), "alternatives": len(man["alternatives"]),
                     "frames": len(man["frames"]), "segments": len(man["segments"]),
                     "message_themes": len(man["messaging_crowding"]),
                     "vocabulary_pairs": len(man["vocabulary"])},
        "todos_for_analyst": todos,
        "next": "fill every TODO, then: make_manifest.py --check, charts.py, build_pdf.py",
    }, indent=2))


if __name__ == "__main__":
    main()
