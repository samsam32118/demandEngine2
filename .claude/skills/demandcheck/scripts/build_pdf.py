#!/usr/bin/env python3
"""build_pdf.py — assemble the demandcheck report PDF from the run directory.

Inputs (all inside --run):
  report-manifest.json   written by the analyst (schema: references/report-spec.md)
  charts/*.png           written by eda_charts.py
  clean/*.csv            the canonical tables (evidence + full appendix)
  creatives/**/*.png     the downloaded ad creatives (rendered as evidence)
  state.json             budget ledger for the reproducibility page

Output: <run>/report.pdf — cover with the verdict and the headline numbers,
contents, executive summary, chapters built from an ordered block list
(prose, key numbers, callouts, pull-quotes, charts, tables, ad-creative
exhibits), the explanations, what would change the verdict, a plain-words
methodology page, a glossary, the full ad-creative evidence gallery, the
full data appendix, and the ledger.

Needs reportlab; Pillow (comes with matplotlib's install) is used to
downscale creative images so a 300-ad gallery stays a reasonable file size:
    python3 -m pip install matplotlib reportlab pillow

The builder never fails on missing material: a missing chart, image or table
is skipped with a warning, and the run's report card at the end of the build
says exactly what the manifest left on the table.
"""

import argparse
import csv
import glob
import json
import os
import re
import sys

try:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import letter, landscape
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import inch
    from reportlab.lib.utils import ImageReader
    from reportlab.platypus import (
        BaseDocTemplate, Frame, Image, KeepTogether, LongTable, NextPageTemplate,
        PageBreak, PageTemplate, Paragraph, Spacer, Table, TableStyle,
    )
    from reportlab.platypus.tableofcontents import TableOfContents
except ImportError:
    print("error: reportlab is not installed.\n"
          "fix:   python3 -m pip install matplotlib reportlab pillow", file=sys.stderr)
    sys.exit(3)

try:
    from PIL import Image as PILImage
except ImportError:  # thumbnails become a no-op; the PDF just gets heavier
    PILImage = None


# --------------------------------------------------------------- design tokens

INK = colors.HexColor("#14161c")
INK_SOFT = colors.HexColor("#3d424e")
MUTED = colors.HexColor("#6b7280")
FAINT = colors.HexColor("#9aa1ad")
RULE = colors.HexColor("#dfe3e8")
HAIR = colors.HexColor("#eef0f3")
SURFACE = colors.HexColor("#f7f8fa")
PAPER = colors.HexColor("#ffffff")

# Categorical hues validated for colour-vision deficiency at all pairs
# (dataviz skill, scripts/validate_palette.js): blue / violet / aqua / orange.
ACCENT = colors.HexColor("#2a78d6")
ACCENT_DK = colors.HexColor("#1c5cab")
ACCENT_TINT = colors.HexColor("#eaf2fd")
CLASS_COLORS = {
    "direct": colors.HexColor("#2a78d6"),
    "indirect": colors.HexColor("#4a3aa7"),
    "latent": colors.HexColor("#1baf7a"),
    "urgent": colors.HexColor("#eb6834"),
    "unclear": colors.HexColor("#9aa1ad"),
}
GOOD = colors.HexColor("#1baf7a")
WARN = colors.HexColor("#eb6834")
COVER_BG = colors.HexColor("#0f1218")
COVER_PANEL = colors.HexColor("#191e28")
COVER_RULE = colors.HexColor("#2b3240")
COVER_TEXT = colors.HexColor("#ffffff")
COVER_MUTED = colors.HexColor("#9aa3b2")
COVER_ACCENT = colors.HexColor("#6ba8f0")
WARN_TINT = colors.HexColor("#fdf0e9")
GOOD_TINT = colors.HexColor("#e9f7f1")

FONT = "Helvetica"
FONT_B = "Helvetica-Bold"
FONT_I = "Helvetica-Oblique"

PAGE = letter
MARGIN = 0.85 * inch
TOP_MARGIN = 0.95 * inch
BOT_MARGIN = 0.85 * inch
BODY_W = PAGE[0] - 2 * MARGIN
WIDE_PAGE = landscape(letter)
WIDE_MARGIN = 0.5 * inch
WIDE_W = WIDE_PAGE[0] - 2 * WIDE_MARGIN

COVER_FOOT = (
    "Every figure in this report is measured, dated and listed in full at the "
    "back. The advertising shown is live and reproduced exactly as it runs."
)

CALLOUT_KINDS = {
    # variant: (background, left-rule colour, default title)
    "takeaway": (ACCENT_TINT, ACCENT, "The takeaway"),
    "plain": (SURFACE, INK_SOFT, "In plain English"),
    "evidence": (PAPER, ACCENT, "The evidence"),
    "watch-out": (WARN_TINT, WARN, "Worth knowing"),
    "good-news": (GOOD_TINT, GOOD, "What is working"),
}

NUMERIC_RE = re.compile(r"^[\s\-+]?[$€£]?\s?-?[\d,]+(\.\d+)?\s?[%x×]?$")


# -------------------------------------------------------------------- helpers

def esc(text) -> str:
    return (str(text if text is not None else "")
            .replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))


def track(text: str) -> str:
    """Letter-spaced eyebrow text (base-14 fonts give no charSpace control).

    Long labels are left alone — tracking a whole phrase hurts more than it
    helps, and the word gap needs a non-breaking pair or Paragraph eats it.
    """
    text = esc(text).upper()
    if len(text) > 20:
        return text
    return "&#160;".join(text).replace("&#160; &#160;", "&#160;&#160;&#160;")


def anchor_for(text) -> str:
    """Stable in-document link target for a heading."""
    slug = re.sub(r"[^a-z0-9]+", "-", str(text).lower()).strip("-")
    return f"sec-{slug[:48] or 'section'}"


def link_to(target, label, styles):
    """A clickable cross-reference paragraph — used to point at the appendices."""
    return Paragraph(
        f'<a href="#{anchor_for(target)}" color="#1c5cab">{esc(label)} →</a>',
        styles["link"])


def is_numeric(v) -> bool:
    v = str(v or "").strip()
    return bool(v) and bool(NUMERIC_RE.match(v))


def fnum(v):
    """Float from a messy cell; None when it isn't a number."""
    s = str(v or "").strip().replace("$", "").replace(",", "")
    try:
        return float(s)
    except ValueError:
        return None


def fmt_int(v):
    n = fnum(v)
    return f"{n:,.0f}" if n is not None else (str(v or ""))


def fmt_usd(v, places=2):
    n = fnum(v)
    return f"${n:,.{places}f}" if n is not None else (str(v or ""))


def warn(msg):
    print(f"warning: {msg}", file=sys.stderr)


# ---------------------------------------------------------------- run loaders

def read_csv_rows(path):
    if not os.path.isfile(path):
        return []
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


class RunData:
    """Everything the builder reads out of the run directory besides the manifest."""

    def __init__(self, run):
        self.run = run
        self.ads = read_csv_rows(os.path.join(run, "clean", "ads.csv"))
        self.copy = read_csv_rows(os.path.join(run, "clean", "ad_copy.csv"))
        self.keywords = read_csv_rows(os.path.join(run, "clean", "keywords.csv"))
        self.copy_by_id = {}
        for r in self.copy:
            cid = (r.get("creative_id") or "").strip()
            if cid:
                self.copy_by_id[cid] = r
        self.ads_by_id = {}
        for r in self.ads:
            cid = (r.get("creative_id") or "").strip()
            if cid:
                self.ads_by_id[cid] = r
        if not self.ads:
            self._recover_ads_from_disk()
        self.creatives_shown = set()
        self._thumbs = {}

    def _recover_ads_from_disk(self):
        """No ads.csv (or an empty one) — fall back to the downloaded PNGs.

        Evidence that exists on disk should reach the reader even when the
        cleaner never wrote the table for it.
        """
        for png in sorted(glob.glob(os.path.join(self.run, "creatives", "*", "*.png"))):
            cid = os.path.splitext(os.path.basename(png))[0]
            advertiser = os.path.basename(os.path.dirname(png))
            self.ads_by_id.setdefault(cid, {
                "creative_id": cid, "advertiser_title": advertiser,
                "png_path": os.path.relpath(png, self.run),
            })
        self.ads = list(self.ads_by_id.values())
        if self.ads:
            warn(f"clean/ads.csv missing or empty — recovered "
                 f"{len(self.ads)} creatives from creatives/ on disk")

    # -- creative images ---------------------------------------------------

    def png_for(self, row):
        """Absolute path to a creative's PNG, or None."""
        cid = (row.get("creative_id") or "").strip()
        cand = (row.get("png_path") or "").strip()
        tries = []
        if cand:
            tries += [cand if os.path.isabs(cand) else os.path.join(self.run, cand)]
        if cid:
            tries += glob.glob(os.path.join(self.run, "creatives", "*", f"{cid}.*"))
        for t in tries:
            if os.path.isfile(t) and os.path.splitext(t)[1].lower() in (
                    ".png", ".jpg", ".jpeg", ".gif"):
                return t
        return None

    def thumb(self, path, max_px):
        """Downscaled copy of an image, cached under <run>/.thumbs/."""
        if PILImage is None or not max_px:
            return path
        if path in self._thumbs:
            return self._thumbs[path]
        out = path
        try:
            with PILImage.open(path) as im:
                if max(im.size) > max_px:
                    d = os.path.join(self.run, ".thumbs")
                    os.makedirs(d, exist_ok=True)
                    key = re.sub(r"[^A-Za-z0-9._-]", "_",
                                 os.path.relpath(path, self.run))
                    out = os.path.join(d, f"{max_px}-{key}.png")
                    if not os.path.isfile(out):
                        im2 = im.convert("RGB")
                        im2.thumbnail((max_px, max_px), PILImage.LANCZOS)
                        im2.save(out, "PNG", optimize=True)
        except Exception as e:  # a corrupt PNG must not kill the report
            warn(f"could not downscale {os.path.basename(path)}: {e}")
            out = path
        self._thumbs[path] = out
        return out

    # -- creative selection ------------------------------------------------

    def creative_rows(self, ids=None, advertiser=None, select="longest",
                      limit=None, require_image=True, require_copy=False):
        rows = []
        if ids:
            for cid in ids:
                r = self.ads_by_id.get(str(cid).strip())
                if r:
                    rows.append(r)
                else:
                    warn(f"creative id not in clean/ads.csv, skipped: {cid}")
        else:
            rows = list(self.ads)
        if advertiser:
            needle = advertiser.strip().lower()
            rows = [r for r in rows
                    if needle in (r.get("advertiser_title") or "").lower()
                    or needle in (r.get("advertiser_id") or "").lower()]
        if require_image:
            rows = [r for r in rows if self.png_for(r)]
        if require_copy:
            rows = [r for r in rows if self.headline_of(r)]
        if not ids:  # explicit id lists keep the analyst's order
            if select == "active":
                rows.sort(key=lambda r: (
                    (r.get("active") or "").lower() not in ("true", "1", "yes"),
                    -(fnum(r.get("days_running")) or 0)))
            elif select == "recent":
                rows.sort(key=lambda r: (r.get("last_shown") or ""), reverse=True)
            else:  # "longest" — the proven set first, which is what earns space
                rows.sort(key=lambda r: -(fnum(r.get("days_running")) or 0))
        return rows[:limit] if limit else rows

    def headline_of(self, row):
        c = self.copy_by_id.get((row.get("creative_id") or "").strip(), {})
        h = (c.get("headline") or "").strip()
        return "" if h.upper() == "ILLEGIBLE" else h

    def copy_of(self, row):
        return self.copy_by_id.get((row.get("creative_id") or "").strip(), {})


