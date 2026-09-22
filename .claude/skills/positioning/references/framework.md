# The framework — each step, and the data question it becomes

April Dunford's method works because each step constrains the next: you cannot
know what is unique until you know what you are being compared *to*, and you
cannot pick a market frame until you know which strengths you are trying to
make obvious. Run them out of order and you get a positioning that describes
the product rather than placing it.

This file is the field manual for running the steps against real data. Read
§1–§4 before Phase 2, and the whole thing before Phase 7.

**Contents**

| § | Step | Chart it produces |
|---|---|---|
| 1 | Understand your best customers | `customer_evidence` |
| 2 | Let go of the baggage | *(no chart — a discipline)* |
| 3 | Align on vocabulary | `vocabulary_gap` |
| 4 | List true competitive alternatives | `alternatives_map` |
| 5 | Isolate unique attributes vs table stakes | `attribute_matrix` |
| 6 | Map attributes to value | `value_flow` |
| 7 | Determine who cares a lot | `segment_heat` |
| 8 | Find a market frame | `frame_quadrant` |
| 9 | Sales story, messaging, canvas | `messaging_crowd` + drawn pages |
| — | The six CSVs | schemas |

---

## §1 Understand your best customers

**What the step asks.** Not "who is our target market" — that is a plan. Who
already loves this, why, and where are more like them? Dunford's point is that
your best customers are *evidence*, and they are usually stranger and narrower
than the segment on the pitch deck.

**The data question.** *Which kinds of customer are named by the most
artefacts, and what do those artefacts say they get out of it?*

Sources, roughly in order of how much they are worth:

- **Reviews** — the strongest, because the customer wrote them. G2, Capterra
  and TrustRadius pages found via SERP; App Store reviews via
  `appstore.py reviews --sort-by most_recent` if it ships an app. Mine the
  reviewer's own description of their company, and the sentence explaining what
  changed for them.
- **Case studies** — self-selected and polished, but they name a company, a
  size and a problem.
- **Logo walls** — weak alone (a logo proves a signup, not love), but they map
  a segment cheaply. `extract_site.py` pulls them out of image alt text.
- **Job posts naming the tool** — an employer asking for experience with the
  product is unusually strong evidence of real use.

**Record one row per artefact.** Aggregating as you go hides the difference
between a segment backed by forty reviews and one backed by a single
testimonial — which is exactly the difference the chart exists to show.

**The trap.** The loudest segment on the marketing site is the one the company
*wants*, which is often not the one that stays. Where reviews disagree with the
homepage, the reviews win and the disagreement is worth a line in the notebook.

---

## §2 Let go of the baggage

**What the step asks.** In Dunford's process this is a workshop step: get the
team to stop defending the positioning they already have. You have no team, so
it becomes a discipline instead — and it is why `pos.py assume` exists.

The failure mode here is specific and it is yours, not the user's: you will
read the homepage first, absorb its framing, and then spend the whole budget
finding evidence for it. The company's own self-description is the single most
contaminating input in the study, and it arrives in Phase 1.

**So write down what you expect before Phase 2, and what would refute it.**
When the data contradicts the homepage, that contradiction is usually the most
valuable finding in the report — it is the reason the user is asking.

---

## §3 Align on vocabulary

**What the step asks.** Agree on the words. In a company this means ending the
argument about whether it is a "platform" or a "tool". Automatically, it means
something sharper and more useful.

**The data question.** *What does this company call things, and what do buyers
type into Google — and how much demand sits in the gap?*

- Left side: `extract_site.py vocab` counts the terms across the product's own
  pages and its alternatives'.
- Right side: `keywords.py search-volume` prices both the company's words and
  the market's, in one call.

The finding is almost always the same shape and almost always lands: a company
has invented a category word with 260 searches a month while its buyers type
something with 14,800. Pair them honestly — the two words must mean the same
thing to a buyer, or the chart is a trick.

**The trap.** Search volume is not the only vocabulary that matters — an
enterprise category can be real and barely searched. Where a term has low
volume but appears on every competitor's page, say so in that row's note
instead of dropping it.

---

## §4 List true competitive alternatives

**The step that carries the most weight, and the one most often done wrong.**

**What the step asks.** What would the customer do if this product did not
exist? That set is always bigger than the competitor set, and the honest answer
for most B2B products is "keep using a spreadsheet" or "keep doing nothing".

**The data question.** *What are all the routes out of this problem, and how big
is each one?*

Four lanes, and **the last two are mandatory**:

