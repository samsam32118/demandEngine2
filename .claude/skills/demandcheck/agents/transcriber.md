# Transcriber — Haiku, the fallback eyes

**Read this only when `ocr_creatives.py` flagged something.** The OCR reader
handles the creatives now — locally, in seconds, for nothing — and it is the
default path (SKILL.md, Phase 2 step 3). A transcriber exists for the residue
it cannot read: copy set over photography, ornate banners, a render that
timed out, or a machine with no OCR engine installed at all.

Spawn with the Agent tool, `model: "haiku"`, one transcriber per ~25 flagged
images, all in one message. Never spawn one for creatives OCR already read
cleanly — that is paying tokens to re-read solved work.

## What to send it

`raw/ad_copy/ocr-review.json` is the work list. Each entry names the creative,
its PNG path, why OCR failed, and what it thought it saw:

```json
{"creative_id": "CR0123…", "png": "creatives/plunge.com/CR0123….png",
 "advertiser_title": "Plunge", "reason": "gibberish", "ocr_conf": 41.2,
 "text_preview": "she Sy Wea aR ee ore"}
```

`reason` is one of `no_text` (nothing legible found — often a photo-only
creative, which is a legitimate finding), `gibberish` (a confident-looking
read that is not language), `low_conf` (read, but below the confidence floor),
`timeout` or `error`. A `no_text` image with a genuinely wordless creative
should come back `ILLEGIBLE` from the transcriber too — that is the right
answer, not a failure.

## What a transcriber does

It looks at each image and writes down **exactly what the ad says**. This is
transcription, not interpretation:

- Copy text **verbatim** — spelling, casing, punctuation as rendered. The
  analyst later mines this corpus for the words sustained money uses; a
  paraphrase would poison that analysis.
- Never guess. A blurry or truncated render is recorded as `ILLEGIBLE` (whole
  field) or `...` (truncated tail). An empty/broken image file gets one row
  with headline `ILLEGIBLE` and a note.
- Ignore the `text_preview` in the review list — it is what the machine got
  wrong. Read the image.
- No judgments, no summaries, no theme labels — that's the cleaner's and
  analyst's job.

## Output — JSON, not CSV

Write **JSON**, one object per creative, to the task's output file (path given
in the task prompt; the cleaner merges these into `clean/ad_copy.csv`, and a
transcriber row wins over the OCR row for the same `creative_id`).

This is deliberate and load-bearing. Measured against 10 live Google ads, a
Haiku transcriber asked for CSV wrote unquoted commas on **5 of 10 rows** —
`Create a fresh, safe salon with our…` split at the comma and spilled the rest
of the sentence into the `cta` and `other_text` columns. The reads themselves
were good; the file was structurally wrong, which is worse than a bad read
because it looks fine until the analyst counts CTA words and finds sentence
fragments. Ad copy is full of commas. JSON escapes them for you.

```json
[{"creative_id": "CR0123…", "advertiser_title": "HubSpot",
  "headline": "Get a Free AI Visibility Score - HubSpot AEO",
  "description": "HubSpot AEO gives you an AI visibility score, and exact steps to improve it.",
  "cta": "Try it Free for 28 Days",
  "other_text": "www.hubspot.com/geo; HubSpot AEO Tool",
  "extraction": "haiku"}]
```

- `creative_id` comes from the PNG filename (`<creative_id>.png` — the
  download index maps them; the task prompt says where `index.csv` is).
- `headline` = the largest/most prominent text; `description` = the body
  line(s); `cta` = button/action text if rendered ("Shop now"); `other_text` =
  anything else legible (prices, disclaimers, display URL), `;`-joined.
- `extraction` = `haiku` on every object you write; omit `ocr_conf`. That
  column is how the analyst tells a machine read from a model read.
- Multi-frame or stacked renders: transcribe every distinct text block,
  top-to-bottom, into the same row.

## Task prompt template

```
You are an ad-copy transcriber. Read images; write down the text. Nothing else.
These creatives are the ones local OCR could not read, so read them carefully.

Images: research/demandcheck/<slug>/creatives/<dir>/  — the files listed below.
Index (creative_id → advertiser): research/demandcheck/<slug>/creatives/<dir>/index.csv

Write ONE JSON array to research/demandcheck/<slug>/raw/ad_copy/<task-id>.json —
one object per image, keys: creative_id, advertiser_title, headline,
description, cta, other_text, extraction.

Rules:
- Verbatim text only, exactly as rendered. Unreadable field → ILLEGIBLE.
  Truncated text → transcribe what's visible and end with ...
- An image with no text at all → headline ILLEGIBLE, other_text "no text in render".
- extraction is "haiku" on every object.
- JSON, not CSV: ad copy is full of commas and CSV rows come back broken.
- One object per image, even for failures. Valid JSON or the wave loses the batch.

Files: <list of PNG filenames from ocr-review.json>

Your final message: rows written, count of ILLEGIBLE fields — 2 lines.
```
