#!/usr/bin/env python3
"""selftest.py — check the skill's scripts still work. Run after any change.

Two tiers:

  offline  no network, no credentials. Question construction and validation,
           chunking, cache keys, premise parsing, the numeric rubric, the CAC
           arithmetic, the state machine's transition table, and a scan for
           anything that could leak a credential.
  live     one Jev round-trip plus the seven judge.py stages over fixtures in
           a throwaway lab. Costs about a tenth of a cent.

    python3 .claude/skills/demand-forecasting/scripts/selftest.py
    python3 .claude/skills/demand-forecasting/scripts/selftest.py --live
"""

from __future__ import annotations

import argparse
import io
import json
import os
import re
import shutil
import sys
import tempfile
import time
from contextlib import redirect_stdout

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import cac  # noqa: E402
import jev  # noqa: E402
import judge  # noqa: E402
import maze as mazelib  # noqa: E402

PASS, FAIL = 0, 0


def check(label: str, condition: bool, detail: str = "") -> None:
    global PASS, FAIL
    if condition:
        PASS += 1
        print(f"  ok   {label}")
    else:
        FAIL += 1
        print(f"  FAIL {label}" + (f" — {detail}" if detail else ""))


def raises(label: str, exc: type, fn) -> None:
    try:
        fn()
    except exc:
        check(label, True)
        return
    except Exception as other:  # noqa: BLE001
        check(label, False, f"raised {type(other).__name__}, expected {exc.__name__}")
        return
    check(label, False, "did not raise")


# ------------------------------------------------------------------ offline

def test_questions() -> None:
    print("questions")
    check("Noul wire", jev.Noul(instructions="q?").wire() ==
          {"type": "noul", "instructions": "q?"})
    check("Choice wire carries criteria",
          jev.Choice(instructions="q?", criteria={"a": None}).wire()["criteria"] == {"a": None})
    check("Score wire carries ordered levels",
          jev.Score(instructions="q?", criteria=["lo", "hi"]).wire()["criteria"] == ["lo", "hi"])
    raises("Score rejects 1 level", jev.JevValidationError,
           lambda: jev.Score(instructions="q", criteria=["only"]).wire())
    raises("Score rejects 11 levels", jev.JevValidationError,
           lambda: jev.Score(instructions="q", criteria=[str(i) for i in range(11)]).wire())
    raises("Choice rejects 256 options", jev.JevValidationError,
           lambda: jev.Choice(instructions="q",
                              criteria={str(i): None for i in range(256)}).wire())
    raises("Choice rejects empty criteria", jev.JevValidationError,
           lambda: jev.Choice(instructions="q", criteria={}).wire())
    raises("Noul rejects stray criteria keys", jev.JevValidationError,
           lambda: jev.Noul(instructions="q", criteria={"maybe": "?"}).wire())


def test_answers() -> None:
    print("answers")
    n = jev._parse_answer("k", {"type": "noul", "noul": 0.9})
    check("noul parses", isinstance(n, jev.NoulAnswer) and n.yes() and n.confidence is None)
    c = jev._parse_answer("k", {"type": "choice", "choice": "a",
                                "probabilities": {"a": 0.9, "b": 0.1}, "confidence": 0.8})
    check("choice at_least gates on confidence",
          c.at_least(0.5) == "a" and c.at_least(0.95) is None)
    s = jev._parse_answer("k", {"type": "score", "score": 2.0,
                                "legend": {"0": "lo", "1": "mid", "2": "hi"},
                                "probabilities": {"2": 1.0}, "confidence": 1.0})
    check("score normalizes to 0-1", abs(s.normalized - 1.0) < 1e-9, f"{s.normalized}")
    check("score labels the nearest level", s.label == "hi", s.label)
    raises("unknown answer type raises", jev.JevError,
           lambda: jev._parse_answer("k", {"type": "vibes"}))
    r = jev.Result(answers={"k": n})
    raises("typed accessor rejects a mismatch", jev.JevError, lambda: r.choice("k"))


