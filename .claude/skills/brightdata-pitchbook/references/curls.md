# Verified Bright Data PitchBook Web Scraper API curls

All requests use the same Bearer token:

```
Authorization: Bearer $BRIGHTDATA_API_TOKEN
```

Dataset id: `gd_m4ijiqfp2n9oe3oluj` (PitchBook Companies Information).

Base URL: `https://api.brightdata.com`.

## 1. Scrape — synchronous lookup by URL (primary path)

Blocks until data is ready and returns rows directly. No snapshot_id, no
polling. Body wraps inputs in `{"input": [...]}` (PitchBook API convention).

```bash
curl -X POST \
  "https://api.brightdata.com/datasets/v3/scrape?dataset_id=gd_m4ijiqfp2n9oe3oluj&notify=false&include_errors=true" \
  -H "Authorization: Bearer $BRIGHTDATA_API_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"input":[{"url":"https://pitchbook.com/profiles/company/467033-41"}]}'
```

Response: a JSON array of company records (one per input URL), returned
synchronously once scraping completes (~15–60 seconds for a single URL).

### Multiple companies in one call

```bash
curl -X POST \
  "https://api.brightdata.com/datasets/v3/scrape?dataset_id=gd_m4ijiqfp2n9oe3oluj&notify=false&include_errors=true" \
  -H "Authorization: Bearer $BRIGHTDATA_API_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"input":[
    {"url":"https://pitchbook.com/profiles/company/467033-41"},
    {"url":"https://pitchbook.com/profiles/company/56147-77"}
  ]}'
```

## 2. Trigger — async path (produces snapshot_id)

Use this if you want to kick off a job without waiting. Produces a
`snapshot_id` you can poll later. **Note:** the `/trigger` body is a plain
array `[...]`, NOT the `{"input": [...]}` wrapper.

```bash
curl -X POST \
  "https://api.brightdata.com/datasets/v3/trigger?dataset_id=gd_m4ijiqfp2n9oe3oluj&include_errors=true" \
  -H "Authorization: Bearer $BRIGHTDATA_API_TOKEN" \
  -H "Content-Type: application/json" \
  -d '[{"url":"https://pitchbook.com/profiles/company/467033-41"}]'
```

Response:

```json
{ "snapshot_id": "s_m4x7enmven8djfqak" }
```

## 3. Monitor progress (async path only)

```bash
curl -X GET "https://api.brightdata.com/datasets/v3/progress/s_m4x7enmven8djfqak" \
  -H "Authorization: Bearer $BRIGHTDATA_API_TOKEN"
```

Status values: `starting | running | ready | failed`. Poll every ~10 seconds.

## 4. Download results (async path only)

Only call once `status=ready`. Returns HTTP 409 otherwise.

```bash
curl -X GET "https://api.brightdata.com/datasets/v3/snapshot/s_m4x7enmven8djfqak?format=json" \
  -H "Authorization: Bearer $BRIGHTDATA_API_TOKEN"
```

Snapshots are retained **16 days**. Supported `format` values: `json`,
`ndjson` / `jsonl`, `csv`.

## 5. List snapshots (metadata-only, free)

```bash
curl -X GET "https://api.brightdata.com/datasets/v3/snapshots?dataset_id=gd_m4ijiqfp2n9oe3oluj" \
  -H "Authorization: Bearer $BRIGHTDATA_API_TOKEN"
```

Optional filter: `&status=ready|running|failed|starting`.

## PitchBook URL format

PitchBook company profile URLs follow this pattern:

```
https://pitchbook.com/profiles/company/<numeric-id>-<suffix>
```

Examples:
- `https://pitchbook.com/profiles/company/467033-41`
- `https://pitchbook.com/profiles/company/56147-77`

To find the URL for a company by name, search the web for:
```
"<company name>" site:pitchbook.com/profiles/company
```
or simply `"<company name> pitchbook"` and look for the profile link.
