#!/usr/bin/env python3
"""build_pdf.py — the positioning report, as a deck of pictures.

The brief this skill serves is "as little text as possible", which is not a
style preference: positioning is a set of comparisons, and comparisons are
what prose is worst at. Every spread here is one picture that carries one of
April Dunford's steps, framed by a kicker, a headline and at most one line of
consequence. If a page needs a paragraph to land, the chart on it is wrong.

Usage:
    build_pdf.py --run research/positioning/<slug>
    build_pdf.py --run <run> --out /tmp/other.pdf --portrait

Reads <run>/report-manifest.json and <run>/charts/*.png. Prints a report card
at the end naming anything missing, so a thin run is visible rather than
silently shipped.

Needs:  python3 -m pip install reportlab pillow matplotlib
"""

import argparse
import csv
import json
import os
import re
import sys
import textwrap
from datetime import date

try:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import letter, landscape
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.units import inch
    from reportlab.lib.utils import ImageReader
    from reportlab.platypus import (BaseDocTemplate, Frame, PageTemplate, Paragraph,
                                    Spacer, Image, Table, TableStyle, PageBreak,
                                    Flowable, NextPageTemplate)
except ImportError:
    print("error: reportlab is not installed.\n"
          "fix:   python3 -m pip install reportlab pillow matplotlib", file=sys.stderr)
    sys.exit(3)

# assets/DESIGN.md is the source of truth; theme.py transcribes it and audits
# its own contrast. Run `python3 theme.py` after any change.
import theme as T
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

def _c(token):
    """A reportlab colour from a DESIGN.md token name."""
    return colors.HexColor(T.c(token))

INK        = _c("ink")
INK_SOFT   = _c("ink-secondary")
MUTED      = _c("ink-mute")
FAINT      = _c("ink-mute")
HAIR       = _c("hairline")
RULE       = _c("hairline")
PAPER      = _c("canvas")
SAND       = _c("canvas-sand")
SURFACE    = _c("canvas-hover")
YOU        = _c("primary")
ON_YOU     = _c("on-primary")
YOU_EDGE   = _c("ink")
YOU_TINT   = colors.HexColor(T.YOU_TINT)
RIVAL      = colors.HexColor(T.LANE_COLORS["direct"])
RIVAL_TINT = _c("canvas-hover")
ADJACENT   = colors.HexColor(T.LANE_COLORS["adjacent"])
DIY        = colors.HexColor(T.LANE_COLORS["diy"])
DIY_TINT   = _c("canvas-hover")
GOLD       = _c("solar")
DARK_TILE  = _c("ink-soft")

R_LG = T.ROUNDED["lg"]      # 12px — tiles, cards, buttons
R_MD = T.ROUNDED["md"]      # 8px  — badges
R_XS = T.ROUNDED["xs"]      # 4px  — inline

# Lausanne is proprietary; DESIGN.md names Inter 400 as the substitute and
# warns that system-ui defaults break the brand's print-like density.
_FONTS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "assets", "fonts")
_INTER = os.path.join(_FONTS, "Inter-Regular.ttf")
if os.path.isfile(_INTER):
    pdfmetrics.registerFont(TTFont("Inter", _INTER))
    F = FB = FI = "Inter"
else:
    warn_font = True
    F = FB = FI = "Helvetica"

WARN_LOG = []


def warn(msg):
    WARN_LOG.append(msg)
    print(f"warn: {msg}", file=sys.stderr)


def esc(t):
    return (str(t if t is not None else "")
            .replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))


def human(n):
    try:
        n = float(n)
    except (TypeError, ValueError):
        return "—"
    if n >= 1_000_000:
        return f"{n/1_000_000:.1f}M".replace(".0M", "M")
    if n >= 1_000:
        return f"{n/1_000:.1f}k".replace(".0k", "k")
    return f"{n:,.0f}"


def short(t, n):
    t = str(t or "")
    return t if len(t) <= n else t[:n - 1].rstrip() + "…"


# ------------------------------------------------------------------- pages

# The eight chart pages, in the order Dunford's method runs. `step` is what the
# kicker says; `so_what` is the one line of consequence the analyst may
# override from the manifest.
SPREADS = [
    ("customer_evidence", "Step 1", "Understand your best customers", "customers_note"),
    ("vocabulary_gap",    "Step 2", "Align on vocabulary",            "vocabulary_note"),
    ("alternatives_map",  "Step 3", "List the true alternatives",     "alternatives_note"),
    ("attribute_matrix",  "Step 4", "Isolate what is only yours",     "attributes_note"),
    ("value_flow",        "Step 5", "Map attributes to value",        "value_note"),
    ("segment_heat",      "Step 6", "Find who cares a lot",           "segments_note"),
    ("frame_quadrant",    "Step 7", "Choose the market frame",        "frame_note"),
    ("messaging_crowd",   "Step 8", "Take the open ground",           "messaging_note"),
]


