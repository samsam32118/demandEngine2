#!/usr/bin/env python3
"""pos.py — the run ledger for a positioning study. Stdlib only.

This is the ONLY writer of state.json. Hand-edited JSON drifts from the raw
files and quietly breaks the audit trail that lets the report say where every
number came from, so every state change goes through a subcommand here.

    pos.py init --url https://acme.com --slug acme --budget-usd 6
    pos.py note "wave 1: SERP on brand + alternatives"
    pos.py spend --source dataforseo-keywords --op for-site --usd 0.07 --detail acme.com
    pos.py add --kind alternative --name "Notion" --domain notion.so --via "SERP: acme alternatives"
    pos.py set  --id alt:notion.so --status collected --score 0.8
    pos.py assume add --text "..." --forbids "..." --check "..."
    pos.py assume judge A1 --status refuted --evidence "..."
    pos.py frontier --kind alternative --limit 8
    pos.py status

Run dirs live at research/positioning/<slug>/ and are auto-discovered when
exactly one exists.
"""

import argparse
import json
import os
import re
import sys
import time
from datetime import datetime, timezone

ROOT = "research/positioning"
KINDS = ("alternative", "segment", "frame", "page", "keyword-set", "app")
STATUSES = ("candidate", "queued", "collected", "dropped")


# ------------------------------------------------------------------ plumbing

def now():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def die(msg, code=2):
    print(f"error: {msg}", file=sys.stderr)
    sys.exit(code)


def slugify(text):
    s = re.sub(r"[^a-z0-9]+", "-", str(text).lower()).strip("-")
    return s[:60] or "run"


def discover(explicit):
    """Find the run dir. Explicit wins; otherwise the single run under ROOT."""
    if explicit:
        return explicit
    env = os.environ.get("POSITIONING_RUN")
    if env:
        return env
    if not os.path.isdir(ROOT):
        die(f"no {ROOT}/ — run `pos.py init` first")
    runs = sorted(d for d in os.listdir(ROOT) if os.path.isdir(os.path.join(ROOT, d)))
    if not runs:
        die(f"no runs under {ROOT}/ — run `pos.py init` first")
    if len(runs) > 1:
        die(f"{len(runs)} runs under {ROOT}/ ({', '.join(runs)}) — pass --run")
    return os.path.join(ROOT, runs[0])


def state_path(run):
    return os.path.join(run, "state.json")


def load(run):
    p = state_path(run)
    if not os.path.isfile(p):
        die(f"no state.json in {run} — run `pos.py init` first")
    with open(p, encoding="utf-8") as f:
        return json.load(f)


def save(run, st):
    st["updated"] = now()
    p = state_path(run)
    tmp = p + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(st, f, indent=2, ensure_ascii=False)
    os.replace(tmp, p)


def notebook(run, text):
    with open(os.path.join(run, "notebook.md"), "a", encoding="utf-8") as f:
        f.write(f"\n### {now()}\n\n{text.rstrip()}\n")


def node_id(kind, key):
    return f"{ 'alt' if kind == 'alternative' else kind[:4] }:{slugify(key)}"


# -------------------------------------------------------------------- init

def cmd_init(a):
    slug = a.slug or slugify(re.sub(r"^https?://(www\.)?", "", a.url).split("/")[0])
    run = a.run or os.path.join(ROOT, slug)
    for sub in ("raw/site", "raw/serp", "raw/keywords", "raw/ads", "raw/reviews",
                "receipts", "clean", "charts", "creatives", "extract"):
        os.makedirs(os.path.join(run, sub), exist_ok=True)
    if os.path.isfile(state_path(run)) and not a.force:
        die(f"{run} already initialised — pass --force to reset the ledger")
    st = {
        "slug": slug,
        "url": a.url,
        "product_name": a.name or "",
        "geo": {"location_code": a.location_code, "language_code": a.language_code},
        "budget": {"cap_usd": round(float(a.budget_usd), 2), "spent_usd": 0.0, "calls": []},
        "brightdata": {"day": datetime.now(timezone.utc).strftime("%Y-%m-%d"), "count": 0},
        "phase": "intake",
        "nodes": {},
        "assumptions": [],
        "created": now(),
        "updated": now(),
    }
    save(run, st)
    notebook(run, f"**Run opened.** Product URL `{a.url}`, budget "
                  f"${st['budget']['cap_usd']:.2f}, geo "
                  f"{a.location_code}/{a.language_code}.")
    print(json.dumps({"run": run, "slug": slug, "cap_usd": st["budget"]["cap_usd"]}, indent=2))


# ------------------------------------------------------------------- nodes

def cmd_add(a):
    run = discover(a.run)
    st = load(run)
    key = a.domain or a.name
    nid = a.id or node_id(a.kind, key)
    if nid in st["nodes"] and not a.force:
        print(json.dumps({"id": nid, "existing": True}))
        return
    st["nodes"][nid] = {
        "id": nid, "kind": a.kind, "name": a.name, "domain": a.domain or "",
        "lane": a.lane or "", "via": a.via, "status": a.status,
        "score": a.score, "notes": a.note or "", "added": now(),
    }
    save(run, st)
    print(json.dumps({"id": nid, "added": True}))


