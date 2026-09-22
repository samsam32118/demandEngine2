---
name: dataforseo-ads-transparency
description: See the actual Google ads your competitors are running — every creative in their public ad library, including the real ad copy (headline, description, display URL) via downloadable rendered ad images, plus format, run dates, and which advertiser accounts a brand advertises under — from DataForSEO's Google Ads Transparency API (ads_advertisers + ads_search). Use this whenever the user wants competitor advertising intel: "what ads is <company> running", "show me <brand>'s Google ads", "who's advertising for <keyword>", "pull <competitor>'s ad library", "what creatives are my competitors using", "is <company> running YouTube/video ads", "how long has this ad been running", "what's <competitor>'s Google Ads strategy", "find advertisers in <niche>", "ad transparency", "ads library", "advertiser ID", or any request to ground ad-copy, creative, or competitive-positioning decisions in the ads competitors are actually paying to run. Trigger even when the user doesn't say "DataForSEO" or "transparency" — any question about what ads a company/domain runs on Google, YouTube, Shopping, Play or Maps belongs here. This is Google Ads Transparency creative data — distinct from the sibling `dataforseo-keywords` skill (search volume, CPC, and what keywords cost) and from `apple-ads` (Apple's EU App Store ad repository); reach for those when the question is about keyword demand/pricing or Apple ads instead. Prefer this over web search whenever the user wants real ad creatives, advertiser accounts, or ad run-dates rather than descriptions of them. Two things to know before drawing conclusions: reading the ad copy takes `--download-creatives` (the API's `title` field is the advertiser's name, not the headline), and `--target <domain>` returns every advertiser tied to that domain including agencies and resellers, so pull by `--advertiser-ids` when you mean one specific company. Opinionated defaults (override when the task calls for it): `ads --target <domain>` is the fastest route to "what are they running" and needs no ID lookup; `advertisers "<brand>"` when you need the advertiser IDs — note it matches advertiser names and domains, not category terms, so feed it brands ("salesforce") not topics ("crm software"), and map a market by running `ads --target` once per known competitor; `ads --advertiser-for "<brand>"` when a domain won't resolve; sort creatives by `days_running` — an ad Google has served for years is a proven winner, and that is the single highest-signal column in the output.
---

# dataforseo-ads-transparency

Live **Google Ads Transparency** data from **DataForSEO's SERP API** — the same
public ad library Google publishes at `adstransparency.google.com`, but
scriptable and joined into rows you can sort. Two endpoints answer two
questions, one CLI (`scripts/ads.py`):

| Operation | The question it answers | Billing (live) | Billing (`--queued`) |
|---|---|---|---|
| `advertisers NAME` | **Who** runs Google ads under this brand name — and what are their advertiser IDs? | $0.002 flat | $0.0006 flat |
| `ads --target / --advertiser-ids` | **What** are they actually running — every creative, its format, and its run dates | $0.002 per 40 creatives | $0.0006 per 40 |

Stdlib-only Python — no `.venv`, no dependencies to install.

## Prerequisites

Credentials come from the environment (already set in this workspace):

- `DATA_FOR_SEO_LOGIN`
- `DATA_FOR_SEO_PASSWORD`

The same API credentials as `dataforseo-keywords` and `dataforseo-appstore`,
from https://app.dataforseo.com/api-access (auth is HTTP Basic). If unset, the
script falls back to a `.env` in the working directory, then exits with a clear
message. Never hardcode them.

## The one thing to internalize: advertiser IDs are the join key

Google's transparency library is keyed by **advertiser account**, not by
company. `advertisers` finds the accounts; `ads` turns an account into
creatives. Three ways in, cheapest first:

```bash
# 1. You know the domain — one call, no lookup needed. Start here.
python3 .claude/skills/dataforseo-ads-transparency/scripts/ads.py ads --target hubspot.com

# 2. You want the accounts themselves — IDs, ad counts, which entities a brand
#    advertises under. Pass a NAME, not a category (see the caveat below).
python3 .claude/skills/dataforseo-ads-transparency/scripts/ads.py advertisers "hubspot" --format table

# 3. Domain didn't resolve, or the brand advertises under a different domain —
#    let the CLI resolve the name for you (TWO billable calls).
python3 .claude/skills/dataforseo-ads-transparency/scripts/ads.py ads --advertiser-for "hubspot" --max-advertisers 3
```

