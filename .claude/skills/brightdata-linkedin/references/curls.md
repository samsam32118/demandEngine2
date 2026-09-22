# Verified Bright Data LinkedIn Web Scraper API curls

All requests use the same Bearer token:

```
Authorization: Bearer $BRIGHTDATA_API_TOKEN
```

Base URL: `https://api.brightdata.com`.

## Dataset ids

| Kind    | Dataset id                | Covers |
|---------|---------------------------|-----------------------------------|
| people  | `gd_l1viktl72bvl7bjuj0`   | LinkedIn person profiles |
| company | `gd_l1vikfnt1wgvvqz95w`   | LinkedIn company pages |
| jobs    | `gd_lpfll7v5hcqtkxl6l`    | LinkedIn job postings |
| posts   | `gd_lyy3tktm25m4avu764`   | LinkedIn posts, articles, author feeds |

---

## 1. People — lookup by profile URL

One record billed per input URL.

```bash
curl -X POST \
  "https://api.brightdata.com/datasets/v3/trigger?dataset_id=gd_l1viktl72bvl7bjuj0&include_errors=true" \
  -H "Authorization: Bearer $BRIGHTDATA_API_TOKEN" \
  -H "Content-Type: application/json" \
  -d '[
    {"url": "https://www.linkedin.com/in/elad-gil/"},
    {"url": "https://www.linkedin.com/in/reidhoffman/"}
  ]'
```

Response: `{ "snapshot_id": "s_..." }`.

## 2. People — discover by name

Discover-new mode. Input is `{first_name, last_name}` pairs. One
record per returned match (often multiple per ambiguous name).

```bash
curl -X POST \
  "https://api.brightdata.com/datasets/v3/trigger?dataset_id=gd_l1viktl72bvl7bjuj0&include_errors=true&type=discover_new&discover_by=name" \
  -H "Authorization: Bearer $BRIGHTDATA_API_TOKEN" \
  -H "Content-Type: application/json" \
  -d '[
    {"first_name": "Bill", "last_name": "Gates"},
    {"first_name": "James", "last_name": "Smith"}
  ]'
```

## 3. Company — lookup by URL

One record billed per input URL. Accepts the `www.linkedin.com`,
`il.linkedin.com`, and `organization-guest/company/` variants.

```bash
curl -X POST \
  "https://api.brightdata.com/datasets/v3/trigger?dataset_id=gd_l1vikfnt1wgvvqz95w&include_errors=true" \
  -H "Authorization: Bearer $BRIGHTDATA_API_TOKEN" \
  -H "Content-Type: application/json" \
  -d '[
    {"url": "https://www.linkedin.com/company/ibm"},
    {"url": "https://il.linkedin.com/company/bright-data"}
  ]'
```

## 4. Jobs — lookup by posting URL

One record billed per input URL.

```bash
curl -X POST \
  "https://api.brightdata.com/datasets/v3/trigger?dataset_id=gd_lpfll7v5hcqtkxl6l&include_errors=true" \
  -H "Authorization: Bearer $BRIGHTDATA_API_TOKEN" \
  -H "Content-Type: application/json" \
  -d '[
    {"url": "https://www.linkedin.com/jobs/view/3741234567"}
  ]'
```

## 5. Jobs — discover by keyword + location

Discover-new mode. Input is a single search filter dict. Every
returned posting is billed, so `limit_per_input` is mandatory.

```bash
curl -X POST \
  "https://api.brightdata.com/datasets/v3/trigger?dataset_id=gd_lpfll7v5hcqtkxl6l&include_errors=true&type=discover_new&discover_by=keyword&limit_per_input=25" \
  -H "Authorization: Bearer $BRIGHTDATA_API_TOKEN" \
  -H "Content-Type: application/json" \
  -d '[
    {
      "location": "New York",
      "keyword": "VP Corporate Development",
      "country": "US",
      "time_range": "Past month",
      "job_type": "Full-time",
      "experience_level": "Director",
      "remote": "",
      "company": ""
    }
  ]'
```

Accepted filter labels follow LinkedIn's UI strings:
- `time_range`: `Any time`, `Past 24 hours`, `Past week`, `Past month`
- `job_type`: `Full-time`, `Part-time`, `Contract`, `Internship`, `Temporary`
- `experience_level`: `Internship`, `Entry level`, `Associate`, `Mid-Senior level`, `Director`, `Executive`
- `remote`: `On-site`, `Remote`, `Hybrid` (or empty for any)

## 6. Jobs — discover by search URL

Alternative discovery path when you already have a pre-built LinkedIn
jobs search URL (e.g. from pasting one out of the browser).

```bash
curl -X POST \
  "https://api.brightdata.com/datasets/v3/trigger?dataset_id=gd_lpfll7v5hcqtkxl6l&include_errors=true&type=discover_new&discover_by=url&limit_per_input=25" \
  -H "Authorization: Bearer $BRIGHTDATA_API_TOKEN" \
  -H "Content-Type: application/json" \
  -d '[
    {"url": "https://www.linkedin.com/jobs/search/?keywords=VP%20Corporate%20Development&location=New%20York"}
  ]'
```

