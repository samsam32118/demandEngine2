---
name: brightdata-pitchbook
description: Look up companies on PitchBook via Bright Data's pay-as-you-go Web Scraper API — pull a company's profile, founding date, HQ, headcount, industries, funding rounds, investors, valuation, and key people. Trigger whenever the user says "look up <company> on PitchBook", "get PitchBook data for <startup>", "who invested in <company>", "what's <company>'s valuation", "find PitchBook profile for <company>", "how much funding has <company> raised", "research <startup> on PitchBook", or otherwise asks for PitchBook-sourced company, funding, investor, or startup data. When the user only gives a company name (not a URL), this skill automatically searches the web to resolve the PitchBook URL first, then scrapes the profile. Use this instead of web search whenever the user wants structured PitchBook data — even if they don't explicitly say "Bright Data".
---

# brightdata-pitchbook

Thin wrapper around Bright Data's **PitchBook Web Scraper API** (pay-as-you-go,
no minimum spend). Scripts handle the web-search URL-resolution step and the
Bright Data scrape call so callers stay task-oriented.

## Prerequisites

`BRIGHTDATA_API_TOKEN` must be set on a Bright Data account with the
**PitchBook Web Scraper API** (`gd_m4ijiqfp2n9oe3oluj`) enabled. Scripts exit
with a clear error if the token is missing.

## Two-step workflow

PitchBook profiles live at structured URLs like:

```
https://pitchbook.com/profiles/company/467033-41
```

If the user gives only a company name, resolve the URL first using the
**brightdata-serp** skill before calling the scraper:

```
python3 .claude/skills/brightdata-serp/scripts/search.py "<company name> pitchbook" --format parsed
```

Look for a result on `pitchbook.com/profiles/company/…` and extract the URL.
Then pass it to `lookup_company.py`.

## Billing model — read this before running anything

This skill calls Bright Data's PitchBook Web Scraper API. Each **returned**
record is billed per-record on the pay-as-you-go plan (~$0.001–$0.0015 per
record, **no minimum spend**).

- **Lookups** (`lookup_company.py`) bill for one record per input URL.
  Cheap and predictable — always prefer this path.
- Re-downloading via `get_snapshot.py` is **free** within the 16-day
  retention window. Don't re-trigger for the same data inside that window.
- `list_snapshots.py` and `--status-only` on `get_snapshot.py` are free
  (metadata-only, no scraping).

## Tasks

Run from the `scripts/` directory; each prints one JSON object to stdout.

- **Look up a company by PitchBook URL** — `python scripts/lookup_company.py --url https://pitchbook.com/profiles/company/<id> [--url ...]`
  Uses the synchronous `/scrape` endpoint; returns data directly (no polling).
  One billable record per URL.

- **Re-download an existing snapshot** — `python scripts/get_snapshot.py --snapshot-id s_xxx [--status-only]`
  Free within the 16-day retention window. Use this instead of re-triggering.

- **List recent snapshots** — `python scripts/list_snapshots.py [--status ready] [--limit 20]`
  Free. Handy if the user lost a snapshot id.

## Guidance

- **Resolve the PitchBook URL first.** If the user gives a display name
  ("that sneaker startup"), run `search.py "<company name> pitchbook"
  --format parsed` (brightdata-serp) and find the
  `pitchbook.com/profiles/company/<id>` URL in the results. Don't guess —
  a wrong URL wastes a billable record. One paid SERP call is cheap next to
  wasting a PitchBook scrape on a wrong URL.
- **The scrape endpoint is synchronous.** `lookup_company.py` uses
  `/datasets/v3/scrape?notify=false` which blocks until the data is ready.
  No polling loop needed for normal lookups (typically completes in
  15–60 seconds).
- **Prefer cached data.** Before triggering, ask whether the user already
  has a snapshot_id from a recent run — `get_snapshot.py` is free within
  16 days of the original trigger.
- **Don't dump raw JSON.** See the output contract below.

## Output contract

For a single company, summarise the profile in 4–8 bullets:
- Company name (+ legal name if different)
- Description (one sentence)
- HQ city, country
- Founded date
- Industries / verticals (top 3)
- Headcount range
- Total funding raised + last round type/date/amount
- Valuation (if available)
- Key people (CEO, founders) if present
- Website / PitchBook URL

Always include the `snapshot_id` (if one was returned) at the end so the
user can re-fetch for free. **Never dump the full JSON unless the user
explicitly asks for "raw data".**

## References

- `references/curls.md` — verified curl examples for every endpoint
- `references/LIMITS.md` — billing, retention, auth, and failure modes

## Smoke test

No live smoke test (avoids accidental billing). Verify setup by running:

```bash
python -c "import os; tok=os.environ.get('BRIGHTDATA_API_TOKEN'); print('token set' if tok else 'ERROR: BRIGHTDATA_API_TOKEN not set')"
```
