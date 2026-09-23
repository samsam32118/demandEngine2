# The state machine — states, guards, artifacts

`maze.py` holds the only executable copy of this machine (`MACHINE` in
`scripts/maze.py`); this file explains it. If the two ever disagree, the code
is right and this file is stale.

```bash
maze.py state                         # where am I, what is legal, which guards hold
maze.py state --set PROBE --note "…"  # advance; refused if the transition is undefined
```

A transition the machine does not define is refused. `--force` exists, and
using it without a notebook entry saying why is how a lab stops being
auditable.

## Why a machine at all

The expensive failures in the previous iteration were sequence failures, not
judgment failures:

- spending the instrument budget in EXPERIMENT on a card whose thresholds
  were written *after* someone glanced at the data
- writing a report from a maze where nothing was ever measured
- looping PROBE → PROBE forever because no one checked whether anything had
  moved

None of those is a hard problem to notice from outside. All of them are easy
to walk into from inside a long context. A table that refuses the transition
costs nothing and catches all three.

## The states

### INTAKE — the brief

| | |
|---|---|
| **Entry** | the user brought an idea |
| **Costs** | nothing |
| **Produces** | `maze.json`, `notebook.md`, the mission brief entry |
| **Exit (G1)** | idea verbatim, geo, instrument budget, the bar, the CAC ceiling (theirs or none), the scope classification, and the credential check are all recorded |

The scope classification is the one people skip and the one that saves the
run: **maze-explorable** (the pain already shows in behaviour an instrument
can see) or **novelty-dependent** (the want would be created by the product
existing). On a novelty-dependent idea, zero signal bounds the method, not the
idea — and the report has to say so rather than fake a refutation.

Run `jev.py check` here, not later. A loop that discovers in EXPERIMENT that
judgment is offline has already spent the budget.

**Failure mode:** inventing a CAC ceiling the user never named. Ask once; if
they would rather see numbers first, that is the default and it costs nothing.

### MAP — decompose

| | |
|---|---|
| **Entry** | G1 |
| **Costs** | 2–4 SERP calls, at most |
| **Produces** | 10–25 nodes, `census.json` |
| **Exit (G2)** | breadth on ≥2 axes and every node a precise formulation someone could build |
| **Also exits** | — |

Decompose along WHO × PAIN × WEDGE × CHANNEL × MODEL. Include the obvious
mainstream node (usually to prune it publicly), several vertical
specializations, several adjacent pains, and at least one contrarian node.

`judge.py census` turns the SERPs into ranked seed domains — the vocabulary
for the whole maze is harvested from those domains in PROBE, so a bad census
poisons every cluster downstream. When no domain clears the floor, that is
itself a finding: nobody is selling here.

**Failure mode:** nodes that are categories rather than formulations. "AI for
healthcare" is not a node; "AI session notes for solo-practice therapists
billing insurance" is.

### PROBE — measure the frontier

| | |
|---|---|
| **Entry** | G2, or G7 from TRAVERSE |
| **Costs** | the bulk of the instrument budget's *cheap* half |
| **Produces** | `triage.json`, `scores.json`, demand scores on every node |
| **Exit (G3)** | every root node has a measured demand score and the frontier is ranked |
| **Also exits** | **G4** → MAP when nothing scores above 2 · **G8** → REPORT when budget ≥90% |

Harvest, then triage, then price, then score. Clusters are harvested from
competitor footprints and live ad copy — never written from imagination. Terms
you do write carry `--cluster-source guessed` into the verdict, because zero
volume on a guessed cluster impeaches the guess, not the market.

The batching levers are the whole cost story: one `search-volume` call prices
1000 keywords, 1–2 `for-site` calls seed the maze's whole vocabulary, one App
Store `search` per category shared across nodes.

**Failure mode:** a big `unassigned` pile in `triage.json` read as noise. It
usually means the axes do not carve the market the way buyers do — which is
G4, not a rounding error.

### HYPOTHESIZE — pre-register

| | |
|---|---|
| **Entry** | G3 |
| **Costs** | nothing (`explain` is thousandths of a cent) |
| **Produces** | `card.md` per node, `explain.json` |
| **Exit (G5)** | card written, thresholds pre-registered, `judge.py explain` returned HARD |
| **Also exits** | **G6** → back to PROBE when the explanation is SOFT or VARIES |

Pre-registration is the heart of the method: thresholds chosen after seeing
data always pass; thresholds chosen before are predictions that can fail. Once
data pulling starts the card is frozen — new insight goes in a *new* card or
an explicitly logged amendment, never a silent edit.

`judge.py explain` is the gate, and it is free. It substitutes decoy buyers
into your explanation and asks, cold, whether it still reads true; it asks per
premise whether the premise forbids any observation, how narrow it is, and
whether it makes exactly one claim.

**Failure mode:** treating a SOFT result as a formality to argue past. A
premise no result can kill buys an experiment that can only confirm, which is
the most expensive thing in this skill.