def test_batching() -> None:
    print("batching")
    client = jev.Client(api_key="test-key-not-real", use_cache=False, max_questions=10)
    wire = {f"q{i:03d}": jev.Noul(instructions="short?").wire() for i in range(35)}
    chunks = client._chunk(wire, state_tokens=100)
    check("chunks respect max_questions", all(len(c) <= 10 for c in chunks),
          str([len(c) for c in chunks]))
    check("chunks cover every question",
          sorted(k for c in chunks for k in c) == sorted(wire))
    check("chunks do not overlap",
          len([k for c in chunks for k in c]) == len(wire))
    check("chunking is deterministic", client._chunk(wire, 100) == chunks)
    raises("oversized state is refused, not sent", jev.JevValidationError,
           lambda: client.ask("x" * 200_000, {"q": jev.Noul(instructions="?")}))
    big = jev.Client(api_key="test-key-not-real", use_cache=False)
    raises("a single oversized question is refused", jev.JevValidationError,
           lambda: big._chunk({"q": jev.Noul(instructions="x" * 400_000).wire()}, 10))


def test_cache_keys() -> None:
    print("cache")
    with tempfile.TemporaryDirectory() as tmp:
        client = jev.Client(api_key="test-key-not-real", cache_dir=tmp)
        a = {"state": "s", "model": "jev-latest", "questions": {"x": {"type": "noul"}}}
        b = {"model": "jev-latest", "questions": {"x": {"type": "noul"}}, "state": "s"}
        c = {"state": "s2", "model": "jev-latest", "questions": {"x": {"type": "noul"}}}
        check("key ignores dict ordering", client._cache_path(a) == client._cache_path(b))
        check("key tracks the state", client._cache_path(a) != client._cache_path(c))
        path = client._cache_path(a)
        client._cache_write(path, {"answers": {}, "model": "jev-1.13.0"})
        check("round-trips through disk", client._cache_read(path) is not None)
        check("a corrupt entry degrades to a miss",
              (open(path, "w").write("{not json"), client._cache_read(path))[1] is None)


def test_secrets() -> None:
    print("secrets")
    key = "sk-live-secret-value-do-not-print"
    check("fingerprint is short and not the key",
          len(jev.key_fingerprint(key)) == 8 and key not in jev.key_fingerprint(key))
    check("fingerprint is stable", jev.key_fingerprint(key) == jev.key_fingerprint(key))
    check("redaction removes the key",
          key not in jev._redact(f"boom Authorization: Bearer {key}", key))

    saved = {n: os.environ.pop(n, None) for n in jev.API_KEY_ENV_NAMES}
    try:
        with tempfile.TemporaryDirectory() as tmp:
            cwd = os.getcwd()
            os.chdir(tmp)
            try:
                raises("no credential raises JevAuthError", jev.JevAuthError, jev.resolve_api_key)
                check("available() is False when offline", jev.available() is False)
                with open(".env", "w") as fh:
                    fh.write('TYPESAFEAI_API_KEY="from-dotenv"\n')
                check(".env is the last resort", jev.resolve_api_key() == "from-dotenv")
                os.environ["TYPESAFE_API_KEY"] = " from-env "
                check("env wins over .env, and is stripped",
                      jev.resolve_api_key() == "from-env")
            finally:
                os.chdir(cwd)
    finally:
        for name, value in saved.items():
            os.environ.pop(name, None)
            if value is not None:
                os.environ[name] = value

    # No script may print a credential. Scanned line by line: a pattern allowed
    # to span newlines matches a print on one line and a redaction call three
    # lines later, and reports a leak that is not there.
    # Flag any print whose arguments touch the key variable. The one
    # legitimate such print goes through key_fingerprint(), so that call is
    # erased first rather than special-cased inside the pattern — where
    # `\bprint` would also have to fend off the tail of "key_finge-rprint(".
    fingerprinted = re.compile(r"key_fingerprint\([^)]*\)")
    leaky = re.compile(r"(?:\bprint|\bsys\.std(?:out|err)\.write)\([^\n]*?"
                       r"\b(?:self\._key|api_key|_key)\b")

    def leaks(line: str) -> bool:
        return bool(leaky.search(fingerprinted.sub("<fingerprint>", line)))

    check("the scanner catches a real leak", leaks('    print(f"key={self._key}")'))
    check("the scanner spares the fingerprint call",
          not leaks('        print(f"fp {key_fingerprint(self._key)}")'))
    for name in ("jev.py", "judge.py", "maze.py", "cac.py"):
        hits = [f"{name}:{n}" for n, line in enumerate(
            open(os.path.join(HERE, name), encoding="utf-8"), start=1) if leaks(line)]
        check(f"{name} never prints a credential", not hits, "; ".join(hits[:3]))

    # And prove it, rather than only grepping for it: every error path has to
    # survive carrying a real-looking key, because that is when a key leaks —
    # into a stack trace someone pastes into a chat.
    sentinel = "sk-live-THIS-MUST-NEVER-APPEAR-9f3a"
    saved_attempts = jev._MAX_ATTEMPTS
    jev._MAX_ATTEMPTS = 1
    try:
        client = jev.Client(api_key=sentinel, base_url="http://127.0.0.1:1",
                            use_cache=False, timeout=1.0)
        try:
            client.ask("s", {"q": jev.Noul(instructions="?")})
            check("a network failure raises", False, "it succeeded")
        except jev.JevError as exc:
            check("a network error never carries the key", sentinel not in str(exc))

        import urllib.error
        import urllib.request

        real_urlopen = urllib.request.urlopen
        for code, label in ((401, "a 401"), (422, "a 422"), (500, "a 500")):
            def boom(*a, _code=code, **kw):
                raise urllib.error.HTTPError(
                    "http://127.0.0.1:1/v1/systemone", _code, "nope", {},
                    io.BytesIO(f"upstream echoed Bearer {sentinel}".encode()))
            urllib.request.urlopen = boom
            try:
                client.ask("s", {"q": jev.Noul(instructions="?")})
                check(f"{label} raises", False, "it succeeded")
            except jev.JevError as exc:
                check(f"{label} body is redacted before it reaches the message",
                      sentinel not in str(exc), str(exc)[:80])
            finally:
                urllib.request.urlopen = real_urlopen
    finally:
        jev._MAX_ATTEMPTS = saved_attempts


