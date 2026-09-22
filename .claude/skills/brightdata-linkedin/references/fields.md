# Bright Data LinkedIn datasets — field reference

> **Authoritative source:** `python scripts/describe_fields.py --kind <kind>`
> calls `GET /datasets/{dataset_id}/metadata` and returns the live field list
> for the chosen dataset. This file is a grouped convenience summary refreshed
> from the live endpoint on 2026-04-09, but it **will drift**. When in doubt,
> re-run `describe_fields.py`.

Each of the four LinkedIn datasets returns its own record shape. Every
name listed below is a real active field in the live schema as of the
refresh date — no invented or aspirational fields.

---

## People profile (`gd_l1viktl72bvl7bjuj0`)

42 active fields.

### Identity
- `id` — unique profile identifier
- `name` — full display name
- `first_name`, `last_name`
- `url` — canonical profile URL
- `linkedin_id` / `linkedin_num_id` — LinkedIn internal ids
- `avatar` / `default_avatar` — profile picture URL + default flag
- `banner_image`
- `influencer` — boolean, "influencer" badge
- `memorialized_account` — boolean

### Location
- `city`, `country_code`, `location`

### Headline & current role
- `position` — current job title on the profile
- `current_company` — full current-company object
- `current_company_name`, `current_company_company_id`
- `about` — the "About" section body
- `educations_details` — free-text education summary

### Experience & education
- `experience` — array of prior roles
- `education` — array of degrees
- `certifications`
- `courses`
- `honors_and_awards`
- `volunteer_experience`
- `organizations`
- `projects`
- `publications`
- `patents`
- `languages`

### Activity & recommendations
- `posts` — recent posts
- `activity` — recent reactions/comments
- `recommendations` — received recommendations
- `recommendations_count`

### Network
- `followers`
- `connections`
- `people_also_viewed`
- `similar_profiles`

### Links
- `bio_links` — external links in the bio

### Metadata
- `input_url` — the URL the scrape was triggered with

---

## Company page (`gd_l1vikfnt1wgvvqz95w`)

36 active fields.

### Identity
- `id`
- `name`
- `company_id`
- `url` — canonical company URL
- `logo` — profile picture URL
- `image` — banner/cover image
- `slogan`

### Description
- `about` — summary paragraph
- `unformatted_about` — raw About text as captured
- `description` — raw HTML description
- `additional_information` — open-roles summary text
- `specialties` — specialty list

### Size & classification
- `company_size` — headcount range (e.g. `"11-50"`)
- `employees_in_linkedin` — exact count as LinkedIn reports it
- `followers` — follower count
- `founded` — year
- `industries` — industry tag(s)
- `organization_type` — Public / Private / Nonprofit / etc.

### Location
- `headquarters`
- `country_code`
- `country_codes_array` — every country the company operates in
- `locations` — full locations array
- `formatted_locations` — display-ready location strings
- `get_directions_url` — directions URLs per location

### People & content
- `employees` — sample employees array
- `alumni` — alumni count
- `alumni_information` — alumni insights
- `affiliated` — affiliated companies
- `similar` — similar companies
- `updates` — recent company posts

### Financial
- `funding` — funding round object
- `investors`
- `stock_info` — for public companies
- `crunchbase_url` — linked Crunchbase profile when available

### Contact
- `website`
- `website_simplified` — root domain only

---

## Jobs (`gd_lpfll7v5hcqtkxl6l`)

27 active fields.

### Identity
- `job_posting_id` — LinkedIn job posting id
- `url` — posting URL
- `job_title`
- `title_id` — standardized LinkedIn job title id
- `job_posted_date` — parsed date
- `job_posted_time` — raw timestamp string
- `apply_link`
- `is_easy_apply` — boolean
- `application_availability` — boolean, whether the job still accepts applications

### Employer
- `company_id`
- `company_name`
- `company_url`
- `company_logo`
- `job_poster` — poster profile object

### Description & filters
- `job_description_formatted` — full HTML description
- `job_summary` — short summary
- `job_seniority_level`
- `job_employment_type` — Full-time / Part-time / Contract / Internship
- `job_function`
- `job_industries`
- `job_location`
- `country_code`

### Compensation
- `base_salary` — structured pay range object (currency + period)
- `job_base_pay_range` — raw text
- `salary_standards` — employer-provided pay notes

### Application metrics
- `job_num_applicants`

### Metadata
- `discovery_input` — original keyword/filter dict for discover-mode jobs

---

## Posts (`gd_lyy3tktm25m4avu764`)

35 active fields.

### Identity
- `id` — unique post id
- `url` — canonical post URL
- `post_type` — article / post / etc.
- `title` — article title when present
- `headline` — short summary headline
- `date_posted`

### Content
- `post_text` — main body text
- `post_text_html` — body preserving line breaks
- `original_post_text` — body as it appears on LinkedIn

### Author
- `user_id`
- `account_type` — `Person` or `Company`
- `user_title`
- `author_profile_pic`
- `use_url` — author profile URL
- `user_followers`
- `user_posts` — author total posts
- `user_articles` — author total articles
- `num_connections` — author connections

### Publishing
- `hashtags`
- `tagged_people`
- `tagged_companies`

### Engagement
- `num_likes`
- `num_comments`
- `top_visible_comments`
- `repost` — details of the reshared post when applicable

### Media
- `images`
- `videos`
- `video_duration`
- `video_thumbnail`
- `embedded_links`
- `external_link_data` — preview cards for external links
- `document_cover_image`
- `document_page_count`

### Related
- `more_articles_by_user`
- `more_relevant_posts`

---

## Why this list exists but shouldn't be trusted forever

Bright Data adds and renames fields over time. Hardcoding against this
file will eventually break. Prefer:

1. `python scripts/describe_fields.py --kind <people|company|jobs|posts>`
   for the live schema.
2. `--fields name,headline,current_company_name,experience` on the task
   scripts to return only the columns you want (reduces payload size
   only — billing is still per returned record).
