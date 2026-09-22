# Run notes — meal-planning-market (with_skill)

Skill: `/home/user/demandEngine2/.claude/skills/keyword-insights` (SKILL.md read first; followed as written).
Working dir for all commands: `/home/user/demandEngine2`.
Date: 2026-09-22.

## Commands run

1. **Dry run** — cost preview only, spends nothing.

```bash
python3 .claude/skills/keyword-insights/scripts/loop.py run "meal planning" \
  --for "a founder and her cofounder deciding whether to build a product in this space, who want numbers not vibes" \
  --iterations 3 --dry-run
```

Printed: `billable_dataforseo_calls_at_most: 3`, `dataforseo_ceiling_usd: 0.27`,
`jev_estimate_usd: 0.03`. Nothing billed.

2. **The real run** — the only billable command.

```bash
python3 .claude/skills/keyword-insights/scripts/loop.py run "meal planning" \
  --for "a founder and her cofounder deciding whether to build a product in this space; they want hard numbers on whether real demand exists or whether it is a graveyard" \
  --iterations 3 \
  --location "United States" \
  --max-spend 0.40 \
  --out ".../with_skill/outputs/meal-planning-insights.md" \
  --json "<scratchpad>/meal-planning-run.json"
```

No other billable calls were made. No second seed was run (see "Judgement calls").

## What it actually cost

Figures below are the `cost` field DataForSEO returned per response and the
Jev usage the run reported — not estimates. Taken from the run's own manifest
(`--json` dump) and the closing line of stdout.

| | calls | rows | actual |
|---|---:|---:|---:|
| DataForSEO | 3 billable (+0 cached) | 4,380 | **$0.2700** |
| Jev | 41 requests, 506,941 input / 134,766 output tokens | — | **$0.0213** |
| **Total** | | | **$0.2913** |

DataForSEO call breakdown (each billed a flat $0.09 regardless of payload):

| # | action | endpoint | inputs | rows | cost | secs |
|---|---|---|---:|---:|---:|---:|
| 1 | expand | `keywords_for_keywords/live` | 1 | 2,237 | $0.09 | 9.71 |
| 2 | price | `search_volume/live` | 900 | 900 | $0.09 | 4.48 |
| 3 | expand | `keywords_for_keywords/live` | 1 | 1,243 | $0.09 | 7.32 |

Budget was $0.40 DataForSEO. Spent $0.27, i.e. $0.13 under — which is one
billable call short of anything useful, so it was left unspent.

Wall clock: 32.98s total (`time`), of which the run reported 32.6s internal
and 10.81s in Jev.

## What the run produced

- 4,271 keywords measured, 5,285,880 searches/mo.
- 750 keywords placed on both axes, covering 90% of measured searching.
- 13 candidate claims generated, **7 survived** testing; 5 were rejected as
  "misread", 1 as "changes nothing". Rejections are in the report.
- 2 follow-up threads chased, both answered (no dead end this run — the
  backtrack path in the loop was not exercised).

## Judgement calls

- **Seed = "meal planning"** (not "meal planning app" or "meal prep"). SKILL.md
  warns that long-tail seeds sometimes return only themselves. The head term
  expanded to 4,271 keywords and pulled in the adjacent diet-plan and
  prepared-meal territory, which is what the "is it a graveyard?" question
  actually needs.
- **`--iterations 3`** — the documented default. 4 would have cost ~$0.36 and
  still fit the budget, but SKILL.md states past four the expansions return
  the same keywords and the extra call buys confirmation.
- **No second seed.** A second run needs 3 fresh billable calls (~$0.27);
  only $0.13 remained. A 1-iteration run would have fit but SKILL.md is
  explicit that fewer than 3 degenerates the method, so it was not worth a
  weaker second report.
- **The report file was left exactly as the skill wrote it.** The skill's
  guarantee is that no language model writes any of it, so no prose was added
  to or edited into it. Framing and the verdict went into the reply instead.

## Went wrong / was confusing

- **Nothing failed.** The run completed first try; no retries, no errors, no
  budget guard trips.
- **Dry-run output looks almost identical to `eval_metadata.json`.** Both are
  small JSON blobs with `seed` / `location` / cost ceiling fields. With both on
  screen at once it took a second look to tell which was which. Not a bug,
  just a readability trap.
- **Two different coverage percentages, both correct.** stdout's last iteration
  says "587 of 750 searches revealed what the person wanted, covering 67% of
  measured searching"; the report header says the 750 placed keywords cover
  "90% of that searching". The 90% is coverage by the placed keywords; the 67%
  is the sub-slice whose intent was unambiguous. Easy to misread as a
  contradiction. Worth knowing that ~33% of the market's volume sits in short
  head terms whose intent the words alone do not resolve — the report says so,
  but only in the rejected-claims section.
- **A lot of keywords go unplaced.** Per-iteration the log reports 32 / 46 /
  101 "left unplaced (options not distinguishable)". This is the skill working
  as designed (it declines rather than guesses), but it means the topic table
  is built on a deliberately conservative subset.
- **Skill directory: not modified by me.** `git status` shows
  `scripts/judge.py` and `scripts/loop.py` as modified, but both have mtimes
  (10:01, 09:56) predating this session's first command (~10:11) — they were
  already dirty in the working tree. The run does write to
  `.claude/skills/keyword-insights/.cache/` (its own DataForSEO and Jev cache),
  which is unavoidable and is gitignored.
- Nothing was committed or pushed.
