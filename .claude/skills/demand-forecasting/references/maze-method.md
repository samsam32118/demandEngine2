# The idea maze — decomposition, priors, traversal

Read this before Phase 1 (MAP) and again at Phase 6 (TRAVERSE).

An "idea maze" (Balaji Srinivasan's term, popularized by Chris Dixon) is the
branching space of decisions hiding inside a vague idea: who exactly it's for,
which pain it attacks first, what the wedge feature is, how customers are
acquired, who pays. Founders who "know the maze" can say why each corridor is a
dead end and where the open doors are. This file is how you build that map
explicitly instead of carrying it as vibes.

## The five axes

Every node is a point in this space. Early nodes may leave later axes open —
that's fine; children fill them in as you descend.

| Axis | Question | Example values (for "AI meeting notes") |
|---|---|---|
| **WHO** | Which person/org, precisely, feels the pain? | therapists; SMB sales teams; field-service techs; PMs; deaf/HoH professionals |
| **PAIN** | Which job-to-be-done, in their words? | "I can't be present AND document the session"; "CRM data entry after calls"; "compliance notes take my evenings" |
| **WEDGE** | The first feature that wins on day one | auto-SOAP-notes from session audio; call→CRM autofill; voice memo→structured work order |
| **CHANNEL** | How do you reach them at a price you can pay? | Google search (they already search for it); App Store; TikTok/YouTube content; outbound email; marketplace/integration listings |
| **MODEL** | Who pays, how much, how often? | $49/mo solo practitioner; $99/seat/mo team plan; usage-priced API; free + $9.99 prosumer sub |

A node's **title** should read like a pitch a builder could act on tomorrow:
"HIPAA-safe AI session notes for solo therapists, self-serve $49/mo, acquired
via Google search" — not "healthcare vertical".

**Node quality test:** if you can't name 5–15 commercial-intent search terms a
buyer of this node would type, the node is too vague — split it or sharpen it.
(The test checks the node's *precision*, not your vocabulary: the cluster that
actually gets priced is **harvested** in Phase 2 — competitor footprints via
`for-site`, long-running ad copy, SERP phrasings — with your own formulations
only filling gaps, labeled `guessed`. See the footprint traversal in
instruments.md.)

**Rationale quality test (hard to vary):** a rationale must explain, not
label. If you can swap the WHO (therapists → dentists) and the rationale
reads equally well, it explains nothing about either — sharpen it until it
leans on something specific to this WHO's situation and thereby *forbids*
something. Easy-to-vary rationales produce vibes-priors the data can't teach
anything to, and refutations that propagate nowhere.

## Seeding the maze (Phase 1)

Aim for 10–25 root-ish nodes with deliberate spread:

- **The mainstream node** — the obvious reading of the idea. Usually crowded;
  include it anyway as the baseline everything else is measured against.
- **4–8 vertical specializations** — same pain, specific WHO. Verticals are
  where mispriced CAC usually hides, because incumbents advertise on the
  generic head terms and ignore "X for <vertical>" long-tail.
- **2–5 adjacent pains** — same WHO, different PAIN discovered by asking "what
  else does this person duct-tape?" (reviews and comments will add more later).
- **1–3 channel/model variants** of promising WHOs — the same product is a
  different business at a different CAC channel or price point.
- **≥1 contrarian node** — a corridor you believe is a dead end. Write down
  why. If your instruments *don't* kill it, your model of the maze is wrong,
  which is the most valuable thing you can learn early.

Sources for enumeration, in order of preference: your own domain knowledge
(free); the user's hints; 2–4 SERP calls ("<idea> for" autocomplete-style
sweeps, "best <idea> for <vertical>" to see what listicles segment on);
incumbent pricing pages (their plan tiers reveal the segments *they* believe
in — free intel from a paid competitor's homework); incumbent ad libraries
(dataforseo-ads-transparency `ads --target <domain>`, ~$0.002 — the segments
and pains their long-running creatives name are the corridors a competitor
has *paid* to learn convert).

## Prior demand scores (before any paid data)

Give every node a 0–5 prior with a one-line rationale. This forces you to have
a belief the data can later embarrass — the embarrassment is the learning.
The score just ranks the queue; the **rationale is the real content** — it is
the premise a later refutation will name and propagate through the maze.

The same rubric is used for measured scores in Phase 2:

| Score | Meaning (B2C, US-scoped — divide volume thresholds by ~5–10 for B2B, where queries are rarer but each is worth more) |
|---|---|
| 0 | No detectable demand: no search, no competitors, no content, no hiring |
| 1 | Traces: some content views or forum chatter; no commercial-intent search |
| 2 | Weak: cluster < 1k/mo; or interest is attention-only (views but nobody pays) |
| 3 | Moderate: 1k–10k/mo commercial-intent cluster; competitors exist but unloved or generic |
| 4 | Strong: 10k–100k/mo cluster; live CPC auction; sustained advertisers or grossing apps present |
| 5 | Heavy: >100k/mo; multiple sustained advertisers; capital actively flowing in |

Note 4–5 cuts both ways: heavy demand usually means priced-in CAC. The sweet
spot the loop hunts is typically **score 3–4 with a cheap-acquisition signal**
(economics.md) — demand that's real but the auction or the incumbents haven't
caught up.

## Traversal policy

- **Breadth first, cheaply.** Probe the whole frontier with batched
  instruments before deepening anything (Phase 2's batching levers make the
  marginal node nearly free — a 1000-keyword call prices ~20 nodes at once).
- **Depth on survivors only.** Hypothesis cards (Phase 3) go to the top 2–4
  nodes. Resist deep-diving a fascinating node that scored 1.
- **Descend by specializing ONE axis per child.** A validated node spawns
  children like: narrower WHO (therapists → solo therapists in private
  practice), sharper WEDGE, alternate CHANNEL, higher/lower MODEL. Changing
  one axis at a time keeps cause and effect readable — if the child scores
  differently, you know which decision did it.
- **Winners hide one level deeper than the first win.** A node that clears
  the bar almost always contains a child that clears it harder. Budget
  permitting, descend at least once past your first VALIDATED.
- **Descend along the explanation's reach, not only the axis grammar.**
  Axis-specialization is the default move, but a validated card's explanation
  predicts corridors the grammar never proposes: whatever mechanism validated
  this WHO applies to *every* WHO that shares it ("per-visit compliance
  documentation in unpaid time" reaches lawyers, home health, social work).
  Spawn those as new roots tagged `reach-of N##` in the rationale. Reach
  corridors are doubly valuable: your explanation predicts them, and nobody
  else's grammar does.
- **Propagate refutations through shared premises.** A REFUTED verdict names
  a dead premise (per its card). Sweep the maze for nodes whose rationale
  leans on the same premise, re-score or prune them citing the experiment,
  and log the sweep in the notebook. One cheap experiment collapsing five
  corridors is the method working, not a shortcut.
- **A uniformly weak frontier indicts the decomposition, not the territory.**
  The five axes are a conjecture about where demand variation lives. If a
  full probe round leaves nothing above score 2, re-map with a different
  pain vocabulary or axis values (Phase 1 again — it's cheap) before
  concluding the idea is dead.
- **Lateral hops are legal but logged.** Serendipity from reviews/comments
  (an adjacent pain people scream about) becomes a new node at TRAVERSE,
  tagged in its rationale as `discovered-in-flight from E###` — the notebook
  shows where every corridor came from.

## Pruning (and resurrection)

Prune a node when any of these fire, and record which one:

- **No demand anywhere**: keyword cluster ~0 volume AND no social attention
  AND no competitors monetizing. (All three — absence of competitors *alone*
  is ambiguous: it's either no demand or an unexploited corridor. Search and
  social data disambiguate.) One more gate before this prune fires: check the
  node isn't **novelty-dependent** (intake's scope check — a want the product
  itself would create). Instruments see only *expressed* demand; a
  novelty-dependent corridor with zero signal goes to `parked` with reason
  `outside instrument reach`, never `pruned` — the loop has no evidence about
  it either way, and must not pretend it does.
- **Beloved incumbent**: dominant player rated ≥4.5 with high review velocity
  and free tier covering the wedge. You'd be fighting love with features.
- **Priced out for this user**: CAC (from `cac.py`) exceeds a ceiling the
  **user themselves** named at intake, with no plausible organic channel. If
  they named no ceiling, a high CAC never prunes a node — it gets reported
  with its repay table and channel options, and they decide. The skill does
  not retire someone's idea over a number they haven't judged yet.
- **Structural blocker** the user can't change: platform dependency that's
  been shut down for others, regulated data you can't touch, etc.

Pruned ≠ deleted. Nodes stay in the maze with status `pruned` and a reason —
the map of dead corridors is half the deliverable's value ("we checked, here's
why not"). Resurrect only when *new* evidence contradicts the recorded pruning
reason, and log the resurrection explicitly.

`parked` is for nodes that are alive but unaffordable this session
(INCONCLUSIVE verdicts with a named missing measurement) — they're the first
candidates when more budget appears.

## Good node / bad node examples

- Bad: "AI meeting notes for healthcare" — WHO too broad, no wedge, no
  channel, can't write its keyword cluster.
- Good: "AI SOAP-note generator for solo therapists (WHO), kills evening
  documentation (PAIN), wedge = record session → compliant note in 2 min
  (WEDGE), acquired via Google search on 'therapy notes software' cluster
  (CHANNEL), $49/mo self-serve (MODEL)."
- Bad: "TikTok version" — a channel is not a node; attach it to a WHO/PAIN.
- Good contrarian: "Generic consumer meeting-notes app at $9.99/mo — expect
  REFUTED: head CPCs bid up by funded incumbents (Otter, Fireflies), churn
  high. Testing anyway to calibrate the maze."