**Why `advertisers` output looks the way it does.** The API returns three item
shapes, and only two carry an ID you can use. Big brands come back as an
`ads_multi_account_advertiser` — a group with a title and a combined ad count
but **no advertiser_id of its own**; the real IDs sit in a nested `advertisers`
array. Reading only the top level of that item leaves you holding a name and
nothing to look up. This CLI lifts every member account into its own row
(`kind: account_of_group`) carrying the parent's title, so **every row that can
be looked up has an `advertiser_id` in it**. Rows with `kind: domain` are
domains Google associates with the term — no ID, but they feed `--target`.

`--format ids` prints bare IDs, one per line, for piping:

```bash
IDS=$(python3 .../ads.py advertisers "hubspot" --format ids --sort-by ads --limit 3)
python3 .../ads.py ads --advertiser-ids $IDS --format table
```

## Cost model — read before running

Each call is **one billable request**. The account balance is small and shared —
treat every call as real money:

- **`advertisers` is flat** — the same price whatever it returns.
- **`ads` bills per 40 creatives.** `--depth 120` is 3 billable pages, not one.
  Default is 40; max is **120 live**, **700 queued**.
- **Live (default) vs `--queued`.** Live returns in ~2–6s at $0.002. `--queued`
  uses the Standard task queue at $0.0006 (~1/3) but takes ~30s+ (guaranteed
  within 45 min). Live is the right default for interactive research — the
  difference is a seventh of a cent, and the chained `advertisers`→`ads`
  workflow would otherwise cost you a minute of waiting. Reach for `--queued`
  when you're batching many pulls and don't need them back now.
  `--priority high` (queued only) is $0.0012, ~1 min.
- **Preview with `--dry-run`** before paying — prints the exact request, a cost
  estimate, and whether the answer is already cached (free). No call made.
- **Caching is automatic.** Every completed result is cached on disk keyed by
  the request, so re-running an identical query is free and flagged
  `cached (free)`. Live and queued share one cache entry (same data either
  way). Pass `--no-cache` to force fresh.
- **Keep everything you paid for** with `--raw PATH` (complete API result,
  including preview image/video URLs) and `--csv PATH` (full row set, never
  capped by `--limit`).
- **Rate limits are generous** (2000 calls/min); polling a queued task is free.

If a call returns `40200 Payment Required` / `40210 Insufficient Funds`, the
balance has run out — that's an account issue to fix at
https://app.dataforseo.com, not a skill bug; don't retry in a loop.

## Operations

Run from the repo root. Each prints to stdout; `--csv PATH` also writes the
full result set. Add `--dry-run` to any billable op to preview it for free.

### Who advertises under a brand name

```bash
python3 .claude/skills/dataforseo-ads-transparency/scripts/ads.py \
    advertisers "salesforce" --format table --sort-by ads
```

