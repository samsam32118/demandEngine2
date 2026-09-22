# Traversal — the graph, the waves, the money

Read before Phase 1 (SEED WAVE); keep open while running waves.

## The graph

Three node kinds, all created by `dc.py` (never by hand), each carrying
provenance in `via`:

| Kind | Id prefix | Identity | Created when | Expanded by |
|---|---|---|---|---|
| domain | `D001…` | registrable host (`plunge.com`) | it appears in a SERP result, an ad library row, or the user seeds it | `for-site` (keywords) + `advertisers`/`ads` (ad library + creatives) |
| keyword | `K001…` | exact phrase, lowercased | `for-site` returns it, or the user's seed words | one SERP query (`--format parsed`) → new domains |
| advertiser | `A001…` | Google advertiser id (`AR…`) | an `advertisers` or `ads` pull returns it | `ads --advertiser-ids` at depth 120 (own creatives, resellers excluded) |

Edges are implicit in provenance: `via: "serp:cold plunge tub"` on a domain is
the edge keyword→domain; `via: "for-site:plunge.com"` on a keyword is the edge
domain→keyword. This is what makes the no-invented-keywords rule *auditable*:
walk any node's `via` chain and you end at the user's verbatim seed.

Node statuses: `pending` (in the frontier), `expanded` (traversed),
`skipped` (cleaner ruled it junk/out-of-scope — the reason goes in `--note`).
`sightings` counts how many independent pulls surfaced the node — a domain
seen in four SERPs outranks one seen in one.

## Wave lifecycle

A wave is one breadth-first ring of the graph. Always the same six steps —
size, collect, read creatives (OCR), reduce, clean, then correct-and-decide
(rule on the open conjectures with `dc.py conjecture judge` before choosing the
next frontier, so a refutation can redirect the remaining budget; details in
SKILL.md). Waves are tracked by `dc.py wave open` / `wave close` so the
notebook, the ledger, and the graph all agree on what happened when.

**BFS, not DFS.** Expand the ring, then look at everything together, then pick
the next ring. Never chase one interesting domain three hops deep while the
rest of the frontier starves — depth comes at DEEPEN, after coverage.

## Frontier scoring

The cleaner proposes; the orchestrator disposes. Rank candidates within kind:

- **Domains**: sightings × SERP prominence (best position), plus a bonus if
  the domain also appears as an advertiser (it *pays* for this traffic —
  strongest capture evidence). Skip: hosts that can't be `for-site`d usefully
  (google.com, youtube.com, wikipedia.org, reddit.com, amazon.com, facebook,
  pinterest, quora) — but **record them in `domains.csv` as
  aggregator/media**: who captures the SERP is capture evidence even when the
  host isn't worth expanding.
