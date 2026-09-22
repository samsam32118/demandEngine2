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
| `direction` | 12-month series, summed across topics | is this growing or shrinking, and what runs the other way? |
| `pricing_axis` | click-price spread across jobs vs across topics | is a click priced by what someone wants, or by where they are? |
| `intent` | volume by job, and the topic furthest from the market's mix | what is everyone doing here, and who is doing something else? |
| `ambiguity` | share of volume whose intent was indistinguishable | how much of this market's searching tells you nothing? |
| `settled` / `open` | branded share, most vs least | where have buyers picked a supplier, and where have they not? |
| `split` | biggest term vs dearest click | is the money where the attention is? |
| `head` | largest keyword and its job | what is the single biggest thing happening here? |
| `money_seat` | implied spend by cell vs its share of searching | where is spend concentrated out of proportion? |
| `selfserve` | self-serve volume share, and where it peaks | is the competitor a company, or doing without? |
| `season` | peak month over mean, per topic | is there a season, and where is it sharpest? |
| `substitute` | keywords naming two topics at once | what is weighed against what? |
| `gradient` | bare topic vs its dearest qualified form | does narrowing reach a different buyer, or just fewer? |

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