Returns advertiser accounts with `advertiser_id`, `title`, `location` (the
country the account is registered in), `verified` (Google confirmed the
advertiser's identity), and `approx_ads_count`, plus associated domains.

> **`approx_ads_count` is per-market and rounded — never compare it across
> locations.** It counts ads in the library *for the location you queried*, so
> the same account (`AR16735076323512287233`) reports 10,000+ from the US and
> 17 from the UK. Round figures like 10,000 / 2,000 / 200 are Google's ceilings,
> not counts. It's a scale proxy *within one market*, and it is not spend.
`--sort-by ads` puts the biggest libraries first; the default `rank` keeps
Google's own relevance order.

> **This is a name/domain lookup, not a market search — and confusing the two
> is the easiest way to get a wrong answer.** The keyword is matched against
> advertiser *names* and domains, exactly like the search box on
> adstransparency.google.com. It does **not** find everyone bidding on a topic.
> Verified behaviour: `"salesforce"` returns Salesforce's account group;
> `"crm software"` returns one unrelated domain and **zero** advertiser IDs;
> `"crm"` returns small firms with "CRM" in their company name (Auto CRM LLC,
> Boosted CRM) and **not** Salesforce or HubSpot. So feed it brands, not
> categories.
>
> To map a *market*, get the competitor list first — from
> `dataforseo-keywords` (who ranks/bids for the terms), `brightdata-serp`, or
> the user — then run `ads --target <domain>` once per competitor and compare
> the libraries. That's also cheaper than guessing keywords here.

### What creatives they're running

```bash
python3 .claude/skills/dataforseo-ads-transparency/scripts/ads.py \
    ads --target hubspot.com --depth 120 --format table \
    --csv research/data/ads/hubspot-creatives.csv
```

One row per creative: `advertiser_id`, `creative_id`, `title`, `format`
(text/image/video), `copy` (see below), `url` (the live ad on Google's
transparency site — open it
to see the actual creative), `first_shown`, `last_shown`, plus three fields
this CLI derives:

- **`days_running`** — `last_shown - first_shown`. The highest-signal column in
  the output. Advertisers cut losers fast, so a creative Google has served for
  years is one the competitor has proven works. Sort by it and read the top.
- **`days_since_shown`** and **`active`** — whether it's still live.
  `active` is true when `last_shown` is within 7 days (`--active-days N` to
  change it). Google's feed lags a day or two, so a small window avoids calling
  yesterday's running ads "stopped".

Table and JSON output also print a **summary**: creative count, format mix,
`advertisers_by_creatives` (read this one — see the warning below), how many
are still active, the longest-running creative, and the date range.

`--target` accepts a bare domain or a full URL (`https://www.nike.com/en/shoes`
is trimmed to `nike.com`).

> **`--target <domain>` is not "this company's ads."** It returns every
> advertiser Google associates with that domain, including resellers,
> affiliates and media agencies — and their ads can outrank the brand's own.
> Measured: of 120 creatives on `hubspot.com` only 79 were HubSpot's (the rest
> agencies bidding around the brand); on `salesforce.com` the top-ranked video
> creatives belong to Vobile, a third party, so a naive read concludes
> "Salesforce runs no video" when they run plenty. Always check
> `advertisers_by_creatives` in the summary, and when the question is about one
> company specifically, resolve its accounts with `advertisers` and pull by
> `--advertiser-ids`. Use `--target` for "who is advertising around this
> domain", `--advertiser-ids` for "what is this company running".

### Getting the actual ad copy

**The API returns no headline or description text.** `title` is the
*advertiser's name* ("Nike, Inc."), not the ad. This trips people up because
reading competitor copy is the most common reason to pull an ad library at all.

The copy is still recoverable: Google renders most text ads to a PNG, and
`--download-creatives` fetches them. Reading those images is how you get the
headline, description and display URL.

```bash
python3 .../ads.py ads --target nike.com --depth 120 \
    --download-creatives research/data/ads/nike-creatives
# → 33 rendered ad PNGs → .../nike-creatives  (7 had no PNG render)
# then open the .png files to read what each ad actually says
```

Downloads are **free** — they hit Google's CDN, not the paid API, so this costs
nothing on top of the pull you already made. Files are named
`<creative_id>.png` beside an `index.csv` joining each image to its advertiser,
format and run dates.

The `copy` column tells you in advance what you'll get:

| `copy` | Meaning |
|---|---|
| `png` | A rendered image of the ad — `--download-creatives` gets you the text. Most text ads (33 of 35 in a Nike sample). |
| `js` | Preview is a JavaScript bundle needing a browser (all image and video ads, a few text). Open the row's `url` instead. |
| *(empty)* | No preview asset at all. |

So: **text ads → readable copy; image and video ads → open the `url` by hand.**
Since long-running text ads are usually what you want for copy research, this
covers the main case. Plan a video-creative review as manual work.

### Narrowing the pull

```bash
# Only video creatives (YouTube-style), UK library, launched this year
python3 .../ads.py ads --target hubspot.com --ad-format video \
    --location-name "United Kingdom" --since 2026-01-01 --format table
```

- `--ad-format text|image|video` — **works, and narrows properly.** The fastest
  way to answer "are they running video?" is `--ad-format video` and read the
  count.
- `--since` / `--until` (`YYYY-MM-DD`, earliest `2018-05-31`) — restrict to ads
  shown in a window. Good for "what did they launch this quarter".