def cmd_set(a):
    run = discover(a.run)
    st = load(run)
    n = st["nodes"].get(a.id) or die(f"no node {a.id}")
    for field in ("status", "lane", "note", "domain", "name"):
        v = getattr(a, field, None)
        if v is not None:
            n["notes" if field == "note" else field] = v
    if a.score is not None:
        n["score"] = a.score
    save(run, st)
    print(json.dumps(n, indent=2))


def cmd_frontier(a):
    run = discover(a.run)
    st = load(run)
    rows = [n for n in st["nodes"].values()
            if n["status"] == "candidate" and (not a.kind or n["kind"] == a.kind)]
    rows.sort(key=lambda n: (-(n.get("score") or 0), n["name"]))
    print(json.dumps(rows[:a.limit], indent=2))


# ------------------------------------------------------------------ budget

def cmd_spend(a):
    run = discover(a.run)
    st = load(run)
    usd = 0.0 if a.cached else round(float(a.usd), 4)
    st["budget"]["calls"].append({
        "at": now(), "source": a.source, "op": a.op, "usd": usd,
        "detail": a.detail or "", "cached": bool(a.cached),
    })
    st["budget"]["spent_usd"] = round(sum(c["usd"] for c in st["budget"]["calls"]), 4)
    if a.source.startswith("brightdata") and not a.cached:
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        if st["brightdata"]["day"] != today:
            st["brightdata"] = {"day": today, "count": 0}
        st["brightdata"]["count"] += 1
    save(run, st)
    b = st["budget"]
    print(json.dumps({"spent_usd": b["spent_usd"], "cap_usd": b["cap_usd"],
                      "remaining_usd": round(b["cap_usd"] - b["spent_usd"], 4),
                      "brightdata_today": st["brightdata"]["count"]}, indent=2))


# ------------------------------------------------------------- assumptions

def cmd_assume(a):
    run = discover(a.run)
    st = load(run)
    if a.action == "add":
        aid = f"A{len(st['assumptions']) + 1}"
        st["assumptions"].append({
            "id": aid, "text": a.text, "forbids": a.forbids, "check": a.check,
            "status": "open", "evidence": "", "added": now(),
        })
        save(run, st)
        notebook(run, f"**Assumption {aid}** — {a.text}\n\n- forbids: {a.forbids}\n- check: {a.check}")
        print(json.dumps({"id": aid}, indent=2))
        return
    if a.action == "judge":
        for c in st["assumptions"]:
            if c["id"] == a.cid:
                c["status"] = a.status
                c["evidence"] = a.evidence or ""
                c["judged"] = now()
                save(run, st)
                notebook(run, f"**{a.cid} → {a.status}.** {a.evidence or ''}")
                print(json.dumps(c, indent=2))
                return
        die(f"no assumption {a.cid}")
    print(json.dumps(st["assumptions"], indent=2))


# ----------------------------------------------------------------- receipts

def cmd_reduce(a):
    """Fold collector receipts into the ledger, serially. Receipts are JSON:
       {"task": "...", "calls": [{"source","op","usd","detail","cached"}],
        "candidates": [{"kind","name","domain","lane","via","score"}], "notes": "..."}"""
    run = discover(a.run)
    st = load(run)
    rdir = os.path.join(run, "receipts")
    done = os.path.join(rdir, "processed")
    os.makedirs(done, exist_ok=True)
    files = sorted(f for f in os.listdir(rdir) if f.endswith(".json"))
    folded = {"receipts": 0, "calls": 0, "usd": 0.0, "nodes": 0, "errors": []}
    for fn in files:
        path = os.path.join(rdir, fn)
        try:
            with open(path, encoding="utf-8") as f:
                r = json.load(f)
        except Exception as e:
            folded["errors"].append(f"{fn}: {e}")
            continue
        for c in r.get("calls", []):
            usd = 0.0 if c.get("cached") else round(float(c.get("usd") or 0), 4)
            st["budget"]["calls"].append({
                "at": c.get("at") or now(), "source": c.get("source", "?"),
                "op": c.get("op", "?"), "usd": usd, "detail": c.get("detail", ""),
                "cached": bool(c.get("cached")), "receipt": fn,
            })
            folded["calls"] += 1
            folded["usd"] += usd
            if str(c.get("source", "")).startswith("brightdata") and not c.get("cached"):
                st["brightdata"]["count"] += 1
        for cand in r.get("candidates", []):
            kind = cand.get("kind", "alternative")
            key = cand.get("domain") or cand.get("name") or ""
            if not key:
                continue
            nid = node_id(kind, key)
            if nid in st["nodes"]:
                continue
            st["nodes"][nid] = {
                "id": nid, "kind": kind, "name": cand.get("name", key),
                "domain": cand.get("domain", ""), "lane": cand.get("lane", ""),
                "via": cand.get("via", f"receipt {fn}"), "status": "candidate",
                "score": cand.get("score"), "notes": cand.get("note", ""), "added": now(),
            }
            folded["nodes"] += 1
        folded["receipts"] += 1
        os.replace(path, os.path.join(done, fn))
    st["budget"]["spent_usd"] = round(sum(c["usd"] for c in st["budget"]["calls"]), 4)
    save(run, st)
    folded["usd"] = round(folded["usd"], 4)
    folded["spent_usd"] = st["budget"]["spent_usd"]
    print(json.dumps(folded, indent=2))


