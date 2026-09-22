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

---

## it-14 — an audit of every call, and a fix that had to be thrown away

Forty billable calls across this session's runs, $3.60. The audit:

| | |
|---|---|
| dead-end probes | **16 of 40 calls — $1.44, bought then discarded** |
| runs ending on a dead end | 3 of the last 4 |
| second harvested site | 120 keywords, against the first's 1,542 |
| forecast | ran last, so a run could spend its budget before reaching it |

Forty per cent of the money went on measurements the loop judged useless
**after paying for them**.

### The obvious fix was measured, and it was worse

Ask Jev whether a probe is worth buying *before* the money moves: two
hundredths of a cent against nine cents, so it pays for itself at any
accuracy above chance. Replayed against all 29 historical probes:

| | |
|---|---|
| dead ends caught | 4 of 14 — $0.36 saved |
| good probes wrongly skipped | 9 of 15 — **$0.81 lost** |
| **net** | **−$0.45** |

Both questions were aimed at the wrong thing. For a price probe it asked
"do these read as phrases people actually type?", and the honest answer for
synthesised combinations is no — which is the *premise* of a price probe,
not an objection to it. Most guesses miss; the few that land are the value.
For an expansion it asked whether the seed was a broad category, but the
dead expansions were on topics from inside the market, which all read as
categories.

**The information was not in the request.** Reverted.

### What is predictive is the template, and it is measurable

| follow-up | paid off | dead | hit rate |
|---|---:|---:|---:|
| `diy`, `money`, `minority`, `growth` | 12 | 0 | **100%** |
| `outlier` | 2 | 2 | 50% |
| `adjacent` | 1 | 2 | 33% |
| `movers` | 1 | 7 | **12%** |
| `brands` | 0 | 5 | **0%** |

`brands` and `movers`: **13 probes, 1 payoff, $1.17.** That is where the
waste lives, and it is mechanistic rather than random. `brands` priced
`<brand> vs / alternative / pricing` combinations, which Google barely
holds; `movers` expanded on topic fragments already in the corpus.

So the loop now ranks by **expected bits per call** — the network's
information gain times the measured hit rate of that kind of question. The
record lives on disk and every run adds to it, so the estimate sharpens
with use. Every term is computed or observed; none is asserted.

And `brands` was not merely down-weighted, it was **replaced**: the question
it was asking — what vocabulary are these suppliers built on — is answered
properly by harvesting that supplier's site, for the same $0.09 and twenty
times the rows. The worst template became the best mechanism.

### The one constant in the loop, stated as such

A probe must be expected to remove at least **0.01 bits** — a hundredth of a
yes/no answer — about what the reader came for. This is a chosen number, not
a measured or structural one, so it is named, stated in units that can be
argued with, and kept in one place.

It had to become final, too. Declining a probe first fell through to asking
Jev for a second opinion, which promptly bought one worth **0.0002 expected
bits**. A floor that can be talked out of is not a floor: the fallback now
fires only when the network cannot price a question at all, never when it
has priced it at nearly nothing.

### Sites are bought one at a time

Yields are wildly unequal and unknowable before buying — 1,542 usable
keywords from one harvest, 120 from the next — so buying two up front spends
$0.09 on a coin flip. Buy one, gate it for relevance, and buy another only
if there is still not enough to run the analysis on. That is a question
about having enough data, not about quality, so code settles it.

### The forecast's money is reserved

It is the one call that answers what the reader came with, and it runs last.
Its $0.09 is now held back from the probe budget so a run cannot spend
everything on questions and then be unable to afford the answer.

---

## it-15 — checking the bill against the vendor's rate card

Every cost in this ledger came from the `cost` field DataForSEO returns, and
the flat $0.09 came from the sibling skill's documentation. Neither had been
checked against what the vendor actually publishes.

**Confirmed, two ways.** All 91 cached calls across four endpoints, with row
counts from 1 to 24,028, billed exactly $0.09 — and the rate card the API
serves at `/v3/appendix/user_data` gives `cost_type: per_request, cost:
0.09` for every Google Ads endpoint, at every priority. There is no cheaper
queue mode: only `live` is listed for them.

**But there are two billing models, and we were on the wrong one for a
quarter of our calls.** DataForSEO Labs charges `$0.012 per request +
$0.00012 per row`. The two cross at **650 rows**.

| our call | calls | median rows | flat | per-row | right endpoint |
|---|---:|---:|---:|---:|---|
| `for-keywords` | 40 | 513 | $3.60 | $7.52 | flat — already right |
| `for-site` | 8 | 1,071 | $0.72 | $0.96 | flat — already right |
| **`search_volume`** | 27 | 134 | **$2.43** | **$1.35** | **per-row** |
| `ad_traffic` | 16 | 1 | $1.44 | — | no alternative exists |

The rule that falls out is about the request, not a preference: **pay per
row when the size is bounded, pay flat when it is not.** An expansion can
return anything — one in this session returned 24,028 rows, which would be
$2.90 per-row — so the flat rate is insurance. Pricing a list cannot return
more rows than it was given, so its cost is bounded and per-row wins.

### The trade, stated

Head to head on the same 600 keywords:

| | cost | keywords with volume |
|---|---:|---:|
| Google Ads | $0.090 | 125 |
| per-row | **$0.025** | 103 (82%) |

Volumes agree on 94% of what both hold. The 18% missed are real, including
`template project planning` at 12,100 a month, because the per-row endpoint
answers only for keywords in its own database — while the flat one returns a
row for every keyword sent and bills the same whether it carries anything.
**Across all our calls, 71% of the rows the flat endpoint returned carried
no volume at all.**

Cost per keyword actually found decides it: **$0.00072 against $0.00024**,
three times cheaper. And the loss falls on the least critical call, since a
price probe tests a direction while the corpus comes from the site harvest,
which stays on the flat rate.

It also returns **94 months of history rather than 48**, which is a free
upgrade to every trend figure.

### Where a run's money goes now

