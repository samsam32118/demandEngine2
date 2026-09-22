# Email pattern priors

The pattern inference engine in `email_guesser.py` ranks 11 common work-email
templates. When no evidence is harvested at a domain, guesses fall back to
these global priors. When evidence is harvested, the prior is used as the
Laplace-smoothing target so a single direct-source hit doesn't flip the
ranking on flimsy data.

Priors are rough industry averages — they are not precisely measurable because
different sample frames (SaaS vs. Fortune 500 vs. open-source committers) give
very different distributions. Treat them as a starting point, not a truth.

| Template           | Example (Jane Doe @acme.com)  | Prior |
|--------------------|-------------------------------|-------|
| `{first}.{last}`   | `jane.doe@acme.com`           | 0.35  |
| `{first}`          | `jane@acme.com`               | 0.15  |
| `{f}{last}`        | `jdoe@acme.com`               | 0.12  |
| `{first}{last}`    | `janedoe@acme.com`            | 0.08  |
| `{f}.{last}`       | `j.doe@acme.com`              | 0.06  |
| `{first}_{last}`   | `jane_doe@acme.com`           | 0.05  |
| `{first}-{last}`   | `jane-doe@acme.com`           | 0.04  |
| `{last}`           | `doe@acme.com`                | 0.04  |
| `{last}.{first}`   | `doe.jane@acme.com`           | 0.04  |
| `{first}{l}`       | `janed@acme.com`              | 0.04  |
| `{last}{f}`        | `doej@acme.com`               | 0.03  |

Priors do not sum to 1.0 — the remainder is the long tail (employee-number
schemes, aliases, nicknames, initials-only like `jd@`, regional variants).

## Confidence labels

| Label | Trigger |
|---|---|
| `high` | aggregator (RocketReach) hit with share-% ≥ 60, OR ≥3 pattern matches with raw weighted share ≥ 0.6 |
| `medium` | ≥1 pattern match |
| `low — no evidence` | no emails harvested; fallback to priors |

Direct-source hits (the company's own `/contact`, `/about`, `/team`, `/press`
pages) are weighted 2× SERP hits when scoring. This mirrors the primary-source
rule in `CLAUDE.md` for dossier research.

## Role-account filter

The following local-parts are classified as role accounts and excluded from
pattern scoring. They are still surfaced in `discovered_emails` as they're
useful for general outreach:

```
info, contact, hello, sales, press, support, help, hi, team,
admin, administrator, administrators, careers, jobs, pr, media,
ir, investors, legal, marketing, billing, noreply, no-reply,
office, hr, recruiting, feedback, enquiries, inquiries,
dpo, privacy, compliance, security, disclosure, abuse, dmca,
webmaster, postmaster, board, ops, operations,
privacyofficer, compliance-officer
```

Detection is **split-aware**: the filter splits the local-part on `.`, `-`,
and `_` and disqualifies the address if any component is a role word. So
`board-administrator@`, `regulator-inquiries@` (via "inquiries"), and
`privacy.officer@` are all correctly classified as roles.

## Structural inference (pattern fallback)

When the snippet window for a harvested email doesn't contain a proper-noun
pair near the address (a common case — SERP snippets are short and messy),
the scorer falls back to **structural inference**: it asks which templates
are *mechanically compatible* with the local-part's delimiter structure.

| Local-part           | Primary delimiter    | Compatible templates                  | Credit |
|----------------------|----------------------|---------------------------------------|--------|
| `carl.bass`          | `.`                  | `{first}.{last}`, `{last}.{first}`    | 0.5 each |
| `j.doe`              | `.` (left=1 char)    | `{f}.{last}`                          | 1.0   |
| `simon.mays-smith`   | `.` (primary over `-`) | `{first}.{last}`, `{last}.{first}`  | 0.5 each |
| `jane_doe`           | `_`                  | `{first}_{last}`                      | 1.0   |
| `jane-doe`           | `-` (only)           | `{first}-{last}`                      | 1.0   |
| `carl`               | none                 | — (undecidable)                       | —     |

Structural matches cap at **medium** confidence — the `high` label requires
both ≥3 hits **and** raw weighted share ≥ 0.6, which split-credit structural
signals rarely reach. A single name-pair confirmation can push a pattern to
`high` because it gets full (unsplit) weight.

Tie-breaking: `{first}.{last}` and `{last}.{first}` tie under pure structural
signal. The Laplace-smoothed score uses global priors (0.35 vs 0.04) to
break the tie in favor of `{first}.{last}`, which matches the real-world
distribution.

## Aggregator signal (RocketReach via SERP)

RocketReach publishes company-specific "email format" pages that are indexed
by Google and contain the pattern + share-% **directly in the SERP snippet
body** — no page fetch required (the page itself is bot-protected). The skill
issues one extra SERP query per run:

```
"<domain>" "email format" site:rocketreach.co
```

and parses the snippet with two regexes: one for the bracketed pattern
(`[first].[last]` → `{first}.{last}`), one for the percentage nearby. Only
results whose title or body contain the literal `@<domain>` are kept — this
filter drops tangential mentions where another company's page happens to
name-drop the target domain in the body.

Weighting: each aggregator hit contributes `pct/10` to the weighted evidence
for that template (so a 91.8% hit is worth ~9 direct matches). A single
aggregator hit with `pct ≥ 60` is sufficient to promote the pattern to
`high` confidence on its own — RocketReach has seen thousands of samples
we haven't, and that share-% encodes real distribution data.

Caveat: SERP result composition is variable. Sometimes RocketReach surfaces
the primary-company page, sometimes only a subsidiary or unrelated page.
When nothing useful comes back, the skill falls back silently to the
name-pair + structural signals.

## Ceiling

Even with the correct format, pattern-only guessing tops out around 62-66%
accuracy (DiscoverOrg 2018 study, 2,700 verified emails). Sources of the
gap: nicknames (`Jonathan` → `Jon`, `Jennifer` → `Jen`), legacy formats
coexisting with current ones, subdomain variants, and brand-routed aliases.
A `high` label means "very likely the right format for this domain", not
"confirmed deliverable address". Actual deliverability requires an SMTP
handshake, which this skill deliberately does not perform.
