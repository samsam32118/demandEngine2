# brightdata-tiktok — output fields per dataset

Grouped convenience list. **Not authoritative** — schemas drift. The live
source of truth is:

```bash
python scripts/describe_fields.py --kind profiles|posts|comments|shop
python scripts/describe_fields.py --kind posts --inputs   # request side
```

Field counts below were read from `/datasets/{id}/metadata` on 2026-08-04.

---

## Profiles — `gd_l1villgoiiidt09ci` (40 fields)

**Identity**
`account_id` · `id` · `nickname` · `url` · `secu_id` · `short_id` ·
`is_verified` · `is_private` · `predicted_lang` · `region`

**Bio & media**
`biography` · `bio_link` · `profile_pic_url` · `profile_pic_url_hd` ·
`create_time`

**Audience & volume**
`followers` · `following` · `likes` · `digg_count` · `like_count` ·
`videos_count`

**Engagement rates** — the reason to use this dataset rather than
reading a profile page
`awg_engagement_rate` · `comment_engagement_rate` · `like_engagement_rate`

**Settings & misc**
`ftc` · `relation` · `open_favorite` · `comment_setting` · `duet_setting`
· `stitch_setting` · `top_videos` · plus assorted flags

Verified live: `@nike` → 9,000,000 followers · 48,300,000 likes · 1,083
videos · `awg_engagement_rate` 0.00512 · `is_verified` true.

---

## Posts — `gd_lu702nij2f790tmv9h` (43 fields)

**Post identity**
`url` · `post_id` · `shortcode` · `description` · `create_time` ·
`post_type` · `offical_item` · `original_item` · `secu_id`

**Engagement — the core metrics**
`play_count` (views) · `digg_count` (likes) · `comment_count` ·
`share_count` · `collect_count` (saves)

**Content**
`hashtags` · `music` · `original_sound` · `video_duration` · `video_url`
· `preview_image` · `width` · `ratio`

**Author block** — denormalised onto every row, so a discovery doubles
as a creator sample
`profile_id` · `profile_username` · `profile_url` · `profile_avatar` ·
`profile_biography` · `profile_followers`

**Provenance**
`discovery_input` — echoes the keyword/profile/URL that surfaced this
row. Essential when you fan out across several inputs in one job.

---

## Comments — `gd_lkf2st302ap89utw5k` (16 fields)

**The comment**
`comment_id` · `comment_url` · `comment_text` · `date_created` ·
`num_likes` · `num_replies` · `url`

**The commenter**
`commenter_user_name` · `commenter_id` · `commenter_url`

**Parent post context** — every comment row carries its video, so you can
flatten a multi-video pull without re-joining
`post_url` · `post_id` · `post_date_created` · `num_of_comments`

**Replies**
`collect_replies` (echo of the input flag) · `replies` (nested thread,
populated only when `--collect-replies` was passed)

---

## Shop — `gd_m45m1u911dsa4274pi` (64 fields)

**Product**
`url` · `id` · `title` · `description` · `available` · `category` ·
`category_url` · `domain`

**Pricing** — note the band fields; TikTok Shop lists ranges for
variant-priced products
`currency` · `initial_price` · `final_price` · `discount_percent` ·
`initial_price_low` · `initial_price_high` · `final_price_low` ·
`final_price_high` · `shipping_fee`

**Variants & spec**
`colors` · `sizes` · `specifications`

**Social proof**
`sold` (units) · `reviews_count` · `reviews`

**Seller**
`seller_id` · `seller_rating` · `store_details`

**Media**
`images` · `videos`

---

## `--fields` (custom_output_fields)

Every task script takes `--fields a,b,c` to trim the returned columns.

**Leave it off by default.** Billing is per *record*, not per field, so
trimming saves nothing on the invoice and routinely strips signal the
caller didn't know they wanted (engagement rates, the `discovery_input`
provenance key, the denormalised author block). Reach for it only when
the user asks for a narrow payload or context-window pressure forces it:

```bash
python scripts/discover_posts.py --keyword "sales coach" \
    --limit-per-input 50 \
    --fields url,description,play_count,digg_count,profile_username
```