# DESIGN.md sizes are web pixels. A printed page is read closer than a screen,
# so the whole scale is taken down by one factor — the RATIOS between tiers are
# what the brand actually specifies, and those survive the scaling intact.
PT = 0.78


def ts(token):
    """Font size in points for a DESIGN.md typography token."""
    return T.size(token) * PT


def tl(token):
    """Leading in points for the same token."""
    return T.leading(token) * PT


def styles(wide):
    S = {}
    # micro-cap is the only uppercase in the system and the only positive
    # tracking. reportlab has no tracking on ParagraphStyle, so the eyebrow is
    # spaced by hand at the call site where it matters.
    S["kicker"] = ParagraphStyle("kicker", fontName=F, fontSize=ts("micro-cap"),
                                 leading=tl("micro-cap"), textColor=MUTED, spaceAfter=2)
    S["h1"] = ParagraphStyle("h1", fontName=F, fontSize=ts("display-md"),
                             leading=tl("display-md"), textColor=INK, spaceAfter=4)
    S["h2"] = ParagraphStyle("h2", fontName=F, fontSize=ts("heading"),
                             leading=tl("heading"), textColor=INK, spaceAfter=6)
    S["deck"] = ParagraphStyle("deck", fontName=F, fontSize=ts("body-md"),
                               leading=tl("body-md"), textColor=MUTED, spaceAfter=8)
    S["sowhat"] = ParagraphStyle("sowhat", fontName=F, fontSize=ts("body-md"),
                                 leading=tl("body-md"), textColor=INK)
    S["tiny"] = ParagraphStyle("tiny", fontName=F, fontSize=ts("micro-cap"),
                               leading=tl("micro-cap"), textColor=MUTED)
    S["cell"] = ParagraphStyle("cell", fontName=F, fontSize=ts("caption"),
                               leading=tl("caption"), textColor=INK_SOFT)
    S["cellb"] = ParagraphStyle("cellb", fontName=F, fontSize=ts("caption"),
                                leading=tl("caption"), textColor=INK)
    return S


class Tile(Flowable):
    """A white product-tile on the sand canvas, holding one image.

    DESIGN.md § Elevation: "the contrast between the tile and the canvas IS the
    elevation" — this system has essentially no shadow tier, so a chart becomes
    a white card with a 1px hairline border and 12px corners, and that is what
    gives it depth. Drawing the tile rather than relying on the PNG's own white
    background is the difference between a chart pasted on a page and a chart
    that belongs to the brand.
    """

    def __init__(self, img_path, width, max_height, pad=16):
        Flowable.__init__(self)
        self.img, self.width, self.pad = img_path, width, pad
        # Size the tile to its content. A tile with a slab of empty white on one
        # side reads as a layout mistake, not as breathing room — the mosaic
        # works because each tile is the shape of what it holds.
        self.height = max_height
        try:
            iw, ih = ImageReader(img_path).getSize()
            self.height = min(max_height, (width - 2 * pad) * ih / iw + 2 * pad)
        except Exception:
            pass

    def draw(self):
        c = self.canv
        c.saveState()
        c.setFillColor(PAPER)
        c.setStrokeColor(HAIR)
        c.setLineWidth(1)
        c.roundRect(0, 0, self.width, self.height, R_LG, stroke=1, fill=1)
        try:
            iw, ih = ImageReader(self.img).getSize()
            box_w, box_h = self.width - 2 * self.pad, self.height - 2 * self.pad
            sc = min(box_w / iw, box_h / ih)
            w, h = iw * sc, ih * sc
            c.drawImage(self.img, (self.width - w) / 2, (self.height - h) / 2,
                        width=w, height=h, mask="auto")
        except Exception as e:
            warn(f"tile image failed {self.img}: {e}")
        c.restoreState()


class Box(Flowable):
    """A drawn panel. The canvas and the story arc are diagrams, not tables, so
    they are drawn rather than assembled out of table cells — it is the only
    way to get the chevrons, the tints and the numbering to line up."""

    def __init__(self, width, height, painter):
        Flowable.__init__(self)
        self.width, self.height, self.painter = width, height, painter

    def draw(self):
        self.painter(self.canv, self.width, self.height)


