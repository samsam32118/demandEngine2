#!/usr/bin/env python3
"""theme.py — the Ramp design system, transcribed. Stdlib only.

`assets/DESIGN.md` is the source of truth; this file is its transcription for
Python. When the two disagree, DESIGN.md wins — fix this file, not that one.

Everything here is addressed by **token name**, never by raw hex, because the
tokens carry the brand's reasoning and the hexes do not. `COLOR["primary"]`
says "the single filled affordance"; `#ffe74c` says nothing, and the moment a
call site hardcodes it the discipline is gone.

The three rules that shape every chart in this skill:

**One weight.** Lausanne is proprietary; the spec names Inter 400 as the
canonical substitute, and `assets/fonts/Inter-Regular.ttf` ships with the
skill. Every tier — 48px hero down to the 10px eyebrow — renders at 400.
Hierarchy comes from size alone. `weight()` exists so no call site can quietly
ask for bold.

**One voltage.** Yellow is the only filled brand colour, reserved for the
product being positioned and for the single recommendation. Everything the
product is measured against uses the ink ladder — `ink` → `ink-secondary` →
`ink-mute` → `ink-mute-2`. That is not a compromise for lack of hues: the
spec forbids a secondary accent, and a monochrome ladder happens to be the
most legible categorical encoding there is once shape and label carry the
meaning too.

**Sand, not white.** The page is `canvas-sand`; white is for the tiles that
float on it. The contrast between the two IS the elevation — this system has
essentially no shadow tier, so a chart is a white tile with a 1px `hairline`
border and 12px corners, and that is what gives it depth.

Run `python3 theme.py` to audit contrast on every pair a reader has to read.
"""

# ---------------------------------------------------------------- tokens
# Transcribed verbatim from assets/DESIGN.md § Colors.
COLOR = {
    "primary":         "#ffe74c",   # the single filled brand affordance
    "on-primary":      "#212121",   # text on yellow — near-black, NEVER white
    "ink":             "#212121",   # body text; warm near-black, never pure #000
    "ink-soft":        "#2b2e35",   # dark tile fill
    "ink-secondary":   "#2d3748",   # secondary headings
    "ink-mute":        "#4a5568",   # helper text, captions
    "ink-mute-2":      "#718096",   # disabled and badge text
    "ink-mute-3":      "#a0aec0",   # tertiary placeholder ONLY — never body text
    "canvas":          "#ffffff",   # tiles floating on the sand
    "canvas-sand":     "#f4f2f0",   # DEFAULT PAGE BACKGROUND — non-negotiable
    "canvas-cool":     "#f7fafc",
    "canvas-hover":    "#edf2f7",
    "hairline":        "#e2e8f0",   # 1px borders — the system's whole edge treatment
    "midnight-top":    "#000000",
    "midnight-bottom": "#112d5b",
    "solar":           "#f4d35e",
    "blaze":           "#e07a3c",   # sanctioned as a CHART LINE COLOR
    "success":         "#38a169",
    "danger":          "#e53e3e",
}

# § Typography. size, line-height, letter-spacing. Weight is 400. Always.
TYPE = {
    "display-xl": (48, 50, -0.01),
    "display-lg": (40, 42, -0.005),
    "display-md": (28, 32, 0.0),
    "heading":    (24, 28, 0.0),
    "body-lg":    (20, 26, 0.0),
    "body-md":    (16, 24, 0.0),
    "body-sm":    (14, 20, 0.0),
    "caption":    (13, 19, 0.0),
    "micro-cap":  (10, 22, 0.18),   # ALL CAPS — the only uppercase in the system
}

ROUNDED = {"xs": 4, "sm": 6, "md": 8, "ms": 10, "lg": 12, "xl": 16, "pill": 9999}
SPACING = {"xs": 4, "sm": 8, "md": 12, "lg": 16, "xl": 20, "xxl": 24,
           "huge": 32, "mega": 64}
TILE_PAD = (32, 24, 32, 32)     # § Layout: the canonical asymmetric tile inset

FONT_STACK = ["Inter", "Geist Sans", "Liberation Sans", "DejaVu Sans"]
WEIGHT = 400                    # the whole system. There is no other value.


def c(token):
    """A colour by token name. Raises on an unknown token rather than guessing —
    a silent fallback is how a palette drifts back to improvised hexes."""
    try:
        return COLOR[token]
    except KeyError:
        raise KeyError(f"no such colour token: {token!r}. "
                       f"Known: {', '.join(sorted(COLOR))}") from None


def size(token):
    return TYPE[token][0]


def leading(token):
    return TYPE[token][1]


def tracking(token):
    return TYPE[token][2]


def weight(_token=None):
    """Always 400. The single-weight discipline is the brand voice, so this is
    a function rather than a constant: a call site asking for a weight gets the
    only answer the system has."""
    return WEIGHT


# ------------------------------------------------------------ semantic roles
# The product being positioned. Yellow is the only voltage in the system, so it
# means exactly one thing on every page: this is you.
YOU        = c("primary")
YOU_EDGE   = c("ink")           # yellow needs an ink hairline to be a legible mark
YOU_TINT   = "#fff9d9"          # primary at ~18% over canvas — chip backgrounds
ON_YOU     = c("on-primary")

# What the product is measured against: the ink ladder, per "no secondary
# brand accent". Ordered darkest-first so the most serious rival reads heaviest.
LANE_COLORS = {
    "direct":   c("ink"),
    "adjacent": c("ink-secondary"),
    "diy":      c("ink-mute"),
    "nothing":  c("ink-mute-2"),
}
LANE_LABELS = {"direct": "Direct competitors", "adjacent": "Adjacent tools",
               "diy": "Do it themselves", "nothing": "Do nothing"}
