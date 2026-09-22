---
name: demandcheck
description: Check whether real demand exists for a topic, product, or idea — and characterize it. Direct, indirect, latent, or urgent; how it shows up (search volume, CPC auctions, who ranks); who captures it and at what price; which messaging is categorically working (ads that keep running are ads that pay); and hard-to-vary explanations of why the demand takes this shape. Runs a budgeted graph traversal over live data — the user's seed words to Google SERP to real websites, keywords harvested from those sites via DataForSEO, ad libraries via Ads Transparency — with Haiku collectors, local OCR reading the ad creatives, a Sonnet cleaner, and an Opus analyst; it never invents keywords, and it holds its own expectations to account against the data before it concludes. Delivers a plain-English PDF that reproduces the ad creatives themselves as evidence, with EDA charts, the full data, and four stack-ranked ways in. Trigger on "is there demand for X", "demandcheck X", "does anyone actually want X", "is the demand direct or latent", "who's capturing demand for X", "what messaging works in X". To converge on one buildable variant and price customer acquisition (CAC), use demand-forecasting instead.
---

# demandcheck

The user hands you a topic, product, or idea. Your job is not to judge whether
they should build it — that's the sibling `demand-forecasting` skill. Your job
is to answer a prior question with live data: **does demand exist, and what is
its character?**

- **What shape is it** — direct (people search for the thing and advertisers
  bid on it), indirect (routed through adjacent problems), latent (real pain,
  weak monetization), urgent (now-phrasing at premium prices)?
- **How does it show up, and how does it get captured** — which queries, at
  what volume and price, who ranks, who pays for ads, and where the gaps are?
- **What messaging is categorically working** — an advertiser cuts a losing ad
  in weeks, so a creative that has run for months is *proven* copy. What people
  pay to say, and the words on their marketing pages, are the most revealing
  demand evidence there is.
- **What explains it** — 2–5 hard-to-vary explanations (Deutsch's criterion,
  borrowed from demand-forecasting) of why the demand takes this shape, each
  forbidding something checkable in the data you collected.
- **Where the reader goes from here** — four routes into the market,
  stack-ranked, each with the rows that rank it and what it costs to take.

The run's own error correction — what it expected, what the data refuted, what
these instruments cannot see — decides what the report may claim, and narrows
any claim it cannot support. It is not report content: the reader gets the
conclusions, the evidence for them, and the routes forward.

Why this shape: an LLM is excellent at inventing a plausible market and the
keywords to "prove" it — that is the failure mode. Every rule below keeps the
*evidence* measured while leaving the *thinking* bold: you conjecture what the
market looks like, then spend the budget trying to refute yourself. The three
instruments are other skills in this repo: `brightdata-serp` (what Google
shows), `dataforseo-keywords` (what searches cost and how many there are),
`dataforseo-ads-transparency` (what advertisers actually run). This skill is
the survey: the traversal policy, the crew, the ledger, the error correction,
and the report.

## The prime directive — fabricate no observations, conjecture boldly

Two halves, and confusing them is the skill's deepest failure mode
(`references/error-correction.md` argues this out — read it at intake).

**Half one: you never make up a query.** Every search term and every keyword in
the run must be traceable to one of exactly two origins:

1. **The user's own seed words, verbatim.** Not rephrased, not expanded, not
   "improved". If they said "cold plunge tub", you may search "cold plunge
   tub" — not "ice bath therapy".
2. **Harvest.** Facts a paid pull returned: domains that appeared in a SERP,
   keywords that `for-site` returned for a real website, brand names printed
   in results or on downloaded ad creatives.

The loop this creates is the whole method: seed words → SERP → real websites →
`for-site` those websites → real keywords with volumes and prices → SERP the
best harvested keywords → new websites → repeat. Provenance is recorded on
every graph node (`via`), and the cleaner rejects any candidate that lacks it.
If you catch yourself wanting to search a phrase no data source produced,
that's the signal to expand the graph another hop instead.