| | before it-14 | now |
|---|---:|---:|
| opening | 1 expansion, $0.09 | 1–2 harvests, $0.09–0.18 |
| probes | 2 × $0.09 | 1–2 × ~$0.02 |
| forecast | $0.09 | $0.09 |
| **typical run** | **$0.45** | **$0.22–0.31** |

---

## it-16 — one dial, and two bugs it uncovered

`--iterations` was the only knob, and raising it made the report worse.
More probes grow the corpus; nothing else grew with it, so a larger share
of what was measured never got read. The fix is a single `--effort` dial,
1 to 5, moving five things together: sites harvested, probes allowed,
corpus placed on the two axes, claims tested, spend ceiling.

**The dial is the bits floor.** A probe costs $0.09 and buys some expected
reduction in uncertainty about what the reader came for, so the only real
question is *how small an answer will you pay $0.09 for* — 0.05 of a bit at
effort 1, 0.002 at effort 5. That retires the one arbitrary constant in the
loop: `MIN_EXPECTED_BITS = 0.01` was a number I picked, and it is now the
caller's choice in units they can argue with.

### The first ladder was measuring a bug

| effort | sites | probes | $data | keywords | coverage | findings |
|---|---:|---:|---:|---:|---:|---:|
| 1 glance | 1 | 0 | 0.27 | 97 | 30% | 2 |
| 3 normal | 2 | 2 | 0.39 | 1,648 | 60% | 6 |
| 4 deep | 3 | 1 | 0.54 | 1,838 | **43%** | 3 |
| 5 exhaustive | 4 | 0 | 0.54 | 1,516 | 63% | 4 |

Effort 4 is worse than both its neighbours, which is not a thing a dial is
allowed to do. The cause was `--relevance-cap`: the filter that decides
whether a harvested keyword belongs to this market reads the top N by
volume and **admitted everything below N without asking**.

Sorting by volume checks the incumbent's largest pages first — the ones
most likely to be its *other* business — so it was fair to wonder whether
the tail was cleaner than the head. It is not. Of 200 sampled from Radar
Healthcare's 1,467 unchecked keywords, **17% belonged to this market,
against 18% of the 400 that were checked**. The cap was admitting about
1,200 off-market terms into a 1,648-term corpus. Only the volume weighting
— the tail is 79% of the terms and 5% of the searching — had been keeping
the reports usable.

**Two fixes.** An unchecked keyword is no longer admitted; and the cap
stopped being an effort knob. A harvest costs $0.09 whether or not anyone
reads it, and vetting a keyword costs about a hundred-thousandth of a cent,
so leaving rows you already bought unread to save $0.016 of judgment is
backwards. Vetting the whole 1,867-row harvest took Jev from $0.005 to
$0.022 — 5% of a run's bill — and found 336 in-market keywords where the
capped filter found 72.

### The ladder, measured properly

Three runs at each level, Jev cache off so every run asks fresh:

| effort | sites | probes | keywords | coverage | findings | $data | $jev |
|---|---:|---:|---:|---:|---:|---:|---:|
| 1 glance | 1 | 0 | ~95 | 23–29% | 4, 4, 4 | 0.24 | 0.005 |
| 3 normal | 2 | 1–2 | 434–735 | 42–57% | 3, 4, 6 | 0.48 | 0.025 |
| 5 exhaustive | 4 | 2–3 | 731–1,027 | 44–64% | 4, 5, 5 | 0.68 | 0.035 |

**Effort buys coverage, not findings.** The spread in findings within one
level (3 to 6 at normal) is as wide as the spread across the whole dial.
Two findings either way is noise, and an earlier draft of this entry
explained a 6-versus-4 difference as "higher effort produces better-tested
findings" — a story about a number that turned out to be a coin flip. What
actually moves is the share of the market a finding is about: 25% → 50% →
57% of the searching, monotone in the means.

Findings are a count of judgments made one claim at a time, and near the
0.5 line they go either way between runs. Coverage is arithmetic over the
whole corpus. That is why the ladder is read on coverage, and why
`kept_share` is reported as a band rather than a number.

### Two bugs found while measuring

**The forecast bid.** DataForSEO documents `bid` as an integer and enforces
it unevenly: £24.11 and £10.38 went through, £32.73 came back `50301:
Request contains an invalid argument`, naming no field. A run that had
already spent $0.45 on harvesting silently lost its closing forecast — the
single most useful call in the report — to a rounding decision made three
functions away. The rounding now happens at the wire, where the contract
is. Two selftest checks pin it.

**A stray paste in the control arm.** `select_by_code` carried a block of
follow-up-table code in its `settled` branch, calling an `add` that does
not exist in that scope. It had never fired, because no corpus the code arm
had seen produced a `settled` claim; the bigger vetted corpus produced one
and the arm crashed with a `NameError`. `settled` now has a threshold like
its siblings, using the `branded_share_high` constant that the paste had
displaced.

Neither bug was what I was looking for. Both were found by running the same
thing at five settings and asking why one rung was out of line.

### Where the suite ended up

| | before it-16 | after |
|---|---:|---:|
| jev checks | 22/22 | **18/18** |
| code checks | 5/8 (crashed on one case) | **17/18** |
| jev `kept_share` | 0.26 | 0.31 |
| code `kept_share` | 0.86 | 0.86 |

The suite lost four checks and gained a working control arm. Two of the
lost checks were `must_mention` phrases from the section that prices the
move, and they were not measuring the method: that section is downstream of
a forecast call, which is downstream of which keywords Jev placed as
biddable, so one divergent judgment sends an offline run down an uncached
path and the call misses. A check that fails for that reason is noise in
the suite, so the renderer is pinned in `selftest.py` against a forecast
row supplied directly, and the cases test the method. The other two came
with `thin-niche`.

**`thin-niche` stopped being thin.** The case was written for an
eleven-keyword market. Harvesting from the businesses that rank (it-13)
opens `hvac dispatch software` into the whole field-service-management
category — 907 keywords, 649,450 searches a month — and being confident
about *that* is correct. The case now sets `no_harvest`, because what it
exists to test is the register used on a thin corpus, and it has to keep
one to test it.