# ------------------------------------------------------------------- styles

def build_styles():
    base = getSampleStyleSheet()
    s = {}

    def st(name, parent, **kw):
        s[name] = ParagraphStyle(name, parent=parent, **kw)
        return s[name]

    body = st("body", base["Normal"], fontName=FONT, fontSize=10, leading=15.2,
              textColor=INK_SOFT, spaceAfter=8)
    st("body_ink", body, textColor=INK)
    st("lead", body, fontSize=11.5, leading=17.5, textColor=INK, spaceAfter=10)
    st("bullet", body, leftIndent=15, bulletIndent=3, spaceAfter=5)
    st("eyebrow", base["Normal"], fontName=FONT_B, fontSize=7, leading=10,
       textColor=ACCENT, spaceAfter=4)
    st("eyebrow_muted", s["eyebrow"], textColor=FAINT)

    st("cover_title", base["Title"], fontName=FONT_B, fontSize=34, leading=38,
       textColor=COVER_TEXT, alignment=0, spaceAfter=0)
    st("cover_seed", base["Normal"], fontName=FONT, fontSize=12.5, leading=18,
       textColor=COVER_MUTED, spaceBefore=10)
    st("cover_meta", base["Normal"], fontName=FONT, fontSize=8.5, leading=14,
       textColor=COVER_MUTED)
    st("cover_eyebrow", base["Normal"], fontName=FONT_B, fontSize=7, leading=10,
       textColor=COVER_ACCENT, spaceAfter=6)
    st("verdict_label", base["Normal"], fontName=FONT_B, fontSize=7,
       leading=10, textColor=COVER_ACCENT, spaceAfter=6)
    st("verdict", base["Normal"], fontName=FONT, fontSize=15, leading=21,
       textColor=COVER_TEXT)
    st("cover_stat_value", base["Normal"], fontName=FONT_B, fontSize=19,
       leading=22, textColor=COVER_TEXT)
    st("cover_stat_label", base["Normal"], fontName=FONT_B, fontSize=6.5,
       leading=9, textColor=COVER_ACCENT, spaceBefore=4)
    st("cover_stat_note", base["Normal"], fontName=FONT, fontSize=7.5,
       leading=10, textColor=COVER_MUTED, spaceBefore=2)
    st("cover_strip", base["Normal"], fontName=FONT_B, fontSize=6.5, leading=9,
       textColor=COVER_MUTED, spaceAfter=6)
    st("cover_card", base["Normal"], fontName=FONT, fontSize=5.8, leading=7.5,
       textColor=MUTED)

    # h1 feeds the table of contents; h1_plain has the same look without an entry
    st("h1", base["Heading1"], fontName=FONT_B, fontSize=19, leading=23,
       textColor=INK, spaceBefore=4, spaceAfter=4, keepWithNext=1)
    st("h1_plain", s["h1"])
    st("h1_sub", s["h1"], fontSize=15, leading=19, spaceBefore=2)
    st("h2", base["Heading2"], fontName=FONT_B, fontSize=12, leading=15.5,
       textColor=INK, spaceBefore=14, spaceAfter=4, keepWithNext=1)
    st("h3", s["h2"], fontSize=10, leading=13, textColor=ACCENT_DK,
       spaceBefore=10, spaceAfter=2)
    st("deck", base["Normal"], fontName=FONT, fontSize=11, leading=16,
       textColor=MUTED, spaceBefore=2, spaceAfter=2)

    st("caption", base["Normal"], fontName=FONT, fontSize=8, leading=11.5,
       textColor=MUTED, spaceBefore=3, spaceAfter=14)
    st("note", s["caption"], spaceAfter=8)

    st("quote", base["Normal"], fontName=FONT_B, fontSize=15, leading=21,
       textColor=INK)
    st("quote_attr", base["Normal"], fontName=FONT, fontSize=8.5, leading=12,
       textColor=MUTED, spaceBefore=6)

    st("stat_value", base["Normal"], fontName=FONT_B, fontSize=17, leading=20,
       textColor=INK)
    st("stat_label", base["Normal"], fontName=FONT_B, fontSize=6.5, leading=9,
       textColor=ACCENT_DK, spaceBefore=3)
    st("stat_note", base["Normal"], fontName=FONT, fontSize=7.5, leading=10,
       textColor=MUTED, spaceBefore=2)

    st("callout_title", base["Normal"], fontName=FONT_B, fontSize=7.5,
       leading=11, textColor=INK, spaceAfter=4)
    st("callout_body", body, fontSize=9.5, leading=14.5, textColor=INK,
       spaceAfter=0)

    st("cell", base["Normal"], fontName=FONT, fontSize=8, leading=11,
       textColor=INK_SOFT)
    st("cell_r", s["cell"], alignment=2)
    st("cell_head", s["cell"], fontName=FONT_B, fontSize=7, textColor=INK)
    st("cell_head_r", s["cell_head"], alignment=2)
    st("cell_tiny", s["cell"], fontSize=6.2, leading=8)
    st("cell_tiny_head", s["cell_tiny"], fontName=FONT_B, textColor=INK)

    st("card_adv", base["Normal"], fontName=FONT_B, fontSize=8, leading=11,
       textColor=INK)
    st("card_head", base["Normal"], fontName=FONT_B, fontSize=8.5, leading=11.5,
       textColor=INK, spaceBefore=3)
    st("card_desc", base["Normal"], fontName=FONT, fontSize=7.5, leading=10.5,
       textColor=INK_SOFT, spaceBefore=2)
    st("card_meta", base["Normal"], fontName=FONT, fontSize=6.5, leading=9,
       textColor=FAINT, spaceBefore=3)
    st("card_flag", base["Normal"], fontName=FONT_B, fontSize=6.5, leading=9,
       textColor=ACCENT_DK)

    st("link", body, textColor=ACCENT_DK, fontSize=8.5, leading=12,
       spaceBefore=2, spaceAfter=12)
    st("rank_num", base["Normal"], fontName=FONT_B, fontSize=22, leading=24,
       textColor=PAPER, alignment=1)
    st("path_name", base["Normal"], fontName=FONT_B, fontSize=12.5, leading=16,
       textColor=INK, spaceAfter=3)
    st("path_body", body, fontSize=9.5, leading=14, spaceAfter=5)
    st("path_label", base["Normal"], fontName=FONT_B, fontSize=6.5, leading=9,
       textColor=ACCENT_DK, spaceBefore=4, spaceAfter=1)
    st("beat_num", base["Normal"], fontName=FONT_B, fontSize=20, leading=22,
       textColor=ACCENT)
    st("beat_head", base["Normal"], fontName=FONT_B, fontSize=9.5, leading=13,
       textColor=INK, spaceBefore=5)
    st("beat_body", base["Normal"], fontName=FONT, fontSize=8.5, leading=12.5,
       textColor=INK_SOFT, spaceBefore=3)
    st("kind_name", base["Normal"], fontName=FONT_B, fontSize=10.5, leading=14,
       textColor=INK)
    st("kind_def", base["Normal"], fontName=FONT, fontSize=9, leading=13,
       textColor=INK, spaceBefore=3)
    st("kind_stat", base["Normal"], fontName=FONT_B, fontSize=8, leading=11.5,
       textColor=INK_SOFT, spaceBefore=6)
    st("kind_eg", base["Normal"], fontName=FONT, fontSize=8, leading=11.5,
       textColor=MUTED, spaceBefore=2)
    st("kind_means", base["Normal"], fontName=FONT, fontSize=8.5, leading=12.5,
       textColor=INK_SOFT, spaceBefore=6)
    st("toc0", base["Normal"], fontName=FONT_B, fontSize=10, leading=17,
       textColor=INK)
    st("toc1", base["Normal"], fontName=FONT, fontSize=9, leading=14,
       textColor=MUTED, leftIndent=16)
    return s