| Lane | What it is | How to find it |
|---|---|---|
| `direct` | Products sold for the same job | `<brand> alternatives`, `<brand> vs`, `ads advertisers "<brand>"` |
| `adjacent` | Tools bought for something else that absorb this job | competitors' comparison pages; `for-site` neighbours |
| `diy` | Spreadsheets, in-house scripts, manual process | `<job> template`, `<job> spreadsheet`, `<job> checklist` |
| `nothing` | Live with it; hire a person instead | `hire a <role>`, `<role> salary`, `how to <job> manually` |

Sizing them: monthly search volume for the alternative's own name or its
canonical phrase. It is a proxy, not a market share, and the report says so —
but it is a *measured* proxy, and it is the only thing that puts "Excel" and
"ServiceTitan" on one axis.

**Why the bottom two lanes matter so much.** They have no marketing team, so
they never appear in a competitor list, and a model asked for competitors will
omit them every time. They also win more deals than any vendor. A positioning
built only against `direct` will lose to inertia and never find out why.

**The trap.** Resellers, review aggregators and listicle sites appear in every
SERP for `<brand> alternatives` and are not alternatives. So do the company's
own domains. Drop them at clean time and note the drop.

---

## §5 Isolate unique attributes vs table stakes

**What the step asks.** Of everything this product can do, what can *only* it
do, relative to the alternatives from §4? Everything else is the price of
entry — true, but useless for persuading anyone.

**The data question.** *For each capability, which of the alternatives also
claim it?*

Build the matrix from evidence, one column per alternative:

- **Present** — the capability is named on their marketing or docs pages, or in
  a running ad.
- **Absent** — you looked at the pages where it would be and it is not there.
- Not the same as "I did not check". If you did not check, the honest cell is
  absent-with-a-note, and the row's evidence column says so.

Three verdicts, and `--check` enforces their consistency:

- `unique` — you have it, at most one alternative does. This is the wedge.
- `table_stakes` — you have it and so does most of the set.
- `gap` — the set has it and you do not. These belong in the report: a gap the
  reader knows about is a gap they can decide to accept.

**The trap, and it is the big one.** Marketing pages overstate. Two products
both claiming "AI-powered scheduling" may be doing entirely different things,
and a matrix built on claim-matching will call a real advantage table stakes.
Where a claim is load-bearing for the positioning, check the depth — a docs
page, a help-centre article, a pricing tier that gates it — and put what you
found in the evidence column. One verified unique attribute is worth more than
five asserted ones.

Equally: do not let a company's *phrasing* create a unique attribute. If only
they call it "auto-reshuffle" but three rivals describe the same behaviour in
other words, that is table stakes with a better name.

---

## §6 Map attributes to value

**What the step asks.** Features are not value. "Auto-reshuffle when a job
overruns" is a feature; "you finish the day you sold" is why anyone pays. The
translation runs attribute → benefit → value theme, and it is where most
positioning quietly fails, because the feature list feels like it is already
doing the work.

**The data question.** *For each unique attribute, what does it let the customer
do, and what does that let them stop losing?*

Weight the links by evidence: how many reviews, case studies or long-running
ads say that benefit. A ribbon whose weight is 1 is a claim nobody has
corroborated, and the chart makes that visible on purpose.

Two failures the chart is built to expose:

- **An attribute that reaches no theme** — a capability that translates into no
  value the customer names. It is real, and it is not a selling point.
- **A theme resting on one thin strand** — a value claim with a single
  supporting attribute is fragile: one competitor release erases it.

Aim for **three value themes**. Two is usually a product that has not found its
range; five is a list, and a list is what the reader already has.

---

## §7 Determine who cares a lot

**What the step asks.** Which customers value your specific strengths so much
that everything else about selling to them gets easier? Dunford's advice is to
segment *narrowly* — narrow targets are easier to reach, cheaper to convince
and much more likely to stay.

**The data question.** *Score each segment against each value theme: how much
does this kind of buyer care about this specific thing?*

Score 0–5 per cell, and ground each score:

- 5 — reviews from this segment name it unprompted as the reason they switched
- 3–4 — plausible from their situation and corroborated somewhere
- 1–2 — they would take it, but it is not why they buy
- 0 — irrelevant to them

The winning segment is the row that is hot **all the way across**, not the row
with the biggest population. A segment scoring 5,5,5 is a positioning; a
segment scoring 5,1,1 is one feature's audience.

**The trap.** Segment size is seductive and mostly irrelevant here. A narrow
segment that scores 19/20 will out-convert a broad one scoring 9/20, and the
narrow one is the one you can actually name in a headline. Where the user's
apparent target scores badly, say so plainly — it is the finding.

