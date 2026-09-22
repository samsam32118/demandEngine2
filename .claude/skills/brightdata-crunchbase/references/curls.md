# Verified Bright Data Crunchbase Web Scraper API curls

All requests use the same Bearer token:

```
Authorization: Bearer $BRIGHTDATA_API_TOKEN
```

Dataset id: `gd_l1vijqt9jfj7olije` (Crunchbase Companies Information).

Base URL: `https://api.brightdata.com`.

## 1. Trigger — lookup by URL (PDP mode)

One record billed per input URL.

```bash
curl -X POST \
  "https://api.brightdata.com/datasets/v3/trigger?dataset_id=gd_l1vijqt9jfj7olije&include_errors=true" \
  -H "Authorization: Bearer $BRIGHTDATA_API_TOKEN" \
  -H "Content-Type: application/json" \
  -d '[
    {"url": "https://www.crunchbase.com/organization/apple"},
    {"url": "https://www.crunchbase.com/organization/brightdata"}
  ]'
```

Response:

```json
{ "snapshot_id": "s_m4x7enmven8djfqak" }
```

## 2. Trigger — discover by keyword

One record billed per returned row. `limit_per_input` is the main cost cap.

```bash
curl -X POST \
  "https://api.brightdata.com/datasets/v3/trigger?dataset_id=gd_l1vijqt9jfj7olije&include_errors=true&type=discover_new&discover_by=keyword&limit_per_input=25" \
  -H "Authorization: Bearer $BRIGHTDATA_API_TOKEN" \
  -H "Content-Type: application/json" \
  -d '[
    {"keyword": "AI"},
    {"keyword": "Venture Capital"}
  ]'
```

Response: `{ "snapshot_id": "..." }`.

### Trim the returned columns

Add `custom_output_fields` (pipe-delimited) to the query string. This reduces
payload size only — billing is still per returned record.

```
&custom_output_fields=name|url|founded_date|num_employees|industries
```

## 3. Monitor progress

```bash
curl -X GET "https://api.brightdata.com/datasets/v3/progress/s_m4x7enmven8djfqak" \
  -H "Authorization: Bearer $BRIGHTDATA_API_TOKEN"
```

Response while running (may come back as HTTP 202):

```json
{
  "snapshot_id": "s_m4x7enmven8djfqak",
  "dataset_id": "gd_l1vijqt9jfj7olije",
  "status": "running"
}
```

Status values: `starting | running | ready | failed`. Poll every ~10 seconds.

## 4. Download results

Only call this once `status=ready`. Returns HTTP 409 otherwise.

```bash
curl -X GET "https://api.brightdata.com/datasets/v3/snapshot/s_m4x7enmven8djfqak?format=json" \
  -H "Authorization: Bearer $BRIGHTDATA_API_TOKEN"
```

Response: a JSON array of company records, one per returned row. Snapshots are
retained **16 days** — after that, the download endpoint 404s and you have to
re-trigger (and re-pay).

Supported `format` values: `json` (array), `ndjson` / `jsonl` (newline-
delimited), `csv`.

## 5. List snapshots

Free, metadata-only.

```bash
curl -X GET "https://api.brightdata.com/datasets/v3/snapshots?dataset_id=gd_l1vijqt9jfj7olije" \
  -H "Authorization: Bearer $BRIGHTDATA_API_TOKEN"
```

Optional filters: `status=ready|running|failed|starting`. Useful for recovering
a snapshot id you forgot to save.

## 6. Get dataset field metadata

Free, metadata-only. Use this to discover the authoritative list of returned
fields — it's long (~100-124 entries) and changes over time.

```bash
curl -X GET "https://api.brightdata.com/datasets/gd_l1vijqt9jfj7olije/metadata" \
  -H "Authorization: Bearer $BRIGHTDATA_API_TOKEN"
```

Response shape:

```json
{
  "id": "gd_l1vijqt9jfj7olije",
  "fields": {
    "name":        {"type": "string", "active": true, "required": true,  "description": "..."},
    "url":         {"type": "string", "active": true, "required": true,  "description": "..."},
    "founded_date":{"type": "date",   "active": true, "required": false, "description": "..."},
    "num_employees":{"type":"string", "active": true, "required": false, "description": "..."}
  }
}
```

## Async webhook delivery (optional)

Instead of polling, ask Bright Data to POST the result to a webhook:

```
&endpoint=https://example.com/hooks/crunchbase
&notify=https://example.com/hooks/crunchbase-done
&auth_header=Bearer%20secret
&uncompressed_webhook=true
```

This skill doesn't wire that up out of the box — use `--no-wait` and
`get_snapshot.py` instead if you need async behaviour.
