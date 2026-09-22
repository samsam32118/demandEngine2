# brightdata-pitchbook — limits and caveats

Things that will bite you if you don't know them up front.

## 1. Pay-as-you-go, no minimum spend

This skill targets Bright Data's **Web Scraper API** pay-as-you-go SKU —
not the Datasets marketplace, which has a $250 minimum order. Pricing is
~$0.001–$0.0015 per **returned** record with no minimum commitment.

If you ever see "$250 minimum" language, you're looking at the wrong page.

## 2. One dataset id

```
gd_m4ijiqfp2n9oe3oluj   # PitchBook Companies Information
```

There is no separate people / investors / funding-rounds dataset via this
API. All data (investors, funding rounds, key people, valuation) comes back
as nested fields on the company record.

## 3. Two API endpoints — use scrape for normal lookups

| Endpoint | Path | Sync? | Body format | When to use |
|----------|------|-------|-------------|-------------|
| scrape   | `/datasets/v3/scrape?notify=false` | Yes — blocks | `{"input": [...]}` | Normal single or small-batch lookups |
| trigger  | `/datasets/v3/trigger` | No — returns snapshot_id | `[...]` | Large batches or --no-wait deferred jobs |

**Critical:** the body format differs between the two endpoints:
- `/scrape` wraps inputs: `{"input": [{"url": "..."}]}`
- `/trigger` takes a bare array: `[{"url": "..."}]`

`client.py` handles this automatically; only matters if you write raw curls.

## 4. Snapshot retention: 16 days

Every `/trigger` job produces a `snapshot_id`. Bright Data keeps the data
for **16 days** — re-downloading within that window via `get_snapshot.py`
is free. After 16 days the snapshot is gone and you pay to re-scrape.

The synchronous `/scrape` endpoint does **not** create a persistent snapshot.
Save the JSON output to disk right after the call if you need durable storage.

## 5. Async flow and polling cadence (trigger path only)

```
POST /datasets/v3/trigger  →  {snapshot_id}
GET  /datasets/v3/progress/{id}   # status: starting | running | ready | failed
GET  /datasets/v3/snapshot/{id}   # 409 until ready
```

No public QPS limit, but poll every 10s and retry 429/5xx with exponential
backoff. Don't lower `--poll-interval` below ~5s.

## 6. URL resolution is your responsibility

This skill does **not** turn a company name into a PitchBook URL. Before
calling the scraper you must resolve the URL. The correct workflow:

1. Run brightdata-serp `search.py "<company name> pitchbook"` (one paid SERP call).
2. Find a result matching `pitchbook.com/profiles/company/<id>`.
3. Pass that URL to `lookup_company.py`.

Don't guess — a wrong URL wastes a billable record and returns no data.

## 7. Auth

One Bearer token from the Bright Data dashboard, exported as
`BRIGHTDATA_API_TOKEN`. Scripts exit with code 2 and a clear stderr message
if it's missing. No second key to manage.

## 8. HTTP timeout for the synchronous scrape

The `/scrape?notify=false` call is a single blocking HTTP request. The
default timeout in `client.py` is **300 seconds** (5 minutes). A single
PitchBook URL typically completes in 15–60 seconds. If you batch many URLs
in one call and see timeouts, either:
- Reduce batch size (split into multiple calls), or
- Pass `--timeout 600` to `lookup_company.py`.

## 9. What this skill does NOT do

- Discover companies by keyword (no keyword-discovery mode for this dataset
  via the Web Scraper API — use Crunchbase or LinkedIn skills for that).
- Run LLM summarization. Scripts emit structured JSON; SKILL.md's output
  contract tells the caller how to narrate it.
- Fan out across multiple Bright Data datasets.
