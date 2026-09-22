---
name: dataforseo-appstore
description: Live Apple App Store data — which apps rank for a keyword, full app details (ratings, price, developer, description, screenshots), user reviews, and top-chart rankings — from DataForSEO's Apple App Data API. Use this whenever the user wants App Store / iOS competitive or ASO research: what apps show up for an App Store search, how a competitor app is rated and reviewed, what users actually say in the reviews, which apps top a category chart, or the full metadata for a specific app by name/id/URL. Trigger on "app store", "ASO", "app store keyword/search", "competitor apps", "reviews of <app>", "how is <app> rated", "top free/paid/grossing apps", "app store rankings", "what does <app> look like on the store", "find iOS apps like X", or any request to ground App Store / iOS-app decisions in real store data instead of guesses. This is App Store data (iOS apps) — distinct from the sibling `dataforseo-keywords` skill, which is Google Ads web search volume. Prefer this over web search whenever the user wants real App Store rankings, ratings, reviews, or app metadata. Opinionated defaults (override when the task calls for it): reach for `search` to see who you're up against for a term, `reviews --sort-by most_recent` to mine live voice-of-customer (the single highest-signal move for a competitor), `info` for a one-app teardown, `list` for category charts, and the live `listings` only when you need DB-style filtering — it's the one pricey call (~$0.10 vs fractions of a cent).
---

# dataforseo-appstore

Live Apple **App Store** data from **DataForSEO's Apple App Data API** — the
rankings, ratings, reviews, and metadata Apple shows, but scriptable. Five
operations plus detached-retrieval and reference helpers, one CLI
(`scripts/appstore.py`):

| Operation | What you get | Billing (Standard) | Kind |
|---|---|---|---|
| `search` | Apps ranking for a keyword (ASO / competitive intel) | per 100 items (~$0.0012) | task |
| `info` | Full details for one app: rating, price, developer, description, screenshots, similar apps | per app (~$0.0006) | task |
| `reviews` | User reviews for one app: rating, title, text, reviewer, version, date | per 25 reviews (~$0.00075) | task |
| `list` | Top-chart apps by collection (top free/paid/grossing/new) + category | per 100 items (~$0.0012) | task |
| `listings` | Search DataForSEO's App Store **database** by title/description/category/numeric filters | **~$0.10 flat** | live |

This is how James sizes the App Store competitive field **from real store
data** rather than guesswork (see `marketing/CLAUDE.md`): who ranks for "sales
coach", how those apps are rated, and — most valuable — what their users
complain about in the reviews. Save meaningful pulls next to the keyword
exports under `research/data/` and note them in `marketing/memory.md`.

Stdlib-only Python — no `.venv`, no dependencies to install.

## Prerequisites

Credentials come from the environment (already set in this workspace):

- `DATA_FOR_SEO_LOGIN`
- `DATA_FOR_SEO_PASSWORD`

The same API credentials as `dataforseo-keywords`, from
https://app.dataforseo.com/api-access (auth is HTTP Basic). If unset, the
script falls back to a `.env` in the working directory, then exits with a clear
message. Never hardcode them.

## Task-based vs. live — the one thing to internalize

The App Data API has **two request shapes**, and this skill hides the
difference behind subcommands so you rarely think about it:

- **Task-based** (`search`, `info`, `reviews`, `list`): you POST a task, it
  goes in a queue, and results come back a little later. The CLI POSTs, then
  **polls until the result is ready and prints it** — so it *feels* synchronous
  (usually ~15–40s on the Standard queue). You'll see `· task … posted,
  polling…` on stderr while it waits.
- **Live** (`listings`): POST and the result comes straight back, like the
  Keywords API.

When the Standard queue is slow, don't sit and wait — **`--async`** POSTs the
task and prints its id immediately; retrieve it later with **`get <id>`**
(the CLI remembers which endpoint each id belongs to). `ready` lists tasks that
have finished and are waiting to be collected. Tasks stay retrievable for ~3
days.

## Cost model — read before running

Each posted task (and each `listings` call) is **one billable request**. The
account balance is small and shared — treat every call as real money:

- **Task ops bill by volume returned, in fixed blocks:** `search`/`list` per
  **100 items**, `reviews` per **25 reviews**. So `reviews --depth 100` bills
  4 blocks; `search --depth 300` bills 3. `info` is a flat per-app charge.
  (`search`/`list` always return *at least* 100 — a depth below 100 costs the
  same one block, you just get the full first page.)
- **`listings` is the expensive one — ~$0.10 per call, flat**, whatever the
  limit. Use it only when you actually need database-style filtering
  (min-rating, category, sort); for "who ranks for X" use `search` (100× cheaper).
- **`--priority high` doubles the cost** but returns in ~1 min instead of up to
  ~45 (usually far less). Default is Standard (cheap).
- **Preview with `--dry-run`** before paying — it prints the exact request, a
  billing estimate, and whether the answer is already cached (free). No call made.
- **Caching is automatic.** Every completed result is cached on disk keyed by
  the request. Re-running an identical query is free and flagged `cached (free)`.
  Priority doesn't fragment the cache (same data either way). Pass `--no-cache`
  to force fresh.
- **Keep everything you paid for** with `--raw PATH` (complete API result:
  screenshots, similar apps, full review bodies) and `--csv PATH` (full row set).
- **Rate limits are generous** (2000 calls/min); polling `task_get` is free.

If a call returns `40200 Payment Required` / `40210 Insufficient Funds`, the
balance has run out — that's an account issue to fix at
https://app.dataforseo.com, not a skill bug; don't retry in a loop.

## Operations

Run from the repo root. Each prints to stdout; `--csv PATH` also writes the full
result set. Add `--dry-run` to any billable op to preview it for free.

### Who ranks for a keyword (competitive / ASO)

```bash
python3 .claude/skills/dataforseo-appstore/scripts/appstore.py search "sales coach" \
    --depth 100 --format table
