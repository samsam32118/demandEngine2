---
name: brightdata-linkedin
description: Look up and discover LinkedIn people, companies, jobs, and posts via Bright Data's pay-as-you-go Web Scraper API — pull a person's full profile (experience, education, skills), a company's profile (HQ, headcount, industries, employees), a job posting, or a post's engagement and metadata; or discover profiles by name, jobs by keyword/location, and posts by author URL. Trigger whenever the user says "look up <person> on LinkedIn", "get LinkedIn data for <company>", "scrape the LinkedIn profile of <name>", "find LinkedIn jobs for <role>", "pull the LinkedIn company page for <company>", or otherwise asks for structured LinkedIn data. This is the sole LinkedIn data provider for Rivas Will — self-contained; the calling agent tracks the shared Bright Data daily cap.
---

# brightdata-linkedin

Thin wrapper around Bright Data's **LinkedIn Web Scraper APIs** (pay-as-you-go,
no minimum spend). Covers four datasets:

| Dataset | Dataset ID | What it returns |
|---|---|---|
| People profile | `gd_l1viktl72bvl7bjuj0` | A person's full profile (about, experience, education, skills, activity, current position) |
| Company info | `gd_l1vikfnt1wgvvqz95w` | A company page (HQ, founded, headcount, industries, recent updates, employee samples) |
| Jobs | `gd_lpfll7v5hcqtkxl6l` | Individual LinkedIn job postings (title, company, salary, seniority, description) |
| Posts | `gd_lyy3tktm25m4avu764` | Posts / articles with author, engagement, reactions, comments |

Scripts hide the trigger → poll → download loop so callers stay task-oriented.

## Prerequisites

`BRIGHTDATA_API_TOKEN` must be set on a Bright Data account with the **LinkedIn
Web Scraper APIs** enabled. Scripts exit with a clear error if the token is
missing.

## The only LinkedIn provider

This is the **sole** LinkedIn data source for Rivas Will. Any time a
beat needs structured LinkedIn data — a person's profile, a company
page, a job posting, a post's engagement — it comes from here.

This skill is **self-contained**: call its scripts directly. It shares the
**BrightData** token with `brightdata-crunchbase` and `brightdata-pitchbook`,
so a LinkedIn lookup and a Crunchbase lookup draw from the same 100/day pool.
The calling agent tracks that shared daily count.

## Billing model — read this before running anything

Bright Data's LinkedIn Web Scraper API bills **per returned record** on the
pay-as-you-go plan (~$0.001–$0.0015 per record, no minimum spend).

- **Lookups** (`lookup_*.py`) bill for one record per input URL. Predictable
  and cheap — always prefer this when the user knows the person/company/
  job/post URL.
- **Discoveries** (`discover_*.py`) bill for every row returned. A broad
  discovery (e.g. jobs by keyword "software engineer" in the US) can return
  thousands of rows fast, so `--limit-per-input` is required.
- **Snapshot retention is 16 days.** Re-downloading via `get_snapshot.py` is
  free. Don't re-trigger for the same data inside that window.
- `describe_fields.py`, `list_snapshots.py`, and `--status-only` on
  `get_snapshot.py` are free (metadata-only, no scraping).

## Tasks

Run from this skill directory; each prints one JSON object to stdout.

### People profiles

- **Look up people by profile URL** — `python scripts/lookup_people.py --url https://www.linkedin.com/in/<handle> [--url ...] [--fields name,headline,experience] [--no-wait]`
  Start here. One billable record per URL.

- **Discover people by name** — `python scripts/discover_people.py --name "First Last" [--name ...] [--no-wait]`
  Discover-new mode. One billable record per returned match (usually 1–5 per
  name). Ambiguous names (`John Smith`) can return noisy results — confirm
  the right profile before pivoting to `lookup_people.py`.

### Companies

- **Look up companies by LinkedIn URL** — `python scripts/lookup_companies.py --url https://www.linkedin.com/company/<slug> [--url ...] [--fields ...] [--no-wait]`
  One billable record per URL. Accepts `linkedin.com/company/<slug>` and the
  `il.linkedin.com` / `organization-guest/company/` variants.

### Jobs

- **Look up a job by posting URL** — `python scripts/lookup_jobs.py --url https://www.linkedin.com/jobs/view/<id> [--url ...] [--no-wait]`
  One billable record per URL. Use when you already have a posting URL.

