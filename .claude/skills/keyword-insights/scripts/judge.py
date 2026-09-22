"""Every judgment in this skill. Nothing here does arithmetic.

The division of labour the whole method rests on:

    Code counts.  Jev concludes.

Code may sum, divide, sort and compare, because jev-1.13 provably cannot.
Jev decides what a phrase means, whether a statement is true of a set of
searches, whether it forbids anything, whether it was worth measuring, and
which of two findings matters more. Those are the questions with no constant
in them, and a constant invented by the author is the easiest part of any
method to vary.

Each stage asks *atomic* questions — one dimension per question — and lets
code compose. A question that bundles three dimensions comes back with low
confidence, which is the model correctly reporting that the question was
badly formed rather than the model being unreliable.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Sequence

import jev
import kgraph as K
import serp as S

# A Noul's 0.5 is not a tuned constant — it is the point at which the model
# says yes rather than no. Where this module uses a different number, the
# docstring says why that asymmetry is deliberate.
YES = 0.5

# Confidence is a separate signal from probability. A Choice that picks an
# option at 0.35 confidence is telling us the options were not distinguishable
# for this input, which is information, not noise — so those assignments are
# held back rather than silently believed.
ASSIGN_CONFIDENCE = 0.55

# A Choice's confidence falls as options are added, so a fixed floor means
# something different for a 3-option question than an 8-option one. What
# actually matters is whether the winner was distinguished from its nearest
# rival, which is a property of the distribution rather than a number chosen
# by the author.
DECISIVE_MARGIN = 2.0


def decisive(answer: jev.ChoiceAnswer) -> bool:
    ranked = sorted(answer.probabilities.values(), reverse=True)
    if len(ranked) < 2:
        return True
    runner_up = ranked[1]
    return runner_up <= 0 or ranked[0] >= DECISIVE_MARGIN * runner_up

NONE = "none_of_these"

# A Choice spreads one unit of probability across its options, so its
# answers stop being distinguishable long before the 255-option ceiling.
# Ranking happens in groups this size for that reason.
GROUP = 8

# Decoys for the swap test. Unrelated to each other and to any plausible
# market, so a claim that survives substitution was never about its subject.
DECOYS = ("artisan sourdough starters", "municipal parking permits",
          "competitive ice fishing", "vintage typewriter ribbon")


@dataclass
class Stage:
    """What one judgment stage cost and concluded."""

    name: str
    questions: int
    usage: jev.Usage
    notes: list[str] = field(default_factory=list)


def _market_state(graph: K.Graph, asker: str) -> dict:
    """The small shared header every question is answered against.

    Deliberately tiny. Accuracy falls as irrelevant state grows, so each
    question carries its own evidence in its instructions instead — the
    state says only where we are and who is asking.
    """
    return {
        "market": graph.seed,
        "country": graph.geo or "United States",
        "who_is_asking": asker,
    }


# --------------------------------------------------------------------------
# Orient, part 1: what do the mined phrases mean?
# --------------------------------------------------------------------------

def confirm_phrases(client: jev.Client, graph: K.Graph,
                    phrases: Sequence[str], asker: str) -> Stage:
    """Sort mined n-grams into things, modifiers and noise.

    A phrase can only anchor a cluster if it names something people want.
    "crm software" names a thing; "best" narrows one; "login" is neither.
    Telling those apart is a question about meaning, so it is Jev's.
    """
    if not phrases:
        return Stage("confirm_phrases", 0, jev.Usage())
    questions = {}
    for i, phrase in enumerate(phrases):
        questions[f"kind:{i}"] = jev.Choice(
            instructions={
                "phrase": phrase,
                "market": graph.seed,
                "question": "People type `phrase` as part of their searches. "
                            "What is `phrase` doing in those searches?",
            },
            criteria={
                "thing": "It names the thing people are looking for — a "
                         "product, service, category or subject in its own "
                         "right",
                "qualifier": "It narrows or describes something else — a "
                             "price, a quality, an audience, a place, a "
                             "stage of shopping",
                "noise": "It is a fragment, a brand's own word, or does not "
                         "describe anything people are looking for",
            })
    result = client.ask(_market_state(graph, asker), questions)
    notes = []
    for i, phrase in enumerate(phrases):
        answer = result.choice(f"kind:{i}")
        if answer.choice == "thing" and answer.confidence >= ASSIGN_CONFIDENCE:
            graph.add_topic(phrase, kind="mined", confirmed=True)
        elif answer.choice == "qualifier":
            notes.append(f"qualifier: {phrase}")
    return Stage("confirm_phrases", len(questions), result.usage, notes)


def confirm_entities(client: jev.Client, graph: K.Graph,
                     candidates: Sequence[str], asker: str) -> Stage:
    """Which mined tokens name a company or product someone sells?

    Brands matter structurally: a market whose searching is full of names is
    a market where the choosing has already happened somewhere else.
    """
    if not candidates:
        return Stage("confirm_entities", 0, jev.Usage())
    questions = {}
    for i, token in enumerate(candidates):
        questions[f"brand:{i}"] = jev.Noul(
            instructions={
                "word": token,
                "market": graph.seed,
                "question": "Is `word` the name of a specific company, "
                            "product or app that someone sells?",
            },
            criteria={
                "true": "It is a proper name — a company, a product, an app "
                        "or a service that a particular business owns",
                "false": "It is an ordinary word, a category, a feature, a "
                         "place, or a description that no single business owns",
            })
    result = client.ask(_market_state(graph, asker), questions)
    for i, token in enumerate(candidates):
        if result.noul(f"brand:{i}").yes(YES):
            graph.add_entity(token, confirmed=True)
    # Attaching a confirmed name to the keywords that carry it is string
    # matching, so code does it.
    names = graph.confirmed_entities
    for kw in graph.keywords.values():
        toks = set(K.tokens(kw.term))
        kw.entities = sorted(n for n in names if n in toks)
    return Stage("confirm_entities", len(questions), result.usage,
                 [f"brands: {', '.join(names[:12])}"] if names else [])


def pick_sellers(client: jev.Client, graph: K.Graph,
                 results: Sequence[Any], asker: str) -> tuple[list[Any], Stage]:
    """Which of the sites ranking here are businesses selling the thing?

    This is the judgment that turns a word into a seed worth paying for.
    A directory, a government procurement portal, a trade magazine and a
    vendor all rank for the same commercial term, and only one of them has
    a keyword footprint that is this market's own vocabulary. Harvesting
    Capterra would return the vocabulary of all software; harvesting the
    vendor returns the vocabulary of the thing.

    Reading a title, a domain and a snippet and saying what kind of
    organisation is behind them is exactly what a literal reader does well,
    and exactly what a regex cannot.
    """
    if not results:
        return [], Stage("pick_sellers", 0, jev.Usage())
    questions = {}
    for i, r in enumerate(results):
        questions[f"kind:{i}"] = jev.Choice(
            instructions={"website": r.domain, "page_title": r.title,
                          "what_it_says": r.snippet,
                          "searched_for": graph.seed,
                          "question": "Someone searched for `searched_for` "
                                      "and this page came back. What kind of "
                                      "organisation is behind `website`?"},
            criteria={
                "sells_this": "A company whose own business is selling this "
                              "thing — its product or service site",
                "sells_something_wider": "A company that sells this among "
                                         "many other things, where this is "
                                         "one line of a much broader "
                                         "business",
                "lists_or_compares": "A directory, review site, price "
                                     "comparison or roundup of other "
                                     "people's products",
                "writes_about_this": "A publication, blog, encyclopedia or "
                                     "reference that explains it without "
                                     "selling it",
                "buys_or_regulates": "A buyer, government body, procurement "
                                     "portal or regulator, rather than a "
                                     "supplier",
                "neither": "Something else entirely — it is here by accident",
            })
    result = client.ask(_market_state(graph, asker), questions)
    sellers, notes = [], []
    tally: dict[str, int] = {}
    for i, r in enumerate(results):
        answer = result.choice(f"kind:{i}")
        r.kind = answer.choice
        r.kind_confidence = answer.confidence
        tally[answer.choice] = tally.get(answer.choice, 0) + 1
        if answer.choice == "sells_this" and decisive(answer):
            sellers.append(r)
    notes.append(", ".join(f"{v} {k}" for k, v in
                           sorted(tally.items(), key=lambda x: -x[1])))
    # A broad seller is harvested only when no focused one ranks. Its
    # keyword footprint is mostly a different market, and buying it floods
    # the corpus with vocabulary that outvotes the market's own.
    if not sellers:
        wider = [r for i, r in enumerate(results)
                 if result.choice(f"kind:{i}").choice == "sells_something_wider"]
        if wider:
            notes.append(f"no focused seller ranks here; falling back to "
                         f"{len(wider)} broader business(es)")
            sellers = wider
    if not sellers:
        notes.append("nobody ranking here is selling anything — the demand "
                     "is informational, or it is bought somewhere else")
    return sellers, Stage("pick_sellers", len(questions), result.usage, notes)


RELEVANCE_QUESTION = (
    "Is `search` about the thing the `market` market deals in? Where the "
    "words could mean more than one thing, take the meaning most people "
    "typing them intend.")
RELEVANCE_CRITERIA = {
    "true": "Yes — the search is about what this market deals in, whatever "
            "the person wants to do with it: buy it, compare options, learn "
            "about it, do it themselves, or fix it",
    "false": "No — the search is about something else: a broader subject "
             "this market is only a small part of, a neighbouring industry, "
             "other needs of the same customers, or words that mostly mean "
             "something different to the people typing them",
}

# Stated in words because Jev cannot compare numbers. Code did the
# comparison; this is its result.
OUTVOTE_MEASURED = ("This one search is typed more often each month than "
                    "every other search found in this market put together.")
OUTVOTE_QUESTION = ("Given what was measured, are most of the people typing "
                    "`search` looking for something in the `market` market?")
OUTVOTE_CRITERIA = {
    "true": "Yes — this is the market's own name, or a phrase so central to "
            "it that its volume is the market's volume",
    "false": "No — a search this common is mostly people who mean something "
             "broader or different by it, and this market is a small part "
             "of it",
}


def keep_relevant(client: jev.Client, graph: K.Graph,
                  keywords: Sequence[K.Keyword], asker: str
                  ) -> tuple[list[str], Stage]:
    """Which harvested searches actually belong to this market?

    Harvesting is worth doing and dangerous for the same reason: it takes
    whatever the business is about, and a business is usually about more
    than the market you asked about. Harvesting Radar Healthcare for
    `ambulance software` returned 503,680 searches a month of which 680
    were ambulances — the rest was the whole of UK healthcare, led by
    `health information management` at 33,100 a month.

    Left in, that corpus does not merely add noise. Topics are mined by
    volume, so the market's own vocabulary is outvoted by the incumbent's
    wider business and the report ends up about the wrong thing.

    A regex cannot do this: the market's real vocabulary includes words the
    seed never contained, which is the entire point of harvesting. Reading
    a phrase and saying whether it belongs to a named market is a question
    about meaning.

    **The question is about the subject of the search, and nothing else.**
    It used to say yes to anything "close enough that anyone selling in
    this market would care", and a seller cares about their customers'
    whole world: on `cad to bim` it admitted `structural engineering`,
    `architecture firms`, `3d modeling` and `educational buildings`, and on
    seven labelled markets it dropped 5 of 36 plainly-foreign terms (14%).
    Asking instead whether the searcher *wants what the market sells*
    dropped 94% of them and threw out 14% of the real market with them —
    `sourdough starter recipe` from sourdough, `keyword search tool` from a
    keyword tool — because people doing it themselves or learning about it
    are not buying. What they are doing is the job axis's question, and it
    already has an answer for them. Asked only whether the search is about
    what the market deals in, whatever the person wants to do with it:
    92% of the foreign terms dropped, 96% of the market kept (ledger it-21).

    One kind of intruder no wording of this question catches without
    collateral damage: a common word with a second meaning, read in the
    market's sense. That is `outvoting`'s job.

    Returns the terms to drop.
    """
    if not keywords:
        return [], Stage("relevance", 0, jev.Usage())
    questions = {}
    for i, kw in enumerate(keywords):
        questions[f"rel:{i}"] = jev.Noul(
            instructions={"search": kw.term, "market": graph.seed,
                          "question": RELEVANCE_QUESTION},
            criteria=RELEVANCE_CRITERIA)
    result = client.ask(_market_state(graph, asker), questions)
    drop = [kw.term for i, kw in enumerate(keywords)
            if not result.noul(f"rel:{i}").yes(YES)]
    kept_volume = sum(kw.volume for i, kw in enumerate(keywords)
                      if result.noul(f"rel:{i}").yes(YES))
    total_volume = sum(kw.volume for kw in keywords) or 1
    return drop, Stage(
        "relevance", len(questions), result.usage,
        [f"{len(keywords) - len(drop)} of {len(keywords)} harvested searches "
         f"belong to this market, carrying {kept_volume:,} of "
         f"{total_volume:,} searches ({kept_volume / total_volume:.0%})"])


def outvoting(client: jev.Client, graph: K.Graph,
              admitted: Sequence[K.Keyword], asker: str
              ) -> tuple[list[str], Stage]:
    """Drop a search larger than the rest of the market combined, unless
    most of the people typing it are in this market.

    The relevance question reads a phrase against a market, so a phrase
    with two meanings gets the market's meaning. `drawings` was admitted to
    `cad to bim` at 1,830,000 searches a month — 64% of the corpus on its
    own — because to someone converting CAD files, drawings are the thing
    they convert. To nearly everyone typing the word, they are pictures.
    Four rewordings of the relevance question were tried on seven labelled
    markets; each one that dropped `drawings` also threw out `bim` from a
    BIM market or `keyword research` from a keyword-research one (it-21).

    What gives it away is scale, and scale is arithmetic, so code finds it:
    no market's vocabulary is mostly one search unless that search is the
    market's own name. Code says so in words — Jev is never handed two
    numbers to compare — and Jev judges whether most of the people typing
    it could be here. Nineteen cases, three fresh asks each: every one
    right, every time — `drawings`, `3d modeling`, `nhs`, `coffee` and
    `flour` out; `sourdough starter`, `crm`, `revit` and `cad to bim` kept.

    There is no constant in the rule. "Larger than the rest combined" is
    the point where one search outvotes everything else by itself, which is
    precisely what the relevance gate exists to prevent. Only the largest
    term can be in that position, so it is the only one asked; if it is
    kept, nothing smaller can be a majority and the check ends. Across nine
    markets already run, the rule fires on one search: `drawings`.

    It stops when fewer than two other terms remain, because the larger of
    two is always the majority and a comparison that cannot fail is not a
    test — the selftest found that by asking a stub that always said no,
    and watching it strip the market to nothing.
    """
    pool = {k.term: k.volume for k in admitted if k.volume > 0}
    usage = jev.Usage()
    drop: list[str] = []
    notes: list[str] = []
    asked = 0
    # The comparison is only a test while it can fail. With one other term
    # left, the larger of two is always "more than the rest combined", so
    # the rule would ask about — and could drop — a thin market down to
    # nothing, one term at a time. It needs at least two others.
    while len(pool) >= 3:
        top = max(pool, key=lambda t: (pool[t], t))
        rest = sum(pool.values()) - pool[top]
        if pool[top] <= rest:
            break
        asked += 1
        result = client.ask(_market_state(graph, asker), {
            "outvote": jev.Noul(
                instructions={"search": top, "market": graph.seed,
                              "measured": OUTVOTE_MEASURED,
                              "question": OUTVOTE_QUESTION},
                criteria=OUTVOTE_CRITERIA)})
        usage.add(result.usage)
        if result.noul("outvote").yes(YES):
            notes.append(f"\u201c{top}\u201d is searched more than the rest "
                         f"of this market combined, and is its own head "
                         f"term — kept")
            break
        notes.append(f"\u201c{top}\u201d is searched more than the rest of "
                     f"this market combined ({pool[top]:,} a month), and most "
                     f"people typing it mean something else — dropped before "
                     f"it outvotes the market")
        drop.append(top)
        del pool[top]
    return drop, Stage("outvote", asked, usage, notes)


INVENTED_MEASURED = ("This search was not among the searches the businesses "
                     "selling here rank for — it was suggested by Google or "
                     "made by combining words — and it is typed more often "
                     "each month than any search those businesses do rank "
                     "for.")


def invented_giants(client: jev.Client, graph: K.Graph,
                    admitted: Sequence[K.Keyword], asker: str
                    ) -> tuple[list[str], Stage]:
    """Drop an invented or suggested search that outsizes everything the
    market's own businesses rank for, unless most people typing it are here.

    `outvoting` catches one search larger than the rest of the market put
    together. It missed a family of them: a price probe built `how to
    drawings`, `best drawings` and `what is drawings` from the legitimate
    topic "drawings" (as-built and construction drawings), Google gave the
    invented phrase the volume of its nearest real query — 301,000 a month,
    from "how to draw" — and the relevance question read it in the CAD
    sense. No single search was a majority; together they were 39% of the
    market and made "information" its largest part.

    The skill already knew the principle: invented keywords are hypotheses,
    harvested ones are observed commercial vocabulary. A businesses that pays
    to rank is evidence of what a market really searches, so a phrase code
    made up, or Google suggested, that is bigger than *any* search those
    businesses rank for is far more likely a common phrase in another sense.
    Code finds it; the fact goes to Jev in words; Jev judges.

    Across ten markets on disk it fires on the drawings phrases in the two
    contaminated `cad to bim` corpora and on the name of `sourdough starter`
    and its close variants, which it keeps. Twelve cases, three fresh asks:
    the drawings phrases dropped every time, the sourdough names kept every
    time, and three broader terms (`revit` for `cad to bim`, `project
    management`, `keyword research`) dropped where they had been labelled
    keep — broader subjects, which the relevance criterion itself names as
    a reason to say no, and which this rule has never reached in practice
    (it-22). With no harvest there is no observed vocabulary to compare
    against, and the rule does not apply.
    """
    harvested = [k.volume for k in admitted if k.source.startswith("site:")]
    if not harvested:
        return [], Stage("invented", 0, jev.Usage())
    ceiling = max(harvested)
    giants = sorted((k for k in admitted
                     if not k.source.startswith("site:")
                     and k.volume > ceiling),
                    key=lambda k: (-k.volume, k.term))
    if not giants:
        return [], Stage("invented", 0, jev.Usage())
    result = client.ask(_market_state(graph, asker), {
        f"giant:{i}": jev.Noul(
            instructions={"search": k.term, "market": graph.seed,
                          "measured": INVENTED_MEASURED,
                          "question": OUTVOTE_QUESTION},
            criteria=OUTVOTE_CRITERIA)
        for i, k in enumerate(giants)})
    drop = [k.term for i, k in enumerate(giants)
            if not result.noul(f"giant:{i}").yes(YES)]
    notes = []
    if drop:
        big = max((k for k in giants if k.term in drop), key=lambda k: k.volume)
        notes.append(f"{len(drop)} made-up or suggested search"
                     f"{'es' if len(drop) != 1 else ''} larger than anything "
                     f"the businesses here rank for, led by \u201c{big.term}"
                     f"\u201d at {big.volume:,} a month — most people typing "
                     f"{'them' if len(drop) != 1 else 'it'} mean something "
                     f"else, so dropped")
    kept = len(giants) - len(drop)
    if kept:
        notes.append(f"{kept} larger than anything the businesses here rank "
                     f"for, and the market's own name — kept")
    return drop, Stage("invented", len(giants), result.usage, notes)


# --------------------------------------------------------------------------
# Orient, part 2: what is each searcher doing?
# --------------------------------------------------------------------------

OFFERING_CRITERIA = {
    **K.OFFERINGS,
    NONE: "None of these — one named company's own site or account, a job, "
          "or nothing that says what kind of answer they want",
}


def assign(client: jev.Client, graph: K.Graph, keywords: Sequence[K.Keyword],
           asker: str) -> Stage:
    """Place each keyword on the three axes: what it is about, what for,
    and what kind of answer would satisfy the person searching.

    Containment settles the topic axis wherever the topic is literally in the
    keyword — that is a fact about the string, and paying a model to read a
    substring is waste. Jev gets the residue (nothing matched, or several
    did) and the job axis, which no amount of string matching can reach.
    """
    if not keywords:
        return Stage("assign", 0, jev.Usage())

    topics = graph.confirmed_topics
    # A Choice caps at 255 options and one of ours is always "none of
    # these", so the topic list is truncated by measured volume, not by
    # arrival order.
    ranked = sorted(topics, key=lambda t: -sum(
        k.volume for k in graph.keywords.values() if t in k.term))
    topic_criteria = {t: f"The search is about {t}"
                      for t in ranked[:jev.MAX_CHOICE_OPTIONS - 1]}
    topic_criteria[NONE] = ("The search is about something else, or is too "
                            "general to place")

    questions: dict[str, jev.Question] = {}
    needs_topic: list[int] = []
    for i, kw in enumerate(keywords):
        matched = graph.containment_topics(kw.term)
        if len(matched) == 1:
            kw.topic, kw.topic_confidence = matched[0], 1.0
        else:
            needs_topic.append(i)
            questions[f"topic:{i}"] = jev.Choice(
                instructions={
                    "search": kw.term,
                    "question": "Someone types `search` into Google. Which of "
                                "these is the search about?",
                },
                criteria=topic_criteria)
        questions[f"job:{i}"] = jev.Choice(
            instructions={
                "search": kw.term,
                "question": "Someone types `search` into Google. What are "
                            "they trying to do?",
            },
            criteria=dict(K.JOBS))
        questions[f"offer:{i}"] = jev.Choice(
            instructions={
                "search": kw.term,
                "question": "Someone types `search` into Google. What kind "
                            "of answer are they hoping to find?",
            },
            criteria=OFFERING_CRITERIA)

    result = client.ask(_market_state(graph, asker), questions)

    low_topic = low_job = low_offer = 0
    for i, kw in enumerate(keywords):
        if i in needs_topic:
            answer = result.choice(f"topic:{i}")
            if decisive(answer) and answer.choice != NONE:
                kw.topic, kw.topic_confidence = answer.choice, answer.confidence
            else:
                # Not "unclassifiable" — unclassified. The difference matters
                # in the report, so it is kept rather than forced.
                kw.topic, kw.topic_confidence = "", answer.confidence
                low_topic += 1
        job = result.choice(f"job:{i}")
        kw.job, kw.job_confidence = job.choice, job.confidence
        kw.job_certain = decisive(job)
        if not kw.job_certain:
            low_job += 1
        offer = result.choice(f"offer:{i}")
        kw.offering = offer.choice if offer.choice in K.OFFERINGS else ""
        kw.offering_confidence = offer.confidence
        kw.offering_certain = bool(kw.offering) and decisive(offer)
        if not kw.offering_certain:
            low_offer += 1

    notes = [f"{len(keywords)} keywords judged; "
             f"{len(keywords) - len(needs_topic)} placed by containment"]
    if low_topic:
        notes.append(f"{low_topic} left unplaced (options not distinguishable)")
    if low_job:
        notes.append(f"{low_job} of {len(keywords)} searches did not reveal "
                     f"what the person wanted (no intent clearly ahead of "
                     f"the runner-up) — held out of the analysis")
    if low_offer:
        notes.append(f"{low_offer} of {len(keywords)} searches did not say "
                     f"what kind of answer they wanted — a service, "
                     f"software, a product or information")
    return Stage("assign", len(questions), result.usage, notes)


# --------------------------------------------------------------------------
# Decide: spend, or stop?
# --------------------------------------------------------------------------

def decide(client: jev.Client, graph: K.Graph, probes: Sequence[Any],
           picture: str, asker: str) -> tuple[Any | None, Stage]:
    """Choose the next measurement, or decline to make one.

    There is one stopping mechanism, not two. An earlier version also asked
    "is the picture complete?", which is a question about coverage — and
    after one expansion returning 1,651 keywords the honest answer is yes,
    so the loop stopped before it had chased anything. A person does not
    stop when the picture is complete; they stop when nothing left on the
    table looks worth the trouble. That is exactly what the bottom level of
    this rubric says, so it is the only gate needed.
    """
    if not probes:
        return None, Stage("decide", 0, jev.Usage())

    questions: dict[str, jev.Question] = {}
    for i, probe in enumerate(probes):
        questions[f"gain:{i}"] = jev.Score(
            instructions={
                "question": "We can pay for one more measurement. How much "
                            "would answering `open_question` change what can "
                            "be said about `market`?",
                "open_question": probe.label,
                "already_measured": picture,
            },
            criteria=[
                "Nothing — this covers ground already measured",
                "A little — more examples of something already understood",
                "Something real — a part of this market currently invisible",
                "A lot — it would likely change the conclusion, not just add "
                "detail",
            ])

    result = client.ask(_market_state(graph, asker), questions)
    scored = []
    for i in range(len(probes)):
        answer = result.score(f"gain:{i}")
        worthless = max(answer.probabilities,
                        key=answer.probabilities.get) == "0"
        scored.append((answer.normalized, -i, i, answer, worthless))
    scored.sort(reverse=True)
    _, _, best_i, best, worthless = scored[0]
    if worthless:
        return None, Stage("decide", len(questions), result.usage,
                           ["stopping: the best remaining question would "
                            "only re-measure what is already known"])
    chosen = probes[best_i]
    return chosen, Stage("decide", len(questions), result.usage,
                         [f"chasing: {chosen.label[:90]} "
                          f"(gain \u201c{best.label[:40]}\u201d)"])





# --------------------------------------------------------------------------
# Adjudicate: which candidate claims survive?
# --------------------------------------------------------------------------

@dataclass
class Claim:
    """A candidate finding. `text` is arithmetically true by construction —
    code built it from the numbers — so nothing below re-checks the sums."""

    key: str
    text: str
    # The same reading with every number taken out. The quality tests run
    # against this, because a sentence containing "165,000/mo at $49.28"
    # passes any test for specificity on the strength of its digits alone.
    assertion: str
    forbids: str
    evidence: dict
    examples: list[str]
    topic: str = ""
    kind: str = ""
    # The point, in the words a reader scans for: "The money is in
    # services, not software". The numbers stay in `text`.
    headline: str = ""
    # Filled by adjudication.
    reads_true: float = 0.0
    forbids_p: float = 0.0
    swappable: float = 1.0
    obvious: float = 1.0
    stakes: float = 0.0
    stakes_label: str = ""
    surprising: float = 0.0
    account: str = ""
    account_p: float = 0.0
    inert: bool = False
    weight: float = 0.0        # Jev's own share of "which matters most"
    verdict: str = "pending"
    decoy: str = ""

    def survived(self) -> bool:
        return self.verdict == "kept"


def _swap(text: str, topic: str, decoy: str) -> str:
    return text.replace(topic, decoy) if topic and topic in text else \
        f"{text} (about {decoy})"


def adjudicate(client: jev.Client, graph: K.Graph, claims: Sequence[Claim],
               asker: str) -> Stage:
    """Four atomic tests per claim, composed in code.

    Each test is separately answerable by a literal reader, which is why they
    are separate. Bundling them into one rubric produces a confident-looking
    number with no confidence behind it.
    """
    if not claims:
        return Stage("adjudicate", 0, jev.Usage())

    questions: dict[str, jev.Question] = {}
    for i, claim in enumerate(claims):
        claim.decoy = DECOYS[i % len(DECOYS)]
        shared = {"statement": claim.text,
                  "example_searches": claim.examples[:6],
                  "measurements": claim.evidence}

        # Asked against the measurements first. These statements are about
        # a whole market, and six example searches are an illustration of
        # one corner of it — a claim about where a market's money sits is
        # not shown or refuted by six rows, and asking as though it were
        # produced confident rejections of true statements.
        questions[f"true:{i}"] = jev.Noul(
            instructions={**shared,
                          "question": "Is `statement` a fair reading of "
                                      "`measurements`?"},
            criteria={
                "true": "The measurements say what the statement says they "
                        "say",
                "false": "The measurements say something different, or do "
                         "not bear on the statement at all",
            })

        # Two rival accounts of the same market, and the measurements.
        # Asking "does this rule the other out?" of a claim and its own
        # negation is a question about grammar, and always answers yes. A
        # Choice between the two accounts is a question about the data.
        questions[f"account:{i}"] = jev.Choice(
            instructions={"measurements": claim.evidence,
                          "example_searches": claim.examples[:6],
                          "question": "Two accounts of this market. Which one "
                                      "do the measurements support?"},
            criteria={
                "statement": claim.assertion,
                "rival": claim.forbids,
                "neither": "The measurements shown do not settle between "
                           "these two",
            })

        questions[f"swap:{i}"] = jev.Noul(
            instructions={"statement": _swap(claim.assertion, claim.topic,
                                             claim.decoy),
                          "question": "Could `statement` be a fair "
                                      "description of its subject?"},
            criteria={
                "true": "Yes — this reads as a plausible thing to say about "
                        "that subject",
                "false": "No — this makes a specific claim that would have to "
                         "be checked, and would probably be wrong",
            })

        questions[f"obvious:{i}"] = jev.Noul(
            instructions={"statement": claim.assertion,
                          "market": graph.seed,
                          "question": "Could someone who knows only the name "
                                      "`market`, and has seen no data, "
                                      "already say `statement` confidently?"},
            criteria={
                "true": "It follows from what the market is called, or from "
                        "general knowledge about markets",
                "false": "It reports something particular about this market "
                         "that would have to be measured to know",
            })

        # Recorded, reported, and used for ordering — never as a gate.
        # Surprise is evidence about how much a finding matters, not about
        # whether it is true; gating on it threw away eight true statements
        # in a row because they sat at 0.3-0.47, which is the model saying
        # "somewhat unusual", not "wrong".
        questions[f"odd:{i}"] = jev.Noul(
            instructions={"statement": claim.assertion,
                          "market": graph.seed,
                          "measurements": claim.evidence,
                          "question": "Markets vary. Is what `statement` "
                                      "describes out of line for a market "
                                      "like `market`, or the sort of "
                                      "variation any market shows?"},
            criteria={
                "true": "Out of line — a gap or pattern this size is unusual "
                        "and would make someone look twice",
                "false": "Ordinary — most markets would show something like "
                         "this",
            })

        questions[f"stakes:{i}"] = jev.Score(
            instructions={"statement": claim.assertion,
                          "reader": asker,
                          "question": "`reader` is about to make decisions "
                                      "about this market. What does "
                                      "`statement` do for them?"},
            criteria=[
                "Nothing — they would read it and carry on unchanged",
                "Colour — it fills in background they already assumed",
                "A choice — it tells them which of two paths to take",
                "A reversal — it says the plan they most likely arrived with "
                "is the wrong one",
            ])

    result = client.ask(_market_state(graph, asker), questions)

    for i, claim in enumerate(claims):
        claim.reads_true = result.noul(f"true:{i}").noul
        account = result.choice(f"account:{i}")
        claim.account = account.choice
        claim.account_p = account.probabilities.get("statement", 0.0)
        claim.forbids_p = claim.account_p
        claim.swappable = result.noul(f"swap:{i}").noul
        claim.obvious = result.noul(f"obvious:{i}").noul
        claim.surprising = result.noul(f"odd:{i}").noul
        score = result.score(f"stakes:{i}")
        claim.stakes, claim.stakes_label = score.normalized, score.label
        # "Most likely level is Nothing" is the model's own best guess, not
        # a cut-off chosen by the author.
        claim.inert = max(score.probabilities,
                          key=score.probabilities.get) == "0"

        # The account test is won by a majority, not a plurality. Three
        # options means the top pick can hold 0.42 while the other two
        # hold 0.58 between them — the model saying this is more likely
        # not supported than supported. Two claims on `cad to bim` were
        # kept that way, and one of them had been rejected as "the data
        # supports the opposite" the run before: a coin flip, recorded as a
        # finding. Same floor as every other test here.
        if claim.reads_true < YES:
            claim.verdict = "misread"
        elif claim.account == "rival":
            claim.verdict = "the data supports the opposite"
        elif claim.account != "statement" or claim.account_p < YES:
            claim.verdict = "the data does not settle it"
        elif claim.swappable >= YES:
            claim.verdict = "would fit any market"
        elif claim.obvious >= YES:
            claim.verdict = "knowable without data"
        elif claim.inert:
            claim.verdict = "changes nothing"
        else:
            claim.verdict = "kept"

    kept = sum(1 for c in claims if c.survived())
    return Stage("adjudicate", len(questions), result.usage,
                 [f"{kept}/{len(claims)} candidate claims survived"])


def rank(client: jev.Client, graph: K.Graph, claims: Sequence[Claim],
         asker: str) -> Stage:
    """Order the survivors by asking Jev, in groups it can tell apart.

    A Choice spreads one unit of probability across its options, so asking
    it to rank sixty near-identical findings returns noise — and it says so,
    by coming back at 0.14 confidence. Small groups keep each question
    answerable: survivors are split into groups, each group is ranked, the
    group winners are ranked against each other, and a finding's weight is
    its group's share times its share within the group.

    Every number in that product came from Jev. Ranking by a formula over
    the individual scores would put the author's weights back into the
    method by the side door.
    """
    keepers = [c for c in claims if c.survived()]
    if len(keepers) < 2:
        for c in keepers:
            c.weight = 1.0
        return Stage("rank", 0, jev.Usage())

    keepers = sorted(keepers, key=lambda c: c.key)
    groups = [keepers[i:i + GROUP] for i in range(0, len(keepers), GROUP)]
    usage = jev.Usage()

    questions = {}
    for gi, group in enumerate(groups):
        questions[f"g{gi}"] = jev.Choice(
            instructions={
                "reader": asker,
                "market": graph.seed,
                "question": "`reader` can act on only one of these findings "
                            "about `market`. Which would change what they do "
                            "the most?",
            },
            criteria={c.key: c.assertion for c in group})
    result = client.ask(_market_state(graph, asker), questions)
    usage.add(result.usage)

    within: dict[str, float] = {}
    winners: list[Claim] = []
    for gi, group in enumerate(groups):
        answer = result.choice(f"g{gi}")
        for c in group:
            within[c.key] = answer.probabilities.get(c.key, 0.0)
        winners.append(max(group, key=lambda c: within[c.key]))

    if len(winners) > 1:
        final = client.ask(_market_state(graph, asker), {
            "final": jev.Choice(
                instructions={
                    "reader": asker,
                    "market": graph.seed,
                    "question": "These are the strongest findings from each "
                                "group. Which one would change what `reader` "
                                "does the most?",
                },
                criteria={c.key: c.assertion for c in winners})})
        usage.add(final.usage)
        answer = final.choice("final")
        group_share = {w.key: answer.probabilities.get(w.key, 0.0)
                       for w in winners}
        confidence = answer.confidence
        lead = answer.choice
    else:
        group_share = {winners[0].key: 1.0}
        confidence, lead = 1.0, winners[0].key

    for gi, group in enumerate(groups):
        share = group_share.get(winners[gi].key, 0.0)
        for c in group:
            c.weight = share * within[c.key]

    return Stage("rank", len(groups) + 1, usage,
                 [f"{len(groups)} group(s) of at most {GROUP}; lead finding "
                  f"{lead} (confidence {confidence:.2f})"])


def assess_probe(client: jev.Client, graph: K.Graph, question: str,
                 after: str, asker: str) -> tuple[bool, Stage]:
    """Did the measurement we just bought answer the question we asked?

    This is the backtracking test. A person chasing a hunch knows when the
    trail has gone cold — not because a number fell below a line, but
    because what came back was not about the thing they were asking. Getting
    that judgment from Jev is what lets the loop abandon a branch and take
    another, which is the difference between following a lead and grinding
    through a checklist.
    """
    questions = {
        "answered": jev.Noul(
            instructions={"question_asked": question,
                          "what_came_back": after,
                          "question": "We paid to have `question_asked` "
                                      "answered, and `what_came_back` is "
                                      "what the measurement returned. Does "
                                      "it bear on the question?"},
            criteria={
                "true": "These searches are about the thing the question "
                        "asked about — they show what it wanted to know, "
                        "whichever way the answer falls",
                "false": "These searches are about something else, so the "
                         "question is no better answered than before",
            })}
    result = client.ask(_market_state(graph, asker), questions)
    answered = result.noul("answered")
    return answered.yes(YES), Stage(
        "assess", 1, result.usage,
        [("answered" if answered.yes(YES) else "dead end") +
         f" (P={answered.noul:.2f})"])
