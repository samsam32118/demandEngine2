---
name: positioning
description: Position a product using April Dunford's framework, automatically, from nothing but its URL. Reads the product's own marketing pages, finds the alternatives its buyers would actually use (competitors, adjacent tools, spreadsheets, and doing nothing), fetches what those alternatives claim and advertise, prices the vocabulary the market really searches for, and works through the framework in order — best customers, vocabulary, true alternatives, unique attributes vs table stakes, attributes to value, who cares a lot, market frame, sales story and positioning canvas. Delivers a PDF that is almost entirely charts: a comparison grid of what is only yours, a flow from features to value, a segment heat map, and a quadrant that picks the category you should compete in. Trigger on "position my product", "positioning for <url>", "run April Dunford's framework on this", "obviously awesome", "what category should we compete in", "who should we target", "what makes us different from <competitor>", "help me with our positioning", "our messaging isn't landing", "we keep losing to <competitor>", "build a positioning canvas", "what's our market category", or any request to work out how a product should be positioned, differentiated, framed or messaged. Takes a URL and needs nothing else — do not interview the user first.
---

# positioning

The user gives you a URL. You give them back a PDF that answers, with evidence,
the question April Dunford's *Obviously Awesome* is about: **what is this
product, for whom, and compared to what?**

Positioning is not a slogan. It is the context you deliberately put a product
in so that its strengths become obvious — and the same product is a leader in
one context and an also-ran in another. The choice is free, it is reversible,
and almost nobody makes it deliberately. That is the value you are creating.

The deliverable is **a deck of pictures, not a report**. Eight of Dunford's
steps get one chart each, and every chart carries a finding a reader can take
in without reading a paragraph. Prose here is a failure mode: positioning is a
set of *comparisons* — you against the alternatives, one frame against another,
one segment against another — and comparisons are exactly what prose is worst
at. If a page needs an explanation, the chart on it is wrong.

Two rules make the whole thing work, and they pull against each other on
purpose.

## Rule one — nothing enters the study that a source did not say

Every alternative, attribute, keyword, segment and competitor claim must trace
to something you actually fetched: a line on a marketing page, a SERP result, a
keyword row with a real volume, an ad that is genuinely running. Provenance goes
on every node (`--via`), and a candidate with no provenance gets dropped.

Why so strict: an LLM can write a *superb* positioning document for a product
it has never looked at. It will invent the three competitors everyone names,
assert that the product is "AI-native" and "built for scale", and produce
something that reads exactly like the real thing. That artefact is worthless,
and it is indistinguishable from a good one without the audit trail. The whole
apparatus below exists so that the reader can check any claim on the page
against a row in the appendix.

The one exception, and it is the important one: **"do nothing" and "do it in a
spreadsheet" are always in the alternative set**, whether or not a source names
them. They win more deals than any vendor does, and they never show up in a
competitor list because they have no marketing team. Search for their traces
(`<job> template`, `<job> spreadsheet`, `<job> manually`, `hire a <role>`) and
size them like any other alternative.

## Rule two — the data will not do the positioning for you

No table of search volumes contains a claim about which segment cares, which
frame is favourable, or which capability is the wedge. Those are conjectures
*you* make, and the tables' only job is to give them a chance to die.

So make them early, at full strength, where the data can kill them:

```bash
pos.py assume add \
  --text "They should compete as a dispatch tool, not a field-service suite" \
  --forbids "the suite category having low competitive density" \
  --check "if 'field service management' has <4 entrenched players, this is wrong"
```

`--forbids` is the load-bearing field. An assumption that forbids nothing
survives every run and teaches nothing. Register 2–3 at intake, rule on them
each phase (`pos.py assume judge A1 --status refuted --evidence "..."`), and
let a refutation redirect the remaining budget. Being wrong in phase 2 costs a
dollar; being wrong in the PDF costs the reader their go-to-market.

The register never reaches the report. It is what makes the conclusions good,
not something the reader has to audit.

## Do not interview the user

The URL is the input. Everything else — what the product does, who buys it,
who it competes with, what category it is in — is what the study is *for*, and
asking the user for it both wastes their time and contaminates the finding with
the belief you were hired to test. Infer geography and budget from defaults
(US / English, $6.00) unless the user set them.

Two things are worth one short message *before* you start, only when they
apply: the URL is unreachable, or the product is pre-launch with no marketing
site to read. Otherwise, run.

## The crew

You are the **orchestrator**: you own the loop, the frontier, the budget, and
every state change. Paid collection is delegated; judgement is not.

| Tier | Model | Does | Never does |
|---|---|---|---|
| Scout | `haiku` | Runs the exact commands it is handed; banks raw output; writes a receipt listing what it saw | Invents queries; interprets; touches `state.json` |
| Cleaner | `sonnet` | Merges raw into the six canonical CSVs, dedupes, classifies alternative lanes, proposes the next frontier with provenance | Decides what is unique, or which frame wins |
| Analyst | `opus` | Reads the clean corpus and fills the manifest's judgement fields — the verdicts, the frame, the segment, the story | Runs collection; cites what it cannot point to |

