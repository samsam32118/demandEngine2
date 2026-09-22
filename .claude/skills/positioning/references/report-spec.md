# Report spec — a deck of pictures

Read before Phase 8. The analyst reads it before Phase 7, because the analyst
writes the manifest this renders.

The report is the product. Everything else in this skill exists to put one
person in front of a PDF, probably once, probably on a laptop in a meeting they
are about to speak in. They should be able to flip through it in ninety seconds
and come out able to make three decisions.

## The one rule everything else follows from

**Pictures carry the argument. Text labels the picture.**

This is not a house style. Positioning is a set of comparisons — you against
nine alternatives, one frame against five others, one segment against four
others — and prose forces the reader to hold all of that in their head while
you describe it one item at a time. A grid shows it at once. Every time you are
tempted to explain a chart, the honest move is to fix the chart.

What that means concretely, and `make_manifest.py --check` enforces all of it:

| Slot | Ceiling | What it is for |
|---|---|---|
| positioning statement | 330 chars | the whole position, on the cover |
| `answer.*.why` | 230 | why that decision, on the three-card page |
| `notes.*` | 190 | one "so what" line under a chart |
| `sales_story.line` | 135 | one beat |
| `messages.line` | 75 | something a person can say out loud |
| `canvas` item | 60 | a phrase, never a sentence |

There is nowhere in the manifest to put a paragraph. That is deliberate. If a
finding will not fit, it is two findings or it is not sharp yet.

## The visual system

`assets/DESIGN.md` is the source of truth for every visual decision — the Ramp
design system, from designmd.directory. `scripts/theme.py` transcribes it for
Python and both `charts.py` and `build_pdf.py` import that, so a colour cannot
mean one thing in a chart and another on the page around it. Address tokens by
name (`T.c("primary")`, `ts("display-md")`), never by raw hex: the token
carries the reasoning and the hex does not.

Three rules from the spec do real work in the code:

- **One weight.** Lausanne is proprietary; Inter 400 ships with the skill as
  the canonical substitute. Every tier renders at 400 and hierarchy comes from
  size alone. There is no bold anywhere in this report, and `T.weight()` is a
  function so a call site asking for a weight gets the only answer the system
  has.
- **One voltage.** Yellow `primary` is the only filled brand colour, reserved
  for the product being positioned and the single recommendation. It is a
  **fill, never text** — yellow is ~1.3:1 on white, so every yellow shape
  carries a 1px ink edge and every label on yellow is `on-primary` ink.
  Everything the product is measured against uses the ink ladder, because the
  spec forbids a secondary accent.
- **Sand, not white.** The page is `canvas-sand`; each chart is a white tile
  with a hairline border and 12px corners floating on it. That contrast is the
  entire elevation model — this system has no shadow tier, and adding one
  breaks the register.

`python3 scripts/theme.py` audits every foreground/background pair a reader has
to read against WCAG and exits non-zero on a failure. Run it after any visual
change.

## Who the reader is

The founder, or the person who owns go-to-market. They know their product
better than you ever will. They do **not** know what a CPC is, and they have
never thought about their category as a choice.

1. **Explain the instrument, never the reader.** Charts carry their own
   one-line explanation of what they show. Never write "as you know",
   "obviously", "simply", or "don't worry".
2. **Numbers live inside phrases.** "27k searches a month" — never `sv=27100`,
   never a bare column name.
3. **Lead with the finding.** Every chart's title is its conclusion, not its
   subject. "Compete as: HVAC dispatch software" beats "Market frame analysis".
4. **Never narrate the study.** No waves, no budget, no method, no "we
   fetched", no hypotheses that were later dropped. The assumption register and
   the ledger are what make the conclusions good; they are not content. The
   appendix carries every row, and that is the whole of what the reader needs
   about provenance.
5. **State findings at full strength, then stop.** Nothing is *proven*,
   *validated* or *confirmed*, and nothing carries a confidence percentage.
   Equally, nothing true gets hedged into mush. "Four of your nine alternatives
   are not software" is the right register.
6. **Report the awkward finding plainly.** If the user's apparent target
   segment scores worst, that is the most valuable page in the deck. Say it
   without softening and without gloating.

## The spine

`build_pdf.py` renders this fixed order. The analyst controls what is in each
page, not which pages exist.

| # | Page | Built from |
|---|---|---|
| 1 | **Cover**, full-bleed dark — product, URL, date, the positioning statement, four key numbers | `product`, `statement`, `key_numbers` |
| 2 | **The short version** — three cards: compete as / sell to / win on | `answer` |
| 3 | Step 1 — **who already loves it** | `customer_evidence` + `notes.customers_note` |
| 4 | Step 2 — **your words vs your buyers' words** | `vocabulary_gap` |
| 5 | Step 3 — **what they would do instead** | `alternatives_map` |
| 6 | Step 4 — **what is only yours** | `attribute_matrix` |
| 7 | Step 5 — **features into value** | `value_flow` |
| 8 | Step 6 — **who cares a lot** | `segment_heat` |
| 9 | Step 7 — **which category to compete in** | `frame_quadrant` |
| 10 | Step 8 — **what everyone says, and what is open** | `messaging_crowd` |
| 11 | **The positioning canvas** — the page they photograph | `canvas` |
| 12 | **The sales story** — five chevrons, in order | `sales_story` |
| 13 | **Messaging** — audience, line, proof | `messages` |
| 14+ | **Appendix** — every row the deck rests on | `appendix_tables`, `sources` |

A step page whose chart did not render is **dropped, not padded with text**. A
deck with six good pages beats one with eight where two are apologies. The
report card at the end of the build names every drop — read it, and go back and
fill the manifest section rather than shipping the hole.

A chart also declines to draw when its encoding would carry no information —
`customer_evidence` refuses when every segment has an identical count, because
bars that all run to full width read as "maximal" about evidence that is one
line on a marketing page. That is not a failure to report around; the thin
evidence *is* the finding, and it belongs in the note. When a chart skips,
`charts.py` deletes any PNG a previous run left behind, so a stale image can
never be placed as though it were current.

## What makes this deck worth what it cost

- **Page one lands the position.** A reader who sees nothing else gets the
  statement and four numbers that prove it was measured.
- **Page two is three decisions**, not a summary. Compete as, sell to, win on.
- **The comparison grid is the evidence nobody else's positioning deck has.**
  Most positioning work asserts uniqueness. This one shows the matrix, names
  the alternatives, and marks the gaps as well as the wedges.
- **The frame quadrant turns a taste argument into a reading.** Demand on one
  axis, how good you look on the other, crowding as the bubble. The choice
  becomes visible.
- **The status quo is on the map.** Spreadsheets and doing-nothing get lanes,
  sized the same way as the funded competitors.
- **The full data is at the back.** Every figure traces to a row.

## The eight "so what" lines

Each chart page may carry one line under the picture, in `notes.*`. Use it for
the consequence, never for a description of the chart:

- Bad: "This chart shows how many alternatives claim each message."
- Bad: "As you can see, ServiceTitan dominates."
- Good: "Three of your four strongest claims are already made by everyone
  selling into this market."

Leaving a note blank is fine and often right. A chart that needs no line is
working.

## Before you build

```bash
make_manifest.py --run <run> --check    # fails on prose, TODOs, contradictions
charts.py        --run <run>
build_pdf.py     --run <run>            # read the report card it prints
```

`--check` catches the things a reader would notice and you would not: an
attribute marked unique that three alternatives also have, an alternative set
with no status-quo lane, a value-flow link pointing at a node that does not
exist, a score matrix whose shape does not match its own labels. These are not
style warnings. Each one is something that would be visibly wrong on the page.