The one remaining failure is `trap-nonexistent/code`, and it is supposed to
be there: it is it-8's result, still standing. The threshold arm reports a
confident finding about a market that does not exist, because a threshold
on a ratio is still satisfied when the ratio is computed from noise.

Two harness changes came out of this. The probes column prints probes
*followed* rather than probes *billed* — on a warm cache the billed count
is zero, so the ledger's "did it chase anything" metric had been silently
reading as "no". And `coverage` is now scored, because it is the metric
that responds to effort.

---

## it-17 — a filter on one of two doors is not a filter

it-16 fixed the relevance filter to fail closed, and left it where it had
always been: on site harvests only. That placement was a guess about where
off-market keywords come from, and the first live run after the fix showed
the guess was wrong.

Running `https://answerthepublic.com/en` at effort 5: the two site harvests
were clean, and **71% of the corpus volume arrived through probe
expansions**, never vetted. The single largest term in the market was
`adwords for google` at 550,000 searches a month — people looking for
Google Ads, a different product — carrying 28% of the whole corpus on its
own. `gaming keywords` at 22,200 came in the same way and became one of the
twenty topics the report drew conclusions across.

`observe()` called `add_rows` and returned. A site harvest is a business's
whole footprint and an expansion is Google's idea list for a string; both
are wider than the market, and only one was being checked.

The vetting is now a method both paths call.

| | before | after |
|---|---:|---:|
| keywords | 1,649 | 849 |
| searches a month | 1,941,380 | 873,950 |
| volume from unvetted expansions | **71%** | 0% |
| intent resolved (coverage) | 75% | **78%** |
| findings | 6 | 5 |
| P(paid channel pays for itself) | 0.48 | 0.51 |
| P(incumbents hold it) | 0.44 | **0.28** |
| DataForSEO | $0.61 | $0.12 |

The market halved and got more legible. `incumbents_hold_it` fell from 0.44
to 0.28 because the 46% branded share that drove it was largely `adwords`
and `keyword planner` — Google's own products, named by people searching
for Google, not evidence that buyers of *this* category have settled on a
supplier. That is the reading a competitor would have acted on, and it was
wrong.

Suite unchanged at 18/18 jev, selftest 69/69. The cost of the extra
judgment is real but small: Jev per run went from $0.051 to $0.039 here,
because vetting earlier means judging a smaller corpus later.

---

## it-18 — a set that was written, read, and never added to

`self.chased` is initialised in the constructor and read in three places,
all of them filtering out threads already followed. Nothing ever put
anything in it. The only memory the loop had was `dead_tags`, populated on
a dead end — so a question that *paid off* was regenerated next iteration
and bought again.

On `cad to bim tool` at effort 5 the trail reads:

```
[paid_off] These searchers already name their suppliers — are they still choosing
[dead_end] These searchers already name their suppliers — are they still choosing
[paid_off] People are trying to avoid paying — what are they reaching for instead
[paid_off] People are trying to avoid paying — what are they reaching for instead
[paid_off] People are trying to avoid paying — what are they reaching for instead
[paid_off] People are trying to avoid paying — what are they reaching for instead
[paid_off] People are trying to avoid paying — what are they reaching for instead
```

Five of eight iterations on one question, three of them byte-identical
replays served from cache. The backtracking machinery was working
perfectly and the loop had no way to remember success.

**And an empty sample was being judged.** The last three of those probes
returned 17 rows, all 17 dropped by the relevance filter (it-17), leaving
nothing — and `assess_probe` was asked whether that nothing bore on the
question. It answered `P=0.51`, a coin flip that reads as "answered",
which kept the thread alive to be bought again. A probe whose entire yield
is off-market is a dead end by definition; it no longer costs a question
to find that out.

| | before | after |
|---|---:|---:|
| probes bought | 7 | **2** |
| keywords | 663 | 663 |
| coverage | 56% | 56% |
| findings | 6 | 6 |
| DataForSEO | $0.599 | $0.294 |

Identical corpus, identical findings, five fewer probes. The extra five
bought nothing, which is the cleanest possible evidence they should never
have been bought.

Suite 18/18 jev, 17/18 code, selftest 69/69 — unchanged, because no eval
case ran long enough to repeat a thread. Two cases stop at 2 iterations
and the third stops on the bits floor, so the defect was invisible to the
suite and only appeared at effort 5 on a market with a long tail of
follow-ups. That is an argument for running the eval cases at a high
effort occasionally, not for trusting a green suite.

---

## it-19 — the year-on-year was reading Keyword Planner's spikes

Running the AnswerThePublic space at effort 5 across four seeds, two runs
disagreed about the same topic: `seo optimization tools` read **2.39x** in
one and **0.44x** in the other. Topic membership explained it — a topic is
a cluster mined from whatever that run harvested, and the second corpus had
also picked up `seo optimisation tools` at 110,000/mo, which doubled the
group and dragged its weighted series. So topic-level growth is a property
of the corpus, not of the phrase, and two runs are entitled to differ.

Dropping to the keyword level to get a stable number turned up something
worse. Keyword series agree across runs exactly (234/234 identical terms,
byte for byte), but the series themselves carry spikes:

```
keyword research (90,500/mo), 48 months as DataForSEO returns them
  2022-09 →    8k  8k  8k  8k  8k  8k  9k  9k  9k  6k  6k  8k
  2023-09 →    8k  8k  8k  6k  8k  6k  8k  8k  8k  6k  6k  6k
  2024-09 →    6k  9k  8k 14k  9k  8k  9k 12k 12k 301k 1500k 1830k
  2025-09 →   74k  8k  2k  1k  2k  4k 15k 60k 450k 201k 135k 135k
```

Thirty-three months between 6k and 15k, then three at 301k, 1.5M and 1.83M.
Verified against the raw cached response: the spikes are in Google's data
and DataForSEO passes them through. The parser was correct.

`growth()` compared the **sum** of each twelve-month window. Those three
months sit in the denominator, so it reported `keyword research` at
**0.29x** — demand down 71% — when the median month had gone *up*. Every
"this market is shrinking" headline in four reports rested on this.

