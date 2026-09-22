# brightdata-tiktok — verified curl examples

Every request below was validated against the live API on 2026-08-04.
The dataset ids and `discover_by` values come from the API's own
`Available types:` responses, not from the marketing site.

All calls share:

```bash
BASE=https://api.brightdata.com
AUTH="Authorization: Bearer $BRIGHTDATA_API_TOKEN"
CT="Content-Type: application/json"
```

The POST body is a **bare JSON array** of input dicts — not a
`{"input": [...]}` wrapper.

## Dataset ids

```
gd_l1villgoiiidt09ci   # TikTok - Profiles
gd_lu702nij2f790tmv9h  # TikTok - Posts
gd_lkf2st302ap89utw5k  # TikTok - Comments
gd_m45m1u911dsa4274pi  # TikTok Shop
```

## The 11 collectors at a glance

| Dataset | Mode | `discover_by` | Required input keys | Optional |
|---|---|---|---|---|
| Profiles | URL lookup | — | `url` | `country` |
| Profiles | Search | `search_url` | `search_url`, `country` | — |
| Posts | URL lookup | — | `url` | `country` |
| Posts | By creator | `profile_url` | `url` | `start_date`, `end_date`, `what_to_collect`, `post_type`, `country`, `sort_by` |
| Posts | By keyword/hashtag | `keyword` | `search_keyword` | `country` |
| Posts | By discovery page | `url` | **`URL`** (capital) | `country` |
| Comments | URL lookup | — | `url` | `collect_replies`, `num_of_comments` |
| Shop | URL lookup | — | `url` | `category` |
| Shop | By category | `category` | `category_url` | — |
| Shop | By keyword | `keyword` | `keyword` | — |
| Shop | By seller | `shop` | `url` | — |

⚠️ **The capital-`URL` trap.** The posts *discovery-page* collector
(`discover_by=url`) is the only one that wants an uppercase key. Sending
lowercase `url` returns:

```json
"errors":[["url","This input should not contain a url field"],
          ["URL","Required field"]]
```

Note also that the Shop *seller* collector (`discover_by=shop`) uses
plain `url`, **not** `shop_url` — the opposite instinct to the one above.

---

## Profiles

### Look up a profile by URL

```bash
curl -s -X POST "$BASE/datasets/v3/trigger?dataset_id=gd_l1villgoiiidt09ci&include_errors=true" \
  -H "$AUTH" -H "$CT" \
  -d '[{"url":"https://www.tiktok.com/@nike"}]'
```

### Discover profiles from a search URL

`country` is required here (it is optional on the URL-lookup path).

```bash
curl -s -X POST "$BASE/datasets/v3/trigger?dataset_id=gd_l1villgoiiidt09ci&type=discover_new&discover_by=search_url&limit_per_input=25&include_errors=true" \
  -H "$AUTH" -H "$CT" \
  -d '[{"search_url":"https://www.tiktok.com/search?q=sales%20coach","country":"US"}]'
```

## Posts

### Look up a video by URL

```bash
curl -s -X POST "$BASE/datasets/v3/trigger?dataset_id=gd_lu702nij2f790tmv9h&include_errors=true" \
  -H "$AUTH" -H "$CT" \
  -d '[{"url":"https://www.tiktok.com/@nike/video/7526248312446881079"}]'
```

### Discover a creator's recent videos

```bash
curl -s -X POST "$BASE/datasets/v3/trigger?dataset_id=gd_lu702nij2f790tmv9h&type=discover_new&discover_by=profile_url&limit_per_input=10&include_errors=true" \
  -H "$AUTH" -H "$CT" \
  -d '[{"url":"https://www.tiktok.com/@nike","what_to_collect":"Posts","sort_by":"Latest"}]'
```

Date filters use `MM-DD-YYYY`:

```json
[{"url":"https://www.tiktok.com/@nike","start_date":"01-01-2026","end_date":"06-30-2026"}]
```

### Discover videos by keyword or hashtag

