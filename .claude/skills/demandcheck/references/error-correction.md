# Error correction — how this skill creates knowledge, and how it goes wrong

Read at intake, before the first dollar is spent; re-read before ANALYZE.
`demand-lens.md` sets the standard an explanation must meet. This file sets
the standard the *run* must meet: what the data can and cannot do for you, and
the machinery that catches this run's mistakes while they are still cheap.

The argument is David Deutsch's (*The Fabric of Reality*, *The Beginning of
Infinity*), applied to a demand survey.

## The mistake this skill is one step away from making

The skill's central rule — never invent a keyword — was written against a real
failure: an LLM handed "AI receptionist for dentists" will happily produce
thirty plausible keywords, price them from memory, and hand you a market that
does not exist. The rule fixes that. But read carelessly it teaches something
false: that if you just collect enough measured facts, the demand's shape will
emerge from them.

It won't. **Data never speaks.** A table of 640 keywords with volumes and
prices contains no claim about why the demand is latent, who has the pain, or
what the long-running ads reveal. Every such claim is a *conjecture* — invented
by you, not extracted from the rows — and the rows' only job is to give that
conjecture the chance to die. Knowledge grows by conjecture and criticism, and
in that order; nothing is derived upward from observation.

So the prime directive is one rule about *evidence*, not two rules about
thinking:

> **Fabricate no observations. Conjecture boldly.**