Why so strict: keywords written from imagination measure your guesswork, not
the market. Harvested keywords carry a profit motive — someone already paid to
rank or advertise on them.

**Half two: the data will not think for you.** No table of volumes and prices
contains a claim about *why* the demand is latent, who has the pain, or what
the long-running ads reveal — those are conjectures you invent, and the tables'
only job is to give them the chance to die. So state them, early and at full
strength, where the data can kill them:

```bash
dc.py conjecture add --text "..." --forbids "..." --check "..."
```

`--forbids` is the load-bearing field: a claim that forbids nothing survives
every run and teaches nothing. Register 2–3 at intake, rule on them every wave
(`dc.py conjecture judge C1 --status refuted --evidence "..."`), and report the
dead ones. A conjecture refuted in wave 2 is the best dollar the run spends;
a run where everything survived usually forbade nothing.

## Spend the budget

The run has a USD cap — **default $5.00** when the user doesn't set one. Treat
the cap as the *target*, not a ceiling to stay far under: this survey's value
scales with coverage, and unspent budget is unfinished work, not savings. Land
final spend at **≥90% of the cap** and log why any remainder was unspendable.

Batching discipline still applies (one 1000-keyword `search-volume` call
instead of ten 100-keyword calls) — but its purpose here is to buy *more
coverage* per dollar, never to finish cheap. When the frontier thins with
budget left, Phase D exists precisely to spend the rest well.

Two hard external limits sit outside the USD cap and are tracked separately:

