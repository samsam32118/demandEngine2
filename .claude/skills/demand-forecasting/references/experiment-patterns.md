# Experiment patterns P1–P11

Read this at Phase 3 (HYPOTHESIZE) when designing cards, and follow it at
Phase 4 (EXPERIMENT). Each pattern is a reusable protocol: what it measures,
what it costs, what it feeds, and example kill criteria to adapt into cards.

Compose cards from 2–4 patterns spanning ≥2 signal families, ordered
**cheapest-killer-first** — the pattern most likely to refute for the least
money runs first, and a fired kill criterion stops the card immediately.
Patterns test the card's *premises* (X1, X2, …): pick each pattern for the
premise it can kill, and write that mapping into the card's threshold table —
a pattern that tests no premise is spend without a question attached.

Every pattern ends the same way: raw data banked to `experiments/E###/data/`,
spend logged via `maze.py spend`, extracted numbers written into `verdict.md`
next to the pre-registered thresholds.

---

## P1 — Search Demand Probe

*Family: search · Cost: $0.05–0.10 (one batched call covers many nodes) ·
Phase 2 and 4*

Sizes and prices a node's keyword cluster: is anyone looking, and what does
the auction charge for that intent?

1. Build the node's cluster by **harvest, not invention** — you are a strong
   judge of buyer vocabulary and a weak generator of it (the footprint
   traversal, instruments.md): `for-site` the nearest competitors, lift
   category language from their long-running ad copy (P11), take SERP
   phrasings. Then select 5–15 terms a *buyer* types, labeling anything you
   had to invent `guessed`. Separate commercial-intent ("therapy notes
   software", "X pricing", "best X for Y") from informational ("how to write
   therapy notes") — both matter (funnel stages) but thresholds apply to the
   commercial subset.
2. One `search-volume` call, `--monthly` for trend, pooled with every other
   node needing pricing. Bank CSV.
3. Extract per node: commercial cluster volume, volume-weighted median CPC,
   competition index, trend direction (rising/flat/falling), head-vs-tail
   shape.

Example kills: commercial cluster < 1,500/mo (B2C) or < 300/mo (B2B) →
demand too thin for the CHANNEL=search node · volume falling >20% YoY *with a
stated driver conjecture* (seasonality checked first — see P9) → decaying
corridor. A volume kill only counts against a **harvested** cluster: zero
volume on a `guessed`-only cluster impeaches the vocabulary, not the demand —
INCONCLUSIVE until you've re-harvested.

A high CPC is **not** a kill on its own. It sets CAC, which `cac.py` prices
and the user judges — a $14 click is fine for a $600/mo product and fatal for
a $9 one, and that's their call, not the loop's. A CPC threshold belongs in a
card only when it tests a stated premise (usually the persistence premise:
"the vertical tail stays unbid"), and then it kills that premise, not the
node's economics.

Traps: don't average CPC across informational terms (drags it down,
flatters CAC); a cluster dominated by one navigational term ("otter ai") is
brand demand for the *incumbent*, not the category.

## P2 — SERP Gap Probe

*Family: competitor-capital · Cost: 1–3 SERP calls · Phase 2 triage or 4*

Detects mispriced corridors: real commercial intent whose results page is
weak — nobody has built the dedicated answer.

1. SERP the node's top 2–3 commercial terms (`--format parsed`, then default
   markdown for one to see ads/features).
2. Count in the top 10: dedicated products vs. listicles/forums/generic
   incumbents stretched off-vertical. Note ad count.

Gap signal (positive): <3 dedicated products, forums/Reddit asking for
recommendations ranking organically, few/no ads on a commercial query.
Example kills: ≥5 well-fit dedicated products with strong brands → crowded ·
incumbent's exact-match landing pages rank 1–3 with 4 ads → priced and
defended.

Trap: a gap with no P1 volume is a mirage — gaps only matter where P1 showed
intent.

## P3 — Review Mining Probe

*Family: marketplace (+ voice-of-customer) · Cost: ~$0.005 per incumbent ·
Phase 4 — the highest-signal-per-cent pattern*

Turns incumbents' recent reviews into an unmet-need map and WTP evidence.

1. `appstore search` the node's store terms → pick top 2–3 incumbents by
   review count.
2. `reviews --depth 100 --sort-by most_recent` per incumbent. Bank CSVs.
3. Build a complaint taxonomy (billing anger / accuracy / missing feature X /
   platform gaps / support). Count, don't vibe: "23 of 100 recent reviews
   complain about per-minute pricing".
4. Note review velocity (timestamps ≈ install momentum) and "paying but
   angry" quotes — people *paying* while complaining are LTV evidence and a
   conversion wedge.

Example validates: ≥15% of recent reviews share one fixable complaint that
your wedge addresses · incumbent rating ≤4.2 with high velocity. Example
kills: incumbents ≥4.6, complaints scattered/trivial → love, hard to displace.

Trap: reviews skew negative-recent after price changes; check whether the
anger is structural or a one-off event (version dates tell you).

