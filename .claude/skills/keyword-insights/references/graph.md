# The graph, and what each finding reads off it

## Nodes

| node | where it comes from | carries |
|---|---|---|
| **keyword** | DataForSEO | monthly volume, click price, competition, top-of-page bids, 12 months of history |
| **topic** | mined as n-grams from the corpus, confirmed by Jev | whether it names a thing rather than narrowing one |
| **job** | fixed universal taxonomy, assigned by Jev | what the searcher is trying to do |
| **brand** | mined as tokens, confirmed by Jev | a company already named in the search |

## Edges

```
keyword --ABOUT--> topic      containment where the topic is literally in the
                              keyword (a fact about the string, settled by
                              code); Jev only gets the residue — nothing
                              matched, or several did

keyword --SERVES--> job       always Jev. No amount of string matching
                              reaches what a person wants

keyword --NAMES--> brand      string matching, once Jev has confirmed which
                              mined tokens are company names
```

A **cell** is a (topic, job) pair: *people looking for T in order to J*. It
is the unit an insight is about, and it is where the two axes pay off —
the same topic split by intent prices very differently, and the same intent
across topics usually does not.

## Two kinds of thing that are not topics

**A brand.** If "asana" anchors a cluster then every keyword in it contains
"asana", and "this cluster's searching names a company outright" is true by
construction. A circular finding is worse than no finding: it survives every
test that checks whether a claim fits its data. Topics carrying a brand
token are excluded for the same reason.

**A fragment.** Mining n-grams turns up "management" alongside "task
management". The shorter phrase is the longer one with its meaning removed,
and keeping both splits one cluster across two nodes. The most specific
phrase wins — a fact about the strings, not a threshold.

## The finding families

Each fires **once, about the market, naming its own extremes**. An earlier
version fired each once per topic and produced sixteen of twenty findings
that were two sentences with the nouns changed. A pattern holding across a
market's topics is one finding *about the market*, and saying it that way is
both shorter and more informative, because the market-level version can name
which topics break the pattern.

| family | reads | the question it settles |
|---|---|---|
| `thin` | corpus size, top-5 concentration | is there enough spread here to tell buyers apart at all? |
| `direction` | median month of the last twelve against the twelve before, over topics whose series can carry a direction | is this growing or shrinking, and what runs the other way? Topics whose sum-ratio and median-ratio disagree on the sign are named as unreadable, not quoted |
| `pricing_axis` | click-price spread across jobs vs across topics | is a click priced by what someone wants, or by where they are? |
| `intent` | volume by job, and the topic furthest from the market's mix | what is everyone doing here, and who is doing something else? |
| `ambiguity` | share of volume whose intent was indistinguishable | how much of this market's searching tells you nothing? |
| `settled` / `open` / `empty` | branded share, most vs least, and the share of the least-branded topic that is buying or comparing | where have buyers picked a supplier, and where have they not — and is the unclaimed part unclaimed because it is open, or because there is nothing to sell there? `open` and `empty` are built as a contradicting pair from the same numbers, so the account test decides |
| `split` | biggest term vs dearest click | is the money where the attention is? |
| `head` | largest keyword and its job | what is the single biggest thing happening here? |
| `money_seat` | implied spend by cell vs its share of searching | where is spend concentrated out of proportion? |
| `selfserve` | self-serve volume share, and where it peaks | is the competitor a company, or doing without? |
| `season` | peak month over mean, per topic | is there a season, and where is it sharpest? |
| `substitute` | keywords naming two topics at once | what is weighed against what? |
| `gradient` | bare topic vs its dearest qualified form | does narrowing reach a different buyer, or just fewer? |

## Four years of history, for the price of one

Every call sends `date_from` set four years back, and DataForSEO returns
**forty-eight months of monthly history at the same $0.09** it charges for
twelve. Not asking for it was the single most expensive omission in this
skill.

With twelve months you cannot separate a trend from a season. The window
runs September to August, so "the last quarter against the first" is
June-July-August against September-October-November — nine months apart.
On `garden rooms` that produced *"this market is shrinking to 0.88x"* from
what was really a summer-to-autumn comparison.

