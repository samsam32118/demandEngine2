---
name: apple-ads
description: Query and analyze Apple Ad Repository API data for App Store advertising in EU countries. Use this skill whenever users ask about Apple Search Ads, App Store ads, Apple advertising data, EU ad transparency, finding app advertisements, looking up advertiser info, or querying the Apple Ad Repository API. Also trigger when users want to search for what ads an app or developer is running, check advertising restrictions, inspect ad creatives and variations, or explore Apple-delivered advertising compliance data. Trigger even if the user doesn't say "Apple Ad Repository" explicitly — any question about finding/browsing App Store ads, EU advertising rules, or ad restriction history should use this skill.
---

# Apple Ad Repository Skill

Use the Apple Ad Repository API to look up Apple-delivered advertising on the App Store in select European Union countries, retrieve ad creatives and variations, and fetch advertising restriction history.

The API base URL is `https://adrepository.apple.com/api/v1`. All communication must use HTTPS. Responses are always `Content-Type: application/json`. Do not send `Accept: */*` — omit the Accept header or set it explicitly to `application/json`.

Data is delayed by 7 days. For example, `LAST_90_DAYS` means the 90 days ending 7 days ago (not today).

---

## Typical workflow

A full research session usually follows this order:

1. **Find entity IDs** — search by app/developer name to get `appId` or `developerId`
2. **Get country codes** — retrieve the list of supported EU country codes
3. **List ads** — query with RSQL to get ad metadata and `adId` values
4. **Get ad variations** — fetch full creative details (assets, locale variants) for a specific ad
5. **Check restrictions** — look up any suspension or removal actions taken

You don't always need all five steps. Jump in at whatever step makes sense for the user's goal.

---

## Step 1 — Find app and developer IDs

```
GET https://adrepository.apple.com/api/v1/ad-repository-entities
  ?name={URL-encoded search text}
  &types=APP          # APP | DEVELOPER | APP,DEVELOPER (default: both)
  &offset=0
  &limit=10
```

- `name` is required; minimum 2 characters.
- Returns an `AdRepositoryEntity` list with `id`, `name`, and `type`.
- If `type` is `APP`, the `id` is an `appId`. If `type` is `DEVELOPER`, the `id` is a `developerId`.

**Example curl:**
```bash
curl -H "Accept: application/json" \
  "https://adrepository.apple.com/api/v1/ad-repository-entities?name=TripTrek&types=APP&limit=10"
```

**Example response:**
```json
{
  "data": [
    { "id": 324684580, "name": "Spotify: Music and Podcasts", "type": "APP" }
  ],
  "pagination": { "totalResults": 1, "startIndex": 0, "itemsPerPage": 5 }
}
```

---

## Step 2 — Get supported EU country codes

```
GET https://adrepository.apple.com/api/v1/countries-or-regions
```

No parameters. Returns all EU countries where Apple-delivered App Store advertising is available, with ISO 3166-1 alpha-2 codes (e.g., `DE`, `FR`, `ES`).

Use the `code` values in subsequent RSQL filters.

**Example curl:**
```bash
curl -H "Accept: application/json" \
  "https://adrepository.apple.com/api/v1/countries-or-regions"
```

Supported countries (as of March 2025): AT, BE, BG, HR, CY, CZ, DK, EE, FI, FR, DE, GR, HU, IE, IT, LV, LU, NL, PL, PT, RO, SK, SI, ES, SE.

---

## Step 3 — List ads

```
GET https://adrepository.apple.com/api/v1/ad-repository-ads
  ?ql={URL-encoded RSQL filter}
  &offset=0
  &limit=50
```

### RSQL filter syntax

Conditions are separated by `;` (AND). Enclose multiple values in `in=(val1,val2)`.

| Field | Required | Notes |
|---|---|---|
| `type` | yes (if `id` used) | `APP` or `DEVELOPER` |
| `id` | yes (if `type` used) | `appId` or `developerId` |
| `countryOrRegion` | yes | ISO alpha-2 code(s), e.g. `in=(FR,DE)` |
| `datePreset` | no | `LAST_90_DAYS` (default), `LAST_180_DAYS`, `LAST_YEAR` |

You can supply `countryOrRegion` alone (without `id`/`type`) or `id`+`type` alone — both are valid. URL-encode the `ql=` value to handle special characters.