Never write down a search term, a volume, a price, or a line of ad copy that a
paid pull did not return — that is fabricating evidence, and it is fatal
because it destroys the very thing that could correct you. But invent
explanations freely, early, and at full strength. A timid conjecture ("there
may be some interest in this category") cannot be refuted by any table and is
therefore worthless. A bold one ("this is latent demand because the buyers are
clinic office managers who never learn the category's name") forbids things,
and the run can go and check whether the forbidden things happen.

The failure mode the no-invented-keywords rule guards against is fabricated
evidence. The failure mode *this* file guards against is a run that collects
diligently and concludes nothing that could have been wrong.

## Rule 1 — Pre-register the conjecture, at intake, before spending

At Phase 0, before a single call, write down what you expect this survey to
find and what would refute it. You are not a blank slate — you have read the
seed and you already have expectations. The only question is whether they are
written down where the data can kill them, or left implicit where they will
quietly select which numbers you notice.

```bash
dc.py conjecture add \
  --text "Demand here is latent: the pain is real but buyers don't know the category name" \
  --forbids "high-CPC category-name keywords with sustained advertisers on them" \
  --check "if >=3 category-name keywords price above \$3 CPC with 90-day creatives, C1 is refuted"
```

`--forbids` is the load-bearing field. An expectation that forbids nothing is
not a conjecture, and `dc.py` will take it but the run gains nothing from it.
Two or three at intake is right. More is bookkeeping.

## Rule 2 — Every wave judges the standing conjectures

The wave's DECIDE step is not only "what do I expand next" — it is "what did
this wave's data do to what I believed before it". Before closing a wave, take
each open conjecture and rule:

```bash
dc.py conjecture judge C1 --status refuted \
  --evidence "5 category-name keywords at \$4.10-\$6.80 CPC, 3 advertisers past 90 days (K031,K044,K052)"
```

`survived` (the forbidden thing did not appear — the conjecture lives, and is
*not* thereby proven), `refuted` (it appeared — say which rows), `revised`
(the conjecture was too coarse; judge it, then `add` the sharper successor as a
new id rather than editing the old one).

A refuted conjecture at wave 2 is the best thing that can happen to a $5 run:
you bought a corrected picture for a dollar and the remaining four are now
spent on the right frontier. A run that ends with every conjecture `survived`
is not a triumph — it usually means they forbade nothing, and the orchestrator
should say so in the notebook and spend DEEPEN on a real refutation attempt.

**Judging is not optional, and it is not free-form.** The rulings are what make
the notebook an error record instead of a diary.

## Rule 3 — The traversal is itself a conjecture, and it has a known blind spot

Ranking the frontier by `spend_proxy` (volume × CPC) encodes a theory:
*money marks the important demand.* That theory is usually productive and
structurally blind to exactly the quadrant this skill most wants — demand real
enough to be searched but not yet priced. This is why `traversal.md` mandates
1–2 `latent-probe` picks per wave that the ranking function would never choose.

Treat that quota as error correction, not garnish. If a wave ships with no
latent probe, the run has spent that wave confirming its own ranking function.
The same goes for the junk-host skip list (a theory about where knowledge
isn't) and the ≥90-day proven-copy bar (a theory about what advertiser
behaviour means): each is a conjecture the run is standing on, and each is
worth one sentence in the methodology notes.

## Rule 4 — Evidence criticizes; it never justifies

There is no such thing as data that establishes a conclusion. A conjecture that
has survived every check you could afford is exactly that — *not yet refuted,
by the checks you could afford* — and it is the best kind of knowledge there
is, but it is not proof, and next month's data may kill it.

This is a rule about how the analyst may *think and write*, and it binds every
claim in the report:

| Don't write | Write |
|---|---|
| the data proves / validates / confirms | four brands hold every paid position on this term (state the fact) |
| we found that the market is X | the market is X, and here are the rows |
| definitely / clearly shows | the strongest form the numbers support, and no further |
| 87% confidence in this verdict | no number at all — rank the routes forward instead |

A verdict expressed as a probability tells the reader nothing they can act on.

**The reasoning is the analyst's, not the reader's.** These rules govern which
sentences may be written; they are not an invitation to publish the reasoning
itself. What the run expected, what the data refuted, and what would overturn a
verdict decide what goes in the report — they never appear in it
(`references/report-spec.md`, "Never narrate the work").
A verdict paired with "and here is the $0.40 call that would overturn it" hands
them the next move. Prefer the second, always.

## Rule 5 — Name what these instruments structurally cannot see

Search volume, CPC, and ad libraries read one thing: demand that has already
become a Google query or a Google ad. Whole categories of real demand never do:

- **Enterprise and high-ticket B2B** — bought through relationships, RFPs and
  conferences; the search footprint is a rounding error on the revenue.
- **Discovery-led consumer demand** — categories bought where people are shown
  things rather than where they ask for them (TikTok, Instagram, Amazon's own
  search box, app-store browse). Absent here, visible via other skills.
- **Regulated, taboo, or ad-restricted categories** — the ad libraries are thin
  by policy, not by lack of demand.
- **Word-of-mouth and community-native demand** — Discord, WhatsApp, industry
  Slacks, subreddits that never surface as a commercial query.
- **Demand outside this run's geo and language** — every number carries a geo
  for a reason.
- **Demand for a thing nobody can name yet.** This is the deep one, below.

What these instruments could not see for *this* subject binds what the report
may claim. It does not get its own section of caveats: where a blind spot
changes how a finding should be read, it belongs inside that finding ("these
are the people who search for it; this category also sells through short-form
video, which these figures do not reach"). Everywhere else it simply narrows
the claim — a survey that cannot see a channel must not write sentences that
imply it did.

## Rule 6 — Absence of expressed demand is not a verdict about the idea

Deutsch's distinction between *prediction* and *prophecy*: you can predict
within an explanatory frame you already have, and you cannot foresee the growth
of knowledge — including the knowledge that creates a market. Nobody searched
for a spreadsheet in 1978, for a ride-hailing app in 2007, or for a database
that stores embeddings in 2019. Each want was created by the thing existing and
by an explanation of why anyone should care.

So "no expressed demand found" is a measurement of the instruments' reach and
of the present state of the market's vocabulary. It is a real, useful,
often decisive finding — a novelty-dependent idea has to fund the *creation* of
its demand, which is expensive and slow, and knowing that before you build is
worth the $5. But it is not a finding that the idea is bad, and the report must
never let the two verdicts share a sentence (`demand-lens.md` says this too;
it is repeated here because it is the single most consequential error a demand
check can make).

The optimistic corollary is equally operational: a null result restates the
problem rather than closing it. "No expressed demand at the category name; the
adjacent pain X carries 40k searches a month at $0.30" is a route. Problems
are soluble; a survey's job is to hand over a better problem than the one it
was given.

## Rule 7 — Mistakes are the mechanism, so make them cheap, early and loud

The notebook is append-only for exactly this reason. When wave 3 contradicts
wave 1, both entries survive, and the contradiction is the most informative
thing in the run. **Never edit or delete a superseded entry** — rewriting the
record to look like you were right all along is how a research process stops
being able to learn.

Three practices follow:

1. **Front-load the killable claims.** State the conjecture that most of the
   run's value depends on in wave 1, not wave 4, and aim the earliest cheap
   calls at it. Being wrong in wave 1 costs a dollar; being wrong in the report
   costs the reader's decision.
2. **At DEEPEN, buy one refutation, not only more coverage.** Before the
   coverage passes, spend one call on the check most likely to *kill* the
   leading explanation. If it survives that, it has earned its place in the
   report; if it dies, you found out while you could still rewrite.
3. **Let the dead ones do their work.** A refuted conjecture redirects the
   remaining budget and removes a claim the report would otherwise have made.
   That is its whole job. It stays in `state.json` and the notebook — the
   reader gets the surviving conclusion and the evidence for it, not the
   history of how it was reached.

## Tells that a run has stopped correcting itself

Check these before ANALYZE. Any two together mean the run is confirming rather
than testing:

- Every conjecture is `survived` and none was ever `revised`.
- No conjecture's `--forbids` names anything the collected tables could show.
- No wave carried a `latent-probe`; the frontier ranked purely on spend_proxy.
- The notebook has no entry containing a surprise — nothing the previous wave
  would not have predicted.
- The explanations' "strongest rival" sections are strawmen the numbers
  dismiss in a clause.
- The run cannot name what would have overturned its verdict (nobody asked
  the question, so nothing was ever at risk).
- A null result is written as a judgment on the idea rather than on the
  instruments' reach.
