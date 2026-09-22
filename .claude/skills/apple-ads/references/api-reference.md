# Apple Ad Repository API — Complete Reference

Base URL: `https://adrepository.apple.com/api/v1`  
Version: v1 (March 2025)  
Auth: none required  
Data delay: 7 days

---

## Table of Contents

1. [GET /ad-repository-entities](#get-ad-repository-entities)
2. [GET /countries-or-regions](#get-countries-or-regions)
3. [GET /ad-repository-ads](#get-ad-repository-ads)
4. [GET /ad-repository-ads/{adId}](#get-ad-repository-adsadid)
5. [GET /restrictions](#get-restrictions)
6. [Shared Objects](#shared-objects)
7. [Enumerations](#enumerations)
8. [Changelog](#changelog)

---

## GET /ad-repository-entities

Search for app and developer names. Only entities that have been advertised in EU countries appear.

### Request parameters

| Parameter | Type | Required | Default | Description |
|---|---|---|---|---|
| `name` | string | yes | — | Search text, minimum 2 characters |
| `types` | string | no | `APP,DEVELOPER` | Filter by `APP`, `DEVELOPER`, or `APP,DEVELOPER` |
| `offset` | integer | no | 0 | Pagination start index |
| `limit` | integer | no | 50 | Max results per page |

### Response: AdRepositoryEntity

| Field | Type | Description |
|---|---|---|
| `id` | integer | If `type=APP`: appId. If `type=DEVELOPER`: developerId |
| `name` | string | Display name on the App Store |
| `type` | string | `APP` or `DEVELOPER` |
| `pagination` | object | See [Pagination](#pagination-object) |

---

## GET /countries-or-regions

Returns all EU countries where Apple-delivered App Store advertising is available.

### Response

| Field | Type | Description |
|---|---|---|
| `name` | string | Country name (e.g. `"Sweden"`) |
| `code` | string | ISO 3166-1 alpha-2 code (e.g. `SE`) |

### Supported countries (March 2025)

| Code | Country | Code | Country |
|---|---|---|---|
| AT | Austria | IT | Italy |
| BE | Belgium | LV | Latvia |
| BG | Bulgaria | LU | Luxembourg |
| HR | Croatia | NL | Netherlands |
| CY | Cyprus | PL | Poland |
| CZ | Czech Republic | PT | Portugal |
| DK | Denmark | RO | Romania |
| EE | Estonia | SK | Slovakia |
| FI | Finland | SI | Slovenia |
| FR | France | ES | Spain |
| DE | Germany | SE | Sweden |
| GR | Greece | IE | Ireland |
| HU | Hungary | | |

---

## GET /ad-repository-ads

Returns ad metadata for multiple ads. Use RSQL filter syntax in the `ql=` parameter.

### Request parameters

| Parameter | Type | Required | Default | Description |
|---|---|---|---|---|
| `ql` | string | yes | — | URL-encoded RSQL filter (see below) |
| `offset` | integer | no | 0 | Pagination start index |
| `limit` | integer | no | 50 | Max results per page |

### RSQL fields

| Field | Required | Values | Notes |
|---|---|---|---|
| `type` | yes (if `id` present) | `APP`, `DEVELOPER` | Must accompany `id` |
| `id` | yes (if `type` present) | integer | appId or developerId |
| `countryOrRegion` | yes | ISO alpha-2, supports `in=(X,Y)` | |
| `datePreset` | no | `LAST_90_DAYS`, `LAST_180_DAYS`, `LAST_YEAR` | Default: `LAST_90_DAYS` |

Either `id`+`type` or `countryOrRegion` (or both) must be present.

### Response: AdRepositoryAd (list)

Top-level:

| Field | Type | Description |
|---|---|---|
| `data` | array | Array of `AdRepositoryAd` objects |
| `dataStartDate` | string | Effective start of data range (YYYY-MM-DD) |
| `dataEndDate` | string | Effective end of data range (YYYY-MM-DD) |
| `pagination` | object | See [Pagination](#pagination-object) |

Each `AdRepositoryAd` object:

| Field | Type | Description |
|---|---|---|
| `adId` | string | Unique ad identifier (UUID hex string, e.g. `"c4590a2bf73d0f08a141c03cb135a0e6"`); use as path param in variations call |
| `appId` | integer | Unique app identifier |
| `appName` | string | App name on the App Store |
| `developerId` | integer | Unique developer identifier |
| `developerName` | string | Developer name on the App Store (may differ from `legalName`) |
| `legalName` | string | Legal seller name on the App Store (may differ from `developerName`) |
| `placement` | string | See [Placement values](#placement) |
| `format` | string | `Icon Ad` or `Icon + Asset Ad` |
| `subFormat` | string | e.g. `condensed_1`, `medium_1`; null for standard formats |
| `countryOrRegion` | string | ISO alpha-2 country code |
| `audienceRefinement` | object | See [AudienceRefinement](#audiencerefinement-object) |
| `firstImpressionDate` | string | Datetime string `"YYYY-MM-DD HH:MM:SS.s"` or the literal `"Over 1 Year Ago"` for ads older than 1 year |
| `lastImpressionDate` | string | Datetime string `"YYYY-MM-DD HH:MM:SS.s"` |
| `defaultLanguageTag` | string | Default locale (e.g. `es-ES`) |
| `defaultLanguageDisplayName` | string | Locale display name (e.g. `Spanish (Spain)`) |
| `defaultPreviewDevice` | string | Default preview device (e.g. `iPhone_6.5`) |
| `adBanner` | object | See [AdBanner](#adbanner-object) |
| `adAssets` | array | See [AdAsset](#adasset-object) |
| `appIconVariations` | array | URLs of alternate app icons |
| `adLocaleVariations` | array | Empty in list endpoint; populated in variations endpoint |

---

## GET /ad-repository-ads/{adId}

Returns full ad details including locale variations for a single ad.

### Path parameters

| Parameter | Type | Required | Description |
|---|---|---|---|
| `adId` | string | yes | Unique ad identifier from the list endpoint |

### Query parameters

| Parameter | Type | Required | Default | Description |
|---|---|---|---|---|
| `datePreset` | string | no | `LAST_90_DAYS` | `LAST_90_DAYS`, `LAST_180_DAYS`, `LAST_YEAR` |

### Response: AdRepositoryAd (single)

Same structure as the list endpoint with `adLocaleVariations` populated:

#### AdLocaleVariation object

| Field | Type | Description |
|---|---|---|
| `languageTag` | string | Locale code (e.g. `en-GB`) |
| `languageDisplayName` | string | Language display name (e.g. `English (Great Britain)`) |
| `appName` | string | App name in this locale |
| `subTitle` | string | App subtitle in this locale |
| `primaryCategory` | string | App category in this locale |
| `promotionalText` | string | App description in this locale |
| `deviceAssets` | array | See [DeviceAssets](#deviceassets-object) |

#### DeviceAssets object

| Field | Type | Description |
|---|---|---|
| `previewDevice` | string | Device model (e.g. `iphone_6_5`) |
| `adAssets` | array | See [AdAsset](#adasset-object) |

---

## GET /restrictions

Returns advertising restrictions (suspensions or removals). Only ads with at least one impression are included.

### Request parameters

| Parameter | Type | Required | Default | Description |
|---|---|---|---|---|
| `ql` | string | yes | — | URL-encoded RSQL filter |
| `offset` | integer | no | 0 | Pagination start index |
| `limit` | integer | no | 50 | Max results per page |

### RSQL fields

| Field | Required | Values |
|---|---|---|
| `actionTaken` | yes | `ACTION_ACCOUNT_SUSPENDED`, `ACTION_ADVERTISING_REMOVED` |
| `datePreset` | no | `LAST_90_DAYS` (default), `LAST_180_DAYS`, `LAST_YEAR` |

### Response: Restriction

| Field | Type | Description |
|---|---|---|
| `actionDate` | string | Datetime when restriction was enforced (`"YYYY-MM-DD HH:MM:SS.s"`) |
| `actionTaken` | string | `ACTION_ACCOUNT_SUSPENDED` or `ACTION_ADVERTISING_REMOVED` |
| `reason` | string | See [Restriction reasons](#restriction-reasons) |
| `basis` | string | Basis constant (e.g. `"BASIS_APPLE_DETERMINATION"`); the PDF spec implies plain text but real API returns enum-style strings |
| `details` | string | Additional restriction details |
| `firstImpressionDate` | string | First impression date for affected advertising |
| `affectedPlacements` | array | Array of `{ placement, countriesOrRegions[] }` |
| `audienceRefinement` | object | See [AudienceRefinement](#audiencerefinement-object) |
| `dataStartDate` | string | Effective data range start |
| `dataEndDate` | string | Effective data range end |
| `pagination` | object | See [Pagination](#pagination-object) |

---

## Shared Objects

### Pagination object

| Field | Type | Description |
|---|---|---|
| `totalResults` | integer | Total matching records |
| `startIndex` | integer | Index of first item in this page |
| `itemsPerPage` | integer | Number of items per page |

### AudienceRefinement object

| Field | Type | Description |
|---|---|---|
| `ageTarget` | boolean | Age parameters used in campaign |
| `genderTarget` | boolean | Gender parameters used in campaign |
| `locationTarget` | boolean | Country/region parameters used |
| `customerTypeTarget` | boolean | App downloader type targeted (see [Customer types](#customer-type-values)) |

### AdBanner object

| Field | Type | Description |
|---|---|---|
| `joeColor` | string\|null | Encoded color scheme (e.g. `b:ff4c00p:040404s:171c01t:361303q:452501`); frequently `null` in practice |
| `iconPictureUrl` | string | Resolved URL of the app icon |
| `subtitle` | string | App subtitle on the App Store |
| `primaryCategory` | string | App category |
| `inAppPurchases` | boolean | Whether the app has in-app purchases |
| `promotionalText` | string | App description on the App Store |
| `editorialBadge` | boolean | App Store editorial badge shown |
| `shortDescription` | string | Short description (shown when `promotionalText` is absent) |

### AdAsset object

| Field | Type | Description |
|---|---|---|
| `videoUrl` | string | Resolved URL of video asset (null if none) |
| `pictureUrl` | string | Resolved URL of image asset (null if none) |
| `order` | integer | Upload order in App Store Connect |
| `height` | integer | Asset height in pixels |
| `width` | integer | Asset width in pixels |
| `orientation` | string | `LANDSCAPE`, `PORTRAIT`, or `UNKNOWN` |

---

## Enumerations

### Placement

| Value | Description |
|---|---|
| `APPSTORE_SEARCH_RESULTS` | Ads shown in App Store search results |
| `APPSTORE_TODAY_TAB` | Ads shown on the Today tab |
| `APPSTORE_SEARCH_TAB` | Ads shown on the Search tab |
| `APPSTORE_PRODUCT_PAGE` | Ads shown on app product pages (not listed in PDF spec but returned by live API) |

### Date presets

| Value | Description |
|---|---|
| `LAST_90_DAYS` | 90 days ending 7 days ago (default) |
| `LAST_180_DAYS` | 180 days ending 7 days ago |
| `LAST_YEAR` | 365 days ending 7 days ago |

### Restriction reasons

| Value | Meaning |
|---|---|
| `REASON_GOVERNMENT_ORDER` | Removed by government order |
| `REASON_THIRD_PARTY_REPORT` | Removed following third-party report |
| `REASON_POLICY_RESTRICTION_AGE` | Age-related policy restriction |
| `REASON_POLICY_RESTRICTION` | General policy restriction |
| `REASON_TOS_INCOMPATABILITY` | Incompatible with Terms of Service |

### Action taken

| Value | Description |
|---|---|
| `ACTION_ACCOUNT_SUSPENDED` | Advertiser account suspended |
| `ACTION_ADVERTISING_REMOVED` | Specific advertising removed |

### Customer type values

| Value | Description |
|---|---|
| `ALL_USERS` | Targeting all users |
| `NEW_USERS` | Targeting new users only |
| `RETURNING_USERS` | Targeting returning users |
| `USERS_OF_MY_OTHER_APPS` | Targeting users of the developer's other apps |

---

## Changelog

| Date | Change |
|---|---|
| March 2025 | Added countries to GET /countries-or-regions response |
| October 2024 | Added `subFormat` field to ads and variations responses |
| March 2024 | Updated description of `firstImpressionDate` |
| January 2024 | Added `joeColor` to ads, variations, and restrictions responses |
| November 2023 | Added `shortDescription` field |
| August 2023 | Initial version |