def test_premises() -> None:
    print("premise parsing")
    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, "card.md")
        with open(path, "w", encoding="utf-8") as fh:
            fh.write("# card\n\n**Premises**\n\n"
                     "- **X1**: therapists must file a note after every\n"
                     "  session before the insurer pays\n"
                     "- **X2**: they already pay for software\n\n"
                     "## Claim\nnot a premise\n\n- a plain bullet\n")
        got = judge.parse_premises(path)
        check("finds every premise", sorted(got) == ["X1", "X2"], str(sorted(got)))
        check("joins wrapped lines", got["X1"].endswith("before the insurer pays"), got["X1"])
        check("stops at the next bullet", "plain bullet" not in " ".join(got.values()))
        check("stops at a heading", "not a premise" not in " ".join(got.values()))


def test_rubric() -> None:
    print("numeric rubric (code-side, never asked of the model)")
    check("100k+ is band 5", judge.volume_band(120_000) == 5)
    check("10k-100k is band 4", judge.volume_band(22_000) == 4)
    check("1k-10k is band 3", judge.volume_band(8_100) == 3)
    check("under 1k is band 2", judge.volume_band(300) == 2)
    check("zero is band 0", judge.volume_band(0) == 0)
    hi, _ = judge.measured_band(22_000, 4.10, 3)
    check("band 4 with auction and sustainer stays 4", hi == 4.0, str(hi))
    demoted, note = judge.measured_band(22_000, 0.0, 0)
    check("volume with nobody bidding is demoted", demoted == 3.0, f"{demoted} {note}")
    lifted, _ = judge.measured_band(3_600, 4.80, 1)
    check("low volume with real spend is lifted", lifted == 4.0, str(lifted))
    check("the lift never reaches 'heavy'",
          judge.measured_band(300, 9.0, 5)[0] <= 4.0)
    flat, _ = judge.measured_band(8_100, 0.0, 0)
    check("no auction, no sustainer, no change", flat == 3.0, str(flat))