def wrap_lines(canv, text, font, size, max_w):
    """Greedy wrap against real string widths — reportlab has no measured
    wrapper for raw canvas text, and eyeballed character counts overflow."""
    out, line = [], ""
    for word in str(text or "").split():
        trial = f"{line} {word}".strip()
        if canv.stringWidth(trial, font, size) <= max_w or not line:
            line = trial
        else:
            out.append(line)
            line = word
    if line:
        out.append(line)
    return out


def draw_text_block(canv, text, x, y, w, font, size, leading, color, max_lines=None):
    canv.setFont(font, size)
    canv.setFillColor(color)
    lines = wrap_lines(canv, text, font, size, w)
    if max_lines and len(lines) > max_lines:
        lines = lines[:max_lines]
        lines[-1] = lines[-1][:max(0, len(lines[-1]) - 1)] + "…"
    for i, ln in enumerate(lines):
        canv.drawString(x, y - i * leading, ln)
    return y - (len(lines) - 1) * leading


def est_lines(text, width_pt, size):
    """Lines a string will take at this width. Helvetica averages very close to
    0.5em per character across English prose, which is accurate enough to size
    a panel and far cheaper than a layout pass."""
    if not text:
        return 0
    per_line = max(1, int(width_pt / (0.5 * size)))
    return max(1, -(-len(str(text)) // per_line))


def tracked(canv, x, y, text, font, sizept, color, space):
    """Letter-spaced text. micro-cap is the only tier in the system with
    positive tracking, and reportlab only exposes it on a text object."""
    t = canv.beginText(x, y)
    t.setFont(font, sizept)
    t.setFillColor(color)
    t.setCharSpace(space)
    t.textOut(text)
    canv.drawText(t)


def rounded(canv, x, y, w, h, r, fill=None, stroke=None, lw=1.0, dash=None):
    if fill:
        canv.setFillColor(fill)
    canv.setLineWidth(lw)
    if stroke:
        canv.setStrokeColor(stroke)
    if dash:
        canv.setDash(*dash)
    canv.roundRect(x, y, w, h, r, stroke=1 if stroke else 0, fill=1 if fill else 0)
    canv.setDash()


# ------------------------------------------------------------------ cover

def cover_painter(man, wide):
    """The cover, in the brand's own register.

    DESIGN.md is explicit that the sand canvas is non-negotiable and that light
    is the default — so this is not a dark hero with reversed type. The page is
    sand, the statement sits on a white tile with a hairline border and the
    yellow bar down its left edge, and one yellow chip carries the eyebrow. The
    restraint IS the argument the brand makes.
    """
    def paint(canv, W, H):
        pr = man.get("product", {})
        M = 0.78 * inch

        # The one yellow rule. Everything else on this page is ink on sand.
        canv.setFillColor(YOU)
        canv.rect(0, H - 6, W, 6, stroke=0, fill=1)

        y = H - 1.35 * inch
        # micro-cap eyebrow: 10px, +0.18 tracking, the only uppercase here.
        canv.setFont(F, ts("micro-cap"))
        canv.setFillColor(MUTED)
        tracked(canv, M, y, "POSITIONING", F, ts("micro-cap"), MUTED, 0.18 * PT)
        canv.setFillColor(MUTED)
        canv.setFont(F, ts("caption"))
        canv.drawString(M + 1.15 * inch, y,
                        f"April Dunford's framework   ·   "
                        f"{esc(pr.get('date') or date.today().isoformat())}")

        y -= 0.62 * inch
        canv.setFont(F, ts("display-xl"))
        canv.setFillColor(INK)
        canv.drawString(M, y, short(pr.get("name") or "This product", 40))
        canv.setFont(F, ts("body-md"))
        canv.setFillColor(MUTED)
        canv.drawString(M, y - 0.34 * inch, short(pr.get("url") or "", 90))

        # The statement on a white tile — the system's one depth medium.
        y -= 0.92 * inch
        stmt = man.get("statement") or ""
        if stmt:
            tw = W - 2 * M
            canv.setFont(F, ts("body-lg"))
            lines = wrap_lines(canv, stmt, F, ts("body-lg"), tw - 1.15 * inch)
            ph = len(lines) * tl("body-lg") + 0.86 * inch
            canv.setFillColor(PAPER)
            canv.setStrokeColor(HAIR)
            canv.setLineWidth(1)
            canv.roundRect(M, y - ph, tw, ph, R_LG, stroke=1, fill=1)
            canv.setFillColor(YOU)
            canv.rect(M, y - ph + R_LG * 0.5, 4, ph - R_LG, stroke=0, fill=1)
            canv.setFont(F, ts("micro-cap"))
            canv.setFillColor(MUTED)
            tracked(canv, M + 0.48 * inch, y - 0.40 * inch, "THE POSITION",
                    F, ts("micro-cap"), MUTED, 0.18 * PT)
            canv.setFont(F, ts("body-lg"))
            canv.setFillColor(INK)
            for i, ln in enumerate(lines):
                canv.drawString(M + 0.48 * inch, y - 0.72 * inch - i * tl("body-lg"), ln)

        nums = (man.get("key_numbers") or [])[:4]
        if nums:
            # High enough that two wrapped note lines still clear the footer rule.
            y = 2.46 * inch
            gap = 0.24 * inch
            cw = (W - 2 * M - gap * (len(nums) - 1)) / len(nums)
            for i, n in enumerate(nums):
                x = M + i * (cw + gap)
                canv.setStrokeColor(INK)
                canv.setLineWidth(1)
                canv.line(x, y, x + cw, y)
                canv.setFont(F, ts("display-lg"))
                canv.setFillColor(INK)
                canv.drawString(x, y - 0.46 * inch, short(n.get("value", ""), 9))
                canv.setFont(F, ts("body-sm"))
                canv.setFillColor(INK_SOFT)
                yy = y - 0.68 * inch
                for ln in wrap_lines(canv, n.get("label", ""), F, ts("body-sm"), cw)[:2]:
                    canv.drawString(x, yy, ln)
                    yy -= tl("body-sm")
                if n.get("note"):
                    canv.setFont(F, ts("caption"))
                    canv.setFillColor(MUTED)
                    for ln in wrap_lines(canv, n["note"], F, ts("caption"), cw)[:2]:
                        yy -= tl("caption")
                        canv.drawString(x, yy, ln)

        canv.setStrokeColor(HAIR)
        canv.setLineWidth(1)
        canv.line(M, 0.66 * inch, W - M, 0.66 * inch)
        canv.setFont(F, ts("caption"))
        canv.setFillColor(MUTED)
        canv.drawString(M, 0.44 * inch,
                        "Built from the product's own pages, its alternatives' pages and live "
                        "search data. Every figure traces to a row in the appendix.")
    return paint


# ------------------------------------------------------------- answer page

def answer_height(man, fw):
    cards = [(man.get("answer") or {}).get(k, {}) for k in ("frame", "segment", "wedge")]
    inner = (fw - 0.52 * inch) / 3 - 0.68 * inch
    need = 0
    for d in cards:
        need = max(need, 20.5 * min(est_lines(d.get("name"), inner, 16.5), 3)
                   + 13.2 * min(est_lines(d.get("why"), inner, 9.2), 9))
    return min(6.0 * inch, need + 1.40 * inch)


def answer_painter(man):
    def paint(canv, W, H):
        a = man.get("answer") or {}
        cards = [("COMPETE AS", a.get("frame", {}), INK, YOU_TINT),
                 ("SELL TO", a.get("segment", {}), DIY, DIY_TINT),
                 ("WIN ON", a.get("wedge", {}), RIVAL, RIVAL_TINT)]
        gap = 0.26 * inch
        cw = (W - gap * 2) / 3
        for i, (kick, d, accent, tint) in enumerate(cards):
            x = i * (cw + gap)
            rounded(canv, x, 0, cw, H, 12, fill=tint)
            canv.setFillColor(accent)
            canv.rect(x, H - 5, cw, 5, stroke=0, fill=1)
            canv.setFont(FB, 7.8)
            canv.setFillColor(accent)
            canv.drawString(x + 0.34 * inch, H - 0.46 * inch, kick)
            yy = draw_text_block(canv, d.get("name", "—"), x + 0.34 * inch,
                                 H - 0.86 * inch, cw - 0.68 * inch, FB, 16.5, 20.5, INK,
                                 max_lines=3)
            canv.setStrokeColor(accent)
            canv.setLineWidth(1.0)
            canv.line(x + 0.34 * inch, yy - 0.20 * inch, x + 0.34 * inch + 26, yy - 0.20 * inch)
            draw_text_block(canv, d.get("why", ""), x + 0.34 * inch, yy - 0.44 * inch,
                            cw - 0.68 * inch, F, 9.2, 13.2, INK_SOFT, max_lines=9)
    return paint


# ------------------------------------------------------------ canvas page

def canvas_height(man, fw):
    c = man.get("canvas") or {}
    inner = (fw - 0.60 * inch) / 4 - 0.74 * inch
    rows = 0
    for key in ("alternatives", "attributes", "value", "segments"):
        rows = max(rows, sum(min(est_lines(i, inner, 8.8), 4) for i in (c.get(key) or [])[:6]))
    cells = 0.80 * inch + rows * 12 + len((c.get("alternatives") or [])[:6]) * 3 + 0.30 * inch
    band = 1.30 * inch + (0.26 * inch if c.get("trend") else 0)
    return min(6.1 * inch, max(2.4 * inch, cells) + 0.20 * inch + band)


def canvas_painter(man):
    """April Dunford's positioning canvas — the one artefact the reader will
    photograph and put on a wall, so it is drawn as a single object rather
    than reflowed as text."""
    def paint(canv, W, H):
        c = man.get("canvas") or {}
        cells = [
            ("1", "Competitive alternatives", c.get("alternatives") or [], RIVAL, RIVAL_TINT),
            ("2", "Unique attributes", c.get("attributes") or [], INK, YOU_TINT),
            ("3", "Value for customers", c.get("value") or [], DIY, DIY_TINT),
            ("4", "Who cares a lot", c.get("segments") or [], ADJACENT, SURFACE),
        ]
        gap = 0.20 * inch
        cw = (W - gap * 3) / 4
        band = H - (1.30 * inch + (0.26 * inch if c.get("trend") else 0)) - 0.20 * inch
        top = H
        for i, (num, title, items, accent, tint) in enumerate(cells):
            x = i * (cw + gap)
            rounded(canv, x, top - band, cw, band, 10, fill=tint)
            canv.setFillColor(accent)
            canv.circle(x + 0.30 * inch, top - 0.34 * inch, 8.5, stroke=0, fill=1)
            canv.setFont(FB, 8.5)
            canv.setFillColor(colors.white)
            canv.drawCentredString(x + 0.30 * inch, top - 0.34 * inch - 3, num)
            canv.setFont(FB, 9.2)
            canv.setFillColor(accent)
            canv.drawString(x + 0.50 * inch, top - 0.34 * inch - 3.2, title)
            yy = top - 0.72 * inch
            for it in items[:6]:
                canv.setFillColor(accent)
                canv.circle(x + 0.28 * inch, yy + 3.2, 2.0, stroke=0, fill=1)
                yy = draw_text_block(canv, it, x + 0.44 * inch, yy, cw - 0.74 * inch,
                                     F, 8.8, 12, INK_SOFT, max_lines=4) - 15

        # The frame is the container the other four cells are read inside, so it
        # gets `product-tile-dark` (§ Components) — the spec's one sanctioned
        # inverse-polarity tile — rather than a fifth equal cell.
        y2 = top - band - gap
        h2 = y2
        canv.setFillColor(DARK_TILE)
        canv.roundRect(0, 0, W, h2, R_LG, stroke=0, fill=1)
        canv.setFillColor(YOU)
        canv.circle(0.46 * inch, h2 - 0.38 * inch, 9, stroke=0, fill=1)
        canv.setFont(F, ts("caption"))
        canv.setFillColor(ON_YOU)
        canv.drawCentredString(0.46 * inch, h2 - 0.38 * inch - 3.4, "5")
        tracked(canv, 0.70 * inch, h2 - 0.38 * inch - 3.4,
                "MARKET FRAME  —  THE CONTEXT THAT MAKES ALL OF THE ABOVE OBVIOUS",
                F, ts("micro-cap"), PAPER, 0.18 * PT)
        canv.setFont(F, ts("display-md"))
        canv.setFillColor(PAPER)
        canv.drawString(0.46 * inch, h2 - 0.86 * inch, short(c.get("frame") or "—", 62))
        if c.get("trend"):
            canv.setFont(F, ts("body-sm"))
            draw_text_block(canv, "Trend worth layering on: " + c["trend"],
                            0.46 * inch, h2 - 1.20 * inch, W - 0.92 * inch,
                            F, ts("body-sm"), tl("body-sm"),
                            colors.HexColor("#c9c6c2"), max_lines=2)
    return paint


# ------------------------------------------------------- sales story page

def story_height(man, fw):
    beats = (man.get("sales_story") or [])[:6]
    if not beats:
        return 0
    inner = fw - 1.1 * inch
    h = sum(34 + 16 * min(est_lines(b.get("line"), inner, 12.5), 2) + 12 for b in beats)
    return min(6.1 * inch, h + 0.16 * inch * (len(beats) - 1))


def story_painter(man):
    """The narrative as chevrons: the shape is the argument — each beat only
    makes sense once the one before it has landed, which a bulleted list
    silently lets the reader skip."""
    def paint(canv, W, H):
        beats = (man.get("sales_story") or [])[:6]
        if not beats:
            return
        n = len(beats)
        gap = 0.16 * inch
        bh = (H - gap * (n - 1)) / n
        notch = 0.20 * inch
        for i, b in enumerate(beats):
            y = H - (i + 1) * bh - i * gap
            last = i == n - 1
            accent = INK if last else MUTED
            tint = YOU_TINT if last else SAND
            canv.setFillColor(tint)
            path = canv.beginPath()
            path.moveTo(0, y)
            path.lineTo(W - notch, y)
            path.lineTo(W, y + bh / 2)
            path.lineTo(W - notch, y + bh)
            path.lineTo(0, y + bh)
            path.lineTo(notch * 0.62, y + bh / 2)
            path.close()
            canv.drawPath(path, stroke=0, fill=1)
            canv.setFillColor(accent)
            canv.rect(0, y, 4.5, bh, stroke=0, fill=1)
            canv.setFont(FB, 7.8)
            canv.setFillColor(accent)
            canv.drawString(0.34 * inch, y + bh - 15, str(b.get("beat", "")).upper())
            draw_text_block(canv, b.get("line", ""), 0.34 * inch, y + bh - 34,
                            W - 1.1 * inch, FB if last else F, 12.5, 16,
                            INK if last else INK_SOFT, max_lines=2)
    return paint


# --------------------------------------------------------------- messages

def messages_flow(man, S, width):
    rows = man.get("messages") or []
    if not rows:
        return []
    data = [[Paragraph("WHO", S["tiny"]), Paragraph("WHAT YOU SAY", S["tiny"]),
             Paragraph("WHY THEY BELIEVE IT", S["tiny"])]]
    for r in rows:
        data.append([
            Paragraph(esc(r.get("audience", "")), S["cell"]),
            Paragraph(f'<font size="11">{esc(r.get("line", ""))}</font>', S["cellb"]),
            Paragraph(esc(r.get("proof", "")), S["cell"]),
        ])
    t = Table(data, colWidths=[width * 0.24, width * 0.44, width * 0.32], repeatRows=1)
    t.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 9), ("BOTTOMPADDING", (0, 0), (-1, -1), 9),
        ("LEFTPADDING", (0, 0), (-1, -1), 10), ("RIGHTPADDING", (0, 0), (-1, -1), 10),
        ("LINEBELOW", (0, 0), (-1, 0), 0.8, RULE),
        ("LINEBELOW", (0, 1), (-1, -2), 0.5, HAIR),
        ("BACKGROUND", (1, 1), (1, -1), YOU_TINT),
        ("TEXTCOLOR", (1, 1), (1, -1), INK),
        ("LINEBEFORE", (1, 1), (1, -1), 2.0, YOU),
    ]))
    return [t]


