---
name: brightdata-tiktok
description: Scrape TikTok via Bright Data's pay-as-you-go Web Scraper API — pull a creator's profile (followers, likes, video count, engagement rates, bio link), a video's full metrics (views, likes, comments, shares, saves, hashtags, sound), the comment thread on any video (text, likes, replies, commenter), or TikTok Shop products (price, discount, units sold, reviews, seller); and discover profiles by search URL, videos by creator/keyword/hashtag/discovery page, and Shop products by keyword/category/seller. Trigger whenever the user says "scrape TikTok", "look up <handle> on TikTok", "get the comments on this TikTok", "find TikTok videos about <topic>", "what's <creator>'s TikTok engagement rate", "pull TikTok posts for #<hashtag>", "TikTok Shop data for <product>", "who's posting about <topic> on TikTok", or otherwise asks for structured TikTok creator, video, comment, or commerce data. Use this instead of web search whenever the user wants real TikTok numbers — even if they don't explicitly say "Bright Data".
---

# brightdata-tiktok

Thin wrapper around Bright Data's **TikTok Web Scraper APIs**
(pay-as-you-go, no minimum spend). Covers four datasets and **all eleven
collectors** Bright Data exposes for them — four URL-lookup paths plus
seven discovery modes:

| Dataset | Dataset ID | What it returns |
|---|---|---|
| Profiles | `gd_l1villgoiiidt09ci` | Creator profile — followers, following, likes, video count, biography, bio link, verification, and the three engagement rates |
| Posts | `gd_lu702nij2f790tmv9h` | Video metrics — plays, likes, comments, shares, saves — plus description, hashtags, sound, duration, and the author block |
| Comments | `gd_lkf2st302ap89utw5k` | One row per comment — text, likes, reply count, commenter identity, optional nested replies |
| Shop | `gd_m45m1u911dsa4274pi` | Product commerce record — price bands, discount, units sold, reviews, variants, seller rating |

Scripts hide the trigger → poll → download loop so callers stay
task-oriented.

## Prerequisites

`BRIGHTDATA_API_TOKEN` must be set on a Bright Data account with the
**TikTok Web Scraper APIs** enabled. Scripts exit with a clear error if
the token is missing.

Verified end-to-end against the live API on 2026-08-04: all four
datasets and all seven discovery collectors are enabled on this account.

## Billing model — read this before running anything

Bright Data bills **per returned record** on the pay-as-you-go plan
(~$0.001–$0.0015 per record, no minimum spend).

- **Lookups** (`lookup_*.py`) bill one record per input URL. Predictable
  and cheap — always prefer this when the user knows the URL.
- **Discoveries** (`discover_*.py`) bill for every row returned, so
  `--limit-per-input` is **required** on all of them.
- **Comments are the cost outlier.** `lookup_comments.py` bills per
  *comment*, not per video — one viral video can return tens of
  thousands of rows. Always cap it with `--num-of-comments`.
- **Snapshot retention is 16 days.** Re-downloading via `get_snapshot.py`
  is free. Don't re-trigger for data you already pulled.
- `describe_fields.py`, `list_snapshots.py`, `smoke_test.py`, and
  `--status-only` on `get_snapshot.py` are free (metadata only).

## Tasks

Run from `scripts/`; each prints one JSON object to stdout.

### Profiles

- **Look up profiles by URL** — `python scripts/lookup_profiles.py --url https://www.tiktok.com/@<handle> [--url ...] [--country US] [--no-wait]`
  Start here. One billable record per URL. This is the only cheap way to
  get `awg_engagement_rate` / `like_engagement_rate` /
  `comment_engagement_rate`.

- **Discover profiles by search URL** — `python scripts/discover_profiles.py --search-url "https://www.tiktok.com/search?q=<query>" --country US --limit-per-input 25 [--no-wait]`
  Build the search on tiktok.com and paste the URL. `--country` is
  **required** by this collector.

### Posts (videos)

- **Look up videos by URL** — `python scripts/lookup_posts.py --url https://www.tiktok.com/@<handle>/video/<id> [--url ...] [--no-wait]`
  One billable record per URL.

- **Discover videos** — `python scripts/discover_posts.py <one mode> --limit-per-input 25 [--no-wait]`
  Three modes, pick exactly one:
  - `--profile-url https://www.tiktok.com/@<handle>` — a creator's recent
    videos. Also takes `--start-date` / `--end-date` (MM-DD-YYYY),
    `--what-to-collect`, `--post-type`, `--sort-by`.
  - `--keyword "<term or #hashtag>"` — topic sweep.
  - `--discovery-url https://www.tiktok.com/discover/<slug>` — a
    discover landing page. Use the `/discover/` shape; `/tag/` URLs come
    back empty (`dead_page`) — reach for `--keyword` for hashtags.

### Comments

- **Scrape comments on videos** — `python scripts/lookup_comments.py --url <video URL> [--url ...] --num-of-comments 50 [--collect-replies] [--no-wait]`
  Input is the **video** URL. Bills per comment — always pass
  `--num-of-comments`. This dataset has no discovery mode.

