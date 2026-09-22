# Hill-climbing ledger

One row per change to a rubric, a gate or a question. Every row records what
moved and what it did to the measurements, including the changes that made
things worse — a ledger that only lists successes is a sales document.

## What is measured

Run `evals/run_evals.py`. It replays frozen DataForSEO responses, so the
DataForSEO cost of an eval is **$0.00**; only genuinely new Jev questions
bill, which is what makes it affordable to re-measure after every change.

| metric | what it means | what good looks like |
|---|---|---|
| `kept_share` | candidates that survive adjudication | 0.10–0.30. A gate that keeps everything is not a gate |
| `gate_work` | share of rejections each gate is responsible for | every gate above zero |
| `discrimination` | per test: spread of answers, and share crossing 0.5 | both non-trivial |
| `rank_confidence` | Jev's confidence in the ordering it returned | > 0.5 |
| `probes_used` | billable DataForSEO calls actually made | > 1 when a thread was worth chasing |
| `trap_findings` | findings produced for a market with nothing in it | 0 |
| `usd` | real spend, from the vendors' own cost fields | — |

---

## it-1 — baseline

First working run. `project management software`, US, 3 iterations requested.

| metric | value |
|---|---|
| kept_share | **0.69** (62 of 90) |
| gate_work | `reads_true` 0.96, `changes nothing` 0.04, **`forbids` 0.00, `swappable` 0.00, `obvious` 0.00** |
| discrimination | `forbids` 100% cross 0.5 (median 0.95) · `swappable` 0% (median 0.23) · `obvious` 0% (median 0.04) · `surprising` 52% (median 0.52) |
| rank_confidence | **0.14** |
| probes_used | **1** of 3 |
| usd | $0.117 ($0.090 data + $0.027 jev) |

**Read:** three of the four gates do no work at all, and the loop never
followed anything up.

1. **The tests were pointed at the wrong object.** A claim reading *"the
   most-searched term is `pmo software` (165,000/mo at $49.28 a click)"*
   cannot be guessed from the market's name and cannot be true of sourdough
   starters — because of the numbers in it. The numbers are the evidence;
   the *interpretation* is the claim. Both tests were measuring the
   template's construction.
2. **`forbids` was tautological.** The rival statement was a direct negation
   of the claim, so "can both be true?" always answered no. It measured
   nothing about the claim's quality.
3. **Ranking asked one Choice over 60 near-identical options.** A Choice
   distributes probability across its options; at 60 options it returns
   noise, and it said so — confidence 0.14.
4. **The stop question asked the wrong thing.** "Is the picture complete?"
   is about coverage, and after 1,651 rows the answer is reasonably yes. The
   question a person actually asks is "is there anything here odd enough to
   be worth chasing?"
5. **56% of job assignments came back under 0.55 confidence**, concentrated
   in head terms (`project management software` 0.54, `microsoft project`
   0.30). That is not a taxonomy bug — a head term genuinely does not reveal
   intent — but building cells on those assignments launders uncertainty
   into confident-looking cells.

---

## it-2 — point the tests at the claim, not at the evidence

A claim carried its numbers: *"the most-searched term is `pmo software`
(165,000/mo at $49.28 a click)"*. No number is guessable from a market's
name and no number is true of sourdough starters, so **swap** and
**obvious** passed everything. Split each claim in two: `text` for the
reader, `assertion` for the tests — the same reading with every digit
removed.

Replaced the **forbids** Noul with an **account** Choice. Asking "does this
rule out its own negation?" is a question about grammar and always answers
yes; asking "which of these two accounts do the measurements support?" is a
question about data. The rival option is now a real alternative state of the
world, not a `not`.

Ranking moved from one Choice over 60 options to groups of 8, then a final
Choice between the group winners, with a finding's weight the product of the
two. A Choice spreads one unit of probability across its options; at 60 it
returns noise and says so.

Stopping moved from "is the picture complete?" (coverage — answers yes after
one expansion) to the bottom level of the gain rubric (nothing on the table
is worth the trouble).

| metric | it-1 | it-2 |
|---|---|---|
| kept_share | 0.69 | **0.20** |
| rank_confidence | 0.14 | **0.85** |
| probes_used | 1 of 3 | **3 of 3** |

## it-3 — a dead end has to be undone, not just noted

Both follow-ups came back dead, and their 1,885 irrelevant rows dropped
intent coverage from 93% to 41%. Noting a dead end while keeping its
keywords is not backtracking: the tangent stays in the corpus, crowds out
the next batch of judging, and drags the market's medians toward a market
nobody asked about.

- **Roll back the rows** a dead-end probe brought in.
- **Drop its whole class of question.** Someone who learns that expanding
  one brand name teaches nothing does not try the next brand name.
