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

---

## it-11 — a joint model instead of thirteen separate opinions

Until now, Jev answered about thirteen independent questions and code
composed them with `and`. That is flat: findings could not constrain one
another, evidence could not propagate, and any question the report did not
anticipate cost another request.

Frank Dellaert's observation is that a Choice over outcomes is exactly the
shape of a conditional probability table row, so one batched request can
supply a whole Bayes network zero-shot, and a conventional engine then
answers an unbounded family of queries with **no further model call**. That
is this skill's own contract at the level of a joint distribution.

Five latent properties, eight measurements, two conclusions. 63 table rows,
one request, **$0.0006**. Inference enumerates the five roots — thirty-two
states — exactly, in pure Python.

### The tables diagnosed the questions

First elicitation: the prior for `growing` came back **0.00**. No market
ever grows. `free_substitute` 0.07, `intent_legible` 0.12, and `o_money`
0.10 against 0.01 — barely informative.

Not a model failure. `growing` was asking *"demand is larger this year than
last, **and rising rather than merely fluctuating**"* — two claims bundled —
of a market with nothing known about it. Read literally, with no reference
class, the honest answer is no. And a prior **is** a reference class: it is
the base rate over all markets, so it has to be asked as one.

Reframed: every statement made atomic and, where it needs one, comparative
("advertisers pay more per click here than in a typical market"); root
questions posed as *"think of every commercial market people search for on
Google; one is picked at random"*.

| | before | after |
|---|---|---|
| prior, `growing` | 0.00 | 0.42 |
| prior, `demand_real` | 0.66 | 0.92 |
| informative measurements | 4 of 8 | **7 of 8** |

### The structure was audited for $0.000078

Asked which property each measurement is evidence about, Jev agreed with six
of eight hand-drawn edges and corrected two — `o_spread` to `category_open`,
and `o_brand` to a second parent under `intent_legible`, since a search
naming a company is both a settled category and legible intent. Both
corrections were right. After them, `o_spread`'s spread went from 0.21 to
0.52.

"I guessed the structure" is an expensive thing to leave unchecked when
checking it costs eight hundredths of a cent.

### Two conclusions were dropped because the model said they were empty

`content_viable` — can you earn customers by being found? Asked which
properties bear on it, Jev gave the identical sign pattern it gave paid
advertising, at near-total confidence. That is the model saying nothing here
tells the two apart, and it is right: keyword data says what people want and
what a click costs, and nothing whatever about whether you could rank. A
number for it would have asserted something the instrument cannot see.

`niche_entry` returned 0.26–0.38 confidence on every property — a badly
specified variable, not a hard one. Its replacement `head_is_a_trap` came
back with a **flat table**, 0.58 to 0.69 across all eight rows. Also right:
whether the head term is a trap turns on the measured price gap between head
and tail, which the data states outright rather than hiding.

Two nodes that move beat three where one does not.

| node | CPT spread | kept |
|---|---|---|
| `paid_viable` | 0.91 | yes |
| `incumbents_hold_it` | 0.79 | yes |
| `head_is_a_trap` | 0.11 | no |

### The DECIDE step is now arithmetic

Expected entropy reduction over the two conclusions, computed exactly,
replaces asking a model to rate how useful a probe would be. First version
scored an already-observed node at zero and stopped the loop after one
iteration every time — wrong semantics: a probe does not supply a missing
observation, it **settles one already held softly**. Weighing each outcome by
how likely it currently looks fixed it. The loop now picks, for example, a
0.297-bit question about whether searchers still name companies.

### What it reads on a market with a known answer

`sourdough starter`, from the data alone:

| | before | after |
|---|---:|---:|
| Many people here solve this themselves for free | 36% | **77%** |
| People here are willing to pay someone | 92% | 74% |
| More people search for this than a year ago | 43% | 95% |
| **Search ads can pay for themselves** | 69% | **54%** |

It inferred that home baking is a do-it-yourself market, and said which
measurement did it (−0.12 from the free-route share).

**Calibration remains unverified** and the report says so. The Asia network
Dellaert demonstrated on is famous enough to sit in any training set; this
one is not, which removes that taint and removes the reassurance with it.
The evals check that posteriors move the right way under evidence, which is
a weaker claim than being right.

| metric | it-10 | it-11 |
|---|---|---|
| selftest | 43 | **54** |
| jev eval checks | 9/9 | **18/18** |
| cost of re-inferring after new evidence | one request | **cached — $0.0003** |

---

## it-12 — what it would cost to act

The baselines beat this skill on the ad-budget prompt, and the ledger said
why: one answered *"£4,000 ≈ 1,250 clicks; on broad match your budget lasts
four days"* and this one answered *"89% shopping intent"*. One changes what
someone does on Monday.

Every run now closes with `ad_traffic_by_keywords` on the searches worth
bidding on — `buy`, `compare` and `local` intents only, because forecasting
clicks from people reading definitions and hunting jobs prices a market that
does not exist. The bid is the median top-of-page bid already measured on
those keywords, so nothing about it is invented.

**Search volume and buyable clicks are different numbers, usually by an
order of magnitude.** Five project-management head terms carrying 165,000
searches a month forecast **232 clicks** at a $12 bid. A reader who sized a
budget from the volume would be out by a factor of seven hundred.