### TikTok Shop

- **Look up products by URL** — `python scripts/lookup_shop.py --url <product URL> [--url ...] [--no-wait]`
  One billable record per URL.

- **Discover products** — `python scripts/discover_shop.py <one mode> --limit-per-input 25 [--no-wait]`
  Three modes, pick exactly one: `--keyword "<term>"`,
  `--category-url <category page>`, or `--shop-url <seller page>`.

### Shared helpers (all datasets)

- **Re-download a snapshot** — `python scripts/get_snapshot.py --snapshot-id s_xxx [--status-only]`
  Free within the 16-day window. Use this instead of re-triggering.

- **List recent snapshots** — `python scripts/list_snapshots.py [--kind profiles|posts|comments|shop] [--status ready] [--limit 20]`
  Free. Handy if the user lost a snapshot id.

- **Describe the schema** — `python scripts/describe_fields.py --kind profiles|posts|comments|shop [--inputs] [--names-only] [--active-only]`
  Free. `--inputs` prints the request-side schema (which keys each
  collector requires) — check it before hand-rolling a call.

## Guidance

- **Resolve the canonical URL first.** Lookups expect real TikTok URLs:
  `https://www.tiktok.com/@<handle>` for creators,
  `https://www.tiktok.com/@<handle>/video/<id>` for videos. If the user
  gives a brand or a description, resolve it via the brightdata-serp
  skill (`search.py 'site:tiktok.com "<name>"' --format parsed`, one
  paid SERP call) before scraping — cheaper than burning a billable
  record on a wrong URL.
- **Cap discoveries.** If the user says "find TikToks about X" without a
  number, default to `--limit-per-input 25` and tell them you capped it.
  Increase only on explicit request.
- **Cap comments harder.** Default to `--num-of-comments 20` unless
  asked otherwise, and say so. This is the one scraper that can return
  thousands of billable rows from a single input.
- **"Top comments" is already what a cap gives you.** Comments return in
  TikTok's relevance order, so `--num-of-comments 20` captured 90% of
  the true top-20 by likes and 94% of all comment likes in testing. If
  the user needs a *strict* top-N ranking, over-pull ~2× and sort on
  `num_likes` yourself — there is no server-side sort option.
- **Cut videos before you cut comments.** Post records carry
  `comment_count`, so triage which videos are worth a comment pull from
  a cheap posts discovery first. Dropping two videos saves far more than
  trimming per-video comment caps.
- **Chain discovery → lookup.** `discover_posts.py --profile-url` returns
  full post records including `url`, so you rarely need a second
  `lookup_posts.py` pass. Feed those video URLs straight into
  `lookup_comments.py` when the user wants the conversation, not the
  metrics.
- **Set `--country` deliberately.** TikTok results are heavily
  geo-varying; a keyword sweep from US and GB will not match. Record
  which country produced a result set before comparing runs.
- **Default to the full record.** Every script returns the complete row
  when `--fields` is omitted — leave it omitted. Trimming saves nothing
  on the bill (billing is per-record, not per-field) and strips signal
  the caller didn't know they wanted (engagement rates, the
  `discovery_input` provenance key, the denormalised author block). Only
  pass `--fields` on explicit request or under context pressure.
- **For long jobs, use `--no-wait`.** Record the `snapshot_id` in your
  response. Big keyword sweeps can take several minutes.
- **Prefer cached data.** Ask whether the user already has a snapshot_id
  from a recent run — `get_snapshot.py` is free within 16 days.
- **Don't dump raw JSON.** See the output contract below.

## Output contract

For a **profile**, summarise in 4–8 bullets:
- Handle + nickname (+ verified badge if true)
- Followers / following / total likes
- Video count
- Engagement rate (average), noted as a percentage
- Bio (one line) + bio link if present
- Profile URL

For **videos**, use a compact table or bullets per post — description
(truncated), plays, likes, comments, shares, post date, URL — capped at
the top 5–10 when discovering. Lead with whatever metric the user's
question is about.

For **comments**, summarise the *themes* first (2–4 bullets on what
people are actually saying), then quote 3–5 representative comments with
their like counts. Comment dumps are near-useless unsynthesised — this
is voice-of-customer data, treat it that way.

For **Shop products**, use a table: title, final price (+ currency),
discount %, units sold, review count, seller rating, URL.

Always include the `snapshot_id` at the end so the user can re-fetch for
free. **Never dump the full JSON unless the user explicitly asks for
"raw data".**

## References

- `references/curls.md` — verified curl for all 11 collectors + the input-key table
- `references/fields.md` — grouped output fields per dataset (convenience; not authoritative)
- `references/LIMITS.md` — billing, retention, auth, geo, and the input-key traps

## Smoke test

```bash
python scripts/smoke_test.py
```

Free, metadata-only. Asserts the metadata call works for all four TikTok
datasets **and** re-verifies that the seven discovery modes this skill
claims still match what the API advertises (it probes with a bogus
`discover_by`, which is a free 400). Prints `SKIP: BRIGHTDATA_API_TOKEN
not set` if the token is missing, so unauthenticated CI doesn't fail.
