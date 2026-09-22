# Economics — what a customer costs, and handing that decision to the user

Read this before Phase 5 (JUDGE). The formulas here are exactly what
`scripts/cac.py` computes — run the script rather than doing the arithmetic
inline (it applies scenario bands consistently and emits a bankable JSON).
This file explains the model so you can choose inputs honestly, and explains
the handoff: **you measure CAC, the user decides whether it's worth it.**

## There is no LTV:CAC test here — on purpose

This loop used to grade every node against LTV:CAC ≥ 3.0 and stamp it
STRONG / PROMISING / LONG-SHOT / FAILS. That test is gone.

LTV = ARPU × margin / churn. On a pre-product idea, **churn is unmeasurable**
and ARPU is a competitor's price, not yours — so the ratio was two guesses
divided by a third, dressed up to three significant figures. Worse, it made
the skill the decider: a node with real, reachable demand got labelled FAILS
because an assumed 10%/mo churn made an assumed LTV too small. Founders'
actual retention, pricing power, margin structure, patience, and cost of
capital vary by an order of magnitude, and none of that is in the data.

What the instruments *can* support is the cost side:

- **CPC is measured** (P1, live auction).
- **Funnel is assumed** — but it's one assumption, stated, banded, and the
  confirmation test's whole job is to replace it with a measurement.
- **Price is observed** (P8, what the market already charges).

So the deliverable is: **this is what a customer costs, here is what you'd
have to charge or retain for that to pay off, here are the cheaper channels,
and here's what a real test would cost.** Then the user chooses. Reporting
"CAC is $205 conservative $427, and at $49/mo you need 5–10 months of
retention" respects both the data and the person spending the money.
Stamping FAILS on it does neither.

**Never write a verdict word about worth.** No STRONG, no FAILS, no "the
economics don't work". CAC is a number you report; worth-it is a judgement
the user makes. The one exception: if the user *themselves* named a maximum
they'd pay per customer at intake, `cac.py --ceiling` reports measured CAC
against **their** line, labelled as theirs.

## The model

**Paid-search CAC** — what one paying customer costs to buy from the auction:

```
CAC = CPC / funnel          where funnel = P(ad click → paying customer)
```

`funnel` compresses the whole chain (click→signup→activation→paid) into one
observable-adjacent number. Compressing is deliberate: mid-funnel stages
aren't measurable from public data, and one conservative end-to-end rate is
harder to fool yourself with than four optimistic stage rates multiplied
together.

**What it takes to pay that back**, at each candidate monthly price:

```
months_to_repay = CAC / (price × margin)
```

This replaces LTV. It needs no churn estimate — it *inverts* the question
into one the user can actually answer: *can you keep a customer longer than
this?* A founder knows their own conviction about retention far better than
any preset does.

**Cohort cost** — the number that makes CAC concrete:

```
cost_of_N_customers = CAC × N          (cac.py prints N = 10 and N = 100)
```

"Your first 100 customers cost $20,500 in ads" lands where a ratio doesn't.

**Three scenarios**, derived from your base inputs — funnel is the soft
number, so it swings widest:

| Scenario | CPC | funnel |
|---|---|---|
| conservative | ×1.25 | ×0.60 |
| base | as given | as given |
| optimistic | ×0.85 | ×1.40 |

Report the **band**, never a single figure. "CAC $125–427, most likely ~$205"
is honest; "$205" is not.

**Reachable demand** (when `--volume` given): a ceiling sanity check —

```
clicks_ceiling ≈ cluster_volume × 0.04     (top-of-page ad share a new entrant can win)
customers/mo  ≈ clicks_ceiling × funnel
spend/mo      ≈ clicks_ceiling × CPC
```

A node with cheap CAC but 11 reachable customers/month is a lifestyle
corridor, not a startup one — report it as such and let the user say which
they wanted. (0.04 is deliberately conservative; organic/content channels add
headroom on top.)

**Organic / content CAC** — the second channel option, on the same axes:

```
content_CAC = cost_per_post / (median_views × view_to_visit × funnel)
```

with `view_to_visit` 0.5–2% (0.5% conservative) and `cost_per_post` your
honest production estimate ($20–150 typical for short-form). Pass
`--content-cost-per-post` / `--content-median-views` (from P4) and `cac.py`
prints it next to paid CAC. A node can be expensive on the auction and cheap
on content — that's not a failing node, it's a channel choice, and it belongs
in the options menu below.

## Input presets — defaults, not truths

