# Ramp Inspired — DESIGN.md
Source: https://designmd.directory/p/ramp-design-md  ·  https://ramp.com
This file is the SOURCE OF TRUTH for every visual decision in this skill.
scripts/theme.py is a transcription of it; when they disagree, this file wins.

## Product feel
Finance automation. Editorial restraint as authority — a back-office platform
that doesn't shout. Reads like a printed magazine, not a SaaS console.

## Colors
primary        #ffe74c   the single filled brand affordance. One per band.
on-primary     #212121   text on yellow is near-black, NEVER white
ink            #212121   default body text; warm near-black, never pure #000
ink-soft       #2b2e35   dark tile fill, cookie-banner CTA
ink-secondary  #2d3748   secondary headings, link emphasis
ink-mute       #4a5568   helper text, captions, footer body
ink-mute-2     #718096   disabled and badge text
ink-mute-3     #a0aec0   tertiary placeholder only
canvas         #ffffff   tiles, cards, inputs floating on the sand
canvas-sand    #f4f2f0   DEFAULT PAGE BACKGROUND — non-negotiable
canvas-cool    #f7fafc   secondary surfaces
canvas-hover   #edf2f7   row hover, neutral fill inside tables
hairline       #e2e8f0   1px borders on tiles, inputs, table rows
midnight-top   #000000   gradient stop (product-tile interiors only)
midnight-bottom #112d5b  gradient stop
solar          #f4d35e   gradient stop; never a button
blaze          #e07a3c   CHART LINE COLOR and band-fill gradient stop
success        #38a169
danger         #e53e3e

## Typography — Lausanne, fallback Inter 400 / Geist Sans 400
ONE WEIGHT (400) ACROSS EVERY TIER. No thin variant. No bold variant.
Hierarchy comes from size alone.
display-xl  48/50  -0.01px   hero
display-lg  40/42  -0.005px  section opener
display-md  28/32   0        sub-section
heading     24/28   0        card title
body-lg     20/26   0        lede
body-md     16/24   0        default body
body-sm     14/20   0        UI label, button text
caption     13/19   0        helper, table label
micro-cap   10/22  +0.18px   ALL-CAPS eyebrow (only uppercase, only positive tracking)

## Rounded
xs 4  ·  sm 6  ·  md 8  ·  ms 10  ·  lg 12  ·  xl 16  ·  pill 9999

## Spacing (base unit 4px)
xs 4 · sm 8 · md 12 · lg 16 · xl 20 · xxl 24 · huge 32 · mega 64
Tile internal padding: asymmetric 32px 24px 32px 32px

## Elevation
0  flat on canvas-sand                       default page surface
1  1px hairline border on canvas             product tiles, cards, inputs
2  drop-shadow 0 3px 3px rgba(0,0,0,0.12)    modal, dropdown
3  drop-shadow 0 9px 7px rgba(0,0,0,0.1)     floating composite on dark
Primary depth medium is the TILE MOSAIC — white tiles on sand. Not shadow.

## Do
- Reserve #ffe74c for the single CTA per band, sized BELOW the body text.
- Run every type tier at weight 400. Size creates hierarchy.
- canvas-sand for the page; canvas (white) for tiles floating on it.
- Build bands as grids of bordered white tiles — the mosaic is the signature.
- -0.01px tracking at 48px, -0.005px at 40px; body and below stay at 0.
- Named gradients (midnight, dusk, daylight, solar, blaze) inside tiles only.

## Don't
- Don't bump above weight 400 — the single-weight discipline IS the brand voice.
- Don't enlarge the yellow chip to a full-width pill.
- Don't replace the sand canvas with pure white at page level.
- Don't add a secondary brand accent. Yellow is the only voltage.
- Don't use the named gradients as page backgrounds or button fills.
- Don't add layered shadows for elevation — the tile mosaic carries the depth.