Spawn all of a phase's scouts **in one message** so they run in parallel.
Scouts write receipts into `receipts/` and never touch state; only `pos.py`
mutates `state.json`, and you fold receipts in serially with
`pos.py reduce-receipts`. Parallel writers racing on one ledger is how a run
silently corrupts its own audit trail.

**No Agent tool available?** Run the same phases inline and serially. The loop
degrades in speed, not in shape.

## The run directory

```
research/positioning/<slug>/
├── state.json            # budget ledger, nodes + provenance, assumption register
├── notebook.md           # append-only: every phase, cost, decision, surprise
├── receipts/             # scout receipts; archived after reduction
├── raw/                  # banked pulls: site/ serp/ keywords/ ads/ reviews/
├── extract/              # extract_site.py profiles, one JSON per company
├── clean/                # the six canonical CSVs (schemas below)
├── charts/               # the eight PNGs
├── report-manifest.json
└── report.pdf            # the deliverable
```

The notebook is append-only. When a later phase contradicts an earlier read,
**both entries survive** — rewriting the record so the run looks right all
along is how a research process loses the ability to learn.

## The loop

Read the reference named by a phase *before* running it.

### Phase 0 — INTAKE (free)

- `pos.py init --url <url> --budget-usd 6` — records the URL, geo and cap.
- Register **2–3 assumptions** before a single paid call (see Rule two). What
  do you expect this study to find? You are not a blank slate; the only
  question is whether your expectations are written where the data can kill
  them or left implicit where they will quietly filter what you notice.
- Instrument check: `BRIGHTDATA_API_TOKEN`, `DATA_FOR_SEO_LOGIN` /
  `DATA_FOR_SEO_PASSWORD`. A missing instrument narrows the study and gets
  named in the report; it does not stop the run.

### Phase 1 — WHAT THEY SAY THEY ARE — read `references/instruments.md`

Fetch the product's own pages and read them structurally. The homepage alone is
not enough: pricing tells you the shape of the offer, the features page is the
attribute list, and the customers page is the segment evidence.

```bash
# one scout, 4-7 pages: /, /pricing, /features (or /product), /customers, /about,
# and any /compare or /vs page — those are the company's own alternative set
python3 .claude/skills/brightdata-web-unlocker/scripts/unlock.py \
    "https://acme.com/pricing" --save research/positioning/acme/raw/site/acme-com-pricing.html

python3 .claude/skills/positioning/scripts/extract_site.py profile \
    --dir research/positioning/acme/raw/site --domain acme.com \
    --out research/positioning/acme/extract
```

The profile gives you claims, features, pricing tiers, named customers, the
company's own self-framing, and a vocabulary count. Read it, not the HTML.

### Phase 2 — WHAT ELSE THEY WOULD DO — read `references/framework.md` §4

The alternative set, harvested three ways and never invented:

1. **SERP** the brand and the job: `<brand> alternatives`, `<brand> vs`,
   `best <category from their own self-framing>`, and one query for the
   *manual* route (`<job> spreadsheet template`, `hire a <role>`).
2. **Ad libraries**: `ads advertisers "<brand>"` shows who is buying the brand
   name — competitors bidding on you are competitors who think they can win.
3. **Their own comparison pages**, already extracted in Phase 1.

Classify every alternative into a lane — `direct`, `adjacent`, `diy`,
`nothing`. The bottom two lanes are mandatory and are the ones a model
reflexively omits.

### Phase 3 — WHAT THE ALTERNATIVES CLAIM

For the top 4–6 alternatives, one scout each, in parallel: fetch home +
pricing + features, run `extract_site.py profile`, and pull the ad library
(`ads ads --target <domain> --depth 60 --download-creatives ...`). Ads matter
more than pages here: an advertiser cuts a losing ad in weeks, so a creative
that has run for months is copy that *pays*.

This phase produces the attribute matrix. A capability claimed by five of six
alternatives is table stakes no matter how proud the product is of it.

### Phase 4 — WHAT THE MARKET CALLS IT — read `references/framework.md` §3, §8

```bash
# the vocabulary a real site monetises, with volumes and prices attached
keywords.py for-site "acme.com"       --sort-by search_volume --csv raw/keywords/acme.csv
keywords.py for-site "competitor.com" --sort-by search_volume --csv raw/keywords/comp.csv

# price every candidate frame and every harvested term in ONE call (≤1000 terms)
keywords.py search-volume "hvac dispatch software" "field service management" ... \
    --csv raw/keywords/frames-priced.csv
```

This is the phase that makes steps 3 and 8 quantitative rather than a matter of
taste. It gives you the vocabulary gap (what they call it vs what buyers type)
and the demand behind every candidate market frame.

### Phase 5 — WHO ALREADY LOVES IT — read `references/framework.md` §1

Segment evidence, from wherever it exists: review sites via SERP
(`site:g2.com <brand>`, `<brand> reviews`), App Store reviews if it ships an
app (`appstore.py reviews`), the case studies and logo wall from Phase 1, and
job posts naming the tool. One row per artefact — the counting is
`make_manifest.py`'s job, and pre-aggregating hides how thin a segment's
evidence really is.

