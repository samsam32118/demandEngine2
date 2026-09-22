# brightdata-zoominfo — field list (39 fields, 2026-04 schema)

Convenience grouping. The authoritative source is
`python scripts/describe_fields.py`. Field types come from the metadata
endpoint.

## Identity & primary URLs

| Field | Type | Notes |
|---|---|---|
| `id` | text | Unique 9-digit numeric ZoomInfo id (e.g. `155353090`) |
| `url` | url | The company's ZoomInfo profile URL (required input + echoed back) |
| `name` | text | Official company name (e.g. `Walmart`) |
| `description` | text | Multi-sentence company overview |
| `website` | url | Company website (not the ZoomInfo URL) |

## Firmographics

| Field | Type | Notes |
|---|---|---|
| `headquarters` | — | City + country / region |
| `industry` | — | Industry classification (top-level) |
| `business_classification_codes` | — | NAICS / SIC etc. |
| `employees` | — | Headcount band or detail |
| `employees_text` | text | Free-text headcount string when present |
| `total_employees` | — | Total employee count |
| `phone_number` | text | Main switchboard |
| `email_formats` | — | Inferred email naming conventions |
| `social_media` | — | Linked social handles |
| `enps score` | — | Employee NPS score (note: field name has a literal space) |
| `ceo_rating` | — | CEO rating score |

## Financial

| Field | Type | Notes |
|---|---|---|
| `revenue` | number | Numeric revenue value |
| `revenue_currency` | text | ISO currency code (draft field, mostly USD) |
| `revenue_text` | text | Free-text revenue string (draft field) |
| `stock_symbol` | text | Public ticker (often null for private companies) |
| `total_funding_amount` | — | Aggregate disclosed funding |
| `most_recent_funding_amount` | — | Last round size |
| `funding_currency` | — | Currency of disclosed funding |
| `funding_rounds` | — | Array of disclosed rounds (date, type, amount, investors) |

## People — read carefully, the field names are misleading

Verified live against Walmart's profile (2026-04-30). Most "people"
fields are integer counts, not contact lists.

| Field | What it actually returns |
|---|---|
| `leadership` | Array of ~3 person objects (name, title, avatar, ZoomInfo /p/ URL). **Members rotate between calls to the same /c/ URL** — verified on Actionstep 2026-04-30 (two lookups 10 min apart returned disjoint trios). |
| `ceo` | Structured `{name, title, score, url}` — frequently all-null even when the actual CEO appears in `leadership` and `org_chart` on the same row |
| `top_contacts` | **Integer count** of decision-makers (Walmart: 148 135; Actionstep: 198). Not a list. |
| `c_level_employees` | **Integer count** (Walmart: 145; Actionstep: 9) |
| `vp_level_employees` | **Integer count** (Walmart: 1078; Actionstep: 12) |
| `director_level_employees` | **Integer count** (Walmart: 7362; Actionstep: 21) |
| `manager_level_employees` | **Integer count** (Actionstep: 59) |
| `non_manager_employees` | **Integer count** (Actionstep: 106) |
| `org_chart` | Varies. Actionstep returned 5 C-suite entries (CEO/CFO/CTO/President/Controller) with /p/ URLs; Walmart returned null. The `avatar` URLs in this field are placeholder `/undefined`. |
| `email_formats` | Frequently `null` even on Fortune-50 and 51–200 companies; use `email-guesser` for pattern inference |

**No individual email addresses are returned by this dataset, ever.**
The `email_formats` field is a best-effort inference of the company's
email naming pattern when populated; for individual contact email
lookup use the `email-guesser` skill.

## Tech, products, news

| Field | Type | Notes |
|---|---|---|
| `tech_stack` | — | Detected technology vendors / products |
| `products_owned` | — | Company's own product portfolio |
| `news_and_media` | — | Recent news and media mentions |
| `recent_scoops` | — | ZoomInfo "scoops" feed entries |
| `popular_searches` | — | Common queries leading to this profile |

## Related companies

| Field | Type | Notes |
|---|---|---|
| `similar_companies` | — | ZoomInfo's similar-company recommendations |

## When to use `--fields`

The default behavior of `lookup_company.py` is to return all 39 fields.
Leave it alone — billing is per-record, not per-field, so trimming
saves no money and routinely strips out signals the caller didn't
think to ask for (`recent_scoops`, `news_and_media`, `org_chart`,
`tech_stack`).

Pass `--fields` only when context-window pressure forces it (e.g. when
batching 20+ companies into a single context). Some recipes if you
must:

- Compact firmographic snapshot:
  `name,url,headquarters,industry,total_employees,revenue,website`
- Decision-maker focus (only `leadership` and `org_chart` return actual
  people; the others are integer counts kept as size signals):
  `name,url,ceo,leadership,org_chart,top_contacts,c_level_employees,vp_level_employees,email_formats,phone_number`
- Tech-stack lookup:
  `name,url,tech_stack,products_owned,industry,total_employees`
- Funding focus:
  `name,url,total_funding_amount,most_recent_funding_amount,funding_rounds,funding_currency,revenue,revenue_currency`
