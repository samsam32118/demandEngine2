# Crunchbase company record — field reference

> **Authoritative source:** `python scripts/describe_fields.py` calls
> `GET /datasets/gd_l1vijqt9jfj7olije/metadata` and returns the live list.
> This file is a grouped convenience summary that can drift from reality.

Bright Data's Crunchbase dataset returns ~100-124 fields per company. Here is
the short mental model grouped by what you usually want:

## Identity
- `id` — Bright Data internal id
- `name`
- `legal_name`
- `url` — Crunchbase org URL (also the input to `lookup_companies.py`)
- `cb_rank` — Crunchbase ranking
- `image` / `images`

## Description & classification
- `about` / short description
- `full_description`
- `industries` — list of industry tags
- `company_type` — for_profit / non_profit / etc.
- `operating_status` — active / closed / etc.
- `ipo_status` — private / public / delisted

## Location
- `region`
- `country_code` / `country`
- `city`
- `address` — HQ street address
- `headquarters_regions`

## Dates & size
- `founded_date`
- `num_employees` — string range (e.g. `"51-100"`)
- `founders` — list of founder names/ids
- `employee_count` — exact number where known

## Contact & social
- `contact_email`
- `phone_number`
- `social_media_links` — structured list
- `website`

## Traffic & tech
- `monthly_visits`
- `web_traffic_by_semrush`
- `tech_stack` / `builtwith_tech`
- `apps`

## Investors & funding
- `num_investments` / `num_investors`
- `funds_total` — total funding raised (use this, not `total_funding_amount`)
- `funds_raised` — funding rounds raised amount
- `funding_rounds` — nested list per round (date, amount, stage, investors)
- `funding_rounds_list`
- `funds_list`
- `investors` — nested list
- `num_investments_lead`
- `investment_stage`
- `ipo_fields` / `ipo_status` / `stock_symbol`

## People
- `founders`
- `current_employees` — nested list
- `current_advisors` — nested list
- `contacts` / `num_contacts` / `num_contacts_linkedin`
- `people_highlights`

## Events
- `acquisitions` / `num_acquisitions` — nested list of M&A activity
- `exits` / `num_exits`
- `milestones`
- `event_appearances` / `num_event_appearances`
- `sub_organizations` / `num_sub_organizations`
- `sub_organization_of`

## IP
- `num_patents`
- `num_trademarks`
- `patents` / `trademarks`

## Metadata
- `timestamp` — when Bright Data last scraped the record
- `source`

## Why this list exists but isn't trusted

Bright Data adds and renames fields over time. Hardcoding against this file
will eventually break. Prefer:

1. `python scripts/describe_fields.py` for the live schema.
2. `--fields name,url,founded_date,num_employees,industries` on the task
   scripts to return only the columns you want (reduces payload size).
