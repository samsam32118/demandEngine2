#!/usr/bin/env python3
"""jev.py — typed client for TypeSafe's Jev (System One) model.

Jev is not a chat model. It takes a `state` and a map of typed *questions*
and returns typed answers your code can branch on:

    Noul   -> P(yes), 0..1                      (no confidence field)
    Choice -> the winning option + probabilities + confidence
    Score  -> a probability-weighted position on your rubric + confidence

The division of labour this whole skill rests on: **code owns the workflow
and every number; Jev supplies the semantic judgment.** Never ask Jev to
count, to compare dates, or to do arithmetic — it is bad at all three (see
references/jev-contract.md). Ask it whether a sentence means something.

Wire format (docs.typesafe.ai/api):

    POST https://api.typesafe.ai/v1/systemone
    Authorization: Bearer <key>
    {"state": ..., "model": "jev-latest", "questions": {...}}

Speed comes from three things this module does for you:

1. **Fan-out.** Every question in one request. Jev ingests the state once and
   evaluates all questions against it in parallel, so 50 questions cost about
   what 1 costs in wall-clock. (TypeSafe measure 12x cheaper / 10x faster
   than one-call-per-question.)
2. **Auto-chunking + concurrency.** Past the 64k context budget we split on
   question boundaries and run the chunks concurrently.
3. **A content-addressed cache.** Re-running a stage is free and instant,
   which is what makes the loop cheap to iterate on.

Stdlib-only, to match every other skill in this repo (no venv, no install).

Credentials: TYPESAFE_API_KEY, else TYPESAFEAI_API_KEY, else either name in a
.env in the working directory. The key is never printed, never logged, and
redacted out of every error message.

CLI:
    jev.py check                      # credentials + reachability, no secrets printed
    jev.py models                     # what this account may send in `model`
    jev.py ask --state-file s.json --questions-file q.json [--out a.json]
"""

from __future__ import annotations

import argparse
import concurrent.futures
import hashlib
import json
import os
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from typing import Any, Callable, Iterable, Mapping, Sequence

DEFAULT_BASE_URL = "https://api.typesafe.ai"
DEFAULT_MODEL = "jev-latest"
DEFAULT_TIMEOUT = 60.0

# jev-1.13: $42 per billion input tokens. Output tokens are free.
USD_PER_INPUT_TOKEN = 42.0 / 1e9

# Model context budget: 64k for state + all questions; 32k for state + the
# single longest question. We chunk well inside both, because accuracy also
# falls as the state grows (jaggedness #5), not just the hard limit.
CONTEXT_BUDGET_TOKENS = 64_000
STATE_BUDGET_TOKENS = 32_000
SAFETY = 0.75
DEFAULT_MAX_QUESTIONS = 64
DEFAULT_CONCURRENCY = 8

_RETRY_STATUS = {429, 500, 502, 503, 504, 529}
_MAX_ATTEMPTS = 5

# Hard API limits, enforced client-side so a bad question fails locally
# instead of burning a round-trip on a 422.
MAX_CHOICE_OPTIONS = 255
MAX_SCORE_LEVELS = 10
MIN_SCORE_LEVELS = 2


# ------------------------------------------------------------------ errors

class JevError(RuntimeError):
    """Any failure talking to Jev. Never carries the API key."""


class JevAuthError(JevError):
    pass


class JevValidationError(JevError):
    """422 — the request body was malformed, or we caught it before sending."""


class JevRateLimited(JevError):
    pass


# --------------------------------------------------------------- questions

@dataclass(frozen=True)
class Noul:
    """A yes/no question. The answer is P(yes) as a float in 0..1.

    `criteria` optionally pins down what a yes and a no mean; use it whenever
    the boundary case matters, because Jev reads the instruction literally.
    """

    instructions: Any
    criteria: Mapping[str, Any] | None = None

    def wire(self) -> dict:
        q: dict[str, Any] = {"type": "noul", "instructions": self.instructions}
        if self.criteria:
            bad = set(self.criteria) - {"true", "false"}
            if bad:
                raise JevValidationError(
                    f"Noul criteria keys must be 'true'/'false', got {sorted(bad)}")
            q["criteria"] = dict(self.criteria)
        return q