def test_cac() -> None:
    print("cac arithmetic")
    out = cac.compute(cpc=4.10, funnel=0.02, margin=0.8, prices=[49, 99], volume=22_000)
    base = out["scenarios"]["base"]["cac"]
    check("CAC is CPC over funnel", abs(base - 205.0) < 0.01, str(base))
    check("conservative is the widest",
          out["scenarios"]["conservative"]["cac"] > base > out["scenarios"]["optimistic"]["cac"])
    check("100 customers is 100x one", abs(
        out["scenarios"]["base"]["cost_per_cohort"]["100"] - base * 100) < 0.01)
    repay = {r["price"]: r["months"]["base"] for r in out["repay"]}
    check("a higher price repays sooner", repay[99] < repay[49])
    check("repay is CAC over price times margin",
          abs(repay[49] - round(base / (49 * 0.8), 1)) < 0.05)
    check("reach ceiling is derived from volume",
          out["reachable"]["clicks_per_month"] == round(22_000 * cac.REACHABLE_CLICK_SHARE))
    check("no verdict on whether the CAC is acceptable",
          not any(k in out for k in ("verdict", "ltv", "ratio", "passes")))


def test_machine() -> None:
    print("state machine")
    m = mazelib.MACHINE
    check("INTAKE is the initial state", mazelib.INITIAL_STATE in m)
    check("every target state exists",
          all(t in m for _, nexts in m.values() for t in nexts),
          str([t for _, n in m.values() for t in n if t not in m]))
    check("DECIDE is the only terminal state",
          [s for s, (_, n) in m.items() if not n] == ["DECIDE"])
    reachable, frontier = {mazelib.INITIAL_STATE}, [mazelib.INITIAL_STATE]
    while frontier:
        for nxt in m[frontier.pop()][1]:
            if nxt not in reachable:
                reachable.add(nxt)
                frontier.append(nxt)
    check("every state is reachable from INTAKE", reachable == set(m),
          str(set(m) - reachable))
    check("REPORT is reachable without an experiment",
          "REPORT" in m["PROBE"][1])
    check("EXPERIMENT is only reachable via HYPOTHESIZE",
          [s for s, (_, n) in m.items() if "EXPERIMENT" in n] == ["HYPOTHESIZE"])


def test_lab_roundtrip() -> None:
    print("lab state")
    tmp = tempfile.mkdtemp()
    try:
        root = os.path.join(tmp, "research", "demand")
        mazelib.main(["--root", root, "init", "--idea", "x", "--slug", "x",
                      "--budget-usd", "1"])
        lab = os.path.join(root, "x")
        state = mazelib.load(lab)
        check("a new lab starts at INTAKE", state["state"] == mazelib.INITIAL_STATE)
        mazelib.main(["--lab", lab, "add", "--title", "n", "--who", "w", "--demand", "3"])
        buf = io.StringIO()
        with redirect_stdout(buf):
            mazelib.main(["--lab", lab, "state", "--set", "MAP"])
        check("a legal transition is applied", mazelib.load(lab)["state"] == "MAP")
        try:
            with redirect_stdout(io.StringIO()):
                mazelib.main(["--lab", lab, "state", "--set", "DECIDE"])
            check("an illegal transition is refused", False, "it was allowed")
        except SystemExit:
            check("an illegal transition is refused", True)
        check("a refused transition changes nothing", mazelib.load(lab)["state"] == "MAP")
        with redirect_stdout(io.StringIO()):
            mazelib.main(["--lab", lab, "state", "--set", "DECIDE", "--force"])
        check("--force overrides, and is recorded",
              mazelib.load(lab)["state"] == "DECIDE"
              and mazelib.load(lab)["state_history"][-1]["forced"] is True)
        labelled = {g[0] for g in mazelib.guards(mazelib.load(lab))}
        check("guards evaluate against a real lab", len(labelled) >= 6, str(len(labelled)))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


# --------------------------------------------------------------------- live

