"""A Bayes net over what a search market is, with Jev supplying the tables.

The idea is not mine. Frank Dellaert showed that Jev's Choice interface is
exactly the shape of a conditional probability table row — define the
outcomes, get calibrated probabilities back — so one batched request can
supply every CPT in a network, zero-shot, and a conventional inference
engine then answers an unbounded family of queries **without another model
call**. Jev is the fallible domain expert; the graph is the reasoning.

That is this skill's own contract, sharpened. Before this, thirteen claims
were judged independently and composed with `and`: findings could not
constrain one another, evidence could not propagate, and every new question
cost another request. A joint distribution fixes all three at once.

What it adds here:

* **An answer, not just facts.** "P(you can buy customers here profitably)
  = 0.31" is what the reader came for; the claims are why.
* **Queries nobody paid for.** Once the tables exist, any posterior is
  arithmetic.
* **A principled next probe.** Expected entropy reduction over the thing the
  reader cares about, computed exactly, replacing a model's guess at how
  useful a measurement would be.
* **Still no thresholds.** Code computes the statistics, Jev says what each
  one means for its observed node, and that enters as *virtual evidence* —
  the correct formalism for "0.8 sure this is an expensive market".

**Calibration is unverified.** Jev is trained for calibration and the Asia
network it was demonstrated on is famous enough to be in anyone's training
data; this network is not, which removes that particular taint and removes
the reassurance with it. `evals/` measures whether the posteriors move the
right way under evidence, which is a weaker claim than being correct.
"""

from __future__ import annotations

import itertools
import math
from dataclasses import dataclass, field
from typing import Mapping, Sequence

import jev

# --------------------------------------------------------------------------
# The variables.
#
# Latent nodes are what a reader wants to know and no instrument measures.
# Observed nodes are what the keyword data can see. Decision nodes are the
# three ways into a market, and they are consequences of the latent
# properties rather than causes of anything — which is why they hang at the
# bottom with no children.
# --------------------------------------------------------------------------

# Each statement is atomic and, where it needs one, comparative. An earlier
# set asked absolute questions — "demand is larger this year than last, and
# rising rather than merely fluctuating" — which bundles two claims and
# offers no reference class. Read literally, with nothing to compare against,
# the honest answer to most of them is no, and the prior for `growing` came
# back at 0.00: no market ever grows. The model was not being unhelpful; the
# question had no scale in it.
LATENT: dict[str, str] = {
    "demand_real": "people here are willing to pay someone to solve this",
    "intent_legible": "the words people search usually reveal what they want",
    "category_open": "buyers here have not yet settled on who supplies this",
    "free_substitute": "many people here solve this themselves for free "
                       "instead of paying",
    "growing": "more people search for this than did a year ago",
}

OBSERVED: dict[str, str] = {
    "o_money": "advertisers pay more per click here than in a typical market",
    "o_crowd": "more advertisers compete for these searches than in a "
               "typical market",
    "o_brand": "the searches name particular companies",
    "o_diy": "the searches look for free, manual or do-it-yourself routes",
    "o_vague": "the largest searches do not reveal what the person wants",
    "o_up": "there is more searching now than there was a year ago",
    "o_spread": "the searching is spread across many distinct terms rather "
                "than concentrated in a few",
    "o_gradient": "narrowing a search changes its click price sharply",
}

# The three questions this instrument can actually settle.
#
# An earlier set had `content_viable` — can you earn customers by being
# found? Asked which properties bear on it, Jev gave the identical sign
# pattern it gave for paid advertising (+,+,+,-,+) with near-total
# confidence, which is the model saying there is nothing here that tells the
# two apart. It is right: keyword data says what people want and what a
# click costs, and nothing whatever about whether you could rank. A number
# for it would have been an assertion the instrument cannot see, which is
# the failure this whole skill exists to avoid.
#
# `niche_entry` came back at 0.26-0.38 confidence on every property, which
# is the model reporting a badly specified variable rather than a hard one.
#
# A replacement, `head_is_a_trap`, was tried and also dropped: its table came
# back flat, 0.58 to 0.69 across all eight rows, which is the model saying
# these properties do not determine that. It was right — whether the head
# term is a trap turns on the measured price gap between head and tail, a
# fact the data states outright rather than a hidden property to infer. Two
# nodes that move are worth more than three where one does not.
DECISION: dict[str, str] = {
    "paid_viable": "buying customers here with search ads can pay for itself",
    "incumbents_hold_it": "entering here means taking customers from "
                          "established names rather than finding new ones",
}

