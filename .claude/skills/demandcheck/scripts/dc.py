#!/usr/bin/env python3
"""dc.py — deterministic state manager for a demandcheck run.

The run lives in <run>/state.json. All mutations go through this CLI so the
graph, the ledger, and the caps stay consistent and auditable; hand-editing
the JSON is how runs drift. Stdlib-only.

Subcommands:
  init             create a run directory (state.json, notebook.md, subdirs)
  wave open|close  bracket a traversal wave
  add              add a graph node (domain/keyword/advertiser) with provenance
  set              update a node's status/score (appends to node history)
  conjecture       register / judge / list what the run expected to find
  spend            log billable spend by hand (receipts are the normal path)
  reduce-receipts  fold receipts/*.json into the ledger and the graph
  frontier         rank pending nodes worth expanding next
  status           one-screen run summary (budget, caps, waves, graph)

Run discovery: every subcommand accepts --run <dir>. If omitted, searches
<--root> (default research/demandcheck) for directories containing state.json;
uses the single match, errors if zero or several.
"""

import argparse
import csv
import glob
import json
import os
import re
import sys
import tempfile
from datetime import datetime, timezone

KINDS = ["domain", "keyword", "advertiser"]
PREFIX = {"domain": "D", "keyword": "K", "advertiser": "A"}
NODE_STATUSES = ["pending", "expanded", "skipped"]
# open until a wave's data rules on it; see references/error-correction.md
CONJECTURE_STATUSES = ["survived", "refuted", "revised"]
INSTRUMENTS = ["serp", "keywords", "ads", "other"]
SERP_DAILY_CAP = 100  # shared across every brightdata-* skill
DEFAULT_ROOT = os.path.join("research", "demandcheck")
CLEAN_TABLES = ["keywords", "domains", "advertisers", "ads", "ad_copy", "serp_results"]


def now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def today() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def die(msg: str, code: int = 2):
    print(f"error: {msg}", file=sys.stderr)
    sys.exit(code)


def find_run(args) -> str:
    if getattr(args, "run", None):
        run = args.run
        if not os.path.isfile(os.path.join(run, "state.json")):
            die(f"no state.json in {run} (run `dc.py init` first?)")
        return run
    root = getattr(args, "root", DEFAULT_ROOT)
    candidates = []
    if os.path.isdir(root):
        for name in sorted(os.listdir(root)):
            if os.path.isfile(os.path.join(root, name, "state.json")):
                candidates.append(os.path.join(root, name))
    if len(candidates) == 1:
        return candidates[0]
    if not candidates:
        die(f"no run found under {root}; run `dc.py init` or pass --run <dir>")
    die("multiple runs found, pass --run: " + ", ".join(candidates))


def load(run: str) -> dict:
    with open(os.path.join(run, "state.json"), "r", encoding="utf-8") as f:
        return json.load(f)


