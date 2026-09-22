# Report spec — the PDF, the template, the manifest

Read before Phase R. The analyst reads it before Phase A, since the analyst
writes the manifest the builder renders.

The report is the product. Everything else in this skill exists to put
trustworthy insight in front of one person reading a PDF, probably on a phone,
probably once. Three failure modes matter equally: a report nobody can read, a
report that reads well but shows the reader nothing they can check, and a
report that spends its pages talking about itself instead of about the market.

## Who the reader is, and how to treat them

An outsider, and a capable one. They know their own business; they do not know
what a CPC is. The report travels without the chat, without the run directory,
without you.

1. **Explain the instrument, never the reader's intelligence.** The
   orientation page (below) does the heavy lifting once — how a search market
   works and what the four kinds of demand are. After that, introduce any
   further metric in plain words at first use and then use the short name:
   "the price an advertiser pays Google each time someone clicks their ad (the
   *cost per click*, CPC)". Never write "as you probably know", "simply",
   "obviously", or "don't worry" — the first flatters, the rest condescend.
   Never use a term the reader has not met yet: an exec who does not know how
   Google's ad auction works has to be able to read every page in order.
2. **Numbers live inside sentences.** "About 9,900 US searches a month" — never
   `sv=9900`, never a bare column name. `spend_proxy` is "monthly searches
   multiplied by the price per click" the first time it appears.
3. **Lead with the finding, then the evidence.** Every chapter opens with its
   answer in one line (`takeaway`), not with a description of the method used
   to get it.
4. **Give the reader something to do with each fact.** A number with no
   consequence is trivia. "About 158,400 searches a month are answered by
   publishers rather than by anyone selling a tub" beats "latent volume is
   158,400".