LANE_ORDER = ["direct", "adjacent", "diy", "nothing"]

# Badge anatomy, per § Components: fill + ink-level text. Colour never carries
# the text. `gap` puts danger on the border, which is the only place it clears
# contrast and the only role the spec gives it outside the cookie banner.
VERDICT_STYLE = {
    "unique":       {"fill": c("primary"),      "text": c("on-primary"),    "edge": c("ink")},
    "table_stakes": {"fill": c("canvas-hover"), "text": c("ink-secondary"), "edge": c("hairline")},
    "gap":          {"fill": c("canvas"),       "text": c("ink-secondary"), "edge": c("danger")},
}
VERDICT_COLORS = {k: v["edge"] for k, v in VERDICT_STYLE.items()}
VERDICT_LABELS = {"unique": "Only you", "table_stakes": "Table stakes",
                  "gap": "You lack it"}

# Sequential ramp for the heat map: sand → solar → blaze. All three are brand
# tokens, and blaze is explicitly sanctioned for charts. Ink stays legible on
# every step, so no cell needs a white-text exception.
HEAT_STOPS = [c("canvas-sand"), "#fbeeb8", c("solar"), "#eda94a", c("blaze")]

# Categorical series for value-flow themes. Yellow leads; the rest step down
# the ink ladder rather than introducing hues the brand does not have.
SERIES = [c("primary"), c("ink"), c("ink-secondary"), c("ink-mute"),
          c("ink-mute-2"), c("blaze")]

# Convenience aliases used across the chart set.
INK       = c("ink")
INK_SOFT  = c("ink-secondary")
MUTED     = c("ink-mute")
FAINT     = c("ink-mute")        # deliberately NOT ink-mute-2: 4.4:1 is too thin
HAIR      = c("hairline")
RULE      = c("hairline")
PAPER     = c("canvas")
SAND      = c("canvas-sand")
SURFACE   = c("canvas-hover")


# ------------------------------------------------------------ contrast math

def _srgb(v):
    v = v / 255.0
    return v / 12.92 if v <= 0.04045 else ((v + 0.055) / 1.055) ** 2.4


def luminance(hex_color):
    h = hex_color.lstrip("#")
    r, g, b = (int(h[i:i + 2], 16) for i in (0, 2, 4))
    return 0.2126 * _srgb(r) + 0.7152 * _srgb(g) + 0.0722 * _srgb(b)


def contrast(fg, bg):
    a, b = luminance(fg), luminance(bg)
    lo, hi = sorted((a, b))
    return (hi + 0.05) / (lo + 0.05)


def ink_on(bg):
    """The readable text colour for a fill. In this system the answer is almost
    always ink — the palette is built so that it is — but the dark tile and the
    midnight gradient need canvas, and a fixed choice fails at one end."""
    return INK if contrast(INK, bg) >= contrast(PAPER, bg) else PAPER


PAIRS = [
    ("body on sand",        c("ink"),           c("canvas-sand"), 4.5),
    ("body on tile",        c("ink"),           c("canvas"),      4.5),
    ("secondary on tile",   c("ink-secondary"), c("canvas"),      4.5),
    ("caption on tile",     c("ink-mute"),      c("canvas"),      4.5),
    ("caption on sand",     c("ink-mute"),      c("canvas-sand"), 4.5),
    ("text on the chip",    c("on-primary"),    c("primary"),     4.5),
    ("text on chip tint",   c("ink"),           YOU_TINT,         4.5),
    ("lane: direct",        LANE_COLORS["direct"],   c("canvas"), 4.5),
    ("lane: adjacent",      LANE_COLORS["adjacent"], c("canvas"), 4.5),
    ("lane: diy",           LANE_COLORS["diy"],      c("canvas"), 4.5),
    ("lane: nothing",       LANE_COLORS["nothing"],  c("canvas"), 3.0),
    ("verdict: gap border", c("danger"),        c("canvas"),      3.0),
    ("verdict: gap text",   c("ink-secondary"), c("canvas"),      4.5),
    ("verdict: stakes text", c("ink-secondary"), c("canvas-hover"), 4.5),
    ("ink on hottest cell", c("ink"),           HEAT_STOPS[-1],   4.5),
    ("ink on mid cell",     c("ink"),           HEAT_STOPS[2],    4.5),
    ("ink on coolest cell", c("ink"),           HEAT_STOPS[0],    4.5),
    ("tile edge on sand",   c("hairline"),      c("canvas-sand"), 1.05),
    ("chip edge on tile",   YOU_EDGE,           c("canvas"),      3.0),
    ("dark tile text",      c("canvas"),        c("ink-soft"),    4.5),
]


def audit(verbose=True):
    fails = []
    for name, fg, bg, need in PAIRS:
        r = contrast(fg, bg)
        if r < need:
            fails.append((name, fg, bg, r, need))
        if verbose:
            print(f"  {'PASS' if r >= need else 'FAIL'}  {r:5.2f}:1  "
                  f"(need {need})  {name}  {fg} on {bg}")
    return fails


if __name__ == "__main__":
    import sys
    print("Ramp design system — WCAG audit\n")
    fails = audit()
    print()
    if fails:
        print(f"{len(fails)} pair(s) below target:")
        for name, fg, bg, r, need in fails:
            print(f"  {name}: {r:.2f}:1, needs {need}:1 ({fg} on {bg})")
        sys.exit(1)
    print(f"All {len(PAIRS)} pairs pass.")
