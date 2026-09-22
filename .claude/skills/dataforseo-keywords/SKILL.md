---
name: dataforseo-keywords
description: Pull live Google Ads keyword data — real search volume, CPC, competition, top-of-page bids, monthly trends, and click/spend forecasts — from DataForSEO's Google Ads Keywords Data API. Use this whenever the user wants to size demand for keywords, research what a domain ranks/bids for, validate ad targeting, estimate CPCs or ad spend, build or check a keyword list, or read search volume/competition for terms like "ai sales coach" or "sales coaching app". Trigger on "keyword research", "search volume for X", "how much does it cost to advertise on X", "what keywords does <domain> target", "CPC for these keywords", "forecast clicks/spend for this ad", "is there demand for X", or any request to ground ad/keyword decisions in real Google data instead of guesses. Prefer this over web search whenever the user wants numeric keyword metrics. Opinionated guidance (strong defaults, not fences — override when the task genuinely calls for it) — favor grounding keyword discovery in a real website or page via `for-site` (target a live domain or URL — the products, competitors, and landing pages people actually search are higher-signal than terms invented from thin air); price a list you already have with `search-volume` (the cheapest path — up to 1000 keywords per billable call); reach for `for-keywords` deliberately and with judgement, never reflexively — it expands off the seed's breadth, so niche seeds (e.g. "ai sales coach") return almost nothing while broad head terms (e.g. "crm software") balloon into thousands of noisy billable rows, so seed it thoughtfully and sort by volume; use `ad-traffic` for click/spend forecasts. Always set location and language (defaults US/en) — metrics swing enormously by geo (e.g. "coffee shop" is ~2.7M/mo in the US but ~1.3k in Oslo), so a wrong location silently produces confidently wrong numbers.
---

# dataforseo-keywords

Live keyword data from **DataForSEO's Google Ads Keywords Data API** — the
same numbers Google Keyword Planner shows, but scriptable. Four operations,
one CLI (`scripts/keywords.py`):

| Operation | What you get | Max per call | Best for |
|---|---|---|---|
| `search-volume` | Exact search volume, competition, CPC, bids, 12-month trend | **1000 keywords in / 1000 rows out** | Cheapest way to price a list you already have |
| `for-keywords` | The seeds **expanded** into new keyword ideas, same metrics | **20 seeds in / up to 20,000 ideas out** | Discovering keywords you don't have yet |
| `for-site` | Every keyword a domain (or page) is relevant to, same metrics | **1 target in / up to ~2000+ rows out** | Reverse-engineering a domain's keyword footprint |
| `ad-traffic` | A **forecast** of clicks, avg CPC, and total spend at a bid + match | **1000 keywords in / 1 aggregate row out** | Estimating what a campaign would cost and deliver |

**Every keyword call costs the same whether it carries 1 keyword or its max**,
so fill the batch. Two things to internalize before you run anything:

- **`for-keywords` expansion scales with how *broad* the seed is.** A broad
  head term (`crm software` → ~1,600 ideas, `laptop` → ~2,500) expands hugely;
  a niche long-tail seed (`ai sales coach`) may return **only itself**, because
  Google Ads genuinely has no more ideas to give for it. If you want breadth,
  seed with head terms and let it expand; if you only want metrics for exact
  terms you already have, that's `search-volume`, not `for-keywords`.
- **`search-volume` and `ad-traffic` do not expand** — you get exactly what you
  send (one row per keyword for `search-volume`; one campaign-level aggregate
  for `ad-traffic`).

See *Cost model* below before running anything.

This is how James makes ad decisions **data-driven** rather than gut-feel
(see `marketing/CLAUDE.md`): pull real search volume and CPC for candidate
terms before committing budget in the Google $500 ad round, and save the
results next to the Keyword Planner exports in `research/data/keywords/`.

Stdlib-only Python — no `.venv`, no dependencies to install.

## Prerequisites

Credentials come from the environment (already set in this workspace):

- `DATA_FOR_SEO_LOGIN`
- `DATA_FOR_SEO_PASSWORD`

