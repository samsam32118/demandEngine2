# The demand lens — classification, capture, messaging, explanations

Skim at intake; read fully before Phase A (ANALYZE). This file is what makes
the survey a *demand check* rather than a keyword dump: the four demand
classes and their instrument signatures, the capture analysis, the test for
"messaging that categorically works", and the standard every explanation in
the report must meet.

## Demand is revealed preference

People demonstrate demand by what they already spend to deal with a pain —
money first, then time and attention, and only last their words. Ranked,
strongest first (adapted from demand-forecasting's ladder to what *these*
three instruments can see):

1. **Sustained ad spend** — an advertiser has kept a creative running for
   months. Advertisers cut losers in weeks; a long-running ad is a public
   statement that the spend pays. The single best signal in this skill.
2. **Auction price** — a live CPC and top-of-page bid on a query is other
   people's money bidding for that intent, priced in real time.
3. **Search volume with commercial phrasing** — thousands of people typing
   "best X" / "X price" every month.
4. **Search volume with informational phrasing** — the pain shows up, the
   wallet not yet.
5. **SERP attention** — who bothers to rank content for it.

Every number in the report carries its geo; every claim names its rung.

## The four classes — definitions and instrument signatures

The cleaner tags provisionally (`demand_class` in `keywords.csv`); the analyst
owns the final classification and may re-tag with a note. Classes describe
*keyword clusters*, not whole markets — most markets are a mix, and the mix
IS the finding.

**Direct** — people search for the thing itself and advertisers bid on it.
- Signature: category/product phrasing (`cold plunge tub`, `buy X`, `X
  price`), nonzero CPC with real competition_index, active creatives in
  discovered ad libraries, product domains ranking.
- Read: the demand is priced and contested. Report who holds it and at what
  price.

**Indirect** — the demand routes through adjacent problems or categories.
- Signature: harvested keywords from adjacent-category domains (a sauna
  seller monetizing "cold plunge" terms); SERPs where the rankers/advertisers
  aren't category players; the seed's volume dwarfed by an adjacent pain's
  volume that the same domains monetize.
- Read: the market reaches this product sideways. Report the route — which
  adjacent intent, who owns it.

**Latent** — the pain shows up; almost nobody monetizes it.
- Signature: real volume on informational/how-to/DIY phrasing (`how to make
  an ice bath`, `diy cold plunge chiller`) with low CPC, low
  competition_index, thin or absent ad coverage; content/media domains
  ranking where product domains could.
- Read: *unpriced demand* — the interesting quadrant. Quantify it (volume at
  weak auction pressure) and name who half-captures it today.

**Urgent** — now-phrasing at premium prices.
- Signature: `near me`, `same day`, `emergency`, `repair`, `fix` modifiers
  carrying a CPC premium over the category base; local/service advertisers.
- Read: demand that pays extra for immediacy. Report the premium (urgent CPC
  vs category median CPC).

`intent_markers` (buy/best/price/near-me/how-to/diy/emergency/brand/none) are
mechanical tags the cleaner applies from the phrase text; `demand_class` is
judgment on top of markers plus prices plus who-captures. Brand terms are
their own thing: tag `brand`, never SERP-expand them, and count their volume
as *capture already won* by that brand — evidence for chapter 2, not a class.

**"No demand" vs "demand my instruments can't see."** These instruments read
*expressed* demand — searches typed, ads run. A novelty-dependent idea (the
want would be created by the product existing) can score zero everywhere and
still be buildable; nobody searched for spreadsheets in 1978. Intake
classified the seed; if it was novelty-dependent, zero-signal results bound
the *instruments*, not the idea — the report says "no expressed demand
found via search and ads" and names what wasn't measurable. Never let the
two verdicts share a sentence.

## Capture analysis — who gets the demand today

For each meaningful cluster, chapter 2 answers four questions from the clean
tables:

- **Who ranks** — domains from `serp_results.csv` (organic rows), typed as
  competitor / aggregator / media. An aggregator-heavy SERP is a market
  nobody owns yet; a competitor-heavy SERP is a moat.
- **Who pays** — advertisers active on the cluster's domains (`ads.csv`
  joined through `advertisers.csv`), their creative counts, active share,
  and how long they've sustained (`days_running`).