## P4 — Social Arbitrage Probe

*Family: social · Cost: ~$0.05–0.10 · Phase 4, for nodes with a content
CHANNEL hypothesis*

Measures whether organic attention is cheap relative to the demand it leaks.

1. `discover_posts.py --keyword "<pain phrase>"` (cap 25). Extract view
   distribution (median, p90), post dates, # distinct creators.
2. For the 2–3 top videos: `lookup_comments.py --num-of-comments 20`. Count
   product-seeking comments ("what app is this", "link??", "I need this for
   my clinic") per video.
3. Saturation check: how many *dedicated* creators own the topic vs. drive-by
   virality.

Arbitrage signal: p90 views > 200k, <5 dedicated creators, product-seeking
comments present → content CAC likely far below paid CAC (feed content-CAC
math in economics.md). Example kills: topic content median <5k views → no
attention to arbitrage · comments are pure entertainment, zero product-seeking
→ attention without intent.

Trap: TikTok geo/FYP variance is huge — same country per run, treat one run
as one sample, not truth.

## P5 — Ad Sustainer Probe

*Family: competitor-capital · Cost: ~$0.002–0.01 (ads-transparency) + free
(apple-ads) + optionally 1–2 SERP · Phase 4 — the "their math works" detector*

Finds competitors whose sustained ad spend is best explained by working unit
economics in the segment. Run dates are directly measurable in the target geo
— sustainer evidence no longer has to be inferred from EU-only data.

1. **Google surfaces, any country (primary):** ads-transparency
   `ads --target <competitor-domain>` per known competitor (from P2/P3), or
   resolve accounts via `advertisers` and pull `--advertiser-ids` when
   precision matters. Sort by `days_running`: a category-term creative served
   ≥90 days is a sustainer. Check `advertisers_by_creatives` first — agencies
   and resellers ride along on `--target` — and split brand-term ads
   (defensive, run forever on pre-existing intent) from category-term ads
   (the ones that demonstrate paid acquisition working) before crediting
   anyone; `--download-creatives` (free) shows which segment the copy
   actually targets.
2. **Apple App Store, EU (complement):** apple-ads entity-search each known
   competitor → list ads `datePreset==LAST_YEAR` across EU countries → note
   continuity (an app with ads across 90/180/365-day presets is a sustainer),
   placements, and ad variations (their tested messaging).
3. Optional: SERP the money terms now vs. your Phase-2 pull — same
   advertisers twice, weeks apart, corroborates.

Validates: ≥1 sustainer in the node's exact segment (not just the broad
category) → someone's CAC < LTV *here*. Kills: zero ads anywhere by anyone
despite P1 volume → either auction is a bargain (check CPC — that's the
arbitrage!) or intent doesn't convert (pair with P3: are people paying at
all?). This fork matters — write which branch the evidence supports.

"Sustainer → their math works" is an inference to the best explanation, so
name the rivals before crediting it: a sustainer burning fresh Series A money
(P6 tells you) may be buying growth at CAC > LTV on purpose; brand campaigns
and agency inertia also keep bad ads alive. A bootstrapped or long-profitable
sustainer is the strong version of this signal; a freshly-funded one is
corroboration at best.

Traps: `--target` mixes in agencies and resellers (read
`advertisers_by_creatives` before attributing); absence in one country's
library ≠ no ads (try the domain instead of the brand name, or another
`--location-name`, before concluding); apple-ads is EU-only and
App-Store-only — a US-only or Google-only advertiser is invisible there.
Presence is strong evidence; absence is weak, everywhere.

## P6 — Capital Flow Probe

*Family: competitor-capital · Cost: ~$0.03–0.05 · Phase 4, finalists*

`discover_companies.py --keyword "<node phrase>" --limit-per-input 25` on
Crunchbase (Pitchbook to cross-check a specific company). Extract: companies
attacking the node, funding recency/stage/amounts, dead-company graveyard.

Validates: fresh seed/A rounds into the corridor (investors diligenced demand
recently). Also warns: heavy recent funding = CAC inflation incoming; a
graveyard = investigate *why* they died before entering. Kills: nothing —
capital is corroborating, never sufficient (VCs are wrong constantly); use it
as the second family only alongside a spend/search family.

## P7 — Hiring Pain Probe

*Family: hiring · Cost: ~$0.03–0.05 per role formulation · Phase 4, B2B
nodes*

`discover_jobs.py --keyword "<role that does the job manually>" --location
"United States" --limit-per-input 25`. Try 2–3 title formulations (job titles
rarely match pain language) before concluding absence.

Extract: posting counts, salary ranges, company size distribution. A salary
range is a **value anchor**: companies paying $45k/yr for manual work your
$200/mo product automates gives the MODEL axis a defensible price — which is
what the repay table in `cac.py --price` needs.

Validates: ≥20 active postings for the manual role in target geo. Kills:
near-zero postings across formulations *and* P1 showed no B2B search →
companies neither hire nor search for this → pain likely not budget-worthy.

## P8 — Price Anchor Probe