These are the API credentials from https://app.dataforseo.com/api-access
(auth is HTTP Basic). If they're unset, the script falls back to a `.env` in
the working directory, then exits with a clear message. Never hardcode them.

## Cost model — read before running

Each `search-volume` / `for-keywords` / `for-site` / `ad-traffic` call is
**one billable request** (~$0.05–0.10 each), *regardless of how many keywords
you send or rows you get back*. The account balance is small and shared —
treat every call as real money and squeeze the most out of each one:

- **Pick the cheapest endpoint for the question** (decision guide below).
- **Fill the batch.** One request bills the same for 1 keyword or the max, so
  send the max: up to **1000** keywords to `search-volume` / `ad-traffic`, up
  to **20** seeds to `for-keywords`. One 1000-keyword call instead of a
  thousand 1-keyword calls is the single biggest cost lever here.
- **Preview with `--dry-run`** before paying. It prints the exact request and
  tells you whether it's `billable` or already cached (free) — no call made.
  Use it to sanity-check a big pull before committing.
- **Caching is automatic.** Every response is cached on disk keyed by the full
  request. Re-running an identical query is free and flagged `from_cache`.
  Pass `--no-cache` only when you deliberately want fresh numbers.
- **Keep everything you paid for.** A call returns more than the summary
  columns (12-month trend, spelling, keyword annotations/concepts). Use
  `--raw PATH` to save the complete result and `--monthly` to fold the trend
  into CSV so a repeat pull is never needed.
- **Rate limit: 12 requests/minute** per account on Live endpoints.

`locations` and `languages` lookups are free. If a call returns `40200
Payment Required` or `40201` (account paused), the balance has run out or
been flagged — that's an account issue to fix at
https://app.dataforseo.com, not a skill bug; don't retry in a loop.

### Which endpoint? (opinionated — highest-signal and cheapest first)

- **You already have the keywords** → `search-volume`. Exact metrics for up
  to 1000 in one call. Don't reach for `for-keywords` to look up terms you
  already know.
- **You need to *discover* keywords → prefer `for-site` on a real domain or
  page.** Point it at a competitor, your own site, or a relevant landing
  page (`--target-type page` scopes to one URL). What a live page is actually
  about is higher-signal — and usually cheaper overall — than seed terms you
  invent. This is the default discovery move.
- **Only when you have no relevant URL** (or you deliberately want to expand a
  theme) → `for-keywords`, seeded with a few *broad* head terms. Use it with
  judgement: niche seeds return almost nothing, broad seeds balloon into
  thousands of noisy billable rows. Sort by volume and bank with `--csv`.
- **You want a click/spend forecast** for a bid → `ad-traffic`.

Two gotchas worth internalizing:

- **`search-volume` combines similar keywords.** Google returns a *combined*
  volume for near-duplicate terms; to tell them apart, submit them in
  separate requests — more precise, more calls, only when it matters.
- **Location dominates the numbers.** Defaults are US/en; the wrong geo
  returns confidently wrong data (`coffee shop` is ~2.7M/mo in the US but
  ~1.3k in Oslo). Set `--location-name` / `--location-code` — or
  `--worldwide` — on purpose, and look codes up with the `locations` op.

## Operations

Run from the repo root. Each prints to stdout; `--csv PATH` also writes the
full result set to a file. Add `--dry-run` to any keyword op to preview the
request for free.

### Metrics for a known list of keywords (cheapest)

**Max: 1000 keywords per call → 1000 rows back (one per keyword).** Optimal
use: pool everything you want priced into one call — it bills the same as one
keyword — and add `--monthly` to bank the trend.

```bash
python3 .claude/skills/dataforseo-keywords/scripts/keywords.py search-volume \
    "ai sales coach" "sales coaching app" "cold call practice" \
    --sort-by search_volume --monthly --csv research/data/keywords/james-terms.csv
```

Exact `search_volume`, `competition`, `competition_index`, `cpc`, and
`low`/`high_top_of_page_bid` for each keyword you pass — **up to 1000 in a
single billable call**. Use this whenever you already know the terms and just
want their numbers. `--monthly` adds the 12-month trend; `--raw PATH` saves
the complete response. (`spell` shows Google's correction when a term is
misspelled; the column is hidden when everything is spelled fine.)