- Fixed the `branded` follow-up, which expanded on a brand and got back that
  brand's own login and help pages. The question was always what people put
  *next to* the name, so it now prices the name against the words of
  choosing and buying.

## it-4 — two bugs found by reading the numbers

**`assess_probe` was handed the global market picture** as "what came back",
not the probe's own rows. One small measurement never visibly moves a whole
market, so every probe read as a dead end. Handing it the rows the probe
actually returned: both probes then paid off (P=0.53, P=0.85).

**The confidence floor was calibrated for a 5-option Choice.** A Choice's
confidence falls as options are added, so 0.55 means something different for
an 8-option question. Replaced with a scale-free test: the winner is taken
when it is at least twice its nearest rival. Coverage 34% → 47%.

## it-5 — a pattern across nine topics is one finding, not nine

Sixteen of twenty findings were two sentences with the nouns changed
(*"project tracking software is moving down"*, *"pmo software is moving
down"*, …). Rewrote generation so each family fires **once, about the
market, naming its own extremes**. Nothing specific is lost — the
market-level sentence carries the outliers by name — and the repetition
goes. 90 candidates → 13.

Also removed from the topic set: **brands** (a cluster anchored on "asana"
makes "this cluster names a company" true by construction) and **fragments**
("management" is "task management" with the meaning taken out).

## it-6 — surprise is not a truth condition

Gating on `surprising ≥ 0.5` killed 8 of 13 true statements sitting at
0.28–0.47 — the model saying "somewhat unusual", not "wrong". Surprise is
evidence about how much a finding *matters*, not whether it is *true*.
Demoted to a reported signal and an input to ordering. `reads_true` was also
rephrased to ask against the measurements rather than six example searches,
which cannot show or refute a claim about a whole market.

| metric | it-5 | it-6 |
|---|---|---|
| kept_share | 0.08 (1 of 13) | **0.54 → 0.27 after it-7** |
| findings | 1 | **7–9, all distinct** |

## it-7 — what a thin market is allowed to say

`hvac dispatch software` returns eleven keywords and 1,340 searches a month,
and produced *"this market is shrinking: 0.33x"* in the same confident
register as a market three thousand times larger. Two changes:

- **Every claim now carries what it rests on** — the keyword count and the
  searching behind it — inside its own measurements, so the judge can see
  the basis as well as the ratio.
- **Added a claim that the market is too concentrated to read**, generated
  for every market including the ones where it is obviously false. First
  attempt asserted "there is very little searching here", which needs a
  scale reference Jev does not have (`reads_true` 0.39). Reframed as
  concentration — *"the five largest terms are N% of all of it"* — which is
  verifiable from the measurement. It is now rejected as **"the data
  supports the opposite"** on a broad market, which is the right answer.

## it-8 — jev arm against the threshold arm

Both arms, same frozen data, same four cases.

| arm | checks | mean kept_share | the market that does not exist |
|---|---|---|---|
| **jev** | **9/9** | 0.27 | **0 findings** |
| code | 7/9 | 0.94 | **1 confident finding** |

The threshold arm keeps 94% of everything it generates and reports a finding
about `ceremonial halberd resharpening for left handed accountants` — one
keyword, zero searches. That is not a tuning failure that better constants
would fix. A threshold on a ratio is still satisfied when the ratio is
computed from noise, because the constant has no way to ask whether the
thing it is dividing means anything. That is the question the whole arm is
missing, and it is the one Jev is asked.

**Known limit of the offline eval:** replaying frozen responses exercises
the judging but not the chasing — a follow-up probe's keyword list changes
when a rubric changes, so it misses the cache and the loop stops. The eval
measures what survives, not what gets chased. Testing the chase costs real
calls: `run_evals.py --live`.

---

## it-9 — three defects found by handing the skill to strangers

Two agents were given the skill and a realistic prompt and nothing else.
Both produced reports that passed every assertion, and both found bugs the
author's own testing had not. That is the argument for the exercise.

### The growth figure was measuring the season

`growth()` computed `sum(trend[-3:]) / sum(trend[:3])` and its docstring
called it "last quarter against the same quarter a year earlier". It is not.
DataForSEO returns exactly twelve months — for this account September
through August — so the comparison is **June-July-August against
September-October-November**: different parts of the year, nine months
apart.

On `garden rooms` this read as a market shrinking to 0.88x. September is the
single highest month in the entire series. A builder about to buy ads would
have been told demand was falling *as they bought into the peak month* — and
the report's own seasonality finding was sitting three lines below,
naming September as the peak.

There is no fix inside the data. Twelve months gives the shape of a year and
nothing about the level between years, and a least-squares slope over
exactly one period still varies with where the window starts. **The
`direction` family is removed**, and `kgraph.direction_is_unmeasurable()`
says why, so nobody adds it back.

### Half of every probe was buying the same answer twice

`probe_candidates` emitted both `"{facet} {topic}"` and `"{topic} {facet}"`.
Google normalises word order and returns identical volume and identical
click price for both, so every thousand-slot probe was spending five hundred
slots asking questions it had already asked.

Measured across the cached corpora, the duplication lands almost entirely in
this skill's own probes, not in Google's expansions:

| source | duplicated share of volume |
|---|---|
| `expand` (Google's own idea list) | 0–4% |
| `price` (probes this skill synthesised) | **13–42%** |

Two fixes. `probe_candidates` now emits each pair once, so a probe tests a
thousand different questions instead of five hundred twice. And `add_rows`
collapses word-order permutations on the way in, which catches Google's own
as well — 428 of them in the UK corpus.

A second layer is **not** fixable from one response: Google reports a
*combined* volume for terms it considers near-duplicates, so `insulated
garden rooms` and `insulated garden office` arrive byte-identical. Telling
those apart needs them submitted in separate requests. Recorded in
`references/graph.md` rather than papered over.

### A median click price of $0.00 on a market whose head term costs $3.80

`garden studios` showed `median click $0.00` because 44 of its 63 keywords
are long-tail terms nobody bids on — while the head term, carrying most of
the searching, goes for $3.84. An unweighted median over keywords answers a
question no advertiser asked. Replaced with a click price weighted by how
much each term is searched: `Σ(volume × cpc) / Σ(volume)`, which is what an
advertiser is actually exposed to. Same cluster, same data, $0.00 → $3.84.

### What the evals did not catch

Both arms scored 9/9 on the garden-rooms assertions — **the assertions do
not discriminate.** They check that a report cites volumes, cites prices,
states its cost and admits what it does not know, and a competent agent with
the raw `dataforseo-keywords` skill does all of that too.

The real difference showed up in the content, and not entirely in this
skill's favour. Asked about a £4,000 ad budget, the baseline ran click and
spend forecasts and pulled a competitor's live ad creatives, and answered
*"£4,000 ≈ 1,250 clicks, and on broad match the budget lasts four days"*.
This skill answered what the market is shaped like. For that prompt the
baseline's answer was more directly usable. It also took **630 seconds and
$0.36** against **365 seconds and $0.29** — and a second run of it would
have produced a different report, where this one is reproducible.

The honest reading: this skill is for understanding a market, and it should
not be reached for when the question is what a specific budget buys. The
assertions should be rewritten to test that distinction rather than the
presence of numbers.

| metric | it-8 | it-9 |
|---|---|---|
| jev checks | 9/9 | 9/9 |
| code checks | 7/9 | 8/9 |
| jev kept_share | 0.27 | 0.24 |
| distinct hypotheses per price probe | ~500 | **~1000** |

---

## it-10 — the growth figure was not unmeasurable, I was asking wrong

it-9 removed the `direction` family on the grounds that twelve months cannot
separate a trend from a season. That reasoning was right and the conclusion
was wrong, and the baseline run found out why: **`date_from` makes
DataForSEO return forty-eight months of history for the same $0.09 it
charges for twelve.** The data was there the whole time and this skill never
asked for it.

So growth comes back, computed honestly: **the last twelve months against
the twelve before them.** Both windows are complete cycles, so the season
cancels exactly rather than approximately.

On `garden rooms`, the market that exposed the original bug:

| | figure | what it is |
|---|---|---|
| old formula | 0.96x | last 3 months of the window over the first 3 — summer against autumn |
| **year on year** | **0.88x** | twelve months against the twelve before |
| peak month, one year | September | one unusual month in one year |
| **peak month, four years** | **April** | a shape that repeats |

Two things worth noticing. The old number was *closer to right than it
deserved to be* — the decline is real, and the broken formula understated
it. And the agent who caught the bug drew the wrong inference from it: they
concluded the builder was buying into the peak month, when averaged over
four years the September peak is not there. A correct diagnosis of a defect
is not the same as a correct reading of the data.

**A silent failure this uncovered.** `weighted_trend` filtered on
`len(k.trend) == 12`. When the history grew to forty-eight months it matched
nothing, returned an empty series, and the `direction` and `season` claims
stopped being generated — not rejected, never built. Nothing failed; the
report was simply quieter. It now takes its length from the data. A
hardcoded length in a filter is a trap, because the failure looks like a
finding that did not survive.

| metric | it-9 | it-10 |
|---|---|---|
| months of history per call | 12 | **48** |
| cost per call | $0.09 | **$0.09** |
| jev checks (live) | 9/9 | **9/9** |
| dead-end probes across the suite | 1 | **0** |

Refreshing the frozen fixtures with the longer history cost $0.74, which is
what an eval suite costs when the shape of the data changes. It does not
recur.