The key is `search_keyword`, not `keyword` (that's the Shop dataset).

```bash
curl -s -X POST "$BASE/datasets/v3/trigger?dataset_id=gd_lu702nij2f790tmv9h&type=discover_new&discover_by=keyword&limit_per_input=25&include_errors=true" \
  -H "$AUTH" -H "$CT" \
  -d '[{"search_keyword":"sales coach","country":"US"}]'
```

### Discover videos from a /discover/ page — capital `URL`

```bash
curl -s -X POST "$BASE/datasets/v3/trigger?dataset_id=gd_lu702nij2f790tmv9h&type=discover_new&discover_by=url&limit_per_input=25&include_errors=true" \
  -H "$AUTH" -H "$CT" \
  -d '[{"URL":"https://www.tiktok.com/discover/sales-tips"}]'
```

Use the `/discover/<slug>` shape. A `/tag/<slug>` hashtag URL passes
validation but returns an empty result row:

```json
{"error":"No result for: https://www.tiktok.com/tag/salestips",
 "error_code":"dead_page"}
```

For hashtags, use `discover_by=keyword` with `search_keyword` instead.

## Comments

URL collection only — this dataset has **no** discovery mode. The input
is the *video* URL.

```bash
curl -s -X POST "$BASE/datasets/v3/trigger?dataset_id=gd_lkf2st302ap89utw5k&limit_per_input=50&include_errors=true" \
  -H "$AUTH" -H "$CT" \
  -d '[{"url":"https://www.tiktok.com/@nike/video/7526248312446881079","num_of_comments":50,"collect_replies":true}]'
```

Probing `discover_by` on this dataset returns:

```
This dataset does not support discovery. Supported types: ['url_collection']
```

## Shop

### Look up a product by URL

```bash
curl -s -X POST "$BASE/datasets/v3/trigger?dataset_id=gd_m45m1u911dsa4274pi&include_errors=true" \
  -H "$AUTH" -H "$CT" \
  -d '[{"url":"https://shop.tiktok.com/view/product/1729432193useexample"}]'
```

### Discover products by keyword

```bash
curl -s -X POST "$BASE/datasets/v3/trigger?dataset_id=gd_m45m1u911dsa4274pi&type=discover_new&discover_by=keyword&limit_per_input=25&include_errors=true" \
  -H "$AUTH" -H "$CT" \
  -d '[{"keyword":"running shoes"}]'
```

### Discover products in a category

```bash
curl -s -X POST "$BASE/datasets/v3/trigger?dataset_id=gd_m45m1u911dsa4274pi&type=discover_new&discover_by=category&limit_per_input=25&include_errors=true" \
  -H "$AUTH" -H "$CT" \
  -d '[{"category_url":"https://shop.tiktok.com/category/womens-shoes"}]'
```

### Discover a seller's catalogue — plain `url`

```bash
curl -s -X POST "$BASE/datasets/v3/trigger?dataset_id=gd_m45m1u911dsa4274pi&type=discover_new&discover_by=shop&limit_per_input=25&include_errors=true" \
  -H "$AUTH" -H "$CT" \
  -d '[{"url":"https://shop.tiktok.com/@someseller"}]'
```

---

## The async loop (same for every dataset)

```bash
# 1. trigger -> {"snapshot_id":"s_xxxxxxxx"}
SNAP=s_xxxxxxxx

# 2. poll until status=ready  (starting | running | ready | failed)
curl -s -H "$AUTH" "$BASE/datasets/v3/progress/$SNAP"

# 3. download (409 until ready)
curl -s -H "$AUTH" "$BASE/datasets/v3/snapshot/$SNAP?format=json"
```

## Free metadata calls

```bash
# output field schema for one dataset
curl -s -H "$AUTH" "$BASE/datasets/gd_lu702nij2f790tmv9h/metadata"

# recent snapshots (recover a lost snapshot_id)
curl -s -H "$AUTH" "$BASE/datasets/v3/snapshots?dataset_id=gd_lu702nij2f790tmv9h"

# enumerate a dataset's discover modes — deliberately bogus value, free 400
curl -s -X POST "$BASE/datasets/v3/trigger?dataset_id=gd_m45m1u911dsa4274pi&type=discover_new&discover_by=__probe__" \
  -H "$AUTH" -H "$CT" -d '[{"url":"x"}]'
# -> Incorrect discovery collector id Available types: category, keyword, shop
```

The last one is how `smoke_test.py` detects collector drift, and how the
input schemas in this file were derived: POST an input missing its
required keys and the `validation_error` body names the required fields
while the echoed `line` shows the optional ones.