# --------------------------------------------------------------- page furniture

class ReportDoc(BaseDocTemplate):
    """Feeds headings into the contents, the PDF bookmarks and the running head."""

    section_title = ""

    def afterFlowable(self, flowable):
        if not isinstance(flowable, Paragraph):
            return
        name = flowable.style.name
        if name not in ("h1", "h1_sub"):
            return
        text = flowable.getPlainText()
        level = 0 if name == "h1" else 1
        if level == 0:
            self.section_title = text
        key = anchor_for(text)
        self.canv.bookmarkPage(key)                 # PDF sidebar outline
        self.canv.addOutlineEntry(text, key, level=level, closed=False)
        self.notify("TOCEntry", (level, text, self.page, key))   # clickable entry

    def beforeDocument(self):
        # multiBuild runs the whole story more than once to settle the contents;
        # without this reset the running head starts each pass on the last
        # section of the previous one.
        self.section_title = ""
        self.canv.showOutline()


def make_doc(path, title, subject, running_title):
    def furniture(canv, doc):
        """Header and footer, drawn at page end so the running head is current."""
        if doc.page == 1:
            return
        canv.saveState()
        w, h = canv._pagesize          # doc.pagesize lags behind on template flips
        left = WIDE_MARGIN if w > h else MARGIN
        right = w - left
        top = h - (0.52 * inch)
        canv.setFont(FONT, 7)
        canv.setFillColor(FAINT)
        canv.drawString(left, top, running_title)
        section = (doc.section_title or "")[:70]
        canv.drawRightString(right, top, section)
        canv.setStrokeColor(HAIR)
        canv.setLineWidth(0.5)
        canv.line(left, top - 5, right, top - 5)
        y = 0.5 * inch
        canv.setFillColor(FAINT)
        canv.drawString(left, y, "DemandCheck")
        canv.setFont(FONT_B, 7.5)
        canv.setFillColor(MUTED)
        canv.drawRightString(right, y, str(doc.page))
        canv.restoreState()

    def cover_art(canv, doc):
        """Full-bleed dark cover: the report should look like what it cost."""
        canv.saveState()
        w, h = canv._pagesize
        canv.setFillColor(COVER_BG)
        canv.rect(0, 0, w, h, stroke=0, fill=1)
        canv.setFillColor(ACCENT)
        canv.rect(0, h - 0.22 * inch, w, 0.22 * inch, stroke=0, fill=1)
        canv.setStrokeColor(COVER_RULE)
        canv.setLineWidth(0.5)
        canv.line(MARGIN, 0.78 * inch, w - MARGIN, 0.78 * inch)
        canv.setFont(FONT, 7)
        canv.setFillColor(COVER_MUTED)
        canv.drawString(MARGIN, 0.58 * inch, COVER_FOOT)
        canv.restoreState()

    doc = ReportDoc(path, pagesize=PAGE, title=title, author="demandcheck",
                    subject=subject, leftMargin=MARGIN, rightMargin=MARGIN,
                    topMargin=TOP_MARGIN, bottomMargin=BOT_MARGIN)
    cover_frame = Frame(MARGIN, BOT_MARGIN, BODY_W,
                        PAGE[1] - TOP_MARGIN - BOT_MARGIN, id="cover")
    main_frame = Frame(MARGIN, BOT_MARGIN, BODY_W,
                       PAGE[1] - TOP_MARGIN - BOT_MARGIN, id="main")
    wide_frame = Frame(WIDE_MARGIN, WIDE_MARGIN + 10, WIDE_W,
                       WIDE_PAGE[1] - WIDE_MARGIN - 0.75 * inch, id="wide")
    doc.addPageTemplates([
        PageTemplate(id="cover", frames=[cover_frame], onPage=cover_art),
        PageTemplate(id="main", frames=[main_frame], onPageEnd=furniture),
        PageTemplate(id="wide", frames=[wide_frame], onPageEnd=furniture,
                     pagesize=WIDE_PAGE),
    ])
    return doc


# ------------------------------------------------------------ block renderers

def rule(color=RULE, width=BODY_W, thickness=0.5, space_before=0, space_after=8):
    t = Table([[""]], colWidths=[width], rowHeights=[0.1])
    t.setStyle(TableStyle([
        ("LINEABOVE", (0, 0), (-1, 0), thickness, color),
        ("TOPPADDING", (0, 0), (-1, -1), space_before),
        ("BOTTOMPADDING", (0, 0), (-1, -1), space_after),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
    ]))
    return t


def section_opener(styles, title, kicker=None, deck=None, width=BODY_W):
    """A chapter/section opener: eyebrow, title (goes in the contents), deck."""
    out = []
    if kicker:
        out.append(Paragraph(track(kicker), styles["eyebrow"]))
    out.append(Paragraph(esc(title), styles["h1"]))
    if deck:
        out.append(Paragraph(esc(deck), styles["deck"]))
    out.append(rule(RULE, width, 0.75, 8, 16))
    return [KeepTogether(out)]


def para_block(styles, block):
    text = block.get("text") or block.get("body") or ""
    if not text:
        return []
    style = styles["lead"] if block.get("lead") else styles["body"]
    return [Paragraph(esc(text), style)]


def bullets_block(styles, block):
    items = block.get("items") or block.get("bullets") or []
    return [Paragraph(esc(i), styles["bullet"], bulletText="—") for i in items]


def stats_block(styles, block, width=BODY_W, dark=False):
    """A row of headline numbers. The reader's eye lands here first."""
    items = [i for i in (block.get("items") or []) if i.get("value")]
    if not items:
        return []
    items = items[:5]
    n = len(items)
    sv = styles["cover_stat_value" if dark else "stat_value"]
    sl = styles["cover_stat_label" if dark else "stat_label"]
    sn = styles["cover_stat_note" if dark else "stat_note"]
    cells = []
    for it in items:
        inner = [Paragraph(esc(it["value"]), sv),
                 Paragraph(esc(it.get("label", "")).upper(), sl)]
        if it.get("note"):
            inner.append(Paragraph(esc(it["note"]), sn))
        cells.append(inner)
    col_w = width / n
    t = Table([cells], colWidths=[col_w] * n, hAlign="LEFT")
    style = [
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING", (0, 0), (-1, -1), 11),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 12),
        ("LEFTPADDING", (0, 0), (-1, -1), 11),
        ("RIGHTPADDING", (0, 0), (-1, -1), 8),
        ("BACKGROUND", (0, 0), (-1, -1), COVER_PANEL if dark else SURFACE),
        ("LINEABOVE", (0, 0), (-1, 0), 2, ACCENT),
    ]
    for i in range(1, n):
        style.append(("LINEBEFORE", (i, 0), (i, 0), 0.5,
                      COVER_RULE if dark else RULE))
    t.setStyle(TableStyle(style))
    out = [t]
    if block.get("caption"):
        out.append(Paragraph(esc(block["caption"]), styles["caption"]))
    else:
        out.append(Spacer(1, 14))
    return [KeepTogether(out)]


def callout_block(styles, block, width=BODY_W):
    variant = (block.get("variant") or "takeaway").lower()
    bg, bar, default_title = CALLOUT_KINDS.get(variant, CALLOUT_KINDS["takeaway"])
    title = block.get("title", default_title)
    text = block.get("text") or ""
    if not text:
        return []
    inner = []
    if title:
        inner.append(Paragraph(esc(title).upper(), styles["callout_title"]))
    inner.append(Paragraph(esc(text), styles["callout_body"]))
    t = Table([[inner]], colWidths=[width], hAlign="LEFT")
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), bg),
        ("LINEBEFORE", (0, 0), (0, -1), 2.5, bar),
        ("BOX", (0, 0), (-1, -1), 0.25, RULE if bg == PAPER else bg),
        ("LEFTPADDING", (0, 0), (-1, -1), 12),
        ("RIGHTPADDING", (0, 0), (-1, -1), 12),
        ("TOPPADDING", (0, 0), (-1, -1), 10),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 11),
    ]))
    return [KeepTogether([Spacer(1, 2), t, Spacer(1, 14)])]


def quote_block(styles, block, data, width=BODY_W):
    """A pull-quote. With a creative_id it fills itself from the ad copy."""
    text = (block.get("text") or "").strip()
    attr = (block.get("attribution") or "").strip()
    cid = (block.get("creative_id") or "").strip()
    thumb_flow = []
    if cid:
        row = data.ads_by_id.get(cid)
        if not row:
            warn(f"quote references unknown creative {cid} — skipped")
            return []
        cp = data.copy_of(row)
        text = text or (cp.get("headline") or "").strip()
        if not text or text.upper() == "ILLEGIBLE":
            warn(f"quote creative {cid} has no legible headline — skipped")
            return []
        if not attr:
            attr = creative_attribution(row)
        data.creatives_shown.add(cid)
        png = data.png_for(row)
        if png and block.get("show_image", True):
            thumb_flow = [fitted_image(data, png, 1.5 * inch, 1.1 * inch)]
    if not text:
        return []
    body = [Paragraph("“" + esc(text) + "”", styles["quote"])]
    if attr:
        body.append(Paragraph(esc(attr), styles["quote_attr"]))
    if thumb_flow:
        cells = [[body, thumb_flow]]
        t = Table(cells, colWidths=[width - 1.75 * inch, 1.75 * inch], hAlign="LEFT")
        t.setStyle(TableStyle([
            ("VALIGN", (0, 0), (0, 0), "MIDDLE"),
            ("VALIGN", (1, 0), (1, 0), "MIDDLE"),
            ("ALIGN", (1, 0), (1, 0), "RIGHT"),
            ("LINEBEFORE", (0, 0), (0, -1), 2.5, ACCENT),
            ("LEFTPADDING", (0, 0), (0, -1), 14),
            ("RIGHTPADDING", (0, 0), (-1, -1), 0),
            ("TOPPADDING", (0, 0), (-1, -1), 6),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ]))
    else:
        t = Table([[body]], colWidths=[width], hAlign="LEFT")
        t.setStyle(TableStyle([
            ("LINEBEFORE", (0, 0), (0, -1), 2.5, ACCENT),
            ("LEFTPADDING", (0, 0), (-1, -1), 14),
            ("RIGHTPADDING", (0, 0), (-1, -1), 0),
            ("TOPPADDING", (0, 0), (-1, -1), 6),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ]))
    return [KeepTogether([Spacer(1, 6), t, Spacer(1, 16)])]


