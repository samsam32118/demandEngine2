---
name: brightdata-zoominfo
description: Look up and discover companies on ZoomInfo via Bright Data's pay-as-you-go Web Scraper API — pull a company's profile, revenue, headcount, headquarters, industry, leadership, top contacts, org chart, tech stack, funding rounds, and similar companies; or discover companies by ZoomInfo search-result URL (location + industry + size filters). Trigger whenever the user says "look up <company> on ZoomInfo", "get ZoomInfo data for <company>", "who runs <company>", "find <company>'s revenue and headcount", "pull the ZoomInfo profile of <company>", "find ZoomInfo contacts at <company>", "what's <company>'s tech stack", "discover ZoomInfo companies in <industry/location>", or otherwise asks for ZoomInfo-sourced firmographic, leadership, or contact data. When the user only gives a company name (not a URL), this skill expects the caller to resolve the ZoomInfo URL first via the brightdata-serp skill. Use this instead of web search whenever the user wants structured ZoomInfo data — even if they don't explicitly say "Bright Data".
---

# brightdata-zoominfo

Thin wrapper around Bright Data's **ZoomInfo Web Scraper API** (pay-as-you-go,
no minimum spend). Scripts handle the web-search URL-resolution step and the
Bright Data scrape call so callers stay task-oriented.

## Prerequisites

`BRIGHTDATA_API_TOKEN` must be set on a Bright Data account with the **ZoomInfo
Web Scraper API** (`gd_m0ci4a4ivx3j5l6nx`) enabled. Scripts exit with a clear
error if the token is missing.

## Two URL paths — lookup vs. discover

ZoomInfo profiles live at structured URLs:

```
https://www.zoominfo.com/c/<company-name>/<id>          # company profile (lookup)
https://www.zoominfo.com/companies-search/<filters>     # search results (discover)
```

**Person URLs (`/p/<name>/<id>`) are NOT supported.** The Bright Data
ZoomInfo dataset is company-only: it accepts `/p/` URLs at validation
but silently scrapes them to all-null records — and still bills one
chargeable record. `lookup_company.py` refuses `/p/` URLs with exit 2
to prevent the waste. For person data, scrape the company instead and
read the nested `leadership` array, then pivot to `brightdata-linkedin
lookup_people` if you need the full profile.

**Lookup** (one billable record per URL): use when the user already knows the
company. If the user gives only a company name, resolve the URL first using the
**brightdata-serp** skill before calling the scraper:

```
python3 .claude/skills/brightdata-serp/scripts/search.py "<company name> zoominfo" --format parsed
```

Look for a result on `zoominfo.com/c/<name>/<id>` and extract the URL.
Then pass it to `lookup_company.py`.

**Discover** (billed per returned row, capped by `--limit-per-input`): use when
the user wants to find companies matching filters. Build a ZoomInfo search URL
of the form `https://www.zoominfo.com/companies-search/<filters>` (e.g.
`location-usa-industry-software`) and pass it to `discover_companies.py`.
Bright Data's discovery collector for this dataset only accepts `search_url`
inputs — there is no free-text keyword discovery.

## Billing model — read this before running anything

This skill calls Bright Data's ZoomInfo Web Scraper API. Each **returned**
record is billed per-record on the pay-as-you-go plan (~$0.001–$0.0015 per
record, **no minimum spend**).

- **Lookups** (`lookup_company.py`) bill for one record per input URL.
  Cheap and predictable — always prefer this when the user knows the company.
- **Discoveries** (`discover_companies.py`) bill for every row returned. A
  broad search URL can return hundreds of rows, so `--limit-per-input` is
  required. Tell the user the expected max (= `len(urls) * limit_per_input`)
  before running.
- Re-downloading via `get_snapshot.py` is **free** within the 16-day
  retention window. Don't re-trigger for the same data inside that window.
