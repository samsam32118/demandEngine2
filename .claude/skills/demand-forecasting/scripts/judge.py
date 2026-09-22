#!/usr/bin/env python3
"""judge.py — the Jev judgment stages of the demand-forecasting loop.

Every stage here replaces a step where v1 pulled raw instrument output into
the agent's context and eyeballed it: 2,000 keyword rows, 200 app reviews,
40 ad creatives. Reading those costs minutes and tens of thousands of tokens,
and the resulting judgment is unauditable — it lives in prose nobody can
re-run.

Each stage instead sends the rows to Jev as a batch of typed questions and
gets back calibrated numbers this script thresholds in code. A 600-keyword
triage is about one second and a tenth of a cent, and the answers are written
to disk so the verdict can be re-derived later.

    STAGE       IN (instrument output)          OUT (typed, banked)
    triage      keyword rows                    per-node keyword clusters
    census      SERP rows                       ranked competitor seed domains
    reviews     app reviews                     pain hit-rate, WTP, themes
    creatives   ad-library rows                 who/wedge framing, sustainers
    score       measured evidence per node      0-5 demand score (composite)
    explain     a hypothesis card               hard-to-vary verdict
    verdict     card thresholds + measurements  VALIDATED/REFUTED/INCONCLUSIVE

THE CONTRACT, which every stage keeps: **Jev answers semantic questions; this
file does all the arithmetic.** Jev decides whether a query reads commercial,
whether a review is from someone who pays, whether an explanation still holds.
It never sums a cluster, compares a threshold, medians a CPC or picks a
verdict — jev-1.13 is unreliable at counting and numeric comparison, and
those are exactly the parts that must be reproducible anyway.

Stdlib-only. Run from the repo root.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import re
import statistics
import sys
from typing import Any, Sequence

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import jev  # noqa: E402  (sibling module, path fixed above)
import maze as mazelib  # noqa: E402

# Confidence floors. A Choice always picks something — the probabilities sum
# to 1 even when nothing fits — so a floor is what turns "picked" into
# "decided". Higher floors where a wrong call is expensive to unwind.
ASSIGN_CONFIDENCE = 0.55      # keyword -> node, cheap to revisit
CENSUS_CONFIDENCE = 0.50      # SERP row -> competitor class, cheap
REFUTE_PROBABILITY = 0.60     # P("demand is absent") -> REFUTED, expensive
INTENT_FLOOR = 0.50           # P(commercial intent) to keep a keyword
PAIN_FLOOR = 0.50
SUSTAINED_DAYS = 90           # an advertiser who kept paying this long

NONE_OPTION = "none_of_these"


# ------------------------------------------------------------------- io

def die(msg: str, code: int = 2):
    print(f"error: {msg}", file=sys.stderr)
    raise SystemExit(code)


def load_rows(path: str) -> list[dict]:
    """Read instrument output: .csv, .json (list or {rows|items|results}), .jsonl."""
    if not os.path.exists(path):
        die(f"no such file: {path}")
    ext = os.path.splitext(path)[1].lower()
    with open(path, encoding="utf-8") as fh:
        if ext == ".csv":
            return [dict(r) for r in csv.DictReader(fh)]
        if ext == ".jsonl":
            return [json.loads(line) for line in fh if line.strip()]
        data = json.load(fh)
    if isinstance(data, list):
        return [r for r in data if isinstance(r, dict)]
    if isinstance(data, dict):
        for key in ("rows", "items", "results", "data", "reviews", "creatives", "keywords"):
            value = data.get(key)
            if isinstance(value, list):
                return [r for r in value if isinstance(r, dict)]
    die(f"{path}: expected a list of rows, or an object with a rows/items/results list")
    return []


def num(value: Any, default: float | None = None) -> float | None:
    """Parse a number out of CSV text without letting '' become 0."""
    if value is None or value == "":
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def emit(args, payload: dict, lines: Sequence[str]) -> None:
    for line in lines:
        print(line)
    if getattr(args, "out", None):
        os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
        with open(args.out, "w", encoding="utf-8") as fh:
            json.dump(payload, fh, indent=2, ensure_ascii=False)
            fh.write("\n")
        print(f"\nbanked: {args.out}")


def resolve_lab(args) -> str | None:
    """Find the lab without dying if there isn't one.

    Every stage wants the lab — for the cache and the Jev ledger — but only
    `triage` strictly needs it. Silently losing the ledger because `--lab` was
    omitted is worse than a stage that works anywhere, so discover it softly
    and carry on when there is nothing to find.
    """
    if getattr(args, "lab", None):
        return args.lab
    root = getattr(args, "root", mazelib.DEFAULT_ROOT)
    if not os.path.isdir(root):
        return None
    found = [os.path.join(root, name) for name in sorted(os.listdir(root))
             if os.path.isfile(os.path.join(root, name, "maze.json"))]
    if len(found) == 1:
        args.lab = found[0]
        return found[0]
    if len(found) > 1:
        die("several labs found, pass --lab: " + ", ".join(found))
    return None


def client_for(args) -> jev.Client:
    cache_dir = args.cache_dir
    resolve_lab(args)
    if not cache_dir and getattr(args, "lab", None):
        cache_dir = os.path.join(args.lab, ".jev-cache")
    if not cache_dir:
        cache_dir = ".jev-cache"
    try:
        return jev.Client(
            cache_dir=cache_dir,
            use_cache=not args.no_cache,
            concurrency=args.concurrency,
            model=args.model,
        )
    except jev.JevAuthError as exc:
        die(f"{exc}\n\nWithout Jev these stages cannot run. The loop still works — "
            f"fall back to reading the rows yourself, and record in the report's "
            f"threats-to-validity that the judgments were unaudited.")
        raise


def log_usage(args, usage: jev.Usage, note: str) -> None:
    """Record Jev spend on the lab ledger, separately from instrument spend.

    Jev costs fractions of a cent, but a lab that cannot say what it spent is
    not auditable, and the split matters: the instrument budget is the scarce
    one.
    """
    print(usage.line())
    lab = getattr(args, "lab", None)
    if not lab or not os.path.isfile(os.path.join(lab, "maze.json")):
        return
    try:
        state = mazelib.load(lab)
    except (OSError, ValueError):
        return
    ledger = state.setdefault("jev", {"usd": 0.0, "requests": 0, "input_tokens": 0,
                                      "seconds": 0.0, "ledger": []})
    ledger["usd"] = round(ledger.get("usd", 0.0) + usage.usd, 8)
    ledger["requests"] = ledger.get("requests", 0) + usage.requests
    ledger["input_tokens"] = ledger.get("input_tokens", 0) + usage.input_tokens
    ledger["seconds"] = round(ledger.get("seconds", 0.0) + usage.seconds, 3)
    ledger["ledger"].append({"ts": mazelib.now(), "note": note, **usage.as_dict()})
    mazelib.save(lab, state)


def load_nodes(args) -> dict[str, dict]:
    lab = getattr(args, "lab", None) or mazelib.find_lab(args)
    args.lab = lab
    state = mazelib.load(lab)
    nodes = state.get("nodes") or {}
    if getattr(args, "nodes", None):
        wanted = {n.strip().upper() for n in args.nodes.split(",") if n.strip()}
        unknown = wanted - set(nodes)
        if unknown:
            die(f"unknown node(s): {', '.join(sorted(unknown))}")
        nodes = {k: v for k, v in nodes.items() if k in wanted}
    if not nodes:
        die("no nodes to work with — add some with `maze.py add` first")
    return nodes


def node_rubric(node: dict) -> str:
    """One line describing a node, used as a Choice option's rubric.

    Jev reads instructions literally, so the rubric spells out the WHO and the
    job rather than assuming the reader infers them from the title.
    """
    axes = node.get("axes") or {}
    parts = [node.get("title") or ""]
    who, pain = axes.get("who"), axes.get("pain")
    if who:
        parts.append(f"for {who}")
    if pain:
        parts.append(f"whose job-to-be-done is {pain}")
    return " — ".join(p for p in parts if p)


def pct(part: int, whole: int) -> str:
    return f"{(100.0 * part / whole):.0f}%" if whole else "n/a"


# -------------------------------------------------------------- triage

BRANDISH = re.compile(r"\b(login|log in|sign in|coupon|promo code|careers|apk|crack|download)\b", re.I)


def cmd_triage(args):
    """Assign harvested keywords to maze nodes and gate them on buying intent.

    Two questions per keyword, deliberately:

      Choice -> which node, if any, is this person shopping for. Relative:
                it settles *which*, and its confidence says whether the nodes
                are actually distinguishable by this query.
      Noul   -> is this commercial intent at all. Absolute: it can be low for
                every node, which a Choice can never say.

    Mixing those two into one question is the single most common way to get a
    cluster full of "what is a soap note".
    """
    nodes = load_nodes(args)
    rows = load_rows(args.keywords)
    brands = [b.strip().lower() for b in (args.brands or "").split(",") if b.strip()]

    seen: set[str] = set()
    candidates: list[dict] = []
    dropped: list[dict] = []
    for row in rows:
        kw = (row.get("keyword") or row.get("term") or "").strip()
        if not kw:
            continue
        key = kw.casefold()
        if key in seen:
            continue
        seen.add(key)
        volume = num(row.get("search_volume"), 0.0) or 0.0
        cpc = num(row.get("cpc"))
        reason = None
        if volume < args.min_volume:
            reason = f"volume {volume:.0f} < {args.min_volume}"
        elif BRANDISH.search(kw):
            reason = "navigational/brand-ish term"
        elif any(b in key for b in brands):
            reason = "competitor brand term"
        if reason:
            dropped.append({"keyword": kw, "reason": reason})
            continue
        candidates.append({"keyword": kw, "search_volume": volume, "cpc": cpc})

    candidates.sort(key=lambda r: -r["search_volume"])
    if len(candidates) > args.limit:
        for row in candidates[args.limit:]:
            dropped.append({"keyword": row["keyword"], "reason": f"beyond --limit {args.limit}"})
        candidates = candidates[: args.limit]
    if not candidates:
        die("no keywords survived the code-side filter — loosen --min-volume/--limit")

    criteria = {nid: node_rubric(node) for nid, node in nodes.items()}
    criteria[NONE_OPTION] = (
        "None of the above — a definition or how-to, a free template, a job "
        "search, a specific brand's own page, or an unrelated topic"
    )

    questions: dict[str, jev.Question] = {}
    for i, row in enumerate(candidates):
        questions[f"node:{i}"] = jev.Choice(
            instructions={
                "search_query": row["keyword"],
                "question": "Someone types `search_query` into Google. "
                            "Which of these products are they shopping for?",
            },
            criteria=criteria,
        )
        questions[f"intent:{i}"] = jev.Noul(
            instructions={
                "search_query": row["keyword"],
                "question": "Is the person typing `search_query` looking for a software "
                            "product to use?",
            },
            criteria={
                "true": "Looking for a tool, app or software — browsing, comparing, "
                        "pricing, or ready to buy one",
                "false": "Wants information or a definition, a free template or a "
                         "manual method, a job, or one named brand's own login or "
                         "support page",
            },
        )

    client = client_for(args)
    result = client.ask(
        {"idea": args.idea or "", "geo": args.geo}, questions)
    log_usage(args, result.usage, f"triage {len(candidates)} keywords")

    clusters: dict[str, list[dict]] = {nid: [] for nid in nodes}
    unassigned: list[dict] = []
    for i, row in enumerate(candidates):
        pick = result.choice(f"node:{i}")
        intent = result.noul(f"intent:{i}").noul
        entry = {**row, "intent": round(intent, 3),
                 "assign_confidence": round(pick.confidence, 3), "node": pick.choice}
        if intent < args.intent_floor:
            entry["reason"] = f"intent {intent:.2f} < {args.intent_floor}"
            unassigned.append(entry)
        elif pick.choice == NONE_OPTION:
            entry["reason"] = "fits no node"
            unassigned.append(entry)
        elif pick.confidence < args.assign_confidence:
            entry["reason"] = (f"nodes not distinguishable by this query "
                               f"(confidence {pick.confidence:.2f})")
            unassigned.append(entry)
        else:
            clusters[pick.choice].append(entry)

    # Every number below is computed here, never asked of the model.
    summary = {}
    for nid, kws in clusters.items():
        volumes = [k["search_volume"] for k in kws]
        cpcs = [k["cpc"] for k in kws if k["cpc"] is not None and k["cpc"] > 0]
        summary[nid] = {
            "title": nodes[nid].get("title"),
            "keywords": len(kws),
            "volume_total": int(sum(volumes)),
            "volume_top": int(max(volumes)) if volumes else 0,
            "cpc_median": round(statistics.median(cpcs), 2) if cpcs else None,
            "cpc_max": round(max(cpcs), 2) if cpcs else None,
            "cluster": sorted(kws, key=lambda k: -k["search_volume"]),
        }

    payload = {
        "stage": "triage", "geo": args.geo, "model": result.model,
        "considered": len(candidates), "assigned": sum(len(v) for v in clusters.values()),
        "thresholds": {"intent_floor": args.intent_floor,
                       "assign_confidence": args.assign_confidence,
                       "min_volume": args.min_volume},
        "nodes": summary,
        "unassigned": sorted(unassigned, key=lambda k: -k["search_volume"]),
        "dropped_before_jev": dropped,
        "usage": result.usage.as_dict(),
    }

    lines = [f"triage — {len(rows)} rows in, {len(candidates)} judged, "
             f"{len(dropped)} filtered in code first", ""]
    lines.append(f"{'node':<6}{'kw':>5}{'volume/mo':>12}{'CPC med':>10}{'CPC max':>10}  title")
    for nid, s in sorted(summary.items()):
        cpc_med = f"${s['cpc_median']:.2f}" if s["cpc_median"] else "—"
        cpc_max = f"${s['cpc_max']:.2f}" if s["cpc_max"] else "—"
        lines.append(f"{nid:<6}{s['keywords']:>5}{s['volume_total']:>12,}"
                     f"{cpc_med:>10}{cpc_max:>10}  {s['title']}")
    lines.append(f"\nunassigned: {len(unassigned)} "
                 f"({pct(len(unassigned), len(candidates))} of judged) — "
                 f"inspect them before trusting a thin cluster")
    for row in payload["unassigned"][:5]:
        lines.append(f"  {row['keyword']:<44} {row['reason']}")
    emit(args, payload, lines)


# -------------------------------------------------------------- census

CENSUS_CLASSES = {
    "vendor": "A company selling a software product that does this job",
    "adjacent": "A software product for a neighbouring job these buyers also have",
    "marketplace": "An app store, directory, review site or marketplace listing",
    "content": "An article, blog post, listicle or comparison page, not a product",
    "community": "A forum, subreddit, Q&A thread or social post",
    "irrelevant": "Unrelated to this job",
}


def cmd_census(args):
    """Turn a SERP into the ranked seed domains the keyword harvest starts from.

    Phase 2's whole vocabulary comes from `for-site` on real competitors, so
    picking the wrong domains here poisons every cluster downstream. That
    makes classification worth a calibrated answer rather than a glance.
    """
    rows = load_rows(args.serp)
    items = []
    for row in rows:
        url = row.get("url") or row.get("link") or ""
        if not url:
            continue
        items.append({
            "title": row.get("title") or "",
            "url": url,
            "snippet": (row.get("snippet") or row.get("description") or "")[:400],
            "domain": re.sub(r"^www\.", "", (re.split(r"/+", url)[1] if "//" in url
                                             else url.split("/")[0]).lower()),
        })
    if not items:
        die("no SERP rows with a url/link field")

    questions: dict[str, jev.Question] = {}
    for i, item in enumerate(items):
        payload = {"result": {"title": item["title"], "url": item["url"],
                              "snippet": item["snippet"]}}
        questions[f"class:{i}"] = jev.Choice(
            instructions={**payload,
                          "question": "What kind of page is `result`?"},
            criteria=CENSUS_CLASSES,
        )
        questions[f"sells:{i}"] = jev.Noul(
            instructions={**payload, "job": args.job,
                          "question": "Does `result` belong to a company selling a "
                                      "product that does `job`?"},
            criteria={"true": "The page is a vendor's own site for such a product",
                      "false": "Anything else, including reviews of such products"},
        )

    client = client_for(args)
    result = client.ask({"idea": args.idea or "", "job": args.job}, questions)
    log_usage(args, result.usage, f"census {len(items)} SERP rows")

    classified = []
    for i, item in enumerate(items):
        pick = result.choice(f"class:{i}")
        sells = result.noul(f"sells:{i}").noul
        classified.append({
            **item,
            "class": pick.choice if pick.confidence >= args.census_confidence else "unclear",
            "class_confidence": round(pick.confidence, 3),
            "sells_product": round(sells, 3),
        })

    by_domain: dict[str, dict] = {}
    for row in classified:
        slot = by_domain.setdefault(row["domain"], {"domain": row["domain"], "hits": 0,
                                                    "best_sells": 0.0, "classes": []})
        slot["hits"] += 1
        slot["best_sells"] = max(slot["best_sells"], row["sells_product"])
        slot["classes"].append(row["class"])

    seeds = sorted(
        (d for d in by_domain.values() if d["best_sells"] >= args.sells_floor),
        key=lambda d: (-d["best_sells"], -d["hits"], d["domain"]),
    )
    counts: dict[str, int] = {}
    for row in classified:
        counts[row["class"]] = counts.get(row["class"], 0) + 1

    payload = {"stage": "census", "model": result.model, "results": classified,
               "class_counts": counts, "seed_domains": seeds,
               "usage": result.usage.as_dict()}

    lines = [f"census — {len(items)} results classified", ""]
    lines.append("  " + " · ".join(f"{k} {v}" for k, v in sorted(counts.items())))
    lines.append(f"\nseed domains for `keywords.py for-site` (top {min(5, len(seeds))} "
                 f"of {len(seeds)}; 1-3 is the whole budget):")
    for d in seeds[:5]:
        lines.append(f"  {d['domain']:<34} sells {d['best_sells']:.2f} · {d['hits']} result(s)")
    if not seeds:
        lines.append("  none cleared the floor — this SERP is content, not vendors. "
                     "That is itself a finding: no one is selling here.")
    emit(args, payload, lines)


# ------------------------------------------------------------- reviews

SEVERITY = [
    "A preference or nice-to-have",
    "An annoyance they work around",
    "A recurring cost in time or money",
    "It blocks the job; they are looking for something else",
]


def cmd_reviews(args):
    """Mine incumbent reviews for the pain, for willingness-to-pay, and for themes.

    The output is a hit *rate* plus five quotes, not 200 reviews — the agent
    reads the rate, and the quotes are there so a human can check the rate.
    """
    rows = load_rows(args.reviews)
    themes = [t.strip() for t in (args.themes or "").split(",") if t.strip()]
    reviews = []
    for row in rows:
        text = (row.get("review_text") or row.get("text") or row.get("content") or "").strip()
        if not text:
            continue
        reviews.append({
            "rating": num(row.get("rating")),
            "title": (row.get("title") or "").strip(),
            "text": text[: args.max_chars],
            "date": row.get("timestamp") or row.get("date") or "",
        })
    if not reviews:
        die("no reviews with a review_text/text/content field")
    if len(reviews) > args.limit:
        reviews = reviews[: args.limit]

    theme_criteria = {t: f"The review is mainly about: {t}" for t in themes}
    theme_criteria["other"] = "None of the listed themes"

    questions: dict[str, jev.Question] = {}
    for i, r in enumerate(reviews):
        body = {"review": {"title": r["title"], "text": r["text"], "stars": r["rating"]}}
        questions[f"pain:{i}"] = jev.Noul(
            instructions={**body, "pain": args.pain,
                          "question": "Does `review` describe the reviewer running into `pain`?"},
            criteria={"true": "The reviewer hit this specific problem",
                      "false": "The review is about something else, or is generic praise"},
        )
        questions[f"pays:{i}"] = jev.Noul(
            instructions={**body,
                          "question": "Does `review` show the reviewer pays, or has paid, "
                                      "for this product?"},
            criteria={"true": "Mentions a subscription, a price, a plan, a renewal or a refund",
                      "false": "No evidence they pay for it"},
        )
        questions[f"sev:{i}"] = jev.Score(
            instructions={**body, "question": "How badly does `review` say this costs the "
                                              "reviewer?"},
            criteria=SEVERITY,
        )
        if themes:
            questions[f"theme:{i}"] = jev.Choice(
                instructions={**body, "question": "What is `review` mainly about?"},
                criteria=theme_criteria,
            )

    client = client_for(args)
    result = client.ask({"product": args.product or "", "pain": args.pain}, questions)
    log_usage(args, result.usage, f"reviews {len(reviews)} rows")

    judged = []
    for i, r in enumerate(reviews):
        entry = {
            **r,
            "pain_hit": round(result.noul(f"pain:{i}").noul, 3),
            "pays": round(result.noul(f"pays:{i}").noul, 3),
            "severity": round(result.score(f"sev:{i}").score, 2),
            "severity_label": result.score(f"sev:{i}").label,
        }
        if themes:
            pick = result.choice(f"theme:{i}")
            entry["theme"] = pick.choice
            entry["theme_confidence"] = round(pick.confidence, 3)
        judged.append(entry)

    hits = [r for r in judged if r["pain_hit"] >= args.pain_floor]
    paying_hits = [r for r in hits if r["pays"] >= 0.5]
    theme_counts: dict[str, int] = {}
    for r in judged:
        if "theme" in r:
            theme_counts[r["theme"]] = theme_counts.get(r["theme"], 0) + 1

    quotes = sorted(hits, key=lambda r: (-r["severity"], -r["pain_hit"]))[:5]
    payload = {
        "stage": "reviews", "model": result.model, "product": args.product,
        "pain": args.pain, "reviewed": len(judged),
        "pain_hits": len(hits), "pain_hit_rate": round(len(hits) / len(judged), 3),
        "paying_pain_hits": len(paying_hits),
        "mean_severity_of_hits": round(
            statistics.fmean([r["severity"] for r in hits]), 2) if hits else None,
        "themes": theme_counts, "evidence_quotes": quotes, "reviews": judged,
        "usage": result.usage.as_dict(),
    }

    lines = [f"reviews — {len(judged)} judged for: {args.pain}", ""]
    lines.append(f"  pain hit rate      {len(hits)}/{len(judged)} ({pct(len(hits), len(judged))})")
    lines.append(f"  of those, paying   {len(paying_hits)} "
                 f"({pct(len(paying_hits), len(hits))} of hits) — the money rung")
    if payload["mean_severity_of_hits"] is not None:
        lines.append(f"  mean severity      {payload['mean_severity_of_hits']:.2f} / "
                     f"{len(SEVERITY) - 1}")
    if theme_counts:
        top = sorted(theme_counts.items(), key=lambda kv: -kv[1])
        lines.append("  themes             " + ", ".join(f"{k} {v}" for k, v in top))
    lines.append("\n  strongest evidence:")
    for q in quotes:
        lines.append(f"   {q['severity']:.1f}★sev {q['rating'] or '?'}star "
                     f"| {q['text'][:110].replace(chr(10), ' ')}…")
    emit(args, payload, lines)


# ----------------------------------------------------------- creatives

FRAMES = {
    "problem": "Leads with the problem the buyer has",
    "outcome": "Leads with the result or benefit they get",
    "price": "Leads with price, a discount, or a free tier",
    "feature": "Leads with what the product does",
    "social_proof": "Leads with customers, reviews, ratings or logos",
    "brand": "Just the brand name, with no argument",
}


def cmd_creatives(args):
    """Read what sustained advertisers actually say, and find the gap.

    A creative that has run 300+ days is someone's acquisition math working in
    public. What matters is not that they advertise but *what their proven
    copy never says* — that is the wedge nobody is currently buying.
    """
    rows = load_rows(args.creatives)
    ads = []
    for row in rows:
        copy = " ".join(str(row.get(f) or "") for f in ("title", "copy", "headline",
                                                        "description", "text")).strip()
        if not copy:
            continue
        ads.append({
            "creative_id": row.get("creative_id") or "",
            "advertiser": row.get("advertiser_name") or row.get("advertiser_id") or "",
            "copy": copy[: args.max_chars],
            "format": row.get("format") or "",
            "days_running": num(row.get("days_running")),
        })
    if not ads:
        die("no creatives with readable copy — download the PNGs and OCR them first "
            "(see .claude/skills/demandcheck/scripts/ocr_creatives.py)")
    if len(ads) > args.limit:
        ads = ads[: args.limit]

    questions: dict[str, jev.Question] = {}
    for i, ad in enumerate(ads):
        body = {"ad_copy": ad["copy"]}
        questions[f"who:{i}"] = jev.Noul(
            instructions={**body, "audience": args.who,
                          "question": "Is `ad_copy` written specifically for `audience`, "
                                      "naming them or their work?"},
            criteria={"true": "It names that audience or their specific situation",
                      "false": "It is generic, or aimed at a different audience"},
        )
        questions[f"wedge:{i}"] = jev.Noul(
            instructions={**body, "wedge": args.wedge,
                          "question": "Does `ad_copy` promise `wedge`?"},
            criteria={"true": "The copy makes that specific promise",
                      "false": "The copy never makes that promise"},
        )
        questions[f"frame:{i}"] = jev.Choice(
            instructions={**body, "question": "What does `ad_copy` lead with?"},
            criteria=FRAMES,
        )

    client = client_for(args)
    result = client.ask({"category": args.category or "", "audience": args.who}, questions)
    log_usage(args, result.usage, f"creatives {len(ads)} rows")

    judged = []
    for i, ad in enumerate(ads):
        judged.append({
            **ad,
            "targets_audience": round(result.noul(f"who:{i}").noul, 3),
            "names_wedge": round(result.noul(f"wedge:{i}").noul, 3),
            "frame": result.choice(f"frame:{i}").choice,
            "frame_confidence": round(result.choice(f"frame:{i}").confidence, 3),
        })

    sustained = [a for a in judged
                 if a["days_running"] is not None and a["days_running"] >= args.sustained_days]
    pool = sustained or judged
    wedge_named = [a for a in pool if a["names_wedge"] >= 0.5]
    targeted = [a for a in pool if a["targets_audience"] >= 0.5]
    frames: dict[str, int] = {}
    for a in pool:
        frames[a["frame"]] = frames.get(a["frame"], 0) + 1

    payload = {
        "stage": "creatives", "model": result.model, "audience": args.who,
        "wedge": args.wedge, "judged": len(judged),
        "sustained_days": args.sustained_days, "sustained": len(sustained),
        "longest_run_days": max((a["days_running"] for a in judged
                                 if a["days_running"] is not None), default=None),
        "pool": "sustained" if sustained else "all creatives (none carried run dates)",
        "wedge_named": len(wedge_named), "audience_targeted": len(targeted),
        "wedge_open": len(wedge_named) == 0,
        "frames": frames, "creatives": judged, "usage": result.usage.as_dict(),
    }

    lines = [f"creatives — {len(judged)} read, {len(sustained)} sustained "
             f"(>= {args.sustained_days}d)", ""]
    if payload["longest_run_days"]:
        lines.append(f"  longest run        {payload['longest_run_days']:.0f} days — "
                     f"someone's acquisition math works here")
    lines.append(f"  names the wedge    {len(wedge_named)}/{len(pool)} "
                 f"({pct(len(wedge_named), len(pool))}) of {payload['pool']}")
    lines.append(f"  aimed at {args.who[:22]:<22} {len(targeted)}/{len(pool)} "
                 f"({pct(len(targeted), len(pool))})")
    lines.append("  leads with         " + ", ".join(
        f"{k} {v}" for k, v in sorted(frames.items(), key=lambda kv: -kv[1])))
    lines.append("\n  " + ("WEDGE OPEN: no proven creative makes this promise — the "
                           "message nobody is buying."
                           if payload["wedge_open"] else
                           "wedge already claimed by proven copy — sharpen it or move on."))
    emit(args, payload, lines)


# --------------------------------------------------------------- score

#: Numeric bands from references/maze-method.md, computed in code because a
#: rubric with numbers in it is arithmetic, and Jev does not do arithmetic.
VOLUME_BANDS = [(100_000, 5), (10_000, 4), (1_000, 3), (1, 2), (0, 0)]

SEMANTIC_DIMENSIONS = {
    "incumbent_gap": (
        "How much room do the incumbents leave?",
        ["Incumbents are loved and fit this buyer exactly",
         "Incumbents fit well; complaints are minor",
         "Incumbents work but are generic for this buyer",
         "Incumbents are resented, or plainly not built for this buyer",
         "No incumbent seriously serves this buyer"],
    ),
    "pain_acuteness": (
        "How costly is this pain to the buyer, going by the evidence?",
        ["A preference; nobody spends on it",
         "An annoyance handled with a workaround",
         "A recurring cost in time or money",
         "It blocks paid work, or a duty they cannot skip"],
    ),
    "buyer_vocabulary": (
        "Does the keyword cluster read like buyers, or like researchers?",
        ["Definitions and how-tos — people learning, not buying",
         "Mixed: some tool-shopping among the reading",
         "Mostly tool-shopping language",
         "Buying language: pricing, comparisons, 'best X for Y'"],
    ),
}

#: Blend weights. The measured half is the numbers instruments produced; the
#: judged half is what those numbers mean. Both are needed: volume with no
#: acute pain is a research audience, acute pain with no volume is a hobby.
WEIGHT_MEASURED = 0.6
WEIGHT_JUDGED = 0.4


def volume_band(volume: float) -> int:
    for floor, band in VOLUME_BANDS:
        if volume >= floor:
            return band
    return 0


def measured_band(volume: float, cpc: float, sustained: float) -> tuple[float, str]:
    """The numeric half of the demand rubric, kept whole in code.

    Bands 4 and 5 in references/maze-method.md already *require* a live
    auction or a sustained advertiser, so paying a bonus on top of them
    counts the same evidence twice. Below band 4 that evidence is news, and
    it lifts the score — but never to "heavy", which volume alone decides.
    Volume with nobody bidding is attention, not demand, so it is demoted.
    """
    band = volume_band(volume)
    auction, sustainer = cpc > 0, sustained >= 1
    if band >= 4:
        if not auction and not sustainer:
            return max(0.0, band - 1.0), "volume but no auction and no sustainer — attention, not spend"
        return float(band), "volume, auction and sustainers as the band requires"
    bonus = (0.5 if auction else 0.0) + (0.5 if sustainer else 0.0)
    if not bonus:
        return float(band), "no auction, no sustained advertiser"
    return min(4.0, band + bonus), "money already moves here despite modest volume"


def build_evidence(args) -> dict[str, dict]:
    """Assemble the per-node evidence record, mostly from banked stage output.

    Hand-assembling this was a step where v1 lost time and introduced typos.
    A triage file already holds every number this stage needs, so `--triage`
    derives the record and `--merge NODE=file.json` folds in that node's
    reviews/creatives findings. `--evidence` stays for the hand-written case.
    """
    evidence: dict[str, dict] = {}
    if args.evidence:
        with open(args.evidence, encoding="utf-8") as fh:
            loaded = json.load(fh)
        if not isinstance(loaded, dict) or not loaded:
            die(f"{args.evidence}: expected an object of node id -> evidence")
        evidence.update(loaded)

    if args.triage:
        with open(args.triage, encoding="utf-8") as fh:
            triage = json.load(fh)
        if triage.get("stage") != "triage":
            die(f"{args.triage}: not a triage output (run `judge.py triage --out` first)")
        for nid, s in (triage.get("nodes") or {}).items():
            cluster = s.get("cluster") or []
            evidence.setdefault(nid, {}).update({
                "title": s.get("title"),
                "keywords": s.get("keywords"),
                "volume_total": s.get("volume_total"),
                "cpc_median": s.get("cpc_median"),
                "cpc_max": s.get("cpc_max"),
                "top_keywords": [k["keyword"] for k in cluster[:12]],
            })

    for spec in args.merge or []:
        if "=" not in spec:
            die(f"--merge takes NODE=path.json, got {spec!r}")
        nid, path = spec.split("=", 1)
        nid = nid.strip().upper()
        with open(path, encoding="utf-8") as fh:
            banked = json.load(fh)
        stage = banked.get("stage", "finding")
        slot = evidence.setdefault(nid, {})
        if stage == "reviews":
            slot["review_findings"] = {
                "reviewed": banked.get("reviewed"),
                "pain_hit_rate": banked.get("pain_hit_rate"),
                "paying_pain_hits": banked.get("paying_pain_hits"),
                "mean_severity_of_hits": banked.get("mean_severity_of_hits"),
                "themes": banked.get("themes"),
                "quotes": [q.get("text", "")[:200]
                           for q in (banked.get("evidence_quotes") or [])[:4]],
            }
        elif stage == "creatives":
            slot["sustained_advertisers"] = banked.get("sustained")
            slot["ad_findings"] = {
                "longest_run_days": banked.get("longest_run_days"),
                "wedge_open": banked.get("wedge_open"),
                "wedge_named": banked.get("wedge_named"),
                "audience_targeted": banked.get("audience_targeted"),
                "frames": banked.get("frames"),
            }
        else:
            slot[stage] = banked

    if not evidence:
        die("nothing to score — pass --triage, --evidence, or both")
    if args.nodes:
        wanted = {n.strip().upper() for n in args.nodes.split(",") if n.strip()}
        evidence = {k: v for k, v in evidence.items() if k in wanted}
        if not evidence:
            die("--nodes matched nothing in the evidence")
    return evidence


def cmd_score(args):
    """Score a node 0-5 on demand: code scores the numbers, Jev scores the meaning.

    This is the composite-scoring pattern. The numeric rubric bands are pure
    arithmetic and stay here. Jev rates three semantic dimensions it is
    actually good at, this function normalises them to 0-1, and the weights
    are visible and overridable rather than hidden in a prompt.
    """
    evidence = build_evidence(args)

    questions: dict[str, jev.Question] = {}
    for nid, ev in evidence.items():
        for dim, (question, levels) in SEMANTIC_DIMENSIONS.items():
            questions[f"{dim}:{nid}"] = jev.Score(
                instructions={"node": ev, "question": question},
                criteria=levels,
            )

    client = client_for(args)
    result = client.ask({"idea": args.idea or "", "geo": args.geo}, questions)
    log_usage(args, result.usage, f"score {len(evidence)} nodes")

    scored = {}
    for nid, ev in evidence.items():
        volume = float(ev.get("volume_total") or 0)
        cpc = num(ev.get("cpc_median")) or 0.0
        sustained = float(ev.get("sustained_advertisers") or 0)
        band = volume_band(volume)
        measured, band_note = measured_band(volume, cpc, sustained)

        dims = {}
        for dim in SEMANTIC_DIMENSIONS:
            answer = result.score(f"{dim}:{nid}")
            dims[dim] = {"score": round(answer.score, 2),
                         "normalized": round(answer.normalized, 3),
                         "confidence": round(answer.confidence, 3),
                         "label": answer.label}
        judged = 5.0 * statistics.fmean(d["normalized"] for d in dims.values())
        blended = WEIGHT_MEASURED * measured + WEIGHT_JUDGED * judged
        demand = max(0, min(5, int(round(blended))))
        low_confidence = [d for d, v in dims.items() if v["confidence"] < args.confidence_floor]

        scored[nid] = {
            "demand": demand, "blended": round(blended, 2),
            "measured_component": round(measured, 2), "volume_band": band,
            "band_note": band_note, "judged_component": round(judged, 2),
            "dimensions": dims, "low_confidence_dimensions": low_confidence,
            "evidence": ev,
        }

    payload = {"stage": "score", "model": result.model,
               "weights": {"measured": WEIGHT_MEASURED, "judged": WEIGHT_JUDGED},
               "nodes": scored, "usage": result.usage.as_dict()}

    lines = ["score — measured numbers blended with judged meaning", ""]
    lines.append(f"{'node':<6}{'demand':>7}{'measured':>10}{'judged':>8}   dimensions")
    for nid, s in sorted(scored.items()):
        dims = " ".join(f"{d[:4]}={v['normalized']:.2f}" for d, v in s["dimensions"].items())
        lines.append(f"{nid:<6}{s['demand']:>7}{s['measured_component']:>10.2f}"
                     f"{s['judged_component']:>8.2f}   {dims}")
    lines.append("")
    for nid, s in sorted(scored.items()):
        if s["low_confidence_dimensions"]:
            lines.append(f"  {nid}: low confidence on "
                         f"{', '.join(s['low_confidence_dimensions'])} — the evidence "
                         f"does not settle it; buy the missing measurement or say so.")
    lines.append("  apply with:")
    for nid, s in sorted(scored.items()):
        lines.append(f"    maze.py set {nid} --demand {s['demand']} --status probed "
                     f"--note \"measured {s['measured_component']:.1f} / judged "
                     f"{s['judged_component']:.1f}\"")
    emit(args, payload, lines)


# ------------------------------------------------------------- explain

PREMISE_RE = re.compile(r"^\s*[-*]?\s*\**\s*(X\d+)\**\s*[:.—-]\s*(.+?)\s*$")

SPECIFICITY = [
    "True of almost any software buyer",
    "True of a broad group, such as anyone who writes things up at work",
    "True of a recognisable trade or profession",
    "True only of this buyer, in their specific working conditions",
]


def parse_premises(path: str) -> dict[str, str]:
    """Pull X1/X2/… out of a card, joining wrapped lines.

    Cards are written for humans and their premises wrap, so a line-at-a-time
    parser silently truncates half of one and then judges the half.
    """
    with open(path, encoding="utf-8") as fh:
        lines = fh.read().splitlines()
    premises: dict[str, list[str]] = {}
    current: str | None = None
    for line in lines:
        m = PREMISE_RE.match(line)
        if m:
            current = m.group(1)
            premises[current] = [m.group(2)]
            continue
        if current is None:
            continue
        stripped = line.strip()
        # A premise ends at a blank line, a heading, or the next list item.
        if not stripped or stripped.startswith(("#", "|", ">")) or \
                re.match(r"^[-*+]\s|^\d+[.)]\s", stripped):
            current = None
            continue
        if line[:1].isspace():
            premises[current].append(stripped)
        else:
            current = None
    return {pid: " ".join(parts) for pid, parts in premises.items()}


def cmd_explain(args):
    """Put Deutsch's hard-to-vary criterion under a calibrated instrument.

    An explanation that survives having its parts swapped explains nothing —
    it was never about *these* people. v1 asked the agent to notice that about
    its own story, which is the one judgment an author is worst placed to make.

    Three atomic questions, composed here rather than in a prompt. Asking a
    single "how hard to vary is this" Score instead bundles three dimensions
    into one rubric and comes back at 0.14 confidence — the model correctly
    reporting that the question was unanswerable as put.

      swap        code rewrites the explanation with a decoy buyer and asks,
                  cold, whether it still reads true. High = it varies freely.
      forbids     does each premise rule out an observation we could make?
      specificity how narrow is each premise? Points at the weak clause.
      single      does each premise make exactly one claim? A bundled premise
                  cannot be refuted — half of it survives any result.
    """
    premises = parse_premises(args.card)
    if not premises:
        die(f"no premises found in {args.card}. Write them as lines like "
            f"'- X1: therapists must file a compliant note per session'.")
    decoys = [d.strip() for d in (args.decoys or "").split(",") if d.strip()]
    if not decoys:
        die("--decoys is required: 2-5 other buyers this explanation must NOT fit, "
            "e.g. --decoys 'freelance designers,truck drivers,retail managers'")

    explanation = " ".join(premises.values())
    questions: dict[str, jev.Question] = {}
    for pid, text in premises.items():
        body = {"premise": text, "buyer": args.who}
        questions[f"forbids:{pid}"] = jev.Noul(
            instructions={**body,
                          "question": "Does `premise` rule out something we could go and "
                                      "observe?"},
            criteria={"true": "There is an observation that would show it false",
                      "false": "No observation could contradict it"},
        )
        questions[f"specific:{pid}"] = jev.Score(
            instructions={**body, "question": "Who is `premise` true of?"},
            criteria=SPECIFICITY,
        )
        questions[f"single:{pid}"] = jev.Noul(
            instructions={**body,
                          "question": "Does `premise` make exactly one claim?"},
            criteria={"true": "One claim, which one observation could settle",
                      "false": "Two or more claims joined together, so part of it "
                               "would survive any single result"},
        )
    for i, decoy in enumerate(decoys):
        questions[f"swap:{i}"] = jev.Noul(
            instructions={"explanation": explanation, "other_buyer": decoy,
                          "question": "Read `explanation` with `other_buyer` in place of "
                                      "the buyer it names. Does it still read as true?"},
            criteria={"true": "It reads just as true of the other buyer",
                      "false": "It becomes false or obviously ill-fitting"},
        )

    client = client_for(args)
    result = client.ask({"buyer": args.who, "idea": args.idea or ""}, questions)
    log_usage(args, result.usage, f"explain {len(premises)} premises, {len(decoys)} decoys")

    swaps = {decoys[i]: round(result.noul(f"swap:{i}").noul, 3) for i in range(len(decoys))}
    swap_mean = statistics.fmean(swaps.values())

    detail = {}
    for pid, text in premises.items():
        spec = result.score(f"specific:{pid}")
        forbids = result.noul(f"forbids:{pid}").noul
        single = result.noul(f"single:{pid}").noul
        # Blocking faults are the ones that make an experiment unable to fail.
        # A mildly compound premise is worth saying out loud but is not a
        # reason to stop, or nothing with a subordinate clause would ever pass.
        faults, notes = [], []
        if forbids < args.forbid_floor:
            faults.append("forbids nothing — no observation could refute it")
        if spec.normalized < args.specific_floor:
            faults.append(f"too broad — {spec.label.lower()}")
        if single < args.single_floor:
            faults.append("bundles several claims — split it so one result can kill one claim")
        elif single < 0.5:
            notes.append("mildly compound; a miss will not say which half died")
        detail[pid] = {"text": text, "forbids": round(forbids, 3),
                       "specificity": round(spec.normalized, 3),
                       "specificity_label": spec.label,
                       "specificity_confidence": round(spec.confidence, 3),
                       "single_claim": round(single, 3),
                       "faults": faults, "notes": notes}

    faulty = [pid for pid, d in detail.items() if d["faults"]]
    # Composed here, from three atomic measurements, so the reasoning is legible.
    if swap_mean >= args.swap_ceiling:
        verdict = "VARIES"
        note = (f"it reads true of unrelated buyers (mean {swap_mean:.2f}) — this is an "
                f"explanation about software in general, not about {args.who}")
    elif faulty:
        verdict = "SOFT"
        note = (f"specific to {args.who}, but {len(faulty)} premise(s) cannot be refuted "
                f"as written: {', '.join(faulty)}")
    else:
        verdict = "HARD"
        note = "specific, falsifiable premise by premise, and it does not fit the decoys"

    payload = {"stage": "explain", "model": result.model, "who": args.who,
               "verdict": verdict, "note": note, "premises": detail,
               "faulty_premises": faulty,
               "swap_test": swaps, "swap_mean": round(swap_mean, 3),
               "thresholds": {"swap_ceiling": args.swap_ceiling,
                              "forbid_floor": args.forbid_floor,
                              "specific_floor": args.specific_floor,
                              "single_floor": args.single_floor},
               "usage": result.usage.as_dict()}

    lines = [f"explain — {verdict}: {note}", ""]
    lines.append(f"  swap test      mean {swap_mean:.2f} (ceiling {args.swap_ceiling}) — "
                 f"P(still true of someone else)")
    for decoy, p in sorted(swaps.items(), key=lambda kv: -kv[1]):
        flag = "  <- still true of them" if p >= args.swap_ceiling else ""
        lines.append(f"     {p:.2f}  {decoy}{flag}")
    lines.append(f"\n  {'premise':<5}{'forbids':>9}{'specific':>10}{'1 claim':>9}   text")
    for pid, d in sorted(detail.items()):
        lines.append(f"  {pid:<5}{d['forbids']:>9.2f}{d['specificity']:>10.2f}"
                     f"{d['single_claim']:>9.2f}   {d['text'][:52]}")
    for pid, d in sorted(detail.items()):
        for fault in d["faults"]:
            lines.append(f"     {pid}: {fault}")
        for note in d["notes"]:
            lines.append(f"     {pid}: (note) {note}")
    if verdict != "HARD":
        lines.append("\n  Sharpen before spending: thresholds are derived from premises, so "
                     "a premise no result can kill buys an experiment that can only confirm.")
    emit(args, payload, lines)


# ------------------------------------------------------------- verdict

OPS = {
    ">=": lambda m, t: m >= t, ">": lambda m, t: m > t,
    "<=": lambda m, t: m <= t, "<": lambda m, t: m < t,
    "==": lambda m, t: m == t,
}

#: Where the node's keywords came from. judge.py triage harvests them from
#: competitor footprints; anything the agent wrote from imagination is
#: "guessed", and a null result on a guessed cluster impeaches the guess.
CLUSTER_SOURCE = {
    "harvested": "Harvested from competitor footprints and live ad copy, so the "
                 "terms are ones the market already uses",
    "guessed": "Written from imagination rather than harvested, so a zero here "
               "may only mean the terms are wrong",
    "unknown": "Not recorded",
}

NULL_EXPLANATIONS = {
    "demand_absent": "These buyers really do not look for a product like this",
    "instrument_blind": "The pain is real but this instrument cannot see it — "
                        "the buying never passes through the channel measured",
    "geo_mismatch": "The demand exists somewhere this measurement did not cover",
    "guessed_cluster": "The keywords were invented rather than harvested, so the "
                       "cluster measures the guess, not the market",
    "wrong_vocabulary": "These buyers call it something else",
}


def cmd_verdict(args):
    """Turn pre-registered thresholds plus measurements into one of three words.

    The threshold comparisons are arithmetic and happen here, exactly as
    pre-registered. Jev answers only the two questions that are genuinely
    semantic, and its confidence routes the hard case: a null result only
    becomes REFUTED when the model is confident demand is actually absent.
    Below that floor it is INCONCLUSIVE, which names the missing measurement
    instead of retiring someone's idea on an instrument's blind spot.
    """
    with open(args.thresholds, encoding="utf-8") as fh:
        spec = json.load(fh)
    checks = spec.get("thresholds") or spec
    if not isinstance(checks, dict) or not checks:
        die(f"{args.thresholds}: expected {{name: {{op, value, measured, premise}}}}")

    results = []
    for name, c in checks.items():
        op = c.get("op", ">=")
        if op not in OPS:
            die(f"threshold {name!r}: op must be one of {', '.join(OPS)}")
        measured, target = c.get("measured"), c.get("value")
        if measured is None:
            results.append({"name": name, "status": "unmeasured", "op": op,
                            "value": target, "measured": None,
                            "premise": c.get("premise")})
            continue
        passed = OPS[op](float(measured), float(target))
        results.append({"name": name, "status": "pass" if passed else "fail", "op": op,
                        "value": target, "measured": measured,
                        "premise": c.get("premise")})

    failed = [r for r in results if r["status"] == "fail"]
    unmeasured = [r for r in results if r["status"] == "unmeasured"]
    families = [f.strip() for f in (args.families or "").split(",") if f.strip()]

    premises = parse_premises(args.card) if args.card else {}
    measurement_summary = {r["name"]: {"measured": r["measured"], "required":
                                       f"{r['op']} {r['value']}", "status": r["status"]}
                           for r in results}

    # Ask about contradiction, not confirmation. An experiment measures a few
    # thresholds; most premises it never touches. "Is every premise supported?"
    # therefore fails a perfectly healthy card, because silence reads as
    # absence. Survival is what the method actually asks for, so ask for that —
    # and ask it in the direction the threshold runs, since P(noul) and
    # 1 - P(negated noul) are not interchangeable on this model.
    contradiction_criteria = {
        "true": "At least one measurement is inconsistent with what it claims",
        "false": "Nothing measured is inconsistent with it — including measurements "
                 "that say nothing about it either way",
    }
    explanation_text = " ".join(premises.values()) or args.explanation or ""
    questions: dict[str, jev.Question] = {
        "contradicted": jev.Noul(
            instructions={"explanation": explanation_text,
                          "measurements": measurement_summary,
                          "question": "Does anything in `measurements` contradict a claim "
                                      "made in `explanation`?"},
            criteria=contradiction_criteria,
        ),
    }
    # Per-premise, so a refutation names the premise it killed — that is what
    # propagates through the rest of the maze at TRAVERSE.
    tested_premises = sorted({r["premise"] for r in results if r.get("premise")}
                             & set(premises))
    for pid in tested_premises:
        relevant = {r["name"]: measurement_summary[r["name"]]
                    for r in results if r.get("premise") == pid}
        questions[f"kills:{pid}"] = jev.Noul(
            instructions={"premise": premises[pid], "measurements": relevant,
                          "question": "Does anything in `measurements` contradict "
                                      "`premise`?"},
            criteria=contradiction_criteria,
        )
    if failed or unmeasured:
        # Where the cluster came from is a fact the lab knows, not something
        # to leave the model guessing at: a harvested cluster rules out the
        # "you invented the keywords" reading, and a guessed one all but
        # forces it. Saying so is the difference between a routed decision
        # and a coin flip.
        questions["why_null"] = jev.Choice(
            instructions={"missed": [r["name"] for r in failed + unmeasured],
                          "measurements": measurement_summary,
                          "buyer": args.who or "",
                          "instruments": args.instruments or "",
                          "keyword_cluster_source": CLUSTER_SOURCE[args.cluster_source],
                          "question": "What best explains the misses in `missed`?"},
            criteria=NULL_EXPLANATIONS,
        )

    client = client_for(args)
    result = client.ask({"buyer": args.who or "", "geo": args.geo}, questions)
    log_usage(args, result.usage, "verdict")

    contradicted = result.noul("contradicted").noul
    explanation_held = contradicted < args.contradiction_ceiling
    dead_premises = [pid for pid in tested_premises
                     if result.noul(f"kills:{pid}").noul >= args.contradiction_ceiling]
    why = result.choice("why_null") if "why_null" in result else None

    # The decision table. Every branch is here, in code, so a verdict can be
    # re-derived from the banked JSON without re-running anything.
    # Route on the probability mass sitting on "demand_absent", not on the
    # answer's confidence. Confidence describes the *shape* of the whole
    # distribution across five options; what this branch needs to know is how
    # much the model puts on this one reading. A thin spread over four
    # instrument-failure options and a peak on absent demand are the same
    # confidence and opposite decisions.
    p_absent = (why.probabilities.get("demand_absent", 0.0) if why else 0.0)
    if failed:
        if why and why.choice == "demand_absent" and p_absent >= args.refute_probability:
            verdict = "REFUTED"
            killed = dead_premises or sorted({r["premise"] for r in failed if r["premise"]})
            because = (f"{', '.join(r['name'] for r in failed)} missed, and the best "
                       f"explanation is absent demand "
                       f"(P={p_absent:.2f}); premise(s) "
                       f"{', '.join(killed) or '—'} died — sweep the maze for nodes "
                       f"leaning on them")
        else:
            verdict = "INCONCLUSIVE"
            label = why.choice if why else "unknown"
            because = (f"{', '.join(r['name'] for r in failed)} missed, but the miss is "
                       f"better explained by {label}"
                       + (f" (P={why.probabilities.get(label, 0.0):.2f}, "
                          f"absent-demand only P={p_absent:.2f})" if why else "")
                       + " — demand that is not there and demand this instrument cannot "
                         "see do not share a verdict word")
    elif unmeasured:
        verdict = "INCONCLUSIVE"
        because = (f"never measured: {', '.join(r['name'] for r in unmeasured)} — "
                   f"buy that measurement or park the node saying so")
    elif len(families) < args.families_min:
        verdict = "INCONCLUSIVE"
        because = (f"only {len(families)} signal family survived kill attempts "
                   f"({', '.join(families) or 'none'}); the bar is {args.families_min}")
    elif not explanation_held:
        verdict = "INCONCLUSIVE"
        because = (f"every threshold met, but the measurements contradict the "
                   f"explanation (P={contradicted:.2f}"
                   + (f", premise(s) {', '.join(dead_premises)}" if dead_premises else "")
                   + ") — good numbers with no surviving explanation are usually an "
                     "instrument artifact")
    else:
        verdict = "VALIDATED"
        because = (f"all {len(results)} thresholds met, kill attempts survived from "
                   f"{len(families)} families ({', '.join(families)}), explanation "
                   f"uncontradicted (P={contradicted:.2f})")

    payload = {"stage": "verdict", "model": result.model, "verdict": verdict,
               "because": because, "thresholds": results,
               "explanation_contradicted": {"p": round(contradicted, 3),
                                            "ceiling": args.contradiction_ceiling,
                                            "held": explanation_held},
               "premises_contradicted": dead_premises,
               "premises_tested": tested_premises,
               "families_survived": families,
               "null_explanation": ({"choice": why.choice,
                                     "p_demand_absent": round(p_absent, 3),
                                     "refute_probability": args.refute_probability,
                                     "confidence": round(why.confidence, 3),
                                     "probabilities": {k: round(v, 3)
                                                       for k, v in why.probabilities.items()}}
                                    if why else None),
               "cac_note": "CAC is measured by cac.py and reported, never graded. "
                           "Whether it is worth paying is the user's call.",
               "usage": result.usage.as_dict()}

    lines = [f"verdict — {verdict}", f"  {because}", ""]
    for r in results:
        mark = {"pass": "PASS", "fail": "FAIL", "unmeasured": "----"}[r["status"]]
        prem = f" [{r['premise']}]" if r.get("premise") else ""
        got = "not measured" if r["measured"] is None else r["measured"]
        lines.append(f"  {mark}  {r['name']:<28} need {r['op']} {r['value']}, got {got}{prem}")
    lines.append(f"\n  explanation contradicted  P={contradicted:.2f} "
                 f"(ceiling {args.contradiction_ceiling}) — "
                 f"{'survives' if explanation_held else 'does not survive'}")
    for pid in tested_premises:
        p_kill = result.noul(f"kills:{pid}").noul
        flag = "  <- dead" if pid in dead_premises else ""
        lines.append(f"     {p_kill:.2f}  {pid} contradicted by its own thresholds{flag}")
    if why:
        lines.append("  best read of misses   " + ", ".join(
            f"{k} {v:.2f}" for k, v in sorted(why.probabilities.items(),
                                              key=lambda kv: -kv[1]) if v >= 0.01))
        lines.append(f"                        P(demand_absent)={p_absent:.2f}, "
                     f"refute at >= {args.refute_probability}")
    if verdict == "VALIDATED":
        lines.append("\n  Next: price it — cac.py. VALIDATED means demand is real and "
                     "CAC is about to be measured, not that the CAC is acceptable.")
    emit(args, payload, lines)


# ----------------------------------------------------------------- CLI

def add_common(sp, *, lab=True):
    if lab:
        sp.add_argument("--lab", help="lab directory (auto-discovered if omitted)")
        sp.add_argument("--root", default=mazelib.DEFAULT_ROOT,
                        help=argparse.SUPPRESS)
    sp.add_argument("--out", help="bank the typed result as JSON here")
    sp.add_argument("--cache-dir", help="jev cache (default <lab>/.jev-cache)")
    sp.add_argument("--no-cache", action="store_true", help="force fresh judgments")
    sp.add_argument("--concurrency", type=int, default=jev.DEFAULT_CONCURRENCY)
    sp.add_argument("--model", help=f"override the model (default {jev.DEFAULT_MODEL})")


def main(argv: Sequence[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        prog="judge.py", description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="stage", required=True)

    sp = sub.add_parser("triage", help="keywords -> per-node clusters, intent-gated")
    sp.add_argument("--keywords", required=True, help="CSV/JSON from keywords.py")
    sp.add_argument("--nodes", help="comma-separated node ids (default: all)")
    sp.add_argument("--idea", help="the idea, for context")
    sp.add_argument("--geo", default="US")
    sp.add_argument("--brands", help="comma-separated competitor brand words to drop")
    sp.add_argument("--min-volume", type=float, default=10,
                    help="drop keywords below this monthly volume before judging")
    sp.add_argument("--limit", type=int, default=600, help="max keywords to judge")
    sp.add_argument("--intent-floor", type=float, default=INTENT_FLOOR)
    sp.add_argument("--assign-confidence", type=float, default=ASSIGN_CONFIDENCE)
    add_common(sp)
    sp.set_defaults(fn=cmd_triage)

    sp = sub.add_parser("census", help="SERP rows -> ranked competitor seed domains")
    sp.add_argument("--serp", required=True, help="JSON/CSV of SERP results")
    sp.add_argument("--job", required=True, help="the job-to-be-done, in the buyer's words")
    sp.add_argument("--idea")
    sp.add_argument("--census-confidence", type=float, default=CENSUS_CONFIDENCE)
    sp.add_argument("--sells-floor", type=float, default=0.5)
    add_common(sp)
    sp.set_defaults(fn=cmd_census)

    sp = sub.add_parser("reviews", help="app reviews -> pain rate, WTP, themes")
    sp.add_argument("--reviews", required=True, help="CSV/JSON from appstore.py reviews")
    sp.add_argument("--pain", required=True, help="the pain to look for, one sentence")
    sp.add_argument("--product", help="whose reviews these are")
    sp.add_argument("--themes", help="comma-separated themes to classify into")
    sp.add_argument("--limit", type=int, default=250)
    sp.add_argument("--max-chars", type=int, default=700,
                    help="truncate each review; irrelevant text costs accuracy")
    sp.add_argument("--pain-floor", type=float, default=PAIN_FLOOR)
    add_common(sp)
    sp.set_defaults(fn=cmd_reviews)

    sp = sub.add_parser("creatives", help="ad copy -> who/wedge framing, sustainers")
    sp.add_argument("--creatives", required=True, help="CSV/JSON from ads.py (or OCR output)")
    sp.add_argument("--who", required=True, help="the audience the node targets")
    sp.add_argument("--wedge", required=True, help="the promise your wedge would make")
    sp.add_argument("--category")
    sp.add_argument("--limit", type=int, default=200)
    sp.add_argument("--max-chars", type=int, default=400)
    sp.add_argument("--sustained-days", type=int, default=SUSTAINED_DAYS)
    add_common(sp)
    sp.set_defaults(fn=cmd_creatives)

    sp = sub.add_parser("score", help="evidence -> 0-5 demand score (composite)")
    sp.add_argument("--triage", help="a banked `judge.py triage --out` file; derives "
                                     "each node's volume/CPC/top keywords")
    sp.add_argument("--merge", action="append", metavar="NODE=FILE",
                    help="fold a banked reviews/creatives finding into that node "
                         "(repeatable)")
    sp.add_argument("--evidence",
                    help="hand-written JSON {node id: {volume_total, cpc_median, "
                         "sustained_advertisers, review_findings, …}}")
    sp.add_argument("--nodes", help="comma-separated node ids to score (default: all)")
    sp.add_argument("--idea")
    sp.add_argument("--geo", default="US")
    sp.add_argument("--confidence-floor", type=float, default=0.5)
    add_common(sp)
    sp.set_defaults(fn=cmd_score)

    sp = sub.add_parser("explain", help="hypothesis card -> hard-to-vary verdict")
    sp.add_argument("--card", required=True, help="path to card.md with X1/X2/… premises")
    sp.add_argument("--who", required=True, help="the buyer the explanation is about")
    sp.add_argument("--decoys", required=True,
                    help="2-5 other buyers it must NOT fit, comma-separated")
    sp.add_argument("--idea")
    sp.add_argument("--swap-ceiling", type=float, default=0.5,
                    help="mean P(still true of a decoy) at or above this = VARIES")
    sp.add_argument("--forbid-floor", type=float, default=0.5)
    sp.add_argument("--specific-floor", type=float, default=0.5)
    sp.add_argument("--single-floor", type=float, default=0.25,
                    help="P(premise makes one claim) below this blocks; 0.25-0.5 "
                         "is reported as a note")
    add_common(sp)
    sp.set_defaults(fn=cmd_explain)

    sp = sub.add_parser("verdict", help="thresholds + measurements -> the verdict")
    sp.add_argument("--thresholds", required=True,
                    help="JSON {name: {op, value, measured, premise}} from the card")
    sp.add_argument("--card", help="card.md, to read the premises")
    sp.add_argument("--explanation", help="the explanation, if not in a card")
    sp.add_argument("--families", help="comma-separated families whose kill attempts it survived")
    sp.add_argument("--families-min", type=int, default=2)
    sp.add_argument("--who")
    sp.add_argument("--geo", default="US")
    sp.add_argument("--instruments", help="which instruments ran, for the blindness read")
    sp.add_argument("--cluster-source", choices=sorted(CLUSTER_SOURCE), default="unknown",
                    help="'harvested' if the cluster came from judge.py triage over "
                         "competitor footprints; 'guessed' if you wrote the terms")
    sp.add_argument("--contradiction-ceiling", type=float, default=0.5,
                    help="P(measurements contradict it) at or above this = it did "
                         "not survive")
    sp.add_argument("--refute-probability", type=float, default=REFUTE_PROBABILITY,
                    help="P(demand is genuinely absent) needed before a miss is "
                         "called REFUTED rather than INCONCLUSIVE")
    add_common(sp)
    sp.set_defaults(fn=cmd_verdict)

    args = p.parse_args(argv)
    try:
        args.fn(args)
    except jev.JevError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