---

## §8 Find a market frame

**The step with the most leverage, and the reason this is worth doing at all.**

**What the step asks.** Which market context makes your strengths obvious? The
same product framed as a "field service management suite" is a weak also-ran
with three missing modules; framed as "HVAC dispatch software" it is the only
one that does the thing that matters. Nothing about the product changed.

**The data question.** For each candidate frame, three measured quantities and
one judged one:

| | What | Where from |
|---|---|---|
| **Demand** | monthly searches for the frame's own cluster | `keywords.py search-volume` |
| **Density** | how many entrenched players own the term | SERP + `ads advertisers` |
| **Price** | what a click costs there | keyword CPC |
| **Favourability** | *judged*: of your unique attributes, what share actually differentiate you inside this frame — 0–100 | you |

Favourability is the judgement, so make it a countable one: in this frame, how
many of your `unique` attributes are things buyers in this category are
actually comparing on? A capability that is a wedge in one frame is a
curiosity in another.

Where the candidate frames come from — never invented:

- the company's own self-framing (`extract_site.py` → `self_frames`)
- what each alternative calls its category
- the highest-volume harvested keyword clusters
- the category a review site files them under

**Reading the quadrant.** Top-right is the goal: real demand, and your
strengths differentiate. Bottom-right (big pond, you look ordinary) is where
most companies already are, because they picked the biggest category. Top-left
(strong position, small pond) is a real option and sometimes the right one —
but say what it costs: you will have to create the demand you did not find.

**The trap.** Do not recommend a frame with 720 searches a month just because
favourability is high. Say what taking it requires — that is a different and
more expensive go-to-market than entering a category that already exists — and
let the reader choose. A frame nobody searches for is a category you are
proposing to build.

**Layering a trend.** Dunford allows one, carefully: a trend makes the
positioning feel current. It goes on the canvas, not in the frame. If the trend
is doing the work of the positioning, the positioning is not doing its job.

---

## §9 Sales story, messaging, canvas

**What the step asks.** Turn the positioning into something a person can say
out loud, in the order it has to arrive in.

The story is not a feature list with adjectives. Five beats, each one only
making sense once the previous has landed:

1. **The change** — what shifted in the customer's world (not in your product)
2. **What it broke** — the cost that change created
3. **The old fix** — what people do about it now (this is §4's alternatives)
4. **Why that fails** — the specific way the old fix runs out
5. **The new way** — your unique attributes, arriving as the answer to a
   question the reader is now asking

The messaging table is one line per audience, plus the proof that makes it
credible. Keep each line under about ten words: a message that needs a
subordinate clause is not finished.

The canvas is the one page someone will photograph. Four cells (alternatives,
unique attributes, value, who cares) inside one frame, with an optional trend.
Every item a phrase, never a sentence.

`messaging_crowd` is the check on all of it: a promise six alternatives already
make is not available to you, however true it is. Take the open ground.

---

## The six CSVs

The cleaner owns these. Every row carries provenance.

**`clean/alternatives.csv`**
`name, lane, domain, volume, cpc, note, via`
`lane` ∈ direct | adjacent | diy | nothing. `volume` = monthly searches for its
name or canonical phrase.

**`clean/attributes.csv`**
`attribute, you, comp_<Name>…, verdict, evidence`
One `comp_` column per alternative you compared. Cells are 1/0. `verdict` ∈
unique | table_stakes | gap. `evidence` is the page or ad that settled the row.

**`clean/keywords.csv`**
`keyword, search_volume, cpc, competition, frame, via`
`frame` tags which candidate market frame the term belongs to — this is what
lets `frames.csv` be computed rather than guessed.

**`clean/frames.csv`**
`frame, demand_volume, cpc, density, favorability, recommended, note`
`density` = entrenched players. `favorability` 0–100 is the analyst's.
Exactly one row has `recommended` set.

**`clean/customers.csv`**
`segment, evidence_type, evidence, source_url, praise_theme`
One row per artefact. `evidence_type` ∈ reviews | case_studies | logo_wall |
job_posts.

**`clean/messaging.csv`**
`competitor, theme, claim, source, via`
`claim` is what they actually said, verbatim. `source` ∈ site | ad. The
product's own rows use its own domain in `competitor` — that is how
`make_manifest.py` knows which themes are already yours.

**`clean/vocabulary.csv`**
`yours, theirs, your_volume, their_volume, note`
One row per paired idea. Only pair terms a buyer would consider synonymous.