# Parents. Latent nodes are roots; each observed node hangs off the one
# latent property it is evidence about; each decision node depends on the
# three properties that actually decide it.
#
# The structure is fixed rather than mined per run. A structure fitted to
# each market would be easy to vary — you could always find one that
# flattered the data — and this one has to survive every market it meets.
#
# It was drawn by hand and then audited: Jev was asked, for each
# measurement, which property it is most evidence about. It agreed with six
# of eight edges and corrected two, both of which it was right about. That
# audit cost $0.000078, which makes "I guessed the structure" an expensive
# thing to leave unchecked. See evals/LEDGER.md, it-11.
PARENTS: dict[str, tuple[str, ...]] = {
    **{name: () for name in LATENT},
    "o_money": ("demand_real",),
    "o_crowd": ("demand_real",),
    # Two parents, on Jev's advice. Asked which property a search naming a
    # company is evidence about, it answered `intent_legible` at 0.69 against
    # 0.15 for the `category_open` edge drawn here by hand — and it is right
    # that naming a company is about as legible as intent gets. It is also
    # evidence the category is settled. A single parent forced a false
    # choice between two true things.
    "o_brand": ("category_open", "intent_legible"),
    "o_diy": ("free_substitute",),
    "o_vague": ("intent_legible",),
    "o_up": ("growing",),
    # Also reparented on Jev's advice (0.53 against 0.21 for the hand-drawn
    # edge, at low confidence). A market whose searching spreads across many
    # distinct terms is one whose vocabulary has not consolidated, which is
    # a statement about whether the category is settled rather than about
    # whether any one search is readable.
    "o_spread": ("category_open",),
    "o_gradient": ("intent_legible",),
    # Every latent property, because that is what Jev said when asked which
    # of them bear on paid acquisition: all five, four at 0.98 confidence or
    # better. Thirty-two rows is still one batched request.
    "paid_viable": ("demand_real", "intent_legible", "category_open",
                    "free_substitute", "growing"),
    "incumbents_hold_it": ("category_open", "demand_real", "free_substitute"),
}

ALL: dict[str, str] = {**LATENT, **OBSERVED, **DECISION}

# Which observed node a probe would most inform. Used to price a probe by
# what it would actually settle, rather than by a guess at its usefulness.
PROBE_INFORMS: dict[str, str] = {
    "resolve": "o_vague",
    "diy": "o_diy",
    "brands": "o_brand",
    "vocabulary": "o_brand",
    "money": "o_money",
    "premium": "o_money",
    "intents": "o_vague",
    "segment": "o_gradient",
    "minority": "o_spread",
    "movers": "o_up",
    "season": "o_up",
    "rivals": "o_brand",
    "head": "o_vague",
    "adjacent": "o_spread",
    "outlier": "o_spread",
}


def assignments(names: Sequence[str]) -> list[tuple[bool, ...]]:
    return list(itertools.product((False, True), repeat=len(names)))


def row_key(node: str, parent_state: tuple[bool, ...]) -> str:
    return node + "|" + "".join("1" if v else "0" for v in parent_state)


# --------------------------------------------------------------------------
# Asking Jev for the tables
# --------------------------------------------------------------------------

def _phrase(node: str, value: bool) -> str:
    text = ALL[node]
    return text if value else f"it is NOT true that {text}"


# A prior is a base rate. Asking "is this true of this market?" with nothing
# known invites a literal no; asking about a market drawn at random from all
# of them is the question a prior actually answers, and it is how anyone
# eliciting one from an expert would put it.
ROOT_FRAME = ("Think of every commercial market that people search for on "
              "Google — every product, service, trade and category. One is "
              "picked at random and you are told nothing else about it.")


def cpt_questions() -> dict[str, jev.Question]:
    """One question per table row. All of them fit in a single request.

    Each row is a language question about a child variable under one
    assignment of its parents, exactly as a person eliciting a table from an
    expert would ask it. A Choice over two outcomes returns a row that sums
    to one by construction, and carries a confidence that says whether the
    model could tell the two apart at all.
    """
    questions: dict[str, jev.Question] = {}
    for node, parents in PARENTS.items():
        for state in assignments(parents):
            if parents:
                instructions = {
                    "about": "a commercial market that people search for on "
                             "Google",
                    "known_about_it": [_phrase(p, v)
                                       for p, v in zip(parents, state)],
                    "question": "Taking `known_about_it` as given and "
                                "everything else as unknown, is `statement` "
                                "true of this market?",
                    "statement": ALL[node],
                }
            else:
                instructions = {
                    "setup": ROOT_FRAME,
                    "question": "Is `statement` true of the market that was "
                                "picked?",
                    "statement": ALL[node],
                }
            questions[row_key(node, state)] = jev.Choice(
                instructions=instructions,
                criteria={"true": f"Yes — {ALL[node]}",
                          "false": f"No — {_phrase(node, False)}"})
    return questions