| | sum of window | median of window |
|---|---:|---:|
| `keyword research` | 0.29x | **3.42x** |
| `content marketing` | 0.32x | **2.96x** |
| `ai influencer generator` | 90.13x | **0.77x** |
| `seo tips` | 26.20x | **3.40x** |

The direction inverts on the largest terms in the market. Across 754
keywords at 1,000+/mo drawn from four markets, 9% carry a month at 10x
their own median and 3% at 50x.

**Fix:** compare the median month of each window, in `growth`,
`long_growth`, the market-wide roll-up in `insights`, and
`_by_calendar_month` behind seasonality and `peak_month`. A median cannot
be moved by fewer than six bad months out of twelve.

It needs **three or more years to bite** — the median of two observations
is their mean, so on a two-year window a lone spike still names the peak
month. Every call already asks for four (`seo.history_start`), so the
guarantee comes from the shape of the request, not from the function. A
selftest check pins that, and the docstring says not to shorten the window
without revisiting it. Writing the test wrong is how the limit was found:
the first version used two years and failed.

| | before | after |
|---|---:|---:|
| selftest | 69/69 | **73/73** |
| evals, jev arm | 18/18 | **18/18** |
| evals, code arm | 17/18 | **16/18** |

**The code arm got worse and is staying that way.** Its constants
(`growth_up: 1.30`, `growth_down: 0.77`, `seasonality: 2.00`) were
hand-tuned while the inputs were contaminated, so correcting the inputs
moved values across fixed thresholds and it now keeps 90% of claims
instead of 86%. Re-tuning them would be fitting the control to the data it
exists to be a control for. The judgment arm did not move, which is the
result worth having: the thing that reads a number against a stated
criterion survived a change in the number, and the thing that compares it
to a constant did not.

**What it cost to find:** four effort-5 runs, $1.93 of DataForSEO. The
defect was invisible to the eval suite because every case runs on small
cached corpora whose keywords have no spikes, and invisible to five
previous market reports because a plausible-looking decline is exactly
what a reader expects from this category. It took two runs of the *same*
market disagreeing with each other to surface it.

---

## it-20 — reviewing the skill against what the AnswerThePublic campaign exposed

Six seeds, ten runs, and four hand-written scripts to get from the
reports to a strategy. Everything a script had to do by hand is a thing
the skill should have done, so each one was read as a defect report.

### 1. The lead finding was backwards, and the test could not catch it

`open` said *"The open ground is “keywords”: 100% of its 267,160 monthly
searches name no company at all."* True, and worthless: 2% of those
searches were anyone buying or comparing. Nobody had claimed the ground
because there was nothing on it. A founder acting on the sentence buys
ads against people learning what a keyword is.

The account test could not have caught it, because the rival it was
offered — *"every part of this market already has suppliers"* — is not
the account that competes with it. Jev chooses between the two accounts
code hands it, and code handed it the wrong pair.

**Fix:** the share of the topic that is buying, comparing or looking for a
supplier (the forecast's own `BIDDABLE` set, now one definition in
`kgraph`) goes into the sentence and the evidence; the rival becomes
*"there is almost nobody in it looking to buy"*; and the mirror-image
claim `empty` is built from the same numbers so that the account test,
not the generator, decides. Measured on six corpora:

| topic | commercial | `open` | `empty` |
|---|---:|---|---|
| seo optimization tools | 96% | **kept** (account 0.96) | rival 0.06 |
| sourdough bread starter | 95% | account 0.95, fair-reading 0.48 | rival 0.03 |
| pmo software | 100% | account 0.89, fair-reading 0.30 | rival 0.06 |
| content marketing | 2% | rival 0.43 | **kept** (0.87) |
| seo tips | 0% | rival 0.40 | **kept** (0.92) |
| seo and keyword | 0% | rival 0.22 | account 0.88, fair-reading 0.35 |

Never both. The account test picks the commercial side at 0.89–0.96 and
the empty side at 0.87–0.92, with the wrong side at 0.03–0.43.

**The first wording of `empty` was killed on every corpus, and it
deserved it.** It said the topic was unbranded *because* there was
nothing to sell there. Fair-reading gave it 0.17–0.48 while the account
test was picking its side — correctly, since a mechanism is not a
measurement. Restated as the conjunction the numbers contain, it reads
0.50–0.62 where it should survive, and the account margins sharpened
from 0.51/0.75 to 0.88/0.92. The test does not care whose sentence it is.

**Left open:** `pmo software` and `sourdough` carry perfect numbers for
`open` (unbranded 1.0, commercial 0.95–1.0) and fair-reading rejects it
anyway. One cause was measured: the evidence carried the *market's*
brand list (asana, jira, smartsheet) next to "name no company at all".
Judged fresh, cache off, single-claim batches: 0.31, 0.37 with the list;
0.45, 0.46 without. The claim now carries the topic's own brands, which
is the right evidence regardless — and it is not enough on its own to
clear 0.5, so the residual is unexplained and stays that way here.

### 2. Direction claims quoted series that could not carry one

After it-19 a median survives a spike, but nothing survives a series that
swings 450x inside the compared window, and `direction` was still naming
`seo tips` "at 23.01x" as the exception running the other way. The gate
belongs in the skill, and it must not be a constant — nobody can defend
"3x is too erratic".

**Fix, with no threshold in it:** a series is readable when the ratio of
window sums and the ratio of window medians fall on the same side of
1.0. The series is asked whether it agrees with itself. `keyword
research` (0.29x by sum, 3.42x by median) is out; a smooth 0.65x decline
is in. `growth_readable` travels with every topic row, the `direction`
claim names what it excluded in a `too_erratic_to_read` list, the report
says so in *How to read this*, and the network's `o_up` node goes
unobserved rather than misinformed when the market's own series fails
the test. On `content ideas` it excluded `content marketing`, `marketing
and content` and `content creation`.