```

Returns the ranked App Store search results — `rank_absolute`, `app_id`,
`title`, `rating`, `reviews_count`, `price`, `url`. This is the first move for
"who are we up against for <term>". `--depth` 1–700 (default 100; bills per
100). Feed an `app_id` from here straight into `info` or `reviews`.

### Full details for one app

```bash
python3 .claude/skills/dataforseo-appstore/scripts/appstore.py info 6742204639 --format table
# or pass an App Store URL — the id is parsed out of it:
python3 .claude/skills/dataforseo-appstore/scripts/appstore.py info \
    "https://apps.apple.com/us/app/closercoach-ai-sales-trainer/id6742204639"
```

One rich record: developer, category, rating + review count, price, size,
version, minimum iOS, last-update date, description, similar apps, and
screenshots. Table mode prints a readable key/value block; `--format json` and
`--raw PATH` keep everything. Cheapest op (per-app).

### What users actually say (voice-of-customer — highest signal)

```bash
python3 .claude/skills/dataforseo-appstore/scripts/appstore.py reviews 6742204639 \
    --depth 100 --sort-by most_recent --format table --csv research/data/appstore/closercoach-reviews.csv
```

Real reviews: `rating`, `title`, `review_text`, `profile_name`, app `version`,
`timestamp`. `--sort-by most_recent` (freshest complaints/praise) or
`most_helpful` (default; the reviews Apple surfaces). `--depth` 25–500 (default
100; bills per 25). This is the richest competitive input in the whole
skill — a competitor's 1-star reviews are a map of the gaps James can exploit.
(Apple obfuscates reviewer names, so `profile_name` is often a hashed token.)

### Top-chart apps by collection + category

```bash
python3 .claude/skills/dataforseo-appstore/scripts/appstore.py list \
    --collection top_free_ios --category business --depth 100 --format table
```

`--collection` (required): `top_free_ios`, `top_paid_ios`, `top_grossing_ios`,
`new_ios`, `new_free_ios`, `new_paid_ios`. `--category` optional (see the
`categories` lookup — e.g. `business`, `health_and_fitness`, `productivity`,
`education`). `--depth` up to 1000 (bills per 100).

### Database search with filters (live, US-only, ~$0.10)

```bash
python3 .claude/skills/dataforseo-appstore/scripts/appstore.py listings \
    --description "sales coaching" --min-rating 4 --min-reviews 20 \
    --order-by "rating.value,desc" --category business --limit 50 \
    --csv research/data/appstore/coaching-listings.csv