5. **Never narrate the work.** The report contains findings and the evidence
   for them — never how the findings were arrived at. No expectations that
   were later abandoned, no hypotheses, no "what would overturn this", no
   waves, no budget, no cost per call, no description of the procedure. The
   internal discipline that produced the conclusions (the conjecture register,
   the analyst's attack on its own leading explanation) stays in the run
   directory where it belongs; it is what makes the conclusions good, not
   something the reader has to audit. The market and the
   date are on the cover, and the appendices carry every row the report rests
   on; that is the whole of what the reader needs about where the figures come
   from.
6. **State findings in the strongest form the data supports, then stop.** No
   claim is *proven*, *validated* or *confirmed*, and none carries a
   confidence percentage; equally, nothing true gets hedged into uselessness.
   "Four brands hold every paid position on this term" is the right register.
   Don't seek the reader's agreement, don't apologise for the scope, and don't
   pad with the report's own virtues.
7. **Respect is concrete, not decorative.** Report a null result plainly and
   say what it bounds ("no demand is being expressed in search for this — that
   is a fact about the channel, not a verdict on the idea"). Never soften a
   finding to be pleasant. The reader should finish feeling equipped, which
   comes from clarity, complete evidence, and a clear set of options — not
   from praise.

## What makes this PDF worth what it cost

Five things, all mechanical — the builder gives them to you if the manifest is
filled in properly:

- **Page one lands the answer.** A dark cover carrying the verdict in one
  sentence, four headline numbers, and a strip of the market's actual
  advertising. A reader who looks at nothing else knows the answer and knows
  the report contains the real thing.
- **The reader is oriented before they are informed.** One page explains how a
  search market works — searches are an audience, the click price is what that
  audience is worth to the companies already there, and advertising that loses
  money gets switched off — and then defines the four kinds of demand, each one
  sized from this market with a real term as the example. Everything after it
  is legible to someone who has never bought an ad.
- **The search terms come before the argument.** The largest measured terms —
  with searches, click price and what a month of those clicks is worth — sit
  on their own page right after the summary. Every later claim rests on rows
  the reader has already seen.
- **The advertising, shown, not described.** Every creative is reproduced as a
  picture with its wording, its advertiser and how long it has run. This is the
  evidence nobody else's market report has.
- **Four ways in, stack-ranked.** The closing chapter is a decision, not a
  summary: four routes, ordered, each with the evidence that ranks it and what
  it costs the reader to take it.
- **The full data, at the back, linked from the front.** Every table, every
  row, with clickable cross-references from the chapters that use them.

## The workflow — never start from a blank manifest

```bash
# 1. charts first: the manifest should only reference charts that exist
python3 .claude/skills/demandcheck/scripts/eda_charts.py    --run <run>

# 2. scaffold: numbers, tables, chart placements, creative picks and four
#    ranked paths — computed from the corpus, prose left as TODO
python3 .claude/skills/demandcheck/scripts/make_manifest.py --run <run>

# 3. the analyst fills every TODO and edits blocks freely, then audits
python3 .claude/skills/demandcheck/scripts/make_manifest.py --run <run> --check

# 4. build
python3 .claude/skills/demandcheck/scripts/build_pdf.py    --run <run>
```

`make_manifest.py` exists so no number is ever retyped by hand and no analyst
faces an empty file. `--check` reports leftover TODOs, missing sections, fewer
or more than four paths forward, creative ids that don't exist, charts that
were never rendered, "proven/validated/confirmed" language, and any sentence
that narrates the process instead of the market. `build_pdf.py` prints a
**report card** at the end of every build listing unused charts, uncited
creatives and missing sections — read it, and go back if it names something.

To see the whole template working before you have a run, build the synthetic
demo:

```bash
python3 .claude/skills/demandcheck/assets/report-selftest/make_demo_run.py --out /tmp/dc-demo
python3 .claude/skills/demandcheck/scripts/eda_charts.py --run /tmp/dc-demo
cp .claude/skills/demandcheck/assets/manifest-example.json /tmp/dc-demo/report-manifest.json
python3 .claude/skills/demandcheck/scripts/build_pdf.py --run /tmp/dc-demo
```

`assets/manifest-example.json` is a complete, finished manifest for that demo
run — the tone reference as much as the schema reference.

## The PDF, page by page

The builder renders this fixed spine; the analyst controls the content inside
it, not the order.

| # | Page | Built from |
|---|---|---|
| 1 | **Cover** (full-bleed dark) — title, market, date, seed; the verdict panel; four key-number tiles; a strip of the market's live advertising | `title`, `seed`, `geo`, `date`, `verdict_line`, `key_numbers`, `creatives/` (automatic) |
| 2 | **Contents** (clickable, and a PDF bookmark tree) + *What's inside* | headings; `whats_inside` (optional override) |
| 3 | **The short version** — executive summary + "What stood out" cards | `executive_summary`, `highlights`, `summary_blocks` |
| 4 | **How to read this market** — three sentences on how a search market works, then the four kinds of demand, each sized and exampled from this market | automatic; `demand_primer` to override or skip |
| 5 | **The search terms behind every number here** — the largest measured terms, with a link to the full set | `clean/keywords.csv` (automatic); `key_terms` to override |
| 6+ | **Chapters 1–4** — one per page-break, each opening with its takeaway | `chapters[]` |
| | **Why the market looks this way** — the mechanics, each with its evidence and the alternative read | `explanations[]` |
| | **Four ways in** — four stack-ranked routes with their tradeoffs | `paths_forward`, `paths_lead`, `paths_close` |
| | **Glossary** | `glossary` |
| | **Appendix A — the advertising** — every creative, grouped by advertiser | `clean/ads.csv` + `clean/ad_copy.csv` + `creatives/` (automatic) |
| | **Appendix B — the full data** — every clean table, landscape | `appendix_tables` |
| | *(`--ledger` only)* **Data ledger** — the operator's cost record, never part of the reader's report | `state.json` |

Chapters 1–4 are mandatory in substance (demand verdict; how it shows up and
who captures it; how the market talks and what is earning its keep; what it
costs). The analyst may add more.

## Blocks — the chapter body language

A chapter is `{"heading", "kicker", "takeaway", "blocks": [...]}`. `blocks` is
an **ordered list**, so prose, evidence and pictures interleave in whatever
order the argument needs. Every block is `{"type": ..., ...}`:

| type | fields | use it for |
|---|---|---|
| `paragraph` | `text`, `lead` (bool — larger opening paragraph) | prose |
| `bullets` | `items[]` | a short evidence list, never more than 5 |
| `stats` | `items[{value,label,note}]`, `caption` | 3–5 numbers the chapter turns on |
| `callout` | `variant`, `title`, `text` | one idea pulled out of the flow |
| `quote` | `creative_id` **or** `text`+`attribution`, `show_image` | verbatim ad copy as a pull-quote |
| `chart` | `file`, `caption` | one chart from `charts/` |
| `table` | `columns`+`rows`, **or** `csv`+`limit`+`sort_by`+`columns`+`where`; `title`, `note` | ≤15 rows, hand-shaped or sliced live from a clean CSV |
| `creatives` | `ids[]` **or** `advertiser`/`select`/`limit`; `columns`, `title`, `intro`, `caption`, `image_height_in` | the ad exhibits — see below |
| `heading` | `text` | a sub-head inside a chapter |
| `divider`, `pagebreak` | — | pacing |

`callout` variants: `takeaway` (blue — the point), `plain` (grey — *In plain
English*, restate a finding with zero jargon), `evidence` (the numbers behind a
claim), `watch-out` (orange — something to know before acting on it),
`good-news` (green — what is working). Each supplies its own default title.

The flat legacy keys (`paragraphs`, `bullets`, `tables`, `charts` on a chapter)
still render, in that fixed order. Use `blocks`; the fixed order is what made
old reports read like a data dump.

## The ad creatives — the evidence rules

The ad images are the most valuable thing this skill collects and the easiest
thing to under-use. Rules:

1. **Every downloaded creative appears in the report.** Appendix A does this
   automatically — grouped by advertiser, longest-running first, each ad
   reproduced at its own aspect ratio with advertiser, run length, live/ended,
   format, date range, creative id, and the wording read off the image
   underneath it. Nothing to write; do not turn it off.
2. **The chapters must show creatives too.** An appendix nobody reaches is not
   evidence. Chapter 3 carries a `creatives` block of 6 exhibits and 1–2
   `quote` blocks; the scaffold pre-fills both with the longest-running ads
   whose copy was read cleanly, spread across advertisers so one brand cannot
   pass for a market.
3. **Quote from the image, never from memory.** A `quote` block with a
   `creative_id` pulls the headline, the advertiser, the run length and the
   thumbnail straight from `clean/ad_copy.csv` and `clean/ads.csv`, so the
   quote cannot drift from the source. Prefer it to hand-typed `text`.
4. **Run length is part of the quote.** "Northwind Recovery — running 412 days,
   still live" is what makes the wording evidence rather than an anecdote. The
   builder writes it for you.
5. **`ILLEGIBLE` is never filled in.** The builder shows the picture and says
   the wording could not be read. That is an honest row, and the reader can
   still see the ad.
6. **Images are scaled, never stretched.** The builder fits each image into a
   fixed well at its own aspect ratio and downscales a copy (`--thumb-px`,
   default 620) so a 300-ad gallery stays a sane file size. Originals are
   untouched in `creatives/`.

Useful flags: `--max-creatives N` caps the gallery (0 = all, the default),
`--creative-columns 2|3|4`, `--no-creative-appendix` for a run where the ad
libraries were empty.

## Four ways in — the closing chapter

The report ends on the reader's decision, not on a summary. `paths_forward` is
**exactly four** routes, stack-ranked, rendered as numbered cards with the rank
badge stepping lighter down the ladder.

```jsonc
{"rank": 1,
 "name":       "Own the practice questions with content, then sell into them",
 "thesis":     "what the route is, in one or two sentences a reader could act on",
 "evidence":   "the rows from this report that put it at this rank — named terms, volumes, prices, ads",
 "tradeoff":   "what it costs: money, time, and what you give up by choosing it",
 "best_if":    "the reader this route is right for",
 "first_step": "the first concrete move, this week"}
```

Rules that make the chapter worth the page:

1. **Four, and ranked.** Not three, not six. The ranking is the value — a list
   of options with no order pushes the decision back onto the reader.
2. **Every rank is argued from this report's own rows.** `evidence` names
   terms, volumes, prices, advertisers or ads. A rank with no numbers behind it
   is an opinion in a report the reader paid for facts from.
3. **Every route costs something, and the report says what.** `tradeoff` is
   mandatory; if a route appears to cost nothing, the analysis is incomplete.
4. **Cover the real spread.** The default four are: the strongest route the
   evidence supports; the cheapest route to a first customer; the route that
   trades cost for defensibility; and the contrarian route with the condition
   that would make it right. Reorder or replace them when the corpus argues for
   something else, but do not ship four flavours of the same move.
5. **`paths_close` is the one-line answer** for a reader who wants to be told:
   what to fund, and what to run alongside it.

## How to read this market — the orientation page

An executive reading this has never bought a Google ad and will not read a
tutorial. Page 4 is the whole mental model in one page, and the builder writes
it: three numbered beats (searches are an audience; companies bid and pay per
click, which prices that audience; losing ads get switched off, so an old ad is
a working message), then the four kinds of demand as cards — definition, this
market's size for that kind, a real example term with its numbers, and one line
on what it means for the reader.

Two things make it work, and both are automatic:

- **The examples are real.** Each card takes the largest term of its class out
  of `clean/keywords.csv`, so the definition is illustrated by this market
  rather than by a textbook.
- **The colours are the chart colours.** Each card's rule is the same hue that
  class wears in `demand_mix.png`, `demand_map.png` and `money_map.png`, so the
  charts arrive pre-labelled.

Override any of it with `demand_primer` — `{"skip": true}`, `heading`, `deck`,
`beats: [[head, body], …]`, `kinds_lead`, or a full `cards` list. Tailor the
"what it means" line when this market genuinely behaves differently; leave it
alone otherwise.

**The cover and the executive summary come before this page, so they must not
use its vocabulary.** Write the verdict as "a pool four times cheaper that
almost nobody advertises into", not "a large latent segment". `--check` flags
"direct/indirect/latent/urgent demand" appearing before it is defined. After
page 4 the terms are the reader's, and the chapters should use them.

## Linking the appendices

The evidence at the back is only useful if the front points at it. The builder
turns every heading into a PDF bookmark and a clickable contents entry, and
cross-references are real internal links:

- The early search-terms page links to Appendix B automatically.
- Any `creatives` block that shows fewer ads than were collected links to
  Appendix A automatically (`"link_appendix": false` turns it off).
- Point at a table or section from prose with a `link` block:
  `{"type": "link", "target": "Appendix B — the full data", "label": "All 412
  terms, with competition and bid ranges, in Appendix B"}`. `target` is the
  heading text; the builder resolves it to the anchor.

Link when the reader would reasonably want to check a claim or see the rest of
a set — not on every mention.

## The chart set (eda_charts.py)

All charts read `clean/*.csv` by the exact schemas in
`references/traversal.md`; each is skipped with a stderr note when its inputs
are missing or thinner than 3 points — a thin run produces a thin report, never
a crash. One message per chart, stated in its title. ~150 dpi PNGs into
`charts/`.

| # | File | Chart | The one message |
|---|---|---|---|
| 1 | `demand_mix.png` | bar: monthly searches by demand class | how big each kind of demand is |
| 2 | `cpc_by_class.png` | bar: median CPC by class (+ IQR whiskers) | what each kind of demand costs per click |
| 3 | `demand_map.png` | scatter: volume (log) vs CPC (log), coloured by class | the whole landscape on one canvas |
| 4 | `latent_gap.png` | bar: top-10 volumes among weak-auction rows | the biggest unpriced demand |
| 5 | `seasonality.png` | lines: 12-month trend, top-5 clusters | when this demand happens |
| 6 | `capture_leaders.png` | bar: advertisers by creative count, active shaded | who pays for this demand hardest |
| 7 | `ad_longevity.png` | histogram: days_running, ≥90-day bars highlighted | how much advertising has earned its keep |
| 8 | `proven_messaging.png` | grouped bar: words in ≥90-day copy vs the rest | the words sustained spend uses |
| 9 | `money_map.png` | bar: top-15 keywords by spend proxy | where the search spend concentrates |
| 10 | `format_mix.png` | bar: creatives by format | how this market advertises |

Style: the four demand-class hues are validated for colour-vision deficiency at
all pairs (`dataviz` skill's `validate_palette.js`), every series carries a
direct label or an axis label, titles are sentences, money axes carry dollar
signs, and a source line sits under each chart. Every chart in the report needs
a `caption` — the builder prints it as "**Reading this chart.** …", and a chart
without one is a chart the reader has to decode alone.

## report-manifest.json — top-level fields

```jsonc
{
  "title", "seed", "geo", "date",              // cover identity
  "verdict_line":  "one plain sentence — the cover panel",
  "key_numbers":   [{"value", "label", "note"}],        // 4 tiles
  "key_terms":     {"limit": 18},                       // or full override, or {"skip": true}
  "summary_deck":  "one line under 'The short version'",
  "executive_summary": ["paragraph", "..."],            // first one renders large
  "highlights":    [{"variant", "title", "text"}],      // 'What stood out' cards
  "whats_inside":  ["…"],                               // optional override
  "chapters":      [{"heading", "kicker", "takeaway", "blocks": [...]}],
  "explanations":  [{"name", "premises": [], "evidence", "alternative"}],
  "paths_forward": [{"rank", "name", "thesis", "evidence", "tradeoff",
                     "best_if", "first_step"}],         // exactly 4, ranked
  "paths_lead":    "one sentence framing the choice",
  "paths_close":   "if they do one thing, this is it",
  "glossary":      [{"term", "plain"}],
  "appendix_tables": [{"title", "csv", "what_it_is"}]
}
```

`explanations` renders as its own chapter after the numbered ones — don't also
write it into `chapters`. Its `evidence` field is the numbers that carry the
mechanism and its `alternative` is the other way to read them and why it loses;
both are market analysis, not an account of how the work was done. (The older
`prediction_and_check` / `rival` names still render.)

`conjectures` and `next_tests` are **not rendered** — that discipline governs
the run, never the report. `--check` will tell you if they are still in the
manifest.

Appendix tables render up to `--max-table-rows` rows each (default 2,000) and
say so when they truncate; values longer than 96 characters are shortened with
"…" and a note, because a monthly-trend string should not set a column's width.

## Delivery

`report.pdf` goes to the user — send the file, don't just name the path — with
a chat summary: the verdict line, the most surprising finding, the top-ranked
path forward, and the run directory. Spend, waves and anything else about how
the run went belong in chat if the user asks, never in the PDF.