def fitted_image(data, path, max_w, max_h, thumb_px=560):
    """An Image scaled to fit a box, aspect preserved, never blindly stretched."""
    src = data.thumb(path, thumb_px)
    try:
        iw, ih = ImageReader(src).getSize()
    except Exception as e:
        warn(f"unreadable image {path}: {e}")
        return Spacer(1, 1)
    if not iw or not ih:
        return Spacer(1, 1)
    scale = min(max_w / iw, max_h / ih)
    return Image(src, width=iw * scale, height=ih * scale)


def chart_block(run, data, styles, block, width=BODY_W):
    path = os.path.join(run, "charts", block.get("file", ""))
    if not os.path.isfile(path):
        warn(f"chart missing, skipped: {os.path.relpath(path, run)}")
        return []
    img = fitted_image(data, path, min(width, 6.4 * inch), 4.0 * inch,
                       thumb_px=1800)
    out = [img]
    if block.get("caption"):
        out.append(Paragraph("<b>Reading this chart.</b> " + esc(block["caption"]),
                             styles["caption"]))
    else:
        out.append(Spacer(1, 12))
    return [KeepTogether([Spacer(1, 4)] + out)]


def _table_flowable(columns, rows, styles, width, tiny=False, zebra=True):
    n = len(columns)
    if not n:
        return None
    head_style = styles["cell_tiny_head"] if tiny else styles["cell_head"]
    cell_style = styles["cell_tiny"] if tiny else styles["cell"]
    right = [all(is_numeric(r[i]) for r in rows if i < len(r) and str(r[i]).strip())
             and any(is_numeric(r[i]) for r in rows if i < len(r))
             for i in range(n)]
    head_r = styles["cell_tiny_head"] if tiny else styles["cell_head_r"]
    data = [[Paragraph(esc(str(c).replace("_", " ")),
                       head_r if (right[i] and not tiny) else head_style)
             for i, c in enumerate(columns)]]
    for r in rows:
        r = list(r) + [""] * (n - len(r))
        data.append([
            Paragraph(esc(v), (styles["cell_r"] if (right[i] and not tiny)
                               else cell_style))
            for i, v in enumerate(r[:n])])
    # widths proportional to the longest sampled content, bounded both ways
    weights = []
    for i in range(n):
        longest = max([len(str(columns[i]))]
                      + [len(str(r[i])) if i < len(r) else 0 for r in rows[:120]])
        weights.append(min(max(longest, 5 if tiny else 8), 46))
    total = float(sum(weights)) or 1.0
    floor = (0.42 if tiny else 0.62) * inch
    widths = [max(floor, width * w / total) for w in weights]
    over = sum(widths) - width
    if over > 0:
        for i in sorted(range(n), key=lambda i: -widths[i]):
            give = min(over, widths[i] - floor)
            widths[i] -= give
            over -= give
            if over <= 0:
                break
    cls = LongTable if len(rows) > 25 else Table
    t = cls(data, colWidths=widths, repeatRows=1, hAlign="LEFT")
    style = [
        ("BACKGROUND", (0, 0), (-1, 0), SURFACE),
        ("LINEABOVE", (0, 0), (-1, 0), 1.0, INK),
        ("LINEBELOW", (0, 0), (-1, 0), 0.5, RULE),
        ("LINEBELOW", (0, -1), (-1, -1), 0.75, RULE),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING", (0, 0), (-1, -1), 4 if not tiny else 2),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4 if not tiny else 2),
        ("LEFTPADDING", (0, 0), (-1, -1), 5 if not tiny else 3),
        ("RIGHTPADDING", (0, 0), (-1, -1), 5 if not tiny else 3),
    ]
    if zebra:
        style.append(("ROWBACKGROUNDS", (0, 1), (-1, -1), [PAPER, SURFACE]))
    t.setStyle(TableStyle(style))
    return t


def csv_slice(run, spec):
    """Rows for a table block that points at a clean CSV instead of literals."""
    rel = spec.get("csv", "")
    rows = read_csv_rows(os.path.join(run, rel))
    if not rows:
        warn(f"table csv missing or empty: {rel}")
        return [], []
    cols = spec.get("columns") or list(rows[0].keys())
    sort_by = spec.get("sort_by")
    if sort_by:
        rows.sort(key=lambda r: (fnum(r.get(sort_by)) if fnum(r.get(sort_by))
                                 is not None else float("-inf")),
                  reverse=not spec.get("ascending"))
    where = spec.get("where") or {}
    for k, v in where.items():
        rows = [r for r in rows if (r.get(k) or "").strip().lower() == str(v).lower()]
    rows = rows[:int(spec.get("limit") or 15)]
    out = []
    for r in rows:
        line = []
        for c in cols:
            v = r.get(c, "")
            if c in ("cpc", "low_top_of_page_bid", "high_top_of_page_bid"):
                v = fmt_usd(v)
            elif c in ("search_volume", "spend_proxy"):
                v = fmt_int(v)
            line.append(v)
        out.append(line)
    labels = spec.get("labels") or [c.replace("_", " ") for c in cols]
    return labels, out


def table_block(run, styles, block, width=BODY_W):
    if block.get("csv"):
        columns, rows = csv_slice(run, block)
    else:
        columns = block.get("columns") or []
        rows = block.get("rows") or []
    if not columns or not rows:
        return []
    t = _table_flowable(columns, rows, styles, width)
    if t is None:
        return []
    out = []
    if block.get("title"):
        out.append(Paragraph(esc(block["title"]), styles["h3"]))
    out.append(t)
    if block.get("note"):
        out.append(Paragraph(esc(block["note"]), styles["note"]))
    else:
        out.append(Spacer(1, 14))
    return [KeepTogether(out)] if len(rows) <= 12 else out


# ----------------------------------------------------------- creative evidence

def creative_attribution(row):
    """"Plunge — running 412 days, still live" — the line under a quote."""
    adv = (row.get("advertiser_title") or "").strip() or "unknown advertiser"
    days = fnum(row.get("days_running"))
    bits = [adv]
    if days:
        bits.append(f"running {days:,.0f} days")
    active = (row.get("active") or "").strip().lower()
    if active in ("true", "1", "yes"):
        bits.append("still live")
    elif active in ("false", "0", "no"):
        bits.append("no longer running")
    cid = (row.get("creative_id") or "").strip()
    line = " — ".join([bits[0], ", ".join(bits[1:])]) if len(bits) > 1 else bits[0]
    return f"{line} (ad {cid})" if cid else line


def creative_card(data, styles, row, col_w, img_h=1.55 * inch, thumb_px=620):
    """One ad: the picture as delivered, then exactly what it says."""
    inner_w = col_w - 16
    png = data.png_for(row)
    if png:
        art = fitted_image(data, png, inner_w, img_h, thumb_px=thumb_px)
    else:
        art = Paragraph("(this ad has no rendered image — Google returns none "
                        "for some video and app formats)", styles["card_meta"])
    well = Table([[art]], colWidths=[inner_w], rowHeights=[img_h])
    well.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ("TOPPADDING", (0, 0), (-1, -1), 0),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
    ]))
    cell = [well, Spacer(1, 6)]
    days = fnum(row.get("days_running"))
    flags = []
    if days:
        flags.append(f"{days:,.0f} days")
    if (row.get("active") or "").strip().lower() in ("true", "1", "yes"):
        flags.append("live")
    fmt = (row.get("format") or "").strip()
    if fmt:
        flags.append(fmt)
    cell.append(Paragraph(esc((row.get("advertiser_title") or "").strip()
                              or "unknown advertiser"), styles["card_adv"]))
    if flags:
        cell.append(Paragraph(esc(" · ".join(flags)), styles["card_flag"]))
    cp = data.copy_of(row)
    head = (cp.get("headline") or "").strip()
    desc = (cp.get("description") or "").strip()
    cta = (cp.get("cta") or "").strip()
    if head:
        cell.append(Paragraph(esc(head), styles["card_head"]))
    if desc and desc.upper() != "ILLEGIBLE":
        cell.append(Paragraph(esc(desc), styles["card_desc"]))
    if cta and cta.upper() != "ILLEGIBLE":
        cell.append(Paragraph("<b>" + esc(cta) + "</b>", styles["card_desc"]))
    if not head and not desc:
        cell.append(Paragraph("Wording not machine-readable from this image — "
                              "the picture above is the evidence.",
                              styles["card_meta"]))
    meta = []
    if row.get("first_shown") or row.get("last_shown"):
        meta.append(f"{(row.get('first_shown') or '?')} to "
                    f"{(row.get('last_shown') or '?')}")
    cid = (row.get("creative_id") or "").strip()
    if cid:
        meta.append(f"ad {cid}")
    if meta:
        cell.append(Paragraph(esc(" · ".join(meta)), styles["card_meta"]))
    data.creatives_shown.add(cid)
    return cell


