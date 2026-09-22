---
name: brightdata-web-unlocker
description: Fetch any URL — including pages that block plain requests with CAPTCHAs, bot-detection, JS challenges, geo-blocks, or paywalls — via Bright Data's Web Unlocker API, which routes the request through real browser fingerprinting and residential/mobile IPs so it comes back like a normal visitor loaded it. Automatically picks the right Bright Data zone: web_unlocker1 for most sites, web_unlocker_premium for a fixed list of ~90 high-defense domains (major retailers like target.com, walmart.com.mx, costco.com, bestbuy.com, kroger.com; marketplaces like shopee.*, lazada.*, carousell.*, temu.com; travel sites like hyatt.com, skyscanner.net, wizzair.com; people-search sites like familytreenow.com, peoplefinders.com; and more — see references/premium-domains.md for the full list). Trigger whenever the user says "fetch this page", "scrape <url>", "get past this site's bot detection", "this site is blocking my request/curl/WebFetch", "pull the HTML from <url>", "use web unlocker", "bright data unlocker", or gives a URL and wants its actual rendered content when a normal fetch would get blocked or challenged. For LinkedIn, Crunchbase, PitchBook, ZoomInfo, or TikTok profile/company data specifically, prefer the dedicated brightdata-* skill instead — it returns clean structured fields; reach for web-unlocker when there's no dedicated skill for the target site, or you need the raw rendered page itself.
---

# brightdata-web-unlocker

Thin wrapper around Bright Data's **Web Unlocker API** (pay-as-you-go). One
endpoint, `POST https://api.brightdata.com/request`, with a payload that
tells Bright Data which zone and URL to fetch. Bright Data routes the
request through its unlocker infrastructure — residential/mobile IPs, real
browser fingerprinting, JS-challenge and CAPTCHA solving — and hands back
the target page's response body as if a normal browser had loaded it. No
HTML parsing or rendering on our side; you get back exactly what the site
would have served a real visitor.

Stdlib-only Python — no `.venv` to create, no dependencies to install.
Shares the `BRIGHTDATA_API_TOKEN` with the other `brightdata-*` skills in
this repo.

## When to use this vs. the other brightdata-* skills

- **Need LinkedIn / Crunchbase / PitchBook / ZoomInfo / TikTok data?** Use
  the dedicated `brightdata-linkedin` / `brightdata-crunchbase` /
  `brightdata-pitchbook` / `brightdata-zoominfo` / `brightdata-tiktok`
  skill instead. Those hit purpose-built datasets and hand back clean,
  structured fields (name, HQ, funding rounds, etc.) instead of raw HTML
  you'd have to parse yourself.
- **Need a Google search?** Use `brightdata-serp`.
- **Need the actual page content from a specific URL** — and either there's
  no dedicated skill for that site, or you genuinely need the rendered page
  itself (raw HTML, a JSON API response, anything a dedicated skill doesn't
  cover) — that's what this skill is for.

## Prerequisites

- `BRIGHTDATA_API_TOKEN` — same token the other `brightdata-*` skills use.
  Must belong to an account with a Web Unlocker zone enabled.
- `BRIGHTDATA_UNLOCKER_ZONE` — the default zone name. Defaults to
  `web_unlocker1` (matches the operator's working example). Override via
  env var if your account uses a different name.
- `BRIGHTDATA_UNLOCKER_PREMIUM_ZONE` — the premium zone name. Defaults to
  `web_unlocker_premium`. Override the same way.

Scripts exit with a clear error if the token is missing.

## Zone auto-detection

Some domains are gated behind Bright Data's premium unlocker zone — trying
them through the standard zone gets blocked. `unlock.py` looks at the
target URL's hostname and automatically picks:

- `web_unlocker_premium` if the host (or a subdomain of it) matches one of
  the ~90 domains in `scripts/premium_domains.py` (mirrored for quick
  reading in `references/premium-domains.md`) — major retailers,
  marketplaces, travel sites, people-search sites, and similar
  high-defense targets.
- `web_unlocker1` for everything else.

Pass `--zone` to override auto-detection explicitly — e.g. if Bright Data
moves a domain into the premium tier before this list is updated, or your
account names its zones differently.

If a fetch through the standard zone comes back blocked or challenged for a
domain that isn't in the premium list, that's the signal Bright Data has
started gating it — add the domain to `PREMIUM_DOMAINS` in
`scripts/premium_domains.py` (and mirror it in
`references/premium-domains.md`) rather than routing around it per-call.

## Billing model — read this before running anything

Every successful call to `/request` is one billable Web Unlocker request on
your Bright Data plan. Pricing isn't hardcoded here — check your Bright
Data dashboard/contract for the current per-request rate; the premium zone
is typically priced higher than the standard zone.

Responses are cached at `workspace/cache/<sha256>.json` keyed on `(url,
zone, format, method, country)` — re-fetching the same URL is free. Pass
`--no-cache` only if you deliberately want a fresh paid call (e.g. the page
may have changed since the cached copy).

## Operations

Run from the repo root. Script prints one JSON object to stdout (unless
`--save` or `--stdout body` is used — see below).

### Fetch a URL

```bash
python .claude/skills/brightdata-web-unlocker/scripts/unlock.py "<url>" \
    [--zone web_unlocker1|web_unlocker_premium] [--format raw|json] \
    [--method GET] [--country us] [--save path/to/file] \
    [--stdout json|body] [--no-cache]
```

Flags:
- `--zone` — override zone auto-detection. Rarely needed; auto-detection
  handles the domains that matter (see above).
- `--format raw|json` — Bright Data's response shape. Default `raw`.
  - `raw` — the target page's body, verbatim (matches the operator's
    working curl examples). Simplest option; use this by default.
  - `json` — Bright Data wraps the response in a `{status_code, headers,
    body}` envelope. Use this when you need to check the upstream HTTP
    status programmatically (e.g. distinguish a real 200 from a
    403/challenge page) instead of just reading the body.
