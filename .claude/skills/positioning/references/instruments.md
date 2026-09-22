# Instruments — the exact commands, what they cost, and what they lie about

Read before the first paid call. Scouts get their commands copied from here
verbatim. All paths are from the repo root; `<run>` is
`research/positioning/<slug>`.

**Four iron rules:**

1. **Bank everything you paid for.** Always `--save` / `--csv` / `--raw` into
   `<run>/raw/`. Re-pulling data you failed to keep is pure waste, and the
   appendix needs the rows.
2. **Receipt every call.** Copy `meta.cost` (or the SERP estimate) into the
   scout's receipt as soon as the command returns. Cache hits (`_from_cache` /
   `from_cache` true) are free — receipt them with `"cached": true` and cost 0.
3. **`--dry-run` when unsure.** Every DataForSEO op takes it, free: it prints
   the exact request, whether it is cached, and the price.
4. **Same geo everywhere.** Pass the run's `--location-code` / `--language-code`
   on every call once intake set a non-US geo. Volumes swing 100× by country,
   and a study that mixes geos is comparing nothing to nothing.

Budget shape for a $6 study: roughly $0.30 on site fetches, $0.15 on SERP,
$4.50 on keywords (the workhorse and the biggest line item), $0.30 on ads,
and the rest held back for Phase 6's refutation buy.

---

## brightdata-web-unlocker — the marketing pages

The primary instrument of this skill: positioning is an argument about what
companies *say*, and this is what reads it. ~$0.001–0.005 per page and **1 of
the shared BrightData 100/day cap**. Cache hits are free and do not count.

```bash
python3 .claude/skills/brightdata-web-unlocker/scripts/unlock.py \
    "https://acme.com/pricing" \
    --save <run>/raw/site/acme-com-pricing.html
```

Then always parse it with the extractor rather than reading the HTML yourself:

```bash
python3 .claude/skills/positioning/scripts/extract_site.py profile \
    --dir <run>/raw/site --domain acme.com --out <run>/extract
```

**Which pages, in priority order.** `/` (the self-framing), `/pricing` (the
shape of the offer and its tiers — often the clearest statement of who it is
for), `/features` or `/product` (the attribute list), `/customers` or
`/case-studies` (segment evidence), `/compare` or `/vs/*` (the company's own
alternative set, free of charge), `/about`. Four to seven pages for the product
itself; three for each alternative.

**Naming matters.** The extractor's `profile` mode globs on the domain, so
bank as `<domain-with-dashes>-<page>.html` — `acme-com-pricing.html`. Write a
sidecar `.url` file next to it when the real URL is not recoverable from the
name; the extractor reads it.

**Traps.** Single-page apps return a shell with no copy — the extractor will
report near-zero claims, and that is your signal to fetch the marketing
subpaths directly rather than assuming the product is vague. Cookie-wall pages
return the banner as the whole body; if `word_count` is under ~120, refetch
with `--country us` or treat the page as unread and say so. Some sites put the
real pricing behind JS, so `price_points` comes back empty while `pricing`
tiers are found — that is normal, not a failure.

---

## brightdata-serp — the alternative set and the review sites

~$0.003–0.01 per query, **1 of the shared 100/day cap**.

```bash
# the alternative set — the highest-value queries in the whole study
python3 .claude/skills/brightdata-serp/scripts/search.py \
    "acme alternatives" --format parsed --num 10 > <run>/raw/serp/acme-alternatives.json

# who is buying ads against the brand — do this one as markdown, which keeps
# the ad blocks that --format parsed silently drops
python3 .claude/skills/brightdata-serp/scripts/search.py \
    "acme" --format markdown > <run>/raw/serp/acme-ads.md

# the status quo lanes, which no competitor list will ever give you
python3 .claude/skills/brightdata-serp/scripts/search.py \
    "hvac dispatch spreadsheet template" --format parsed --num 10 > ...
```

**Query budget: 6–10 for a $6 study.** Spend them on: `<brand> alternatives`,
`<brand> vs`, `best <their own category phrase>`, one DIY query, one
hire-a-person query, `<brand> reviews`, and `site:g2.com <brand>`.

**Traps.** `--format parsed` is unreliable: on some zones it returns an empty
`results` list *and* an empty `body`, with a `note` saying `brd_json=1 not
honored by this zone`. There is nothing to salvage locally when that happens —
in a live run it hit 2 of 5 parsed calls — so the query has to be re-run as
markdown, and that is a second paid call. Budget for it, or use
`--format markdown --stdout markdown` from the start and pull the domains out
with a regex; markdown has not failed. Keep `parsed` for the queries where you
want positions and snippets as structured fields.

