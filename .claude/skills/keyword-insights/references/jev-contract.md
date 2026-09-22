# Writing a question Jev answers well

Read this before adding or changing any question in `scripts/judge.py`.
Most of the ways this skill has been wrong were bad questions, not a bad
model — and the model said so each time, by returning low confidence.

## The three primitives

| | returns | use it for | carries confidence? |
|---|---|---|---|
| **Noul** | P(yes), 0–1 | one yes/no about meaning | **no** — the probability *is* the answer |
| **Choice** | one option + a probability for every option | which of several, relatively | yes |
| **Score** | a position between ordered levels | how much, for ranking | yes |

A **Choice** always picks something: its probabilities sum to one. When
"none of these" is a real outcome, it needs an explicit option, or the model
will distribute that possibility across the options you did give.

A **Score** lands *between* levels. It is calibrated for ranking and
thresholding, never for reconstructing a real quantity by interpolation.

## What Jev is for, and what it is not

Jev-1.13 reads short text against explicit criteria, literally and well. It
**cannot count, cannot do arithmetic, cannot compare magnitudes reliably,
reads dates as text, and cannot generate text at all.**

So the line is:

- **Code** computes every number and renders every sentence.
- **Jev** decides what the sentences mean and which ones survive.

A question that requires the model to notice that 165,000 is larger than 720
is a question code should have answered before asking.

## Confidence is data

A Choice returning its pick at 0.30 confidence is not noise — it is the
model reporting that the options were not distinguishable *for this input*.
That is worth acting on. In this skill, a keyword whose intent came back
indistinguishable is held out of the analysis rather than forced into a
cell, and the share held out is reported, because it is itself a finding:
most of a market's volume sits in short terms that reveal nothing.

**Confidence falls as options are added.** A fixed floor means something
different for a 3-option question than an 8-option one, so this skill tests
whether the winner beat its nearest rival — `judge.decisive()` — rather than
comparing confidence to a constant.

**A Noul has no confidence field.** Its probability is absolute, not
relative: it can legitimately be low for everything you ask.

## One question, one dimension

A rubric that bundles three dimensions comes back with confidence near
zero. That is the correct answer to a badly formed question.

```python
# no — three questions wearing one coat
jev.Score(instructions={"claim": text},
          criteria=["vague", "specific but obvious",
                    "specific, surprising and actionable"])

# yes — ask separately, compose in code
jev.Noul(...)   # is this a fair reading of the measurements?
jev.Noul(...)   # could it be guessed from the market's name?
jev.Score(...)  # what does it do for the reader?
```

## Ask about meaning, not about grammar

The version of the hard-to-vary test that asked *"if the opposite were true,
would this be false?"* passed 100% of claims with a median of 0.95. It was
asking about the relationship between a sentence and its own negation, which
is a fact about English.

The version that works offers **two rival accounts of the world** and asks
which the measurements support. That is a question about data, and it
rejects claims whose opposite fits better.

## Test the claim, not its evidence

A claim carrying its numbers passes every test for specificity on the
strength of the digits. No number is guessable from a market's name; no
number is true of an unrelated market. Both tests passed everything until
each claim was split into `text` (with the measurements, for the reader) and
`assertion` (the same reading, digits removed, for the tests).

## Batch everything

Questions sent together are answered in as few requests as the context
budget allows, and those requests run concurrently. Batching is ~12x cheaper
and ~10x faster than one call per question, for identical answers. Pricing
is **input tokens only — output is free**, so the cost of a stage is the
size of what you send.

Keep state small. Accuracy falls as irrelevant context grows, so this skill
keeps the shared state to a three-line header and puts each question's
evidence in its own `instructions`.

## Adding a stage

1. Write down what code must compute first, so the question needs no
   arithmetic.
2. Choose the primitive by the shape of the answer — yes/no, which one, how
   much — not by what is convenient to parse.
3. Write criteria for a literal reader. Say what the *searcher wants*, not
   how the phrase is worded; wording is the thing that does not generalise
   across markets.
4. Batch it into the existing `ask`.
5. Run `evals/run_evals.py` before and after, and write both numbers in
   `evals/LEDGER.md`.

## When an answer looks wrong

Fix the sentence, not the number.

`hvac work order app` once scored 0.49 on a buying-intent question whose
criteria said "comparing tools, checking pricing, ready to buy" — and that
query is none of those. The fix was to widen the instruction to what the
searcher actually wants. The threshold never moved.

Moving a threshold to get the answer you expected is how a method becomes
unfalsifiable. It is also the first thing `evals/LEDGER.md` will catch.
