# brightdata-crunchbase — limits and caveats

Things that will bite you if you don't know them up front.

## 1. This is the pay‑as‑you‑go Web Scraper API, not the Datasets marketplace

Bright Data sells Crunchbase in two SKUs. This skill points at the **Web
Scraper API** (pay‑as‑you‑go, billed per record, **no minimum spend**). It
does **not** use the Datasets marketplace snapshot, which has a $250 minimum
order — that's avoided on purpose.

If you ever see "$250 minimum" language, you're on the wrong product page.

- Pricing: from ~$0.001/record on a Bright Data subscription, up to ~$0.0015/
  record on the generic pay‑as‑you‑go tier.
- Billed per **returned** record, not per input. A discovery with
  `limit_per_input=100` and two keywords can bill up to 200 records.

## 2. One dataset id, one shape

The Crunchbase scraper exposes a single public dataset id:

```
gd_l1vijqt9jfj7olije   # Crunchbase Companies Information
```

There is **no separate people / investors / funding‑rounds / acquisitions
dataset**. Those categories come back as nested fields on the company
record (`funding_rounds`, `investors`, `key_people`, `acquisitions`, …).
If the user asks for "all investors in fintech 2024", the only path is
discover companies → read the nested investor lists → aggregate.

Custom datasets for those slices exist only through Bright Data sales, not
through this API.

## 3. Two input modes

- **Lookup by URL** (`lookup_companies.py`) — one record per input URL, very
  predictable cost, use this whenever you already know the company.
- **Discover by keyword** (`discover_companies.py`) — discover‑new mode with
  `discover_by=keyword`. `--limit-per-input` is **required** because an
  uncapped broad keyword like "AI" can return thousands of rows and burn a
  budget instantly. Other generic `discover_by` values exist on the Web
  Scraper API but aren't confirmed for this dataset.

## 4. Snapshot retention: 16 days

Every trigger produces a `snapshot_id`. Bright Data keeps the data on their
side for **16 days**. Within that window, `get_snapshot.py` re‑downloads for
free. After 16 days the snapshot is gone and you pay again to re‑scrape.

If you need durable storage, dump the JSON to disk right after a successful
`wait_for_snapshot`.

## 5. Async flow and polling cadence

```
POST /datasets/v3/trigger  →  {snapshot_id}
GET  /datasets/v3/progress/{id}   # status: starting | running | ready | failed
GET  /datasets/v3/snapshot/{id}   # 409 until ready
```

- Trigger is fast, scraping is not. Small lookups (1–5 URLs) are often ready
  in under a minute; large discoveries can take 5–15+ minutes.
- No public QPS limit, but we still poll every 10s and retry 429/5xx with
  exponential backoff. Please don't lower `--poll-interval` below ~5s.
- For very large jobs, use `--no-wait`, record the snapshot id, and come
  back with `get_snapshot.py --snapshot-id …`.

## 6. Field schema drifts

`references/fields.md` is a grouped convenience list but it's not the source
of truth. Always prefer:

```
python scripts/describe_fields.py
```

which calls `/datasets/{dataset_id}/metadata` and returns the live field set.
This endpoint is free.

## 7. Auth

One Bearer token from the Bright Data dashboard, exported as
`BRIGHTDATA_API_TOKEN`. The scripts exit with code 2 and a clear stderr
message if it's missing. There is no second key to manage.

## 8. What this skill does NOT do

- Resolve a free‑text company name ("that sneaker startup") into a
  Crunchbase slug. The URL path expects `https://www.crunchbase.com/
  organization/<slug>`. Claude should resolve the slug via web search or
  ask the user first.
- Run LLM summarization on the result. The scripts emit structured JSON;
  the `SKILL.md` output contract tells the caller how to narrate it.
- Fan out across multiple Bright Data datasets. One dataset, one scope.
