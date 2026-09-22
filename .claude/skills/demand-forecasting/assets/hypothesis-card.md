# {EID} — {node id}: {node title}

**Status:** PRE-REGISTERED {timestamp} · FROZEN once data pulling starts
**Node axes:** WHO {…} · PAIN {…} · WEDGE {…} · CHANNEL {…} · MODEL {…}

## The explanation (hard to vary — write this first)

> {3–6 sentences: the mechanism that causes this WHO's pain, why incumbents
> leave it unsolved, why now, and — for a mispricing hunt — why the gap would
> persist rather than being an artifact. Hard-to-vary test: if you could swap
> the WHO (therapists → dentists) and this still read true, it explains
> nothing about either — sharpen it until it forbids something.}

**Premises** (numbered; every threshold and kill below names the one it tests).

Write one claim per premise, on a line starting `- **X1**: …` — `judge.py
explain` parses that form, and a premise bundling two claims survives any
single result, so no experiment can kill it. Run the gate before spending:

```bash
python3 .claude/skills/demand-forecasting/scripts/judge.py explain \
    --card {this file} --who "{the WHO}" \
    --decoys "{2-5 buyers this must NOT fit, comma-separated}" \
    --out {experiment dir}/explain.json
```

It must come back **HARD**. SOFT or VARIES means sharpen and re-run — the gate
is free and the experiment is not.

- **X1**: {e.g. "solo therapists must produce a compliant note after every
  session, and do it in unpaid evening time"}
- **X2**: {e.g. "they already pay for practice software, so a $49/mo tool
  clears their purchasing bar without a sales motion"}
- **X3**: {e.g. "incumbents bid the generic head terms and ignore the
  vertical long-tail, so that auction stays cheap" — the persistence premise;
  every cheap-acquisition card needs one}

## Claim (falsifiable, numeric)

> {One sentence someone could bet against, derived from the premises. Every
> quantity has a number and a geo. Example: "US solo therapists generate
> ≥15,000/mo commercial-intent searches for AI session notes at median CPC
> ≤ $6, at least one competitor has a category-term ad with `days_running`
> ≥90 in the Google Ads Transparency library (US), and top incumbents carry a
> ≥15% recent-review complaint rate on a wedge we can build."}

## Pre-registered thresholds

| # | Metric (with geo) | Threshold | Instrument / pattern | Tests premise |
|---|---|---|---|---|
| T1 | {e.g. commercial cluster volume, US} | ≥ {n}/mo | P1 search-volume | X1 |
| T2 | {e.g. weighted median CPC} | ≤ ${n} | P1 | X3 |
| T3 | {…} | {…} | {…} | X{…} |

## Kill criteria (any one refutes — name the premise it kills)

- K1: {specific observation, e.g. "commercial cluster < 5k/mo"} → kills {X#}
- K2: {…} → kills {X#}

When a kill fires, `verdict.md` must say whether the best explanation of the
observation is *the premise being false* (→ REFUTED) or *the instrument being
blind to it* (→ INCONCLUSIVE, name the blind instrument) — state the strongest
rival reading and why it loses. TRAVERSE then re-examines every maze node
whose rationale shares a dead premise.

## Experiment plan (cheapest-killer-first)

| Step | Pattern | Instrument calls | Est. cost | Can it kill? |
|---|---|---|---|---|
| 1 | P{n} {name} | {command sketch} | ${…} | K1 |
| 2 | … | … | … | … |

**Signal families covered:** {≥2 of: search / marketplace / social /
competitor-capital / hiring} · **Total est. cost:** ${…} · **Budget check:**
{remaining budget per maze.py status}

## CAC inputs to resolve

- CPC: {which P1 cluster and subset the volume-weighted median comes from}
- Funnel: {preset planned, or measured source — this is the assumption that
  sets the width of the CAC band, and the one the confirmation test replaces}
- Price points for the repay table: {which P8 source will set them}
- Content-channel inputs, if a CHANNEL hypothesis: {P4 median views, cost per
  post}

CAC is priced here, never graded — no threshold in this card may be "LTV:CAC
≥ n" or any other test of whether the cost is worth paying. That call is the
user's, made from the numbers at Phase 7.

## Amendments (log only — never edit the sections above after freezing)

- {timestamp}: {what changed and why; spawn a new card for new claims}