### Keyword ideas from seed terms

**Max: 20 seeds per call → up to 20,000 ideas back.** Optimal use: give it a
few *broad* head terms and let Google expand them, then sort by volume.

```bash
python3 .claude/skills/dataforseo-keywords/scripts/keywords.py for-keywords \
    "sales coaching" "sales training software" "cold calling" \
    --sort-by search_volume --format table --csv research/data/keywords/ideas.csv
```

Returns the seeds plus related keyword ideas, each with `search_volume`,
`competition` (LOW/MEDIUM/HIGH), `competition_index` (0–100), `cpc`, and
`low_top_of_page_bid` / `high_top_of_page_bid`.

How many ideas you get depends on the seed's breadth, not on any limit you
set: `crm software` returns ~1,600 ideas, `laptop` ~2,500, while a narrow
long-tail phrase like `ai sales coach` may return **only itself** — that's
Google, not a bug. Two implications: (1) seed with head terms when you want
discovery; (2) a big pull can exceed the default `--limit 100` stdout cap, so
add `--csv` to bank the full set (the summary reports `total_returned`).

### Keywords a domain or page is relevant to

**Max: 1 target per call → up to ~2,000+ rows back.** Optimal use: always add
`--csv` (footprints are large) and `--sort-by search_volume` to surface the
head terms first.

```bash
python3 .claude/skills/dataforseo-keywords/scripts/keywords.py for-site \
    "competitor.com" --sort-by search_volume --csv research/data/keywords/competitor.csv
```

`--target-type site` (default) covers the whole domain; `--target-type page`
scopes to a single URL. Same metric columns as `for-keywords`. A domain can
return 1000+ rows — stdout is capped by `--limit` (default 100) while
`--csv` always gets everything, so nothing is lost.

### Forecast clicks, CPC, and spend for an ad campaign

**Max: 1000 keywords per call → 1 campaign-level aggregate row back.** Optimal
use: forecast one keyword at a time when you need per-keyword numbers, and use
a high `--bid` to see the traffic ceiling.

```bash
python3 .claude/skills/dataforseo-keywords/scripts/keywords.py ad-traffic \
    "ai sales coach" "best ai sales coach" "sales coaching app" \
    --bid 999 --match exact --date-interval next_month --format table
```

- `--bid` (required, integer USD) — the max bid you'd set. Higher bid →
  higher projected metrics. Use a **high bid (e.g. 999)** to level out
  account-specific factors and see the keyword's headroom.
- `--match` (required) — `exact`, `broad`, or `phrase`.
- Forecast window: `--date-interval next_week|next_month|next_quarter`
  (default `next_month`), or exact future dates with `--date-from` /
  `--date-to`.

**Important — this endpoint returns a campaign-level aggregate.** Since the
June 2024 Google Ads API change, `ad-traffic` returns **one row for the
whole keyword set** (total projected `clicks`, `average_cpc`, and `cost`),
not per-keyword rows. To forecast a single keyword, send just that one
keyword. `average_cpc` here is a truer demand signal than the broad-match
`search_volume` from the other two operations.

### Find a location or language code

```bash
python3 .claude/skills/dataforseo-keywords/scripts/keywords.py locations --contains "United Kingdom"
python3 .claude/skills/dataforseo-keywords/scripts/keywords.py languages --contains "Spanish"
```

## Location and language

All keyword operations default to **`location_code 2840` (United States)**
and **`language_code en`** — the James ICP is US-first. Override per call:

- `--location-code 2826` or `--location-name "London,England,United Kingdom"`
- `--language-code de` or `--language-name German`
- `--worldwide` — omit location entirely for global aggregate results

Use `location_name` over `location_code` when you don't know the code; the
script sends whichever you provide. Look codes up with the `locations` /
`languages` operations.

## Output formats