- **BrightData: 100 calls/day**, shared across every `brightdata-*` skill.
  Each SERP query is 1 of the 100 (cache hits are free and don't count).
  `dc.py status` shows today's count; when it's exhausted, keyword→SERP
  expansion pauses but domain expansion (`for-site`, ads) continues.
- **DataForSEO keywords: 12 requests/minute** account-wide. Never let more
  than 8 concurrent collectors carry keyword calls, and tell each collector
  how many it may make.

## The crew — three model tiers

You (the session reading this) are the **orchestrator**: you own the loop, the
frontier, the budget, and all state changes. The paid work is delegated to
subagents spawned with the Agent tool at three tiers — role instructions live
in `agents/` and are read before spawning each kind:

| Tier | Model | Role | Does | Never does |
|---|---|---|---|---|
| Collector | `haiku` | hands | Runs the exact commands it is given, banks raw output, writes a receipt, lists candidate nodes it saw | Invents queries; interprets; touches state.json |
| **OCR reader** | *no model* | eyes | `scripts/ocr_creatives.py` reads every downloaded creative PNG into verbatim ad-copy rows — locally, ~7 images/second, $0.00 | Guess: what it cannot read it flags |
| Transcriber | `haiku` | fallback eyes | Reads **only** the creatives OCR flagged (`raw/ad_copy/ocr-review.json`) — ornate banners, text over photography | Re-read what OCR already read cleanly |
| Cleaner | `sonnet` | editor | Merges raw into the canonical CSVs, dedupes, classifies domains and keyword intent, spot-checks the ad copy, proposes the next frontier with provenance | Concludes anything about the market |
| Analyst | `opus` | analyst | Reads the clean corpus, classifies the demand, writes the insights and explanations, attacks its own leading explanation, drafts the report manifest | Runs collection; cites nothing it can't point to; says "proven" of anything |

**Why OCR and not a vision model.** These PNGs are Google's own renders —
synthetic type on flat ground, the easiest input OCR ever gets — and 104 of
120 creatives in a live HubSpot pull came back `format: text`, the easy case.
A local engine reads a 120-creative wave in ~17 seconds for nothing, where a
batch of vision agents costs tokens and minutes.

Run head-to-head on 10 live creatives, OCR and a Haiku transcriber agreed on
the headline **10 times out of 10**, and OCR captured every word Haiku did
plus the display URLs Haiku dropped on 4 ads and the sitelinks it dropped on
another — in 1.7s versus 66s and 36k tokens. Haiku also wrote unquoted commas
into 5 of its 10 CSV rows, spilling descriptions into the CTA column; that is
why `agents/transcriber.md` now asks for JSON. The model tier stays in the
crew for the residue only — the ad whose copy is set over photography — which
is where a model is actually worth paying for.

Spawning rules: launch all of a wave's collectors **in one message** so they
run in parallel; collectors write per-task **receipt JSONs** into `receipts/`
(schema in `agents/collector.md`) and never touch `state.json` — parallel
writers racing on one ledger is how state corrupts. Only `scripts/dc.py`
mutates state; the orchestrator folds receipts in serially with
`dc.py reduce-receipts`. When a subagent task completes, its notification
carries `total_tokens` and `duration_ms` — record them in the notebook entry
for the wave (they are not persisted anywhere else).

**No Agent tool available?** Run the same phases yourself, inline and serially:
collect, then read the creatives (the OCR script needs no agent at all), then
clean, then analyze, producing identical artifacts. The loop degrades in
speed, not in shape.

## The run directory — state on disk

All state lives on disk so the run survives context loss and every claim stays
auditable. Created by `dc.py init`:

```
research/demandcheck/<slug>/
├── state.json        # the graph: nodes, provenance, waves, budget ledger, SERP daily count, conjecture register
├── notebook.md       # append-only: every wave, cost, decision, surprise
├── receipts/         # collector receipts; archived to receipts/processed/ after reduction
├── raw/              # banked pulls: serp/, keywords/, ads/ (you paid for these — keep them)
├── creatives/        # downloaded ad PNGs, one dir per advertiser id
├── clean/            # the canonical CSVs the cleaner owns (schemas in references/traversal.md)
├── charts/           # EDA PNGs from eda_charts.py
├── .thumbs/          # downscaled creative images the PDF embeds (rebuildable)
├── report-manifest.json
└── report.pdf        # the deliverable
```

The notebook is append-only: when a later wave contradicts an earlier read of
the market, both entries must survive. **Never edit or delete a superseded
entry** — rewriting the record so the run looks right all along is how a
research process loses the ability to learn. Write an entry after every phase
step — timestamp, what ran, what it cost, what changed, and what surprised you.

## The loop

Read the listed reference *before* running its phase — they are field manuals,
not optional context.

### Phase 0 — INTAKE (free) — read `references/error-correction.md`

- Record the seed **verbatim** — the user's words are the only non-harvested
  queries you will ever run. Note whether the seed is *topic words* or a
  *company/domain* (changes Phase 1).
- Budget cap (default $5.00), geo and language (default US / en /
  location_code 2840 — record them; metrics swing 100× by geography).
- Scope check: is this demand *expressed* (people already search, buy, or pay
  around the pain) or *novelty-dependent* (the want would be created by the
  product existing)? These instruments read expressed demand only — for a
  novelty-dependent seed you survey the nearest expressed pains and the report
  says so (see `references/demand-lens.md`).
- Instrument check: `DATA_FOR_SEO_LOGIN`/`DATA_FOR_SEO_PASSWORD` and
  `BRIGHTDATA_API_TOKEN` in the env. A missing instrument narrows the survey
  and is named in the report; it doesn't stop the run.
- `dc.py init --seed "..." --slug <slug> --budget-usd <cap>` then write the
  mission brief as the first notebook entry.
- **Pre-register 2–3 conjectures** — before a single call. What do you expect
  this survey to find, and what would refute it? You are not a blank slate;
  the only question is whether your expectations are written where the data can
  kill them or left implicit where they will quietly filter which numbers you
  notice.

  ```bash
  dc.py conjecture add \
    --text "Demand is latent — the pain is real but buyers don't know the category name" \
    --forbids "high-CPC category-name keywords carrying 90-day creatives" \
    --check "3+ category terms above \$3 CPC with sustained advertisers refutes this"
  ```

  Aim the first cheap calls at whichever conjecture the run's value most
  depends on. Being wrong in wave 1 costs a dollar; being wrong in the report
  costs the reader's decision.

### Phase 1 — SEED WAVE — read `references/traversal.md`

Topic seed: `dc.py wave open`, then spawn one collector to SERP the user's
words verbatim — 1–4 queries, `--format parsed --num 10`, plus **one** repeat
of the main seed with `--format markdown` (parsed output can drop the paid-ad
blocks; the markdown view shows who is *advertising* on the seed, which is
capture evidence). Company/domain seed: skip SERP — the domain goes straight
into the frontier as wave 1.

Reduce receipts, then run the cleaner: it seeds `clean/serp_results.csv` and
`clean/domains.csv` and proposes the first frontier.

### Phase 2…N — WAVES (collect → read creatives → clean → decide) — read `references/instruments.md`

Each wave, in order:

1. **Size it.** `wave_budget ≈ 0.35 × (remaining − deepen_reserve)` where
   `deepen_reserve = 0.15 × cap`, floor $0.75. A domain expansion costs
   ≈ $0.07 (`for-site` + `advertisers` + `ads --depth 120` + free creative
   downloads); a keyword expansion ≈ $0.01 (one SERP query). Fill the wave
   from the frontier until the wave budget is spent — **an under-filled wave
   is a bug, not a virtue.**
2. **Collect.** Spawn all collectors in one message (model `haiku`, task
   blocks per `agents/collector.md` — exact commands, bank paths, receipt
   path). Respect the stagger rule (≤8 collectors carrying keyword calls).
3. **Read the creatives.** One command, no agents, free:

   ```bash
   python3 .claude/skills/demandcheck/scripts/ocr_creatives.py --run research/demandcheck/<slug>
   ```

   It reads every PNG downloaded so far (already-read creatives are skipped,
   so run it every wave), writes `raw/ad_copy/ocr-<dir>.csv`, and prints what
   it could not read. Only if `needs_transcriber` > 0 do you spawn transcribers
   (model `haiku`, `agents/transcriber.md`, ~25 flagged images each) — the
   list is in `raw/ad_copy/ocr-review.json`. Exit code 3 means no OCR engine is
   installed: install one from the message, or send the whole batch to
   transcribers and note it in the notebook.
4. **Reduce.** `dc.py reduce-receipts` — folds receipts into the ledger and
   graph serially: spend logged per call, candidates become nodes with
   provenance, SERP daily counter bumped. Then `dc.py status`.
5. **Clean.** Spawn one cleaner (model `sonnet`, `agents/cleaner.md`). It
   merges the wave's raw into `clean/`, tags keyword intent and provisional
   demand class per `references/demand-lens.md`, and proposes the ranked next
   frontier — every candidate with provenance.
6. **Correct, then decide.** First rule on every open conjecture against what
   this wave actually returned — `dc.py conjecture judge C1 --status
   survived|refuted|revised --evidence "<the rows that did it>"`. A refutation
   here redirects the remaining budget, which is the whole point of ruling
   before deciding; `wave close` will tell you if you skipped this. Then
   sanity-check the frontier proposal against budget and caps, set node
   scores/statuses via `dc.py set`, `dc.py wave close --note "..."`, write the
   notebook entry (including anything that surprised you), loop.

Carry the `latent-probe` picks every wave even when spend_proxy ranking says
otherwise — ranking the frontier by volume × CPC is itself a conjecture ("money
marks the important demand") and it is blind to exactly the unpriced quadrant
this skill most wants to find.

Stop opening new waves when any of: spend ≥ 90% of cap (go to ANALYZE);
frontier empty (go to DEEPEN); only SERP expansion remains and the BrightData
day is exhausted (go to DEEPEN).

### Phase D — DEEPEN (the anti-cheap pass)

If ≥10% of the cap remains when waves stop, spend it — in this order of value:

0. **Buy one refutation.** Before any coverage pass, spend one call on the
   check most likely to *kill* the explanation the report is going to lead
   with — the SERP that would show the wrong advertisers, the `for-site` on the
   domain whose vocabulary would contradict you, the `search-volume` batch on
   the terms your story says should be cheap. If it survives that, it has
   earned the lead; if it dies, you found out while you could still rewrite.
   Judge the conjecture either way.
1. **Price the whole long-tail.** Every harvested keyword not yet priced goes
   through `search-volume` in ≤1000-keyword batches (one call ≈ $0.05–0.10
   regardless of size — this is the best coverage-per-dollar in the skill).
2. **Own-ads pulls on the top advertisers.** `ads --advertiser-ids` at
   `--depth 120` for the 3–5 biggest capture leaders — resellers excluded,
   full creative history, more PNGs for the OCR reader.
3. **Page-level footprints.** `for-site --target-type page` on the 2–3 most
   linked landing pages from the SERPs — page-level vocabulary is sharper
   than domain-level.
4. **One `ad-traffic` forecast** on the head cluster (`--bid 999 --match
   exact`) for a true auction price to anchor the ad-spend chapter.

Then re-run the OCR reader, reduce, clean as usual. Land ≥90% spent; log
the remainder.

### Phase A — ANALYZE — read `references/demand-lens.md` and `references/error-correction.md`

Before spawning, run the tells checklist at the end of `error-correction.md`
against your own run (every conjecture survived? no wave carried a latent
probe? no entry records a surprise?). If two or more tells fire and budget
remains, that is what DEEPEN is for — go back and buy the missing criticism.

Render the charts and scaffold the manifest *before* spawning the analyst — it
should never face a blank file, and no number should ever be retyped by hand:

```bash
python3 .claude/skills/demandcheck/scripts/eda_charts.py    --run research/demandcheck/<slug>
python3 .claude/skills/demandcheck/scripts/make_manifest.py --run research/demandcheck/<slug>
```

`make_manifest.py` computes the cover's key numbers, the demand-mix /
top-terms / capture tables, the charts that actually rendered, six ad exhibits
(longest-running creatives with legible copy, spread across advertisers), four
ranked paths waiting to be argued, the appendix tables and a default glossary —
leaving `TODO` markers everywhere prose is needed.

Then spawn one analyst (model `opus`, `agents/analyst.md`). It reads `clean/`,
`state.json`, and the notebook — never raw guesses — and finishes
`report-manifest.json`:

1. **The demand verdict** — does demand exist, in what mix of
   direct / indirect / latent / urgent, with volumes, prices, and cluster
   sizes per class.
2. **How it shows up and who captures it** — the queries and their volumes,
   who ranks, who pays, at what CPC, and the capture gaps (volume nobody
   advertises against).
3. **How the market talks — and what messaging is categorically working** —
   vocabulary map from keywords and the ad copy read off the creatives;
   value propositions with verbatim quotes; what long-running ads say vs
   newcomers; high-volume phrasings no ad uses (open messaging territory).
4. **What it costs** — the CPC landscape by theme and demand class,
   top-of-page bid bands, spend-proxy leaders (volume × CPC), who advertises
   hardest and longest, format mix.
5. **The explanations** — 2–5 hard-to-vary explanations of why the demand
   takes this shape, each with its premises, the numbers that carry it, and
   the alternative reading it beats.
6. **Four ways in** — exactly four routes forward, stack-ranked, each with the
   rows that put it at that rank, what it costs the reader in money, time and
   forgone options, who it suits, and the first move.

Every claim cites its evidence — a keyword row, a creative id, a SERP line.
Findings are stated in the strongest form the data supports; nothing is
"proven" or "validated", and nothing carries a confidence percentage.

**The report never narrates the run.** The conjecture register, the refutations,
the waves, the budget, the method and where each figure was bought are what make
the conclusions good — they are not content, and none of them reach the PDF.
Where a limit changes how a finding should be read, it goes inside that finding.
Plain language throughout: the reader is an outsider (rules in
`references/report-spec.md`).

### Phase R — REPORT — read `references/report-spec.md`

```bash
python3 -m pip install matplotlib reportlab pillow   # once per machine; scripts guard and remind
python3 .claude/skills/demandcheck/scripts/make_manifest.py --run research/demandcheck/<slug> --check
python3 .claude/skills/demandcheck/scripts/build_pdf.py --run research/demandcheck/<slug>
```

`--check` audits the finished manifest (leftover TODOs, missing sections, fewer
than four paths forward, creative ids that don't exist, charts never rendered,
"proven"-style language, and sentences that narrate the process); clear every
PROBLEM before building. `build_pdf.py` then lays out `report.pdf`: a
full-bleed dark cover carrying the verdict, four headline numbers and a strip
of the market's live advertising; a clickable contents; the executive summary;
**an orientation page** that explains how a search market works and defines the
four kinds of demand, each sized and exampled from this run's own rows;
**the search terms behind every number, on their own page**; the chapters —
prose, callouts, pull-quotes of real ad copy, charts, tables and **ad-creative
exhibits** in whatever order the argument needs; the explanations; **Four ways
in** (the ranked routes); a glossary; **Appendix A: every
ad reproduced as a picture** with its wording and run length; and **Appendix B:
the full data**. The cost ledger is operator material and only renders with
`--ledger`.

The builder prints a **report card** at the end of every build: unused charts,
how many creatives reached the chapters, missing sections. Read it, and go back
if it names something. Then deliver `report.pdf` to the user with a short
summary in chat: the verdict in one line, the single most surprising finding,
total spend vs cap, and the run directory path.

## Scripts

- `scripts/dc.py` — stdlib-only state manager; the **only** writer of
  `state.json`: `init`, `wave`, `add`, `set`, `conjecture`, `spend`,
  `reduce-receipts`, `frontier`, `status`. Auto-discovers the run under `research/demandcheck/`
  when there's exactly one; pass `--run` otherwise. Use it for all state
  changes — hand-edited JSON drifts and breaks the audit trail.
- `scripts/ocr_creatives.py` — reads the downloaded creative PNGs into
  `raw/ad_copy/*.csv` locally and free, and lists what it couldn't read.
  Needs an OCR engine (`apt-get install tesseract-ocr`, macOS
  `brew install tesseract`, or `pip install rapidocr-onnxruntime`) and
  `pip install pillow`, which is optional but worth several accuracy points
  on small banners and enables the gap sweep. `--self-test` checks the engine
  against four shipped fixtures in two seconds — run it once per machine
  before trusting a run's ad copy.
- `scripts/eda_charts.py` — the EDA chart set (matplotlib). Skips any chart
  whose data is missing rather than failing the run.
- `scripts/make_manifest.py` — scaffolds `report-manifest.json` from the
  corpus (every number computed, prose left as `TODO`), and `--check` audits a
  finished one. The analyst never starts from a blank file.
- `scripts/build_pdf.py` — manifest-driven PDF builder (reportlab + Pillow).
  Renders the ad creatives as evidence — on the cover, as exhibits inside the
  chapters, and as a full gallery in Appendix A. Flags worth knowing:
  `--max-creatives`, `--creative-columns`, `--thumb-px`, `--max-table-rows`,
  `--ledger`, `--strict`.

The OCR, chart and PDF scripts are this repo's deliberate exceptions to the
stdlib-only convention: they need tesseract/Pillow, `matplotlib` and
`reportlab`, check for them on start, and exit with the exact install command
if absent. PyPI is reachable from this workspace.

`assets/report-selftest/make_demo_run.py` builds a synthetic run — invented
brands, drawn ad images, fake numbers — so the whole report path can be
exercised in ten seconds for $0.00 after changing any of the three scripts;
`assets/manifest-example.json` is that demo's finished manifest, and the tone
reference for the analyst.

`assets/ocr-benchmark/` holds the reader's regression harness — 18 synthetic
ad layouts with known copy, and a scorer. Run it after changing any OCR
heuristic; the baseline is headline 100%, description 97%, CTA 89%,
other 83%.

## References — read before the phase that needs them

| File | Read before | Contents |
|---|---|---|
| `references/error-correction.md` | Phase 0 (re-read at Phase A) | How this skill creates knowledge: conjecture vs fabricated evidence, the conjecture register, the traversal's own blind spot, criticize-don't-justify vocabulary, what the instruments can't see, the tells checklist |
| `references/traversal.md` | Phase 1 | Graph model, wave lifecycle, frontier scoring, budget math, caps, clean-CSV schemas, resumability |
| `references/instruments.md` | Phase 2 | The three instruments: exact commands, costs, banking flags, traps |
| `references/demand-lens.md` | Phase A (skim at intake) | Direct/indirect/latent/urgent signatures, capture analysis, messaging-that-works criteria, the explanation standard |
| `references/report-spec.md` | Phase R (the analyst reads it at Phase A) | The report template and its page spine, the block schema, the ad-creative evidence rules, the chart set, the manifest schema, and the language rules that keep the reader informed rather than talked down to |

## Output contract

While looping, keep the user oriented with short interim updates: wave number,
nodes expanded, spend so far, and the single most interesting thing since the
last update — not raw data dumps. The final deliverables are `report.pdf`
(sent to the user) and the run directory. The chat summary states: the demand
verdict in one line (which classes, how big), the strongest proven-messaging
finding, what the market pays (headline CPC range), **what the run expected and
the data refuted**, total spend vs cap, and where the run directory is.

## Compressed example (shape, not gospel)

Seed "cold plunge tub", $5 cap → INTAKE: expressed demand, US/en; C1 "demand is
mostly latent, priced under $1" (forbids: category terms above $3 with 90-day
advertisers), C2 "the buyers are athletes, so proven copy sells performance"
(forbids: proven copy leading on home/luxury) →
SEED WAVE: 2 SERP calls on the verbatim seed (parsed + markdown) → 9 domains,
3 visible advertisers → WAVE 2 ($1.60): collectors `for-site` 4 retail domains
+ pull their ad libraries (312 creatives, 118 PNGs downloaded free);
OCR writes 118 ad-copy rows in 16s and flags 6 for a transcriber; cleaner tags
"cold plunge tub" (9.9k/mo, $1.42 CPC, direct) vs "ice bath benefits"
(60k/mo, $0.31, latent) and proposes
6 harvested keywords + 3 domains; **C1 refuted** — the category name prices at
$1.42 with four 90-day advertisers on it, so the demand is a mix rather than
latent, and the rest of the budget swings toward capture → WAVE 3 ($1.10):
SERP the 6 keywords, `for-site` 2 new domains → DEEPEN ($1.05): first the
refutation call — `for-site` on the home-wellness domain whose vocabulary would
sink C2 (C2 survives: 11 of 14 long-runners still lead on recovery) — then one
640-keyword `search-volume` call prices the whole tail; `--advertiser-ids` pull
on the 2 biggest advertisers; `ad-traffic` on the head cluster → ANALYZE: direct
demand ~40k/mo around $1.20–2.10 CPC captured by 5 brands; latent demand 4×
larger at a tenth the price, captured by content sites, zero product
advertisers — the gap; the longest-running ads all sell "recovery" not "cold
exposure"; explanation E1 (recovery language converts, with the rows that carry
it and the alternative read it beats); C1's refutation redirected the budget in
wave 2 and stays in the notebook; the scope line (this category also sells hard
on TikTok, which search data cannot see) is folded into the chapter-2 finding
it qualifies; four ranked ways in, led by "own the practice questions" → REPORT: charts, then
`make_manifest.py` scaffolds the manifest with every number computed, six ad
exhibits picked and four paths waiting; the analyst fills the prose and
`--check` comes back clean → a 30-page PDF: verdict, four headline numbers and
live ad creatives on the cover, the search terms on page four, four chapters
carrying 9 charts and ads quoted from their own images, four ranked ways in,
every one of the 118 creatives in Appendix A, full tables in Appendix B.
$4.71 of $5.00 spent — reported in chat, never in the PDF.