FIXTURES = {
    "keywords.csv": "keyword,search_volume,competition,cpc\n"
                    "ai meeting notes,22000,HIGH,6.40\n"
                    "best ai notetaker for therapists,1900,HIGH,4.10\n"
                    "what is a soap note,14000,LOW,0.90\n"
                    "therapy notes software,8100,HIGH,5.20\n"
                    "hvac work order app,3600,HIGH,4.80\n",
    "reviews.csv": "rating,title,review_text\n"
                   "2,Slow,\"I pay $69/month and still rewrite every note for insurance.\"\n"
                   "5,Great,\"Works well for our standups.\"\n"
                   "1,Wrong format,\"It writes a meeting summary, not a progress note.\"\n",
    "creatives.csv": "advertiser_id,title,creative_id,format,copy,days_running\n"
                     "AR01,Otter,CR1,text,\"Never take meeting notes again.\",466\n"
                     "AR02,Fireflies,CR2,text,\"Record and transcribe every call.\",297\n",
    "serp.json": json.dumps([
        {"title": "Mentalyc — AI Progress Notes for Therapists",
         "url": "https://www.mentalyc.com/",
         "snippet": "AI writes your SOAP and DAP progress notes. HIPAA compliant."},
        {"title": "12 Best Therapy Note Tools — Reviewed",
         "url": "https://blog.example.com/best", "snippet": "We tested 12 tools."},
    ]),
    "card.md": "# E001\n\n**Premises**\n\n"
               "- **X1**: A private-practice therapist must file a clinical note for every "
               "session before the insurer pays.\n"
               "- **X2**: Therapists write those notes outside their billable hours.\n",
    "thresholds.json": json.dumps({"thresholds": {
        "cluster_volume": {"op": ">=", "value": 8000, "measured": 12020, "premise": "X1"},
        "cpc_ceiling": {"op": "<=", "value": 6.0, "measured": 4.9, "premise": "X2"}}}),
}


def run_stage(label: str, argv: list[str]) -> dict | None:
    started = time.time()
    try:
        with redirect_stdout(io.StringIO()):
            rc = judge.main(argv)
    except SystemExit as exc:
        check(label, False, f"exited {exc.code}")
        return None
    except Exception as exc:  # noqa: BLE001
        check(label, False, f"{type(exc).__name__}: {exc}")
        return None
    out_index = argv.index("--out") + 1 if "--out" in argv else None
    payload = None
    if out_index and os.path.exists(argv[out_index]):
        with open(argv[out_index], encoding="utf-8") as fh:
            payload = json.load(fh)
    check(f"{label} ({time.time() - started:.2f}s)", rc == 0 and payload is not None)
    return payload


