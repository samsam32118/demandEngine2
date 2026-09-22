# brightdata-linkedin — limits and caveats

Things that will bite you if you don't know them up front.

## 1. This is the pay-as-you-go Web Scraper API, not the Datasets marketplace

Bright Data sells LinkedIn data in two SKUs. This skill points at the
**Web Scraper API** (pay-as-you-go, billed per record, **no minimum
spend**). It does **not** use the Datasets marketplace snapshot, which
has a $250 minimum order — that's avoided on purpose.

If you ever see "$250 minimum" language, you're on the wrong product page.

- Pricing: from ~$0.001/record on a Bright Data subscription, up to
  ~$0.0015/record on the generic pay-as-you-go tier.
- Billed per **returned** record, not per input. A discovery with
  `limit_per_input=100` and two inputs can bill up to 200 records.

## 2. Four dataset ids, one API shape

The four LinkedIn scrapers live under distinct dataset ids but share
the same `/datasets/v3/trigger|progress|snapshot` contract:

```
gd_l1viktl72bvl7bjuj0   # People Profile
gd_l1vikfnt1wgvvqz95w   # Company Info
gd_lpfll7v5hcqtkxl6l    # Jobs
gd_lyy3tktm25m4avu764   # Posts
```

The only things that differ between datasets are:
- The `dataset_id` query param.
- The input body shape (URL dicts, `{first_name, last_name}`, or a
  jobs-search filter dict).
- The returned field schema (see `references/fields.md`).

There is no single "LinkedIn" dataset — you have to pick the right id
for the question. `client.py` exposes all four as constants plus a
`DATASETS` dict keyed by a short `kind` string.

## 3. Lookup vs discover modes

| Mode | Billing | When to use |
|------|---------|-------------|
| Lookup by URL | 1 record per input | You know the exact person/company/job/post URL |
| Discover by name (people) | 1 record per returned match | You have a name and want Bright Data to resolve the profile |
| Discover by keyword (jobs) | 1 record per returned posting | You want a list of jobs matching filters |
| Discover by profile_url (posts) | 1 record per returned post | You want recent posts by a specific person |
| Discover by company_url (posts) | 1 record per returned post | You want recent posts from a specific company |

**`--limit-per-input` is the main cost guard for discover modes.** An
uncapped `keyword=software engineer country=US` can return thousands of
rows and burn a budget instantly.

## 4. Body format for /trigger

The POST body is a **bare JSON array** of input dicts, not a
`{"input": [...]}` wrapper:

```json
[
  {"url": "https://www.linkedin.com/in/elad-gil/"},
  {"url": "https://www.linkedin.com/in/reidhoffman/"}
]
```

This matches the crunchbase skill and differs from the pitchbook
`/scrape` endpoint, which uses the `{"input": [...]}` shape. If you
copy curl from one skill to another, mind the wrapper.

## 5. Snapshot retention: 16 days

Every trigger produces a `snapshot_id`. Bright Data keeps the data on
their side for **16 days**. Within that window, `get_snapshot.py`
re-downloads for free. After 16 days the snapshot is gone and you pay
again to re-scrape.

If you need durable storage, dump the JSON to disk right after a
successful `wait_for_snapshot`.

## 6. Async flow and polling cadence

```
POST /datasets/v3/trigger   →  {snapshot_id}
GET  /datasets/v3/progress/{id}   # status: starting | running | ready | failed
GET  /datasets/v3/snapshot/{id}   # 409 until ready
```

- Trigger is fast, scraping is not. Small lookups (1–5 URLs) are often
  ready in under a minute; large discoveries can take 5–15+ minutes.
- No public QPS limit, but we still poll every 10s and retry 429/5xx
  with exponential backoff. Please don't lower `--poll-interval` below
  ~5s.
- For very large jobs, use `--no-wait`, record the snapshot id, and
  come back with `get_snapshot.py --snapshot-id …`.

## 7. Field schemas drift

`references/fields.md` is a grouped convenience list but it's not the
source of truth. Always prefer:

```
python scripts/describe_fields.py --kind people
python scripts/describe_fields.py --kind company
python scripts/describe_fields.py --kind jobs
python scripts/describe_fields.py --kind posts
```

which calls `/datasets/{dataset_id}/metadata` for the chosen dataset
and returns the live field set. This endpoint is free.

## 8. Auth

One Bearer token from the Bright Data dashboard, exported as
`BRIGHTDATA_API_TOKEN`. The scripts exit with code 2 and a clear stderr
message if it's missing. There is no second key to manage.

The token must have the **LinkedIn Web Scraper APIs** enabled on your
Bright Data account — that's a separate toggle from the Crunchbase and
PitchBook scrapers the other two Bright Data skills use.

Each **discovery collector** is also toggled separately inside the
LinkedIn group. On an account where a given collector isn't enabled,
`/datasets/v3/trigger` returns HTTP 400
`"Incorrect discovery collector id Available types:"` with an empty
list. `client.py` catches that shape and adds a hint to the error.
Observed on this repo's test account (2026-04-09): `people lookup by
URL`, `company lookup by URL`, `jobs lookup by URL`, `posts lookup by
URL`, `discover_jobs by keyword`, and `discover_posts by profile_url /
company_url` are all enabled; `discover_people by name` is **not**
enabled. Flip the collector on in the Bright Data dashboard to enable
it — the dataset id doesn't change.

## 9. URL resolution is your responsibility

This skill does **not** turn a free-text name into a LinkedIn URL. The
lookup paths expect canonical URLs:
- People: `https://www.linkedin.com/in/<handle>`
- Companies: `https://www.linkedin.com/company/<slug>`
- Jobs: `https://www.linkedin.com/jobs/view/<id>`
- Posts: `https://www.linkedin.com/posts/<slug>` (or `/pulse/` / `/feed/update/`)

If you only have a name, run brightdata-serp `search.py "<name>
site:linkedin.com/in/"` (one paid SERP call) to resolve the URL first.
Don't guess — a wrong URL still costs a billable record on most of the
datasets, which is a worse deal than one extra SERP call.

For people you can also use `discover_people.py` to let Bright Data
resolve a name, but results are noisy for common names and bill per
match.

## 10. Budget classification

This skill shares the **Bright Data** token with `brightdata-crunchbase`
and `brightdata-pitchbook`; the calling agent tracks the shared daily count.
There is no separate LinkedIn tier — a LinkedIn lookup and a Crunchbase
lookup both draw from the same 100/day pool.

If the BrightData cap is exhausted for the day, wait for the next beat
— every sanctioned search backend is on the same budget.

## 11. What this skill does NOT do

- Resolve a free-text name or company ("that sneaker startup") into a
  canonical LinkedIn URL. See section 9.
- Run LLM summarization on the result. Scripts emit structured JSON;
  `SKILL.md`'s output contract tells the caller how to narrate it.
- Fan out across multiple Bright Data product families. LinkedIn only —
  use `brightdata-crunchbase` or `brightdata-pitchbook` for company
  financials.
