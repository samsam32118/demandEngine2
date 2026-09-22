#!/usr/bin/env python3
"""maze.py — deterministic state manager for a demand-forecasting idea maze.

The maze lives in <lab>/maze.json. All mutations go through this CLI so the
state stays consistent, timestamped, and auditable; hand-editing the JSON is
how labs drift. Stdlib-only.

Subcommands:
  init      create a lab directory (maze.json, notebook.md, experiments/)
  add       add a maze node                       -> prints its id (N01, N02…)
  set       update a node's status/scores/fields  (appends to node history)
  exp       register an experiment for a node     -> prints its id (E001…) + dir
  spend     log billable API spend to the ledger
  frontier  rank the nodes worth working next
  tree      render the maze as an ASCII tree
  status    one-screen lab summary (counts, budget, frontier head)

Lab discovery: every subcommand accepts --lab <dir>. If omitted, searches
<--root>/ (default research/demand) for directories containing maze.json;
uses the single match, errors if zero or several.
"""

import argparse
import json
import os
import sys
import tempfile
from datetime import datetime, timezone

STATUSES = ["unexplored", "probed", "hypothesized", "validated", "refuted", "pruned", "parked"]
TERMINAL = {"validated", "refuted", "pruned"}
GLYPHS = {
    "unexplored": "?", "probed": "~", "hypothesized": "!",
    "validated": "V", "refuted": "X", "pruned": "-", "parked": "=",
}
AXES = ["who", "pain", "wedge", "channel", "model"]
DEFAULT_ROOT = os.path.join("research", "demand")


def now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def die(msg: str, code: int = 2):
    print(f"error: {msg}", file=sys.stderr)
    sys.exit(code)


def find_lab(args) -> str:
    if getattr(args, "lab", None):
        lab = args.lab
        if not os.path.isfile(os.path.join(lab, "maze.json")):
            die(f"no maze.json in {lab} (run `maze.py init` first?)")
        return lab
    root = getattr(args, "root", DEFAULT_ROOT)
    candidates = []
    if os.path.isdir(root):
        for name in sorted(os.listdir(root)):
            if os.path.isfile(os.path.join(root, name, "maze.json")):
                candidates.append(os.path.join(root, name))
    if len(candidates) == 1:
        return candidates[0]
    if not candidates:
        die(f"no lab found under {root}; run `maze.py init` or pass --lab <dir>")
    die("multiple labs found, pass --lab: " + ", ".join(candidates))


def load(lab: str) -> dict:
    with open(os.path.join(lab, "maze.json"), "r", encoding="utf-8") as f:
        return json.load(f)