- `list_snapshots.py`, `describe_fields.py`, and `--status-only` on
  `get_snapshot.py` are free (metadata-only, no scraping).

## Tasks

Run from this skill directory; each prints one JSON object to stdout.

- **Look up a company by ZoomInfo URL** — `python scripts/lookup_company.py --url https://www.zoominfo.com/c/<name>/<id> [--url ...] [--fields name,revenue,headquarters,total_employees]`
  Uses the synchronous `/scrape` endpoint; returns data directly (no polling).
  One billable record per URL.

- **Discover companies by ZoomInfo search URL** — `python scripts/discover_companies.py --search-url "https://www.zoominfo.com/companies-search/<filters>" [--search-url ...] --limit-per-input 25 [--fields ...] [--no-wait]`
  Uses the async `/trigger` path with `discover_by=search_url`. `--limit-per-input`
  is required — start small (25). One billable record per returned row.

- **Re-download an existing snapshot** — `python scripts/get_snapshot.py --snapshot-id s_xxx [--status-only]`
  Free within the 16-day retention window. Use this instead of re-triggering.

- **List recent snapshots** — `python scripts/list_snapshots.py [--status ready] [--limit 20]`
  Free. Handy if the user lost a snapshot id.

- **Describe the field schema** — `python scripts/describe_fields.py [--names-only] [--active-only]`
  Free. Authoritative source for what columns the scraper can return (39 fields
  including `top_contacts`, `c_level_employees`, `org_chart`, `tech_stack`,
  `email_formats`, `funding_rounds`, `similar_companies`, `news_and_media`).

## Guidance

- **Resolve the ZoomInfo URL first.** If the user gives a display name
  ("that legal-tech vendor"), run `search.py "<company name> zoominfo"
  --format parsed` (brightdata-serp) and find the
  `zoominfo.com/c/<name>/<id>` URL in the results. Don't guess — a wrong
  URL wastes a billable record. One paid SERP call is cheap next to
  wasting a ZoomInfo scrape on a wrong URL.
- **Cap discoveries.** If the user says "find me US software companies"
  without a number, default to `--limit-per-input 25` and tell them you
  capped it so they don't get surprised on their next Bright Data invoice.
  Increase only on explicit request.
- **Default to the full record.** `lookup_company.py` already returns
  all 39 fields when `--fields` is omitted — leave it omitted unless the
  user explicitly wants a trimmed payload. Trimming saves nothing on
  the bill (billing is per-record, not per-field) and routinely strips
  out signals the caller didn't know they wanted (`recent_scoops`,
  `news_and_media`, `org_chart`, `tech_stack`). Only pass `--fields`
  when context-window pressure forces it.
- **The lookup endpoint is synchronous.** `lookup_company.py` uses
  `/datasets/v3/scrape?notify=false` which blocks until the data is ready.
  No polling loop needed for normal lookups (typically completes in
  15–60 seconds).
- **For long discoveries, use `--no-wait`.** Record the `snapshot_id` in
  your response so the user can fetch later via `get_snapshot.py`. Large
  discoveries can take 10+ minutes.
- **Prefer cached data.** Before triggering, ask whether the user already
  has a snapshot_id from a recent run — `get_snapshot.py` is free within
  16 days of the original trigger.
- **Show every populated field.** See the output contract below — the
  default is comprehensive presentation, not a 5-bullet summary.

## People and contact data — what you actually get

Verified live against Walmart's profile (2026-04-30). Plan around these
findings, not the field names:

- `leadership` — array of ~3 person entries per company, each with
  `name`, `title`, `avatar`, and a ZoomInfo `/p/` URL. The names are
  real and can be passed to `brightdata-linkedin lookup_people` for full
  profiles. **The 3-entry sample rotates
  between calls to the same `/c/` URL** — verified against Actionstep
  on 2026-04-30 where two lookups ten minutes apart returned disjoint
  trios. Don't treat it as a stable list. For a wider C-suite view use
  `org_chart` (when populated, often 5+ entries) or run two lookups
  and merge.
