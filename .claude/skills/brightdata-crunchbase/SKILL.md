---
name: brightdata-crunchbase
description: Look up and discover companies on Crunchbase via Bright Data's pay-as-you-go Web Scraper API — pull a company's profile, founding date, HQ, headcount, industries, funding rounds, investors, acquisitions, patents, and key people; or discover companies by free-text keyword. Trigger whenever the user says "look up <company> on Crunchbase", "research <startup>", "who invested in <company>", "when was <company> founded", "how much funding has <company> raised", "find AI startups on Crunchbase", "discover fintech companies", "get Crunchbase data for …", or otherwise asks for Crunchbase-sourced company, funding, investor, founder, or startup data. Use this instead of web search whenever the user wants structured Crunchbase data — even if they don't explicitly say "Bright Data".
---

# brightdata-crunchbase

Thin wrapper around Bright Data's **Crunchbase Web Scraper API** (pay‑as‑you‑go,
no minimum spend). Scripts hide the trigger → poll → download loop so callers
stay task‑oriented.

## Prerequisites

`BRIGHTDATA_API_TOKEN` must be set on a Bright Data account with the
**Crunchbase Web Scraper API** enabled. Scripts exit with a clear error if the
token is missing.

## Billing model — read this before running anything

This skill calls Bright Data's Crunchbase Web Scraper API. Each **returned**
record is billed per‑record on your Bright Data plan (pay‑as‑you‑go, **no
minimum**, ~$0.001–$0.0015 per record).

- **Lookups** (`lookup_companies.py`) bill for one record per input URL. Cheap
  and predictable — always prefer this when the user knows the company.
- **Discoveries** (`discover_companies.py`) bill for every row returned. A
  broad keyword can return thousands of rows fast, so `--limit-per-input` is
  required. Before running a discovery, tell the user the expected max
  record count (= `len(keywords) * limit_per_input`) so they can ballpark
  the spend.
- **Snapshot retention is 16 days.** Re‑downloading via `get_snapshot.py` is
  free. Don't re‑trigger for the same data inside that window.
- `describe_fields.py`, `list_snapshots.py`, and `--status-only` on
  `get_snapshot.py` are free (metadata‑only, no scraping).

## Tasks

Run from this skill directory; each prints one JSON object to stdout.

- **Look up known companies** — `python scripts/lookup_companies.py --url https://www.crunchbase.com/organization/<slug> [--url ...] [--fields name,url,founded_date,num_employees] [--no-wait]`
  Start here. One billable record per URL.

- **Discover companies by keyword** — `python scripts/discover_companies.py --keyword "<kw>" [--keyword ...] --limit-per-input 25 [--fields ...] [--no-wait]`
  `--limit-per-input` is required. Start small (25) and expand only if needed.

- **Re‑download an existing snapshot** — `python scripts/get_snapshot.py --snapshot-id s_xxx [--status-only]`
  Free within the 16‑day retention window. Use this instead of re‑triggering.

- **List recent snapshots** — `python scripts/list_snapshots.py [--status ready] [--limit 20]`
  Free. Handy if the user lost a snapshot id.

- **Describe the field schema** — `python scripts/describe_fields.py [--names-only] [--active-only]`
  Free. Authoritative source for what columns the scraper can return.

## Guidance

- **Resolve the slug first.** The lookup path expects
  `https://www.crunchbase.com/organization/<slug>`. If the user gives a
  display name ("that sneaker startup"), either resolve the slug via web
  search or ask them for the URL. Don't guess — a wrong slug wastes a
  billable record.
- **Cap discoveries.** If the user says "find me AI startups" without a
  number, default to `--limit-per-input 25` and tell them you capped it so
  they don't get surprised on their next Bright Data invoice. Increase only
  on explicit request.
- **Default to the full record.** `lookup_companies.py` and
  `discover_companies.py` already return every available field when
  `--fields` is omitted — leave it omitted. Trimming saves nothing on
  the bill (billing is per-record, not per-field) and routinely strips
  out signals the caller didn't know they wanted (funding rounds,
  acquisitions, key people, patents). Only pass `--fields` when the
  user explicitly asks for a trimmed payload or context-window pressure
  forces it (e.g. `--fields name,url,founded_date,num_employees`).
- **For long jobs, use `--no-wait`.** Record the `snapshot_id` in your
  response so the user can fetch later via `get_snapshot.py`. Large
  discoveries can take 10+ minutes.
- **Nested fields, not separate endpoints.** Investors, funding rounds,
  acquisitions, key people, and patents all come back as nested structures
  on the company record. There are no separate endpoints for them.
- **Prefer cached data.** Before triggering, ask whether the user already
  has a snapshot_id from a recent run — `get_snapshot.py` is free within
  16 days of the original trigger.
- **Don't dump raw JSON.** See the output contract below.

## Output contract

For a single company, summarise the profile in 4–8 bullets:
- Name (+ legal name if different)
- Description (one sentence)
- HQ city, country
- Founded date
- Industries (top 3)
- Headcount range
- Total funding raised + last round type/date
- Key people (CEO, founders) if present
- Website

For a discovery result, summarise the top 5–10 hits in a compact table or
bulleted list (name, URL, HQ, industries, headcount), then offer to drill
into any specific company with `lookup_companies.py`.

Always include the `snapshot_id` at the end so the user can re‑fetch for free.
**Never dump the full JSON unless the user explicitly asks for "raw data".**

## References

- `references/curls.md` — verified curl examples for every endpoint
- `references/fields.md` — grouped field list (convenience; not authoritative)
- `references/LIMITS.md` — billing, retention, auth, and failure modes

## Smoke test

```bash
python scripts/smoke_test.py
```

Free, metadata‑only. Asserts the dataset metadata call works and that `name`
and `url` are in the field schema. Prints `SKIP: BRIGHTDATA_API_TOKEN not set`
if the token is missing, so unauthenticated CI doesn't fail.