def creative_grid(data, styles, rows, width=BODY_W, columns=3, img_h=1.55 * inch,
                  thumb_px=620):
    """A grid of ad cards, laid out row by row so pages break between rows."""
    if not rows:
        return []
    columns = max(1, min(4, int(columns)))
    col_w = (width - (columns - 1) * 12) / columns
    out = []
    for i in range(0, len(rows), columns):
        chunk = rows[i:i + columns]
        cells = [creative_card(data, styles, r, col_w, img_h, thumb_px) for r in chunk]
        while len(cells) < columns:
            cells.append([Spacer(1, 1)])
        widths, gapped = [], []
        for j, c in enumerate(cells):
            if j:
                gapped.append([Spacer(1, 1)])
                widths.append(12)
            gapped.append(c)
            widths.append(col_w)
        t = Table([gapped], colWidths=widths, hAlign="LEFT")
        style = [
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("TOPPADDING", (0, 0), (-1, -1), 0),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
            ("LEFTPADDING", (0, 0), (-1, -1), 0),
            ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ]
        for j in range(0, 2 * len(chunk), 2):  # real cards only; odd cols are gaps
            style += [("BACKGROUND", (j, 0), (j, 0), PAPER),
                      ("BOX", (j, 0), (j, 0), 0.5, RULE),
                      ("TOPPADDING", (j, 0), (j, 0), 8),
                      ("BOTTOMPADDING", (j, 0), (j, 0), 10),
                      ("LEFTPADDING", (j, 0), (j, 0), 8),
                      ("RIGHTPADDING", (j, 0), (j, 0), 8)]
        t.setStyle(TableStyle(style))
        out.append(KeepTogether([t, Spacer(1, 10)]))
    return out


def creatives_block(data, styles, block, width=BODY_W):
    rows = data.creative_rows(
        ids=block.get("ids"), advertiser=block.get("advertiser"),
        select=block.get("select", "longest"), limit=int(block.get("limit") or 6),
        require_copy=bool(block.get("require_copy")))
    if not rows:
        warn("creatives block matched no downloaded ads — skipped")
        return []
    out = []
    if block.get("title"):
        out.append(Paragraph(esc(block["title"]), styles["h3"]))
    if block.get("intro"):
        out.append(Paragraph(esc(block["intro"]), styles["body"]))
    out += creative_grid(data, styles, rows, width,
                         columns=block.get("columns", 3),
                         img_h=float(block.get("image_height_in") or 1.55) * inch)
    if block.get("caption"):
        out.append(Paragraph(esc(block["caption"]), styles["caption"]))
    if block.get("link_appendix", True):
        total = len([r for r in data.ads if data.png_for(r)])
        if total > len(rows):
            out.append(link_to("Appendix A — the advertising",
                               f"All {total:,} ads running in this market, "
                               f"in Appendix A", styles))
    return out


# ------------------------------------------------------------- block dispatch

def render_blocks(run, data, styles, blocks, width=BODY_W):
    out = []
    for block in blocks or []:
        if not isinstance(block, dict):
            out += [Paragraph(esc(block), styles["body"])]
            continue
        kind = (block.get("type") or "paragraph").lower()
        if kind in ("paragraph", "text", "p"):
            out += para_block(styles, block)
        elif kind in ("bullets", "list"):
            out += bullets_block(styles, block)
        elif kind in ("stats", "key_numbers"):
            out += stats_block(styles, block, width)
        elif kind == "callout":
            out += callout_block(styles, block, width)
        elif kind == "quote":
            out += quote_block(styles, block, data, width)
        elif kind == "chart":
            out += chart_block(run, data, styles, block, width)
        elif kind == "table":
            out += table_block(run, styles, block, width)
        elif kind in ("creatives", "ads", "gallery"):
            out += creatives_block(data, styles, block, width)
        elif kind == "link":
            target = block.get("target") or "Appendix B — the full data"
            out += [link_to(target, block.get("label") or f"See {target}", styles)]
        elif kind in ("heading", "subheading"):
            out += [Paragraph(esc(block.get("text", "")), styles["h2"])]
        elif kind == "divider":
            out += [rule(HAIR, width, 0.5, 6, 12)]
        elif kind == "pagebreak":
            out += [PageBreak()]
        else:
            warn(f"unknown block type '{kind}' — rendered as a paragraph")
            out += para_block(styles, block)
    return out


def chapter_blocks(ch):
    """A chapter's ordered blocks, accepting the flat legacy keys too."""
    if ch.get("blocks"):
        return ch["blocks"]
    blocks = []
    for p in ch.get("paragraphs", []):
        blocks.append({"type": "paragraph", "text": p})
    if ch.get("bullets"):
        blocks.append({"type": "bullets", "items": ch["bullets"]})
    for t in ch.get("tables", []):
        blocks.append(dict(t, type="table"))
    for c in ch.get("charts", []):
        blocks.append(dict(c, type="chart"))
    for g in ch.get("creatives", []):
        blocks.append(dict(g, type="creatives"))
    return blocks


# ------------------------------------------------------------- report sections

def cover(man, styles, data):
    """Page one has one job: land the answer, and show the evidence exists."""
    title_text = man.get("title") or f"DemandCheck: {man.get('seed','')}"
    title_style = styles["cover_title"]
    if len(title_text) > 58:
        title_style = ParagraphStyle("cover_title_sm", parent=title_style,
                                     fontSize=25, leading=29)
    elif len(title_text) > 38:
        title_style = ParagraphStyle("cover_title_md", parent=title_style,
                                     fontSize=29, leading=33)
    story = [Spacer(1, 0.35 * inch),
             Paragraph(track("Demand check"), styles["cover_eyebrow"]),
             Paragraph(esc(title_text), title_style),
             Paragraph("What people actually search for, what advertisers "
                       "actually pay, and what their ads actually say.",
                       styles["cover_seed"]),
             Spacer(1, 20),
             Paragraph(" &#160;·&#160; ".join([
                 f"<b>{esc(man.get('geo',''))}</b>",
                 esc(man.get("date", "")),
                 f"“{esc(man.get('seed',''))}”"]), styles["cover_meta"])]

    if man.get("verdict_line"):
        inner = [Paragraph(track("The verdict"), styles["verdict_label"]),
                 Paragraph(esc(man["verdict_line"]), styles["verdict"])]
        t = Table([[inner]], colWidths=[BODY_W])
        t.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), COVER_PANEL),
            ("LINEBEFORE", (0, 0), (0, -1), 3, ACCENT),
            ("LEFTPADDING", (0, 0), (-1, -1), 18),
            ("RIGHTPADDING", (0, 0), (-1, -1), 18),
            ("TOPPADDING", (0, 0), (-1, -1), 18),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 20),
        ]))
        story += [Spacer(1, 24), t]

    kn = man.get("key_numbers") or []
    if kn:
        story += [Spacer(1, 20)]
        story += stats_block(styles, {"items": kn}, dark=True)

    story += cover_ad_strip(data, styles)
    return story


def cover_ad_strip(data, styles, count=5):
    """A row of the market's actual advertising, on the cover.

    It is the fastest possible proof that the report contains the real thing
    rather than a description of it.
    """
    pool = data.creative_rows(select="longest", require_image=True)
    rows, seen = [], set()
    for r in pool:
        adv = (r.get("advertiser_title") or "").strip().lower()
        if adv in seen:
            continue
        seen.add(adv)
        rows.append(r)
        if len(rows) >= count:
            break
    if len(rows) < count:      # thin market: fall back to the longest-running
        for r in pool:
            if r not in rows:
                rows.append(r)
            if len(rows) >= count:
                break
    if len(rows) < 3:
        return []
    n = len(rows)
    col_w = (BODY_W - (n - 1) * 8) / n
    cells, widths = [], []
    for i, r in enumerate(rows):
        if i:
            cells.append([Spacer(1, 1)])
            widths.append(8)
        png = data.png_for(r)
        art = fitted_image(data, png, col_w - 12, 0.82 * inch, thumb_px=420)
        well = Table([[art]], colWidths=[col_w - 12], rowHeights=[0.82 * inch])
        well.setStyle(TableStyle([
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("ALIGN", (0, 0), (-1, -1), "CENTER"),
            ("LEFTPADDING", (0, 0), (-1, -1), 0),
            ("RIGHTPADDING", (0, 0), (-1, -1), 0),
            ("TOPPADDING", (0, 0), (-1, -1), 0),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
        ]))
        days = fnum(r.get("days_running"))
        label = (r.get("advertiser_title") or "").strip()
        if days:
            label += f" · {days:,.0f} days"
        cells.append([well, Spacer(1, 3), Paragraph(esc(label), styles["cover_card"])])
        widths.append(col_w)
    grid = Table([cells], colWidths=widths, hAlign="LEFT")
    style = [("VALIGN", (0, 0), (-1, -1), "TOP"),
             ("LEFTPADDING", (0, 0), (-1, -1), 0),
             ("RIGHTPADDING", (0, 0), (-1, -1), 0),
             ("TOPPADDING", (0, 0), (-1, -1), 0),
             ("BOTTOMPADDING", (0, 0), (-1, -1), 0)]
    for j in range(0, 2 * n, 2):
        style += [("BACKGROUND", (j, 0), (j, 0), PAPER),
                  ("LEFTPADDING", (j, 0), (j, 0), 6),
                  ("RIGHTPADDING", (j, 0), (j, 0), 6),
                  ("TOPPADDING", (j, 0), (j, 0), 6),
                  ("BOTTOMPADDING", (j, 0), (j, 0), 6)]
    grid.setStyle(TableStyle(style))
    return [Spacer(1, 26),
            Paragraph(track("What this market is running right now"),
                      styles["cover_strip"]),
            grid]


