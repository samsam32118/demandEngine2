# NOTES — tools, commands, and cost

Run date: 2026-09-22 · Working dir: `/home/user/demandEngine2`
The `keyword-insights` skill was explicitly excluded from this run and was neither read nor invoked.
Nothing was committed or pushed.

## Cost summary

| Provider | Calls | Cost |
|---|---:|---:|
| DataForSEO — Google Ads Keywords Data API (`dataforseo-keywords`) | 4 | **$0.3600** |
| DataForSEO — Apple App Data API (`dataforseo-appstore`) | 2 | **$0.0042** |
| **DataForSEO total** | **6** | **$0.3642** |
| Bright Data SERP API (`brightdata-serp`) | 2 | not billed to the DataForSEO budget (counts against the shared 100/day Bright Data cap) |

**Budget: $0.40 · Spent: $0.3642 · Headroom left: $0.0358.**
Per-call costs are the `cost` field returned by the API itself, not estimates.

## Billable calls, in order

### 1. Keyword expansion — $0.09
`dataforseo-keywords` → `for-keywords`, 20 broad seeds, US/en, sorted by volume.
Seeds: meal planning, meal prep, meal planner, weekly meal plan, grocery list app, recipe app, meal planning app, family meal planning, meal plan, dinner ideas, meal kit, macro meal plan, diet plan, healthy meal plan, meal prep delivery, recipe organizer, what to cook, meal planning for weight loss, calorie counter app, grocery shopping list.

```
python3 .claude/skills/dataforseo-keywords/scripts/keywords.py for-keywords <20 seeds> \
  --sort-by search_volume --limit 60 --format table --csv $S/ideas.csv --raw $S/ideas_raw.json
```
**Returned:** 24,028 keywords (23,696 with volume), 39,973,030 searches/mo total, each with 12 months of monthly history, CPC, competition index, and top-of-page bids. Banked in full via `--raw` so no re-pull was needed.
Preceded by a free `--dry-run` to confirm the request and that it was billable.

### 2. Four-year history for a curated list — $0.09
`dataforseo-keywords` → `search-volume`, 142 hand-built keywords, `--date-from 2022-09-01` to pull the full 48-month history (the key move — it is what makes the trend claims possible rather than seasonal noise).
List spanned: generic software intent, 30 competitor/incumbent brand names, AI-native entry terms, constraint-driven niches (diabetic, renal, PCOS, FODMAP, bariatric, pregnancy, ADHD, seniors, halal/kosher), retailer-anchored terms, and B2B/professional software terms.

```
mapfile -t KW < $S/terms.txt
python3 .claude/skills/dataforseo-keywords/scripts/keywords.py search-volume "${KW[@]}" \
  --date-from 2022-09-01 --sort-by search_volume --limit 0 --format table \
  --csv $S/curated.csv --raw $S/curated_raw.json
```
**Returned:** 142 rows, 48 months each (2022-09 → 2026-08).

### 3. Traffic forecast, consumer cluster — $0.09
`dataforseo-keywords` → `ad-traffic`, 20 consumer app keywords, exact match, ceiling bid.
```
... ad-traffic <20 consumer terms> --bid 999 --match exact --date-interval next_month \
  --format table --raw $S/adtraffic_consumer.json
```
**Returned:** 311.43 clicks/mo · $9.86 avg CPC · $3,069.23/mo.

### 4. Traffic forecast, B2B cluster — $0.09
Same op, 18 dietitian/nutrition-professional keywords.
**Returned:** 127.16 clicks/mo · $34.19 avg CPC · $4,347.33/mo.

### 5. App Store competitive field — $0.0012
`dataforseo-appstore` → `search "meal planner"`, depth 100.
```
python3 .claude/skills/dataforseo-appstore/scripts/appstore.py search "meal planner" \
  --depth 100 --format table --csv $S/as_mealplanner.csv
```
**Returned:** top 100 ranked US App Store apps with rating, review count, price.

### 6. Voice of customer — $0.003
`dataforseo-appstore` → `reviews` for ReciMe (app id 1593779280, the category leader found in step 5), depth 100, `--sort-by most_recent`.
**Returned:** 100 freshest reviews with rating, title, text, version, date. This was the single highest-signal call of the run — it turned "the market is hard" into "the market's ARPU ceiling is ~$40/yr and the leader is strip-mining goodwill to hit it".

## Non-DataForSEO calls

### 7–8. Bright Data SERP × 2
```
python3 .claude/skills/brightdata-serp/scripts/search.py \
  "meal planning app shut down OR acquired OR sunset 2024 2025 Yummly Whisk Real Plans PlateJoy" \
  --num 20 --format parsed --stdout json
python3 .claude/skills/brightdata-serp/scripts/search.py \
  "meal planning app startup raises seed funding 2025 2026 recipe app venture round" \
  --num 20 --format parsed --stdout json
```
Used to corroborate the shutdown dates the keyword decline had already implied (Yummly 20 Dec 2024; PlateJoy 1 Jul 2025 — confirmed on PlateJoy's own support page; Whisk → Samsung Food) and to find the funding picture (ReciMe $1.5M seed; Season Health $34M Series A / a16z; Meez $11.5M; Tracxn category totals).

## Free local analysis (no API cost)

Four throwaway Python scripts in the scratchpad, run against the banked `--raw` JSON:

| Script | What it produced |
|---|---|
| `analyze.py` | Intent bucketing of all 23,696 keywords; volume-weighted CPC per cluster; highest-CPC terms with volume ≥1,000 |
| `brands.py` | Brand-footprint rollup across 70 competitor names; 12-month seasonality curve for the planning cluster |
| `trend.py` | The core finding — 48-month cluster trends (recent-12-month mean vs earliest-12-month mean) and calendar-year totals |
| `gaps.py` | Head/tail volume concentration; under-contested terms (vol ≥500, competition ≤35, CPC ≥$3); constraint-driven niche sizing; free/template intent share |

Scratchpad (intermediate CSV/JSON, not part of the deliverable):
`/tmp/claude-0/-home-user-demandEngine2/22b84561-1390-57d0-b24c-341deee32baf/scratchpad/mp/`

## Cost-control decisions worth recording

- **One 20-seed expansion instead of several narrow ones.** A call bills the same for 1 seed or 20, so the seeds were chosen to span the whole space (software, kits, diets, recipes, grocery) in a single $0.09 request. That one call produced ~70% of the report's evidence.
- **`--date-from 2022-09-01` on the `search-volume` call.** Same price, 4x the history. Without it, every trend statement would have been seasonality dressed up as growth — and the actual headline finding (a 2025 inflection in "meal planning app") would have been invisible.
- **`--raw` on every paid call**, so all four re-analysis passes were free and nothing was ever re-purchased.
- **Skipped `appstore listings`** (~$0.10 flat, ~24x the cost of `search` for this question) — `search` answered "who ranks for meal planner" for $0.0012.
- **Skipped `for-site`** on competitor domains: the 24,028-keyword expansion already covered the footprint, and the brand-level question was better answered by grep-ing the banked corpus for free.
- **Skipped `dataforseo-ads-transparency`.** Competitor ad creatives would have been interesting but not decision-relevant here — the traffic forecasts had already shown the paid channel is ~440 clicks/month total, so creative strategy is moot. Budget was better spent on 48 months of history.
