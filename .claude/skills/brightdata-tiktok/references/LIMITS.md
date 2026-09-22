# brightdata-tiktok — limits and caveats

Things that will bite you if you don't know them up front.

## 1. This is the pay-as-you-go Web Scraper API, not the Datasets marketplace

Bright Data sells TikTok data in two SKUs. This skill points at the
**Web Scraper API** (pay-as-you-go, billed per record, **no minimum
spend**). It does **not** use the Datasets marketplace snapshot, which
carries a large minimum order — that's avoided on purpose.

If you ever see "$X minimum order" language, you're on the wrong product
page.

- Billed per **returned** record, not per input. A discovery with
  `limit_per_input=100` and two inputs can bill up to 200 records.

## 2. Four dataset ids, eleven collectors, one API shape

```
gd_l1villgoiiidt09ci   # TikTok - Profiles
gd_lu702nij2f790tmv9h  # TikTok - Posts
gd_lkf2st302ap89utw5k  # TikTok - Comments
gd_m45m1u911dsa4274pi  # TikTok Shop
```

All four share the `/datasets/v3/trigger|progress|snapshot` contract.
Only three things differ: the `dataset_id`, the input body shape, and
the returned field schema.

Between them they expose **eleven collectors** — four URL-collection
paths plus seven discovery modes. `DISCOVER_MODES` in `client.py` is the
registry, and `smoke_test.py` re-verifies it against the API on every
run.

## 3. Input keys are mode-specific, and two of them are traps

`describe_fields.py --kind <kind> --inputs` prints the full table. The
two that will cost you a debugging round:

- **Posts / discovery-page (`discover_by=url`) wants a capital `URL`.**
  Lowercase `url` is explicitly rejected:
  `["url","This input should not contain a url field"],["URL","Required field"]`
  It's the only collector in the set that does this.
- **Shop / seller (`discover_by=shop`) wants plain `url`, not `shop_url`.**
  The opposite instinct to the one above.

Two more worth knowing:
- Posts / keyword uses **`search_keyword`**; Shop / keyword uses
  **`keyword`**. Same concept, different key, different dataset.
- Profiles / search **requires `country`**, while Profiles / URL-lookup
  treats it as optional.

The scripts handle all of this. This section is for when you hand-roll
curl or extend the skill.

## 4. Lookup vs discover modes

| Mode | Billing | When to use |
|------|---------|-------------|
| Profile lookup by URL | 1 record per input | You know the @handle |
| Profile discovery by search_url | 1 per returned profile | You want accounts matching a search |
| Post lookup by URL | 1 record per input | You have video URLs |
| Post discovery by profile_url | 1 per returned post | Recent videos from a creator |
| Post discovery by keyword | 1 per returned post | Topic/hashtag sweep |
| Post discovery by discovery URL | 1 per returned post | A `/discover/<slug>` landing page |
| Comments by video URL | **1 per returned COMMENT** | Voice-of-customer mining |
| Shop lookup by URL | 1 record per input | You have product URLs |
| Shop discovery (keyword/category/shop) | 1 per returned product | Catalogue/competitor sweeps |

**`--limit-per-input` is the main cost guard for every discover mode**,
and the scripts make it required there.

## 5. Comments is the one that can surprise you on cost

Every other scraper bills roughly one record per input you hand it.
Comments bills **per comment returned from a single video URL**. One
viral TikTok can carry tens of thousands.

Always pass `--num-of-comments` (and/or `--limit-per-input`) unless the
user has explicitly asked for the full comment set and knows the shape
of the bill.

**`--num-of-comments` is a real, standalone cap** — verified 2026-08-04
by requesting 30 comments on a 166-comment video with no
`limit_per_input` set: exactly 30 rows came back. You do not need both
guards; either one works.

`--collect-replies` returns replies **nested in each row's `replies`
array**, not as extra rows — so it does not multiply the record count
the way an earlier draft of this file claimed. Caveat from the same
test: with the flag set, `replies` came back empty (`[]`) on a comment
whose `num_replies` was 1, so the flag's effect is **unverified**. Don't
promise a caller threaded replies until you've confirmed it populates
for their video.

## 5b. Comment ordering — relevance, not likes, not date

Comments come back in **TikTok's own relevance order** — the order you'd
see scrolling the app. Measured on a 30-comment pull (2026-08-04):

- Not sorted by likes: a 32-like comment sat at position 6, below
  comments with 23 and 13 likes.
- Not sorted by date either, in either direction.

There is **no sort/order/offset input** on this collector, so you cannot
ask for "top by likes" server-side.