def whats_inside(styles, man):
    """Orients the reader in three lines. Not a description of how the work
    was done — what they are holding and where to look."""
    items = man.get("whats_inside") or [
        "<b>The verdict and the four chapter openers</b> give you the whole "
        "picture in about four minutes.",
        "<b>Every figure traces to a named search term or a live ad</b>, listed "
        "in full in the appendices at the back.",
        "<b>The advertising is reproduced as it runs</b>, with how long each ad "
        "has been live underneath it — an ad that has run for months is an ad "
        "that pays for itself.",
        "<b>The last chapter is four ways in</b>, ranked, with what each one "
        "costs you.",
    ]
    out = [Paragraph("What's inside", styles["h2"])]
    for i in items:
        out.append(Paragraph(i, styles["bullet"], bulletText="—"))
    out.append(Spacer(1, 6))
    return out


# --------------------------------------------------- the orientation page

# Three sentences that make every number in the report legible to a reader who
# has never bought an ad. Nothing here is about how the report was made.
MARKET_BEATS = [
    ("People search for what they want.",
     "The number of searches is the size of the audience, month after month. "
     "It is the closest thing there is to a headcount of people with the "
     "problem."),
    ("Companies bid to sit beside those searches.",
     "They pay each time someone clicks. That price is the market's own "
     "valuation of one of those people — set by what the companies already "
     "there are willing to pay."),
    ("Advertising that loses money gets switched off.",
     "Within weeks, usually. So an ad still running after a year is a message "
     "that pays for itself, and its wording is worth reading closely."),
]

# name -> (one-line definition, what it means for the reader)
DEMAND_KINDS = {
    "direct": ("People searching for the thing itself, by name.",
               "They are shopping. They convert soonest, and they are the most "
               "expensive people in the market to reach — everyone selling is "
               "bidding for them."),
    "indirect": ("People searching for a neighbouring problem that leads here.",
                 "They can be reached, but somebody has to connect the two "
                 "things for them. Cheaper than direct, and less contested."),
    "latent": ("People with the problem who are not looking for the product yet.",
               "The cheapest attention in the market, because few companies bid "
               "for it. Slower to turn into a sale, and usually the largest "
               "group."),
    "urgent": ("People who need it now — repair, emergency, same-day.",
               "The fastest decisions and the highest prices per click. Usually "
               "a small group, and worth serving only if you can actually turn "
               "up."),
    "unclear": ("Searches whose intent the wording does not settle.",
                "Held separately rather than folded into a number they might "
                "not belong in."),
}


def market_beats_flowables(styles, beats, width=BODY_W):
    n = len(beats)
    col_w = (width - (n - 1) * 14) / n
    cells, widths = [], []
    for i, (head, body) in enumerate(beats, 1):
        if i > 1:
            cells.append([Spacer(1, 1)])
            widths.append(14)
        cells.append([Paragraph(str(i), styles["beat_num"]),
                      Paragraph(esc(head), styles["beat_head"]),
                      Paragraph(esc(body), styles["beat_body"])])
        widths.append(col_w)
    t = Table([cells], colWidths=widths, hAlign="LEFT")
    style = [("VALIGN", (0, 0), (-1, -1), "TOP"),
             ("LEFTPADDING", (0, 0), (-1, -1), 0),
             ("RIGHTPADDING", (0, 0), (-1, -1), 0),
             ("TOPPADDING", (0, 0), (-1, -1), 0),
             ("BOTTOMPADDING", (0, 0), (-1, -1), 0)]
    for j in range(0, 2 * n, 2):
        style.append(("LINEABOVE", (j, 0), (j, 0), 2, ACCENT))
        style.append(("TOPPADDING", (j, 0), (j, 0), 8))
    t.setStyle(TableStyle(style))
    return [t, Spacer(1, 22)]


def demand_kind_cards(styles, cards, width=BODY_W):
    """Two-by-two: what each kind of demand is, sized from this market."""
    if not cards:
        return []
    out = []
    for i in range(0, len(cards), 2):
        pair = cards[i:i + 2]
        col_w = (width - 14) / 2
        cells, widths = [], []
        for j, c in enumerate(pair):
            if j:
                cells.append([Spacer(1, 1)])
                widths.append(14)
            inner = [Paragraph(esc(c["name"]).upper(), styles["kind_name"]),
                     Paragraph(esc(c["definition"]), styles["kind_def"])]
            if c.get("stat"):
                inner.append(Paragraph(esc(c["stat"]), styles["kind_stat"]))
            if c.get("example"):
                inner.append(Paragraph(esc(c["example"]), styles["kind_eg"]))
            if c.get("means"):
                inner.append(Paragraph("<b>What it means.</b> " + esc(c["means"]),
                                       styles["kind_means"]))
            cells.append(inner)
            widths.append(col_w)
        while len(cells) < 3:
            cells += [[Spacer(1, 1)], [Spacer(1, 1)]]
            widths += [14, col_w]
        t = Table([cells], colWidths=widths, hAlign="LEFT")
        style = [("VALIGN", (0, 0), (-1, -1), "TOP"),
                 ("LEFTPADDING", (0, 0), (-1, -1), 0),
                 ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                 ("TOPPADDING", (0, 0), (-1, -1), 0),
                 ("BOTTOMPADDING", (0, 0), (-1, -1), 0)]
        for j, c in enumerate(pair):
            col = 2 * j
            # the colour is the same one this kind wears in every chart
            style += [("BACKGROUND", (col, 0), (col, 0), SURFACE),
                      ("LINEABOVE", (col, 0), (col, 0), 3, c["color"]),
                      ("LEFTPADDING", (col, 0), (col, 0), 12),
                      ("RIGHTPADDING", (col, 0), (col, 0), 12),
                      ("TOPPADDING", (col, 0), (col, 0), 10),
                      ("BOTTOMPADDING", (col, 0), (col, 0), 12)]
        t.setStyle(TableStyle(style))
        out.append(KeepTogether([t, Spacer(1, 14)]))
    return out


def demand_primer_section(data, styles, man):
    """One page that makes the rest of the report legible: how a search market
    works, and what the four kinds of demand are — each sized and exampled
    from this market's own rows."""
    spec = man.get("demand_primer") or {}
    if spec.get("skip"):
        return []
    story = section_opener(
        styles, spec.get("heading") or "How to read this market",
        kicker="Start here",
        deck=spec.get("deck") or
        "Two minutes that make every number in this report mean something.")
    story += market_beats_flowables(styles, spec.get("beats") or MARKET_BEATS)

    cards = spec.get("cards")
    if cards is None:
        cards = build_kind_cards(data)
    if not cards:
        return story
    story.append(Paragraph(
        spec.get("kinds_lead") or
        "Not all of that audience wants the same thing, so this report sorts "
        "every search term into four kinds. They behave differently, they cost "
        "different amounts to reach, and the mix between them is the finding.",
        styles["body"]))
    story.append(Spacer(1, 8))
    story += demand_kind_cards(styles, cards)
    return story