**The limit, recorded rather than patched:** `seo tips` passes — sum
26.2x, median 3.40x, both up — and is quoted at 2.98x on a series that
swings 31.7x. Both estimators agree on the sign, so by the rule it is
readable and the median is the figure shown. A half-window test would
catch it and would also flag every seasonal market, which is worse.

### 3. The report hid the number that decided the strategy

*The shape of the market* showed one label per topic. `seo tools` read
"doing it themselves" and is 37% people comparing or buying; `keywords`
read "trying to understand it" and is 2%. A *buying or comparing* column
now sits beside brand share, on the same job set the forecast bids on, so
the two can be read against each other.

### 4. Two things the reader was not told

A topic is a cluster mined from what this run harvested. `seo marketing
tools` read 2% branded pooled across five corpora and 53% in the run
centred on it. Keyword series agree across runs exactly (234/234); topic
percentages are a reading of the corpus. The report now says so. Not
fixable without changing what a topic is, and disclosed rather than
hidden.

### 5. Dead output

`long_growth` was computed into every topic row and read by nothing.
Removed.

### The suite

| | before | after |
|---|---:|---:|
| selftest | 73/73 | **88/88** |
| evals, jev arm | 18/18 | **18/18** |
| evals, code arm | 16/18 | 16/18 |
| jev mean kept share | 0.30 | 0.24 |

The fifteen new checks build a two-topic graph with four years of
history, one readable and one not, and pin: the spiked topic is neither
rising nor falling but named as erratic; the network is told no
direction for it; `open` says who is there to buy; `empty` is built from
the same numbers as its contradiction; the report carries the column and
both notes. The code arm's two failures are it-8's and it-19's, unchanged.
Kept share fell because the pair usually resolves to one survivor or
none, where `open` alone used to survive on brand share.

### Not fixed, and named

The question *how do I win in this space* took six seeds and a pooling
script. The skill is single-seed by design and the report is right to be;
a `pool` over several runs' JSON, computing at the keyword level where
series are stable, is the feature this campaign actually wanted. Not
built here — it is a feature, not a defect, and this was a review.

---

## it-21 — `cad to bim`: a gate that asked the seller, and three sentences their numbers contradicted

Effort 5 on `cad to bim` came back with 2,555 keywords carrying 2,878,370
searches a month, 26% of it with readable intent — and **`drawings` at
1,830,000 a month, 64% of the corpus by itself**, beside `money drawing`,
`shell drawing`, `educational buildings`, `3d modeling` and `structural
engineering`. One finding compared `drawings` ($3.19) with `mechanical
shop drawings` ($109) as a price gradient inside one market; another's
"90% trying to understand it" was carried by children's drawing searches.

### The relevance question asked the wrong party

Its yes read *"close enough that anyone selling in this market would
care"*. A seller cares about their customers' whole world — structural
engineers and architecture firms are exactly who a CAD-to-BIM firm sells
to. Wordings were measured against labels written before any answer was
seen, first on this corpus, then on seven harvested markets (220 terms
each: top 150 by volume plus 60 sampled):

| wording | foreign terms dropped | real market kept |
|---|---:|---:|
| v1 — would a seller care (was) | 5/36 (14%) | 256/260 (98%) |
| v2 — is the searcher buying | 34/36 (94%) | 224/260 (86%) |
| v4 — is it about what the market deals in | 31–33/36 | 250–251/260 |
| **v5 — v4, taking the meaning most people intend** | **33/36 (92%)** | **249/260 (96%)** |
| v6 — v4 and a separate "same sense?" question | 36/36 | 186/260 (72%) |

