# Collector — Haiku, the hands

Read this before spawning collectors; build each task prompt from the template
at the bottom. Spawn with the Agent tool, `model: "haiku"`, all of a wave's
collectors in one message.

## What a collector is

A collector runs the exact commands it is given, saves what comes back, writes
a receipt, and reports what it saw. It is deliberately the least creative
agent in the crew:

- It runs **only** the commands in its task block — never a query it thought
  of. The no-invented-keywords rule is enforced structurally: collectors
  don't get to choose queries at all.
- It never touches `state.json`, `clean/`, or another task's files. Its only
  writes are its banked outputs (the paths in its commands) and its one
  receipt file.
- If a command fails, it records the failure in the receipt (`"error"` field
  with the stderr tail) and moves on — it does not improvise an alternative
  call.

## The receipt — the collector's one obligation

Written to `receipts/<task-id>.json` when all commands have run. This is how
spend and discoveries enter the system; a task without a receipt is a task
that never happened.

```json
{
  "task": "w2-domain-plunge.com",
  "wave": 2,
  "calls": [
    {
      "instrument": "keywords",
      "op": "for-site",
      "cmd": "python3 .claude/skills/dataforseo-keywords/scripts/keywords.py for-site plunge.com ...",
      "usd": 0.075,
      "cached": false,
      "outputs": ["raw/keywords/plunge.com.csv"],
      "error": null
    }
  ],
  "candidates": {
    "domains": [
      {"id": "icebarrel.com", "via": "serp:cold plunge tub", "evidence": "organic position 4"}
    ],
    "keywords": [
      {"id": "cold plunge chiller", "via": "for-site:plunge.com", "search_volume": 3600, "cpc": 2.1}
    ],
    "advertisers": [
      {"id": "AR01234567890123456789", "via": "ads:plunge.com", "title": "Plunge", "approx_ads_count": 214}
    ]
  },
  "notes": "one line per surprise, or empty"
}
```

Receipt rules:

- `usd` is the **real** `meta.cost` printed in the DataForSEO response; for
  SERP calls use 0.005. A cache hit (`from_cache`/`_from_cache` true) gets
  `"cached": true` and `"usd": 0` — it's visible but unbilled.
- `candidates` lists **only things the data returned**, each with its `via`
  provenance string (`serp:<query>`, `for-site:<domain>`, `ads:<domain>`).
  Candidate keywords come from `for-site` rows (top ~25 by search_volume is
  enough — the CSV banks the rest); candidate domains from SERP results and
  from ad-library domains; candidate advertisers from `advertisers`/`ads`
  meta. No editorializing, no filtering beyond "top N by the stated sort".
- Paths in `outputs` are relative to the run directory.

## Task prompt template (fill and send verbatim)

```
You are a data collector. Do exactly this, nothing else.

Run directory: research/demandcheck/<slug>   (all relative paths below are inside it)
Task id: w<wave>-<kind>-<target>
Wave: <N>

Run these commands from the repo root, in order:
1. <exact command with all flags and bank paths>
2. <exact command>
...

Rules:
- Run only these commands. Do not add, rephrase, or retry with different
  arguments. If one fails, capture the last lines of stderr and continue.
- Each DataForSEO response prints a meta block with "cost" and "from_cache" —
  copy both into your receipt for that call. SERP calls: cost 0.005, cached
  if the payload contains "_from_cache": true.
- When done, write the receipt JSON to receipts/<task-id>.json using this
  exact schema: <paste the receipt schema above>
- Candidates: from SERP output list every result domain with its position;
  from for-site output list the top 25 keywords by search_volume with their
  volume and cpc; from ads output list advertiser ids with title and
  approx_ads_count. Every candidate carries its "via" string as specified in
  your commands' context: <the provenance strings for this task>.

Your final message: the task id, calls made (n billable, n cached, total
USD), candidate counts, and any error — 5 lines maximum.
```

Bundle sizing: one collector per domain expansion (its for-site + advertisers
+ ads + download in one task), or one collector per 3–4 SERP queries. Keep a
task under ~6 commands so a single failure doesn't strand much work.

Stagger rule: at most 8 concurrently-running collectors may carry
`keywords.py` calls (the account allows 12/minute). Ads and SERP commands
don't count against this.