**Example curl (app in France and Germany, last 90 days):**
```bash
QL="type==APP;id==1582276305;countryOrRegion=in=(FR,DE);datePreset==LAST_90_DAYS"
curl -H "Accept: application/json" \
  "https://adrepository.apple.com/api/v1/ad-repository-ads?ql=$(python3 -c "import urllib.parse,sys; print(urllib.parse.quote(sys.argv[1]))" "$QL")&offset=0&limit=50"
```

**Key response fields (`AdRepositoryAd`):**

| Field | Description |
|---|---|
| `adId` | Use this to call the ad variations endpoint |
| `appId` / `appName` | The advertised app |
| `developerId` / `developerName` / `legalName` | Advertiser identity |
| `placement` | `APPSTORE_SEARCH_RESULTS`, `APPSTORE_TODAY_TAB`, `APPSTORE_SEARCH_TAB`, `APPSTORE_PRODUCT_PAGE` (undocumented in PDF spec but returned live) |
| `format` | `Icon Ad` or `Icon + Asset Ad` |
| `subFormat` | e.g. `condensed_1`, `medium_1` — present only for newer ad formats |
| `countryOrRegion` | ISO code of the country this ad ran in |
| `audienceRefinement` | `ageTarget`, `genderTarget`, `locationTarget`, `customerTypeTarget` booleans |
| `firstImpressionDate` / `lastImpressionDate` | Datetime string `"YYYY-MM-DD HH:MM:SS.s"` or the literal `"Over 1 Year Ago"` for very old ads |
| `adBanner` | App Store metadata: `iconPictureUrl`, `subtitle`, `primaryCategory`, `joeColor` (often null in practice), `promotionalText`, `shortDescription`, `inAppPurchases`, `editorialBadge` |
| `adAssets` | Array of video/image assets with `videoUrl`, `pictureUrl`, `order`, `height`, `width`, `orientation` |
| `appIconVariations` | Alternate app icon URLs |
| `adLocaleVariations` | Locale-specific metadata — empty here, populated in the variations endpoint |
| `dataStartDate` / `dataEndDate` | Effective date range of the returned data |

---

## Step 4 — Get ad variations

Fetches full locale and creative variants for a single ad. Use the `adId` from Step 3.

```
GET https://adrepository.apple.com/api/v1/ad-repository-ads/{adId}
  ?datePreset=LAST_90_DAYS
```

**Example curl:**
```bash
curl -H "Accept: application/json" \
  "https://adrepository.apple.com/api/v1/ad-repository-ads/76324182?datePreset=LAST_90_DAYS"
```

This returns the same `AdRepositoryAd` object as Step 3, but with `adLocaleVariations` populated:

```json
"adLocaleVariations": [
  {
    "languageTag": "en-GB",
    "languageDisplayName": "English (Great Britain)",
    "appName": "TripTrek",
    "subTitle": "Plan your trips with confidence.",
    "primaryCategory": "travel",
    "promotionalText": "App description shown on the App Store.",
    "deviceAssets": [
      {
        "previewDevice": "iphone_6_5",
        "adAssets": [
          {
            "videoUrl": "https://...",
            "pictureUrl": null,
            "order": 1,
            "height": 1920,
            "width": 1080,
            "orientation": "PORTRAIT"
          }
        ]
      }
    ]
  }
]
```

---

## Step 5 — Get advertising restrictions

Returns suspension or removal actions applied to ads. Only ads that had at least one impression appear here.

```
GET https://adrepository.apple.com/api/v1/restrictions
  ?ql={URL-encoded RSQL filter}
  &offset=0
  &limit=50
```

### RSQL filter

| Field | Required | Values |
|---|---|---|
| `actionTaken` | yes | `ACTION_ACCOUNT_SUSPENDED`, `ACTION_ADVERTISING_REMOVED` |
| `datePreset` | no | `LAST_90_DAYS` (default), `LAST_180_DAYS`, `LAST_YEAR` |

**Example curl:**
```bash
QL="actionTaken==ACTION_ADVERTISING_REMOVED;datePreset==LAST_90_DAYS"
curl -H "Accept: application/json" \
  "https://adrepository.apple.com/api/v1/restrictions?ql=$(python3 -c "import urllib.parse,sys; print(urllib.parse.quote(sys.argv[1]))" "$QL")&offset=0&limit=50"
```

**Key response fields:**