This skill does not ship a task script for this path — use
`discover_jobs.py` with keyword filters, or paste the search URL into
`lookup_jobs.py` if the API accepts it.

## 7. Posts — lookup by URL

One record billed per input URL. Handles `/posts/`, `/pulse/`, and
`/feed/update/` URLs.

```bash
curl -X POST \
  "https://api.brightdata.com/datasets/v3/trigger?dataset_id=gd_lyy3tktm25m4avu764&include_errors=true" \
  -H "Authorization: Bearer $BRIGHTDATA_API_TOKEN" \
  -H "Content-Type: application/json" \
  -d '[
    {"url": "https://www.linkedin.com/posts/orlenchner_scrapecon-activity-7180537307521769472-oSYN"}
  ]'
```

## 8. Posts — discover by author (profile URL)

Pulls recent posts by a specific person.

```bash
curl -X POST \
  "https://api.brightdata.com/datasets/v3/trigger?dataset_id=gd_lyy3tktm25m4avu764&include_errors=true&type=discover_new&discover_by=profile_url" \
  -H "Authorization: Bearer $BRIGHTDATA_API_TOKEN" \
  -H "Content-Type: application/json" \
  -d '[
    {"url": "https://www.linkedin.com/in/elad-gil/"}
  ]'
```

## 9. Posts — discover by company URL

Pulls recent posts from a specific company page.

```bash
curl -X POST \
  "https://api.brightdata.com/datasets/v3/trigger?dataset_id=gd_lyy3tktm25m4avu764&include_errors=true&type=discover_new&discover_by=company_url" \
  -H "Authorization: Bearer $BRIGHTDATA_API_TOKEN" \
  -H "Content-Type: application/json" \
  -d '[
    {"url": "https://www.linkedin.com/company/bright-data"}
  ]'
```

---

## 10. Monitor progress

```bash
curl -X GET "https://api.brightdata.com/datasets/v3/progress/s_m4x7enmven8djfqak" \
  -H "Authorization: Bearer $BRIGHTDATA_API_TOKEN"
```

Response while running (may come back as HTTP 202):

```json
{
  "snapshot_id": "s_m4x7enmven8djfqak",
  "dataset_id": "gd_l1viktl72bvl7bjuj0",
  "status": "running"
}
```

Status values: `starting | running | ready | failed`. Poll every ~10 seconds.

## 11. Download results

Only call this once `status=ready`. Returns HTTP 409 otherwise.

```bash
curl -X GET "https://api.brightdata.com/datasets/v3/snapshot/s_m4x7enmven8djfqak?format=json" \
  -H "Authorization: Bearer $BRIGHTDATA_API_TOKEN"
```

Response: a JSON array of records. Snapshots are retained **16 days** —
after that, the download endpoint 404s and you pay to re-scrape.

Supported `format` values: `json` (array), `ndjson` / `jsonl`
(newline-delimited), `csv`.

## 12. List snapshots

Free, metadata-only.

```bash
curl -X GET "https://api.brightdata.com/datasets/v3/snapshots?dataset_id=gd_l1viktl72bvl7bjuj0" \
  -H "Authorization: Bearer $BRIGHTDATA_API_TOKEN"
```

Optional filters: `status=ready|running|failed|starting`. Useful for
recovering a snapshot id you forgot to save.

## 13. Get dataset field metadata

Free, metadata-only. Use this to discover the authoritative list of
returned fields for a dataset — each of the four LinkedIn datasets has
its own schema.

```bash
curl -X GET "https://api.brightdata.com/datasets/gd_l1viktl72bvl7bjuj0/metadata" \
  -H "Authorization: Bearer $BRIGHTDATA_API_TOKEN"
```

Response shape:

```json
{
  "id": "gd_l1viktl72bvl7bjuj0",
  "fields": {
    "name":       {"type": "string", "active": true, "required": true,  "description": "..."},
    "headline":   {"type": "string", "active": true, "required": false, "description": "..."},
    "experience": {"type": "array",  "active": true, "required": false, "description": "..."}
  }
}
```

## Trimming returned columns

Add `custom_output_fields` (pipe-delimited) to the query string on any
`/trigger` call. This reduces payload size only — billing is still per
returned record.

```
&custom_output_fields=name|headline|current_company|experience
```

## Async webhook delivery (optional)

Instead of polling, ask Bright Data to POST the result to a webhook:

```
&endpoint=https://example.com/hooks/linkedin
&notify=https://example.com/hooks/linkedin-done
&auth_header=Bearer%20secret
&uncompressed_webhook=true
```

This skill doesn't wire that up out of the box — use `--no-wait` and
`get_snapshot.py` instead if you need async behaviour.
