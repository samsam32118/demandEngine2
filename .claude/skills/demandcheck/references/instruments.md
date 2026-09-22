# Instruments — the three data sources

Read before Phase 2; collectors get their commands copied from here. All
commands run from the **repo root**. Each instrument is another skill in this
repo — read its own SKILL.md when something here isn't enough; this card
compresses.

**Iron rules:**

1. **Bank everything you paid for.** Always pass `--csv` / `--raw` /
   `--download-creatives` pointing into the run's `raw/` and `creatives/`
   dirs. A re-pull of data you failed to save is pure waste.
2. **Receipt every call.** Collectors copy `meta.cost` (or the SERP estimate)
   into their receipt right after each command returns. Cache hits
   (`from_cache` / `_from_cache` true) are free — receipt them with
   `"cached": true` and cost 0.
3. **Dry-run when unsure.** Every DataForSEO op takes `--dry-run` (free): it
   prints the exact request, whether it's cached, and the price.
4. **Geo deliberately.** Pass the run's `--location-code` / `--language-code`
   on every DataForSEO call when intake set a non-US geo. Record geo next to
   every number.

## brightdata-serp — what Google shows (keyword → domains)

One mode. ~$0.003–0.01 per query **and 1 of the shared 100/day BrightData
cap**. Cache hits free (`_from_cache: true` in the payload — don't count them).

```bash
# The standard expansion call — structured top-10
python3 .claude/skills/brightdata-serp/scripts/search.py \
    "cold plunge tub" --format parsed --num 10 \
    > research/demandcheck/<slug>/raw/serp/cold-plunge-tub.json

# Once per wave on the highest-value query: the markdown view keeps the ad blocks
python3 .claude/skills/brightdata-serp/scripts/search.py \
    "cold plunge tub" --format markdown \
    > research/demandcheck/<slug>/raw/serp/cold-plunge-tub.md
```

Parsed output: `{"results": [{"title", "url", "snippet", "position"}], ...}`.
Extract per query: every result domain (candidate nodes), positions, and —
from the markdown run — which domains bought ads on the query (`is_ad` rows in
`serp_results.csv`; the strongest capture evidence a SERP can give).

Traps: `--format parsed` can drop ad/shopping blocks — that's why one markdown
call per wave exists. Worse: some Bright Data zones ignore `brd_json=1`
entirely and the parsed call returns an **empty results list** (the payload
carries a `note` about the zone) — when that happens, the collector still
banks the file, and the cleaner builds `serp_results.csv` from the markdown
pull instead; don't re-spend on parsed retries. Shopping-carousel items in the
markdown often have no per-item URLs — a brand seen there without a link is a
`notes` entry, not a domain node. One SERP sighting of an ad is weak; the ad
*library* (below) is the sustained-spend instrument. Only Google is supported.

## dataforseo-keywords — what searches cost and how many (domain → keywords)

The workhorse and the biggest line item: **~$0.05–0.10 per call regardless of
batch size** — batching is everything. 12 req/min account-wide. Cache = free
repeats. Every response prints `meta.cost` — copy it into the receipt.

```bash
# THE harvest call — every keyword a real site monetizes, volumes/CPCs attached
python3 .claude/skills/dataforseo-keywords/scripts/keywords.py for-site \
    "plunge.com" --sort-by search_volume --monthly \
    --csv research/demandcheck/<slug>/raw/keywords/plunge.com.csv

# DEEPEN: page-level footprint of a landing page seen in the SERPs
python3 .claude/skills/dataforseo-keywords/scripts/keywords.py for-site \
    "https://plunge.com/pages/cold-plunge-benefits" --target-type page \
    --csv research/demandcheck/<slug>/raw/keywords/plunge-benefits-page.csv

# DEEPEN: price the entire unpriced long-tail in one call (≤1000 keywords)
python3 .claude/skills/dataforseo-keywords/scripts/keywords.py search-volume \
    "cold plunge tub" "ice bath tub" "cold therapy tub" ... --monthly \
    --csv research/demandcheck/<slug>/raw/keywords/longtail-priced.csv

# DEEPEN: true auction price for the head cluster (one aggregate row)
python3 .claude/skills/dataforseo-keywords/scripts/keywords.py ad-traffic \
    "cold plunge tub" "cold plunge" --bid 999 --match exact
```

Row fields: `keyword, search_volume, competition, competition_index, cpc,
low_top_of_page_bid, high_top_of_page_bid` (+ `monthly_searches` with
`--monthly` — 12-month trend, feeds the seasonality chart). `--csv` writes the
**full** row set even when stdout is truncated by `--limit`.

Traps: `search-volume` merges near-duplicate terms (their combined volume
lands on one row — fine for a survey; note it in methodology). `for-site`
rows are "keywords Google deems relevant to this site", not a ranking report —
still harvested vocabulary with real prices, which is what this skill needs.
Planner CPC on tiny-volume terms is noisy; `ad-traffic` is the truer price for
the head cluster. **Do not use `for-keywords`** in this skill — it expands
seeds through Google's co-search graph, which re-opens the door to
model-shaped queries; the traversal gets its breadth from real websites
instead.

## dataforseo-ads-transparency — what advertisers actually run (domain → money & messaging)

Google's Ads Transparency library. `advertisers` is $0.002 flat; `ads` is
$0.002 per 40 creatives (**use `--depth 120`** = $0.006 — this skill wants the
full library); rendered-creative downloads are **free**. Same credentials as
dataforseo-keywords. Effectively no rate limit (2000/min).

```bash
# Who advertises under this name/domain (advertiser ids + library sizes)
python3 .claude/skills/dataforseo-ads-transparency/scripts/ads.py \
    advertisers "plunge.com" --format table \
    --csv research/demandcheck/<slug>/raw/ads/plunge-advertisers.csv

# The domain's ad library + FREE rendered creatives (the actual ad text)
python3 .claude/skills/dataforseo-ads-transparency/scripts/ads.py \
    ads --target plunge.com --depth 120 \
    --csv research/demandcheck/<slug>/raw/ads/plunge-ads.csv \
    --download-creatives research/demandcheck/<slug>/creatives/plunge.com

# DEEPEN: one company's own creatives, resellers excluded (ids from advertisers.csv)
python3 .claude/skills/dataforseo-ads-transparency/scripts/ads.py \
    ads --advertiser-ids AR01234567890123456789 --depth 120 \
    --csv research/demandcheck/<slug>/raw/ads/AR0123-own.csv \
    --download-creatives research/demandcheck/<slug>/creatives/AR0123
```

Creative rows: `creative_id, advertiser_id, title, format(text|image|video),
first_shown, last_shown, days_running, active, copy, url`. `meta.summary`
carries `format_mix`, `advertisers_by_creatives`, `longest_running`,
`active_now` — bank it (it's in the JSON stdout; keep with `--raw` if needed).

**The ad text is not in the API.** `title` is the advertiser's *name*. The
`copy` column says what you can get: `png` → the free download renders the ad
(headline + description readable — `scripts/ocr_creatives.py` turns these into
`ad_copy.csv` locally, ~7 images/second, no tokens); `js` → image/video ads,
preview needs the row's `url` in a browser (log the url, don't guess the
copy); empty → nothing renders.

Download every PNG you can (`--download-creatives`), then read them in one
command after the wave's collectors finish:

```bash
python3 .claude/skills/demandcheck/scripts/ocr_creatives.py \
    --run research/demandcheck/<slug>
```

It skips creatives already read, so running it each wave is cheap, and it
prints `needs_transcriber` — the count of creatives that need the Haiku
fallback (`agents/transcriber.md`), listed in `raw/ad_copy/ocr-review.json`.

Traps: `--target` returns everyone Google associates with the domain —
*including agencies, resellers, affiliates*. Read `advertisers_by_creatives`
before attributing creatives to the brand; use `--advertiser-ids` when it
matters (DEEPEN does). `advertisers` matches names/domains, never categories —
"cold therapy" returns nothing; feed it brands and domains from the graph.
`approx_ads_count` is per-market and rounded — never compare across locations.
Ignore `--platform` (doesn't narrow); use `--ad-format` if needed. Location
coverage is country-level only.

## What feeds what — the wave in one picture

```
user seed words ──SERP──▶ serp_results.csv ──domains──▶ for-site ──▶ keywords.csv
                                   │                        │
                                   │                   advertisers/ads
                                   ▼                        ▼
                          (markdown run: is_ad)      ads.csv + creatives/*.png
                                                            │
                                                  ocr_creatives.py
                                                   (+ transcriber for
                                                    what it flags)
                                                            ▼
                                                      ad_copy.csv
best harvested keywords ──SERP──▶ new domains ──▶ next wave …
```

## Cost cheat-sheet

| Call | Typical cost |
|---|---|
| creative PNG downloads | free |
| reading those PNGs (local OCR) | free — no tokens, ~7 images/sec |
| ads-transparency `advertisers` | $0.002 flat |
| ads-transparency `ads --depth 120` | $0.006 |
| serp query | ~$0.003–0.01 (and 1 of 100/day) |
| dataforseo-keywords any op | ~$0.05–0.10 flat (batch to 1000) |

A $5 run properly spent lands around: 10–20 SERP queries, 12–20 `for-site`
pulls, every discovered domain's ad library, 1–2 long-tail pricing batches,
one `ad-traffic` anchor.
