# Instruments — the lab bench

Read this before Phase 2 (PROBE) and keep it open through Phase 4
(EXPERIMENT). Every instrument here is another skill in this repo; commands
run from the **repo root**. Read an instrument's own SKILL.md before first use
in a session — it carries flags, gotchas, and cost details this summary
compresses.

**Iron rules across all instruments:**

1. **Bank everything you paid for.** Always pass the instrument's `--csv` /
   `--raw` / snapshot flags and save under the experiment's `data/` dir. A
   re-pull of data you failed to save is pure waste.
2. **Log every billable call**: `maze.py spend --usd <est> --calls 1 --note
   "<what and why>"` right after it returns. Cache hits (flagged
   `from_cache`/`_from_cache`) are free — don't log them as spend.
3. **Dry-run before big pulls** where supported (`--dry-run` on all DataForSEO
   ops) — it shows the exact request and whether it's cached, for free.
4. **Cap every discovery.** BrightData discovery modes bill per returned row;
   `--limit-per-input` is your seatbelt. Estimate max spend before running.
5. **Geo deliberately.** Default US/en everywhere unless intake said
   otherwise; record the geo next to every number you write down.
6. **Instruments embody theories.** Each one reads the world through an
   interpretive chain (search volume ≈ buying intent; sustained ads ≈
   acquisition that pays for itself; reviews ≈ the paying user's voice). The traps listed per
   instrument below are where those chains break. Before any fired kill
   criterion becomes a REFUTED verdict, check the relevant trap: instrument
   blindness is INCONCLUSIVE (Phase 5), never refutation.

## Availability check (INTAKE, free)

Judgment first — `judge.py` needs it, and finding out later wastes the budget:

```bash
python3 .claude/skills/demand-forecasting/scripts/jev.py check
```

It reports which variable supplied the key (`TYPESAFE_API_KEY`, else
`TYPESAFEAI_API_KEY`, else `.env`) plus a one-way fingerprint, never the key
itself, and makes one round-trip to confirm the endpoint answers. Offline
means every `judge.py` stage is unavailable: you read the rows yourself, and
the report says which judgments were unaudited.

Then the paid instruments:

```bash
# Which instrument families are online?
python3 - <<'EOF'
import os
d = bool(os.environ.get("DATA_FOR_SEO_LOGIN") and os.environ.get("DATA_FOR_SEO_PASSWORD"))
b = bool(os.environ.get("BRIGHTDATA_API_TOKEN"))
print(f"DataForSEO (search/appstore/ads-transparency): {'ONLINE' if d else 'OFFLINE'}")
print(f"BrightData (serp/tiktok/crunchbase/pitchbook/linkedin/zoominfo): {'ONLINE' if b else 'OFFLINE'}")
print("Apple Ad Repository: ONLINE (no key needed; EU-only data)")
print("YouTube transcripts: check yt-dlp →", end=" ")
import shutil; print("ONLINE" if shutil.which("yt-dlp") else "OFFLINE (pip install yt-dlp)")
EOF
```

Wire-level verification if needed: each DataForSEO skill has
`scripts/smoke_test.py --dry-run` (free); BrightData skills have free
metadata-only `smoke_test.py`. Record the result in the mission brief.

## Signal families → instruments

| Family | Instruments | What it measures |
|---|---|---|
| **Search demand** | dataforseo-keywords | People actively looking; auction price of intent (CPC) |
| **Marketplace demand** | dataforseo-appstore | People installing/paying; incumbent strength; review velocity |
| **Voice of customer** | appstore reviews, tiktok comments, youtube-transcript | Unmet needs, WTP evidence, wedge ideas (feeds other families' nodes) |
| **Social attention** | brightdata-tiktok | Organic channel potential; content-CAC arbitrage |
| **Competitor & capital** | dataforseo-ads-transparency, brightdata-serp, apple-ads, brightdata-crunchbase, brightdata-pitchbook | Sustained ads and what they say (best explained by working unit economics — P5 names the rivals), funding flowing in, competitor census |
| **B2B demand & sizing** | brightdata-linkedin, brightdata-zoominfo | Salaries paid for the pain; market head-count/firmographics |
| **Direct probe** | email-guesser, email-verify, resend | Real outreach smoke test — **gated, see bottom** |

Jev is not a signal family. It reads what the instruments above return; it
never supplies evidence of its own, and a claim whose only support is a Jev
answer is not triangulated. See `references/jev-contract.md`.

Voice-of-customer rides along with marketplace/social pulls; for
triangulation counting, the five independent families are: search,
marketplace, social, competitor-capital, hiring.

## dataforseo-keywords — search demand & intent pricing

The workhorse. ~$0.05–0.10 **per call regardless of batch size** → batching is
everything. Cache = free repeats. 12 req/min limit.

| Op | Use in this loop | Batching lever |
|---|---|---|
| `for-site` | **The cluster source** — harvest the keywords a competitor already monetizes (Phase 2 seeding, Phase 4 teardown) | 1 domain/call, ~2000 rows with volumes/CPCs attached — pick the 1–3 most-on-point competitors |
| `search-volume` | Price every node's assigned cluster (Phase 2) and every card's cluster (Phase 4) | **1000 keywords / call — pool ALL nodes into one call** |
| `for-keywords` | Grounded fallback when a maze corner has no competitor to reverse — expands *real* seed terms through Google's co-search data | 20 seeds/call; seed with broad heads, niche seeds return nothing |
| `ad-traffic` | True CPC forecast for a shortlisted cluster (truer than planner CPC) — Phase 4 for finalists only | 1000 kw/call but returns ONE aggregate row — one call per finalist cluster |

**The footprint traversal — how clusters get built.** You are a strong judge
of keywords and a weak generator of them: terms written from imagination miss
the vocabulary buyers actually type, and pricing invented terms measures your
guesswork, not the market. So harvest first, then select:

1. **Website → keywords.** `for-site` the 1–3 competitors closest to the node
   (census from Phase 1's SERP calls, listicles, app results). What comes back
   is the vocabulary they *monetize* — someone already paid to learn these
   terms convert.
2. **Keywords → websites.** SERP the highest-signal harvested terms
   (`--format parsed`): the domains that rank and the domains that advertise
   are competitors the census missed.
3. **Websites → more keywords.** `for-site` the best new domain; also lift
   category language from long-running ad creatives
   (dataforseo-ads-transparency `--download-creatives` — copy a competitor
   has paid to serve for a year is vocabulary with a profit motive behind it).
4. Repeat until a hop stops surfacing new clusters (usually 2–3 hops), then
   **select** — the part you're good at: assign terms to nodes, keep the
   commercial-intent subset, dedupe, strip navigational/brand terms.

Your own formulations are allowed only to fill holes the harvest left, each
labeled `guessed` in the notes. The label matters at JUDGE: zero volume on a
harvested cluster is evidence about demand; zero volume on a guessed cluster
is evidence about your guess (INCONCLUSIVE, not REFUTED — re-harvest before
ruling).

```bash
# Phase 2 seed: what does the incumbent actually rank/bid for? (volumes included)
python3 .claude/skills/dataforseo-keywords/scripts/keywords.py for-site \
    "getfreed.ai" --sort-by search_volume \
    --csv research/demand/<slug>/experiments/E001-probe/data/freed-footprint.csv

# Phase 2 price: one call prices every node's assigned cluster. Tag terms per node.
python3 .claude/skills/dataforseo-keywords/scripts/keywords.py search-volume \
    "therapy notes software" "soap note generator" "ai notes for therapists" \
    "sales call summary crm" "field service voice notes" ... \
    --monthly --sort-by search_volume \
    --csv research/demand/<slug>/experiments/E001-probe/data/all-clusters.csv

# Phase 4 finalist: true auction price at the ceiling
python3 .claude/skills/dataforseo-keywords/scripts/keywords.py ad-traffic \
    "therapy notes software" "ai therapy notes" --bid 999 --match exact
```

Extract per cluster: total volume, volume-weighted median CPC, competition
index, 12-month trend direction (`--monthly`). Traps: `search-volume` merges
near-duplicate terms (submit separately only when it matters); planner CPC on
tiny-volume terms is noisy — trust `ad-traffic` for finalists.

## dataforseo-appstore — marketplace demand & voice of customer

Fractions of a cent per task call; `listings` is the ~$0.10 outlier — use only
for DB-style filtering. Task ops queue ~15–40s (feels synchronous).

| Op | Use in this loop |
|---|---|
| `search` | Who ranks for the node's store terms; count competitors, ratings, review counts (Phase 2) |
| `reviews --sort-by most_recent` | **Highest-signal call in the repo**: incumbents' recent 1–2★ reviews = unmet-need map + wedge ideas + WTP evidence (Phase 4) |
| `info` | Competitor teardown: price/IAP, update cadence, `similar_apps` adjacency (Phase 4) |
| `list --collection top_grossing_ios` | Category-level "people pay money here" check |

```bash
python3 .claude/skills/dataforseo-appstore/scripts/appstore.py search "therapy notes" \
    --depth 100 --format table
python3 .claude/skills/dataforseo-appstore/scripts/appstore.py reviews <app_id> \
    --depth 100 --sort-by most_recent \
    --csv research/demand/<slug>/experiments/E00X-*/data/<app>-reviews.csv
```

Extract: competitor count and rating distribution for the node's terms; from
reviews — complaint taxonomy (bugs / pricing anger / missing feature X),
review *velocity* (dates on recent page ≈ install momentum), and "paying but
angry" quotes (retention + willingness-to-pay evidence, and a conversion
wedge). Trap: App Store ≈ B2C/
prosumer lens; a B2B node scoring zero here is normal, not refuting.

## brightdata-serp — competitor census & SERP-gap detection

1 billable call per query against the shared BrightData 100/day cap; cached
repeats free. `--format parsed` for structured top-10, default markdown for
reading ads/features.

Use for: enumerating competitors ("best <wedge> for <who>"); the
**keywords → websites hop** of the footprint traversal (the domains that rank
or advertise on a harvested term are the next `for-site` targets); **SERP-gap
probe** — commercial-intent query returning weak/generic results and few ads =
mispriced corridor; resolving URLs for other instruments (pricing pages,
LinkedIn/Crunchbase/TikTok/ZoomInfo targets); pricing-page discovery
("<competitor> pricing").

```bash
python3 .claude/skills/brightdata-serp/scripts/search.py \
    "ai note taker for therapists" --format parsed --num 10
```

Extract: # of dedicated products in top 10 vs. listicles/forums (dedicated <3
= gap); ad presence on the query; competitor list to feed `for-site`, app
lookups, crunchbase. Trap: one SERP snapshot ≠ "sustained advertiser" — ads
seen here are a weak version of the ad-library signal
(dataforseo-ads-transparency, apple-ads); don't count a single sighting as
family evidence on its own.

## dataforseo-ads-transparency — what competitors' ads actually are (any country)

Google's Ads Transparency library, scriptable — the loop's primary
**sustained-advertiser detector** and its window into what competitors *pay
to say*. Same DataForSEO credentials as keywords/appstore. `advertisers` is
$0.002 flat; `ads` is $0.002 per 40 creatives live (`--queued` ⅓ price);
rendered-creative downloads are free (Google CDN); cached repeats free;
`--dry-run` previews any call for free.

| Op | Use in this loop |
|---|---|
| `ads --target <domain>` | The P5 sustainer check: a domain's whole ad library with derived `days_running`/`active` per creative, plus a summary (format mix, active count, `advertisers_by_creatives`) |
| `ads --advertiser-ids <ID…>` | Same, scoped to one company's accounts when `--target` contamination matters (≤25 IDs) |
| `advertisers "<brand>"` | Resolve a brand to advertiser IDs + per-market `approx_ads_count` scale proxy |
| `ads … --download-creatives DIR` | Free rendered PNGs → the actual headlines/descriptions (P11 copy & vocabulary harvest) |

```bash
# P5: is anyone sustaining spend here? Sort by days_running, read the summary.
python3 .claude/skills/dataforseo-ads-transparency/scripts/ads.py ads \
    --target getfreed.ai --format table \
    --csv research/demand/<slug>/experiments/E00X-*/data/freed-ads.csv

# P11: read what their proven ads actually say (downloads are free)
python3 .claude/skills/dataforseo-ads-transparency/scripts/ads.py ads \
    --target getfreed.ai \
    --download-creatives research/demand/<slug>/experiments/E00X-*/data/freed-creatives
```

Extract: creatives with `days_running` ≥ 90 in the node's segment (sustainers
— advertisers cut losers fast, so a year-old creative is a proven winner);
brand-term vs category-term split (brand-defense ads run forever on
pre-existing intent — only category ads demonstrate paid acquisition
working); format mix (text-heavy = search-intent buyer, video-heavy = funding
awareness); copy themes and vocabulary from the PNGs (feeds the footprint
traversal and the WEDGE axis).

