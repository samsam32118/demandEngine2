# Run notes — keyword-insights, "garden rooms" (UK)

Task: UK garden-room builder about to spend £4k on Google Ads, wants to know
what people search and where the money goes. Budget cap: $0.40 DataForSEO.

## Commands run

All from `/home/user/demandEngine2`. Credentials came from the environment
(`DATA_FOR_SEO_LOGIN`, `DATA_FOR_SEO_PASSWORD`, `TYPESAFEAI_API_KEY` — all
already set; there is no `.env` in the repo).

**1. Dry run — cost preview, spent nothing.**

```bash
python3 .claude/skills/keyword-insights/scripts/loop.py run "garden rooms" \
  --location "United Kingdom" --language "English" \
  --for "a UK garden room building company about to spend £4,000 on Google Ads and deciding which searches to bid on" \
  --iterations 3 --max-spend 0.40 --dry-run
```

Printed: `billable_dataforseo_calls_at_most: 3`, `dataforseo_ceiling_usd: 0.27`,
`jev_estimate_usd: 0.03`. Under the $0.40 cap, so 3 iterations was the plan.
(4 iterations would have been ~$0.36 — also under cap, but SKILL.md says past
4 the extra calls buy confirmation, which is the thing the method avoids.)

**2. The real run.** Same flags minus `--dry-run`, plus `--out` into this
directory and `--json` into the scratchpad.

**3. Offline replay.** Same flags plus `--offline`, after the skill source
changed underneath me (see below). Replayed the cached probes against the
updated code — no new DataForSEO calls.

## What it actually cost

Figures below are what the tools printed, not estimates. The skill reports
the `cost` field DataForSEO returned on each response.

| | calls | printed cost |
|---|---|---|
| Run 2 (real) — DataForSEO | 3 billable, 0 cached, 3,929 rows | **$0.2700** |
| Run 2 — Jev | 37 requests (+1 cached), 422,757 input tokens | **$0.017756** |
| Run 3 (offline replay) — DataForSEO | 0 billable, 3 cached | **$0.0000** |
| Run 3 — Jev | 2 requests (+36 cached), 11,003 input tokens | **$0.000462** |
| **Total DataForSEO** | | **$0.27** (cap $0.40, $0.13 unused) |
| **Total all-in** | | **$0.288218** |

The three billable calls were: two `keywords_for_keywords` expansions
(513 rows, then 2,612 rows) and one `search_volume` price probe (804 rows),
$0.09 each. Wall time 34.0s for the real run, 1.5s for the replay.

I did not spend the remaining $0.13. One more call would have bought a
single extra probe, and a fourth iteration on its own is not how the loop is
designed to be topped up.

## Heads-up: the delivered report's cost table reads $0.0005, not $0.27

`insights-garden-rooms.md` is the **offline replay's** output, so its "What
this cost" table shows `$0.0005` — the true cost of *that* run, replaying a
warm cache. The data underneath it cost **$0.27**. The real figure is the
table above. I chose the replay's report because of the next item.

## What went wrong / was confusing

**1. The skill was being edited and committed while I was using it.**
My first real run finished at 10:12:32. Between 10:12:43 and 10:14:08 a
concurrent process modified `insights.py`, `judge.py`, `loop.py` and
`report.py`, then committed them at 10:14:28 as `1fab2a9` *"Say what the
findings actually rest on, and stop asserting a currency"*. My run was not
corrupted — every edit landed after it finished — but the report was
immediately stale against HEAD. I re-ran with `--offline`, which cost $0.00
because the cache is checked before the budget check in `seo.py`, and it took
the identical path: same 3 probes, same 4 surviving findings, same lead
finding. The only differences were the two text fixes from that commit. I
shipped the replay's version. Run 1's report is kept at
`<scratchpad>/report-run1-backup.md`.

The two fixes both mattered here: the old text claimed the findings covered
"100% of that searching" when the intent-resolved subset is 94%, and the new
version adds the currency caveat below.

**2. CPCs are US dollars, against a pound budget.** DataForSEO returns click
prices as bare numbers with no currency field; the skill labels them `$` on
the documented basis that they are USD. For a £4k budget every figure in the
report needs converting before it means anything. HEAD now says this in the
report; the version I first got did not.

**3. Word-order duplicates inflate the corpus.** Google's expansion endpoint
returns permutations as separate keywords with identical metrics. There are
**353 such groups** in the 1,317 keywords, double-counting **52,660
searches/mo** of the 299,200 headline figure — about 18%. The biggest is
`garden rooms` and `rooms garden`, both 40,500/mo at $3.11. Finding 3 in the
report cites both as if they were separate evidence. De-duplicated, the
corpus is 964 keywords carrying 246,540 searches/mo.

**4. A second layer of duplication that de-duping by word order misses.**
`insulated garden rooms` and `insulated garden office` are both 6,600/mo at
$4.33 with identical bid ranges; `bespoke garden rooms` and `bespoke garden
office` are both 1,000/mo at $6.67. Google is reporting one aggregate against
several close variants. Treat matching rows as one term, not two.

**5. The "this market is shrinking" finding is probably a season, not a
trend.** `kgraph.py:191-192` computes direction as `sum(trend[-3:]) /
sum(trend[:3])`. On a 12-month series that is **Jun–Aug 2026 against Sep–Nov
2025** — different calendar quarters, not the same quarter a year apart. The
docstring says "last quarter against the same quarter a year earlier", which
is not what the code does. Market totals across the 612 keywords with a full
series: Jun–Aug 26 = 833,250, Sep–Nov 25 = 952,410, ratio 0.875 — which is the
0.88 in the report. But September 2025 is the single highest month in the
whole series at 442,660, 1.44x the 307,800 mean. So the "decline" is mostly
autumn-vs-summer, and the report's own finding 2 (a September peak) is the
mechanism. The data does not show a shrinking market; it shows a seasonal one.

**6. The expansion pulled in adjacent markets.** Sheds, conservatories and
garden studios came back alongside garden rooms, and `conservatory jobs`
(4,400/mo, classified `career`) is someone looking for employment. They are
inside the medians and the shape-of-market table. Reasonable as market
context, but the "conservatory" and "sheds" rows are not this advertiser's
market.

**7. `median click` reads $0.00 for "garden studios" in the table.** 769 of
1,317 keywords (58%) have no CPC, though they carry only 1,020 searches/mo
between them, so they are almost all long tail. For `garden studios`, 62 of
its 81 keywords are zero-CPC, so the median lands on a zero — while its head
term is 14,800/mo at $3.80. Read that column with care on topics with a long
zero-priced tail.

**8. Only 4 of 13 candidate claims survived**, and one of the four is graded
by the skill itself as "Colour — it fills in background they already
assumed". So the report carries roughly three loadbearing findings. That is
the method working as designed (it publishes its rejections), but it is a
thinner result than the seed's 1,317 keywords suggest.

## Housekeeping

- Nothing in `.claude/skills/keyword-insights/` was modified by me. The run
  writes response caches to `.cache/dataforseo` and `.cache/jev` inside the
  skill directory — that path is hardcoded at `loop.py:45-46` and cannot be
  redirected by a flag — but `.cache/` is gitignored, so the tree is clean.
- No commits, no pushes.
- Scratchpad holds `garden-rooms.json` (full graph, claims, ledger),
  `garden-rooms-run2.json`, `report-run1-backup.md` and
  `report-run2-offline.md`.