def build_kind_cards(data):
    """Size each kind of demand from the corpus and pick a real example term."""
    if not data.keywords:
        return []
    buckets = {}
    for r in data.keywords:
        cls = (r.get("demand_class") or "unclear").strip().lower() or "unclear"
        buckets.setdefault(cls, []).append(r)
    cards = []
    for cls in ("direct", "indirect", "latent", "urgent", "unclear"):
        rows = buckets.get(cls)
        if not rows or cls not in DEMAND_KINDS:
            continue
        if cls == "unclear" and len(rows) < max(3, len(data.keywords) // 5):
            continue                      # too small to be worth a card
        definition, means = DEMAND_KINDS[cls]
        vol = sum(fnum(r.get("search_volume")) or 0 for r in rows)
        cpcs = sorted(c for c in (fnum(r.get("cpc")) for r in rows) if c)
        med = cpcs[len(cpcs) // 2] if cpcs else None
        stat = f"{len(rows):,} search terms · {vol:,.0f} searches a month"
        if med:
            stat += f" · about {fmt_usd(med)} a click"
        top = max(rows, key=lambda r: fnum(r.get("search_volume")) or 0)
        example = ""
        if (top.get("keyword") or "").strip():
            example = (f"For example “{top['keyword'].strip()}” — "
                       f"{fmt_int(top.get('search_volume'))} searches a month")
            if fnum(top.get("cpc")):
                example += f" at {fmt_usd(top.get('cpc'))} a click"
        cards.append({"name": f"{cls} demand", "definition": definition,
                      "means": means, "stat": stat, "example": example,
                      "color": CLASS_COLORS.get(cls, MUTED)})
    return cards[:4]


def key_terms_section(run, data, styles, man):
    """The search terms, early and in full view.

    Every claim in the report rests on these rows, so they come before the
    argument rather than after it.
    """
    spec = man.get("key_terms") or {}
    if spec.get("skip"):
        return []
    rows = spec.get("rows")
    columns = spec.get("columns") or ["search term", "searches per month",
                                      "price per click",
                                      "monthly value of those clicks",
                                      "kind of demand"]
    if not rows:
        if not data.keywords:
            return []
        ranked = sorted(
            data.keywords,
            key=lambda r: -(fnum(r.get("spend_proxy")) or
                            (fnum(r.get("search_volume")) or 0)))
        rows = [[r.get("keyword", ""), fmt_int(r.get("search_volume")),
                 fmt_usd(r.get("cpc")),
                 fmt_usd(r.get("spend_proxy"), 0),
                 (r.get("demand_class") or "").strip()]
                for r in ranked[:int(spec.get("limit") or 18)]]
    if not rows:
        return []
    total = len(data.keywords)
    story = section_opener(
        styles, spec.get("heading") or "The search terms behind every number here",
        kicker="The evidence, up front",
        deck=spec.get("deck") or
        f"The {len(rows)} largest of {total:,} measured search terms, ranked by "
        f"what a month of their clicks is worth at today's prices. Every figure "
        f"in this report comes from rows like these.")
    story += table_block(run, styles, {
        "columns": columns, "rows": rows,
        "note": spec.get("note") or
        "“Price per click” is what an advertiser pays Google each time someone "
        "clicks their ad. Multiply it by the searches and you get what a month "
        "of that term's attention costs at today's prices — the fourth column."})
    story.append(link_to("Appendix B — the full data",
                         f"All {total:,} search terms, with competition and "
                         f"top-of-page bids, in Appendix B", styles))
    return story


def explanations_section(styles, expl):
    """Why the market is shaped the way it is — mechanism, then the numbers."""
    story = section_opener(
        styles, "Why the market looks this way", kicker="The mechanics",
        deck="The numbers say what is happening. This says why — and what the "
             "obvious alternative reading gets wrong.")
    for i, e in enumerate(expl, 1):
        block = [Paragraph(esc(e.get("name", "")), styles["h2"])]
        for p in e.get("premises", []):
            block.append(Paragraph(esc(p), styles["bullet"], bulletText="—"))
        story.append(KeepTogether(block))
        evidence = e.get("evidence") or e.get("prediction_and_check")
        if evidence:
            story += callout_block(styles, {
                "variant": "evidence", "title": "What the data shows",
                "text": evidence})
        alt = e.get("alternative") or e.get("rival")
        if alt:
            story.append(Paragraph(
                "<b>The alternative read.</b> " + esc(alt), styles["body"]))
        story.append(Spacer(1, 6))
    return story


# One hue, stepping lighter down the rank — the badge itself says "ranked".
RANK_COLORS = [colors.HexColor("#1c5cab"), colors.HexColor("#2a78d6"),
               colors.HexColor("#5598e7"), colors.HexColor("#86b6ef")]


def path_card(styles, path, i, width=BODY_W):
    """One route forward, as a numbered card with its cost of entry."""
    badge_bg = RANK_COLORS[(i - 1) % len(RANK_COLORS)]
    numeral = styles["rank_num"] if i <= 2 else ParagraphStyle(
        "rank_num_dark", parent=styles["rank_num"], textColor=INK)
    badge = Table([[Paragraph(str(i), numeral)]],
                  colWidths=[0.42 * inch], rowHeights=[0.42 * inch])
    badge.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), badge_bg),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
    ]))
    body = [Paragraph(esc(path.get("name", "")), styles["path_name"])]
    if path.get("thesis"):
        body.append(Paragraph(esc(path["thesis"]), styles["path_body"]))
    for label, key in (("Why it ranks here", "evidence"),
                       ("What it costs you", "tradeoff"),
                       ("Right for you if", "best_if"),
                       ("First move", "first_step")):
        if path.get(key):
            body.append(Paragraph(track(label), styles["path_label"]))
            body.append(Paragraph(esc(path[key]), styles["path_body"]))
    inner_w = width - 0.42 * inch - 14
    card = Table([[badge, body]], colWidths=[0.42 * inch, inner_w], hAlign="LEFT")
    card.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("BACKGROUND", (1, 0), (1, 0), PAPER),
        ("LINEBELOW", (0, 0), (-1, -1), 0.5, RULE),
        ("LEFTPADDING", (0, 0), (0, 0), 0),
        ("RIGHTPADDING", (0, 0), (0, 0), 0),
        ("LEFTPADDING", (1, 0), (1, 0), 14),
        ("RIGHTPADDING", (1, 0), (1, 0), 0),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 14),
    ]))
    return KeepTogether([card, Spacer(1, 14)])


def paths_section(styles, man):
    """Four routes in, stack-ranked, each with what it costs."""
    paths = man.get("paths_forward") or []
    if not paths:
        return []
    deck = man.get("paths_deck") or man.get("paths_lead") or (
        "Four routes this market will pay for, ranked by what the evidence in "
        "this report supports. Each one costs something different.")
    story = section_opener(styles, "Four ways in",
                           kicker="Where to go from here", deck=deck)
    if man.get("paths_lead") and man.get("paths_deck"):
        story.append(Paragraph(esc(man["paths_lead"]), styles["lead"]))
    for i, p in enumerate(paths, 1):
        story.append(path_card(styles, p, p.get("rank") or i))
    if man.get("paths_close"):
        story += callout_block(styles, {
            "variant": "takeaway", "title": "If you do one thing",
            "text": man["paths_close"]})
    return story


def glossary_section(styles, gl):
    story = section_opener(
        styles, "Glossary", kicker="Reference",
        deck="Every technical term used in this report, in one place.")
    story += table_block(None, styles, {
        "columns": ["term", "in plain words"],
        "rows": [[g.get("term", ""), g.get("plain", "")] for g in gl]})
    return story


def creative_appendix(data, styles, max_creatives, columns, thumb_px):
    """Every downloaded ad, grouped by advertiser — the full visual evidence."""
    rows = data.creative_rows(select="longest", require_image=True)
    if not rows:
        return []
    total = len(rows)
    by_adv = {}
    for r in rows:
        by_adv.setdefault((r.get("advertiser_title") or "unknown advertiser").strip()
                          or "unknown advertiser", []).append(r)
    order = sorted(by_adv.items(), key=lambda kv: -len(kv[1]))
    shown, budget = 0, (max_creatives or total)
    story = section_opener(
        styles, "Appendix A — the advertising", kicker="The evidence",
        deck=f"All {total:,} live ads found in this market, as they run, grouped "
             f"by advertiser and longest-running first. The wording under each "
             f"picture is what the ad itself says.")
    for adv, ads in order:
        if shown >= budget:
            break
        take = ads[:max(0, budget - shown)]
        live = sum(1 for a in ads
                   if (a.get("active") or "").lower() in ("true", "1", "yes"))
        longest = max([fnum(a.get("days_running")) or 0 for a in ads] or [0])
        block = [Paragraph(esc(adv), styles["h2"]),
                 Paragraph(esc(f"{len(ads)} ads with a rendered image"
                               + (f" · {live} still running" if live else "")
                               + (f" · longest has run {longest:,.0f} days"
                                  if longest else "")), styles["note"])]
        story.append(KeepTogether(block))
        story += creative_grid(data, styles, take, BODY_W, columns=columns,
                               img_h=1.45 * inch, thumb_px=thumb_px)
        shown += len(take)
    if shown < total:
        story.append(Paragraph(
            f"Showing {shown:,} of {total:,} ads; every one is listed with its "
            f"run dates in Appendix B.", styles["note"]))
    return story


def data_appendix_table(run, entry, styles, max_rows):
    rel = entry.get("csv", "")
    path = os.path.join(run, rel)
    title = entry.get("title", rel)
    out = [Paragraph(esc(title), styles["h1_sub"])]
    if entry.get("what_it_is"):
        out.append(Paragraph(esc(entry["what_it_is"]), styles["deck"]))
    if not os.path.isfile(path):
        out.append(Paragraph(f"(table not found: {esc(rel)})", styles["body"]))
        return out
    with open(path, newline="", encoding="utf-8") as f:
        rows = list(csv.reader(f))
    if len(rows) < 2:
        out.append(Paragraph("(no rows collected for this table)", styles["body"]))
        return out
    header, body = rows[0], rows[1:]
    total = len(body)
    if max_rows and total > max_rows:
        body = body[:max_rows]
        out.append(Paragraph(
            f"Showing the first {max_rows:,} of {total:,} rows — the complete "
            f"file is {esc(rel)} in the run directory.", styles["note"]))
    else:
        out.append(Paragraph(f"All {total:,} rows.", styles["note"]))
    clipped = 0
    trimmed = []
    for r in body:
        row = []
        for v in r:
            v = str(v or "")
            if len(v) > 96:
                v, clipped = v[:95] + "…", clipped + 1
            row.append(v)
        trimmed.append(row)
    t = _table_flowable(header, trimmed, styles, WIDE_W,
                        tiny=len(header) > 8, zebra=True)
    if clipped:
        out.append(Paragraph(
            f"{clipped:,} very long values are shortened with “…” to keep this "
            f"table readable; the file itself holds them in full.",
            styles["note"]))
    if t is not None:
        out.append(t)
    return out