Traps: `title` is the advertiser's *name*, never the headline — the copy
lives only in the rendered creatives (`copy` column says which rows render);
`--target` returns everyone Google associates with the domain *including
agencies and resellers* — read `advertisers_by_creatives` in the summary
before attributing anything to the brand; `advertisers` matches names and
domains, not categories ("crm software" returns nothing useful — map a market
by running `ads --target` once per known competitor instead); location
matters and coverage is country-level only (no cities); don't trust
`--platform` (returns identical sets — use `--ad-format`); absence in one
location's library is weak evidence — try the domain instead of the brand
name, or another `--location-name`, before concluding "no ads".

## apple-ads — EU App-Store sustainer lens (free API)

No credentials needed. Data = Apple-delivered App Store ads in the EU, 7-day
delay, presets LAST_90_DAYS/180/YEAR. The EU/App-Store complement to
dataforseo-ads-transparency (which reads Google surfaces in any country): an
app continuously advertising a segment for 90–365 days is *best explained* by
its economics working — but it is an
inference, so P5's rival check applies (a freshly-funded sustainer may be
buying growth at a loss; cross-check funding stage via P6).

Workflow (see the skill's SKILL.md for curl details): entity search by
app/developer name → list ads with RSQL (`datePreset==LAST_YEAR`) → variations
for creatives/messaging.

Extract: which competitors sustain ads; how long; which countries; ad
*messaging* (their tested positioning = free copywriting research). Traps:
EU-only (note the geo gap for US theses in threats-to-validity); covers
Apple-delivered App Store ads only — absence here proves nothing about
Google/Meta spend (pair with SERP ad sightings).

## brightdata-tiktok — social attention & organic-CAC arbitrage

Pay-per-record (~$0.001–0.0015). Discovery needs `--limit-per-input`
(default 25); comments bill **per comment** — always `--num-of-comments 20`.

Use for: topic attention (`discover_posts.py --keyword "<pain phrase>"` →
view/engagement distribution); creator saturation (few dedicated creators +
high views = organic arbitrage); comment mining on top videos
(voice-of-customer: "what app is this", "I need this for my clinic" = demand
leaking through content); Shop data when physical/commerce-adjacent.

```bash
cd .claude/skills/brightdata-tiktok/scripts && python lookup_comments.py \
    --url "https://www.tiktok.com/@.../video/..." --num-of-comments 20
```

Extract: median/p90 views on topic content; # of dedicated creators; comment
themes and product-seeking comments per 1k views. Trap: attention is ladder
rung 5 — it feeds content-CAC math, never validates alone.

## brightdata-crunchbase / brightdata-pitchbook — capital flow

Pay-per-record; lookups cheap, discoveries capped. Use in Phase 4 for
finalists: who got funded to attack this node in the last 24 months, how much,
which stage. Recent seed/A money = investors recently diligenced demand here
(corroboration only — capital never validates alone, P6) AND future CAC
inflation; a graveyard of dead funded companies = corridor hazard worth a
notebook entry (why did they die — demand or execution?).

```bash
cd .claude/skills/brightdata-crunchbase/scripts && python discover_companies.py \
    --keyword "ai therapy notes" --limit-per-input 25
```

## brightdata-linkedin — the salary signal (B2B nodes)

Pay-per-record; `discover_jobs.py` is the star: job postings whose
descriptions contain the pain = **companies already paying salaries for the
job your product does** (ladder rung 2 — stronger than search).

```bash
cd .claude/skills/brightdata-linkedin/scripts && python discover_jobs.py \
    --keyword "clinical documentation specialist" --location "United States" \
    --limit-per-input 25
```

Extract: posting count for pain-adjacent roles, salary ranges (= value anchor:
a $45k/yr documentation role makes a $200/mo tool trivially affordable),
company sizes. Also: `discover_posts.py` for B2B voice-of-customer. Trap:
role keywords need iteration — job titles rarely match pain language; try 2–3
formulations before concluding absence.

## brightdata-zoominfo — market head-count (B2B sizing)

Pay-per-record; resolve company URLs via SERP first. Use sparingly, Phase 4:
firmographic sizing of a vertical (how many US companies of the right size
exist = SAM ceiling for the MODEL math) and incumbent revenue/headcount
teardowns. `/p/` person URLs are unsupported — company pages only.

## youtube-transcript — long-form voice of customer (free)

yt-dlp transcripts of reviews, "day in the life", tutorial and complaint
videos. Free → use liberally when a node needs qualitative depth: how do
practitioners describe the pain in their own words; what do reviewers of
incumbent tools praise/curse. Resolve video URLs via SERP
(`site:youtube.com <incumbent> review`).

## email-guesser / email-verify / resend — direct outreach probe (GATED)

These can run a real smoke test (find 20 target-persona emails, send a
one-line problem-interview ask, measure reply rate). **Contacting real humans
is beyond passive measurement — never do it inside the loop without the user's
explicit, specific authorization** (who, how many, what message). If
authorized, it's pattern P10; replies are ladder-rung-6 words, but reply
*rate* to a cold pain-statement is a decent desperation proxy. Default
posture: propose it in the report as a confirmation test, don't run it.

## Cost cheat-sheet (order probes cheapest-first with this)

| Call | Typical cost |
|---|---|
| youtube-transcript, apple-ads | free |
| appstore `search`/`info`/`reviews` (100/1/100) | ~$0.001–0.003 |
| ads-transparency `advertisers` (flat) / `ads` (per 40 creatives) | ~$0.002 live, $0.0006 queued; creative PNG downloads free |
| brightdata lookup (1 record) | ~$0.001–0.0015 |
| brightdata discovery (25 rows) | ~$0.03–0.04 |
| tiktok comments (20) | ~$0.02–0.03 |
| serp query | ~$0.003–0.01 (and 1 of 100/day) |
| dataforseo-keywords any op | ~$0.05–0.10 (batch to 1000!) |
| appstore `listings` | ~$0.10 (avoid unless filtering) |
| jev judgment (any `judge.py` stage) | ~$0.0001–0.002 — ledgered separately, never against the instrument budget |

A full loop for one idea typically lands at **$0.50–$2.00** when batched
properly. If your plan estimates above the remaining budget, cut scope at
HYPOTHESIZE (fewer cards), not at measurement quality (unkillable cards).