- **Keywords**: spend_proxy (search_volume × cpc) is the default sort — it
  finds where the money is. That sort is itself a conjecture ("money marks the
  important demand") and it is structurally blind to the unpriced quadrant this
  skill most wants, so deliberately carry 1–2 high-volume/low-CPC terms per
  wave against it (the cleaner flags these as `latent-probe`). The quota is
  error correction, not garnish: a wave with no latent probe spent itself
  confirming the ranking function (`references/error-correction.md`, Rule 3). Brand terms and pure navigational terms
  (`plunge login`) are tagged but not SERP-expanded — their SERPs return only
  the brand itself.
- **Advertisers**: approx_ads_count; expanded only at DEEPEN unless one
  dominates the wave's creatives.

Dedupe is by identity (domain string, keyword string, advertiser id) —
`dc.py reduce-receipts` merges duplicate candidates into the existing node and
bumps `sightings`.

## Budget math

```
deepen_reserve = 0.15 × cap
wave_budget    = max($0.75, 0.35 × (cap − spent − deepen_reserve))
```

Unit economics for filling a wave (from `references/instruments.md`):

| Expansion | Calls | Est. cost |
|---|---|---|
| domain, full | `for-site` ($0.05–0.10) + `advertisers` ($0.002) + `ads --target --depth 120` ($0.006) + creative downloads (free) | ≈ $0.07–0.11 |
| domain, ads-only (aggregator that advertises) | `advertisers` + `ads` | ≈ $0.008 |
| keyword | 1 SERP query | ≈ $0.003–0.01 (+1 of 100/day) |
| advertiser (DEEPEN) | `ads --advertiser-ids --depth 120` | ≈ $0.006 |
| long-tail pricing (DEEPEN) | `search-volume` ≤1000 kw | ≈ $0.05–0.10 per batch |

A typical $5 run: seed wave ≈ $0.04, three waves ≈ $1.00–1.60 each, deepen
≈ $0.75–1.00. If the frontier can't absorb a wave budget, shrink the wave and
move the surplus to DEEPEN — never leave it unspent.

**Log spend from receipts, not vibes.** Every DataForSEO response prints
`meta.cost`; the SERP price is estimated (~$0.005). Collectors copy the real
number into their receipts; `reduce-receipts` sums receipts into the ledger.
Cache hits (`from_cache: true` / `_from_cache: true`) cost nothing and are
recorded in the receipt with `cached: true` so they're visible but unbilled.

## Caps and rate limits

- **BrightData 100/day**, shared across all `brightdata-*` skills. Tracked in
  `state.json.serp_daily` by `reduce-receipts`; check `dc.py status` before
  sizing a wave's keyword expansions. Exhausted → keyword expansion pauses
  until tomorrow; domain and advertiser expansion don't need SERP and
  continue.
- **DataForSEO keywords 12 req/min.** At most 8 concurrent collectors carrying
  keyword calls, one keyword call each per minute. Ads-transparency is
  effectively unlimited (2000/min).
- **`ads` depth**: 120 max live (3 billable pages). Use 120 by default — this
  skill wants the fuller library, and the marginal page costs $0.002.

## Clean CSV schemas — the cleaner's contract

`clean/` is owned by the cleaner; `eda_charts.py` and `build_pdf.py` consume
these files by exact column name. Append, dedupe on the key column, never
rename columns mid-run.

- `domains.csv` — key `domain`:
  `domain, type, discovered_via, first_wave, serp_appearances, best_position, is_advertiser, notes`
  (`type` ∈ competitor | aggregator | media | tool | unknown)
- `keywords.csv` — key `keyword`:
  `keyword, source, wave, search_volume, cpc, competition, competition_index, low_top_of_page_bid, high_top_of_page_bid, spend_proxy, intent_markers, demand_class, monthly_trend`
  (`source` = `user-seed` | `for-site:DOMAIN` ; `spend_proxy` = search_volume × cpc;
  `intent_markers` = `;`-joined subset of buy/best/price/near-me/how-to/diy/emergency/brand/none;
  `demand_class` ∈ direct | indirect | latent | urgent | unclear — provisional
  until the analyst confirms; `monthly_trend` copied from the raw pull's
  `monthly_trend` cell, `2025-01=1000;2025-02=1100;…` — collectors always pass
  `--monthly`, and this column feeds the seasonality chart)
- `advertisers.csv` — key `advertiser_id`:
  `advertiser_id, title, domain, verified, approx_ads_count, discovered_via`
- `ads.csv` — key `creative_id`:
  `creative_id, advertiser_id, advertiser_title, format, first_shown, last_shown, days_running, active, copy_kind, url, png_path`
- `ad_copy.csv` — key `creative_id`:
  `creative_id, advertiser_title, headline, description, cta, other_text, extraction, ocr_conf`
  (`headline`/`description` verbatim from the PNG; `ILLEGIBLE` when unreadable
  — never paraphrased. `extraction` = `ocr:tesseract` | `ocr:rapidocr` |
  `ocr:<engine>:<reason>` for a flagged read | `haiku` when a transcriber read
  it; `ocr_conf` = mean character confidence 0–100, empty for transcriber
  rows. On conflict a `haiku` row supersedes an `ocr:*` row — the transcriber
  only ever ran because OCR flagged that creative.)
- `serp_results.csv` — key (`query`, `position`):
  `query, wave, position, title, url, domain, snippet, is_ad`
  (`is_ad` true for rows lifted from the markdown-format ad blocks)

## Resumability

Everything needed to resume lives on disk. After context loss: `dc.py status`
(budget, wave, caps), `dc.py conjecture list --all` (what the run believed, what
the data already killed — recover this before deciding anything, or the resumed
run will re-form expectations the earlier waves already refuted),
`dc.py frontier` (what's next), tail `notebook.md` (what the last decision was), `ls receipts/` (an unreduced receipt means a wave
stopped mid-reduce — reduce it first). Raw pulls are cached by the instruments
themselves, so accidentally re-running a banked command costs nothing and
returns `from_cache: true`.
