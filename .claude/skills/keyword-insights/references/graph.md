# The graph, and what each finding reads off it

## Nodes

| node | where it comes from | carries |
|---|---|---|
| **keyword** | DataForSEO | monthly volume, click price, competition, top-of-page bids, 12 months of history |
| **topic** | mined as n-grams from the corpus, confirmed by Jev | whether it names a thing rather than narrowing one |
| **job** | fixed universal taxonomy, assigned by Jev | what the searcher is trying to do |
| **offering** | fixed universal taxonomy, assigned by Jev | what kind of answer would satisfy them — a service, software, a physical product, information |
| **brand** | mined as tokens, confirmed by Jev | a company already named in the search |

## Edges

```
keyword --ABOUT--> topic      containment where the topic is literally in the
                              keyword (a fact about the string, settled by
                              code); Jev only gets the residue — nothing
                              matched, or several did

keyword --SERVES--> job       always Jev. No amount of string matching
                              reaches what a person wants

keyword --WANTS--> offering   always Jev, beside the job, and held out the
                              same way when no answer is clearly ahead —
                              "cad to bim" does not say whether the person
                              wants a firm or a tool, and is not forced

keyword --NAMES--> brand      string matching, once Jev has confirmed which
                              mined tokens are company names
```

The **offering** is what separates two searchers doing the same job:
`bim modeling services` and `bim software` are both shopping — for a firm
to do the work, and for a tool to do it themselves. Grouped by offering,
the arithmetic in `Graph.offering_rows` gives each kind of answer its share
of the searching and of the implied ad spend (over the same searches), its
click price weighted by searching, its share buying or comparing (over
searches whose intent read), its brand share **among the people shopping**,
and its year on year. The contrast families read those rows.

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
| `money_seat` | the cell whose share of implied spend runs furthest ahead of its share of searching, both over the same readable searches | where is spend concentrated out of proportion? Not made when no cell's spend runs ahead at the precision the sentence prints |
| `offer_money` | click price and shares of searching and spend, by offering; the dearest offering against the one with the most searching | where is a search worth the most, against where most searching is? Not made unless the dearest offering is also a smaller share of the searching, and its spend share exceeds its search share as printed |
| `offer_growth` | year on year by offering, on readable series only | which kind of answer is demand moving toward? Needs one rising and one falling as printed |
| `offer_open` | brand share among the people shopping, by offering; the least branded against the offering with the most shopping | where do buyers have no supplier in mind, against where most buying happens? |
| `topic_growth` | readable topic series; the biggest rising topic against the biggest falling one | which of this market's names is growing and which is dying? |
| `selfserve` | self-serve volume share, and where it peaks | is the competitor a company, or doing without? |
| `season` | peak month over mean, per topic | is there a season, and where is it sharpest? |
| `substitute` | keywords naming two topics at once | what is weighed against what? |
| `gradient` | the qualifier that raises the click price most, over searches that are narrower than their bare term — searched less than it | does narrowing a search reach a different, dearer searcher? |
| `start_here` | page-one groups of buying searches that no other group beats on buyer money naming no company, difficulty and first-page weakness at once; Jev picks among them | where should a newcomer start? |
| `open_door` | the group with the most buyer money naming no company times the share of its page-one clicks on forum, social and off-target pages | where is the first page least defended? |
| `who_answers` | where buyers' page-one clicks go, by kind of page, weighted by position and by each group's money; the kind ahead of every other as printed, the runner-up as its rival | what do buyers find first — and so, which practitioner move applies? |
| `customer_cost` | average buyer click by offering, over Grow and Convert's 4.78% lead rate | what does a customer cost through search, and for which kind of offer? |
| `who_owns` / `who_owns_not` | Labs share of voice over the buying searches, `www.` merged, sites that sell nothing set apart | does one business take the buyers' clicks? |
| `share_of_search` | each confirmed brand's share of branded searching, median months a year apart | who is gaining on whom? |
| `switching` | searches naming a brand with "alternative", "vs", "competitors" | who are people trying to leave? |
| `pattern` | one-slot skeletons with three or more distinct fillers, the slot checked by Jev | which one page template answers many searches? |
| `new_demand` | searches with no month above 10 three years ago, now at least the market's median size | what did not exist a few years ago? |

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

## Close variants are one search

Google Keyword Planner gives every close variant of a search — plural,
misspelling, a word more or less — the whole cluster's numbers: `bim
service` and `bim services` come back with the same volume and the same
48-month series. Counted twice, they double a market: before this was
handled, 54–56% of the `project management software` corpus, 41–51% of
`sourdough starter`, 40–43% of `keyword research tool` and 20% of `cad to
bim` was the same searching counted again (it-23).

`add_rows` now treats a varying 24-month series matching exactly, with the
same volume, as Google's own fingerprint of a cluster — no coincidence
produces it across two years, while a flat series ("10 every month")
matches by chance and identifies nothing. A newcomer with the same
fingerprint whose words differ from a kept search's by at most one (crude
stems, so `services` meets `service`) is kept only as an alias of it, in
`keywords.csv`'s `also_spelled`. Word-order permutations (`garden rooms` /
`rooms garden`) are collapsed the same way, as before.

## Page one

Two things are read off Google's first page, both from DataForSEO's SERP
API at $0.002 a page, typed — organic results with their domains, the ads,
AI overviews, question boxes, forums and video.

**Whether a search is in the market at all.** The relevance question reads
words, and every contamination this skill has suffered came in through
words. So the market's largest searches, and its most valuable buying
searches, are asked it again with page one in front of Jev. See
`judge.ground`.

**Where someone could win.** Buying searches are grouped by page one: a
search joins the first group, most valuable first, whose own page shares
three of its top-ten URLs, or starts one. Each group's first page is read
by Jev, result by result — specialist, household name, directory, article,
forum or social page, off-target — and its clicks are split by position
using First Page Sage's 2026 CTR curve as relative weights. A group's
**open value** is its buyer money in searches naming no company, times the
share of those clicks sitting on pages not built to answer it (forum,
social, off-target). See `opportunity.py`, and **Where to win** in
`SKILL.md` for the families.

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
