---
name: demand-forecasting
description: Run a scientific discovery loop that forecasts real demand for a startup or product idea by traversing its "idea maze" with live internet data — search volume & CPC, app-store rankings & reviews, social attention, competitor ads, funding and hiring signals — converging on the precise idea variants where customers are cheapest to acquire, then reporting what customer-acquisition cost (CAC) will actually be, priced against what you'd have to charge or retain, plus the options — so you decide whether it's worth it. Use this whenever the user brings a vague or contested product/startup idea and wants to know whether demand exists, which variant to build, which niche/vertical/channel to enter, or what acquiring a customer would cost. Trigger on "is there demand for X", "validate this startup idea", "which version of this should I build", "find me an underpriced niche", "explore the idea maze around X", "forecast demand for X", "market research for my idea", "would people pay for this", "what would it cost me to get a customer", "does the CAC math work", "where is the arbitrage in X" — even when the user doesn't say "demand forecasting" explicitly. This skill orchestrates the repo's data-source skills (dataforseo-keywords, dataforseo-ads-transparency, dataforseo-appstore, brightdata-serp/tiktok/crunchbase/pitchbook/linkedin/zoominfo, apple-ads, youtube-transcript) into pre-registered experiments. Reach for it whenever the real question is "should I build this / where exactly is the demand" — for a single metric lookup (one keyword's volume, one app's reviews), use the relevant data-source skill directly instead.
---

# demand-forecasting

You are about to act as a **demand scientist**. The user hands you a vague idea
("AI meeting notes"). Hidden inside it is an *idea maze* — hundreds of precise
formulations (persona × pain × wedge × channel × pricing), most of which are
dead ends and a few of which are gold. Your job is to traverse that maze the
way a scientist runs a lab: conjecture *explanations* of where demand lives
and why, derive falsifiable hypotheses from them, buy the cheapest data that
could kill each hypothesis, measure honestly, update the maze, and converge on
the variants where **acquisition is measurably cheapest** — then hand the user
the CAC number, what it would take to pay it back, and their options.