- **Discover jobs by keyword + location** — `python scripts/discover_jobs.py --keyword "VP Corporate Development" --location "New York" [--country US] [--remote Remote] [--job-type Full-time] [--experience-level "Mid-Senior level"] [--company "Acme"] --limit-per-input 25 [--no-wait]`
  `--limit-per-input` is required. Start small (25) — a broad combo can
  return hundreds of rows.

### Posts

- **Look up posts by URL** — `python scripts/lookup_posts.py --url https://www.linkedin.com/posts/<slug> [--url ...] [--no-wait]`
  One billable record per URL. Handles `/posts/`, `/pulse/`, and
  `/feed/update/` URLs.

- **Discover posts by author** — `python scripts/discover_posts.py --profile-url https://www.linkedin.com/in/<handle> [--profile-url ...] [--no-wait]` **or** `--company-url https://www.linkedin.com/company/<slug>`
  Pulls recent posts by a person or a company page. One billable record per
  returned post — pass `--limit-per-input` to cap it.

### Shared helpers (all datasets)

- **Re-download an existing snapshot** — `python scripts/get_snapshot.py --snapshot-id s_xxx [--status-only]`
  Free within the 16-day retention window. Use this instead of re-triggering.

- **List recent snapshots** — `python scripts/list_snapshots.py [--kind people|company|jobs|posts] [--status ready] [--limit 20]`
  Free. Handy if the user lost a snapshot id.

- **Describe the field schema** — `python scripts/describe_fields.py --kind people|company|jobs|posts [--names-only] [--active-only]`
  Free. Authoritative source for what columns the scraper can return — each
  dataset has its own schema.

## Guidance

- **Resolve the canonical URL first.** The lookup scripts expect a real
  LinkedIn URL. For people: `https://www.linkedin.com/in/<handle>`. For
  companies: `https://www.linkedin.com/company/<slug>`. If the user gives
  a display name, resolve the URL via the brightdata-serp skill
  (`search.py 'site:linkedin.com/in/ "<name>"' --format parsed`, one paid
  SERP call) before calling the scraper — cheap compared to wasting a full
  profile scrape on a wrong URL.
- **Cap discoveries.** If the user says "find me VP Corp Dev roles" without
  a number, default to `--limit-per-input 25` and tell them you capped it
  so they don't get surprised on their next Bright Data invoice. Increase
  only on explicit request.
- **Default to the full record.** Every `lookup_*.py` and `discover_*.py`
  script already returns the complete dataset row when `--fields` is
  omitted — leave it omitted. Trimming saves nothing on the bill
  (billing is per-record, not per-field) and routinely strips out
  signals the caller didn't know they wanted (experience history,
  recent activity, employee samples, post engagement metadata). Only
  pass `--fields` when the user explicitly asks for a trimmed payload
  or context-window pressure forces it (e.g.
  `--fields name,headline,current_company`).
- **For long jobs, use `--no-wait`.** Record the `snapshot_id` in your
  response so the user can fetch later via `get_snapshot.py`. Large
  discoveries can take 10+ minutes.
- **Prefer cached data.** Before triggering, ask whether the user already
  has a snapshot_id from a recent run — `get_snapshot.py` is free within
  16 days of the original trigger.
- **Don't dump raw JSON.** See the output contract below.

## Output contract

For a **person**, summarise the profile in 4–8 bullets:
- Full name (+ current headline)
- Current role and company
- Location
- Notable prior experience (top 2–3)
- Education (top entry)
- Top skills (3–5) if the user asked
- Profile URL

For a **company**, summarise in 4–8 bullets:
- Name (+ legal name if different)
- One-sentence description
- HQ city, country
- Founded
- Industries (top 3)
- Headcount range
- Website + LinkedIn URL

For **jobs**, use a compact table or bulleted list per posting (title,
company, location, seniority, posting URL, maybe salary if present) —
capped at the top 5–10 when discovering.

For **posts**, summarise each post with author, posting date, a one-line
excerpt, reaction/comment counts, and the post URL.

Always include the `snapshot_id` at the end so the user can re-fetch for
free. **Never dump the full JSON unless the user explicitly asks for "raw
data".**

## References

- `references/curls.md` — verified curl examples for every endpoint
- `references/fields.md` — grouped field list per dataset (convenience; not authoritative)
- `references/LIMITS.md` — billing, retention, auth, and failure modes

## Smoke test

```bash
python scripts/smoke_test.py
```

Free, metadata-only. Asserts the dataset metadata call works for all four
LinkedIn datasets (people, company, jobs, posts). Prints `SKIP:
BRIGHTDATA_API_TOKEN not set` if the token is missing, so unauthenticated
CI doesn't fail.