In practice the default order is a good proxy for "top comments":

| Cap | Share of the true top-N by likes it captures |
|---|---|
| 5 | 4/5 (80%) |
| 10 | 8/10 (80%) |
| 20 | 18/20 (90%) |

Capping at 20 also captured **94% of all comment likes** in the 30-row
sample. So `--num-of-comments 20` is a legitimate "top 20 most relevant"
pull.

If a caller needs a *strict* top-N by likes, over-pull ~2× and sort on
`num_likes` client-side — that is the only way to get it, and it costs
2× the records.

## 6. Body format for /trigger

The POST body is a **bare JSON array** of input dicts, not a
`{"input": [...]}` wrapper:

```json
[{"url": "https://www.tiktok.com/@nike"}]
```

This matches the linkedin and crunchbase skills and differs from the
pitchbook `/scrape` endpoint, which uses the `{"input": [...]}` shape.
If you copy curl from one skill to another, mind the wrapper.

## 7. Snapshot retention: 16 days

Every trigger produces a `snapshot_id`. Bright Data keeps the data for
**16 days**. Within that window `get_snapshot.py` re-downloads for free.
After 16 days the snapshot is gone and you pay again to re-scrape.

If you need durable storage, dump the JSON to disk right after a
successful run.

## 8. Async flow and polling cadence

```
POST /datasets/v3/trigger   →  {snapshot_id}
GET  /datasets/v3/progress/{id}   # starting | running | ready | failed
GET  /datasets/v3/snapshot/{id}   # 409 until ready
```

- Trigger is fast, scraping is not. Observed on this account
  (2026-08-04): a single-profile lookup was ready in **~35s**; a
  3-record profile discovery in **~40s**. Large keyword sweeps run
  several minutes.
- No public QPS limit, but we still poll every 10s and retry 429/5xx
  with exponential backoff. Don't drop `--poll-interval` below ~5s.
- For big jobs use `--no-wait`, record the snapshot id, and come back
  with `get_snapshot.py --snapshot-id …`.

## 9. Field schemas drift

`references/fields.md` is a grouped convenience list, not the source of
truth. Always prefer:

```bash
python scripts/describe_fields.py --kind profiles
python scripts/describe_fields.py --kind posts
python scripts/describe_fields.py --kind comments
python scripts/describe_fields.py --kind shop
```

which calls `/datasets/{dataset_id}/metadata` live. Free.

## 10. Auth

One Bearer token from the Bright Data dashboard, exported as
`BRIGHTDATA_API_TOKEN`. Scripts exit code 2 with a clear stderr message
if it's missing.

The token needs the **TikTok Web Scraper APIs** enabled — a separate
toggle from the LinkedIn, Crunchbase, ZoomInfo and PitchBook scrapers the
sibling skills use. Each **discovery collector** is toggled separately
inside the TikTok group too. When one is off, `/datasets/v3/trigger`
returns HTTP 400 `"Incorrect discovery collector id Available types:"`
and `client.py` appends a hint pointing at the dashboard.

Verified on this repo's account (2026-08-04): all four datasets and all
seven discovery collectors are enabled.

## 11. Geo and `country`

Most collectors accept a two-letter `country` to pick the proxy exit
location. TikTok results are heavily geo-varying — a keyword sweep from
US and from GB will not return the same videos. Set it deliberately when
the question is market-specific, and record which country produced a
result set before comparing two runs.

`country` is **required** on the profile-search collector.

## 12. Budget classification

This skill shares the **Bright Data** token with `brightdata-serp`,
`brightdata-linkedin`, `brightdata-crunchbase`, `brightdata-zoominfo`
and `brightdata-pitchbook`. There is no separate TikTok tier — a TikTok
scrape and a SERP query draw from the same 100/day pool, and the calling
agent tracks that shared count.

## 13. What this skill does NOT do

- Resolve a vague description ("that running-shoe brand") into a TikTok
  handle or a Shop URL. Use `brightdata-serp` first —
  `search.py 'site:tiktok.com "<name>"'` — then feed the URL here. A
  wrong URL still bills a record.
- Download video files. `video_url` comes back in the post record;
  fetching it is out of scope.
- Access the "Fast API" TikTok SKUs listed on Bright Data's marketing
  page (posts-by-profile/URL/search "Fast API"). Those are separate
  synchronous products and are **not** present as datasets on this
  account — `/datasets/list` returns no TikTok entry with a `fast`
  name. Everything here uses the async snapshot API.
- Run LLM summarization on the result. Scripts emit structured JSON;
  `SKILL.md`'s output contract tells the caller how to narrate it.
