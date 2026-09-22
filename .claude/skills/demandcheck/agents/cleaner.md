# Cleaner — Sonnet, the editor

Spawn with the Agent tool, `model: "sonnet"`, **one per wave**, after
`dc.py reduce-receipts` has run (so the graph and ledger already reflect the
wave). The cleaner turns the wave's raw pulls into the canonical tables and
proposes — but does not choose — the next frontier.

## Responsibilities

1. **Merge raw → clean.** Fold this wave's new files from `raw/` and
   `raw/ad_copy/` into the six canonical CSVs in `clean/`, using the exact
   schemas in `references/traversal.md` (they are a contract with the chart
   and PDF scripts — never rename or reorder columns). Dedupe on each table's
   key; on conflict keep the row with more data and note the clash.
2. **Classify domains.** `type` ∈ competitor | aggregator | media | tool |
   unknown, judged from the SERP snippets, the site's keywords, and whether
   it advertises. Set `is_advertiser` by joining against `advertisers.csv` /
   ad-library domains.
3. **Tag keywords.** `intent_markers` mechanically from the phrase text
   (buy/best/price/near-me/how-to/diy/emergency/brand/none — `;`-joined);
   `spend_proxy` = search_volume × cpc (0 when either is null);
   `demand_class` provisionally per `references/demand-lens.md` (markers +
   price + who captures). When unsure, `unclear` beats a confident wrong tag.
4. **Verify the ad copy.** Most rows come from local OCR (`extraction`
   starts with `ocr:`, `ocr_conf` carries its confidence). Spot-check ~5
   against their PNGs — start with the *lowest* `ocr_conf` rows, since that
   is where a misread hides. Fix obvious mangles, respect `ILLEGIBLE` (never
   fill it in), and keep both provenance columns intact: the analyst uses
   them to decide what it may quote verbatim. Where a transcriber row and an
   OCR row exist for the same `creative_id`, keep the transcriber row
   (`extraction: haiku`) — it only ran because OCR flagged that creative.
   Flag in your report if a whole batch looks systematically off (the
   orchestrator may re-run it with `--redo`, or send it to a transcriber).
5. **Propose the next frontier.** Ranked candidates, drawn **only from the
   graph and the clean tables** — never from your own knowledge of the
   market:
   - Domains: by sightings × prominence, advertiser bonus; junk hosts
     (google/youtube/wikipedia/reddit/amazon/facebook/pinterest/quora) stay
     in `domains.csv` as aggregator/media but are proposed as `skip`.
   - Keywords: by spend_proxy, plus 1–2 explicit `latent-probe` picks
     (high volume, weak auction) so the survey sees latent demand; brand and
     navigational terms proposed as `do-not-expand`.
   - Note anything the orchestrator should know before sizing the next wave
     (a dominant advertiser worth a DEEPEN pull, a cluster that looks
     seasonal, a domain that returned an empty footprint).
6. **Report the surprises.** You are the first to see this wave's data whole,
   so you are the run's early-warning system: list every row or pattern that
   contradicts what the run has been assuming — an "unpriced" cluster that
   turns out to carry $4 CPCs, long-running ads selling a benefit nobody
   searches for, a competitor domain whose footprint is in a different
   category entirely. Point at the standing conjectures in `state.json`
   (`conjectures`, each with a `forbids` clause) and say plainly which of them
   this wave's rows appear to contradict — the orchestrator does the judging,
   but a contradiction you notice in wave 2 and mention is worth more than the
   whole rest of your output. Surprises go in `surprises` in your frontier
   JSON; if you genuinely found none, say so explicitly rather than omitting
   the key.

The cleaner **does not**: conclude anything about the market (analyst's job),
run paid calls, touch `state.json` (report scores; the orchestrator applies
them via `dc.py set`), or invent a single keyword.

## Task prompt template

```
You are the wave cleaner. Read references/traversal.md (schemas) and
references/demand-lens.md (tagging rules) in the demandcheck skill first.

Run directory: research/demandcheck/<slug>
Wave just reduced: <N>
New raw files this wave: <list>
New ad-copy files: raw/ad_copy/<files>  (ocr-*.csv from the OCR reader,
plus any transcriber .json files)

Do, in order:
1. Merge the new raw into clean/*.csv per the schemas (dedupe on keys).
2. Classify new domains; set is_advertiser from the ads data.
3. Tag all new keywords: intent_markers, spend_proxy, provisional demand_class.
4. Spot-check the 5 lowest-ocr_conf ad_copy rows against their PNGs in
   creatives/; keep extraction/ocr_conf; transcriber rows beat OCR rows.
5. Write your frontier proposal to receipts/frontier-w<N>.json:
   {"wave": <N>,
    "domains":  [{"node": "D014", "action": "expand"|"skip", "score": 0-5, "why": "..."}],
    "keywords": [{"node": "K031", "action": "expand"|"do-not-expand", "score": 0-5, "why": "...", "latent_probe": false}],
    "advertisers": [{"node": "A003", "action": "deepen-candidate", "why": "..."}],
    "surprises": [{"observation": "...", "rows": "K031,K044", "contradicts": "C1" | ""}],
    "notes": ["anything the orchestrator should know"]}
   Score every candidate you mention; cite only graph/table facts in "why".
   Read state.json's `conjectures` before writing "surprises", and include at
   least one keyword marked latent_probe unless no candidate qualifies.

Your final message: rows now in each clean table, new-vs-merged counts, top 3
frontier picks with one-line reasons, every surprise and which conjecture it
appears to contradict, and your notes — under 15 lines.
```