def ledger_section(state, styles):
    """Only rendered with --ledger: an operator's cost record, never part of
    the reader's report."""
    story = section_opener(
        styles, "Data ledger", kicker="Operator record",
        deck="Every billable call behind this report, with its price.")
    b = (state or {}).get("budget", {})
    cap, spent = b.get("usd_cap", 0) or 0, b.get("spent_usd", 0) or 0
    pct = 100.0 * spent / cap if cap else 0
    story.append(Paragraph(
        f"This survey spent <b>${spent:,.2f}</b> of a <b>${cap:,.2f}</b> data "
        f"budget ({pct:.0f}%) across <b>{b.get('calls', 0)}</b> billable calls. "
        f"Identical re-queries are served from cache at no cost, so re-checking "
        f"any number in this report is free.", styles["body"]))
    by_inst = {}
    for e in b.get("ledger", []):
        k = e.get("instrument", "other")
        agg = by_inst.setdefault(k, [0, 0.0])
        if not e.get("cached"):
            agg[0] += e.get("calls", 1)
            agg[1] += e.get("usd", 0.0)
    names = {"serp": "Google search results (Bright Data)",
             "keywords": "Google Ads keyword planner (DataForSEO)",
             "ads": "Google Ads Transparency library (DataForSEO)",
             "other": "other"}
    if by_inst:
        story += table_block(None, styles, {
            "title": "Where the money went",
            "columns": ["data source", "billable calls", "spend"],
            "rows": [[names.get(k, k), f"{n:,}", f"${usd:,.4f}"]
                     for k, (n, usd) in sorted(by_inst.items(),
                                               key=lambda kv: -kv[1][1])]})
    entries = b.get("ledger", [])
    if entries:
        story += table_block(None, styles, {
            "title": "Every call, in order",
            "columns": ["when (UTC)", "cost", "paid or cached", "what and why"],
            "rows": [[e.get("ts", ""), f"${e.get('usd', 0):.4f}",
                      "cache" if e.get("cached") else "paid", e.get("note", "")]
                     for e in entries]})
    return story


# ------------------------------------------------------------------ report card

def report_card(man, data, run, chapters_rendered):
    """Tell the operator what the manifest left unused. Cheap, and it raises
    the floor on every future run."""
    lines = []
    charts_available = {os.path.basename(p) for p in
                        glob.glob(os.path.join(run, "charts", "*.png"))}
    used = set()
    for ch in man.get("chapters", []):
        for b in chapter_blocks(ch):
            if isinstance(b, dict) and (b.get("type") == "chart" or b.get("file")):
                used.add(b.get("file"))
    unused = sorted(charts_available - used)
    n_creatives = len([r for r in data.ads if data.png_for(r)])
    lines.append(f"chapters rendered: {chapters_rendered}")
    lines.append(f"charts used: {len(used & charts_available)} of "
                 f"{len(charts_available)} rendered")
    if unused:
        lines.append(f"  unused charts (consider placing them): {', '.join(unused)}")
    cited = getattr(data, "cited_in_chapters", data.creatives_shown)
    if n_creatives:
        lines.append(f"ad creatives with images: {n_creatives} "
                     f"({len(cited)} shown inside the chapters, all of them in "
                     f"the evidence gallery)")
    else:
        lines.append("ad creatives with images: none were downloaded — "
                     "Appendix A is omitted")
    todos = json.dumps(man).count("TODO")
    if todos:
        lines.append(f"  MISSING: {todos} TODO markers are still in the manifest "
                     f"— they will print in the PDF exactly as written")
    for field, human in (("key_numbers", "cover key numbers"),
                         ("verdict_line", "the cover verdict"),
                         ("executive_summary", "executive summary"),
                         ("explanations", "why the market looks this way"),
                         ("paths_forward", "the four ways in"),
                         ("glossary", "glossary")):
        if not man.get(field):
            lines.append(f"  MISSING: {human} — manifest has no `{field}`")
    paths = man.get("paths_forward") or []
    if paths and len(paths) != 4:
        lines.append(f"  MISSING: paths_forward has {len(paths)} routes — the "
                     f"chapter is four, stack-ranked")
    leaked = [f for f in ("conjectures", "next_tests") if man.get(f)]
    if leaked:
        lines.append(f"  note: `{', '.join(leaked)}` is in the manifest and is "
                     f"not rendered — the report states findings, it does not "
                     f"narrate how it arrived at them")
    if n_creatives and not cited:
        lines.append("  MISSING: no ad creative is shown inside the chapters — "
                     "the strongest evidence this skill collects is sitting in "
                     "the appendix only (add a `creatives` or `quote` block)")
    print("\n--- manifest report card ---", file=sys.stderr)
    for line in lines:
        print(line, file=sys.stderr)
    return [line for line in lines if "MISSING" in line]


# ------------------------------------------------------------------------ main

def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--run", required=True, help="run directory")
    ap.add_argument("--max-table-rows", type=int, default=2000,
                    help="cap per data-appendix table (0 = unlimited; default 2000)")
    ap.add_argument("--max-creatives", type=int, default=0,
                    help="cap on ads in the creative appendix (0 = all; default 0)")
    ap.add_argument("--creative-columns", type=int, default=3,
                    help="ads per row in the creative appendix (default 3)")
    ap.add_argument("--thumb-px", type=int, default=620,
                    help="longest edge for embedded ad images (0 = originals)")
    ap.add_argument("--no-creative-appendix", action="store_true",
                    help="skip the full ad gallery (chapter exhibits still render)")
    ap.add_argument("--ledger", action="store_true",
                    help="append the operator's cost ledger (off by default — it "
                         "is not part of the reader's report)")
    ap.add_argument("--strict", action="store_true",
                    help="exit non-zero if the report card reports a missing section")
    ap.add_argument("--out", help="output path (default <run>/report.pdf)")
    args = ap.parse_args()
    run = args.run.rstrip("/")

    man_path = os.path.join(run, "report-manifest.json")
    if not os.path.isfile(man_path):
        print(f"error: {man_path} not found — the analyst writes it (Phase A).\n"
              f"hint:  python3 scripts/make_manifest.py --run {run}  scaffolds one",
              file=sys.stderr)
        sys.exit(2)
    with open(man_path, encoding="utf-8") as f:
        man = json.load(f)
    state = {}
    if os.path.isfile(os.path.join(run, "state.json")):
        with open(os.path.join(run, "state.json"), encoding="utf-8") as f:
            state = json.load(f)

    data = RunData(run)
    styles = build_styles()
    title = man.get("title") or f"DemandCheck: {man.get('seed', '')}"
    out_path = args.out or os.path.join(run, "report.pdf")
    doc = make_doc(out_path, title,
                   f"Demand survey of “{man.get('seed', '')}” — "
                   f"{man.get('geo', '')}, {man.get('date', '')}", title)

    story = []
    story += cover(man, styles, data)
    story += [NextPageTemplate("main"), PageBreak()]

    # Contents
    toc = TableOfContents()
    toc.levelStyles = [styles["toc0"], styles["toc1"]]
    toc.dotsMinLevel = 0
    story.append(Paragraph("Contents", styles["h1_plain"]))
    story.append(rule(RULE, BODY_W, 0.75, 2, 14))
    story.append(toc)
    story.append(Spacer(1, 24))
    story += whats_inside(styles, man)
    story.append(PageBreak())

    # Executive summary
    story += section_opener(
        styles, "The short version", kicker="Executive summary",
        deck=man.get("summary_deck") or
        "Everything that follows, in the order it matters.")
    for p in man.get("executive_summary", []):
        story.append(Paragraph(esc(p), styles["lead"] if p is
                               (man.get("executive_summary") or [None])[0]
                               else styles["body"]))
    if man.get("highlights"):
        story.append(Paragraph("What stood out", styles["h2"]))
        for h in man["highlights"]:
            if isinstance(h, dict):
                story += callout_block(styles, {
                    "variant": h.get("variant", "takeaway"),
                    "title": h.get("title", ""), "text": h.get("text", "")})
            else:
                story.append(Paragraph(esc(h), styles["bullet"], bulletText="—"))
    story += render_blocks(run, data, styles, man.get("summary_blocks"))

    # Orientation: how a search market works, and the four kinds of demand
    primer = demand_primer_section(data, styles, man)
    if primer:
        story.append(PageBreak())
        story += primer

    # The search terms, before the argument that rests on them
    terms = key_terms_section(run, data, styles, man)
    if terms:
        story.append(PageBreak())
        story += terms

    # Chapters
    chapters = man.get("chapters", [])
    for i, ch in enumerate(chapters, 1):
        story.append(PageBreak())
        story += section_opener(styles, ch.get("heading", f"Chapter {i}"),
                                kicker=ch.get("kicker") or f"Chapter {i}",
                                deck=ch.get("takeaway"))
        story += render_blocks(run, data, styles, chapter_blocks(ch))

    data.cited_in_chapters = set(data.creatives_shown)

    # Explanations
    if man.get("explanations"):
        story.append(PageBreak())
        story += explanations_section(styles, man["explanations"])

    # Four ways in — the reader's actual decision
    paths = paths_section(styles, man)
    if paths:
        story.append(PageBreak())
        story += paths

    if man.get("glossary"):
        story.append(PageBreak())
        story += glossary_section(styles, man["glossary"])

    # Appendix A — the ad creatives (the visual evidence)
    if not args.no_creative_appendix:
        gallery = creative_appendix(data, styles, args.max_creatives,
                                    args.creative_columns, args.thumb_px)
        if gallery:
            story.append(PageBreak())
            story += gallery

    # Appendix B — the full data (landscape)
    app = man.get("appendix_tables", [])
    if app:
        story.append(NextPageTemplate("wide"))
        story.append(PageBreak())
        story += section_opener(
            styles, "Appendix B — the full data", kicker="The evidence",
            deck="Every row behind this report, so any figure in it can be "
                 "checked against its source.", width=WIDE_W)
        for entry in app:
            story += data_appendix_table(run, entry, styles, args.max_table_rows)
            story.append(Spacer(1, 18))
        story.append(NextPageTemplate("main"))

    if args.ledger:
        story.append(PageBreak())
        story += ledger_section(state, styles)

    doc.multiBuild(story)
    size_mb = os.path.getsize(out_path) / 1e6
    print(f"wrote {out_path} ({doc.page} pages, {size_mb:.1f} MB)")
    missing = report_card(man, data, run, len(chapters))
    if args.strict and missing:
        sys.exit(1)


if __name__ == "__main__":
    main()