- `ceo` — structured object but frequently `{name: null, title: null,
  ...}` even on large public companies. Don't rely on it; cross-check
  against the company's own leadership page (the
  leadership-fact primary-source rule from CLAUDE.md still applies).
- `top_contacts`, `c_level_employees`, `vp_level_employees`,
  `director_level_employees`, `manager_level_employees`,
  `non_manager_employees` — **integer counts only**, not contact lists.
  Useful as size signals (e.g. Walmart returns `c_level_employees:
  145`, `vp_level_employees: 1078`) but not as outreach data.
- `email_formats` — frequently `null`, even on Fortune-50 companies.
  Treat as best-effort; the `email-guesser` skill is the better path
  for inferring email patterns.
- `phone_number` — main switchboard. Reliable when present.
- `org_chart` — varies by company. On a 51–200-employee prospect like
  Actionstep it returns 5 C-suite entries with full names + titles +
  ZoomInfo `/p/` URLs (`avatar` is the placeholder
  `https://www.zoominfo.com/undefined`). On Walmart it came back null.
  Treat as a useful bonus when populated, not as a guaranteed source.

**No individual email addresses are returned by this dataset, ever.**
ZoomInfo's per-contact email database is a separate paid product not
exposed via the Bright Data Web Scraper API marketplace as of 2026-04.

## Output contract

**Default: present every populated field, organized by category.** The
record is 39 fields wide; users have repeatedly asked for the comprehensive
view, so don't pre-filter. Skip only fields that came back null or empty
(noting in a closing line which ones were null so the user knows you
didn't omit data silently). Use this skeleton:

- **Identity** — name, id, ZoomInfo URL, description, popular_searches,
  website
- **Firmographics** — headquarters, industry, business_classification_codes
  (note SIC/NAICS codes come back comma-formatted, e.g. `73,737` =
  `7372`), phone_number, employees_text + the `employees`/`total_employees`
  integer (flag the band-string-as-int quirk when it appears, e.g.
  `51200` for `51-200`), social_media
- **Financial** — revenue + revenue_currency + revenue_text, stock_symbol,
  total_funding_amount, most_recent_funding_amount, funding_rounds,
  funding_currency
- **People** — print `ceo` (mark null when it is), the full `leadership`
  table, the full `org_chart` table when populated, then the six
  level-count integers (`top_contacts`, `c_level_employees`,
  `vp_level_employees`, `director_level_employees`,
  `manager_level_employees`, `non_manager_employees`) presented as
  counts, **not** as if they were rosters. Mark `email_formats: null`
  explicitly when null and point at `email-guesser` as the fallback.
- **Tech & products** — tech_stack table (each row: tech_name,
  company_name), products_owned, similar_companies
- **News & signals** — recent_scoops bullets (text + topics + tags),
  news_and_media table (title, url, news_website, date when present)
- **Engagement scores** — ceo_rating, `enps score` (literal field name
  with a space)

For a discovery result, present each row with the same comprehensive
field set, capped at the top 5–10 hits, and offer to drill into a
specific company with `lookup_company.py`.

Always close with the `snapshot_id` (when one was returned) so the user
can re-fetch for free, plus a one-line list of which schema fields came
back null on this record. **Pull the full record by default — leave
`--fields` off unless the user explicitly asks for a trimmed payload.**

## References

- `references/curls.md` — verified curl examples for every endpoint
- `references/fields.md` — grouped list of the 39 dataset fields
- `references/LIMITS.md` — billing, retention, auth, and failure modes

## Smoke test

```bash
python scripts/smoke_test.py
```

Free, metadata-only. Asserts the dataset metadata call works and that
`name`, `url`, and `revenue` are in the field schema. Prints `SKIP:
BRIGHTDATA_API_TOKEN not set` if the token is missing, so unauthenticated
CI doesn't fail.