def save(run: str, state: dict):
    """Atomic write: temp file in the same dir, then rename."""
    path = os.path.join(run, "state.json")
    fd, tmp = tempfile.mkstemp(dir=run, prefix=".state-", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(state, f, indent=2, ensure_ascii=False)
            f.write("\n")
        os.replace(tmp, path)
    except BaseException:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise


def normalize_id(kind: str, value: str) -> str:
    v = value.strip()
    if kind == "keyword":
        return re.sub(r"\s+", " ", v.lower())
    if kind == "domain":
        v = v.lower()
        v = re.sub(r"^[a-z]+://", "", v)
        v = v.split("/")[0].split("?")[0]
        return v[4:] if v.startswith("www.") else v
    if kind == "advertiser":
        return v.upper()
    return v


def find_node(state: dict, kind: str, norm_id: str):
    for key, node in state["nodes"].items():
        if node["kind"] == kind and node["id"] == norm_id:
            return key, node
    return None, None


def upsert_node(state: dict, kind: str, raw_id: str, via: str, wave: int,
                meta: dict | None = None, note: str | None = None):
    """Add a node, or merge into the existing one (bump sightings, record via).

    Returns (key, created: bool)."""
    nid = normalize_id(kind, raw_id)
    if not nid:
        return None, False
    key, node = find_node(state, kind, nid)
    if node is not None:
        node["sightings"] += 1
        if via and via not in node["via"]:
            node["via"].append(via)
        if meta:
            for k, v in meta.items():
                node["meta"].setdefault(k, v)
        node["history"].append({"ts": now(), "event": f"seen again (wave {wave})", "note": via})
        return key, False
    state["counter"][kind] += 1
    key = f"{PREFIX[kind]}{state['counter'][kind]:03d}"
    state["nodes"][key] = {
        "kind": kind,
        "id": nid,
        "via": [via] if via else [],
        "wave": wave,
        "status": "pending",
        "score": None,
        "sightings": 1,
        "meta": meta or {},
        "history": [{"ts": now(), "event": "created", "note": note or via}],
    }
    return key, True


def budget_line(state: dict) -> str:
    b = state["budget"]
    cap = b["usd_cap"]
    pct = 100.0 * b["spent_usd"] / cap if cap else 0.0
    return f"${b['spent_usd']:.4f} of ${cap:.2f} ({pct:.0f}%) · {b['calls']} billable calls"


def warn_if_hot(state: dict):
    b = state["budget"]
    if b["usd_cap"] and b["spent_usd"] >= 0.9 * b["usd_cap"]:
        print("NOTE: >=90% of budget spent — stop opening waves; head to ANALYZE.")


def serp_today(state: dict) -> int:
    return state.get("serp_daily", {}).get(today(), 0)


def conjectures(state: dict) -> dict:
    """The conjecture register, tolerant of runs created before it existed."""
    return state.setdefault("conjectures", {})


def conjecture_tally(state: dict) -> dict:
    tally = {"open": 0, "survived": 0, "refuted": 0, "revised": 0}
    for c in conjectures(state).values():
        tally[c.get("status", "open")] = tally.get(c.get("status", "open"), 0) + 1
    return tally


def unjudged_this_wave(state: dict) -> list:
    """Open conjectures no wave-current ruling has touched (error-correction Rule 2)."""
    wave = state.get("wave", 0)
    out = []
    for key, c in conjectures(state).items():
        if c.get("status") != "open":
            continue
        last = c.get("history", [])[-1] if c.get("history") else None
        if not last or last.get("wave", -1) < wave:
            out.append(key)
    return sorted(out)


# ---------------------------------------------------------------- subcommands

def cmd_init(args):
    run = os.path.join(args.root, args.slug)
    if os.path.exists(os.path.join(run, "state.json")):
        die(f"run already exists: {run}")
    for sub in ["receipts/processed", "raw/serp", "raw/keywords", "raw/ads",
                "raw/ad_copy", "creatives", "clean", "charts"]:
        os.makedirs(os.path.join(run, sub), exist_ok=True)
    state = {
        "seed": args.seed,
        "seed_kind": args.seed_kind,
        "slug": args.slug,
        "created": now(),
        "geo": args.geo,
        "language": args.language,
        "location_code": args.location_code,
        "scope": args.scope,
        "budget": {"usd_cap": args.budget_usd, "spent_usd": 0.0, "calls": 0, "ledger": []},
        "wave": 0,
        "waves": [],
        "counter": {k: 0 for k in KINDS},
        "nodes": {},
        "conjectures": {},
        "serp_daily": {},
    }
    seed_key = None
    if args.seed_kind == "domain":
        seed_key, _ = upsert_node(state, "domain", args.seed, "user-seed", 0)
    else:
        seed_key, _ = upsert_node(state, "keyword", args.seed, "user-seed", 0)
    save(run, state)
    nb = os.path.join(run, "notebook.md")
    if not os.path.exists(nb):
        with open(nb, "w", encoding="utf-8") as f:
            f.write(
                f"# Run notebook — demandcheck: {args.seed}\n\n"
                f"Append-only. Every entry: timestamp, what ran, what it cost, "
                f"what changed.\n\n"
                f"## {now()} — run opened\n\n"
                f"- Seed (verbatim, {args.seed_kind}): {args.seed}\n"
                f"- Geo: {args.geo} / {args.language} (location_code {args.location_code})\n"
                f"- Scope: {args.scope}\n"
                f"- Budget cap: ${args.budget_usd:.2f} — the target, not just a ceiling\n"
            )
    print(f"run created: {run}")
    print(f"  seed node {seed_key} ({args.seed_kind}): {args.seed}")
    print(f"  budget: ${args.budget_usd:.2f} · geo {args.geo}/{args.language} ({args.location_code})")
    print("  next: `dc.py conjecture add` (what do you expect, and what would refute it?),")
    print("        then `dc.py wave open` and spawn the seed-wave collector")


def cmd_wave(args):
    run = find_run(args)
    state = load(run)
    open_waves = [w for w in state["waves"] if w.get("closed") is None]
    if args.action == "open":
        if open_waves:
            die(f"wave {open_waves[-1]['n']} is still open — close it first")
        state["wave"] += 1
        state["waves"].append({"n": state["wave"], "opened": now(), "closed": None,
                               "note": args.note})
        save(run, state)
        print(f"wave {state['wave']} open")
    else:  # close
        if not open_waves:
            die("no wave is open")
        w = open_waves[-1]
        w["closed"] = now()
        if args.note:
            w["note"] = (w.get("note") + " | " if w.get("note") else "") + args.note
        stale = unjudged_this_wave(state)
        save(run, state)
        print(f"wave {w['n']} closed" + (f" — {args.note}" if args.note else ""))
        if stale:
            print("NOTE: this wave ruled on no open conjecture: " + ", ".join(stale)
                  + " — judge them (`dc.py conjecture judge`) or the run is only "
                    "collecting, not correcting.")
        elif not conjectures(state):
            print("NOTE: no conjectures registered — nothing this wave's data could "
                  "have refuted. See references/error-correction.md.")
    warn_if_hot(state)


def cmd_conjecture(args):
    run = find_run(args)
    state = load(run)
    reg = conjectures(state)
    if args.action == "add":
        if not args.text:
            die("--text is required for `conjecture add`")
        n = 1 + max([int(k[1:]) for k in reg if k[1:].isdigit()] or [0])
        key = f"C{n}"
        reg[key] = {
            "text": args.text,
            "forbids": args.forbids or "",
            "check": args.check or "",
            "wave": state.get("wave", 0),
            "created": now(),
            "status": "open",
            "history": [],
        }
        save(run, state)
        print(f"{key} registered (open, wave {reg[key]['wave']}): {args.text}")
        if args.forbids:
            print(f"  forbids: {args.forbids}")
        else:
            print("  WARNING: no --forbids — an expectation that forbids nothing "
                  "cannot be refuted, and buys the run nothing.")
        if args.check:
            print(f"  check: {args.check}")
        return
    if args.action == "judge":
        key = (args.id or "").upper()
        if key not in reg:
            die(f"unknown conjecture {key or '(none given)'}; `dc.py conjecture list`")
        if not args.status:
            die("--status survived|refuted|revised is required for `conjecture judge`")
        if not args.evidence:
            die("--evidence is required: name the rows that did it")
        c = reg[key]
        prev = c["status"]
        c["status"] = args.status
        c["history"].append({"ts": now(), "wave": state.get("wave", 0),
                             "status": args.status, "evidence": args.evidence})
        save(run, state)
        print(f"{key} {prev} -> {args.status} (wave {state.get('wave', 0)}): {args.evidence}")
        if args.status == "revised":
            print("  next: `dc.py conjecture add` the sharper successor — never edit "
                  "a judged conjecture in place.")
        return
    # list
    if not reg:
        print("no conjectures registered — see references/error-correction.md")
        return
    tally = conjecture_tally(state)
    print("conjectures: " + ", ".join(f"{v} {k}" for k, v in tally.items() if v))
    for key in sorted(reg, key=lambda k: int(k[1:]) if k[1:].isdigit() else 0):
        c = reg[key]
        if c["status"] != "open" and not args.all:
            continue
        print(f"  {key} [{c['status']:8s}] wave {c['wave']} — {c['text']}")
        if c.get("forbids"):
            print(f"      forbids: {c['forbids']}")
        if c.get("check"):
            print(f"      check:   {c['check']}")
        for h in c.get("history", []):
            print(f"      → w{h.get('wave')} {h.get('status')}: {h.get('evidence')}")
    if not args.all and any(c["status"] != "open" for c in reg.values()):
        print("  (--all to include judged conjectures)")


def cmd_add(args):
    run = find_run(args)
    state = load(run)
    key, created = upsert_node(state, args.kind, args.id, args.via,
                               args.wave if args.wave is not None else state["wave"],
                               note=args.note)
    if key is None:
        die(f"empty id after normalization: {args.id!r}")
    save(run, state)
    node = state["nodes"][key]
    verb = "added" if created else f"merged (sightings {node['sightings']})"
    print(f"{key} {verb}: [{args.kind}] {node['id']}  via {args.via}")


def cmd_set(args):
    run = find_run(args)
    state = load(run)
    key = args.node.upper()
    if key not in state["nodes"]:
        die(f"unknown node {key}")
    node = state["nodes"][key]
    changes = []
    if args.status:
        changes.append(f"status {node['status']}->{args.status}")
        node["status"] = args.status
    if args.score is not None:
        changes.append(f"score {node.get('score')}->{args.score}")
        node["score"] = args.score
    if not changes and not args.note:
        die("nothing to change; pass --status/--score/--note")
    node["history"].append({"ts": now(), "event": "; ".join(changes) or "note",
                            "note": args.note})
    save(run, state)
    print(f"{key} updated: {'; '.join(changes) if changes else 'note logged'}")


def _log_spend(state: dict, usd: float, calls: int, note: str, instrument: str,
               wave: int, cached: bool):
    b = state["budget"]
    entry = {"ts": now(), "usd": round(usd, 6), "calls": calls, "note": note,
             "instrument": instrument, "wave": wave, "cached": cached}
    b["ledger"].append(entry)
    if not cached:
        b["spent_usd"] = round(b["spent_usd"] + usd, 6)
        b["calls"] += calls
        if instrument == "serp":
            state.setdefault("serp_daily", {})
            state["serp_daily"][today()] = state["serp_daily"].get(today(), 0) + calls


def cmd_spend(args):
    run = find_run(args)
    state = load(run)
    _log_spend(state, args.usd, args.calls, args.note, args.instrument,
               state["wave"], cached=False)
    save(run, state)
    print(f"ledger: +${args.usd:.4f} ({args.calls} call{'s' if args.calls != 1 else ''}) — {args.note}")
    print(f"total: {budget_line(state)}")
    if args.instrument == "serp":
        print(f"BrightData today: {serp_today(state)} of {SERP_DAILY_CAP}")
    warn_if_hot(state)


def cmd_reduce(args):
    run = find_run(args)
    state = load(run)
    receipts_dir = os.path.join(run, "receipts")
    processed_dir = os.path.join(receipts_dir, "processed")
    os.makedirs(processed_dir, exist_ok=True)
    files = sorted(
        f for f in glob.glob(os.path.join(receipts_dir, "*.json"))
        if not os.path.basename(f).startswith("frontier-")
    )
    if not files:
        print("no receipts to reduce")
        return
    added_usd = 0.0
    added_calls = 0
    cached_calls = 0
    nodes_new = {k: 0 for k in KINDS}
    nodes_merged = {k: 0 for k in KINDS}
    errors = []
    for path in files:
        name = os.path.basename(path)
        try:
            with open(path, "r", encoding="utf-8") as f:
                rec = json.load(f)
        except (json.JSONDecodeError, OSError) as e:
            errors.append(f"{name}: unreadable ({e}) — left in place")
            continue
        task = rec.get("task", name)
        wave = rec.get("wave", state["wave"])
        for call in rec.get("calls", []):
            usd = float(call.get("usd") or 0.0)
            cached = bool(call.get("cached"))
            instrument = call.get("instrument", "other")
            if instrument not in INSTRUMENTS:
                instrument = "other"
            note = f"{task}: {instrument} {call.get('op', '?')}"
            if call.get("error"):
                note += " [ERROR]"
            _log_spend(state, usd, 1, note, instrument, wave, cached)
            if cached:
                cached_calls += 1
            else:
                added_usd += usd
                added_calls += 1
        cands = rec.get("candidates", {}) or {}
        for kind_plural, kind in [("domains", "domain"), ("keywords", "keyword"),
                                  ("advertisers", "advertiser")]:
            for c in cands.get(kind_plural, []) or []:
                raw = c.get("id")
                if not raw:
                    continue
                meta = {k: v for k, v in c.items() if k not in ("id", "via")}
                key, created = upsert_node(state, kind, raw, c.get("via", task),
                                           wave, meta=meta)
                if key is None:
                    continue
                if created:
                    nodes_new[kind] += 1
                else:
                    nodes_merged[kind] += 1
        os.replace(path, os.path.join(processed_dir, name))
    save(run, state)
    print(f"reduced {len(files) - len(errors)} receipt(s): "
          f"+${added_usd:.4f} across {added_calls} billable calls "
          f"({cached_calls} cache hits, free)")
    print("nodes: " + ", ".join(
        f"{k} +{nodes_new[k]} new / {nodes_merged[k]} merged" for k in KINDS))
    print(f"budget: {budget_line(state)}")
    print(f"BrightData today: {serp_today(state)} of {SERP_DAILY_CAP}")
    for e in errors:
        print(f"WARNING: {e}", file=sys.stderr)
    warn_if_hot(state)


def cmd_frontier(args):
    run = find_run(args)
    state = load(run)
    rows = [
        (key, n) for key, n in state["nodes"].items()
        if n["status"] == "pending" and (args.kind is None or n["kind"] == args.kind)
    ]
    rows.sort(key=lambda kv: (
        -(kv[1]["score"] if kv[1]["score"] is not None else -1),
        -kv[1]["sightings"],
        kv[0],
    ))
    if not rows:
        print("frontier empty" + (f" for kind={args.kind}" if args.kind else "") +
              " — DEEPEN or ANALYZE.")
        return
    print(f"frontier (top {min(args.k, len(rows))} of {len(rows)} pending"
          + (f", kind={args.kind}" if args.kind else "") + "):")
    for key, n in rows[: args.k]:
        score = f"score {n['score']}" if n["score"] is not None else "unscored"
        via = n["via"][0] if n["via"] else "?"
        print(f"  {key} [{n['kind']:10s}] {score} · seen {n['sightings']}x · via {via} — {n['id']}")


def cmd_status(args):
    run = find_run(args)
    state = load(run)
    print(f"run: {run}")
    print(f"seed ({state['seed_kind']}): {state['seed']} · geo {state['geo']}/"
          f"{state['language']} ({state['location_code']}) · scope {state['scope']}")
    open_w = [w for w in state["waves"] if w.get("closed") is None]
    wave_s = f"{state['wave']} ({'open' if open_w else 'closed'})" if state["wave"] else "none yet"
    print(f"wave: {wave_s} · budget: {budget_line(state)}")
    print(f"BrightData today: {serp_today(state)} of {SERP_DAILY_CAP} "
          f"(shared across all brightdata-* skills)")
    counts = {}
    for n in state["nodes"].values():
        counts.setdefault(n["kind"], {}).setdefault(n["status"], 0)
        counts[n["kind"]][n["status"]] += 1
    for kind in KINDS:
        c = counts.get(kind, {})
        total = sum(c.values())
        detail = ", ".join(f"{s} {c[s]}" for s in NODE_STATUSES if s in c)
        print(f"  {kind + 's:':13s}{total:4d}  ({detail or 'none'})")
    tally = conjecture_tally(state)
    if sum(tally.values()):
        print("conjectures: " + ", ".join(f"{v} {k}" for k, v in tally.items() if v)
              + ("  (`dc.py conjecture list`)" if tally["open"] else ""))
        stale = unjudged_this_wave(state)
        if stale and state.get("wave"):
            print(f"  unjudged this wave: {', '.join(stale)}")
    else:
        print("conjectures: none registered — the run has nothing it could be wrong "
              "about yet (references/error-correction.md)")
    unreduced = [
        f for f in glob.glob(os.path.join(run, "receipts", "*.json"))
        if not os.path.basename(f).startswith("frontier-")
    ]
    if unreduced:
        print(f"UNREDUCED RECEIPTS: {len(unreduced)} — run `dc.py reduce-receipts` before deciding anything")
    clean_bits = []
    for t in CLEAN_TABLES:
        p = os.path.join(run, "clean", f"{t}.csv")
        if os.path.isfile(p):
            with open(p, newline="", encoding="utf-8") as f:
                n_rows = max(0, sum(1 for _ in csv.reader(f)) - 1)
            clean_bits.append(f"{t} {n_rows}")
    print("clean rows: " + (", ".join(clean_bits) if clean_bits else "(none yet)"))
    warn_if_hot(state)


def main(argv=None):
    p = argparse.ArgumentParser(prog="dc.py", description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--run", help="run directory (contains state.json); auto-discovered if omitted")
    p.add_argument("--root", default=DEFAULT_ROOT,
                   help=f"where runs live for init/auto-discovery (default {DEFAULT_ROOT})")
    sub = p.add_subparsers(dest="cmd", required=True)

    sp = sub.add_parser("init", help="create a new run")
    sp.add_argument("--seed", required=True, help="the user's seed, verbatim")
    sp.add_argument("--seed-kind", choices=["topic", "domain"], default="topic",
                    help="topic words (default) or a company domain")
    sp.add_argument("--slug", required=True, help="directory-safe slug, e.g. cold-plunge-tub")
    sp.add_argument("--geo", default="US")
    sp.add_argument("--language", default="en")
    sp.add_argument("--location-code", type=int, default=2840)
    sp.add_argument("--budget-usd", type=float, default=5.0,
                    help="the cap AND the target — land >=90%% spent (default 5.0)")
    sp.add_argument("--scope", choices=["expressed", "novelty-dependent"],
                    default="expressed",
                    help="intake scope check (see references/demand-lens.md)")
    sp.set_defaults(fn=cmd_init)

    sp = sub.add_parser("wave", help="open/close a traversal wave")
    sp.add_argument("action", choices=["open", "close"])
    sp.add_argument("--note")
    sp.set_defaults(fn=cmd_wave)

    sp = sub.add_parser("add", help="add a node with provenance")
    sp.add_argument("--kind", choices=KINDS, required=True)
    sp.add_argument("--id", required=True, help="domain, keyword phrase, or AR… advertiser id")
    sp.add_argument("--via", required=True,
                    help="provenance: user-seed | serp:QUERY | for-site:DOMAIN | ads:DOMAIN")
    sp.add_argument("--wave", type=int, help="defaults to the current wave")
    sp.add_argument("--note")
    sp.set_defaults(fn=cmd_add)

    sp = sub.add_parser("set", help="update a node")
    sp.add_argument("node")
    sp.add_argument("--status", choices=NODE_STATUSES)
    sp.add_argument("--score", type=int, choices=range(0, 6))
    sp.add_argument("--note")
    sp.set_defaults(fn=cmd_set)

    sp = sub.add_parser(
        "conjecture",
        help="register / judge / list what the run expected to find",
        description="A conjecture is what you expect before the data arrives, "
                    "plus what would refute it. Register at intake, judge every "
                    "wave. See references/error-correction.md.")
    sp.add_argument("action", choices=["add", "judge", "list"])
    sp.add_argument("id", nargs="?", help="conjecture id (C1…) for `judge`")
    sp.add_argument("--text", help="the claim, in one plain sentence")
    sp.add_argument("--forbids", help="what this claim says the data will NOT show "
                                      "— the load-bearing field")
    sp.add_argument("--check", help="the concrete test that would settle it")
    sp.add_argument("--status", choices=CONJECTURE_STATUSES,
                    help="ruling for `judge`")
    sp.add_argument("--evidence", help="the rows behind the ruling")
    sp.add_argument("--all", action="store_true", help="`list`: include judged ones")
    sp.set_defaults(fn=cmd_conjecture)

    sp = sub.add_parser("spend", help="log billable spend by hand")
    sp.add_argument("--usd", type=float, required=True)
    sp.add_argument("--calls", type=int, default=1)
    sp.add_argument("--instrument", choices=INSTRUMENTS, default="other")
    sp.add_argument("--note", required=True, help="what was bought and why")
    sp.set_defaults(fn=cmd_spend)

    sp = sub.add_parser("reduce-receipts", help="fold receipts into ledger + graph")
    sp.set_defaults(fn=cmd_reduce)

    sp = sub.add_parser("frontier", help="rank pending nodes")
    sp.add_argument("--kind", choices=KINDS)
    sp.add_argument("-k", type=int, default=10)
    sp.set_defaults(fn=cmd_frontier)

    sp = sub.add_parser("status", help="run summary")
    sp.set_defaults(fn=cmd_status)

    args = p.parse_args(argv)
    try:
        args.fn(args)
    except BrokenPipeError:  # e.g. `dc.py status | head` — not an error
        try:
            sys.stdout.close()
        except Exception:
            pass
        os._exit(0)


if __name__ == "__main__":
    main()