def observation_questions(readings: Mapping[str, str]) -> dict[str, jev.Question]:
    """Turn each measured statistic into a belief about its observed node.

    This is where a number becomes a judgment, and it is the reason this
    network contains no thresholds. Code computes "the click price here is
    $16.08 against $3.40 across everything measured"; whether that makes
    this an expensive market is a question about meaning, and it goes to
    Jev. The answer enters the network as virtual evidence rather than as a
    hard true/false, because "0.8 sure" is the honest input.
    """
    questions: dict[str, jev.Question] = {}
    for node, reading in readings.items():
        if node not in OBSERVED or not reading:
            continue
        questions["obs:" + node] = jev.Noul(
            instructions={"measurement": reading,
                          "question": f"Reading this measurement: is it true "
                                      f"that {OBSERVED[node]}?"},
            criteria={"true": f"Yes — the measurement shows that "
                              f"{OBSERVED[node]}",
                      "false": f"No — the measurement shows otherwise, or "
                               f"says nothing either way"})
    return questions


def readings(stats: Mapping[str, object]) -> dict[str, str]:
    """Turn computed statistics into the sentences Jev judges.

    Every observed node is comparative — "more than a typical market" — and
    the comparison is the part this skill cannot make. It has measured a
    handful of markets; Jev has seen the distribution. So code states the
    number plainly and the reference class comes from the model, which is
    the same division of labour as everywhere else: code counts, Jev
    concludes.
    """
    g = stats
    out: dict[str, str] = {}
    if g.get("click_price") is not None:
        out["o_money"] = (
            f"Advertisers here pay about ${g['click_price']:.2f} for a "
            f"click, weighted by how much each term is searched. The "
            f"dearest single term goes for ${g.get('max_cpc', 0):.2f}.")
    if g.get("competition") is not None:
        out["o_crowd"] = (
            f"Google rates competition for these searches at "
            f"{g['competition']:.0f} out of 100, and "
            f"{g.get('paid_share', 0) * 100:.0f}% of the keywords carry a "
            f"click price at all.")
    if g.get("branded_share") is not None:
        out["o_brand"] = (
            f"{g['branded_share'] * 100:.0f}% of the searching names a "
            f"company outright"
            + (f" ({', '.join(g.get('brands', [])[:5])})."
               if g.get("brands") else "."))
    if g.get("self_serve_share") is not None:
        out["o_diy"] = (
            f"{g['self_serve_share'] * 100:.0f}% of the searching whose "
            f"intent is clear is people looking to solve this without "
            f"buying anything — free versions, templates, doing it "
            f"themselves.")
    if g.get("unclear_share") is not None:
        out["o_vague"] = (
            f"{g['unclear_share'] * 100:.0f}% of the searching is in terms "
            f"whose words do not reveal what the person wants — the same "
            f"phrase covering someone buying, someone studying and someone "
            f"job hunting.")
    if g.get("growth") is not None:
        out["o_up"] = (
            f"The last twelve months of searching ran at "
            f"{g['growth']:.2f} times the twelve months before them.")
    if g.get("topics") is not None:
        out["o_spread"] = (
            f"The searching divides into {g['topics']} distinct things "
            f"people look for, and the five largest terms are "
            f"{g.get('top5_share', 0) * 100:.0f}% of all of it.")
    if g.get("gradient") is not None:
        out["o_gradient"] = (
            f"Narrowing a search changes its click price by up to "
            f"{g['gradient']:.1f} times — the sharpest case here is "
            f"{g.get('gradient_example', 'a qualified term')}.")
    return out


# --------------------------------------------------------------------------
# The engine
# --------------------------------------------------------------------------