Listicles dominate `<brand> alternatives` and are sources, not alternatives:
read the brands *out* of them, do not add the listicle domain as a competitor.
The brand's own domain will rank first for its own name; drop it.

---

## dataforseo-keywords — vocabulary, demand, and the market frames

**~$0.05–0.10 per call regardless of batch size**, so batching is everything.
12 requests/minute account-wide — never run more than 8 scouts carrying keyword
calls. Cache hits are free. Every response prints `meta.cost`.

```bash
# harvest: every keyword Google considers relevant to a real site, priced
python3 .claude/skills/dataforseo-keywords/scripts/keywords.py for-site \
    "acme.com" --sort-by search_volume \
    --csv <run>/raw/keywords/acme-com.csv

# the one call that pays for itself: price every candidate frame, every
# vocabulary pair and every alternative's name together, up to 1000 terms
python3 .claude/skills/dataforseo-keywords/scripts/keywords.py search-volume \
    "hvac dispatch software" "field service management" "crew scheduling software" \
    "servicetitan" "housecall pro" "hvac dispatch spreadsheet" ... \
    --csv <run>/raw/keywords/priced.csv
```

Rows carry `keyword, search_volume, competition, competition_index, cpc,
low_top_of_page_bid, high_top_of_page_bid`.

**Do it in this order.** `for-site` on the product and the two biggest
alternatives first — that harvests real vocabulary with a profit motive behind
it. Then *one* `search-volume` call at the end of Phase 4 carrying everything
you need priced: candidate frames, both halves of every vocabulary pair, and
every alternative's name for the `alternatives_map` sizing. One call, one
price, whether it holds 40 terms or 900.

**Traps.** `search-volume` merges near-duplicates onto one row with combined
volume — fine for sizing, worth a note. Planner CPC on tiny-volume terms is
noisy; do not build an argument on the CPC of a 90-searches-a-month term.
`for-site` returns "keywords Google deems relevant to this site", not a ranking
report — that is still harvested vocabulary at real prices, which is what §3
and §8 need. **Do not use `for-keywords`**: it expands seeds through Google's
co-search graph and re-opens the door to model-shaped queries, which Rule one
exists to close.

---

## dataforseo-ads-transparency — what the alternatives pay to say

`advertisers` is $0.002 flat; `ads` is $0.002 per 40 creatives; rendered
creative downloads are **free**. Effectively no rate limit.

```bash
# who advertises under this brand name — competitors bidding on your name are
# competitors who believe they can take your deals
python3 .claude/skills/dataforseo-ads-transparency/scripts/ads.py \
    advertisers "acme" --format table --csv <run>/raw/ads/acme-advertisers.csv

# an alternative's live ad library, with the creatives that carry the copy
python3 .claude/skills/dataforseo-ads-transparency/scripts/ads.py \
    ads --target servicetitan.com --depth 60 \
    --csv <run>/raw/ads/servicetitan-ads.csv \
    --download-creatives <run>/creatives/servicetitan.com
```

**Why ads outrank marketing pages for §9.** A page can say anything and cost
nothing to leave up. An ad that loses money gets switched off in weeks — so a
creative that has run for months is copy that *pays*, and it is the closest
thing to a controlled experiment anyone in the market has run for you. Read the
long-running ones for `messaging.csv` and mark them `source: ad`.

**Traps.** The API returns no copy text — `title` is the advertiser name. The
words are in the rendered PNGs, which is what `--download-creatives` is for;
open them. `advertisers` matches advertiser *names*, not topics, so
`"crm software"` returns nothing useful — look up each competitor by name.
Resellers and affiliates appear under a brand's name; check the advertiser id
before attributing a claim to the company itself.

---

## dataforseo-appstore — reviews, when the product ships an app

Only relevant if the product has an iOS app. When it does, this is the richest
segment evidence available anywhere, because reviewers describe their own
situation unprompted.

```bash
python3 .claude/skills/dataforseo-appstore/scripts/appstore.py \
    reviews 1234567890 --depth 100 --sort-by most_recent \
    --csv <run>/raw/reviews/app-reviews.csv
```

`--sort-by most_recent` over `most_helpful`: helpful reviews skew old and
positive, and you want what the product is like now.

---

## What to do when an instrument is missing

A missing credential narrows the study; it does not stop it. Say in the report
which evidence was unavailable and what that bounds:

- **No BrightData** — no page fetches and no SERP. You cannot run this study;
  say so rather than producing a positioning from memory.
- **No DataForSEO** — no volumes, no prices. §3's chart and §8's quadrant lose
  their x-axis. Run the rest, drop those two charts, and say in the report that
  the frame recommendation rests on competitive density alone.
- **BrightData daily cap exhausted** — page fetching pauses; keyword and ad work
  continue. Note where the alternative set stopped growing.