# ------------------------------------------------------------------- status

def cmd_status(a):
    run = discover(a.run)
    st = load(run)
    b = st["budget"]
    by_kind, by_status = {}, {}
    for n in st["nodes"].values():
        by_kind[n["kind"]] = by_kind.get(n["kind"], 0) + 1
        by_status[n["status"]] = by_status.get(n["status"], 0) + 1
    by_source = {}
    for c in b["calls"]:
        by_source[c["source"]] = round(by_source.get(c["source"], 0) + c["usd"], 4)
    out = {
        "run": run, "url": st["url"], "phase": st.get("phase"),
        "spent_usd": b["spent_usd"], "cap_usd": b["cap_usd"],
        "remaining_usd": round(b["cap_usd"] - b["spent_usd"], 4),
        "pct_of_cap": round(100 * b["spent_usd"] / b["cap_usd"], 1) if b["cap_usd"] else 0,
        "calls": len(b["calls"]), "spend_by_source": by_source,
        "brightdata_today": st["brightdata"]["count"],
        "nodes_by_kind": by_kind, "nodes_by_status": by_status,
        "assumptions": {c["id"]: c["status"] for c in st["assumptions"]},
    }
    print(json.dumps(out, indent=2))


def cmd_note(a):
    run = discover(a.run)
    notebook(run, a.text)
    if a.phase:
        st = load(run)
        st["phase"] = a.phase
        save(run, st)
    print(json.dumps({"noted": True, "run": run}))


# --------------------------------------------------------------------- cli

def main():
    p = argparse.ArgumentParser(description="positioning run ledger")
    p.add_argument("--run", help="run directory (default: auto-discover)")
    sub = p.add_subparsers(dest="cmd", required=True)

    i = sub.add_parser("init", help="create a run directory")
    i.add_argument("--url", required=True, help="the product URL the study is about")
    i.add_argument("--slug"); i.add_argument("--name", help="product name if known")
    i.add_argument("--budget-usd", default=6.0, type=float)
    i.add_argument("--location-code", default=2840); i.add_argument("--language-code", default="en")
    i.add_argument("--force", action="store_true")
    i.set_defaults(fn=cmd_init)

    a_ = sub.add_parser("add", help="add a node (alternative, segment, frame, page…)")
    a_.add_argument("--kind", choices=KINDS, default="alternative")
    a_.add_argument("--name", required=True); a_.add_argument("--domain")
    a_.add_argument("--lane", help="direct | adjacent | diy | nothing")
    a_.add_argument("--via", required=True, help="where this came from — provenance is mandatory")
    a_.add_argument("--status", choices=STATUSES, default="candidate")
    a_.add_argument("--score", type=float); a_.add_argument("--note")
    a_.add_argument("--id"); a_.add_argument("--force", action="store_true")
    a_.set_defaults(fn=cmd_add)

    s = sub.add_parser("set", help="update a node")
    s.add_argument("id"); s.add_argument("--status", choices=STATUSES)
    s.add_argument("--lane"); s.add_argument("--score", type=float)
    s.add_argument("--note"); s.add_argument("--domain"); s.add_argument("--name")
    s.set_defaults(fn=cmd_set)

    f = sub.add_parser("frontier", help="ranked candidates not yet collected")
    f.add_argument("--kind", choices=KINDS); f.add_argument("--limit", type=int, default=10)
    f.set_defaults(fn=cmd_frontier)

    sp = sub.add_parser("spend", help="log one paid call")
    sp.add_argument("--source", required=True); sp.add_argument("--op", required=True)
    sp.add_argument("--usd", default=0.0); sp.add_argument("--detail")
    sp.add_argument("--cached", action="store_true")
    sp.set_defaults(fn=cmd_spend)

    c = sub.add_parser("assume", help="register / judge what you expect to find")
    c.add_argument("action", choices=["add", "judge", "list"])
    c.add_argument("cid", nargs="?")
    c.add_argument("--text"); c.add_argument("--forbids"); c.add_argument("--check")
    c.add_argument("--status", choices=["open", "survived", "refuted", "revised"])
    c.add_argument("--evidence")
    c.set_defaults(fn=cmd_assume)

    r = sub.add_parser("reduce-receipts", help="fold collector receipts into the ledger")
    r.set_defaults(fn=cmd_reduce)

    st_ = sub.add_parser("status"); st_.set_defaults(fn=cmd_status)

    n = sub.add_parser("note", help="append to the notebook")
    n.add_argument("text"); n.add_argument("--phase")
    n.set_defaults(fn=cmd_note)

    args = p.parse_args()
    args.fn(args)


if __name__ == "__main__":
    main()
