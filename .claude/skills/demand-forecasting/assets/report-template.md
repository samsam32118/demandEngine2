# Demand forecast — {idea}

{date} · geo {geo} · lab `research/demand/{slug}/` · total spend ${x.xx}
({n} billable calls) · bar: cluster ≥ {min_volume}/mo, survived ≥2 signal
families, explanation intact, CAC measured — **no LTV:CAC test; whether the
CAC is worth paying is your call, see Your options** · CAC ceiling: {the
user's, if they named one} · scope: {maze-explorable | novelty-dependent}

## Verdict (one paragraph)

{The answer a busy founder reads first: the winning precise variant(s), what
a customer costs there, and what that cost demands back — or the honest
"nothing cleared the bar, here's what that saves you." No hedging fog. Say
plainly that the worth-it judgement is theirs and point at Your options. If
nothing cleared, also name the new problem the failures revealed — the shared
premise that killed the most corridors, and the reframing that would dodge
it.}

## Ranked findings

### 1. {Nxx — precise node title} — VALIDATED · CAC ${…}–${…}

- **The precise idea:** WHO / PAIN / WEDGE / CHANNEL / MODEL spelled out
- **The explanation (survived the data):** {why this demand exists — the
  card's premises post-verdict, hard to vary — and which kill attempts it
  survived, per family}
- **Demand evidence** (ladder rung + numbers + geo + date, per family):
  search {…} · marketplace {…} · competitor-capital {…}
- **What a customer costs:** CAC ${…} base / ${…} conservative / ${…}
  optimistic — from a measured ${…} CPC and an assumed {…}% funnel. First 10
  ≈ ${…}, first 100 ≈ ${…}.
- **What that demands back:** at ${…}/mo → {…} months of retention to repay
  (base) / {…} (conservative); at ${…}/mo → {…} / {…}. Prices observed via P8
  {source}.
- **Other channel:** content CAC ≈ ${…}/customer {estimate, inputs named} —
  or "not measured".
- **Cheap-acquisition pattern:** {#n from economics.md, the two-number gap,
  and the persistence explanation — why the gap exists and hasn't been
  competed away}
- **Reachable ceiling:** ~{…} customers/mo at ~${…}/mo spend
- **Evidence chain:** {E00X card → data files → verdict.md}
- **Sharpest risk:** {the one thing most likely to make this wrong}

### 2. {…near-miss / INCONCLUSIVE nodes, same shape…}

## Dead corridors (negative results — half the value)

REFUTED means "demand absent" beat its rival explanations, with the dead
premise named. Corridors the instruments merely can't see are `parked`
(INCONCLUSIVE / outside instrument reach) and listed under threats instead —
never in this table.

| Node | Why pruned/refuted (premise that died) | Evidence |
|---|---|---|
| {Nxx title} | {e.g. CPC $11 vs affordable $4; incumbents ≥4.6} | {E00X} |

## Assumptions register

| Assumption | Value used | Source | Sensitivity |
|---|---|---|---|
| funnel {node} | {…} | preset {name} / measured {…} | CAC {…}× at half this rate |
| margin, click-share, price points, content inputs, … | | | |

Retention is **not** assumed anywhere in this report — the repay table says
how long a customer must stay, and only you can say whether they will.

## Threats to validity

- {instruments offline this session, geo blind spots (apple-ads EU-only…),
  proxy weaknesses, single-snapshot caveats, data age}
- Scope: {the intake classification — if novelty-dependent, state plainly
  that zero-signal results bound the method, not the idea, and list any
  corridors parked as `outside instrument reach`}

## Recommended confirmation tests (cheapest real-world checks)

For each surviving node: {e.g. "$200 Google Ads, exact match on [6 terms],
landing page with price shown → GO if cost-per-signup ≤ $2.50; forecast
wrong if ≥ $5"} — numeric go/no-go line, budget, duration, and **which
assumed premise the test replaces with a measurement** (usually the funnel,
which is what makes the CAC band as wide as it is).

## Your options — the decision is yours

This report does not rule on whether ${…}/customer is worth paying. That
depends on your retention, your margin, your patience, and how much capital
you'll put in front of the first 100 customers — none of which is in the
data. What follows is priced; the choice isn't ours.

| # | Option | What changes | The number |
|---|---|---|---|
| A | Test it for real | ~$200 exact-match ads to a priced landing page | replaces the assumed {…}% funnel → GO at ≤ ${…}/signup |
| B | Charge more | {higher tier / annual / team plan} | repay drops from {…} to {…} months |
| C | Change channel | {content / marketplace / outbound} | ~${…}/customer vs ${…} paid (estimate) |
| D | Narrow the WHO | {sub-vertical} | tail CPC ${…} vs cluster ${…} → CAC ~${…} |
| E | Walk away | say no now, cheaply | revisit if CAC < ${…} or price > ${…} |

**What I'd take and why:** {one line — a recommendation you can overrule.}

**Pick one and I'll continue** — the choice steers the next traversal, and
gets logged in the notebook either way.

## Ledger and reproducibility

Spend ledger in `maze.json`; raw data banked under `experiments/*/data/`;
re-pulls of identical queries are cached/free. Probe again in ~a quarter —
mispricing windows move.
