# NOTES — garden-room-ads run (without_skill)

Run date: 2026-09-22. Working dir: `/home/user/demandEngine2`.
`keyword-insights` skill was **not** used or read, per the run constraints.

## Total spend

| Provider | Calls | Cost |
|---|---|---|
| DataForSEO (Google Ads Keywords Data) | 4 | **$0.360** |
| DataForSEO (Google Ads Transparency) | 1 | **$0.002** |
| **DataForSEO total** | **5** | **$0.362** (budget was $0.40) |
| WebSearch (FX rate lookup) | 1 | $0 |
| Bright Data | 0 | $0 |

Creative downloads (24 PNGs) were free — served from the cached ads_search result,
no additional API call.

## Tools / skills used

- **`dataforseo-keywords`** skill → `scripts/keywords.py` (`locations`, `for-keywords`,
  `search-volume`, `ad-traffic`)
- **`dataforseo-ads-transparency`** skill → `scripts/ads.py` (`ads`, `--download-creatives`)
- **`WebSearch`** — one free query for the 21 Sep 2026 USD/GBP rate (0.747), needed
  because the DataForSEO Google Ads endpoints return prices in USD, not GBP
- **`Read`** on the downloaded creative PNGs to read competitor ad copy (the API
  returns no copy text — `title` is the advertiser name)
- **`Bash`** + ad-hoc Python (stdlib `csv`/`json`) for all local analysis;
  no analysis was paid for twice

## Commands run, in order

All keyword calls used `--location-code 2826` (United Kingdom) and
`--language-code en`. Defaults are US/en, so this flag was set on every call —
without it the numbers would have been silently wrong.

**0. Location lookup — free**
```
keywords.py locations --contains "United Kingdom"        # -> 2826
```

**1. Dry run before paying — free**
```
keywords.py for-keywords <10 seeds> --location-code 2826 --dry-run
```
Confirmed "not cached — 1 billable request" before committing.

**2. Discovery — $0.09**
```
keywords.py for-keywords \
  "garden room" "garden office" "garden studio" "garden building" "summer house" \
  "log cabin" "outdoor office" "garden annexe" "garden pod" "insulated garden room" \
  --location-code 2826 --language-code en --sort-by search_volume \
  --csv ideas.csv --raw ideas_raw.json --limit 0
```
Returned **3,424 keywords / 2,339,150 searches per month**. `--raw` banked the
full 12-month monthly-search history, which is where the seasonality chart in the
report came from — no second call needed for the trend.

**3. Gap-filling — $0.09**
```
keywords.py search-volume <146 hand-picked keywords from list.txt> \
  --location-code 2826 --language-code en --sort-by search_volume \
  --csv priced.csv --raw priced_raw.json --limit 0
```
Why: bucketing step 2's output showed the "research/planning" intent cluster
returned **zero rows** — Google's expansion off product seeds never surfaces
planning-permission or cost-research phrasing. One `search-volume` call prices up
to 1,000 keywords for the same price as one, so the list also covered county
modifiers, spec/feature terms, competitor brands and substitute purchases
(loft/garage/extension). 125 of 146 came back with volume.

**4. Forecast — high intent — $0.09**
```
keywords.py ad-traffic <24 buyer-intent terms> \
  --bid 8 --match exact --date-interval next_month --location-code 2826
# -> 455.92 clicks, avg CPC $4.29, cost $1,957.55/mo
```

**5. Forecast — broad head terms — $0.09**
```
keywords.py ad-traffic <12 category head terms> \
  --bid 8 --match broad --date-interval next_month --location-code 2826
# -> 11,098.07 clicks, avg CPC $4.07, cost $45,221.59/mo
```
Same $8 bid on both so the two shapes are directly comparable. This pair is the
core of the "where does the money go" answer.

**6. Competitor ads — $0.002**
```
ads.py ads --target greenretreats.co.uk --depth 40 --location-code 2826
ads.py ads --target greenretreats.co.uk --depth 40 --download-creatives ./creatives   # free, cached
```
40 live creatives; longest-running search ad live since 2022-02-15 (1,675 days).
Read 4 of the 24 rendered PNGs to extract actual headline/description copy and
the "£9,485 inc. VAT" price anchor.

**7. FX — free**
```
WebSearch "USD to GBP exchange rate September 2026"    # -> 1 USD = 0.747 GBP (21 Sep 2026)
```

## Cost-control decisions

- Ran `--dry-run` before the first paid call to confirm billable status.
- Used `--raw` on every paid keyword call so the monthly trend, annotations and
  full result set were banked — the seasonality analysis cost $0 as a result.
- Chose `search-volume` (1 call, 146 keywords) over a second `for-keywords`
  expansion for the gap-fill: same price, exact terms, no noise.
- Used Ads Transparency at default `--depth 40` (1 billable page at $0.002)
  rather than 120 (3 pages) — 40 creatives was ample.
- Did all segmentation, intent bucketing, seasonality, currency conversion and
  budget arithmetic locally in Python against the saved CSV/JSON. Zero repeat calls.
- Stopped purchasing at $0.362 with the question answered rather than spending
  the remaining $0.038.

## Artefacts

Report: `garden-rooms-google-ads-uk.md` (this directory).

Raw data left in the session scratchpad (not copied here, as only the report and
these notes were requested):
`/tmp/claude-0/-home-user-demandEngine2/22b84561-1390-57d0-b24c-341deee32baf/scratchpad/gr/`
— `ideas.csv` + `ideas_raw.json`, `priced.csv` + `priced_raw.json`,
`fc_intent.json`, `fc_broad.json`, `ads_gr.json`, `creatives/` (24 PNGs + index.csv),
and the analysis scripts `an.py`–`an5.py`, `season.py`, `final.py`.

Note: DataForSEO responses are cached on disk keyed by full request, so re-running
any of the above in a later session is free and returns identical numbers.