Two things the call gives away that nothing else does:

- **You do not pay your bid.** $12 bid, $8.00 actual — the auction saying
  how much of your maximum it needs.
- **A market can have less to sell than you were going to spend.** The most
  useful sentence the report can produce is not "this will cost you X" but
  "X is more than this market has; the constraint is not your budget".

Three defects found and fixed on the way in:

1. `_geo` added `date_from` to every call, and the forecast endpoint rejects
   it outright — correctly, since there is no history in a prediction. It
   failed loudly rather than billing wrongly.
2. The endpoint returns **one aggregate row with `keyword: null`**, not a
   row per keyword. The first normaliser dropped it for having no keyword
   and reported zero clicks with a straight face.
3. `--dry-run` under-counted the ceiling by one call.

| metric | it-11 | it-12 |
|---|---|---|
| selftest | 54 | **58** |
| jev eval checks | 18/18 | **22/22** |
| code arm | 17/22 | 17/22 |
| default run cost | ~$0.28 | **~$0.37** |

The extra nine cents buys the only number in the report a reader can put in
a spreadsheet.

**A note on the control arm.** It now fails five checks to the judged arm's
zero, but two of those failures are an artifact: the arms select different
claims, so they chase different probes, so the threshold arm's forecast
keywords miss the frozen cache. The comparison that matters is unchanged —
it keeps 86% of everything it generates, against 28%, and still reports a
confident finding about the market that does not exist.

---

## it-13 — the seed should be a business, not a word

The opening move was `for-keywords` on the seed. That expands off the
breadth of a *string*, and this skill kept meeting markets where a string
has no breadth:

| seed | keywords returned |
|---|---:|
| `meal planning` | 24,028 |
| `project management software` | 1,651 |
| `aksjetips` | 48 |
| `epcr` | 31 |
| `ambulance software` | 25 |
| `investtech` | 18 |

Every thin, disappointing run in this ledger is in the bottom half of that
table. The fix is to stop seeding with words. Same market, same $0.09:

| | keywords | searches a month |
|---|---:|---:|
| `expand "epcr"` | 31 | 2,100 |
| **`for-site eso.com`** | **619** | **367,940** |

A site expands off what a live business is *about*, and a business that has
paid to rank is evidence somebody is selling here. Invented keywords are
hypotheses; harvested ones are observed commercial vocabulary. It also
reaches words no expansion could — `electronic health records software` at
40,500 a month is the market ambulance software sits inside, and nobody
would have thought to seed it.

So the opening move is now: search the seed, ask Jev which result is a
company actually selling into this market, and harvest that company.

### Finding nobody who sells is the finding

The fallback matters as much as the move. When no focused seller ranks, the
loop says so and falls through to Google's idea list. That is the most
decisive thing it can learn about a market, and it is exactly the shape of
the EWA and Investtech results.

### The trap, and the guard

A business is wider than its market. Harvesting Radar Healthcare for
`ambulance software` returned **503,680 searches a month of which 680 were
ambulances** — the rest was the whole of UK healthcare, led by `health
information management` at 33,100 a month.

Left in, that is not noise. **Topics are mined by volume**, so the
incumbent's other business outvotes the market's own vocabulary and the
report comes out about the wrong thing. A regex cannot fix it either: the
market's real vocabulary contains words the seed never held, which is the
whole point of harvesting.

So every harvested search is asked whether it belongs to the market before
it counts. On that run it kept **69 of 400**, carrying 20% of the harvested
volume.

| | before the gate | after |
|---|---:|---:|
| intent coverage | 46% | **60%** |
| findings surviving | 3 | **5** |
| forecast | 26 clicks at $7.74 | 4 clicks at $10.85 |

Upstream, `pick_sellers` now separates a focused seller from one that
"sells this among many other things", and only falls back to the broader
business when no focused one ranks.

### What this costs, and what it corrects

The opening move goes from one call to one search plus `--sites` calls
(default 2), so a default run is about $0.55 rather than $0.37.

It also corrects a report written from the old opening move. The EWA
analysis concluded this market carries "about 340 searches a month with
clear commercial intent" from a 31-keyword corpus; harvested, the same
market carries 98,800 on-market searches. The corpus was ~290x too small.
Its *recommendation* survives — only 38 to 45 of those searches carry a
biddable top-of-page bid, forecasting 4 to 26 clicks a month — but the
market description in it was wrong, which is what a 31-keyword corpus buys.

### Measured, live, both before and after

| case | findings before | after | candidates before | after |
|---|---:|---:|---:|---:|
| broad-competitive | 4 | 3 | 12 | 14 |
| consumer-seasonal | 3 | 5 | 10 | 13 |
| **thin-niche** | **3** | **6** | **6** | **14** |
| trap-nonexistent | 0 | **0** | 1 | 1 |

Candidates rose in every market, because there is more corpus to build them
from. The thin niche — the case this was for — **doubled its findings on a
corpus more than twice the size**, and the market that does not exist still
returns nothing, which is the check that matters most: a move that finds
more in every market including the empty one would be finding noise.

| | it-12 | it-13 |
|---|---|---|
| jev eval checks | 22/22 | **22/22** |
| mean kept_share | 0.32 | 0.26 |
| selftest | 58 | **65** |
| suite cost (live) | $0.74 | $0.87 |
