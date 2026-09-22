# brightdata-zoominfo — limits and caveats

Things that will bite you if you don't know them up front.

## 1. Pay-as-you-go, no minimum spend

This skill targets Bright Data's **Web Scraper API** pay-as-you-go SKU —
not the Datasets marketplace, which has a $250 minimum order. Pricing is
~$0.001–$0.0015 per **returned** record with no minimum commitment.

If you ever see "$250 minimum" language, you're looking at the wrong page.

## 2. One dataset id, company-only

```
gd_m0ci4a4ivx3j5l6nx   # Zoominfo companies information
```

There is no separate ZoomInfo people dataset on the Web Scraper API as
of 2026-04. The full Bright Data dataset list (310 datasets across the
account) contains exactly one ZoomInfo entry, and it is company-keyed.

**Person URLs (`/p/<name>/<id>`) are accepted at validation but return
all-null records** while still billing one chargeable record. `lookup_company.py`
exits 2 if a `/p/` URL is passed.

Only one of the eight people-shaped fields actually returns person
records — verified live against Walmart's profile (2026-04-30):

| Field | What it actually is |
|---|---|
| `leadership` | Array of person objects (~3 entries: name, title, avatar, /p/ URL). The 3-person sample **rotates** between calls to the same `/c/` URL; verified on Actionstep 2026-04-30 with two lookups 10 min apart returning disjoint trios. |
| `ceo` | Structured `{name, title, score, url}` — frequently all-null even when the actual CEO appears in `leadership` and `org_chart` |
| `top_contacts` | **Integer count** (Walmart: 148 135; Actionstep: 198) |
| `c_level_employees` | **Integer count** (Walmart: 145; Actionstep: 9) |
| `vp_level_employees` | **Integer count** (Walmart: 1078; Actionstep: 12) |
| `director_level_employees` | **Integer count** (Walmart: 7362; Actionstep: 21) |
| `manager_level_employees` | **Integer count** (Actionstep: 59) |
| `non_manager_employees` | **Integer count** (Actionstep: 106) |
| `org_chart` | Varies. Actionstep returned 5 C-suite entries (CEO + CFO + CTO + President + Controller) with `/p/` URLs; Walmart returned null. The `avatar` URLs in this field are placeholder `/undefined`. Treat as a useful bonus when populated, not a reliable column. |
| `email_formats` | Frequently `null`, even on Fortune-50 and 51–200 companies. Use the `email-guesser` skill instead for pattern inference. |

**No individual email addresses are returned by this dataset, ever.**
ZoomInfo's per-contact email database is a separate paid product not
exposed via the Bright Data Web Scraper API marketplace as of 2026-04.
For email addresses, use `email-guesser` (pattern inference) or pivot
the `leadership` names to `brightdata-linkedin lookup_people` for
contact context.

## 3. Three API paths — use scrape for normal lookups

| Path | Endpoint | Sync? | Body format | When to use |
|------|----------|-------|-------------|-------------|
| Lookup (sync)  | `/datasets/v3/scrape?notify=false` | Yes — blocks | `{"input": [{"url": "..."}]}` | Normal single or small-batch lookups |
| Lookup (async) | `/datasets/v3/trigger` | No — returns snapshot_id | `[{"url": "..."}]` | Lookups via `--no-wait` |
| Discover       | `/datasets/v3/trigger?type=discover_new&discover_by=search_url` | No — returns snapshot_id | `[{"url": "<search_url>"}]` | Find companies matching ZoomInfo search filters |

**Critical:** the body format differs between endpoints:
- `/scrape` wraps inputs: `{"input": [{"url": "..."}]}`
- `/trigger` takes a bare array: `[{"url": "..."}]`

The discovery collector for the ZoomInfo dataset only accepts
`discover_by=search_url` — there is no free-text keyword discovery. The
input field is still named `url`, not `search_url`. `client.py` handles
all of this automatically; only matters if you write raw curls.

## 4. Snapshot retention: 16 days

Every `/trigger` job produces a `snapshot_id`. Bright Data keeps the data
for **16 days** — re-downloading within that window via `get_snapshot.py`
is free. After 16 days the snapshot is gone and you pay to re-scrape.

The synchronous `/scrape` endpoint does **not** create a persistent
snapshot. Save the JSON output to disk right after the call if you need
durable storage.

## 5. Cancelling a runaway snapshot

`POST /datasets/v3/snapshot/{snapshot_id}/cancel` halts a running job
before it bills more rows. Useful if a discovery is firing with
`limit_per_input` higher than intended. Free.

## 6. Async flow and polling cadence (trigger path)

```
POST /datasets/v3/trigger  →  {snapshot_id}
GET  /datasets/v3/progress/{id}   # status: starting | running | ready | failed
GET  /datasets/v3/snapshot/{id}   # 409 until ready
```

No public QPS limit, but poll every 10s and retry 429/5xx with exponential
backoff. Don't lower `--poll-interval` below ~5s.

## 7. URL resolution is your responsibility

This skill does **not** turn a company name into a ZoomInfo URL. Before
calling the lookup scraper you must resolve the URL. The correct workflow:

1. Run brightdata-serp `search.py "<company name> zoominfo"` (one paid SERP call).
2. Find a result matching `zoominfo.com/c/<slug>/<id>`.
3. Pass that URL to `lookup_company.py`.

For discoveries, build a ZoomInfo search URL of the form
`https://www.zoominfo.com/companies-search/<filters>` (e.g.
`location-usa-industry-software`) — verify the filter combination loads
in a browser before scraping; broken filter strings can return a generic
landing page that costs records but yields no usable rows.

Don't guess company URLs — a wrong URL wastes a billable record and
returns no data.

## 8. Auth

One Bearer token from the Bright Data dashboard, exported as
`BRIGHTDATA_API_TOKEN`. Scripts exit with code 2 and a clear stderr message
if it's missing. No second key to manage.

## 9. HTTP timeout for the synchronous scrape

The `/scrape?notify=false` call is a single blocking HTTP request. The
default timeout in `client.py` is **300 seconds** (5 minutes). A single
ZoomInfo URL typically completes in 15–60 seconds. If you batch many URLs
in one call and see timeouts, either:
- Reduce batch size (split into multiple calls), or
- Pass `--timeout 600` to `lookup_company.py`.

## 10. What this skill does NOT do

- Discover companies by free-text keyword. The ZoomInfo dataset's
  discovery collector only accepts `search_url`. Use Crunchbase or
  LinkedIn skills if you need keyword discovery.
- Look up individual people by ZoomInfo profile URL. The dataset is
  company-keyed; people data is embedded inside company records.
- Run LLM summarization. Scripts emit structured JSON; SKILL.md's
  output contract tells the caller how to narrate it.
- Forget the budget. Calls billed by this skill count against the shared
  100/day BrightData cap; the calling agent tracks that count.