With forty-eight months, growth is **the last twelve months against the
twelve before them**: two complete cycles, so the season cancels exactly.
On the same market the honest figure is 0.90x — the decline is real, and
the old number was right by accident. Seasonality likewise averages each
calendar month across every year available, which moved the garden-room
peak from September (one unusual month in one year) to **April** (a shape
that repeats).

`weighted_trend` takes its length from the data rather than assuming
twelve, because a hardcoded length silently matches nothing when the
history grows and the claims quietly stop being generated.

## One thing this data still cannot tell you

**Whether two near-identical phrases are really two things.** Google reports
a *combined* volume for terms it considers near-duplicates, so `insulated
garden rooms` and `insulated garden office` come back with identical volume,
identical click price and identical bid ranges. They are one measurement
under two names, and telling them apart would need them submitted in
separate requests. Word-order permutations (`garden rooms` / `rooms garden`)
are collapsed on the way in; this second layer is not detectable from a
single response and is left as it arrives.

## Follow-ups

Each family has one obvious next question — the table in
`scripts/insights.py` is the skill's model of curiosity. It says what *could*
be asked; Jev decides what is worth paying for.

Three shapes of probe:

- **expand** — up to 20 seeds into Google's own idea list. Finds unknown
  unknowns. Scales with how broad the seed is.
- **price** — up to 1000 exact terms in one call. Tests known unknowns:
  a thousand guesses about what people search, answered for the price of
  one. Most come back at zero volume, and that is the answer.
- **site** — every keyword a domain is relevant to. Available but never
  auto-chosen, because guessing a domain from a brand name bills in full
  whether or not the guess was right.

Probes are filled to the brim. The suspicion that raised the thread goes
first; the rest of the market's topics fill the remaining slots behind it.

## Reading the trail

The report's trail diagram shows the chase: green nodes answered their
question and the loop went deeper from them; orange nodes did not, and the
loop returned to the seed and took a different thread. A dead end also
discards the keywords it brought in — see `evals/LEDGER.md`, it-3.


## The market network

The keyword graph says what is in a market. The network says what that
means. They are different objects and both are needed: the first is
measurement, the second is inference.

```
demand_real ──┬─> o_money      (advertisers pay more than in a typical market)
              ├─> o_crowd      (more advertisers compete than is typical)
              │
intent_legible┼─> o_vague      (the biggest terms do not reveal intent)
              ├─> o_gradient   (narrowing changes the click price sharply)
              ├─> o_brand  <───┤
category_open ┼─> o_spread     (searching spreads across many terms)
              │
free_substitute -> o_diy       (searches look for free or manual routes)
growing ─────────> o_up        (more searching than a year ago)

  all five ──────> paid_viable
  three ─────────> incumbents_hold_it
```

**Latent** properties are what a reader wants to know and no instrument
measures. **Observed** nodes are what the keyword data sees. **Decision**
nodes are conclusions, which is why nothing hangs below them.

Every table row is one Jev question — "given that people here will pay and
the words do not reveal intent, can search ads pay for themselves?" — and
all 63 of them fit in one request for about $0.0006. Inference enumerates
the five latent roots, thirty-two states, exactly.

### Why there is no threshold anywhere

Code computes a statistic and states it plainly: *"advertisers here pay
about $16.08 for a click, weighted by how much each term is searched."*
Whether that is a lot is a question about the wider world, and this skill
has measured a handful of markets while the model has seen the
distribution. So the reading goes to Jev, whose answer enters the network as
**virtual evidence** — the correct formalism for "0.8 sure", rather than
forcing a true/false through a number the author picked.

### What the structure elicitation found

Asked which property each measurement is evidence about, Jev agreed with six
of eight hand-drawn edges. It moved `o_spread` from `intent_legible` to
`category_open` (a market whose searching has not consolidated into a few
terms is one whose vocabulary is unsettled), and it wanted `o_brand` under
`intent_legible` rather than `category_open` — which is right, because a
search naming a company is about as legible as intent gets. That one became
a two-parent node, since it is evidence about both.