v2 is the mirror image of v1's mistake: it throws out
`sourdough starter recipe` (110,000/mo), `feeding sourdough starter` and
`keyword search tool`, because people learning or doing it themselves are
not buying — and what people are doing is the job axis's question, which
already exists. v3 (not in the table: "do *most* of them want this
market") kept 4 of 19 core terms on `cad to bim`; v6 shows that framing
collapses to "most people want exactly the seed" however it is asked.

**No wording that kept the real market dropped `drawings`.** Given a
CAD-to-BIM market, the word means CAD drawings.

### What gives it away is scale, and scale is arithmetic

A search larger than the rest of the market combined is asked once more,
with that fact stated in words — Jev is never handed two numbers — whether
most people typing it could be here. Nineteen cases, three fresh asks
each, 19/19 every time: `drawings`, `3d modeling`, `nhs`, `coffee`,
`flour`, `google` out; `sourdough starter`, `crm`, `revit`, `meal prep`,
`cad to bim` kept. Across nine markets already run the rule fires on one
search. End to end on the contaminated corpus with the real model: one
question, `drawings` dropped.

The selftest found the rule's edge by asking a stub that always said no:
with two terms left, the larger is always "more than the rest", and the
rule stripped the market to nothing. It now stops when fewer than two
other terms remain — a comparison that cannot fail is not a test.

### Three templates whose framing their own numbers contradicted

**`gradient`** printed *"20.6x the price for 750% of the volume"*: the
"narrowed" search, `bim building modeling`, carries the whole BIM
cluster's 5,400 a month against 720 for `building modeling`. A narrowing
is now searched less than what it narrows. One of ten past gradient
claims was inverted. The network computed the same pair in a second copy
of the loop that iterated a `set`, so its tie-breaking changed between
runs; both now call `Graph.sharpest_narrowing`.

**`money_seat`** said *"the money is concentrated"* over 27% of the
searching and 21% of the spend. **43 of 51** instances across every run
on disk had the premise backwards, at least seven of them kept. Two
causes: spend was divided by the money in *every* keyword — including
head terms held out for unreadable intent — while searching was divided
by the readable ones, so every spend share came out small; and the cell
chosen was the one with the most money, usually just the biggest. Both
shares are now over the same searches, the cell named is the one whose
spend runs furthest ahead of its searching, and the claim is not made
when no cell's does *at the precision the sentence prints* — "0% of the
searching but 0% of the spend" was the three cases left after the first
fix. Regenerated over 60 corpora: built on 54, every premise true.

**The account test was won by plurality.** Two claims on `cad to bim`
survived with the model at 0.42 and 0.46 for their own side — more
likely not supported than supported — and the money claim had been
rejected as "the data supports the opposite" the run before. A coin flip
was recorded as a finding. It now needs a majority, the same 0.5 floor as
every other test. About 1% of kept claims in the Jev arm were affected.

### Before and after, same seed, same reader

| | first run | after |
|---|---:|---:|
| keywords | 2,555 | 1,529 |
| searches a month | 2,878,370 | 345,840 |
| intent readable | 26% | 74% |
| paid channel (forecast) | $1,084/mo | **$308/mo** |

**The earlier `cad to bim tool` report's $1,126 a month was the same
defect.** Its largest biddable searches were `revit download`, `revit
architecture download`, `revit cost` and `structural engineering firms` —
people getting Autodesk's software or looking for engineers.

| | before | after |
|---|---:|---:|
| selftest | 88/88 | **115/115** |
| evals, jev arm | 18/18 | **18/18** |
| evals, code arm | 16/18 | **17/18** |

The code arm's gain is `thin-niche/code`, which no longer has a false
concentration claim to keep.

### Named, not fixed

- `direction` calls 1.01x "growing" and lists 0.98x as "running the
  other way". Saying *flat* needs a constant or a new judgment question.
- The seven-market gold set's largest disagreement with v5 is hospital
  EPR terms on `ambulance software` (`electronic patient record nhs`),
  which I labelled in-market and v5 does not. Whether a hospital records
  system is what ambulance software deals in is arguable; the numbers
  above count it against v5.
- `selfserve` still says "the competitor is doing without" at any share.
  At 1% it was withheld by the majority floor this time; the sentence
  itself leaves the magnitude to judgment.

---

## it-22 — insights ranked by value, the offering axis, and data as files

Asked for: *more insights like "the money is in services, not software";
the report sorted by insights; when there are none it should not matter;
all the data attached as files; seed + effort in, insights by value out;
nothing relying on Claude — only Jev and DataForSEO.*

**The diagnosis was uncomfortable.** The pipeline never touched a language
model — every import is `jev`, the DataForSEO clients, or the standard
library. But the two most useful sentences in the last two deliverables
were not the skill's. "The money is in services, not software" came from
grepping a `cad to bim` corpus by hand after the run and sorting by click
price; "rename the product, `keyword` is dying" came from pooling five
runs by hand. The dependency on Claude was never in the code. It was in
what the code could not see.

### The offering axis

What the skill could not see was *what kind of answer* a searcher wants.
`bim modeling services` and `bim software` are both people shopping — one
for a firm, one for a tool — and the job axis made them the same searcher.
A third axis, fixed and universal like the jobs: `service`, `software`,
`product`, `information`, held out when no answer is clearly ahead.

Read on real keywords: five service searches → service at 0.97–1.00;
`bim software` 0.91, `revit mep software` 0.97 → software;
`sourdough starter kit` → product 1.00; `sourdough starter recipe` →
information 1.00; `cad to bim`, `bim`, `scan to bim` → held out.

### Contrasts, and the ones that did not make it

Four families state "the X is in A, not B", with B where the crowd is:

| family | on `cad to bim` | verdict |
|---|---|---|
| `offer_money` | the money is in services, not information — $25.81 against $10.93 | kept, account 0.92–0.99 |
| `offer_growth` | the growth is in software, not services — 1.19x against 0.67x | kept, account 1.00 |
| `topic_growth` | "bim software" 1.19x against "building information modeling" 0.97x | kept |
| `offer_open` | see below | not in this market |

Built, measured, and taken out or rebuilt:

- **`offer_buyers`** ("the buyers are in services, not information")
  restates how two axes overlap — a firm-seeker is nearly always hiring —
  and fair reading rejected it at 0.30. Removed.
- **A paid-channel pair** ("a small channel" / "a large one") asked Jev a
  magnitude with no reference: it called $273 a month the large channel,
  account 0.58. Magnitudes are the one thing the contract says Jev cannot
  judge. The forecast is a fact, so it is now a line under the title, and
  is compared only against a `--budget` the reader supplies.
- **`offer_open`, three times.** First it named *information* — 4% branded,
  0% buying — the open ground: it-20's unclaimed-because-unwanted, one
  level up. A premise check ("the open side has buyers as printed") let 1%
  through. The fix was to measure the thing the sentence is about: brand
  share **among the people shopping**. Then it compared services against
  the most-branded offering, which had 200 shopping searches; now it
  compares against the offering with the most shopping, as the money
  contrast compares against the most searching. On `cad to bim` it is
  still rejected — services and information shoppers both barely name a
  company — which is correct: the contrast is not in this market.

Across three markets from cache: `cad to bim` keeps money and growth;
`answerthepublic.com` keeps *the money is in software, not information*;
`keyword research tool` keeps none — nothing readable was rising and
services were 0.2% of the searching. Contrasts survive where the data has
them.

### A new door for the drawings

The first probe run came back 39% children's drawing searches, led by
`how to drawings` at 301,000 a month. A price probe had combined the
legitimate topic "drawings" (as-built and construction drawings) with
"how to", and Google gave the invented phrase the volume of "how to draw".
No single search outvoted the rest, so `outvoting` stayed silent.

**`invented_giants`**: a search the loop made up or Google suggested that
outsizes everything the market's own businesses rank for is asked the
scale question, with that fact in words. Across ten corpora it fires on
the drawings phrases and on `sourdough starter`'s own name. Twelve cases,
three fresh asks: all four drawing phrases dropped every time, all five
sourdough names kept every time; `revit`, `project management` and
`keyword research` dropped where I had labelled them keep — broader
subjects, which the relevance criterion names as a reason to say no, and
which this rule has never reached in practice. Recorded as 9/12, not
relabelled after the fact.

**Tried and rejected:** admitting a search only when relevance is
*decisive* (the existing 2x margin, 0.67 for a yes/no). Foreign terms
dropped rose 92% → 100%; the real market kept fell 95% → 90%, and admitted
volume collapsed — `cad to bim` 83% → 10%, and `keyword research tool`
lost `tools for seo`, the heart of the AnswerThePublic insight. The floor
stays at 0.5, and `modelling 3d` (p = 0.51) remains a coin flip that can
flip between runs when question batches change. Disclosed, not fixed.

### The report

Insights only, ranked by Jev's value weight — "which of these would
change what the reader does the most?", already the ranking question —
each with its headline, its sentence, a table of only its own columns,
the searches behind it, and how it held up. "No insights" when nothing
survives. Everything else is nine files beside it: keywords, offerings,
topics, tested (every statement, its scores, its rank or its reason),
series, trail, network, forecast, run. The network's conclusions moved to
`network.json`: its calibration is unverified, and a probability the
reader cannot check is not an insight.

**The selftest found a real defect:** the offering contrasts sat below
`generate()`'s early return for a market with no confirmed topic, so such
a market silently lost them. They run either way now. And the table under
a contrast rounded to three places before formatting, printing 76% under
a sentence that said 77%.

### The suite

| | before | after |
|---|---:|---:|
| selftest | 115/115 | **154/154** |
| evals, jev arm | 18/18 | **22/22** |
| evals, code arm | 17/18 | 19/21 |

The jev arm gained four universal checks — ranked by value, every data
file attached with matching row counts, the network file carrying its
caveat, "No insights" when nothing survives — and the three that read the
network section by its wording now read the file. The code arm's new
failure is `thin-niche/code`: the new families gave its hand-tuned
thresholds more to keep. Not re-tuned, as in it-19.

## it-23 — the practitioners' questions, and a market held to page one

Asked for: *critique the insights — "it sucks" — look at the best people in
this game, the frameworks they use, and use their heuristics with the tools
available to make an insight search engine: keyword and effort in, insights
out.*

### The critique

The `cad to bim` report at effort 5, before this iteration:

| # | insight | what was wrong with it |
|---:|---|---|
| 1 | The open ground is "modelling" | built on searches the loop invented: `top modelling` (8,100 a month — modelling agencies), `modelling jobs`, `what is modelling`, `how to modelling`. Fashion, not BIM |
| 2 | "modelling" is unclaimed, and nobody is there to buy | the same junk from the other side |
| 3 | "bim software" is settled and "modelling" is not | a definition names no company because nobody buys there |
| 4 | The competitor is doing without | 3% of the searching; the headline said the opposite of its number |
| 5 | The growth is in "bim software" | true, colour |
| 6 | The open ground is in services, not software | good — the kind the user asked for more of |
| 7 | Nobody owns buyer search | quora and reddit took 41% of buyer clicks, unsaid; `www.` in every domain |
| 8 | A lead costs $174 | a blend of fashion `top modelling` and $219 service clicks that fits no business |
| 9 | The money is in services, not information | "information" inflated by `modelling 3d`, 135,000 a month of general 3D |
| 10 | revit is taking share from autocad | two points; colour |

Three failures at once. **Garbage in**: every guard compared sizes, and a
harvested `modelling 3d` at 135,000 raised the ceiling `invented_giants`
compares against, so a probe's `top modelling` passed beneath it — and 20%
of the market was Google's close variants counted twice. **Statistics, not
decisions**: nothing said where to start, what a customer costs, who to beat
or what a newcomer could win. **A floor that did not hold**: five of the ten
were labelled *Colour* — the floor asked which stakes level was likeliest
while the report printed the level nearest the mean, and on spread-out
answers the two disagree (126 of the last 400 cached stakes answers).

### What the practitioners do, and what each became

| who | heuristic | became |
|---|---|---|
| Grow and Convert, Pain Point SEO | value demand by readiness to buy; BOFU converted 4.78% against 0.19% | the buying core; `customer_cost` |
| Keyword Insights, SE Ranking | three shared top-ten URLs = one page's work | `serp_clusters` |
| Glen Allsopp (Detailed), Semrush | forum, social or off-target pages on page one are a door left open | `open_door` |
| Will Scott, Barnacle SEO | where directories rank, get onto the directories | `who_answers`, when directories hold the page |
| Ahrefs | traffic value and difficulty together, never volume alone | the beachhead's counts; Labs difficulty |
| Geoffrey Moore | a beachhead you can win outright | `start_here` |
| Brian Balfour | channel–model fit | `customer_cost`, by offering |
| Les Binet (IPA) | share of search leads market share | `share_of_search` |
| Bob Moesta | the push away from what people have | `switching` |
| Eli Schwartz | one template for a repeatable pattern | `pattern` |
| "why now" | demand that did not exist | `new_demand` |
| everyone | search it and look | **grounding** |

### Grounding: the market held to page one

The market's 50 largest searches and its 60 most valuable buying searches
(effort 5) are each read against their first page from DataForSEO's SERP
API ($0.002 a page), and Jev answers the relevance question again with the
pages in front of it — same criteria, so "in this market" keeps one
definition. Dropping one lets the next largest into the head; the head may
take four times its size in pages a run, because at twice, `cad to bim`
spent the allowance on its four harvests and the probes after them went
unread. On `cad to bim` it asked 179 questions and dropped about 90,600
searches a month: template junk (`services provider`, `what is services`, `cheap
services`), general 3D (`architectural models`), hardware (`eva scanner`)
and Autodesk's wider catalogue. `top modelling` and `modelling 3d` never
got in. It is noisy at the boundary, disclosed not fixed: `revit software`
dropped in one run and `revit price` kept; "is BIM software part of the cad
to bim market" is a real judgment call and the model flips on it.

### Close variants, whatever their words

Google gives a close-variant cluster one set of numbers. it-23's first
merge required the words to differ by one stem, and left 19.9% of `cad to
bim` counted twice: `bim services` / `building information modeling
services`, `revit price` / `revit software cost`, `bim consultant` / `bim
consulting services` — same volume, same click price to the cent, same
varying two-year series. That fingerprint no coincidence produces, so a
matching non-zero price now merges any wording; a price of zero matches by
chance and identifies nothing. No priced twin remains in either market run.

### Where to win

Buying searches are clustered by page one, each cluster's first page read
by Jev result by result, its clicks split by position with First Page
Sage's 2026 CTR curve as relative weights.

**Where to start went wrong twice before it went right.** Ranked by forum-
held clicks, the first pick was `revit price` — people pricing Autodesk's
own product — so only searches naming no company count. Then it could never
offer the services groups, which hold the buyer money ($50,713 a month for
`bim modeling services`) behind first pages of small specialist firms at
difficulty 9 — so difficulty is a count, and so is growth, since that group
had fallen to 0.64x unseen. Code keeps the groups nothing beats on all four
at once and Jev picks among them in words: `bim modeling services`,
confidence 0.77–0.81.

**And then the tests are honest about it.** Its fair reading ran 0.30,
0.40, 0.53 and 0.54 across four runs, and seven rephrasings moved it no
more than that: the most money, behind specialists, falling by a third, is
a genuinely mixed case, and it survives in some runs and not others.
Whether it is the place to start is a judgment; where the money is is a
measurement, so it is now stated under the title like the paid line —
"Where the buyer money is: “bim modeling services” carries the most a
newcomer could answer".

**Built, measured, and replaced.** A `weak_open` / `weak_closed` mirror
pair: "often answered by pages not built for them" is a magnitude, and the
account test chose it at 0.97 on 9% (cad to bim) and kept it at 11% (the
AnswerThePublic space), while what the numbers held went unsaid:
directories and review sites took 48% of buyers' page-one clicks there.
Now `who_answers` names the kind of page ahead as printed, with the runner-
up as its rival — and the practitioner move in the assertion, because
"who holds the page" alone was read as changing nothing in both markets.

### The old families, fixed where the critique found them

- **`settled`** is measured among the people shopping in each topic, and
  "settled" means most of them name a company: "keyword tool is settled"
  led the AnswerThePublic report at 3%.
- **`open` / `empty`**: code compares the topic's buying share with the
  market's and builds the one that holds. The account test chose "open
  ground" at 0.78 for a topic with 0% buying.
- **`selfserve`** is made only when more of the searching is doing without
  than shopping.
- **`gradient`** needs a narrowing that shows at the precision it prints
  and sits above Google's 10-a-month reporting floor: `bim drawing software`
  at 10 a month was "3.7x the price for 0% of the volume".
- **`ambiguity`** divided the searches placed on a topic by the searches
  whose words contain its name — two sets — and sent "project management
  software (121% clear)" to the judge. Both sides are now the searches
  placed on the topic.
- **`direction`** is decided on the figure as printed, and only when this
  year's twelve months stand apart from last year's (a two-sided Mann-
  Whitney U test at the conventional 5%). "This market is shrinking: …
  1.00x the twelve before" led one run, with every exception rising; the
  next run said 0.99x, and ranked it first. Twelve months that sit among
  the twelve before them are not a direction. The AnswerThePublic space's
  0.33x still is.
- **Majorities are majorities.** Fair reading, the account test and the
  value floor all need more than half; "Start with “seo keyword research
  tools”" was kept on 0.50 and 0.50. The floor keeps a finding only when
  more than half the stakes weight is on "a choice" or "a reversal", and
  the label printed is the likelier level on that side.

### Before and after

| | `cad to bim` before | after | AnswerThePublic before | after |
|---|---:|---:|---:|---:|
| searches in the market | 408,360 | 154,180 | 795,180 | 73,530 |
| insights | 10 | 8 | 6 | 9 |
| resting on invented or off-market searches | top 3 | 0 | — | 0 |
| labelled Colour | 5 | 0 | 1 | 0 |
| first pages read | 9 | 180 | 0 | 138 |
| data, fresh run | $0.81 | $0.78 | $0.47 | $0.49 |
| judgment, uncached | $0.07 | $0.09 | $0.05 | $0.06 |

`cad to bim` after, in order: **a services lead costs $780 through search,
a software lead $110**; most of the searching is learning, except services
at 85% shopping; buyers are answered first by specialist firms, so a
newcomer competes head-on; the open ground is in services, not software
(9% of services shoppers name a company, 77% of software shoppers); the
money is in services, not information; a gradient, a split, and a two-point
share-of-search move. Under the title: *where the buyer money is — "bim
modeling services", $50,713 a month, difficulty 9, falling to 0.64x, page
one seven specialist firms*. The AnswerThePublic space: start with "seo
keyword research tools" (the most money, at difficulty 74 and 0.47x — the
report says both); no business owns buyer search; a software lead costs
$466, an information lead $190; "keyword suggestion" is unclaimed and
nobody there is buying; the market is shrinking (0.33x); doing without
outnumbers shopping; buyers meet directories and review sites first
(Barnacle SEO).

Run to run, findings near 0.5 still come and go — `start_here` and
`settled` among them. Disclosed, not tuned away.

### Also

- **Bright Data is gone.** The SERP had been scraped through a third
  vendor and parsed out of markdown, against the rule that the skill runs
  on Jev and DataForSEO alone; the previous delivery said otherwise, which
  was wrong. Page one now comes typed from DataForSEO.
- **Eight pages at once.** A page takes 4–16 seconds; 110 in a row was a
  quarter of an hour. **A budget check per action**: a flat $0.10 reserve
  refused $0.002 pages near the ceiling. Ceilings rose to $0.40–$2.20.
- **The threshold arm** crashed on the new families (a list where it
  expected a count); it now keeps them as built, and a selftest holds it.

### The suite

| | before | after |
|---|---:|---:|
| selftest | 154/154 | **199/199** |
| evals, jev arm | 22/22 | 21/22 |
| evals, code arm | 19/21 | 19/21 |

The jev arm's miss is `broad-competitive`'s "do not reveal what the person
wants". Its evidence carried the 121% share above; fixed, the finding reads
fair (0.59) and wins its account (0.72), and the value floor now judges it
background — 40% that it changes a founder's decision. Recorded, not
relabelled.
