---
name: email-guesser
description: Guess a person's work email address and infer a company's email naming pattern from public sources (Bright Data SERP + direct fetch of the company's own contact/about/team pages). Paid — each SERP query is one billable BrightData call. No SMTP verification, no LinkedIn scraping. Trigger whenever the user says "guess <name>'s email", "what's <person>'s email at <company>", "find <company>'s email pattern", "what format does <domain> use for emails", "figure out how <company> structures its emails", or gives a domain and a person's name and asks for their address. Do NOT use this for sending mail — use the `email` skill (SMTP/IMAP) or `resend` skill (HTTP) for that. This skill only predicts addresses.
---

# email-guesser

Discover the email naming pattern a company uses on its domain, and from that pattern guess the most likely email address for a named person.

Evidence sources: the company's own `/contact`, `/about`, `/team`, `/press` pages (direct HTTPS, free), plus Bright Data SERP (paid, via the `brightdata-serp` skill). Each SERP query is one billable BrightData request — see `--max-queries` to cap spend. No SMTP handshake to verify deliverability. No LinkedIn scraping.

## When to use

- "Guess Jane Doe's email at stripe.com"
- "What format do emails at anthropic.com follow?"
- "Find the email pattern for `acme.com`"
- "What's the work email for `<founder>` at `<company>`?"
- Before a founder-outreach beat, when the dossier has a name but no email.

## When NOT to use

- **Sending email** — use `email` (SMTP/IMAP) or `resend` (HTTP). This skill only *predicts* addresses.
- **Verifying deliverability** — this skill deliberately does not probe mailboxes. A guessed email is a guess, not a confirmed account.
- **Personal inboxes** — this skill targets work domains. It will not help you find someone's `@gmail.com`.

## How it works

1. **Direct fetch** — GETs `/`, `/contact`, `/contact-us`, `/about`, `/about-us`, `/team`, `/leadership`, `/press` on both `https://<domain>` and `https://www.<domain>`. Extracts `mailto:` hrefs and any plain-text `...@<domain>` addresses. Direct-source hits are the **primary-source rule** from `CLAUDE.md` applied to email discovery.
2. **SERP queries** — `"@<domain>" contact`, `"@<domain>" press`, `"@<domain>" site:<domain>`, `"@<domain>" site:github.com`, `"@<domain>" site:sec.gov`. The self-restricted `site:<domain>` query surfaces per-person bio pages linked from `/team` or `/leadership` that the fixed direct-fetch path list misses (e.g. `arcadeagroup.com/ryan-beaver/`). Each query is one billable BrightData call; subprocesses into `brightdata-serp/scripts/search.py` and parses each result body for `...@<domain>` matches. When the caller supplies `--first` and `--last`, two extra name-seeded queries fire: `"<First> <Last>" "@<domain>"` and `"<First> <Last>" email "<domain>"`. Name-seeded results are NOT cached (would leak across different names on the same domain) and run on every invocation with a name.
3. **Role-account filter** — `info@`, `contact@`, `hello@`, `sales@`, `press@`, `dpo@`, `board-administrator@`, `regulator-inquiries@`, etc. are surfaced but excluded from pattern inference (they don't tell us how named employees are structured). Role detection is split-aware: any part of a delimited local-part that matches a role word disqualifies the whole address.
4. **Pattern inference (three signals)** —
   - **Name-pair probe** (primary): look in the surrounding snippet for a proper-noun pair (`[A-Z][a-z]+ [A-Z][a-z]+`) and test which of the 11 patterns reproduces the local-part with that pair. High confidence, full weight per matched pattern.
   - **Structural inference** (fallback): if no name-pair probe succeeds, infer compatible patterns from the local-part's delimiter structure alone. `carl.bass` is compatible with `{first}.{last}` and `{last}.{first}` (0.5 credit each). `j.doe` is compatible with `{f}.{last}` only. No delimiter → no structural inference.
   - **Aggregator** (RocketReach via SERP): one extra query `"<domain>" "email format" site:rocketreach.co`. RocketReach publishes the pattern + share-% in the SERP snippet body (the page itself is bot-protected — snippet is the payload). Each hit is filtered to those whose title/body contains the literal `@<domain>` so tangential mentions don't leak in. Weighted `pct/10`, and a single hit with `pct ≥ 60` is strong enough to label the pattern `high` on its own.
   - Direct-source hits weighted 2× SERP hits (primary-source rule from `CLAUDE.md`). Scores use Laplace smoothing against the global priors, so a tie between `{first}.{last}` and `{last}.{first}` under pure structural evidence is broken in favor of `{first}.{last}` by its much higher prior.
5. **Guess generation** — if a first/last name is given, render the top-ranked pattern with the canonicalized name. Fallback to global priors (`{first}.{last}`, `{f}{last}`, `{first}`) when no evidence exists, with confidence label `low — no evidence`.

## Invocation

```
python3 /home/user/rivas/.claude/skills/email-guesser/scripts/email_guesser.py \
    --domain acme.com --first Jane --last Doe --pretty
```

No venv required — the script uses only Python stdlib. It subprocesses into `brightdata-serp/scripts/search.py` for the SERP calls; that script needs `BRIGHTDATA_API_TOKEN` in the environment.

### Budget

With defaults (`--max-queries 5` plus one RocketReach aggregator query, plus two name-seeded queries when a name is supplied), a full run costs **5–8 BrightData calls**. The ~25/session soft target in `CLAUDE.md` means ~3 email-guesser runs per session is the sensible ceiling. Lower `--max-queries` when spending matters more than recall.

### Flags

| Flag | Default | Purpose |
|---|---|---|
| `--domain` (required) | — | bare domain; scheme and `www.` are stripped |
| `--first` | — | first name (required to emit `guesses`) |
| `--last`  | — | last name (required to emit `guesses`) |
| `--no-cache` | off | bypass cache read AND write |
| `--max-queries` | 5 | cap on SERP queries issued |
| `--max-results-per-query` | 10 | `--num` passed through to brightdata-serp |
| `--skip-direct-fetch` | off | skip the `/contact /about /team /press` HTTP fetch |
| `--pretty` | off | pretty-print JSON output |

### Exit codes

| Code | Meaning |
|---|---|
| 0 | success |
| 2 | bad args |
| 3 | SERP subprocess failure after retries (JSON still emitted with `error` key) |
| 4 | unexpected exception (JSON still emitted with `error` key) |

## Output schema

```json
{
  "domain": "acme.com",
  "name": {"first": "Jane", "last": "Doe"},
  "discovered_emails": [
    {"email": "press@acme.com", "role_account": true,  "source_url": "https://acme.com/press", "source_type": "direct"},
    {"email": "john.smith@acme.com", "role_account": false, "source_url": "https://...", "source_type": "serp"}
  ],
  "inferred_patterns": [
    {"pattern": "{first}.{last}", "evidence_count": 3, "confidence": "high"}
  ],
  "guesses": [
    {"email": "jane.doe@acme.com", "pattern": "{first}.{last}", "confidence": "high", "rationale": "3 direct-source matches"}
  ],
  "query_log": [],
  "cached": false,
  "cached_at": null
}
```

## Confidence labels

- `high` — a RocketReach aggregator hit with share-% ≥ 60 **OR** ≥3 pattern matches with raw score ≥ 0.6.
- `medium` — ≥1 pattern match.
- `low — no evidence` — no emails harvested; falling back to global priors.

Treat `medium` guesses as a reasonable first send; treat `low` guesses as a starting point to validate through other means (founder-page bio, conference registration list, `.edu` paper co-authorship).

Even with the correct format, pattern-only guessing tops out around 62-66% accuracy because of nicknames (`jonathan` → `jon`), legacy formats coexisting with current ones, subdomain variants, and brand-routed aliases. Treat `high` as "very likely the right format for this domain", not "confirmed deliverable address".

## Caching

Cache directory: `workspace/cache/email-guesser/<sha256(domain)>.json`. TTL 14 days. Cache key is domain-only (pattern inference does not depend on the target name). Name-seeded SERP queries are deliberately NOT cached — they run fresh every invocation when a name is given, so two people at the same domain never pollute each other's evidence. `--no-cache` skips both read and write.

Caching matters more now that every query is paid: a second run against the same domain within 14 days costs zero BrightData calls (modulo the name-seeded queries, which re-fire at 2 calls per invocation when a name is given).

## Ethics

- No SMTP verification — mailbox probing damages IP reputation and violates several ISPs' ToS.
- No people-data broker APIs (Hunter, Apollo, RocketReach, Clearbit) — not on the Rivas Will approved list.
- No LinkedIn scraping — `brightdata-linkedin` exists for that and is a separate, budgeted skill; email discovery does not justify the spend.
- All harvested emails come from pages that already make them public.

## Pattern priors

When no evidence is found at the domain, guesses fall back to the global industry priors (see `references/patterns.md` for the full table). Top five:

1. `{first}.{last}@domain` — ~35%
2. `{first}@domain` — ~15%
3. `{f}{last}@domain` — ~12%
4. `{first}{last}@domain` — ~8%
5. `{first}_{last}@domain` — ~5%
