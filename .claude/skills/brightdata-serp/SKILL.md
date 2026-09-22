---
name: brightdata-serp
description: Run Google search queries through Bright Data's SERP API and get back a markdown rendering of the SERP (or structured JSON, or raw HTML). This is the sole web-search backend for Rivas Will. Trigger whenever the user says "google <query>", "serp <query>", "search for <query>", "run this through Bright Data SERP", or a heartbeat needs Google results. Billed against the shared Bright Data daily cap (100/day); the calling agent tracks the daily count.
---

# brightdata-serp

Thin wrapper around Bright Data's **SERP API** (pay-as-you-go). One endpoint,
`POST https://api.brightdata.com/request` with a payload that tells Bright
Data which zone, URL, and body transformation to apply. We default to Google
and `data_format=markdown` so Bright Data renders the SERP as markdown
server-side — ready to feed straight to an LLM, paste into a dossier, or
chunk with a markdown-aware splitter. No HTML parsing on our side.

Stdlib-only Python — no `.venv` to create, no dependencies to install. Shares
the `BRIGHTDATA_API_TOKEN` with the other `brightdata-*` skills, and all
draw from one shared 100/day Bright Data cap the calling agent tracks.

## Prerequisites

- `BRIGHTDATA_API_TOKEN` — same token the crunchbase/pitchbook/linkedin
  skills use. Must belong to an account with a SERP API zone enabled.