# --------------------------------------------------------------- appendix

def csv_table(run, spec, S, width):
    path = os.path.join(run, spec.get("csv", ""))
    if not os.path.isfile(path):
        warn(f"appendix table missing: {spec.get('csv')}")
        return []
    with open(path, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    if not rows:
        warn(f"appendix table empty: {spec.get('csv')}")
        return []
    cols = [c for c in (spec.get("columns") or list(rows[0])) if c in rows[0]]
    if not cols:
        cols = list(rows[0])[:6]
    limit = spec.get("limit", 28)
    head = [Paragraph(esc(c.replace("_", " ")).upper(), S["tiny"]) for c in cols]
    data = [head]
    for r in rows[:limit]:
        data.append([Paragraph(esc(short(r.get(c, ""), 60)), S["tiny"]) for c in cols])
    t = Table(data, colWidths=[width / len(cols)] * len(cols), repeatRows=1)
    style = [("VALIGN", (0, 0), (-1, -1), "TOP"),
             ("TOPPADDING", (0, 0), (-1, -1), 4), ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
             ("LEFTPADDING", (0, 0), (-1, -1), 6), ("RIGHTPADDING", (0, 0), (-1, -1), 6),
             ("LINEBELOW", (0, 0), (-1, 0), 0.7, RULE),
             ("LINEBELOW", (0, 1), (-1, -2), 0.3, HAIR)]
    for i in range(1, len(data)):
        if i % 2 == 0:
            style.append(("BACKGROUND", (0, i), (-1, i), SAND))
    t.setStyle(TableStyle(style))
    out = [Paragraph(esc(spec.get("title", os.path.basename(path))), S["h2"]), t]
    if len(rows) > limit:
        out.append(Spacer(1, 4))
        out.append(Paragraph(f"{len(rows):,} rows in total; the first {limit} are shown. "
                             f"Full table: {esc(spec['csv'])}", S["tiny"]))
    return out


# ------------------------------------------------------------------- doc

def make_doc(path, man, wide):
    page = landscape(letter) if wide else letter
    M = 0.62 * inch
    TOP, BOT = 0.62 * inch, 0.62 * inch
    W, H = page

    def furniture(canv, doc):
        if getattr(doc, "_is_cover", False):
            return
        canv.saveState()
        canv.setStrokeColor(HAIR)
        canv.setLineWidth(0.5)
        canv.line(M, 0.44 * inch, W - M, 0.44 * inch)
        canv.setFont(F, 7)
        canv.setFillColor(FAINT)
        name = short((man.get("product") or {}).get("name") or "Positioning", 46)
        canv.drawString(M, 0.28 * inch, f"{name} · positioning")
        canv.setFont(FB, 7.5)
        canv.setFillColor(MUTED)
        canv.drawRightString(W - M, 0.28 * inch, str(doc.page))
        canv.restoreState()

    def sand(canv):
        canv.saveState()
        canv.setFillColor(SAND)
        canv.rect(0, 0, W, H, stroke=0, fill=1)
        canv.restoreState()

    def cover_art(canv, doc):
        doc._is_cover = True
        sand(canv)

    def content(canv, doc):
        doc._is_cover = False
        sand(canv)

    doc = BaseDocTemplate(path, pagesize=page, title=f"Positioning — "
                          f"{(man.get('product') or {}).get('name', '')}",
                          author="positioning", leftMargin=M, rightMargin=M,
                          topMargin=TOP, bottomMargin=BOT)
    fw, fh = W - 2 * M, H - TOP - BOT
    pad = dict(leftPadding=0, rightPadding=0, topPadding=0, bottomPadding=0)
    doc.addPageTemplates([
        PageTemplate(id="cover", frames=[Frame(M, BOT, fw, fh, id="c", **pad)],
                     onPage=cover_art),
        PageTemplate(id="main", frames=[Frame(M, BOT + 0.16 * inch, fw,
                                              fh - 0.16 * inch, id="m", **pad)],
                     onPage=content, onPageEnd=furniture),
    ])
    doc._frame_w, doc._frame_h = fw, fh
    return doc


def chart_image(run, name, max_w, max_h):
    path = os.path.join(run, "charts", f"{name}.png")
    if not os.path.isfile(path):
        return None
    try:
        iw, ih = ImageReader(path).getSize()
    except Exception as e:
        warn(f"unreadable chart {name}: {e}")
        return None
    scale = min(max_w / iw, max_h / ih)
    return Image(path, width=iw * scale, height=ih * scale)


def build(run, out, wide, man):
    S = styles(wide)
    doc = make_doc(out, man, wide)
    fw, fh = doc._frame_w, doc._frame_h - 0.16 * inch
    story = []

    # 1 — cover
    story += [Box(fw, fh + 0.16 * inch, cover_painter(man, wide)),
              NextPageTemplate("main"), PageBreak()]

    # 2 — the answer, three cards
    if man.get("answer"):
        story += [Paragraph("THE SHORT VERSION", S["kicker"]),
                  Paragraph("Three decisions, and the evidence behind each", S["h1"]),
                  Spacer(1, 12),
                  Box(fw, answer_height(man, fw), answer_painter(man)),
                  PageBreak()]

    # 3-10 — one page per step, one picture each
    used = []
    for name, step, title, note_key in SPREADS:
        path = os.path.join(run, "charts", f"{name}.png")
        if not os.path.isfile(path):
            warn(f"chart not rendered, page skipped: {name}")
            continue
        used.append(name)
        note = (man.get("notes") or {}).get(note_key) or man.get(note_key)
        # Leave room for the "so what" line beneath the tile when there is one.
        tile_h = fh - (1.55 if note else 0.85) * inch
        page = [Paragraph(f"{step.upper()} &nbsp;·&nbsp; {esc(title).upper()}", S["kicker"]),
                Spacer(1, 10), Tile(path, fw, tile_h)]
        if note:
            page += [Spacer(1, 14), Paragraph(esc(note), S["sowhat"])]
        story += page + [PageBreak()]

    # 11 — the canvas
    if man.get("canvas"):
        story += [Paragraph("THE POSITIONING CANVAS", S["kicker"]),
                  Paragraph("Everything above, on one page", S["h1"]),
                  Spacer(1, 12),
                  Box(fw, canvas_height(man, fw), canvas_painter(man)),
                  PageBreak()]

    # 12 — the sales story
    if man.get("sales_story"):
        story += [Paragraph("THE SALES STORY", S["kicker"]),
                  Paragraph("The order the argument has to arrive in", S["h1"]),
                  Spacer(1, 12),
                  Box(fw, story_height(man, fw), story_painter(man)),
                  PageBreak()]

    # 13 — messaging
    msg = messages_flow(man, S, fw)
    if msg:
        story += [Paragraph("MESSAGING", S["kicker"]),
                  Paragraph("What to say, to whom, and what makes it credible", S["h1"]),
                  Spacer(1, 14)] + msg + [PageBreak()]

    # 14+ — appendix
    tables = man.get("appendix_tables") or []
    if tables:
        story += [Paragraph("APPENDIX", S["kicker"]),
                  Paragraph("The evidence", S["h1"]),
                  Paragraph("Every figure in this report comes from these rows.", S["deck"]),
                  Spacer(1, 8)]
        for spec in tables:
            flows = csv_table(run, spec, S, fw)
            if flows:
                story += flows + [Spacer(1, 20)]
    src = man.get("sources") or []
    if src:
        story += [Spacer(1, 10), Paragraph("Where this came from", S["h2"])]
        for s in src:
            story.append(Paragraph(f"{esc(s.get('what',''))} — {esc(s.get('where',''))}",
                                   S["tiny"]))
            story.append(Spacer(1, 3))

    while story and isinstance(story[-1], PageBreak):
        story.pop()
    doc.build(story)
    return used


def report_card(run, man, used, out):
    """A build that quietly drops half its pages looks identical to a good one
    from the outside. This is the difference, printed."""
    all_charts = {n for n, *_ in SPREADS}
    rendered = {os.path.splitext(f)[0] for f in os.listdir(os.path.join(run, "charts"))
                if f.endswith(".png")} if os.path.isdir(os.path.join(run, "charts")) else set()
    print("\n" + "─" * 62)
    print(f"REPORT CARD  ·  {os.path.relpath(out)}")
    print("─" * 62)
    print(f"  step pages built     {len(used)}/8   ({', '.join(used) or 'none'})")
    missing = sorted(all_charts - rendered)
    if missing:
        print(f"  charts never rendered  {', '.join(missing)}")
        print("                         → fill that manifest section, re-run charts.py")
    orphan = sorted(rendered - all_charts)
    if orphan:
        print(f"  charts not placed      {', '.join(orphan)}")
    for key, label in (("statement", "positioning statement"), ("answer", "the answer page"),
                       ("canvas", "positioning canvas"), ("sales_story", "sales story"),
                       ("messages", "messaging table"), ("appendix_tables", "appendix")):
        if not man.get(key):
            print(f"  missing                {label}")
    notes = man.get("notes") or {}
    n_notes = sum(1 for _, _, _, k in SPREADS if notes.get(k))
    print(f"  'so what' lines      {n_notes}/8")
    if WARN_LOG:
        print(f"  warnings             {len(WARN_LOG)}")
    print("─" * 62)


def main():
    p = argparse.ArgumentParser(description="build the positioning PDF")
    p.add_argument("--run", required=True)
    p.add_argument("--manifest")
    p.add_argument("--out")
    p.add_argument("--portrait", action="store_true",
                   help="portrait letter (default is landscape — the charts are wide)")
    p.add_argument("--strict", action="store_true", help="exit non-zero if anything warned")
    a = p.parse_args()

    mpath = a.manifest or os.path.join(a.run, "report-manifest.json")
    if not os.path.isfile(mpath):
        print(f"error: no manifest at {mpath}\nfix:   make_manifest.py --run {a.run}",
              file=sys.stderr)
        sys.exit(3)
    with open(mpath, encoding="utf-8") as f:
        man = json.load(f)
    out = a.out or os.path.join(a.run, "report.pdf")
    used = build(a.run, out, not a.portrait, man)
    report_card(a.run, man, used, out)
    print(f"\nwrote {out}")
    if a.strict and WARN_LOG:
        sys.exit(1)


if __name__ == "__main__":
    main()