- `--format json` (default) — a `{meta, keywords}` object. `meta` carries
  `cost`, `from_cache`, location/language, and `total_returned` vs `shown`
  so truncation is always explicit. Best when you'll reason over the numbers.
- `--format table` — a markdown table plus a one-line summary. Best for a
  quick human-readable look.
- `--format csv` — CSV to stdout.
- `--csv PATH` — write the **full** result set (ignoring `--limit`) to a CSV
  file. Use this to drop keyword data into `research/data/keywords/` for the
  ad round; the JSON summary still prints to stdout.
- `--raw PATH` — dump the **complete** raw API result (annotations, concepts,
  full monthly history — nothing dropped) to a JSON file. Use it to bank
  everything a paid call returned so you never have to pay for it twice.
- `--monthly` — add the 12-month search-volume trend as a column in
  table/CSV output (it's always present in JSON output regardless).
- `--limit N` — cap rows printed to stdout (default 100; `0` = all). Never
  caps the `--csv` / `--raw` files.
- `--dry-run` — print the exact request and whether it's billable or cached,
  without calling. Free.

## Working with the results (James context)

- When sizing demand for a theme, lead with `search_volume` and `cpc`, and
  read `competition` / `competition_index` as how contested the ad auction
  is. High CPC + real volume on transactional terms ("ai sales coach", "best
  ai sales coach") is a *positive* signal — money is already flowing there.
- Distinguish **transactional intent** from awareness terms (per the launch
  positioning): the money keywords are the ones people search when they're
  already looking for a solution.
- Save meaningful pulls as CSVs under `research/data/keywords/` so they sit
  beside the existing Keyword Planner exports. Note in `marketing/memory.md`
  what you pulled and why. Don't overwrite the raw Planner exports — add new
  files.

## Smoke test

```bash
python3 .claude/skills/dataforseo-keywords/scripts/smoke_test.py            # ~4 billable calls
python3 .claude/skills/dataforseo-keywords/scripts/smoke_test.py --dry-run  # free: checks wiring only
```

Live mode hits all four endpoints once (~4 billable calls) and asserts each
authenticates and returns a well-formed task. `--dry-run` verifies auth and
request-building without spending — use it when the balance is low. Run after
any credential or `client.py` change.

## Design notes

- **Why one CLI with subcommands.** The four endpoints share auth,
  location/language params, caching, and output formatting. One
  `keywords.py` keeps that logic in one place; the subcommand picks the
  endpoint and its required fields (`--bid`/`--match` for `ad-traffic`).
- **Why `search-volume` is the default recommendation.** It's the cheapest
  path to real metrics — 1000 known keywords for one request — so the docs
  steer you there first and reserve `for-keywords` for genuine discovery.
- **Why `--dry-run`, `--raw`, `--monthly` exist.** All three serve the same
  goal: spend the fewest requests and extract the most from each. Dry-run
  avoids a wasted call, raw banks everything the call returned, monthly keeps
  the trend you already paid for.
- **Why US/en defaults.** James targets the US market first, so the common
  case shouldn't need flags. Everything is overridable and `--worldwide`
  exists for global pulls.
- **Why cache by full request.** Keyword metrics move monthly, not by the
  minute, so paying twice for the same query in a session is pure waste. The
  cache key includes every param, so changing location, language, sort, or
  dates correctly misses the cache.
- **Why full data to `--csv`, capped preview to stdout.** A `for-site` pull
  can be 1000+ rows — too much to dump into context — but you still want the
  whole thing on disk. The file gets everything; stdout gets a bounded, and
  explicitly-labeled, preview.
- **Why stdlib-only.** No `.venv` means no install step when the repo is
  cloned fresh.

## Files

```
.claude/skills/dataforseo-keywords/
├── SKILL.md            — this file
├── scripts/
│   ├── client.py       — Basic auth, POST/GET helpers, retries, task unwrap
│   ├── keywords.py     — CLI: search-volume / for-keywords / for-site / ad-traffic + lookups
│   └── smoke_test.py   — one call per endpoint (or --dry-run for free)
└── .cache/             — on-disk response cache (git-ignored)
```