- **At what price** — cluster CPC range and `low/high_top_of_page_bid` bands:
  what winning this demand costs per click today.
- **Where the gaps are** — volume with no active advertiser and weak
  organic ownership: the capture gap. List the top gaps by spend_proxy
  forgone; these rows are usually the report's most actionable finding.

## Messaging that categorically works

"Categorically working" has a definition here, not a vibe: **a creative
qualifies as proven when it has run long enough that a paying advertiser
demonstrably chose to keep it** — default bar `days_running ≥ 90`, or ≥ 60
with `active` true. Everything else is *attempted* messaging.

The analyst compares three corpora from `ad_copy.csv` (+ keyword phrasing):

1. **Proven copy** (long-runners) — what sustained spend says: the value
   props, the hooks, the exact nouns. Quote verbatim, cite creative_id.
2. **Attempted copy** (the rest) — what newcomers try; the delta against
   proven copy is where the market is still arguing with itself.
3. **Searcher language** (`keywords.csv`) — the words buyers type. Where
   proven copy and searcher language agree, that vocabulary is settled
   ("recovery", not "cold exposure"). High-volume phrasings **no ad uses**
   are open messaging territory — name them.

Caveats the analyst must respect: brand-defense creatives (an advertiser's own
brand name in the copy) run forever on pre-existing intent — exclude them from
"proven category messaging". A freshly-funded advertiser can sustain losing
ads for a while; where one advertiser dominates the long-runner set, say so
rather than generalizing from them.

**Check the provenance before you quote.** `ad_copy.csv` says how each row was
read: `extraction` (`ocr:*` = machine-read off the PNG, `haiku` = a model read
an image OCR could not) and `ocr_conf` (0–100). A row at 95 is a clean read of
Google's own render and is safe to quote character-for-character; a row below
the confidence floor carries its reason in `extraction` (`:low_conf`,
`:gibberish`) and must not be quoted verbatim — count it in the corpus if the
words are plainly right, otherwise leave it out and say how many rows you set
aside. `ILLEGIBLE` is never evidence of anything except that the creative
could not be read.

## The explanation standard (Deutsch, via demand-forecasting)

Numbers without explanations are noise; explanations without numbers are
narrative. Chapter 5 delivers 2–5 explanations of why the demand takes the
shape chapters 1–4 measured. They are *conjectures* — invented by the analyst,
not extracted from the tables — and the tables' job is to give them the chance
to die (`references/error-correction.md` sets the run-level machinery; this is
the bar each individual explanation must clear). Each must be:

- **Mechanistic** — it names who has the pain, why it reaches the market in
  this form (direct/indirect/latent/urgent), and why capture looks the way it
  does. Not "there is growing interest in wellness".
- **Hard to vary** — if you can swap the WHO or the product category and the
  explanation still reads true, it explains nothing. Sharpen until it forbids
  something.
- **Checked against this run's data before it is written down.** Work out what
  the explanation implies about the collected tables, then go and look. ("If
  recovery framing is what converts, the ≥90-day creatives should use recovery
  language at a higher rate than the rest: 14 of 17 vs 3 of 11.") An
  explanation whose implication fails gets rewritten or dropped — that check is
  the analyst's job, and its *result* is what reaches the reader, in the form
  of the numbers that carry the surviving explanation. The reader never sees
  the checking.
- **Stronger than the obvious alternative** — name the best competing reading
  of the same numbers (seasonality artifact, one funded advertiser skewing the
  corpus, aggregator SEO noise, planner CPC noise on tiny volumes) and show why
  the numbers favour yours — or downgrade the claim. This one *is* published:
  it is market analysis, and it is what stops a reader dismissing the finding
  on the first objection they think of.

Format per explanation: a name, the premises it rests on, `evidence` (the rows
and numbers that carry it), and `alternative` (the competing reading and why it
loses). Written in plain words — the premises are sentences an outsider can
evaluate, not jargon.

**Surviving is not being proven.** An explanation that passed every check this
budget could buy is exactly that. Say what the numbers show and stop there —
"14 of the 17 long-running ads lead on recovery" — never "the data proves /
validates / confirms", and never a confidence percentage. The reader cannot act
on 87% confidence; they can act on four ranked routes with their tradeoffs
priced, which is what the closing chapter is for.