def test_live() -> None:
    print("live — one round-trip plus every judge.py stage")
    if not jev.available():
        check("credentials present", False, "set TYPESAFE_API_KEY or TYPESAFEAI_API_KEY")
        return
    client = jev.Client(use_cache=False)
    started = time.time()
    result = client.ask(
        "A customer writes: my payouts have failed for three days.",
        {"urgent": jev.Noul(instructions="Does this convey urgency?"),
         "team": jev.Choice(instructions="Who should handle this?",
                            criteria={"billing": "Payments and refunds",
                                      "engineering": "Bugs and outages"}),
         "anger": jev.Score(instructions="How angry is the writer?",
                            criteria=["calm", "annoyed", "furious"])})
    check(f"round-trip answers all three types ({time.time() - started:.2f}s)",
          result.noul("urgent").noul > 0.5
          and result.choice("team").choice in {"billing", "engineering"}
          and 0 <= result.score("anger").score <= 2)
    check("usage is metered", result.usage.input_tokens > 0 and result.usage.usd > 0)
    check("the served model is reported", result.model.startswith("jev-"))

    tmp = tempfile.mkdtemp()
    try:
        fix = os.path.join(tmp, "fix")
        os.makedirs(fix)
        for name, body in FIXTURES.items():
            with open(os.path.join(fix, name), "w", encoding="utf-8") as fh:
                fh.write(body)
        root = os.path.join(tmp, "research", "demand")
        with redirect_stdout(io.StringIO()):
            mazelib.main(["--root", root, "init", "--idea", "AI meeting notes",
                          "--slug", "t", "--budget-usd", "1"])
            lab = os.path.join(root, "t")
            for title, who in (("Generic notetaker", "anyone in meetings"),
                               ("Notes for therapists", "private-practice therapists"),
                               ("Work orders for field techs", "field service technicians")):
                mazelib.main(["--lab", lab, "add", "--title", title, "--who", who,
                              "--demand", "3"])

        def at(name: str) -> str:
            return os.path.join(fix, name)

        triage = run_stage("triage", ["triage", "--lab", lab, "--keywords", at("keywords.csv"),
                                      "--idea", "AI meeting notes",
                                      "--out", os.path.join(tmp, "triage.json")])
        if triage:
            assigned = {k for n in triage["nodes"].values()
                        for k in (x["keyword"] for x in n["cluster"])}
            check("triage drops an information query",
                  "what is a soap note" not in assigned)
            check("triage computes cluster volume in code",
                  all(isinstance(n["volume_total"], int) for n in triage["nodes"].values()))

        census = run_stage("census", ["census", "--lab", lab, "--serp", at("serp.json"),
                                      "--job", "write a compliant clinical progress note",
                                      "--out", os.path.join(tmp, "census.json")])
        if census:
            check("census prefers the vendor over the listicle",
                  [d["domain"] for d in census["seed_domains"][:1]] == ["mentalyc.com"],
                  str([d["domain"] for d in census["seed_domains"]]))

        reviews = run_stage("reviews", ["reviews", "--lab", lab, "--reviews", at("reviews.csv"),
                                        "--pain", "having to rewrite AI output into a "
                                                  "compliant clinical note",
                                        "--out", os.path.join(tmp, "reviews.json")])
        if reviews:
            check("reviews separates the pain from the praise",
                  0 < reviews["pain_hit_rate"] < 1, str(reviews["pain_hit_rate"]))

        creatives = run_stage("creatives", ["creatives", "--lab", lab,
                                            "--creatives", at("creatives.csv"),
                                            "--who", "private-practice therapists",
                                            "--wedge", "writes the note in the compliant "
                                                       "clinical format insurers accept",
                                            "--out", os.path.join(tmp, "creatives.json")])
        if creatives:
            check("creatives finds the open wedge", creatives["wedge_open"] is True)
            check("creatives counts sustained runs in code", creatives["sustained"] == 2)

        scores = run_stage("score", ["score", "--lab", lab,
                                     "--triage", os.path.join(tmp, "triage.json"),
                                     "--out", os.path.join(tmp, "scores.json")])
        if scores:
            check("every node is scored 0-5",
                  all(0 <= n["demand"] <= 5 for n in scores["nodes"].values()))

        explain = run_stage("explain", ["explain", "--lab", lab, "--card", at("card.md"),
                                        "--who", "private-practice therapists",
                                        "--decoys", "freelance designers,truck drivers,"
                                                    "retail managers",
                                        "--out", os.path.join(tmp, "explain.json")])
        if explain:
            check("the swap test rejects the decoys", explain["swap_mean"] < 0.5,
                  str(explain["swap_mean"]))
            check("explain reaches a verdict",
                  explain["verdict"] in {"HARD", "SOFT", "VARIES"})

        verdict = run_stage("verdict", ["verdict", "--lab", lab,
                                        "--thresholds", at("thresholds.json"),
                                        "--card", at("card.md"),
                                        "--families", "search,marketplace",
                                        "--who", "private-practice therapists",
                                        "--cluster-source", "harvested",
                                        "--out", os.path.join(tmp, "verdict.json")])
        if verdict:
            check("all thresholds met yields VALIDATED",
                  verdict["verdict"] == "VALIDATED", verdict["because"])

        one_family = run_stage("verdict (one family)",
                               ["verdict", "--lab", lab, "--thresholds", at("thresholds.json"),
                                "--card", at("card.md"), "--families", "search",
                                "--cluster-source", "harvested",
                                "--out", os.path.join(tmp, "verdict1.json")])
        if one_family:
            check("one family alone cannot validate",
                  one_family["verdict"] == "INCONCLUSIVE", one_family["because"])

        ledger = mazelib.load(lab).get("jev", {})
        check("every stage was ledgered", ledger.get("requests", 0) >= 7,
              str(ledger.get("requests")))
        check("jev spend stays off the instrument budget",
              mazelib.load(lab)["budget"]["spent_usd"] == 0.0)
        print(f"  live cost: ${ledger.get('usd', 0):.6f} over "
              f"{ledger.get('requests', 0)} requests")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def main() -> int:
    p = argparse.ArgumentParser(prog="selftest.py", description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--live", action="store_true",
                   help="also call the Jev API (~$0.001) and run every judge.py stage")
    args = p.parse_args()

    started = time.time()
    for fn in (test_questions, test_answers, test_batching, test_cache_keys, test_secrets,
               test_premises, test_rubric, test_cac, test_machine, test_lab_roundtrip):
        fn()
    if args.live:
        test_live()
    else:
        print("live tier skipped — pass --live to exercise the API and the stages")

    print(f"\n{PASS} passed, {FAIL} failed in {time.time() - started:.1f}s")
    return 1 if FAIL else 0


if __name__ == "__main__":
    raise SystemExit(main())