| Field | Description |
|---|---|
| `actionDate` | Date the restriction was enforced |
| `actionTaken` | `ACTION_ACCOUNT_SUSPENDED` or `ACTION_ADVERTISING_REMOVED` |
| `reason` | `REASON_GOVERNMENT_ORDER`, `REASON_THIRD_PARTY_REPORT`, `REASON_POLICY_RESTRICTION_AGE`, `REASON_POLICY_RESTRICTION`, `REASON_TOS_INCOMPATABILITY` |
| `basis` | Human-readable basis for the restriction |
| `details` | Additional details |
| `firstImpressionDate` | First impression date for the affected advertising |
| `affectedPlacements` | Array of `{ placement, countriesOrRegions[] }` objects |
| `audienceRefinement` | Same structure as in the ads endpoints |

---

## Pagination

All list endpoints use the same pagination structure:

- **Request**: `offset` (default 0) and `limit` (default 50, max varies)
- **Response**:
  ```json
  "pagination": {
    "totalResults": 330,
    "startIndex": 0,
    "itemsPerPage": 50
  }
  ```

To page through results: increment `offset` by `itemsPerPage` until `startIndex + itemsPerPage >= totalResults`.

---

## Common patterns

### Find all ads for a known app across all EU countries

```bash
# 1. Get entity ID
curl "https://adrepository.apple.com/api/v1/ad-repository-entities?name=Spotify&types=APP"
# → appId e.g. 324684580

# 2. Query ads (no countryOrRegion filter → all countries)
QL="type==APP;id==324684580;datePreset==LAST_YEAR"
curl "https://adrepository.apple.com/api/v1/ad-repository-ads?ql=$(python3 -c "import urllib.parse,sys; print(urllib.parse.quote(sys.argv[1]))" "$QL")"
```

### Find all suspended accounts in the last 6 months

```bash
QL="actionTaken==ACTION_ACCOUNT_SUSPENDED;datePreset==LAST_180_DAYS"
curl "https://adrepository.apple.com/api/v1/restrictions?ql=$(python3 -c "import urllib.parse,sys; print(urllib.parse.quote(sys.argv[1]))" "$QL")"
```

### Download all ad assets for a specific ad

After getting `adId` from the list endpoint, call the variations endpoint and extract all `videoUrl` and `pictureUrl` fields from both `adAssets` and `adLocaleVariations[*].deviceAssets[*].adAssets`.

---

## Python helper

For scripted access, here's a minimal helper that handles RSQL encoding and pagination:

```python
import httpx
from urllib.parse import quote

BASE = "https://adrepository.apple.com/api/v1"
HEADERS = {"Accept": "application/json"}

def get_entities(name: str, types: str = "APP,DEVELOPER", limit: int = 50):
    r = httpx.get(f"{BASE}/ad-repository-entities",
                  params={"name": name, "types": types, "limit": limit},
                  headers=HEADERS)
    r.raise_for_status()
    return r.json()["data"]

def get_countries():
    r = httpx.get(f"{BASE}/countries-or-regions", headers=HEADERS)
    r.raise_for_status()
    return r.json()["data"]

def get_ads(rsql: str, offset: int = 0, limit: int = 50):
    r = httpx.get(f"{BASE}/ad-repository-ads",
                  params={"ql": rsql, "offset": offset, "limit": limit},
                  headers=HEADERS)
    r.raise_for_status()
    return r.json()

def get_ad_variations(ad_id: str, date_preset: str = "LAST_90_DAYS"):
    r = httpx.get(f"{BASE}/ad-repository-ads/{ad_id}",
                  params={"datePreset": date_preset},
                  headers=HEADERS)
    r.raise_for_status()
    return r.json()["data"]

def get_restrictions(rsql: str, offset: int = 0, limit: int = 50):
    r = httpx.get(f"{BASE}/restrictions",
                  params={"ql": rsql, "offset": offset, "limit": limit},
                  headers=HEADERS)
    r.raise_for_status()
    return r.json()

# Usage example
entities = get_entities("TripTrek")
app_id = next(e["id"] for e in entities if e["type"] == "APP")
ads = get_ads(f"type==APP;id=={app_id};countryOrRegion=in=(DE,FR);datePreset==LAST_90_DAYS")
```

---

## Reference

See `references/api-reference.md` for complete field-level documentation of every response object.