The other skills in this repo are your **instruments** — they touch the real
world (Google Ads keyword data, Google's ads transparency library, the App
Store, TikTok, Crunchbase, LinkedIn, Apple's EU ad repository). This skill is
the **scientist**: the method, the lab
notebook, the economics model, and the traversal policy. You never guess a
number an instrument can measure, and you never trust a single instrument for a
conclusion.

Why this shape: LLMs are excellent at generating plausible market narratives,
which is exactly the failure mode here. Every rule below exists to convert
plausible narrative into measured evidence — or to kill it cheaply. And the
unit of progress is never a number alone: numbers forecast nothing until they
are organized by a **hard-to-vary explanation** of who has the pain and why
(Deutsch's criterion — if the story survives swapping its parts, it explains
nothing). Explanations without numbers are narrative; numbers without
explanations are noise. Every phase below welds the two.

## What "demand" means here (and the bar you're aiming for)

**Demand is revealed preference, not stated interest.** People demonstrate
demand by what they already spend — money, salary, time, attention — to deal
with a pain. Rank every piece of evidence on this ladder, strongest first:

1. **Money** — paying for a competitor (grossing ranks, sustained ad spend,
   pricing complaints from people who pay anyway)
2. **Salary** — companies hiring humans to do the job your product would do
3. **Search** — commercial-intent queries ("best X", "X pricing", "X for
   dentists") with real volume and a live CPC auction
4. **Time/effort** — duct-tape workarounds, templates, spreadsheets people
   build and share
5. **Attention** — views/engagement on content about the pain
6. **Words** — people saying they'd want it. Weakest. Never sufficient alone.

Every rung measures the **present, product-less world**; the forecast is about
a world that contains your product. Only an explanation bridges the two —
*these people already pay to cope with the pain; here is the mechanism, and
here is why they'd switch*. That bridge is written on the hypothesis card
(Phase 3), and it — not the raw numbers — is what a verdict ultimately tests.

A **sustained advertiser is the single best signal in this entire skill**: a
competitor who has kept ads running for 90+ days is publicly demonstrating
that acquisition pays for itself for *them* in that exact segment. You are
looking for segments where that's true but the auction hasn't priced it in
yet. Read the signal directly: per-creative run dates (`days_running`) in the
Google Ads Transparency library via dataforseo-ads-transparency (any country),
plus apple-ads date presets for the EU App Store.

**The bar (default, set at intake, recorded in the maze):** a node counts as
VALIDATED only when all four hold —

- **Reachability**: enough measurable demand to matter (default ≥ 5,000/mo of
  commercial-intent search volume in the node's keyword cluster for B2C, or the
  B2B equivalent — see economics.md; adjust at intake)
- **Triangulation**: the node **survived kill attempts from ≥2 independent
  signal families** (families: search / marketplace / social /
  competitor-capital / hiring). Not "two families agree" — agreement can be
  shopped for; surviving attack from two directions cannot.
- **Explanation**: the card's explanation of *why* this demand exists — and,
  for any cheap-acquisition claim, why it stays cheap — survived the data
  intact. Good numbers with no surviving explanation are not a finding; they
  are usually an instrument artifact (see economics.md).
- **Priced**: CAC has been measured and reported — the band, the cohort cost,
  the repay table, the reach ceiling (`scripts/cac.py`).

**Note what is *not* on that list: any test of whether the CAC is good
enough.** There is no LTV:CAC bar in this skill, and no STRONG/FAILS verdict
on economics. LTV on a pre-product idea is a competitor's price divided by an
assumed churn rate — a ratio built from numbers nobody measured — and a skill
has no business retiring someone's idea on that basis. Your job ends at *"a
customer costs about $205, up to $427 if the funnel disappoints; at $49/mo
that's 5–10 months of retention to pay back; here are your options."*
**Whether that's worth it is the user's call, and you say so explicitly.**
Full rationale, formulas, and the handoff script: `references/economics.md`.

The one exception: if the *user* names a maximum they'd pay per customer,
record it at intake (`maze.py init --cac-ceiling`) and report measured CAC
against **their** line, labelled as theirs.

**"Cheap acquisition"** always means cheap relative to another *measured*
number — the observed price the market already pays (fast payback), the head
term's CPC, the content channel's cost — never relative to an imagined LTV.
Those patterns are catalogued in `references/economics.md`, and each is a
*persistence mechanism*: a gap you cannot explain (*why is this intent still
cheap? why hasn't the auction corrected?*) is more likely planner noise or
brand contamination than free money. Every cheap-CAC claim names its pattern.

Be honest about what a forecast is: this loop produces a **measured cost of
acquisition plus the cheapest real-world test that would confirm it** (e.g. a
$200 landing-page ad test with a target cost-per-signup). It does not produce
certainty, and the report says so.

## The lab — state on disk

All state lives in a lab directory so the loop survives context loss and every
claim stays auditable. Created by `maze.py init`:

```
research/demand/<idea-slug>/
├── maze.json           # the idea maze: nodes, statuses, scores, budget ledger
├── notebook.md         # append-only lab notebook — every action, cost, what changed
├── experiments/
│   └── E001-<slug>/
│       ├── card.md     # PRE-REGISTERED hypothesis card (frozen once data pulling starts)
│       ├── data/       # raw banked pulls (CSV/JSON from instruments — keep everything you paid for)
│       └── verdict.md  # measurements vs. thresholds, verdict, surprises
└── report.md           # the final demand forecast dossier
```

The notebook is append-only because a scientist's crossed-out ideas are data:
when a later result contradicts an earlier belief, both entries must survive.
Write a notebook entry after every phase step: timestamp, what you did, what it
cost, and what changed — a verdict, an explanation, a premise, or explicitly
"nothing".

## The loop

Phases 2→6 repeat until a stopping condition. Read the listed reference file
*before* running its phase — they are field manuals, not optional context.

### Phase 0 — INTAKE (free)

Write the mission brief as the first notebook entry:

- The vague idea, verbatim, plus anything the user fixed (geo, B2B/B2C,
  budget, deadline).
- **Data budget** in USD. Default **$3.00 / ~40 billable calls** if the user
  is absent; confirm with the user when they're available. Instruments cost
  real money from small shared balances — the ledger tracks every cent.
- **The bar** (defaults above) — thresholds chosen *now*, before any data.
- **CAC ceiling — the user's, or none.** Ask once, when they're available:
  *"Is there a number above which a customer is too expensive for you? I'll
  report CAC either way — this just tells me when to flag it."* Record it
  (`maze.py init --cac-ceiling`) if they name one; if they'd rather see the
  numbers first, that's the default and it costs nothing. Never invent one.
- **Scope check — expressed vs. novelty-dependent demand.** Classify the
  idea: **maze-explorable** (the pain already shows up in behavior an
  instrument can see — spend, search, hiring, workarounds; "AI meeting
  notes" qualifies) or **novelty-dependent** (the want would be *created* by
  the product existing — nobody searched for spreadsheets in 1978). These
  instruments read expressed demand only. A novelty-dependent idea can still
  be mapped through its nearest expressed pains (what people do today
  instead), but zero-signal results there are **scope, not refutation** —
  record the classification in the mission brief and carry it into the
  report's threats-to-validity.
- **Instrument check**: verify which credentials exist (`DATA_FOR_SEO_LOGIN`/
  `DATA_FOR_SEO_PASSWORD`, `BRIGHTDATA_API_TOKEN`) and note which signal
  families are online. Missing instruments don't stop the loop — they narrow
  triangulation and get listed under threats-to-validity.

Then `maze.py init` to create the lab.

### Phase 1 — MAP (free–cheap) — read `references/maze-method.md`

Decompose the vague idea into an explicit maze along five axes — WHO (persona/
vertical) × PAIN (job-to-be-done) × WEDGE (first feature) × CHANNEL (how
they're acquired) × MODEL (who pays, how much). Enumerate 10–25 starting nodes
via `maze.py add`: the obvious mainstream node, several vertical
specializations, several adjacent pains, at least one contrarian node. Give
each a prior demand guess and a one-line rationale. Desk research with your own
knowledge plus at most 2–4 SERP calls to enumerate competitors; do not deep-dive
yet. Bank every competitor domain you surface — they are Phase 2's seed stock:
the keyword harvest starts from them.

Exit when: the maze has breadth (multiple values per axis represented), every
node is a *precise* formulation someone could build, and `maze.py tree` renders
a maze you'd defend.

### Phase 2 — PROBE (cheap, batched) — read `references/instruments.md`

Score the whole frontier coarsely with the fewest billable calls.

**Clusters are harvested, not invented.** You are a strong judge of buyer
vocabulary and a weak generator of it — terms written from imagination measure
your guesswork, not the market. Build every node's cluster by the **footprint
traversal** (full procedure in instruments.md): `for-site` the 1–3
most-on-point competitor domains from Phase 1's census → the keywords they
already monetize; SERP the best harvested terms → domains the census missed;
`for-site` the best new domain, and lift category language from long-running
ad creatives (dataforseo-ads-transparency, copy downloads free) → more
vocabulary; stop when a hop stops yielding (usually 2–3 hops). Then *select* —
that's the part you're good at: assign 5–15 commercial-intent terms per node,
dedupe, strip navigational/brand terms. Your own formulations only fill holes
the harvest left, and each carries a `guessed` label — at JUDGE, zero volume
on a guessed cluster impeaches the guess, not the demand.

The batching levers matter more than anything else you do this phase:

- **One `search-volume` call prices up to 1000 keywords.** Harvest and assign
  every node's cluster first, then price all of them in ONE call — never one
  call per node.
- **1–2 `for-site` calls seed the whole maze's vocabulary** (~2000 rows each,
  volumes and CPCs already attached) — shared across every node that
  competitor touches.
- One App Store `search` per distinct category, shared across nodes.
- 1–2 SERP calls per *promising* node, none for obvious duds.

Score each node 0–5 on the demand rubric (in maze-method.md), update via
`maze.py set`, and prune the clearly dead (no search demand anywhere on the
cluster, or a beloved free incumbent owning the whole space). Record the
pruning reason — negative results are deliverables.

Exit when: every root node has a demand score and the frontier is ranked.

### Phase 3 — HYPOTHESIZE (free) — read `references/experiment-patterns.md`

For the top 2–4 nodes, write a **pre-registered hypothesis card**
(`maze.py exp <node> --slug <slug>` creates the experiment dir; copy
`assets/hypothesis-card.md`). A card states, *before any deep data is pulled*:

- **The explanation** — the theory the numbers will test, as numbered
  premises (X1, X2, …): what mechanism causes this WHO's pain, why incumbents
  leave it unsolved, why now, and — for cheap-acquisition hunts — why the gap
  would persist. It must be **hard to vary**: if you could swap the WHO and the
  text still read true, it explains nothing; sharpen until it forbids
  something. Thresholds are *derived* from premises, so a miss tells you
  *which premise died* — knowledge that transfers to every maze node sharing
  that premise.
- The falsifiable claim with **numeric thresholds** ("≥8k/mo commercial-intent
  cluster volume in US; CPC ≤ $6; ≥1 sustained advertiser; incumbent rating
  ≤ 4.2"), each threshold naming the premise it tests
- **Kill criteria** — the specific observation that refutes it, and which
  premise it kills
- The experiment plan: which patterns (P1–P11), which instruments, expected
  cost, ordered **cheapest-killer-first**

Pre-registration is the heart of the method. Thresholds chosen after seeing
data always pass; thresholds chosen before are predictions that can fail. Once
data pulling starts the card is frozen — new insight goes in a *new* card or an
explicitly-logged amendment, never a silent edit.

### Phase 4 — EXPERIMENT (the spend phase)

Run each card's plan cheapest-killer-first, so a doomed hypothesis dies for
cents: if the search probe already breaks a kill criterion, stop — don't spend
the rest of the plan out of momentum. Bank every raw result into
`experiments/E###/data/` (`--csv`/`--raw` flags — you paid for it, keep it).
Log spend with `maze.py spend` after every billable call and check
`maze.py status` against budget before every discovery-mode call (those bill
per returned row).

Triangulate: a card that only ever measured one signal family cannot validate,
so plans span ≥2 families by construction.

Surprises found mid-experiment (an adjacent pain screaming from reviews, an
unexpected competitor) go into the notebook and become *new maze nodes* at the
next TRAVERSE — do not chase them mid-experiment.

### Phase 5 — JUDGE — read `references/economics.md`

For each completed card, price acquisition with `cac.py` (never do this
arithmetic in your head):

```bash
python3 .claude/skills/demand-forecasting/scripts/cac.py \
    --cpc 3.20 --funnel-preset b2b_smb --price 99 --price 199 \
    --volume 9400 --label "N07 dental AI receptionist" \
    --json research/demand/<slug>/experiments/E003-*/data/cac.json
```

It outputs the CAC band (conservative / base / optimistic), what 10 and 100
customers cost, how many months of retention repay CAC at each *observed*
price point, the reachable-customer ceiling, and — if you pass the P4 inputs —
the content-channel CAC beside the paid one. It deliberately emits **no
verdict on whether that CAC is acceptable**; that is the user's judgement, and
Phase 7 asks them for it.

Then write `verdict.md`: each pre-registered threshold vs. what was measured,
the CAC block, and the verdict —

- **VALIDATED** — all thresholds met, survived kill attempts from ≥2
  families, the card's explanation survived intact, and CAC is measured and
  reported (its *size* is not a pass/fail condition)
- **REFUTED** — a kill criterion fired (say which, with the number, and
  **which premise died**)
- **INCONCLUSIVE** — name the *specific missing measurement* and its cost;
  either buy it (budget permitting) or park the node saying so

A fired kill criterion refutes a *conjunction*: the premise under test AND
the instrument's theory of what it measures AND the background assumptions.
Before writing REFUTED, state the best explanation of the observation and the
strongest rival, and why the rival loses. If the better explanation is
instrument blindness — a B2B pain that never gets searched, apple-ads' EU-only
lens, a geo mismatch — the verdict is INCONCLUSIVE (name the blind
instrument), not REFUTED. Demand that isn't there and demand your instruments
can't see must never share a verdict word.

Record the measured cost on the node —
`maze.py set N07 --cac-base 160 --cac-cons 333` — so the tree and frontier
carry it into every later decision.

Grade the *card's predictions* against what the card predicted, not what feels
right in hindsight; a refuted favorite stays refuted. But never grade the CAC:
"$333 conservative" is the finding, and there is no sentence after it that
begins "which means this idea…".

### Phase 6 — TRAVERSE

Update the maze (`maze.py set`, then `maze.py tree` to see it):

- REFUTED/pruned nodes: terminal, with reasons (resurrection allowed only if
  *new* evidence arrives — log why).
- VALIDATED or near-miss nodes: **spawn children** by specializing one axis at
  a time (narrower WHO, sharper WEDGE, different CHANNEL) — winners usually
  hide one level deeper than the first win.
- Spawn **reach children** too: whatever mechanism the surviving explanation
  names applies to every WHO that shares it ("compliance notes eat unpaid
  evenings" reaches lawyers, home health, social work). Tag them
  `reach-of N##` in the rationale — corridors your explanation predicts and
  nobody's axis grammar proposes are where outsized wins hide.
- **Propagate refutations.** A REFUTED card killed a *premise*, not just its
  node. Sweep the maze for nodes whose rationale leans on the same premise
  and re-score or prune them, citing the experiment. One cheap experiment
  collapsing a whole corridor family is the method working, not a shortcut.
- Promote serendipity notes from Phase 4 into real nodes.
- **Follow the user's choice.** If they've already picked from an options
  menu (Phase 7, or an interim handoff), that choice sets the next
  specialization: "charge more" → a MODEL child, "change channel" → a CHANNEL
  child, "narrow the WHO" → the sub-vertical whose tail CPC you measured.
- Re-rank with `maze.py frontier`.

A uniformly weak frontier indicts the decomposition, not the territory: the
five axes are themselves a conjecture about where demand variation lives. If
a probe round leaves nothing above score 2, re-map (Phase 1 is cheap) with a
different pain vocabulary or axis values before concluding the idea is empty.

**Stop when any of:** (a) ≥1 node VALIDATED at the bar and the user asked for
a winner; (b) budget ≥90% spent; (c) frontier empty; (d) two consecutive
iterations changed nothing — no verdict, score, or explanation moved.
Otherwise loop to Phase 2 (new territory) or
Phase 3 (deepen survivors). Always land on Phase 7 — including when everything
died: "no reachable demand found here, and here's the evidence" is a
successful, money-saving outcome, and the report should say it plainly.

### Phase 7 — REPORT AND HAND THE DECISION OVER

Fill `assets/report-template.md` → `report.md`. Non-negotiables: ranked
verdicts with numbers and evidence links; the **surviving explanation** for
every VALIDATED/near-miss node, including why its acquisition stays cheap;
the **CAC block** for each (band, cost of the first 10 and 100 customers,
repay months at observed prices, reach ceiling, content CAC if measured); the
full assumptions register (every funnel/margin/price assumption and where it
came from); spend ledger total; threats to validity (instruments offline, geo
gaps, proxy weaknesses, the intake scope classification); and for each
surviving node the **cheapest real-world confirmation test** with a numeric
go/no-go line (e.g. "$200 Google Ads on these 6 exact-match terms → target
≤ $2.50 per landing-page signup; above $5, the forecast is wrong"). The
confirmation test is not an epilogue — it is the experiment that replaces the
card's weakest assumed premise (almost always the funnel, the number that
drives the CAC band's width) with a measurement; say which premise it tests.

Then close with **the decision, handed over** — the point of the whole loop:

1. **Say the CAC plainly**, band and all, with the two drivers named
   (measured CPC, assumed funnel).
2. **Say what it demands back** — repay months at each observed price, and
   the cost of the first 100 customers.
3. **Say explicitly that the worth-it call is theirs**, and why you're not
   making it: retention, margin, patience, and capital are theirs to know.
4. **Give the options menu** (economics.md has the standard five: test it /
   charge more / change channel / narrow the WHO / walk away), each with the
   number that moves if they pick it, plus a one-line "here's what I'd take,
   and why" they can overrule.
5. **Ask** — when the user is present, put the menu to them with
   AskUserQuestion and log the answer in the notebook; it steers the next
   TRAVERSE. When they're absent, leave the menu in `report.md` and stop —
   do not pick for them and spend the rest of the budget on your favourite.

When nothing cleared the bar, the verdict names the *new problem* the
failures revealed — the shared premise that killed the most corridors, and
the reframing that would dodge it — not just the no. Problems are soluble; a
well-mapped dead maze is the map to the next idea. Tell the user where the
lab directory is.

## The scientist's discipline

- **Pre-register, then measure.** Thresholds before data, always. This is
  what separates forecasting from rationalizing.
- **Explain, then predict, then measure.** Every card leads with a
  hard-to-vary explanation and derives its thresholds from it. A number that
  changes no explanation changed nothing; an explanation no number could
  change isn't one.
- **Seek refutation, not confirmation.** Design experiments to *kill* nodes;
  what survives honest kill attempts is what you can recommend. If you notice
  yourself querying for evidence *for* a node, add the query that could break
  it.
- **Cheapest killer first.** Order every plan by cost-to-refute, not by
  interestingness.
- **Harvest keywords; don't invent them.** You are a strong judge and a weak
  generator of buyer vocabulary. Clusters come from competitor footprints
  (`for-site`), live ad copy, and SERPs — traversed website → keywords →
  websites → more keywords until hops stop yielding. Your own formulations
  only fill gaps and carry a `guessed` label: zero volume on a guessed
  cluster impeaches the guess, not the demand (INCONCLUSIVE, never REFUTED).
- **Two-family rule.** No VALIDATED verdict without *surviving kill attempts
  from* two signal families — survived, not "agreed with": agreement can be
  shopped for, survival can't. Single-source demand has fooled every founder
  it ever met.
- **Refutations are claims too.** A fired kill refutes premise AND instrument
  theory AND background assumptions — say which, and beat the strongest
  rival reading. Instrument blindness is INCONCLUSIVE, never REFUTED.
- **No prophecy.** Instruments read *expressed* demand. Zero signal on a
  novelty-dependent idea (intake's scope check) bounds the method, not the
  idea — scope the claim instead of faking a refutation.
- **Price the acquisition; don't grade it.** Report the CAC band, what it
  buys, and what it demands back — then say the worth-it call is theirs.
  Never "the economics don't work", never a ratio verdict, never a churn
  guess smuggled in to answer a retention question that belongs to the user.
- **Always give options, always with numbers.** A CAC figure alone strands
  the user; a single recommendation overrides them. Menu + a stated
  preference they can overrule (economics.md).
- **Numbers over adjectives** in every artifact: "9,400/mo cluster volume at
  $3.20 median CPC", not "strong search demand".
- **No vanity data.** "The market will be $47B by 2030" — banned. Only
  primary observables (volumes, CPCs, ranks, reviews, salaries, funding
  rounds) enter the maze.
- **Geo-tag everything.** Metrics swing 100× by geography; every number
  carries its geo, and defaults (US) are chosen at intake, not assumed
  silently.
- **Respect the ledger.** Log every billable call. Batch aggressively. Prefer
  cache hits and dry-runs. Stop at the budget line even mid-experiment.
- **Honest degradation.** Instruments offline → narrower triangulation →
  fewer families could attack the claim, and the report says so. Never
  fabricate a proxy for a measurement you couldn't take.

## Scripts

Both stdlib-only; run from the repo root. `--help` for full flags.

- `scripts/maze.py` — deterministic maze bookkeeping: `init`, `add`, `set`,
  `exp`, `spend`, `frontier`, `tree`, `status`. Auto-discovers the lab under
  `research/demand/` when there's exactly one; pass `--lab` otherwise. Use it
  for *all* state changes — hand-edited JSON drifts and breaks auditability.
- `scripts/cac.py` — acquisition cost with scenario bands: CAC, cost of the
  first 10/100 customers, months-to-repay at each candidate price, reach
  ceiling, and the content-channel alternative. No LTV, no ratio, no verdict
  — by design (see `references/economics.md`). Override the funnel preset
  whenever you measured a better anchor, and cite it.

## References — read before the phase that needs them

| File | Read before | Contents |
|---|---|---|
| `references/maze-method.md` | Phase 1 | Axes grammar, node quality, prior scoring rubric, traversal & pruning policy |
| `references/instruments.md` | Phase 2 | Every instrument: what it measures, cost, batching lever, exact commands, traps |
| `references/experiment-patterns.md` | Phase 3–4 | Probe patterns P1–P11 with kill criteria and cost estimates |
| `references/economics.md` | Phase 5 | CAC formulas, funnel presets, repay math, cheap-acquisition patterns, the decision handoff and options menu, worked example |

## Output contract

While looping, keep the user oriented with short interim updates: current
phase, maze tree snapshot, spend so far, and the single most important finding
since the last update — not raw data dumps. The final deliverable is
`report.md` (structure in `assets/report-template.md`) plus a short summary in
chat: the winner (or the honest "nothing cleared the bar"), its numbers
(cluster volume, CPC, **CAC band, cost of the first 100 customers, repay
months at the observed price**), the surviving explanation in one line, the
two families whose kill attempts it survived, total spend, and then the
handoff — the worth-it call is theirs, here are the options with their
numbers, here's what you'd take, which option do they want.

## Compressed example (shape, not gospel)

"AI meeting notes" → MAP: N01 generic notetaker (prior 2 — Otter/Fireflies own
it), N04 AI notes for *therapists* (prior 4 — compliance pain, session-heavy),
N07 AI notes for *sales calls* → CRM (prior 3 — crowded), N09 *field
technicians* voice→work-order (prior 3), … → PROBE: `for-site` the two
incumbents the census surfaced — their footprints hand you the vocabulary
buyers actually type ("golden thread documentation" — a term no one would
have invented) — assign terms to nodes, then one 400-keyword `search-volume`
call prices every cluster + two App Store searches ($0.25) →
N04 cluster 22k/mo US, CPC $4.10, incumbents rated 3.8 with billing complaints;
N01 pruned (CPC $11, three funded incumbents with 4.7 ratings) → HYPOTHESIZE
N04 — explanation first: "therapists must file a compliant note per session
(X1); it eats unpaid evenings, and they already pay for practice software
(X2); incumbents are generic notetakers bidding generic head terms, leaving
the vertical long-tail unbid (X3 — the persistence premise)"; derived
thresholds "≥15k/mo cluster, CPC ≤ $6, ≥1 sustained advertiser, incumbent
NPS gap" + kill criteria mapped to premises → EXPERIMENT: P1 search probe,
P3 review mining (200 recent
reviews of top 2 incumbents), P5 ad-sustainer check (ads-transparency:
incumbent's library holds category-term creatives with `days_running` > 300 —
someone's acquisition math works here; P11 rides along free — their proven
copy never mentions compliance, the wedge stays open), P8 pricing sweep, P6
funding scan (~$0.60) → JUDGE: `cac.py --cpc 4.10 --funnel-preset b2b_smb
--price 49 --price 99 --volume 22000` → CAC $205 base / $427 conservative;
first 100 customers $20k–43k; repay 4.9 mo at $49, 2.4 mo at $99; ceiling
~18 customers/mo; survived kills from two families (search + marketplace;
capital corroborates); cheap-acquisition pattern 2, X3 held (head terms bid
up, vertical tail unbid) → VALIDATED (demand real, CAC priced — no grade on
whether $205 is acceptable) → TRAVERSE: spawn N04a (solo practices,
self-serve) vs N04b (group practices, sales-led), plus reach child
"compliance notes for home-health nurses" (`reach-of N04` — X1/X2 apply to
any per-visit documentation duty) → iterate once more → REPORT: the CAC block
in plain words, then the options — (A) $200 ad test at ≤$2.50/signup to pin
the funnel, (B) the $99 tier that halves payback, (C) content at an estimated
~$15/customer, (D) the cash-pay sub-vertical at $2.60 CPC, (E) walk — "I'd
take A first"; ask which they want, log the answer.