@dataclass(frozen=True)
class Choice:
    """Pick one option from a fixed set. Relative: it settles *which* option.

    A Choice is not a set of independent yes/no answers — the probabilities
    sum to 1, so a Choice always picks something even when nothing fits. When
    "none of these" is a real outcome, give it an explicit option.
    """

    instructions: Any
    criteria: Mapping[str, Any]

    def wire(self) -> dict:
        if not self.criteria:
            raise JevValidationError("Choice needs at least one option")
        if len(self.criteria) > MAX_CHOICE_OPTIONS:
            raise JevValidationError(
                f"Choice takes at most {MAX_CHOICE_OPTIONS} options, "
                f"got {len(self.criteria)}")
        return {
            "type": "choice",
            "instructions": self.instructions,
            "criteria": dict(self.criteria),
        }


@dataclass(frozen=True)
class Score:
    """Rate against ordered levels, cheapest level first.

    The answer lands *between* levels (a probability-weighted position), so
    use it for ranking and thresholding — never to reconstruct a real-world
    quantity by interpolation, which jev-1.13 is not calibrated for.
    """

    instructions: Any
    criteria: Sequence[Any]

    def wire(self) -> dict:
        n = len(self.criteria)
        if not (MIN_SCORE_LEVELS <= n <= MAX_SCORE_LEVELS):
            raise JevValidationError(
                f"Score takes {MIN_SCORE_LEVELS}-{MAX_SCORE_LEVELS} levels, got {n}")
        return {
            "type": "score",
            "instructions": self.instructions,
            "criteria": list(self.criteria),
        }


Question = Noul | Choice | Score


# ----------------------------------------------------------------- answers

@dataclass(frozen=True)
class NoulAnswer:
    key: str
    noul: float

    @property
    def confidence(self) -> None:
        """Nouls carry no confidence — the probability *is* the answer."""
        return None

    def yes(self, threshold: float = 0.5) -> bool:
        return self.noul > threshold


@dataclass(frozen=True)
class ChoiceAnswer:
    key: str
    choice: str
    probabilities: Mapping[str, float]
    confidence: float

    def at_least(self, confidence: float) -> str | None:
        """The pick, or None when the model is telling you it isn't sure."""
        return self.choice if self.confidence >= confidence else None


@dataclass(frozen=True)
class ScoreAnswer:
    key: str
    score: float
    legend: Mapping[str, str]
    probabilities: Mapping[str, float]
    confidence: float

    @property
    def levels(self) -> int:
        return len(self.legend)

    @property
    def normalized(self) -> float:
        """0..1 across the rubric — the form composite scoring wants."""
        top = max(self.levels - 1, 1)
        return self.score / top

    @property
    def label(self) -> str:
        """The nearest level's description, for human-readable output."""
        return self.legend.get(str(int(round(self.score))), "")


Answer = NoulAnswer | ChoiceAnswer | ScoreAnswer


def _parse_answer(key: str, raw: Mapping[str, Any]) -> Answer:
    kind = raw.get("type")
    if kind == "noul":
        return NoulAnswer(key=key, noul=float(raw["noul"]))
    if kind == "choice":
        return ChoiceAnswer(
            key=key,
            choice=str(raw["choice"]),
            probabilities={k: float(v) for k, v in raw.get("probabilities", {}).items()},
            confidence=float(raw.get("confidence", 0.0)),
        )
    if kind == "score":
        return ScoreAnswer(
            key=key,
            score=float(raw["score"]),
            legend={str(k): str(v) for k, v in raw.get("legend", {}).items()},
            probabilities={str(k): float(v) for k, v in raw.get("probabilities", {}).items()},
            confidence=float(raw.get("confidence", 0.0)),
        )
    raise JevError(f"unknown answer type {kind!r} for question {key!r}")


@dataclass
class Usage:
    """Token and money ledger. Output tokens are free on jev-1.13."""

    requests: int = 0
    cached_requests: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    seconds: float = 0.0

    @property
    def usd(self) -> float:
        return self.input_tokens * USD_PER_INPUT_TOKEN

    def add(self, other: "Usage") -> None:
        self.requests += other.requests
        self.cached_requests += other.cached_requests
        self.input_tokens += other.input_tokens
        self.output_tokens += other.output_tokens
        self.seconds += other.seconds

    def as_dict(self) -> dict:
        return {
            "requests": self.requests,
            "cached_requests": self.cached_requests,
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "usd": round(self.usd, 6),
            "seconds": round(self.seconds, 3),
        }

    def line(self) -> str:
        return (
            f"jev: {self.requests} request(s) (+{self.cached_requests} cached) · "
            f"{self.input_tokens:,} input tokens · ${self.usd:.6f} · "
            f"{self.seconds:.2f}s wall"
        )