@dataclass
class Net:
    """Exact inference by enumeration over the latent roots.

    Only the five latent nodes need enumerating: every other node is a leaf
    given its parents, so its contribution collapses to a sum of two terms.
    Thirty-two states, exact, microseconds — no approximation and no
    dependency.
    """

    cpt: dict[str, float] = field(default_factory=dict)
    low_confidence: list[str] = field(default_factory=list)

    def p_true(self, node: str, state: tuple[bool, ...]) -> float:
        return self.cpt.get(row_key(node, state), 0.5)

    def _leaf_factor(self, node: str, roots: dict[str, bool],
                     evidence: Mapping[str, float]) -> float:
        """A leaf's contribution, marginalised or weighted by soft evidence."""
        state = tuple(roots[p] for p in PARENTS[node])
        p = self.p_true(node, state)
        q = evidence.get(node)
        if q is None:
            return 1.0                      # unobserved: sums to one
        return p * q + (1.0 - p) * (1.0 - q)

    def _root_posterior(self, evidence: Mapping[str, float]
                        ) -> list[tuple[dict[str, bool], float]]:
        names = list(LATENT)
        out: list[tuple[dict[str, bool], float]] = []
        total = 0.0
        for state in assignments(names):
            roots = dict(zip(names, state))
            w = 1.0
            for name, value in roots.items():
                prior = self.p_true(name, ())
                w *= prior if value else (1.0 - prior)
            for node in ALL:
                if node in LATENT:
                    continue
                w *= self._leaf_factor(node, roots, evidence)
            out.append((roots, w))
            total += w
        if total <= 0:
            return [(r, 1.0 / len(out)) for r, _ in out]
        return [(r, w / total) for r, w in out]

    def posterior(self, evidence: Mapping[str, float] | None = None
                  ) -> dict[str, float]:
        """P(node = true | evidence) for every node in the network."""
        evidence = dict(evidence or {})
        roots = self._root_posterior(evidence)
        out: dict[str, float] = {}
        for name in LATENT:
            out[name] = sum(w for r, w in roots if r[name])
        for node in ALL:
            if node in LATENT:
                continue
            out[node] = sum(
                w * self.p_true(node, tuple(r[p] for p in PARENTS[node]))
                for r, w in roots)
        return out

    # -- value of information --------------------------------------------

    @staticmethod
    def _entropy(p: float) -> float:
        if p <= 0.0 or p >= 1.0:
            return 0.0
        return -(p * math.log2(p) + (1 - p) * math.log2(1 - p))

    def expected_gain(self, observe: str, targets: Sequence[str],
                      evidence: Mapping[str, float] | None = None) -> float:
        """Bits of uncertainty about `targets` that measuring `observe` removes.

        This is what the loop's DECIDE step was reaching for when it asked a
        model to rate how much a probe would change the picture. The network
        can answer it exactly: work out how likely each outcome of the
        measurement is, take the posterior each outcome would leave, and
        weigh the resulting uncertainty against what there is now.
        """
        evidence = dict(evidence or {})
        if observe not in OBSERVED:
            return 0.0
        before = self.posterior(evidence)
        now = sum(self._entropy(before[t]) for t in targets)
        # A probe does not add an observation that was missing; it *settles*
        # one already held softly. Reading a market as "0.6 sure the free
        # route dominates" and then paying to find out for certain is worth
        # something, and an earlier version scored it at zero because the
        # node already appeared in the evidence — which stopped the loop
        # after one iteration every time. The question is what pinning this
        # down would be worth, so the outcome is weighed by how likely each
        # answer currently looks.
        p_obs = before.get(observe, 0.5)
        after = 0.0
        for outcome, weight in ((1.0, p_obs), (0.0, 1.0 - p_obs)):
            if weight <= 0:
                continue
            post = self.posterior({**evidence, observe: outcome})
            after += weight * sum(self._entropy(post[t]) for t in targets)
        return max(0.0, now - after)


    def attribution(self, target: str, evidence: Mapping[str, float]
                    ) -> list[tuple[str, float]]:
        """Which measurement moved this conclusion, and by how much.

        A posterior on its own is a number to be taken on trust. Removing
        one piece of evidence and re-inferring says what that piece was
        worth — so the report can say not just that buying customers here
        looks hard, but that it is the free substitute saying so. Each
        re-inference is thirty-two states, so the whole attribution is
        cheaper than one API call by several orders of magnitude.

        Positive means the measurement pushed the conclusion up.
        """
        full = self.posterior(evidence)[target]
        out = []
        for node in evidence:
            without = {k: v for k, v in evidence.items() if k != node}
            out.append((node, full - self.posterior(without)[target]))
        return sorted(out, key=lambda x: -abs(x[1]))

    def best_probe(self, targets: Sequence[str],
                   evidence: Mapping[str, float] | None = None
                   ) -> list[tuple[str, float]]:
        """Every unmeasured observation, ranked by what it would settle."""
        return sorted(
            ((node, self.expected_gain(node, targets, evidence))
             for node in OBSERVED),
            key=lambda x: -x[1])


def build(result: jev.Result) -> Net:
    """Read a batched answer set into a network."""
    net = Net()
    for node, parents in PARENTS.items():
        for state in assignments(parents):
            key = row_key(node, state)
            if key not in result:
                continue
            answer = result.choice(key)
            net.cpt[key] = answer.probabilities.get("true", 0.5)
            # A row the model could not split is a row to distrust, and
            # saying which rows those are is more useful than hiding them.
            if answer.confidence < 0.35:
                net.low_confidence.append(key)
    return net


def read_evidence(result: jev.Result, nodes: Sequence[str]) -> dict[str, float]:
    return {node: result.noul("obs:" + node).noul
            for node in nodes if "obs:" + node in result}