- `--platform google_search|youtube|google_shopping|…` — **do not trust this
  one.** In testing it came back with the identical creative set as an
  unfiltered call (same `creative_id`s in the same order), so a
  platform-filtered count is not evidence about that surface. Use
  `--ad-format` instead, and if you need per-surface truth, open the `url` of
  individual creatives. It's kept because the API accepts it and the behaviour
  may change.
- `--advertiser-ids` accepts **at most 25** IDs. Note that results are ranked
  across all of them, so one huge account can fill the whole page — pull big
  accounts separately if you need coverage of the small ones.

### Detached retrieval (only relevant with `--queued`)

```bash
# Queue without waiting — prints a task id:
python3 .../ads.py ads --target stripe.com --async
# ...later, fetch it (endpoint auto-detected from the local ledger):
python3 .../ads.py get 08111729-2075-0066-0000-ef47916a64a6 --format table
# see what's finished and uncollected (checks both endpoints):
python3 .../ads.py ready
```

`get` polls until the task is ready (`--max-wait 0` for a single ready/not
check). Pass `--type advertisers|ads` if the ID isn't in the local ledger.
Tasks stay retrievable for ~30 days.

### Find a location code (free)

```bash
python3 .../ads.py locations --contains "United Kingdom"
```

## Location

All ops default to **`location_code 2840` (United States)**. Override with
`--location-code` / `--location-name` / `--location-coordinate`. Coverage is
**country-level only** (214 countries) — there are no city or region codes
here, unlike the keywords API. Location genuinely changes results: an
advertiser's library differs by the market the ads ran in, so pull each market
you care about rather than assuming US is global.

> **You cannot target a city, and `--location-coordinate` will not get you
> one.** Coordinates are resolved up to the containing country before the query
> runs: Oslo's `59.9139,10.7522` comes back with `check_url ...?region=NO` and
> results identical to `--location-code 2578` (Norway). So "ads in Oslo" is
> answerable only as "ads in Norway" — say so rather than implying city
> precision the data doesn't have.

## Output formats

- `--format json` (default) — `{meta, items}`. `meta` carries `cost`,
  `from_cache`, `check_url` (the equivalent page on Google's own transparency
  site), and the derived `summary`. Best when you'll reason over the data.
- `--format table` — markdown table plus the summary block.
- `--format csv` — CSV to stdout.
- `--format ids` (`advertisers` only) — bare advertiser IDs for chaining.
- `--csv PATH` — write the **full** result set (ignoring `--limit`) to a file.
- `--raw PATH` — dump the **complete** raw API result (preview image and video
  URLs, nested group structure — nothing dropped) so a paid call is never
  repeated.
- `--limit N` — cap rows printed to stdout (default 100; `0` = all). Never caps
  the `--csv` / `--raw` files.

## Reading the results

- **Long-running creatives are the answer to "what works for them".** Sort by
  `days_running`, then `--download-creatives` and read the top few. A
  three-year-old ad is a tested, winning message; a two-week-old one is an
  experiment. One caveat worth passing on: a brand's oldest *search* ads are
  often brand-defense ads that run forever because the intent was already
  there, not because the copy is good. Separate brand-term ads from
  category-term ads before copying anyone's tier.
- **Check `advertisers_by_creatives` before concluding anything about a
  company.** If the brand isn't the top entry, you're reading someone else's
  ads (see the `--target` warning above).
- **`format_mix` reveals channel strategy.** A library that's 90% text is a
  search-intent buyer; heavy video means they're funding awareness on YouTube.
- **`approx_ads_count` on `advertisers` is a scale proxy.** An account running
  10,000 ads and one running 12 are not the same competitor, even if both rank
  for the term.
- **Multiple accounts per brand is normal** — regional entities, agencies
  buying on their behalf (you'll see media agencies show up under a brand's
  domain), and legacy accounts. The agency rows are a finding, not noise.
- **`verified: false`** means Google hasn't confirmed that advertiser's
  identity — worth noting when the question is about impersonation or
  low-quality competitors.