@dataclass
class Result:
    """Answers keyed exactly as the questions were, plus what it cost."""

    answers: dict[str, Answer]
    usage: Usage = field(default_factory=Usage)
    model: str = ""

    def __getitem__(self, key: str) -> Answer:
        return self.answers[key]

    def __contains__(self, key: str) -> bool:
        return key in self.answers

    def noul(self, key: str) -> NoulAnswer:
        return _expect(self.answers[key], NoulAnswer, key)

    def choice(self, key: str) -> ChoiceAnswer:
        return _expect(self.answers[key], ChoiceAnswer, key)

    def score(self, key: str) -> ScoreAnswer:
        return _expect(self.answers[key], ScoreAnswer, key)


def _expect(answer: Answer, kind: type, key: str):
    if not isinstance(answer, kind):
        raise JevError(
            f"question {key!r} answered as {type(answer).__name__}, "
            f"expected {kind.__name__}")
    return answer


# --------------------------------------------------------------- the client

def _read_dotenv(names: Iterable[str]) -> str | None:
    path = os.path.join(os.getcwd(), ".env")
    if not os.path.exists(path):
        return None
    wanted = set(names)
    try:
        with open(path, encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, v = line.split("=", 1)
                if k.strip() in wanted:
                    v = v.strip().strip('"').strip("'")
                    if v:
                        return v
    except OSError:
        return None
    return None


#: Checked in order. TYPESAFE_API_KEY is the name the official SDKs use;
#: TYPESAFEAI_API_KEY is what this environment provisions.
API_KEY_ENV_NAMES = ("TYPESAFE_API_KEY", "TYPESAFEAI_API_KEY")


def resolve_api_key() -> str:
    for name in API_KEY_ENV_NAMES:
        value = (os.environ.get(name) or "").strip()
        if value:
            return value
    value = _read_dotenv(API_KEY_ENV_NAMES)
    if value:
        return value
    raise JevAuthError(
        "no TypeSafe credentials. Set " + " or ".join(API_KEY_ENV_NAMES)
        + " (get a key at https://console.typesafe.ai/), or put one in a .env "
          "in the working directory."
    )


def key_fingerprint(key: str) -> str:
    """A non-reversible id for a key, so logs can say *which* key without
    leaking any of it."""
    return hashlib.sha256(key.encode("utf-8")).hexdigest()[:8]


def _redact(text: str, key: str) -> str:
    return text.replace(key, "<redacted>") if key else text


def estimate_tokens(obj: Any) -> int:
    """Cheap upper-ish bound: ~4 characters per token of compact JSON.

    Only used to decide where to split a batch, so approximate is fine —
    the SAFETY margin absorbs the error.
    """
    return max(1, len(json.dumps(obj, ensure_ascii=False, separators=(",", ":"))) // 4)


class Client:
    """A Jev client. Thread-safe: `ask` holds no per-call state."""

    def __init__(
        self,
        *,
        api_key: str | None = None,
        base_url: str | None = None,
        model: str | None = None,
        timeout: float = DEFAULT_TIMEOUT,
        cache_dir: str | None = None,
        concurrency: int = DEFAULT_CONCURRENCY,
        max_questions: int = DEFAULT_MAX_QUESTIONS,
        use_cache: bool = True,
    ) -> None:
        self._key = api_key or resolve_api_key()
        self.base_url = (base_url or os.environ.get("TYPESAFE_BASE_URL")
                         or DEFAULT_BASE_URL).rstrip("/")
        self.model = (model or os.environ.get("TYPESAFE_DEFAULT_MODEL")
                      or DEFAULT_MODEL)
        self.timeout = timeout
        self.cache_dir = cache_dir
        self.concurrency = max(1, concurrency)
        self.max_questions = max(1, max_questions)
        self.use_cache = use_cache and bool(cache_dir)
        self.usage = Usage()

    # -- caching ---------------------------------------------------------

    def _cache_path(self, payload: Mapping[str, Any]) -> str | None:
        if not self.use_cache or not self.cache_dir:
            return None
        blob = json.dumps(payload, sort_keys=True, ensure_ascii=False,
                          separators=(",", ":")).encode("utf-8")
        digest = hashlib.sha256(blob).hexdigest()
        return os.path.join(self.cache_dir, f"{digest}.json")

    def _cache_read(self, path: str | None) -> dict | None:
        if not path or not os.path.exists(path):
            return None
        try:
            with open(path, encoding="utf-8") as fh:
                return json.load(fh)
        except (OSError, ValueError):
            return None

    def _cache_write(self, path: str | None, body: Mapping[str, Any]) -> None:
        if not path:
            return
        try:
            os.makedirs(os.path.dirname(path), exist_ok=True)
            tmp = f"{path}.{os.getpid()}.tmp"
            with open(tmp, "w", encoding="utf-8") as fh:
                json.dump(body, fh, ensure_ascii=False)
            os.replace(tmp, path)
        except OSError:
            pass  # a cache that cannot be written is a slowdown, not a failure

    # -- transport -------------------------------------------------------

    def _post(self, path: str, payload: Mapping[str, Any]) -> dict:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        headers = {
            "Authorization": f"Bearer {self._key}",
            "Content-Type": "application/json",
            "User-Agent": "demand-forecasting-skill/2.0",
        }
        url = f"{self.base_url}{path}"
        delay = 1.0
        last = ""
        for attempt in range(_MAX_ATTEMPTS):
            req = urllib.request.Request(url, data=body, headers=headers, method="POST")
            try:
                with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                    return json.loads(resp.read().decode("utf-8", errors="replace"))
            except urllib.error.HTTPError as exc:
                raw = _redact((exc.read() or b"").decode("utf-8", errors="replace")[:500],
                              self._key)
                if exc.code == 401:
                    raise JevAuthError(
                        f"401 from TypeSafe — the key (fingerprint "
                        f"{key_fingerprint(self._key)}) was rejected: {raw}") from None
                if exc.code == 422:
                    raise JevValidationError(f"422 malformed request: {raw}") from None
                if exc.code in _RETRY_STATUS and attempt < _MAX_ATTEMPTS - 1:
                    retry_after = exc.headers.get("retry-after") if exc.headers else None
                    time.sleep(_retry_delay(retry_after, delay))
                    delay *= 2
                    continue
                if exc.code == 429:
                    raise JevRateLimited(f"429 rate limited: {raw}") from None
                raise JevError(f"HTTP {exc.code} from TypeSafe: {raw}") from None
            except urllib.error.URLError as exc:
                last = _redact(str(exc.reason), self._key)
                if attempt < _MAX_ATTEMPTS - 1:
                    time.sleep(delay)
                    delay *= 2
                    continue
                raise JevError(f"network error reaching TypeSafe: {last}") from None
        raise JevError(f"TypeSafe unreachable after {_MAX_ATTEMPTS} attempts: {last}")

    # -- the one call that matters ---------------------------------------

    def ask(
        self,
        state: Any,
        questions: Mapping[str, Question],
        *,
        model: str | None = None,
        on_chunk: Callable[[int, int], None] | None = None,
    ) -> Result:
        """Evaluate every question against one state and return typed answers.

        Questions are sent in as few requests as the context budget allows,
        and those requests run concurrently. Answers come back keyed exactly
        as you passed them in.
        """
        if not questions:
            return Result(answers={}, model=model or self.model)

        model = model or self.model
        wire = {key: q.wire() for key, q in questions.items()}
        state_tokens = estimate_tokens(state)
        if state_tokens > STATE_BUDGET_TOKENS * SAFETY:
            raise JevValidationError(
                f"state is ~{state_tokens:,} tokens, over the {STATE_BUDGET_TOKENS:,} "
                f"budget. Filter it in code before asking — accuracy falls with "
                f"irrelevant context, so this is a correctness limit, not just a size one."
            )

        chunks = self._chunk(wire, state_tokens)
        if on_chunk:
            on_chunk(0, len(chunks))

        started = time.time()
        merged: dict[str, Answer] = {}
        answered_model = model
        if len(chunks) == 1:
            results = [self._ask_one(state, chunks[0], model)]
        else:
            workers = min(self.concurrency, len(chunks))
            with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as pool:
                futures = [pool.submit(self._ask_one, state, c, model) for c in chunks]
                results = [f.result() for f in futures]
        for answers, used, served_model in results:
            merged.update(answers)
            self.usage.add(used)
            answered_model = served_model or answered_model
        if on_chunk:
            on_chunk(len(chunks), len(chunks))

        missing = set(wire) - set(merged)
        if missing:
            raise JevError(f"TypeSafe returned no answer for: {sorted(missing)}")

        usage = Usage(
            requests=sum(r[1].requests for r in results),
            cached_requests=sum(r[1].cached_requests for r in results),
            input_tokens=sum(r[1].input_tokens for r in results),
            output_tokens=sum(r[1].output_tokens for r in results),
            seconds=time.time() - started,
        )
        return Result(answers=merged, usage=usage, model=answered_model)

    def _chunk(self, wire: Mapping[str, dict], state_tokens: int) -> list[dict]:
        """Split questions so each request stays inside the context budget.

        Sorted by key so chunk boundaries — and therefore cache keys — are
        stable across runs.
        """
        budget = int(CONTEXT_BUDGET_TOKENS * SAFETY) - state_tokens
        if budget <= 0:
            raise JevValidationError("state leaves no room for questions; filter it first")
        chunks: list[dict] = []
        current: dict[str, dict] = {}
        current_tokens = 0
        for key in sorted(wire):
            q = wire[key]
            cost = estimate_tokens(q) + estimate_tokens(key)
            if cost > budget:
                raise JevValidationError(
                    f"question {key!r} is ~{cost:,} tokens, too large for one request")
            over_budget = current and current_tokens + cost > budget
            over_count = len(current) >= self.max_questions
            if over_budget or over_count:
                chunks.append(current)
                current, current_tokens = {}, 0
            current[key] = q
            current_tokens += cost
        if current:
            chunks.append(current)
        return chunks

    def _ask_one(
        self, state: Any, questions: Mapping[str, dict], model: str
    ) -> tuple[dict[str, Answer], Usage, str]:
        payload = {"state": state, "model": model, "questions": dict(questions)}
        path = self._cache_path(payload)
        cached = self._cache_read(path)
        if cached is not None:
            answers = {k: _parse_answer(k, v) for k, v in cached.get("answers", {}).items()}
            return answers, Usage(cached_requests=1), cached.get("model", model)

        started = time.time()
        body = self._post("/v1/systemone", payload)
        elapsed = time.time() - started
        raw_answers = body.get("answers")
        if not isinstance(raw_answers, dict):
            raise JevError(f"unexpected response shape: {sorted(body)}")
        self._cache_write(path, body)
        used = body.get("usage") or {}
        usage = Usage(
            requests=1,
            input_tokens=int(used.get("input_tokens", 0)),
            output_tokens=int(used.get("output_tokens", 0)),
            seconds=elapsed,
        )
        answers = {k: _parse_answer(k, v) for k, v in raw_answers.items()}
        return answers, usage, str(body.get("model", model))

    def models(self) -> list[dict]:
        req = urllib.request.Request(
            f"{self.base_url}/v1/models",
            headers={"Authorization": f"Bearer {self._key}",
                     "User-Agent": "demand-forecasting-skill/2.0"},
            method="GET",
        )
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                body = json.loads(resp.read().decode("utf-8", errors="replace"))
        except urllib.error.HTTPError as exc:
            raw = _redact((exc.read() or b"").decode("utf-8", errors="replace")[:300], self._key)
            raise JevError(f"HTTP {exc.code} listing models: {raw}") from None
        except urllib.error.URLError as exc:
            raise JevError(f"network error listing models: "
                           f"{_redact(str(exc.reason), self._key)}") from None
        return list(body.get("models", []))


def _retry_delay(retry_after: str | None, fallback: float) -> float:
    if retry_after:
        try:
            return max(0.0, min(30.0, float(retry_after)))
        except ValueError:
            pass
    return fallback


def available() -> bool:
    """True when a credential exists. Use to degrade honestly, not to crash."""
    try:
        resolve_api_key()
        return True
    except JevAuthError:
        return False


def build_question(spec: Mapping[str, Any]) -> Question:
    """Build a question from its wire-format dict (used by the CLI)."""
    kind = spec.get("type")
    if kind == "noul":
        return Noul(instructions=spec["instructions"], criteria=spec.get("criteria"))
    if kind == "choice":
        return Choice(instructions=spec["instructions"], criteria=spec["criteria"])
    if kind == "score":
        return Score(instructions=spec["instructions"], criteria=spec["criteria"])
    raise JevValidationError(f"question type must be noul/choice/score, got {kind!r}")


# ---------------------------------------------------------------------- CLI

def _cmd_check(args) -> int:
    try:
        key = resolve_api_key()
    except JevAuthError as exc:
        print(f"jev: OFFLINE — {exc}", file=sys.stderr)
        return 1
    source = next((n for n in API_KEY_ENV_NAMES if (os.environ.get(n) or "").strip()), ".env")
    print(f"credential: found via {source} (fingerprint {key_fingerprint(key)}) — value not shown")
    client = Client(api_key=key, use_cache=False)
    print(f"base url:   {client.base_url}")
    print(f"model:      {client.model}")
    started = time.time()
    try:
        result = client.ask(
            "A customer writes: my payouts have failed for three days.",
            {"urgent": Noul(instructions="Does this convey urgency?")},
        )
    except JevError as exc:
        print(f"jev: UNREACHABLE — {exc}", file=sys.stderr)
        return 1
    print(f"reachable:  yes — answered by {result.model} in {time.time() - started:.2f}s "
          f"(P(urgent)={result.noul('urgent').noul:.2f})")
    print(result.usage.line())
    return 0


def _cmd_models(args) -> int:
    client = Client(use_cache=False)
    for m in client.models():
        print(f"{m.get('name','?'):<14} {m.get('release_date','') :<12} {m.get('description','')}")
    return 0


def _cmd_ask(args) -> int:
    with open(args.questions_file, encoding="utf-8") as fh:
        raw = json.load(fh)
    questions = {k: build_question(v) for k, v in raw.items()}
    if args.state_file:
        with open(args.state_file, encoding="utf-8") as fh:
            state = json.load(fh) if args.state_file.endswith(".json") else fh.read()
    else:
        state = args.state or ""
    client = Client(cache_dir=args.cache_dir, use_cache=not args.no_cache,
                    model=args.model, concurrency=args.concurrency)
    result = client.ask(state, questions)
    out = {
        "model": result.model,
        "usage": result.usage.as_dict(),
        "answers": {k: _answer_dict(a) for k, a in result.answers.items()},
    }
    text = json.dumps(out, indent=2, ensure_ascii=False)
    if args.out:
        with open(args.out, "w", encoding="utf-8") as fh:
            fh.write(text + "\n")
        print(f"wrote {args.out}")
        print(result.usage.line())
    else:
        print(text)
    return 0


def _answer_dict(a: Answer) -> dict:
    if isinstance(a, NoulAnswer):
        return {"type": "noul", "noul": a.noul}
    if isinstance(a, ChoiceAnswer):
        return {"type": "choice", "choice": a.choice,
                "probabilities": dict(a.probabilities), "confidence": a.confidence}
    return {"type": "score", "score": a.score, "label": a.label,
            "normalized": round(a.normalized, 4), "legend": dict(a.legend),
            "probabilities": dict(a.probabilities), "confidence": a.confidence}


def main(argv: Sequence[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        prog="jev.py", description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)

    sp = sub.add_parser("check", help="credentials + reachability (prints no secrets)")
    sp.set_defaults(fn=_cmd_check)

    sp = sub.add_parser("models", help="models this account may send in `model`")
    sp.set_defaults(fn=_cmd_models)

    sp = sub.add_parser("ask", help="run a questions file against a state")
    sp.add_argument("--questions-file", required=True,
                    help="JSON map of question id -> wire-format question")
    sp.add_argument("--state-file", help="JSON or text file holding the state")
    sp.add_argument("--state", help="literal state string (alternative to --state-file)")
    sp.add_argument("--out", help="write the answers JSON here instead of stdout")
    sp.add_argument("--model", help=f"override the model (default {DEFAULT_MODEL})")
    sp.add_argument("--cache-dir", default=".jev-cache")
    sp.add_argument("--no-cache", action="store_true")
    sp.add_argument("--concurrency", type=int, default=DEFAULT_CONCURRENCY)
    sp.set_defaults(fn=_cmd_ask)

    args = p.parse_args(argv)
    try:
        return args.fn(args)
    except JevError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