def save(lab: str, maze: dict):
    """Atomic write: temp file in the same dir, then rename."""
    path = os.path.join(lab, "maze.json")
    fd, tmp = tempfile.mkstemp(dir=lab, prefix=".maze-", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(maze, f, indent=2, ensure_ascii=False)
            f.write("\n")
        os.replace(tmp, path)
    except BaseException:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise


def fmt_ceiling(value) -> str:
    if value is None:
        return "none set — the user decides from the reported CAC"
    return f"${value:,.2f} per customer (the user's own line, not this skill's)"


def get_node(maze: dict, node_id: str) -> dict:
    node_id = node_id.upper()
    if node_id not in maze["nodes"]:
        die(f"unknown node {node_id}; have: {', '.join(sorted(maze['nodes'])) or '(none)'}")
    return maze["nodes"][node_id]


def fmt_cac(node: dict) -> str:
    """Measured acquisition cost, never a grade of it — the user judges worth."""
    econ = node.get("econ") or {}
    cb, cc = econ.get("cac_base"), econ.get("cac_cons")
    if cb is None and cc is None:
        return ""
    parts = []
    if cb is not None:
        parts.append(f"base ${cb:,.0f}")
    if cc is not None:
        parts.append(f"cons ${cc:,.0f}")
    return " · CAC " + "/".join(parts)


# ---------------------------------------------------------------- subcommands

def cmd_init(args):
    slug = args.slug
    lab = os.path.join(args.root, slug)
    if os.path.exists(os.path.join(lab, "maze.json")):
        die(f"lab already exists: {lab}")
    os.makedirs(os.path.join(lab, "experiments"), exist_ok=True)
    maze = {
        "idea": args.idea,
        "slug": slug,
        "created": now(),
        "geo": args.geo,
        "bar": {
            # No economics bar: CAC is measured and handed to the user, who
            # decides whether it is worth paying. cac_ceiling_usd is set only
            # if the *user* named a maximum they'd pay for a customer.
            "cac_ceiling_usd": args.cac_ceiling,
            "min_monthly_cluster_volume": args.min_volume,
            "signal_families_min": 2,
        },
        "budget": {"usd_cap": args.budget_usd, "spent_usd": 0.0, "calls": 0, "ledger": []},
        "counter": {"node": 0, "exp": 0},
        "nodes": {},
        "experiments": {},
    }
    save(lab, maze)
    nb = os.path.join(lab, "notebook.md")
    if not os.path.exists(nb):
        with open(nb, "w", encoding="utf-8") as f:
            f.write(
                f"# Lab notebook — {args.idea}\n\n"
                f"Append-only. Every entry: timestamp, action, cost, what changed "
                f"(verdict, explanation, premise — or 'nothing').\n\n"
                f"## {now()} — lab opened\n\n"
                f"- Idea: {args.idea}\n- Geo: {args.geo}\n"
                f"- Bar: cluster >= {args.min_volume}/mo, >= 2 signal families, "
                f"explanation intact, CAC measured and reported\n"
                f"- CAC ceiling: {fmt_ceiling(args.cac_ceiling)}\n"
                f"- Budget: ${args.budget_usd:.2f}\n"
            )
    print(f"lab created: {lab}")
    print(f"  maze.json, notebook.md, experiments/")
    print(f"  bar: cluster >= {args.min_volume}/mo · >=2 families · CAC measured, not graded")
    print(f"  CAC ceiling: {fmt_ceiling(args.cac_ceiling)}")
    print(f"  budget: ${args.budget_usd:.2f}")


def cmd_add(args):
    lab = find_lab(args)
    maze = load(lab)
    if args.parent:
        get_node(maze, args.parent)  # validate
    maze["counter"]["node"] += 1
    nid = f"N{maze['counter']['node']:02d}"
    node = {
        "title": args.title,
        "parent": args.parent.upper() if args.parent else None,
        "axes": {a: getattr(args, a) for a in AXES},
        "status": "unexplored",
        "demand": args.demand,
        "survived": [],
        "econ": {},
        "experiments": [],
        "rationale": args.rationale,
        "history": [{"ts": now(), "event": "created", "note": args.rationale}],
    }
    maze["nodes"][nid] = node
    save(lab, maze)
    prior = f" (prior demand {args.demand})" if args.demand is not None else ""
    print(f"{nid} added{prior}: {args.title}")


def cmd_set(args):
    lab = find_lab(args)
    maze = load(lab)
    node = get_node(maze, args.node)
    nid = args.node.upper()
    changes = []
    if args.status:
        if args.status not in STATUSES:
            die(f"status must be one of: {', '.join(STATUSES)}")
        changes.append(f"status {node['status']}->{args.status}")
        node["status"] = args.status
    if args.demand is not None:
        changes.append(f"demand {node.get('demand')}->{args.demand}")
        node["demand"] = args.demand
    if args.survived:
        rec = node.setdefault("survived", [])
        for s in args.survived:
            rec.append(s)
            changes.append(f"survived: {s}")
    if args.cac_base is not None:
        node.setdefault("econ", {})["cac_base"] = args.cac_base
        changes.append(f"cac_base=${args.cac_base:,.2f}")
    if args.cac_cons is not None:
        node.setdefault("econ", {})["cac_cons"] = args.cac_cons
        changes.append(f"cac_cons=${args.cac_cons:,.2f}")
    if args.title:
        node["title"] = args.title
        changes.append("title updated")
    if args.rationale:
        node["rationale"] = args.rationale
        changes.append("rationale updated")
    for a in AXES:
        v = getattr(args, a)
        if v is not None:
            node["axes"][a] = v
            changes.append(f"{a} set")
    if not changes and not args.note:
        die("nothing to change; pass --status/--demand/--note/…")
    node["history"].append({"ts": now(), "event": "; ".join(changes) or "note", "note": args.note})
    save(lab, maze)
    print(f"{nid} updated: {'; '.join(changes) if changes else 'note logged'}")
    if args.note:
        print(f"  note: {args.note}")


def cmd_exp(args):
    lab = find_lab(args)
    maze = load(lab)
    node = get_node(maze, args.node)
    nid = args.node.upper()
    maze["counter"]["exp"] += 1
    eid = f"E{maze['counter']['exp']:03d}"
    dirname = f"{eid}-{args.slug}"
    rel = os.path.join("experiments", dirname)
    full = os.path.join(lab, rel)
    os.makedirs(os.path.join(full, "data"), exist_ok=True)
    maze["experiments"][eid] = {"node": nid, "slug": args.slug, "dir": rel, "created": now()}
    node["experiments"].append(eid)
    node["history"].append({"ts": now(), "event": f"experiment {eid} registered", "note": args.slug})
    save(lab, maze)
    print(f"{eid} registered for {nid}: {full}")
    print(f"  next: write the pre-registered card at {os.path.join(full, 'card.md')} "
          f"(template: .claude/skills/demand-forecasting/assets/hypothesis-card.md)")


def cmd_spend(args):
    lab = find_lab(args)
    maze = load(lab)
    b = maze["budget"]
    b["spent_usd"] = round(b["spent_usd"] + args.usd, 4)
    b["calls"] += args.calls
    b["ledger"].append({"ts": now(), "usd": args.usd, "calls": args.calls, "note": args.note})
    save(lab, maze)
    cap = b["usd_cap"]
    pct = 100.0 * b["spent_usd"] / cap if cap else 0.0
    line = f"ledger: +${args.usd:.4f} ({args.calls} call{'s' if args.calls != 1 else ''}) — {args.note}"
    print(line)
    print(f"total spent: ${b['spent_usd']:.4f} of ${cap:.2f} ({pct:.0f}%) · {b['calls']} calls")
    if cap and b["spent_usd"] >= 0.9 * cap:
        print("WARNING: >=90% of budget spent — stopping condition; head to JUDGE/REPORT.")


def cmd_frontier(args):
    lab = find_lab(args)
    maze = load(lab)
    order = {"hypothesized": 0, "probed": 1, "unexplored": 2}
    rows = [
        (order[n["status"]], -(n.get("demand") if n.get("demand") is not None else -1), nid, n)
        for nid, n in maze["nodes"].items()
        if n["status"] in order
    ]
    rows.sort(key=lambda r: (r[0], r[1], r[2]))
    if not rows:
        print("frontier empty — stopping condition reached (all nodes terminal/parked).")
        return
    print(f"frontier (top {min(args.k, len(rows))} of {len(rows)}; finish hypothesized, then probed by demand):")
    for _, _, nid, n in rows[: args.k]:
        d = n.get("demand")
        d_s = f"demand {d}" if d is not None else "demand ?"
        sv = len(n.get("survived") or [])
        sv_s = f" · survived {sv}" if sv else ""
        print(f"  {nid} [{n['status']:12s}] {d_s}{fmt_cac(n)}{sv_s} — {n['title']}")


def cmd_tree(args):
    lab = find_lab(args)
    maze = load(lab)
    nodes = maze["nodes"]
    children = {}
    roots = []
    for nid in sorted(nodes):
        parent = nodes[nid].get("parent")
        if parent and parent in nodes:
            children.setdefault(parent, []).append(nid)
        else:
            roots.append(nid)

    def line(nid, depth):
        n = nodes[nid]
        g = GLYPHS.get(n["status"], "?")
        d = n.get("demand")
        d_s = f" d{d}" if d is not None else ""
        exps = f" [{','.join(n['experiments'])}]" if n["experiments"] else ""
        print(f"{'  ' * depth}{g} {nid}{d_s}{fmt_cac(n)}{exps} {n['title']}")
        for c in children.get(nid, []):
            line(c, depth + 1)

    print(f"idea maze — {maze['idea']} (geo {maze['geo']})")
    legend = "  ".join(f"{v}={k}" for k, v in GLYPHS.items())
    print(f"legend: {legend}")
    for r in roots:
        line(r, 1)
    if not roots:
        print("  (empty — add nodes with `maze.py add`)")


def cmd_status(args):
    lab = find_lab(args)
    maze = load(lab)
    counts = {}
    for n in maze["nodes"].values():
        counts[n["status"]] = counts.get(n["status"], 0) + 1
    b = maze["budget"]
    cap = b["usd_cap"]
    pct = 100.0 * b["spent_usd"] / cap if cap else 0.0
    print(f"lab: {lab}")
    print(f"idea: {maze['idea']} · geo {maze['geo']} · created {maze['created']}")
    bar = maze["bar"]
    print(f"bar: cluster >= {bar['min_monthly_cluster_volume']}/mo · >= "
          f"{bar['signal_families_min']} families · CAC measured and reported, not graded")
    print(f"CAC ceiling: {fmt_ceiling(bar.get('cac_ceiling_usd'))}")
    print(f"nodes: {len(maze['nodes'])} total — "
          + (", ".join(f"{k} {v}" for k, v in sorted(counts.items())) or "none"))
    print(f"experiments: {len(maze['experiments'])}")
    print(f"budget: ${b['spent_usd']:.4f} of ${cap:.2f} ({pct:.0f}%) · {b['calls']} billable calls")
    if cap and b["spent_usd"] >= 0.9 * cap:
        print("WARNING: >=90% budget — stopping condition.")
    validated = [nid for nid, n in maze["nodes"].items() if n["status"] == "validated"]
    if validated:
        print(f"validated: {', '.join(validated)}")


def main(argv=None):
    p = argparse.ArgumentParser(prog="maze.py", description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--lab", help="lab directory (contains maze.json); auto-discovered if omitted")
    p.add_argument("--root", default=DEFAULT_ROOT,
                   help=f"where labs live for init/auto-discovery (default {DEFAULT_ROOT})")
    sub = p.add_subparsers(dest="cmd", required=True)

    sp = sub.add_parser("init", help="create a new lab")
    sp.add_argument("--idea", required=True, help="the vague idea, verbatim")
    sp.add_argument("--slug", required=True, help="directory-safe slug, e.g. ai-meeting-notes")
    sp.add_argument("--geo", default="US")
    sp.add_argument("--budget-usd", type=float, default=3.0)
    sp.add_argument("--cac-ceiling", type=float, default=None, metavar="USD",
                    help="max CAC the USER said they'd pay per customer, if they named "
                         "one; omit and the loop just reports CAC for them to judge")
    sp.add_argument("--min-volume", type=int, default=5000,
                    help="min monthly commercial-intent cluster volume (default 5000)")
    sp.set_defaults(fn=cmd_init)

    sp = sub.add_parser("add", help="add a node")
    sp.add_argument("--title", required=True)
    sp.add_argument("--parent", help="parent node id (omit for a root node)")
    for a in AXES:
        sp.add_argument(f"--{a}")
    sp.add_argument("--demand", type=int, choices=range(0, 6), help="prior demand score 0-5")
    sp.add_argument("--rationale", help="one line: why this node exists")
    sp.set_defaults(fn=cmd_add)

    sp = sub.add_parser("set", help="update a node")
    sp.add_argument("node")
    sp.add_argument("--status", choices=STATUSES)
    sp.add_argument("--demand", type=int, choices=range(0, 6))
    sp.add_argument("--survived", action="append", metavar="CRITICISM",
                    help="log a kill attempt this node survived (repeatable; the node's "
                         "criticism record — what stands in for 'confidence' here)")
    sp.add_argument("--cac-base", type=float, metavar="USD",
                    help="base-scenario CAC from cac.py")
    sp.add_argument("--cac-cons", type=float, metavar="USD",
                    help="conservative-scenario CAC from cac.py")
    sp.add_argument("--title")
    sp.add_argument("--rationale")
    for a in AXES:
        sp.add_argument(f"--{a}")
    sp.add_argument("--note", help="history note (e.g. why pruned, what changed)")
    sp.set_defaults(fn=cmd_set)

    sp = sub.add_parser("exp", help="register an experiment for a node")
    sp.add_argument("node")
    sp.add_argument("--slug", required=True, help="short slug, e.g. probe-search")
    sp.set_defaults(fn=cmd_exp)

    sp = sub.add_parser("spend", help="log billable spend")
    sp.add_argument("--usd", type=float, required=True)
    sp.add_argument("--calls", type=int, default=1)
    sp.add_argument("--note", required=True, help="what was bought and why")
    sp.set_defaults(fn=cmd_spend)

    sp = sub.add_parser("frontier", help="rank nodes worth working next")
    sp.add_argument("-k", type=int, default=5)
    sp.set_defaults(fn=cmd_frontier)

    sp = sub.add_parser("tree", help="render the maze")
    sp.set_defaults(fn=cmd_tree)

    sp = sub.add_parser("status", help="lab summary")
    sp.set_defaults(fn=cmd_status)

    args = p.parse_args(argv)
    args.fn(args)


if __name__ == "__main__":
    main()