### Phase 6 — CLEAN

Spawn one cleaner (`agents/cleaner.md`). It merges everything banked into six
CSVs — schemas in `references/framework.md` — and proposes the next frontier.
Then `pos.py reduce-receipts`, `pos.py status`, and rule on every open
assumption before deciding what to buy next.

**Spend the budget.** The cap is the *target*, not a ceiling to stay under:
this study's value scales with how many alternatives you actually read. Land at
**≥85% of the cap**. If the frontier thins with money left, buy the check most
likely to *kill* the frame you are about to recommend — if it survives that, it
has earned the recommendation.

### Phase 7 — ANALYZE — read `references/framework.md` in full

Scaffold first, so the analyst never faces a blank file and no number is ever
retyped by hand:

```bash
python3 .claude/skills/positioning/scripts/make_manifest.py --run <run>
```

Then spawn one analyst (`opus`, `agents/analyst.md`). It reads `clean/`,
`extract/` and the notebook, and fills only the judgement fields: the verdicts
(unique / table stakes / gap), the value flow, the segment scores, the
favourability of each frame, the recommendation, the canvas, the story, the
messaging, and one "so what" line per chart.

### Phase 8 — REPORT — read `references/report-spec.md`

```bash
python3 .claude/skills/positioning/scripts/make_manifest.py --run <run> --check
python3 .claude/skills/positioning/scripts/charts.py        --run <run>
python3 .claude/skills/positioning/scripts/build_pdf.py     --run <run>
```

`--check` audits the finished manifest and **fails on prose**: every field has
a character ceiling, because the report's premise is that pictures carry the
argument. It also catches contradictions the eye slides past — an attribute
marked unique that three rivals also have, a frame with no favourability score,
an alternative set with no status-quo lane. Clear every PROBLEM before building.

`build_pdf.py` prints a **report card**. Read it. If it says a chart never
rendered, that section of the manifest is empty — go fill it rather than
shipping a deck with a hole in it.

Then hand over `report.pdf` with a short message: the positioning statement in
one line, the single most surprising finding, spend vs cap, and the run path.

## Scripts

- `scripts/pos.py` — stdlib state ledger and the **only** writer of
  `state.json`: `init`, `add`, `set`, `frontier`, `spend`, `assume`,
  `reduce-receipts`, `status`, `note`. Auto-discovers the run when there is
  exactly one.
- `scripts/extract_site.py` — marketing HTML → claims, features, pricing,
  customers, self-framing and vocabulary counts. `page`, `profile`, `vocab`.
  Use it on every fetched page; reading raw HTML yourself costs a thousand
  tokens and comes out inconsistent between competitors, which breaks the
  comparison the whole method rests on.
- `scripts/make_manifest.py` — scaffolds the manifest from `clean/` (every
  number computed, judgement left `TODO`); `--check` audits a finished one.
- `assets/DESIGN.md` — the Ramp design system: the source of truth for every
  visual decision. `scripts/theme.py` transcribes it for Python and is
  imported by both the charts and the PDF. Address tokens by name, never by
  raw hex. Run `python3 theme.py` to audit contrast — it checks every pair a
  reader has to read against WCAG and exits non-zero, so a change that hurts
  legibility fails loudly. `assets/fonts/Inter-Regular.ttf` is the spec's
  named substitute for the proprietary Lausanne.
- `scripts/charts.py` — the eight positioning visuals. Skips a chart whose
  manifest section is empty, or whose encoding would carry no information,
  rather than failing the run — and deletes any stale PNG when it does, so the
  PDF can never place last run's image. A genuine code fault is reported as
  `BUG`, separately from thin data, and exits non-zero.
- `scripts/build_pdf.py` — the visual-first PDF, plus the report card.
  `--portrait` if the reader wants letter; landscape is the default because the
  charts are wide.

See the whole template working, free, in about twenty seconds:

```bash
python3 .claude/skills/positioning/assets/make_demo.py --out /tmp/pos-demo
cp .claude/skills/positioning/assets/manifest-example.json /tmp/pos-demo/report-manifest.json
python3 .claude/skills/positioning/scripts/charts.py    --run /tmp/pos-demo
python3 .claude/skills/positioning/scripts/build_pdf.py --run /tmp/pos-demo
```

`assets/manifest-example.json` is a finished manifest for that demo — the tone
reference as much as the schema reference. Read it before writing your first
one; it shows how short every field is meant to be.

The chart and PDF scripts need `matplotlib`, `reportlab` and `pillow`; they
check on start and print the install command if absent. Everything else is
stdlib.

## References

- `references/framework.md` — Dunford's steps, what each one actually asks, and
  the data question each becomes. Read at Phase 2 and again in full at Phase 7.
- `references/instruments.md` — the exact commands, what each costs, and the
  traps. Read before the first paid call.
- `references/report-spec.md` — what the PDF is, page by page, and the rules
  that keep it a deck of pictures. Read at Phase 8.