- `--method` — HTTP method the unlocker sends to the target. Default
  `GET`. Exposed for completeness; almost everything you'll do is a GET.
- `--country` — Bright Data proxy country hint, e.g. `us`, `de`. Optional.
- `--save PATH` — write the fetched body straight to a file instead of
  printing it, and print a short JSON summary (`path`, `bytes`,
  `status_code`, `zone`) to stdout instead. **Use this for anything that
  isn't a small page** — full HTML documents can be hundreds of KB, and
  dumping that into the conversation wastes context for no benefit. Read
  or grep the saved file for just what you need.
- `--stdout json|body` — stdout shape when not using `--save`. Default
  `json` (the full payload as JSON). `body` prints just the fetched body —
  convenient for piping into a file or another tool.
- `--no-cache` — bypass `workspace/cache/` and force a fresh billable
  call.

### Output shape

Default (`--format raw`):
```json
{
  "url": "https://geo.brdtest.com/welcome.txt?product=unlocker&method=api",
  "zone": "web_unlocker1",
  "format": "raw",
  "status_code": 200,
  "body": "...the page content, verbatim...",
  "retrieved_at": "2026-08-18T15:30:00Z"
}
```

With `--format json`:
```json
{
  "url": "https://example.com/product/123",
  "zone": "web_unlocker_premium",
  "format": "json",
  "status_code": 200,
  "headers": { "content-type": "text/html; charset=utf-8", "...": "..." },
  "body": "<html>...</html>",
  "retrieved_at": "2026-08-18T15:30:00Z"
}
```

With `--save`:
```json
{
  "path": "/abs/path/to/file.html",
  "bytes": 184320,
  "status_code": 200,
  "zone": "web_unlocker1",
  "retrieved_at": "2026-08-18T15:30:00Z"
}
```

### Smoke test

```bash
python .claude/skills/brightdata-web-unlocker/scripts/smoke_test.py
python .claude/skills/brightdata-web-unlocker/scripts/smoke_test.py --premium
```

One call — fetches Bright Data's own test page
(`geo.brdtest.com/welcome.txt?product=unlocker&method=api`, matches the
operator's working curl examples) through `web_unlocker1` by default, or
`web_unlocker_premium` with `--premium`. Asserts a non-empty body came back
and prints it so you can eyeball correctness. Run after any change to the
token or zone env vars. Costs one billable request per run.

## Guidance

- **Don't dump huge bodies into the conversation.** A raw unlocked page can
  be a full HTML document — hundreds of KB. Default to `--save` for
  anything beyond a small page or API response, then read/grep the file
  for what's actually needed.
- **Resolve the exact URL first.** This skill fetches a specific URL; it
  doesn't search. If you only have a company/product name, resolve the URL
  via `brightdata-serp` (or ask the user) before calling `unlock.py`.
- **A non-200 can still be useful data.** `client.py` raises on a failed
  request the same way every other `brightdata-*` skill does, but if you
  need to inspect the target's own status code (as opposed to a Bright
  Data-side failure), use `--format json` and read `status_code` rather
  than inferring it from the body.

## Design notes

- **Why auto-detect the zone instead of always asking.** The premium-vs-
  standard split is real infrastructure the caller shouldn't have to
  remember for ~90 specific domains. Auto-detection means
  `unlock.py https://www.target.com/...` just works; `--zone` stays
  available for the rare override.
- **Why `raw` by default.** It matches the operator's verified working
  examples exactly and is the simplest thing that could work — most
  callers just want the page. `json` is there for the less common case of
  needing the upstream status code without guessing from the body.
- **Why `--save` exists.** Unlike SERP's markdown (meant to be pasted
  straight into a prompt), a raw unlocked page is often full HTML —
  hundreds of KB that would blow out the conversation if printed. Saving
  to disk and reading/grepping selectively is the sane default for
  anything beyond a small page.
- **Why stdlib-only.** No `.venv` means no install step when this repo
  gets cloned fresh — matches every other skill here.

## Files

```
.claude/skills/brightdata-web-unlocker/
├── SKILL.md                        — this file
├── references/
│   └── premium-domains.md          — human-readable copy of the premium domain list
└── scripts/
    ├── client.py                   — POST /request helper, auth, retries
    ├── premium_domains.py          — the authoritative domain list + zone-selection logic
    ├── unlock.py                   — CLI entry point, caching, --save
    └── smoke_test.py
```