*Family: marketplace/competitor · Cost: ~free–$0.02 · Phase 4, required
before any `cac.py` run that shows a repay table*

Grounds the price points in observed prices instead of guesses.

1. `appstore info` per incumbent (price, IAP tiers) and/or SERP "
   <competitor> pricing" → read pricing pages.
2. Record the price *distribution* (floor, mode, ceiling) and the tier
   structure (what's paywalled = what buyers pay for).

Feeds: `--price` (the mode of comparable tiers, plus one tier above and below
so the user can see what pricing power buys), MODEL axis validation, and
price-umbrella detection (all incumbents ≥$X leaves an underprice wedge; all
free/cheap warns the WTP ceiling is low). Kill: every comparable is
free/ad-supported with no paid tier surviving → monetization unproven
anywhere in the corridor.

## P9 — Trend Momentum Probe

*Family: search · Cost: free if P1 used `--monthly` · any phase*

Reads the 12-month trend already banked in P1's CSV. A trend is evidence only
through an explanation of what drives it — extrapolation alone is not a
forecast. Before any trend enters a verdict, write the one-line driver
conjecture and check seasonality (tax, school, holidays) first. With a driver
stated: rising cluster + flat CPC = demand outrunning auction pricing
(mispricing pattern 2 — and the driver tells you how long the window
plausibly stays open). Falling head-term volume with a stated driver =
decaying corridor even if absolute volume still clears thresholds. An
unexplained trend, rising or falling, is a question for the notebook, not a
number for a verdict.

## P10 — Outreach Smoke Test (GATED — explicit user authorization required)

*Family: direct · Cost: SERP calls + email API · only with the user's
specific, informed go-ahead (who, how many, exact message)*

email-guesser → email-verify → resend: 15–25 target-persona contacts, a
2-sentence problem-interview ask (no product pitch, no deception — identify
honestly). Measure reply rate and what the replies say. ≥10% substantive
replies to a cold pain-statement = unusually hot pain; silence is weak
evidence either way. Default: don't run inside the loop — *propose* it in
report.md as a confirmation step. Never fabricate identity or run it without
authorization.

## P11 — Ad-Library Teardown (message & vocabulary harvest)

*Family: competitor-capital · Cost: ~$0.002–0.006 per competitor, creative
downloads free · Phase 2 (vocabulary) and Phase 4 (wedge/positioning)*

Reads what competitors have *paid to learn* about this market: a
long-running ad is A/B-tested positioning with a profit motive behind it, and
its category language is keyword harvest for P1. This is the "see what's
already working" pattern — extract proven language and messaging instead of
inventing your own.

1. ads-transparency `ads --target <domain>` per known competitor (from
   P2/P3/P5) — or `--advertiser-ids` for one company precisely. `--csv` to
   bank.
2. Sort by `days_running`; `--download-creatives` (free) and read the top
   5–10 long-runners. Text ads render to PNG; image/video rows need their
   `url` opened by hand — plan that as manual work.
3. Split brand-defense ads from category ads. From the category ads extract:
   the **vocabulary** (the nouns and phrases buyers are being bid on → feed
   the P1 cluster harvest), the **claimed value props and offers** (pricing
   mentions feed P8; the pains their copy leads with are the pains they've
   proven convert), and the **format mix** (text-heavy = search-intent
   buyer; video-heavy = funding awareness — a different CHANNEL game).

Example validates: P3's top complaint theme appears in *no* incumbent's
proven copy → an open positioning gap the wedge can own (name it in the
card). Example kills: every incumbent's long-running copy already leads with
your wedge → the wedge is table stakes, not a differentiator — kills the
WEDGE premise.

Traps: `title` in the rows is the advertiser's name, not the headline — copy
exists only in the rendered creatives (the `copy` column says which rows
render); a two-week-old ad is an experiment, not a lesson — weight everything
by `days_running`.

---

## Composing a card (worked shape)

Node N04 "AI SOAP notes for solo therapists":

1. **P1** (already priced in Phase 2 — free re-read) — kill if commercial
   cluster <5k/mo or CPC >$9
2. **P3** on top-2 incumbents (~$0.01) — kill if both ≥4.6; validate wedge if
   billing/accuracy complaints ≥15%
3. **P5** sustainer check — ads-transparency on top-2 incumbent domains
   (~$0.004, sort by `days_running`) + apple-ads EU (free) — validate if ≥1
   category-term sustainer ≥90 days; **P11** rides along on the same pull:
   download the creatives (free) and kill the wedge if their proven copy
   already leads with it
4. **P8** pricing sweep (~free) — feed the `--price` points
5. **P6** capital scan (~$0.04) — corroborate
6. → `cac.py` → verdict vs. pre-registered thresholds, plus the CAC band and
   repay table to hand the user (economics.md: the handoff and the options
   menu — the loop reports the cost, the user rules on it)

Total ≈ $0.07 beyond the shared Phase-2 call, spans search + marketplace +
competitor-capital families, and steps 1–2 can kill the card before 90% of
the spend.