- **Absence is weak evidence.** An empty result means nothing in *this*
  location's public library matched — not that the company runs no ads. Check
  another `--location-name`, or the domain instead of the brand name, before
  concluding they don't advertise. An empty `advertisers` result most often
  means the keyword was a category phrase rather than a name (see above), so
  retry with `ads --target <domain>` before reporting "no ads found".
- **Where to save:** drop meaningful CSVs under `research/data/ads/` (create
  it) so they sit beside the keyword and App Store exports, and note in
  `marketing/memory.md` what you pulled and why. Don't overwrite raw data — add.

## Smoke test

```bash
python3 .claude/skills/dataforseo-ads-transparency/scripts/smoke_test.py            # ~4 calls (~$0.007)
python3 .claude/skills/dataforseo-ads-transparency/scripts/smoke_test.py --dry-run  # free: checks wiring only
```

Live mode hits both live endpoints, runs one queued task through post+poll,
reads the free locations lookup, and asserts the three properties this skill
depends on — all of which would fail silently if Google changed the response:
advertiser lookups yield usable IDs (including nested ones), ad results carry
the timestamps `days_running` is built from, and a creative's PNG render still
downloads (the only route to ad copy). `--dry-run` verifies auth and
request-building without spending. Run after any credential or `client.py`
change.

## Design notes

- **Why live is the default here, unlike `dataforseo-appstore`.** App Store
  pulls are one-shot; this skill's natural workflow is a chain
  (`advertisers` → `ads`), so queueing would mean waiting twice. At $0.002 a
  call the saving from queuing is $0.0014 — not worth a minute of latency in
  interactive research. `--queued` is there for batch work.
- **Why the flattener lifts nested advertiser accounts.** The
  `ads_multi_account_advertiser` shape is the single easiest way to get a wrong
  answer from this API: it looks like a normal result row but carries no ID, so
  a naive read reports "found Nike" and then can't fetch a single ad. Emitting
  one row per member account makes the useful thing — an ID you can chain —
  present on every row that has one.
- **Why derive `days_running` / `active` in the CLI.** Every consumer of this
  data asks the same two questions of a raw timestamp pair, and each would pick
  a slightly different definition of "still running". Computing them once means
  conclusions are comparable across pulls.
- **Why `--download-creatives` exists at all.** The most common reason to pull
  an ad library is to read the competitor's copy, and the API returns none —
  just an advertiser name in a field called `title`, which reads like a
  headline and isn't one. The rendered PNG is the only path to the actual
  words, it's free, and without a flag for it every user would have to discover
  `preview_image` in the raw JSON and write their own downloader. The `copy`
  column exists so you know which rows will yield text before you bother.
- **Why the summary names advertisers.** `--target` silently mixes in agencies
  and resellers whose ads can outrank the brand's own, which is the failure
  mode most likely to produce a confidently wrong answer. Putting
  `advertisers_by_creatives` in every summary makes the contamination visible
  on the first pull instead of after a second one.
- **Why the summary block.** A 120-row creative dump is not an answer. Format
  mix, active count and the longest-running ad are the shape of the library,
  and they're what a competitive read actually turns on.
- **Why the `--platform` warning is in the tool and not just the docs.** The
  flag is accepted by the API and looks like it works, which is exactly what
  makes it dangerous — the failure mode is a confident wrong conclusion about a
  competitor's YouTube spend. The caveat rides along in `--help` too.
- **Why cache by request, ignoring priority/tag.** An advertiser's library
  changes by the day, not the second, so paying twice for the same query in a
  session is waste. Priority and tag don't change the *data*, so they're
  excluded from the cache key.
- **Why stdlib-only.** No `.venv` means no install step when the repo is cloned
  fresh — same as the sibling DataForSEO skills.

## Files

```
.claude/skills/dataforseo-ads-transparency/
├── SKILL.md            — this file
├── scripts/
│   ├── client.py       — Basic auth, POST/GET, retries, status-code-aware task polling
│   ├── ads.py          — CLI: advertisers / ads / get / ready / locations
│   └── smoke_test.py   — one call per endpoint (or --dry-run for free)
├── evals/evals.json    — test prompts for the skill-creator eval loop
└── .cache/             — on-disk response cache + async task ledger (git-ignored)
```