```

Searches DataForSEO's stored App Store catalog (not a live Apple query), so you
can filter by numeric fields. `--title` / `--description` (keyword match),
`--category` (repeatable, up to 10), `--min-rating`, `--min-reviews`,
`--order-by "field,dir"` (repeatable, up to 3), `--limit` (max 1000),
`--offset`. For arbitrary conditions use `--filters-json` with a raw DataForSEO
filters array.

> **Field names need an `item.` prefix.** Listings nest each app under an
> `item` object, so sortable/filterable fields are `item.rating.value`,
> `item.rating.votes_count`, `item.price.current`, etc. The `--min-rating` /
> `--min-reviews` / `--order-by` flags add the prefix for you; if you write a
> raw `--filters-json`, use the `item.`-prefixed paths yourself, e.g.
> `--filters-json '[["item.rating.value",">",4.5],"and",["item.price.current","=",0]]'`.

### Detached retrieval (when the Standard queue lags)

```bash
# POST without waiting — prints a task id:
python3 .claude/skills/dataforseo-appstore/scripts/appstore.py search "cold call practice" --async
# ...later, fetch it (endpoint auto-detected from the local ledger):
python3 .claude/skills/dataforseo-appstore/scripts/appstore.py get 07140958-2075-0428-0000-a03b23f62350 --format table
# see what's finished and uncollected:
python3 .claude/skills/dataforseo-appstore/scripts/appstore.py ready
```

`get` polls until the task is ready (or `--max-wait 0` for a single ready/not
check). Pass `--type search|info|reviews|list` if the id isn't in the local
ledger (e.g. posted elsewhere).

### Find a category, location, or language code (free)

```bash
python3 .claude/skills/dataforseo-appstore/scripts/appstore.py categories --contains health
python3 .claude/skills/dataforseo-appstore/scripts/appstore.py locations  --contains "United Kingdom"
python3 .claude/skills/dataforseo-appstore/scripts/appstore.py languages  --contains English
```

## Location and language

All task ops default to **`location_code 2840` (United States)** and
**`language_code en`** — the James ICP is US-first. Override per call with
`--location-code` / `--location-name` and `--language-code` /
`--language-name`; look codes up with the `locations` / `languages` ops. Note
`listings` is **US-only** by design (no locale flags).

## Output formats

- `--format json` (default) — a `{meta, items}` object (`{meta, app}` for
  `info`). `meta` carries `cost`, `from_cache`, result counts, and whether
  stdout was truncated. Best when you'll reason over the data.
- `--format table` — a markdown table (or key/value block for `info`) plus a
  one-line summary. Long cells (review text, descriptions) are truncated for
  readability; the full text is always in `--csv` / `--raw` / json.
- `--format csv` — CSV to stdout.
- `--csv PATH` — write the **full** result set (ignoring `--limit`) to a file.
  Use this to bank pulls under `research/data/appstore/`.
- `--raw PATH` — dump the **complete** raw API result (screenshots, similar
  apps, full review bodies — nothing dropped) so a paid call is never repeated.
- `--limit N` — cap rows printed to stdout (default 100; `0` = all). Never caps
  the `--csv` / `--raw` files. (On `listings`, `--limit` is the API page size.)

## Working with the results (James context)

- **Competitive field:** `search "sales coach"` / `"ai sales coach"` /
  `"cold call practice"` shows exactly who ranks and how they're rated. High
  ratings + high review counts = an entrenched competitor; low counts = a
  crowded long tail James can rise through.
- **Voice-of-customer is the goldmine:** `reviews --sort-by most_recent` on a
  live competitor surfaces the specific complaints (billing/trial anger,
  missing features, bugs) that become James's positioning wedges. Save these.
- **One-app teardown:** `info` for a competitor's price, update cadence
  (`last_update_date` shows how actively it's maintained), and `similar_apps`
  (Apple's own "you might also like" graph — free adjacency intel).
- **Where to save:** drop meaningful CSVs under `research/data/appstore/`
  (create it) so they sit beside the keyword exports, and note in
  `marketing/memory.md` what you pulled and why. Don't overwrite raw data — add.

## Smoke test

```bash
python3 .claude/skills/dataforseo-appstore/scripts/smoke_test.py            # ~5 billable calls + polling
python3 .claude/skills/dataforseo-appstore/scripts/smoke_test.py --dry-run  # free: checks wiring only
```

Live mode posts + polls all four task endpoints, hits `listings` (live), and
reads a free reference lookup, asserting each returns well-formed data.
`--dry-run` verifies auth and request-building without spending. Run after any
credential or `client.py` change.

## Design notes

- **Why one CLI with subcommands.** All ops share auth, location/language,
  caching, polling, and output formatting; the subcommand just picks the
  endpoint and its required fields (`--collection` for `list`, `--sort-by` for
  `reviews`). One place to fix a bug, one mental model.
- **Why polling is hidden behind a synchronous feel.** The task queue is the
  API's model, not the user's question. The CLI POSTs → polls → prints so the
  common case is one command; `--async`/`get`/`ready` exist for when the queue
  is genuinely slow and you'd rather not block.
- **Why cache by request, ignoring priority/tag.** App Store rankings and
  ratings move by the day, not the second, so paying twice for the same query
  in a session is waste. Priority and tag don't change the *data*, so they're
  excluded from the cache key — a Standard and a high-priority pull of the same
  query share one cached answer.
- **Why `listings` is walled off as the pricey one.** At ~$0.10 it's ~100× a
  `search` call, so the docs steer you to `search` for ranking questions and
  reserve `listings` for the rare case that needs numeric DB filtering.
- **Why flatten nested objects.** `rating` and `price` come back as objects,
  and `listings` nests the whole app under `item`; the CLI flattens them to
  scalar columns and drops all-empty columns (e.g. `developer`, which
  `search`/`list` don't return) so tables stay readable. `--raw` keeps the
  nested originals.
- **Why stdlib-only.** No `.venv` means no install step when the repo is cloned
  fresh — same as `dataforseo-keywords`.

## Files

```
.claude/skills/dataforseo-appstore/
├── SKILL.md            — this file
├── scripts/
│   ├── client.py       — Basic auth, POST/GET, retries, status-code-aware task polling
│   ├── appstore.py     — CLI: search / info / reviews / list / listings / get / ready + lookups
│   └── smoke_test.py   — one call per endpoint (or --dry-run for free)
└── .cache/             — on-disk response cache + async task ledger (git-ignored)
```
