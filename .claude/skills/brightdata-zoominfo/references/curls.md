# Verified Bright Data ZoomInfo Web Scraper API curls

All requests use the same Bearer token:

```
Authorization: Bearer $BRIGHTDATA_API_TOKEN
```

Dataset id: `gd_m0ci4a4ivx3j5l6nx` (Zoominfo companies information).

Base URL: `https://api.brightdata.com`.

## 1. Scrape — synchronous lookup by URL (primary path)

Blocks until data is ready and returns rows directly. No snapshot_id, no
polling. Body wraps inputs in `{"input": [...]}` (ZoomInfo API convention,
same as PitchBook).

```bash
curl -X POST \
  "https://api.brightdata.com/datasets/v3/scrape?dataset_id=gd_m0ci4a4ivx3j5l6nx&notify=false&include_errors=true" \
  -H "Authorization: Bearer $BRIGHTDATA_API_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"input":[{"url":"https://www.zoominfo.com/c/walmart-inc/155353090"}]}'
```

Response: a JSON array of company records (one per input URL), returned
synchronously once scraping completes (~15–60 seconds per URL).

### Multiple companies in one call

```bash
curl -X POST \
  "https://api.brightdata.com/datasets/v3/scrape?dataset_id=gd_m0ci4a4ivx3j5l6nx&notify=false&include_errors=true" \
  -H "Authorization: Bearer $BRIGHTDATA_API_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"input":[
    {"url":"https://www.zoominfo.com/c/walmart-inc/155353090"},
    {"url":"https://www.zoominfo.com/c/bright-data-ltd/430599389"}
  ]}'
```

### Trim the payload to a subset of fields

```bash
curl -X POST \
  "https://api.brightdata.com/datasets/v3/scrape?dataset_id=gd_m0ci4a4ivx3j5l6nx&notify=false&include_errors=true&custom_output_fields=name|revenue|total_employees|headquarters|website" \
  -H "Authorization: Bearer $BRIGHTDATA_API_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"input":[{"url":"https://www.zoominfo.com/c/walmart-inc/155353090"}]}'
```

Note: `custom_output_fields` reduces payload size; billing is unchanged.

## 2. Trigger — async lookup (produces snapshot_id)

Use this if you want to kick off a job without waiting. Produces a
`snapshot_id` you can poll later. **Note:** the `/trigger` body is a plain
array `[...]`, NOT the `{"input": [...]}` wrapper.

```bash
curl -X POST \
  "https://api.brightdata.com/datasets/v3/trigger?dataset_id=gd_m0ci4a4ivx3j5l6nx&include_errors=true" \
  -H "Authorization: Bearer $BRIGHTDATA_API_TOKEN" \
  -H "Content-Type: application/json" \
  -d '[{"url":"https://www.zoominfo.com/c/walmart-inc/155353090"}]'
```

Response:

```json
{ "snapshot_id": "s_m4x7enmven8djfqak" }
```

## 3. Trigger — discover-new by ZoomInfo search URL

The ZoomInfo discovery collector only accepts `search_url` — there is no
free-text keyword discovery for this dataset. The input field name is
still `url`, not `search_url`.

```bash
curl -X POST \
  "https://api.brightdata.com/datasets/v3/trigger?dataset_id=gd_m0ci4a4ivx3j5l6nx&type=discover_new&discover_by=search_url&include_errors=true&limit_per_input=25" \
  -H "Authorization: Bearer $BRIGHTDATA_API_TOKEN" \
  -H "Content-Type: application/json" \
  -d '[{"url":"https://www.zoominfo.com/companies-search/location-usa-industry-software"}]'
```

Response:

```json
{ "snapshot_id": "sd_molrll592msrhx79wo" }
```

`limit_per_input` is essential — without it a broad search URL can return
hundreds of rows and bill at ~$0.001–$0.0015 each.

## 4. Monitor progress (async path only)

```bash
curl -X GET "https://api.brightdata.com/datasets/v3/progress/sd_molrll592msrhx79wo" \
  -H "Authorization: Bearer $BRIGHTDATA_API_TOKEN"
```

Status values: `starting | running | ready | failed`. Poll every ~10 seconds.

## 5. Cancel a running snapshot (free, recovers from accidental triggers)

```bash
curl -X POST "https://api.brightdata.com/datasets/v3/snapshot/sd_molrll592msrhx79wo/cancel" \
  -H "Authorization: Bearer $BRIGHTDATA_API_TOKEN"
```

Returns `OK` (text/html). Useful if a discovery is running with a
`limit_per_input` higher than intended.

## 6. Download results (async path only)

Only call once `status=ready`. Returns HTTP 409 otherwise.

```bash
curl -X GET "https://api.brightdata.com/datasets/v3/snapshot/sd_molrll592msrhx79wo?format=json" \
  -H "Authorization: Bearer $BRIGHTDATA_API_TOKEN"
```

Snapshots are retained **16 days**. Supported `format` values: `json`,
`ndjson` / `jsonl`, `csv`.

## 7. List snapshots (metadata-only, free)

```bash
curl -X GET "https://api.brightdata.com/datasets/v3/snapshots?dataset_id=gd_m0ci4a4ivx3j5l6nx" \
  -H "Authorization: Bearer $BRIGHTDATA_API_TOKEN"
```

Optional filter: `&status=ready|running|failed|starting`.

## 8. Describe field schema (metadata-only, free)

```bash
curl -X GET "https://api.brightdata.com/datasets/gd_m0ci4a4ivx3j5l6nx/metadata" \
  -H "Authorization: Bearer $BRIGHTDATA_API_TOKEN"
```

Returns the 39-field schema with type, description, and sample values.

## ZoomInfo URL formats

ZoomInfo company profile URLs follow this pattern:

```
https://www.zoominfo.com/c/<company-slug>/<numeric-id>
```

Examples:
- `https://www.zoominfo.com/c/walmart-inc/155353090`
- `https://www.zoominfo.com/c/bright-data-ltd/430599389`

Search URLs follow this pattern:

```
https://www.zoominfo.com/companies-search/<filter-segments-joined-by-dashes>
```

Examples:
- `https://www.zoominfo.com/companies-search/location-usa-industry-software`
- `https://www.zoominfo.com/companies-search/location-brazil-industry-business-services`
- `https://www.zoominfo.com/companies-search/location-usa-industry-software-employees-50-200`

To find the URL for a specific company by name, search the web for:

```
"<company name>" site:zoominfo.com/c
```

or simply `"<company name> zoominfo"` and look for the profile link.