### EXPERIMENT — spend

| | |
|---|---|
| **Entry** | G5 |
| **Costs** | most of the instrument budget |
| **Produces** | raw pulls in `data/`, `reviews.json`, `creatives.json`, ledger entries |
| **Exit** | the plan ran, or a kill criterion fired and you stopped |

Cheapest-killer-first, so a doomed hypothesis dies for cents. If the search
probe already breaks a kill criterion, stop — the rest of the plan is
momentum, not evidence. Bank everything you paid for. Log spend after every
billable call; check `maze.py status` before every discovery-mode call, since
those bill per returned row.

Plans span ≥2 signal families by construction: a card that only ever measured
one family cannot validate, and finding that out at JUDGE wastes the spend.

**Failure mode:** chasing a surprise mid-experiment. Note it, and let it
become a node at the next TRAVERSE.

### JUDGE — price and rule

| | |
|---|---|
| **Entry** | EXPERIMENT completed or killed |
| **Costs** | nothing |
| **Produces** | `cac.json`, `verdict.json`, `verdict.md` |
| **Exit** | a verdict is written and the CAC is on the node |

`cac.py` for the arithmetic, `judge.py verdict` for the word. Threshold
comparisons run in code exactly as pre-registered; Jev answers only whether
the measurements *contradict* the explanation (per premise, so a refutation
names what it killed) and what best explains a miss.

The three words are not interchangeable, and the distinction is the reason
this state exists:

- **VALIDATED** — thresholds met, ≥2 families survived kill attempts, the
  explanation stands, CAC measured. Nothing here grades the CAC.
- **REFUTED** — a kill fired *and* absent demand carries the probability
  mass. Name the dead premise; TRAVERSE propagates it.
- **INCONCLUSIVE** — the miss is better explained by instrument blindness, a
  geo gap or a guessed cluster; or a measurement was never taken; or only one
  family survived. Name the blind instrument and what the missing measurement
  would cost.

**Failure mode:** writing REFUTED when the honest answer is "our instruments
cannot see this market". Demand that is not there and demand you cannot see
must never share a verdict word.

### TRAVERSE — update the maze

| | |
|---|---|
| **Entry** | a verdict exists |
| **Costs** | nothing |
| **Produces** | new nodes, prunes, a re-ranked frontier |
| **Exit (G7)** | → HYPOTHESIZE to deepen a survivor, or → PROBE for new territory |
| **Also exits** | **G8** → REPORT |

Specialize one axis at a time — winners usually hide one level deeper than the
first win. Spawn **reach children** for every WHO the surviving explanation's
mechanism also covers, tagged `reach-of N##`; corridors your explanation
predicts and no axis grammar proposes are where outsized wins hide.

**Propagate refutations.** A REFUTED card killed a premise, and
`verdict.json` names it. Sweep for nodes leaning on the same premise and
re-score or prune them, citing the experiment. One cheap experiment collapsing
a corridor family is the method working, not a shortcut.

**Failure mode:** looping without moving. Two consecutive iterations in which
no verdict, score or explanation changed is G8 — stop and report.

### REPORT — the dossier

| | |
|---|---|
| **Entry** | G8 |
| **Costs** | nothing |
| **Produces** | `report.md` |
| **Exit** | the dossier is complete |

Everything in `assets/report-template.md`, and specifically: ranked verdicts
with numbers and evidence links; the surviving explanation per node including
why acquisition stays cheap; the CAC block; the assumptions register; both
spend ledgers (instruments and Jev, separately); threats to validity including
any stage where Jev was unavailable and judgment was done by eye; and the
cheapest real-world confirmation test with a numeric go/no-go line.

### DECIDE — hand it over

| | |
|---|---|
| **Entry** | the dossier is written |
| **Exit** | terminal |

Say the CAC plainly, say what it demands back, say explicitly that the
worth-it call is theirs and why you are not making it, give the options menu
with the number that moves for each, state a preference they can overrule, and
ask. When the user is absent, leave the menu in `report.md` and stop — do not
pick for them and spend the rest of the budget on your favourite.

When nothing cleared the bar, name the *new problem* the failures revealed:
the shared premise that killed the most corridors, and the reframing that
would dodge it. A well-mapped dead maze is the map to the next idea.

## The guards `maze.py state` can check for you

These are the machine-checkable ones. The judgment calls — is this a maze you
would defend, did the card really freeze before the data moved — stay with
you, which is why they appear in the transition notes above rather than
pretending to be assertions.

| Printed guard | Reads |
|---|---|
| `>= 10 nodes mapped` | node count |
| `breadth on >= 2 axes` | distinct values per axis |
| `every node has a demand score` | scored vs. total |
| `something worth deepening (best demand >= 3)` | max demand score |
| `frontier non-empty` | nodes still unexplored/probed/hypothesized |
| `budget below 90%` | instrument ledger vs. cap |
| `at least one node probed` | any node past `unexplored` |
| `a node VALIDATED` | any node validated |