- `BRIGHTDATA_SERP_ZONE` — the zone name. Defaults to `serp_api1` (matches
  the operator's working example). Override via env var if your account uses
  a different name.

Scripts exit with a clear error if the token is missing.

## Billing model — read this before running anything

Every successful call is one billable SERP request on your Bright Data plan.
This is the sole web-search backend — there is no free fallback. Treat each
call like the small-but-real expense it is: prefer a tight, specific query
over two speculative ones.

- One call = one billable request, regardless of `--num`.
- Responses are cached at `workspace/cache/<sha256>.json` keyed on
  `(engine, query, hl, gl, num)`. Re-running the same query is free. Pass
  `--no-cache` only if you deliberately want a fresh paid call.
- The Bright Data daily cap (100 calls across crunchbase + pitchbook + linkedin
  + serp, shared token) is the hard stop. The calling agent enforces it.

## When to use

SERP is Rivas Will's only web-search backend. Use it for every general search
the agent needs to run. Call `search.py` directly whenever you want:

- Google results for a general question or site-targeted query.
- Non-US geolocation (`--gl de`, `--gl uk`) and localized interface language.
- A site-targeted sweep (e.g. `site:sec.gov "<company>"` or
  `site:linkedin.com/in/ "<name>"`).
- The full SERP rendered as markdown for dossier use, or parsed as structured
  JSON when you just want the top organic URLs.

Before sending a query, consider whether the cache already has it
(a free cache hit is flagged `_from_cache`) and whether the query is distinct from recent
searches — duplicates are waste.

## Operations

Run from the repo root. Script prints one JSON object to stdout.

### Search

```bash
python .claude/skills/brightdata-serp/scripts/search.py "<query>" \
    [--engine google] [--hl en] [--gl us] [--num 10] \
    [--country us] [--format markdown|parsed|raw] \
    [--zone <zone>] [--stdout json|markdown] [--no-cache]
```

Flags:
- `--engine google` — only Google at launch. The flag exists so adding Bing
  or Yandex later is one function, not a CLI refactor.
- `--hl <code>` — Google interface language, e.g. `en`, `de`, `fr`. Default
  `en`.
- `--gl <code>` — Google geolocation country code, e.g. `us`, `uk`, `de`.
  Default `us`. Goes into the search URL.
- `--num <N>` — number of results to request. Default 10.
- `--country <code>` — Bright Data proxy country, e.g. `us`, `de`. Default
  `us`. Goes into the Bright Data request payload (distinct from `--gl`).
- `--format markdown|parsed|raw` — output format. Default `markdown`.
  - `markdown` — Bright Data renders the full SERP as markdown
    server-side (`data_format=markdown`). Ideal for feeding into an LLM.
  - `parsed` — append `brd_json=1` so Bright Data returns structured JSON;
    the skill normalises it into a list of
    `{title, url, snippet, position}`.
  - `raw` — proxied HTML response, no transformation. For debugging.
- `--zone <name>` — override `$BRIGHTDATA_SERP_ZONE`. Rarely needed.
- `--stdout json|markdown` — stdout shape. Default `json` (the full payload
  as JSON). With `--stdout markdown`, only the markdown body is printed —
  convenient for piping into a file or another tool. Only meaningful with
  `--format markdown`.
- `--no-cache` — bypass `workspace/cache/` and force a fresh paid call. Use
  sparingly — the whole point of the cache is not paying twice for the same
  answer.

### Output shape

Default (`--format markdown`):
```json
{
  "engine": "google",
  "query": "pizza",
  "url": "https://www.google.com/search?q=pizza&hl=en&gl=us&num=10",
  "format": "markdown",
  "status_code": 200,
  "markdown": "pizza - Google Search\n\n...full SERP rendered as markdown...",
  "retrieved_at": "2026-04-22T15:30:00Z"
}
```

With `--format parsed`:
```json
{
  "engine": "google",
  "query": "pizza",
  "url": "https://www.google.com/search?q=pizza&hl=en&gl=us&num=10&brd_json=1",
  "format": "parsed",
  "results": [
    {"title": "...", "url": "https://...", "snippet": "...", "position": 1}
  ],
  "raw_parsed": { ... Bright Data's full parsed response ... },
  "retrieved_at": "2026-04-22T15:30:00Z"
}
```

With `--format raw`:
```json
{
  "engine": "google",
  "query": "pizza",
  "url": "https://www.google.com/search?q=pizza&hl=en&gl=us&num=10",
  "format": "raw",
  "body": "<html>...</html>",
  "retrieved_at": "2026-04-22T15:30:00Z"
}
```

The `parsed` format's `results` list is `{title, url, snippet, position}`.
Downstream code that wants the legacy `{title, href, body}` shape (e.g.
email-guesser) does the renaming inline.

### Smoke test

```bash
python .claude/skills/brightdata-serp/scripts/smoke_test.py
```

One call — queries `"pizza"` with `--no-cache` so it actually hits the wire,
asserts the parser returned ≥1 organic result. Run after any change to the
token or zone env vars. Costs one billable request.

## Calling protocol — self-contained

This skill is self-contained: call `search.py` directly. The calling agent
(Rivas) owns the 100/day Bright Data budget and tracks it in its own state —
there is no shared ledger and no `research` front door. The protocol is:

```bash
python3 .claude/skills/brightdata-serp/scripts/search.py "<query>" --num 10
```

Budget bookkeeping is the caller's job, in three honest steps:

1. **Gate** — before calling, confirm today's Bright Data count is under 100.
2. **Call** — run `search.py` as above (add `--format parsed` for structured
   results, `--country` / `--gl` for geolocation, `--format raw` for HTML).
3. **Log** — if the call actually hit the wire, increment today's counter and
   append a one-line justification to `memory/YYYY-MM-DD.md`. A cache hit
   (`_from_cache: true` in the payload) means no paid call happened — don't
   count it.

The justification is the audit trail. Write it honestly: "site:sec.gov sweep
for Q1 filings", "resolve LinkedIn URL for founder", etc. — so spend stays
reconstructable.

## Design notes

- **Why markdown by default.** Rivas Will dossiers, memos, and sector
  briefs are markdown. A search that returns markdown drops straight into
  a `workspace/` file or an LLM prompt without a parse step. Bright Data
  renders the SERP on their side, so we don't own a fragile HTML parser.
  When a caller needs structured results (e.g. "the top 10 organic URLs"),
  they switch to `--format parsed`.
- **Why cache by query, not by URL.** Two callers asking the same question
  with different `--num` values should share results up to the smaller N.
  We intentionally include `num` and `format` in the cache key so
  `--num 10` and `--num 50` don't collide, and a markdown cache entry
  doesn't satisfy a parsed-JSON request.
- **Why one shared budget.** SERP, crunchbase, pitchbook, and
  brightdata-linkedin all share one Bright Data account with one token and
  one daily quota. The calling agent tracks a single 100/day counter across
  all of them — one real-world quota, one counter. That's the honest model.
- **Why only Google at launch.** Bing/Yandex/Yahoo are one function each to
  add in `_engine_url()`. Waiting until we actually need them avoids
  writing parsers for engines we never use.
- **Why stdlib-only.** No
  `.venv` means no install step when this repo gets cloned fresh.

## Files

```
.claude/skills/brightdata-serp/
├── SKILL.md        — this file
└── scripts/
    ├── client.py   — POST /request helper, auth, retries
    ├── search.py   — CLI entry point, caching, parser normalization
    └── smoke_test.py
```