Every preset used must appear in the report's assumptions register. When you
have a better anchor (an ad test, the user's own funnel data), override the
preset and cite the anchor in `verdict.md`.

| Preset | funnel (visit→paid) | Typical fit |
|---|---|---|
| `b2c_sub` | 1.0% | Consumer subscription apps |
| `prosumer` | 1.5% | Individual professionals paying personally |
| `b2b_smb` | 2.0% | Self-serve SMB SaaS, credit-card checkout |
| `b2b_mid` | 0.5% | Sales-assisted mid-market (funnel = visit→closed deal) |

These sit at the conservative end of published benchmark ranges on purpose,
and the scenario band (×0.6 funnel) stacks on top — public-data forecasting
deserves a double margin of safety on the one number nobody measured.

Churn presets are gone with the LTV test; if a user tells you their real
retention, use it in the repay table's narrative, cite it, and keep it out of
the arithmetic the script does.

**Margin** defaults to 0.85 (software COGS incl. inference; drop to 0.6–0.7
for inference-hungry or human-in-the-loop products). It only enters
`months_to_repay`, so say which value you used.

**Prices** (`--price`, repeatable): anchor on P8's *observed* distribution —
the mode of comparable paid tiers, plus one tier above and below to show what
pricing power buys. For B2B, sanity-check against the P7 salary anchor: a
tool replacing $45k/yr of labor supports $200+/mo; a tool saving 20 min/week
does not support $99/mo. Prices are **options to weigh**, not a forecast of
what the user will charge.

**CPC**: from P1, volume-weighted median over the *commercial-intent* subset
only. For finalists, prefer the `ad-traffic` forecast CPC (post-2024 Google
aggregate) — it reflects the live auction better than planner CPC.

## The handoff — telling the user what CAC will be

Every surviving node gets this block, in `verdict.md`, in `report.md`, and in
chat. Four numbers and a sentence, no adjectives:

1. **CAC band** — "$125 optimistic / $205 base / $427 conservative, driven by
   a measured $4.10 CPC and an assumed 2% funnel."
2. **What it buys** — "first 100 customers ≈ $20,500 in ads at base."
3. **What it demands back** — the repay table: "at $49/mo you need ~5 months
   of retention (base) or ~10 (conservative); at $99/mo, ~2.5 / ~5."
4. **The ceiling** — "the whole cluster tops out around ~18 customers/mo at
   ~$3,600/mo spend."

Then, explicitly: *"I'm not going to tell you whether that's worth it — that
depends on your retention, your margin, and how much capital you're willing
to put in front of the first 100 customers. Here are your options."*

## The options menu — always give them, always with numbers

Never end on a bare number, and never end on a single recommendation. Give
the user a menu, each option carrying the figure that changes if they pick
it. The standard five (drop any that the data doesn't support, add
node-specific ones):

| Option | What it means | The number that moves |
|---|---|---|
| **A — Test it for real** | Run the cheapest confirmation test before committing: ~$200 of exact-match ads to a priced landing page | Replaces the assumed funnel with a measured signup rate → collapses the CAC band. Give the go/no-go: "≤$2.50/signup and CAC lands near base; ≥$5 and the forecast is wrong" |
| **B — Charge more** | Same node, higher MODEL tier (group/team/annual) | Repay months at each price — from the repay table, not from imagination |
| **C — Change channel** | Content/organic, marketplace or integration listings, outbound | Content CAC vs paid CAC, side by side, with the estimate flagged as an estimate |
| **D — Narrow the WHO** | Descend to a vertical whose long-tail clicks are cheaper | Tail CPC vs head CPC (both measured) → the CAC it implies |
| **E — Walk away** | Say no now, cheaply | State what CAC (or what price, or what retention) would have made it a yes — that's the trigger to revisit |

Two rules for the menu:

- **Price every option.** An option without a number attached is a vibe.
- **Say which you'd pick and why in one line** — a recommendation the user
  can overrule is useful; a menu with no point of view is abdication. The
  decision still belongs to them.

When the user is present, put the menu to them directly (AskUserQuestion) and
record the choice in the notebook — it steers the next TRAVERSE. When they're
absent, write the menu into `report.md` and stop there; do not pick for them
and spend the remaining budget on the branch you liked.

## Where acquisition is cheap — patterns to hunt

"Cheap" here always means cheap **relative to another measured number** —
never relative to an imagined LTV. Every claim names its pattern, shows the
two numbers whose gap constitutes it, and gives the persistence explanation:
*why does this gap exist, and why hasn't it been competed away?* A gap you
cannot explain is more likely planner-CPC noise, brand-term contamination, or
a geo mismatch than free money — treat it as an instrument anomaly to
investigate, not a finding to report.

1. **Fast payback at prices the market already pays** (P1+P8) — CAC repays
   inside 1–3 months at the *observed* mode price of comparable products.
   Both numbers measured; only margin is assumed. The strongest form of
   "acquisition looks cheap here".
2. **Head-vs-tail CPC gap** (P1) — the vertical long-tail ("X for dentists")
   prices at a fraction of the head term ("X software") for the same buyer,
   because incumbents bid the head and ignore the tail. Show both CPCs.
3. **Rising volume, flat CPC** (P9) — demand growing faster than advertiser
   attention; the window closes as the auction catches up, so date it.
4. **High-intent tail, zero ads** (P1+P2) — commercial queries with no
   advertiser at all: free clicks via SEO/a dedicated landing page, or fund
   the auction at reserve prices. Before crediting the zero, check the known
   incumbents' ad libraries (P5) — a single SERP snapshot misses dayparted
   and rotated ads.
5. **SERP gap** (P2) — intent with no dedicated product ranking; the subsidy
   is that *organic* position is winnable.
6. **Angry-incumbent conversion subsidy** (P3) — incumbents ≥15% complaint
   rate on a fixable wedge: the same clicks convert better against a weak
   default, which is a funnel argument, so say so and adjust `--funnel`
   explicitly rather than silently.
7. **Content-auction disconnect** (P4) — large topical attention, few
   creators, no product presence: content CAC ≪ paid CAC.
8. **Salary-priced value, consumer-priced tools** (P7+P8) — companies pay
   salaries for the job while existing tools price like consumer apps: the
   MODEL axis is mispriced, not the channel.

## Threats to validity — say these out loud in the report

- **Funnel is assumed, not measured** — it is the single largest source of
  spread in the CAC band, and replacing it is exactly what the recommended
  confirmation test does. Never present base CAC as *the* CAC.
- **Planner CPC ≠ your CPC** — quality score, landing page, and match type
  move real CPCs ±50%; `ad-traffic` narrows but doesn't close this.
- **Retention is the user's to estimate** — the repay table says how long
  they'd need to hold a customer; it does not claim they will. Do not
  quietly re-import a churn guess to answer it for them.
- **Search volume merges variants**; brand terms inflate category clusters
  (strip navigational terms like "otter ai login" before summing).
- **Geo blind spots** — apple-ads is EU-only (Google-surface sustainer checks
  in any country belong to dataforseo-ads-transparency, which is
  country-level only — no city precision); TikTok is FYP-noisy; App Store is
  B2C-lensed. A B2B node's marketplace silence is expected, not damning.
- **Survivorship** — no competitors ≠ no demand (and ≠ demand). Only P1/P4
  demand data disambiguates an empty corridor.
- **Timing** — CPCs and volumes move monthly. Date every number; forecasts
  older than a quarter deserve a re-probe (cache makes repeats cheap).
- **Expressed demand only** — every instrument reads behavior that already
  exists. A novelty-dependent idea (a want the product itself would create)
  is outside this method's reach *in principle*: zero signal there is scope,
  not refutation. Carry intake's classification into the report.
- **Public data is public** — any cheap-CAC window visible to this loop is
  visible to anyone who runs it. The durable edge is the explanation behind
  the numbers and the test you actually run.

## Worked example (matches the script exactly)

N04 "AI SOAP notes for solo therapists": P1 → commercial cluster 22,000/mo
(US), weighted median CPC $4.10. P8 → comparable tiers $39/$49/$99, mode $49.
Preset `b2b_smb` (self-serve, card checkout): funnel 2%, margin 0.85. P4 →
topic content median 40k views, ~$60/post production.

```bash
python3 .claude/skills/demand-forecasting/scripts/cac.py \
  --cpc 4.10 --funnel-preset b2b_smb --price 49 --price 99 \
  --volume 22000 --content-cost-per-post 60 --content-median-views 40000 \
  --label "N04 solo-therapist SOAP notes"
```

| scenario | CPC | funnel | CAC | 100 customers | content CAC |
|---|---|---|---|---|---|
| conservative | $5.12 | 1.20% | $427 | $42,708 | $25 |
| base | $4.10 | 2.00% | $205 | $20,500 | $15 |
| optimistic | $3.48 | 2.80% | $124 | $12,446 | $11 |

Repay: at **$49/mo** → 10.3 / 4.9 / 3.0 months; at **$99/mo** → 5.1 / 2.4 /
1.5 months. Reach ceiling ≈ 880 clicks/mo → ~18 customers/mo at ~$3,600/mo.

**What you tell the user:** "Buying a therapist customer on Google costs
about $205, and up to $427 if the funnel disappoints — the first 100 cost
$20k–43k. At $49/mo they have to stay 5–10 months to pay that back; at $99/mo
it's 2.5–5. Content looks an order of magnitude cheaper (~$15/customer) but
that's an estimate, not a measurement. The whole search cluster tops out
around 18 customers/mo."

**Options:** (A) $200 exact-match ad test → go if ≤$2.50/signup, which would
pin the funnel; (B) test the $99 group-practice tier, where payback halves;
(C) content-first, and treat paid as a top-up; (D) narrow to solo therapists
in cash-pay practice, where the tail CPC was $2.60 vs the $4.10 cluster
median; (E) walk — worth doing if you can't fund $20k of acquisition before
revenue compounds. "I'd take A before B — one $200 test collapses the widest
band in the model." Their call, logged either way.
