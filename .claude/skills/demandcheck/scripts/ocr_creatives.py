#!/usr/bin/env python3
"""ocr_creatives.py — read the downloaded ad creatives locally, for $0.00.

Google's Ads Transparency API carries no ad text (`title` is the advertiser's
name), so the rendered PNG is the only copy there is. Those renders are the
easiest input OCR ever gets: synthetic type, flat background, no perspective —
so a local engine reads a whole wave in seconds for free, where a vision model
costs tokens and minutes per batch. This script is the default reader; the
Haiku transcriber (`agents/transcriber.md`) is the fallback for the handful of
creatives flagged here as unreadable.

It writes the rows the transcriber used to write — `raw/ad_copy/ocr-<dir>.csv`,
the `ad_copy` schema from references/traversal.md plus `extraction` and
`ocr_conf` — so the cleaner merges them unchanged. Creatives already read are
skipped, so running it once per wave costs nothing for the ones it has seen.

Usage:
    python3 .claude/skills/demandcheck/scripts/ocr_creatives.py --run research/demandcheck/<slug>
    python3 .claude/skills/demandcheck/scripts/ocr_creatives.py --run <run> --dir plunge.com
    python3 .claude/skills/demandcheck/scripts/ocr_creatives.py --self-test

Engines (auto-detected, in this order):
    tesseract   apt-get install tesseract-ocr | brew install tesseract
    rapidocr    python3 -m pip install rapidocr-onnxruntime
Pillow (`python3 -m pip install pillow`) is optional but wanted: it upscales
small banners before reading — the difference between `ony` and `only` on 9px
type — and it powers the gap sweep that recovers CTA buttons. Without it the
reader still runs, on clean renders only.

Measured on this repo's 18-layout benchmark (assets/ocr-benchmark, tesseract
5.3.4): headline 100%, description 97%, CTA 89%, other_text 83%; ~530ms per
image single-threaded, ~7 images/second across 4 cores. Against 10 live
HubSpot creatives it matched a Haiku transcriber's headline on 10 of 10 and
captured every word Haiku did plus the display URLs and sitelinks Haiku
dropped — in 1.7s against 66s and 36k tokens.

Exit codes: 0 ok · 2 usage/run problem · 3 no OCR engine installed (the caller
falls back to Haiku transcribers for the whole batch).
"""

import argparse
import csv
import json
import os
import re
import shutil
import statistics
import subprocess
import sys
import tempfile
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

# The ad_copy contract (references/traversal.md) plus two provenance columns:
# which reader produced the row, and how sure it was. The analyst needs both —
# a 41%-confidence read is not something to quote verbatim in a report.
AD_COPY_HEADER = ["creative_id", "advertiser_title", "headline", "description",
                  "cta", "other_text", "extraction", "ocr_conf"]

# Word confidence below this is dropped from the read entirely (tesseract
# emits -1 for non-word rows and low scores for background noise).
WORD_CONF_FLOOR = 40.0
# Whole-image verdicts. Below HARD: the read is not trustworthy at all and the
# row is written ILLEGIBLE. Between HARD and --min-conf: kept, but flagged.
IMAGE_CONF_HARD = 45.0
# How much more a later page-segmentation mode must read before it displaces
# the first mode's (structurally better) result.
PSM_SWITCH_MARGIN = 1.25
# A first read this full is complete — don't pay for a second segmentation mode.
PSM_RETRY_CHARS = 140
# ...and never retry when the first pass was already slow: a pass that crawls
# is a noisy, photographic creative, where the next mode is slower and no
# better. (An all-noise 500x300 test image cost 45s in mode 6 and read nothing.)
PSM_RETRY_MAX_SECONDS = 4.0
# Tesseract's OpenMP threads fight this script's thread pool — one process per
# image, single-threaded inside, is measurably faster and far more predictable.
TESS_ENV = dict(os.environ, OMP_THREAD_LIMIT="1")

CTA_VERBS = (r"shop|buy|order|get|learn|sign|start|try|book|download|install|"
             r"subscribe|join|register|call|watch|explore|discover|see|view|"
             r"request|claim|apply|enroll|schedule|compare|find|visit|read|"
             r"contact|save|browse|check|reserve|upgrade|activate|open")
CTA_RE = re.compile(rf"^(?:{CTA_VERBS})\b[\w %$&'’\-\.,!]{{0,26}}$", re.I)
CTA_EXACT = {
    "shop now", "learn more", "sign up", "get started", "buy now", "book now",
    "order now", "get quote", "get a quote", "contact us", "apply now",
    "try free", "try it free", "start free trial", "free trial", "download",
    "download now", "install now", "subscribe", "see more", "view more",
    "read more", "find out more", "request demo", "book a demo", "see pricing",
    "compare plans", "join now", "register now", "call now", "visit site",
    "start now", "watch now", "explore now", "enroll now", "get offer",
    "shop the sale", "get the app", "sign up free", "add to cart",
}
URL_RE = re.compile(
    r"^(?:https?://)?(?:www\.)?[a-z0-9][a-z0-9\-]*(?:\.[a-z0-9\-]+)+"
    r"(?:/\S*)?$", re.I)
DOMAIN_IN_LINE = re.compile(
    r"\b[a-z0-9][a-z0-9\-]*\.(?:com|net|org|io|co|ai|app|shop|store|us|uk|ca|"
    r"de|fr|au|eu|info|biz)\b(?:/\S*)?", re.I)
PRICE_ONLY = re.compile(r"^(?:from|starting at|as low as|only|just)?\s*"
                        r"[$€£]\s?[\d,.]+(?:\s*(?:/|per)\s*\w+)?$", re.I)
LEGAL_RE = re.compile(r"terms apply|t&cs?|see terms|restrictions apply|"
                      r"©|\ball rights reserved\b", re.I)
# The chrome Google prints around a rendered ad — not the advertiser's copy.
CHROME_ONLY = re.compile(r"^(?:ad|ads|sponsored|anuncio|annonce|"
                         r"why this ad\??)$", re.I)
# ...and the same words as a prefix on the display-URL line ("Ad · plunge.com").
# OCR renders the separator as ·, -, — or |, so accept any of them.
CHROME_PREFIX = re.compile(r"^(?:ad|ads|sponsored|anuncio|annonce)\s*"
                           r"[-–—·•:|]\s*", re.I)
VOWELS = set("aeiouyAEIOUY")
# Letters that reach above the x-height / below the baseline — the input to
# the type-size estimate in type_size().
ASCENDERS = set("bdfhklt0123456789$£€") | set("ABCDEFGHIJKLMNOPQRSTUVWXYZ")
DESCENDERS = set("gjpqy,;")
# Short words that are real copy, not OCR debris, despite being 1-2 letters.
SHORT_WORDS = {"a", "i", "an", "as", "at", "be", "by", "do", "go", "he", "if",
               "in", "is", "it", "me", "my", "no", "of", "on", "or", "so", "to",
               "up", "us", "we", "the", "and", "for", "you", "our", "new", "off",
               "all", "get", "now", "one", "two", "buy", "try", "see", "day"}
# `aR`, `peungev/Orks` — a capital arriving mid-token, which real copy (lower,
# Title, or UPPER) does not do. A reliable tell for a misread glyph run.
MIXED_CAPS = re.compile(r"^(?![A-Z][a-z'’\-]*$)(?![A-Z'’\-]+$)(?=.*[A-Z]).*[A-Z]")
# Punctuation that is copy, not debris — a headline wraps on its dash.
KEEP_PUNCT = {"-", "–", "—", "&", "+", "/"}
# The one character-level correction applied to a read. Capital I and lowercase
# l are the same glyph in most sans faces, so a dictionary-guided recogniser
# resolves the standalone token "AI" to the far commoner English word "Al" —
# on live HubSpot ads it turned "AI search" into "Al search" every time. "AI"
# is a keyword the analyst mines; the name "Al" is vanishingly rare in ad copy.
AI_CONFUSION = re.compile(r"\bAl\b")


def now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def die(msg: str, code: int = 2):
    print(f"error: {msg}", file=sys.stderr)
    sys.exit(code)


def norm(s: str) -> str:
    """Collapse whitespace; strip the punctuation OCR hallucinates at edges."""
    s = re.sub(r"\s+", " ", (s or "").replace("|", "I")).strip()
    return AI_CONFUSION.sub("AI", s.strip(" ·•|~^_="))


# ---------------------------------------------------------------- engines

def detect_engine(pref: str) -> tuple[str, str]:
    """Return (engine, version). Prefers tesseract: it is ~5x faster on these
    flat renders and needs no Python packages. rapidocr is the better reader
    on text laid over photography, so it wins when both are asked for."""
    have_tess = shutil.which("tesseract") is not None
    have_rapid = _rapidocr_available()
    if pref == "tesseract" or (pref == "auto" and have_tess):
        if not have_tess:
            die("tesseract not found.\nfix:   apt-get install tesseract-ocr"
                "   (macOS: brew install tesseract)", 3)
        out = subprocess.run(["tesseract", "--version"], capture_output=True,
                             text=True).stdout.splitlines()
        return "tesseract", (out[0].strip() if out else "tesseract")
    if pref == "rapidocr" or (pref == "auto" and have_rapid):
        if not have_rapid:
            die("rapidocr not installed.\n"
                "fix:   python3 -m pip install rapidocr-onnxruntime", 3)
        return "rapidocr", "rapidocr-onnxruntime"
    die("no OCR engine found — install one (either is free and local):\n"
        "  apt-get install tesseract-ocr    (macOS: brew install tesseract)\n"
        "  python3 -m pip install rapidocr-onnxruntime\n"
        "Without one, fall back to Haiku transcribers (agents/transcriber.md).",
        3)
    raise AssertionError("unreachable")


def _rapidocr_available() -> bool:
    import importlib.util
    return any(importlib.util.find_spec(m) is not None
               for m in ("rapidocr_onnxruntime", "rapidocr"))


_local = threading.local()


def _rapid_engine():
    """One engine per thread — the ONNX session is not thread-safe."""
    eng = getattr(_local, "rapid", None)
    if eng is None:
        try:
            from rapidocr_onnxruntime import RapidOCR
        except ImportError:
            from rapidocr import RapidOCR  # newer package name
        eng = _local.rapid = RapidOCR()
    return eng


def prep_image(path: str, tmpdir: str) -> str:
    """Upscale a small render before OCR when Pillow is available.

    Ad creatives are often 300x250 with 9-11px type — below tesseract's
    comfort zone, where it reads `ony` for `only` and drops whole regions.
    Quadrupling the pixels took this repo's stress fixture from ~60% word
    confidence to ~96%. Pillow is optional: without it the original file goes
    to the engine as-is, a few accuracy points worse.

    Deliberately *not* grayscaled or contrast-stretched: tesseract binarizes
    colour regions itself, and doing it first is destructive — flattening a
    white-on-blue CTA button to grey turned `Shop Now` into `| snopnow fl`.
    Alpha is the one thing worth flattening, onto white, since a transparent
    background otherwise composites to black.
    """
    try:
        from PIL import Image
    except ImportError:
        return path
    try:
        im = Image.open(path)
        im.load()
        if im.mode in ("RGBA", "LA", "P"):
            im = im.convert("RGBA")
            bg = Image.new("RGBA", im.size, (255, 255, 255, 255))
            im = Image.alpha_composite(bg, im)
        im = im.convert("RGB")
        long_side = max(im.size)
        if long_side < 1400:
            scale = min(4.0, max(2.0, 1400 / max(1, long_side)))
            # Cap the result at ~4MP: past that tesseract spends seconds per
            # image for no accuracy gain, and photo-heavy creatives crawl.
            scale = min(scale, (4_000_000 / max(1, im.width * im.height)) ** 0.5)
            if scale > 1.05:
                im = im.resize((max(1, int(im.width * scale)),
                                max(1, int(im.height * scale))), Image.LANCZOS)
        out = os.path.join(tmpdir, f"prep-{abs(hash(path))}.png")
        im.save(out)
        return out
    except Exception:  # noqa: BLE001 — a bad asset must not kill the batch
        return path


def read_lines(path: str, engine: str, psms: list[int], lang: str,
               tmpdir: str, timeout: float = 25.0,
               sweep: bool = True) -> list[dict]:
    """OCR one image into text lines with geometry.

    Line dict: {text, conf, x0, y0, x1, y1, h} — `h` is the type size proxy
    the field assignment below leans on (the biggest type is the headline).

    One pass in mode 3 (automatic layout) does the reading, then the gap
    sweep goes back for whatever the layout analyser skipped. Extra modes may
    be passed and the fullest read wins — mode 3 keeps it unless another reads
    materially more, since its line structure is what field assignment trusts
    — but with the sweep on they earned nothing on this repo's benchmark and
    cost ~50% more time, so the default is mode 3 alone.
    """
    img = prep_image(path, tmpdir)
    if engine != "tesseract":
        return _rapidocr_lines(img)
    best, best_score, slow = None, 0.0, False
    for psm in psms:
        t0 = time.time()
        lines = _tesseract_lines(img, psm, lang, timeout)
        # Score = characters read, weighted by confidence: a mode that finds
        # more text only wins if it is also sure about it.
        score = sum(len(l["text"]) * (l["conf"] / 100.0) for l in lines)
        if best is None or score > best_score * PSM_SWITCH_MARGIN:
            best, best_score = lines, max(score, best_score)
        slow = (time.time() - t0) > PSM_RETRY_MAX_SECONDS
        if best_score >= PSM_RETRY_CHARS or slow:
            break
    best = best or []
    if best and sweep and not slow:
        extra = sweep_gaps(img, best, lang, timeout)
        boxes = [(l["x0"], l["y0"], l["x1"], l["y1"]) for l in best]
        for l in extra:
            cx, cy = (l["x0"] + l["x1"]) / 2, (l["y0"] + l["y1"]) / 2
            if not any(x0 <= cx <= x1 and y0 <= cy <= y1
                       for x0, y0, x1, y1 in boxes):
                best.append(l)
        best.sort(key=lambda l: (l["y0"], l["x0"]))
    return best


def _tesseract_lines(path: str, psm: int, lang: str,
                     timeout: float = 25.0) -> list[dict]:
    cmd = ["tesseract", path, "stdout", "--psm", str(psm), "-l", lang,
           "-c", "preserve_interword_spaces=1", "tsv"]
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout,
                          env=TESS_ENV)
    if proc.returncode != 0:
        return []
    rows = list(csv.DictReader(proc.stdout.splitlines(), delimiter="\t",
                               quoting=csv.QUOTE_NONE))
    groups: dict[tuple, list[dict]] = {}
    for r in rows:
        try:
            conf = float(r.get("conf") or -1)
            if conf < WORD_CONF_FLOOR:
                continue
            text = (r.get("text") or "").strip()
            if not text:
                continue
            key = (int(r["block_num"]), int(r["par_num"]), int(r["line_num"]))
            groups.setdefault(key, []).append({
                "text": text, "conf": conf, "x": int(r["left"]),
                "y": int(r["top"]), "w": int(r["width"]), "h": int(r["height"]),
            })
        except (KeyError, ValueError, TypeError):
            continue
    lines = []
    for _, words in sorted(groups.items()):
        words.sort(key=lambda w: w["x"])
        for seg in split_columns(words):
            line = build_line(seg)
            if line:
                lines.append(line)
    return sorted(lines, key=lambda l: (l["y0"], l["x0"]))


def split_columns(words: list[dict]) -> list[list[dict]]:
    """Cut a tesseract 'line' where a column gap sits.

    Tesseract groups everything on one horizontal row into a single line, so a
    leaderboard reads as `ACME Business Insurance From $29 Get Quote` — logo,
    headline and button welded together. A gap wider than the type is tall is
    a layout gap, not a word space, and that is where the row gets cut.
    """
    if len(words) < 2:
        return [words]
    heights = statistics.median([w["h"] for w in words])
    limit = max(8.0, 0.9 * heights)
    segs, cur = [], [words[0]]
    for prev, w in zip(words, words[1:]):
        if w["x"] - (prev["x"] + prev["w"]) > limit:
            segs.append(cur)
            cur = []
        cur.append(w)
    segs.append(cur)
    return [s for s in segs if s]


def build_line(words: list[dict]) -> dict | None:
    # A logo sitting next to the brand name lands in the same row, and its
    # glyph ("SS)" for HubSpot's sprocket) is both junk text and tall enough
    # to make the line measure larger than the headline below it. Dropping
    # edge junk before measuring fixes the text and the type size at once.
    words = trim_junk_words(words)
    if not words:
        return None
    text = norm(" ".join(w["text"] for w in words))
    if not text:
        return None
    chars = sum(len(w["text"]) for w in words) or 1
    return {
        "text": text,
        "conf": sum(w["conf"] * len(w["text"]) for w in words) / chars,
        "x0": min(w["x"] for w in words),
        "y0": min(w["y"] for w in words),
        "x1": max(w["x"] + w["w"] for w in words),
        "y1": max(w["y"] + w["h"] for w in words),
        "h": type_size(words),
    }


def is_junk_word(t: str) -> bool:
    """A token that carries no word — what a logo, icon or rule becomes.

    The vowel test alone is not enough: half the acronyms this market runs on
    (CRM, SEO, AEO, HVAC, B2B) have no vowel either, and dropping the last
    word of "HubSpot Smart CRM" would be a silent edit of an advertiser's
    copy. Acronyms and anything carrying a digit are protected.
    """
    if t in KEEP_PUNCT:  # real copy: "Score - HubSpot AEO" wraps on the dash
        return False
    if not re.search(r"[A-Za-z0-9]", t):
        return True
    if re.search(r"\d", t):  # "$29", "24/7", "100K+"
        return False
    letters = re.sub(r"[^A-Za-z]", "", t)
    if t.isalnum() and letters.isupper() and 2 <= len(letters) <= 5:
        return False
    return (len(t) <= 3 and not (set(t) & VOWELS)
            and t.lower() not in SHORT_WORDS)


def trim_junk_words(words: list[dict]) -> list[dict]:
    """Drop junk tokens from the ends of a line, never from the middle — a
    misread *inside* a sentence is still evidence of what the ad said."""
    i, j = 0, len(words)
    while i < j and is_junk_word(words[i]["text"]):
        i += 1
    while j > i and is_junk_word(words[j - 1]["text"]):
        j -= 1
    return words[i:j]


def type_size(words: list[dict]) -> float:
    """Estimate the font size a line was set in, from its word boxes.

    A raw box height lies about size: `Learn` (no descender) measures 25%
    shorter than `Spanish` in the very same 26px face, which is enough to
    break a wrapped headline into pieces. Dividing the box by the fraction of
    an em that word's own letters actually occupy — ascenders 0.72, descenders
    another 0.21, x-height alone 0.52 — recovers the size itself.
    """
    ems = []
    for w in words:
        t = w["text"]
        frac = 0.72 if (set(t) & ASCENDERS) else 0.52
        if set(t) & DESCENDERS:
            frac += 0.21
        ems.append(w["h"] / frac)
    return max(1.0, statistics.median(ems))


def edge_profile(img, axis: int) -> list[int]:
    """Mean edge energy per row (axis 0) or per column (axis 1).

    One Pillow resize does the whole reduction in C — a 1.2MP creative
    profiles in about a millisecond, which is what makes the ink search below
    affordable enough to run on every image.
    """
    from PIL import Image, ImageFilter
    e = img.convert("L").filter(ImageFilter.FIND_EDGES)
    small = (e.resize((1, e.height), Image.BOX) if axis == 0
             else e.resize((e.width, 1), Image.BOX))
    return list(small.tobytes())


def ink_runs(prof: list[int], min_run: int, gap_tol: int) -> list[tuple[int, int]]:
    """Contiguous stretches of the profile that carry ink, merged across small
    gaps. Threshold is set off the median, not the maximum: a 48px headline
    out-energises a 14px button by an order of magnitude, and a max-relative
    threshold would erase every small element on the page."""
    if not prof:
        return []
    thr = max(3.0, statistics.median(prof) * 1.8 + 1.5)
    out, start, gap = [], None, 0
    for i, v in enumerate(prof):
        if v >= thr:
            if start is None:
                start = i
            gap = 0
        elif start is not None:
            gap += 1
            if gap > gap_tol:
                if (i - gap) - start >= min_run:
                    out.append((start, i - gap))
                start, gap = None, 0
    if start is not None and len(prof) - start >= min_run:
        out.append((start, len(prof)))
    return out


def tighten(img, rect: tuple[int, int, int, int]) -> list[tuple[int, int, int, int]]:
    """Shrink a region down to the boxes that actually contain ink."""
    x0, y0, x1, y1 = rect
    sub = img.crop(rect)
    if sub.width < 24 or sub.height < 10:
        return []
    boxes = []
    for a, b in ink_runs(edge_profile(sub, 0), 8, max(3, sub.height // 30)):
        band = sub.crop((0, a, sub.width, b))
        for c, d in ink_runs(edge_profile(band, 1), 10, max(6, (b - a) // 2)):
            boxes.append((x0 + c, y0 + a, x0 + d, y0 + b))
    return boxes


def strip_edge_junk(text: str) -> str:
    """Drop the glyph a button's own border becomes at the edge of a crop."""
    toks = text.split()
    while toks and len(toks[0]) <= 2 and not (set(toks[0]) & VOWELS) \
            and toks[0].lower() not in SHORT_WORDS:
        toks.pop(0)
    while toks and len(toks[-1]) <= 2 and not (set(toks[-1]) & VOWELS) \
            and toks[-1].lower() not in SHORT_WORDS:
        toks.pop()
    return norm(" ".join(toks))


def sweep_gaps(path: str, lines: list[dict], lang: str, timeout: float,
               max_crops: int = 4) -> list[dict]:
    """OCR the regions the layout analyser skipped, and return what it missed.

    Tesseract's page analysis silently drops small isolated blocks — which in
    an ad creative is precisely the CTA button ("Get Quote" on an orange pill)
    and the legal fine print. No page-segmentation mode, contrast trick or
    noise-rejection setting recovers them, because the region never reaches
    the recogniser; but crop that same button out and tesseract reads it
    perfectly. So: find the rectangles no line landed in, and look again there.

    Costs one small extra OCR call per gap (~30-80ms on a crop this size) and
    is capped at `max_crops`. Needs Pillow; without it the sweep is skipped.
    """
    try:
        from PIL import Image
    except ImportError:
        return []
    try:
        im = Image.open(path)
        im.load()
    except Exception:  # noqa: BLE001
        return []
    W, H = im.size
    if not lines or W < 40 or H < 40:
        return []
    med_h = statistics.median([l["y1"] - l["y0"] for l in lines])
    min_h = max(14.0, 0.7 * med_h)

    def gaps(span: int, taken: list[tuple[float, float]], floor: float):
        """Uncovered intervals of [0, span) wide enough to hold a line."""
        out, cursor = [], 0.0
        for a, b in sorted(taken):
            if a - cursor >= floor:
                out.append((cursor, a))
            cursor = max(cursor, b)
        if span - cursor >= floor:
            out.append((cursor, float(span)))
        return out

    pad = 0.25 * med_h
    rows = [(l["y0"] - pad, l["y1"] + pad) for l in lines]
    crops = []
    for top, bottom in gaps(H, rows, min_h * 1.2):
        crops.append((0, int(top), W, int(bottom)))
    # Also look beside the text: a leaderboard puts its button in the same
    # horizontal band as the headline, so a row-only sweep would never see it.
    bands = []
    for l in lines:
        for b in bands:
            if l["y0"] < b[1] and l["y1"] > b[0]:
                b[0], b[1] = min(b[0], l["y0"]), max(b[1], l["y1"])
                b[2].append(l)
                break
        else:
            bands.append([l["y0"], l["y1"], [l]])
    for top, bottom, band_lines in bands:
        cols = [(l["x0"] - pad, l["x1"] + pad) for l in band_lines]
        for left, right in gaps(W, cols, max(60.0, 0.12 * W)):
            crops.append((int(left), int(max(0, top - pad)), int(right),
                          int(min(H, bottom + pad))))

    crops = [c for c in crops if (c[2] - c[0]) >= 40 and (c[3] - c[1]) >= min_h]
    # Narrow each gap down to the ink inside it, so what reaches the recogniser
    # is one tight block rather than a band of empty background.
    tight = []
    for c in crops:
        try:
            tight += tighten(im, c)
        except Exception:  # noqa: BLE001
            continue
    tight = [b for b in tight
             if (b[2] - b[0]) >= 24 and min_h * 0.5 <= (b[3] - b[1]) <= 0.6 * H]
    tight.sort(key=lambda b: -((b[2] - b[0]) * (b[3] - b[1])))

    from PIL import Image, ImageOps
    found = []
    for x0, y0, x1, y1 in tight[:max_crops]:
        out = os.path.join(os.path.dirname(path),
                           f"gap-{abs(hash((path, x0, y0, x1, y1)))}.png")
        try:
            pad = max(4, int(0.18 * (y1 - y0)))
            tile = im.crop((max(0, x0 - pad), max(0, y0 - pad),
                            min(W, x1 + pad), min(H, y1 + pad)))
            # Scale the block so its type lands in tesseract's comfort zone.
            # This is the step that matters: a button headline left at page
            # scale reads as *nothing at all* (no psm mode, contrast trick or
            # noise setting recovers it), and the same crop at ~52px tall
            # reads perfectly. Then pad with white so the recogniser sees a
            # margin rather than the button's own border.
            scale = min(4.0, max(0.25, 52.0 / max(1, tile.height)))
            tile = tile.resize((max(8, int(tile.width * scale)),
                                max(8, int(tile.height * scale))), Image.LANCZOS)
            ImageOps.expand(tile, 12, (255, 255, 255)).save(out)
            # Mode 7 (one line) for a block cut to a single line's shape,
            # mode 6 (one paragraph) for a taller one — and each as the
            # other's fallback, because which one an isolated block answers to
            # is not predictable from its geometry alone. A crop this small
            # costs ~20ms an attempt, so trying twice beats guessing once.
            ladder = (7, 6) if (y1 - y0) < 1.6 * min_h else (6, 7)
            for psm in ladder:
                good = []
                for l in _tesseract_lines(out, psm, lang, timeout):
                    l["text"] = strip_edge_junk(l["text"])
                    # Speculative reads: a crop of photography returns
                    # confident nonsense, so only prose survives.
                    if (not l["text"] or l["conf"] < 55
                            or not looks_like_prose(l["text"])):
                        continue
                    l.update(x0=x0, x1=x1, y0=y0, y1=y1, h=(y1 - y0) / 0.93)
                    good.append(l)
                if good:
                    found += good
                    break
        except Exception:  # noqa: BLE001 — a failed crop is just no new text
            continue
        finally:
            if os.path.exists(out):
                os.remove(out)
    return found


def _rapidocr_lines(path: str) -> list[dict]:
    try:
        result, _ = _rapid_engine()(path)
    except Exception:  # noqa: BLE001
        return []
    lines = []
    for det in result or []:
        try:
            box, text, score = det[0], det[1], float(det[2])
        except (IndexError, TypeError, ValueError):
            continue
        text = norm(str(text))
        if not text:
            continue
        xs = [float(p[0]) for p in box]
        ys = [float(p[1]) for p in box]
        lines.append({"text": text, "conf": score * 100.0,
                      "x0": min(xs), "y0": min(ys), "x1": max(xs),
                      "y1": max(ys), "h": max(ys) - min(ys)})
    return sorted(lines, key=lambda l: (l["y0"], l["x0"]))


# ------------------------------------------------------- field assignment

def is_junk(text: str) -> bool:
    """Lines with no word in them — rules, borders, stray glyph noise."""
    if len(text) < 2:
        return True
    if not re.search(r"[A-Za-z0-9]", text):
        return True
    return bool(CHROME_ONLY.match(text))


def strip_chrome(text: str) -> str:
    """Drop Google's own label off a line so the display URL survives it."""
    return norm(CHROME_PREFIX.sub("", text)) or text


def is_url(text: str) -> bool:
    return bool(URL_RE.match(text.strip().rstrip("/")))


def is_meta(text: str) -> bool:
    """Display URL, bare price, or legal fine print — real text, but not the
    ad's pitch. Word-count bounded so body copy that happens to name a price
    ("Save $200 on every tub this week") stays in the description."""
    words = text.split()
    if is_url(text) or PRICE_ONLY.match(text) or LEGAL_RE.search(text):
        return True
    return len(words) <= 8 and bool(DOMAIN_IN_LINE.search(text))


def is_cta(text: str) -> bool:
    t = re.sub(r"[^\w\s'’]", "", text).strip().lower()
    if t in CTA_EXACT:
        return True
    return len(t.split()) <= 4 and bool(CTA_RE.match(text.strip()))


def looks_like_prose(text: str) -> bool:
    """Do these characters look like copy someone wrote, or like OCR noise?

    Tesseract handed a photograph returns confident-looking debris — `she Sy
    Wea aR ee ore` at 47% — and a row like that would land verbatim in the
    analyst's vocabulary corpus. Two cheap signals separate it from ad copy
    without a dictionary: real words carry vowels and consistent casing, and
    real sentences average well over three characters a token. Noise fragments
    average about two.
    """
    toks = re.findall(r"[A-Za-z][A-Za-z'’\-]*", text)
    if not toks:
        # Numbers only ("$1,299 · 40% off") is legitimate ad furniture.
        return bool(re.search(r"\d", text))
    good = 0
    for t in toks:
        if t.lower() in SHORT_WORDS:
            good += 1
        elif len(t) >= 3 and (set(t) & VOWELS) and not MIXED_CAPS.match(t):
            good += 1
    mean_len = sum(len(t) for t in toks) / len(toks)
    if len(toks) >= 5 and mean_len < 3.0:
        return False
    return good / len(toks) >= 0.5


def assemble(lines: list[dict]) -> dict:
    """Turn positioned lines into headline / description / cta / other_text.

    Geometry does the work a vision model was doing: the largest type is the
    headline, body-sized type under it is the description, a short imperative
    is the button, and everything else (display URL, price, legal) is
    other_text. No interpretation, no paraphrase — every character that came
    off the image lands in exactly one field.
    """
    lines = [dict(l, text=strip_chrome(l["text"]), _i=i)
             for i, l in enumerate(lines)]  # _i: identity, dicts compare by value
    lines = [l for l in lines if not is_junk(l["text"])]
    if not lines:
        return {"headline": "", "description": "", "cta": "", "other": [],
                "conf": 0.0, "text": ""}

    all_text = " ".join(l["text"] for l in lines)
    chars = sum(len(l["text"]) for l in lines) or 1
    conf = sum(l["conf"] * len(l["text"]) for l in lines) / chars

    # 1. Headline: the biggest type on the render. Ties (a wrapped headline is
    #    two lines of identical size) are broken by position — the topmost line
    #    seeds it — and the block then grows in both directions through lines
    #    of the same size sitting directly above or below.
    #    Only display URLs are barred from being the headline: on a travel ad
    #    whose largest element is `$149`, the price *is* the headline, and the
    #    transcription contract is "the largest/most prominent text".
    body = [l for l in lines if not is_url(l["text"])] or list(lines)
    head_h = max(l["h"] for l in body)
    seed = min((l for l in body if l["h"] >= 0.85 * head_h),
               key=lambda l: l["y0"])
    head_lines = [seed]
    order = sorted(lines, key=lambda l: l["y0"])
    idx = [l["_i"] for l in order].index(seed["_i"])

    def joinable(l, prev):
        # Same size (the estimate carries a few percent of noise), same column,
        # and not a button or a URL — those are their own fields.
        return (abs(l["h"] - prev["h"]) <= 0.18 * prev["h"]
                and abs(l["x0"] - prev["x0"]) <= 1.5 * prev["h"]
                and not is_url(l["text"]) and not is_cta(l["text"]))

    for l in order[idx + 1:]:
        prev = head_lines[-1]
        if joinable(l, prev) and 0 <= (l["y0"] - prev["y1"]) <= 1.2 * prev["h"]:
            head_lines.append(l)
        else:
            break
    for l in reversed(order[:idx]):
        prev = head_lines[0]
        if joinable(l, prev) and 0 <= (prev["y0"] - l["y1"]) <= 1.2 * prev["h"]:
            head_lines.insert(0, l)
        else:
            break
    headline = " ".join(l["text"] for l in head_lines)

    taken = {l["_i"] for l in head_lines}
    rest = [l for l in order if l["_i"] not in taken]

    # 2. Anything *above* the headline is the ad's chrome, not its pitch. In
    #    Google's own text-ad render that band is the logo, the advertiser's
    #    name and the display URL, in that order — and left in the body it
    #    prefixes almost every description with the brand name ("HubSpot
    #    Eliminate friction, bring tools together…"), which would then read as
    #    the advertiser's chosen copy in the vocabulary analysis. The pitch
    #    starts at the headline; everything before it is other_text.
    head_top = min(l["y0"] for l in head_lines)
    above = [l for l in rest if l["y1"] <= head_top]
    taken |= {l["_i"] for l in above}
    rest = [l for l in rest if l["_i"] not in taken]

    # 3. Display URLs, prices and the button text come out of the body next.
    meta = [l for l in rest if is_meta(l["text"])]
    taken |= {l["_i"] for l in meta}
    rest = [l for l in rest if l["_i"] not in taken]
    # A button is set smaller than the headline — this is what stops `Learn` in
    # a stacked `Learn / Spanish / Fast` headline from being read as a CTA.
    cta_lines = [l for l in rest if l["h"] < 0.85 * head_h and is_cta(l["text"])]
    cta = cta_lines[0]["text"] if cta_lines else ""
    extra_cta = [l["text"] for l in cta_lines[1:]]
    taken |= {l["_i"] for l in cta_lines}
    rest = [l for l in rest if l["_i"] not in taken]

    # 4. What is left splits by type size: body copy vs the fine print. The
    #    threshold is relative to this ad's own body size, so it holds whether
    #    the render is a 300x250 banner or a 1200px hero.
    desc_lines, small = rest, []
    if len(rest) >= 3:
        med = statistics.median([l["h"] for l in rest])
        desc_lines = [l for l in rest if l["h"] >= 0.7 * med]
        keep = {l["_i"] for l in desc_lines}
        small = [l for l in rest if l["_i"] not in keep]

    description = " ".join(l["text"] for l in desc_lines)
    other = ([l["text"] for l in above] + [l["text"] for l in meta]
             + extra_cta + [l["text"] for l in small])
    return {"headline": headline, "description": description, "cta": cta,
            "other": other, "conf": conf, "text": all_text}


def verdict(read: dict, min_conf: float) -> str:
    """ok | low_conf | gibberish | no_text — what the row is worth."""
    # Fewer than six readable characters is a photograph with a stray glyph on
    # it, not an ad with copy — say so instead of publishing `ats` as an ad.
    if len(re.findall(r"[A-Za-z0-9]", read["text"])) < 6:
        return "no_text"
    if read["conf"] < IMAGE_CONF_HARD:
        return "gibberish"
    if len(read["text"]) >= 8 and not looks_like_prose(read["text"]):
        return "gibberish"
    return "ok" if read["conf"] >= min_conf else "low_conf"


# --------------------------------------------------------------- the run

def load_index(cdir: str) -> dict:
    """creative_id → advertiser title, from the index.csv the ads downloader
    writes next to the PNGs."""
    path = os.path.join(cdir, "index.csv")
    out = {}
    if not os.path.isfile(path):
        return out
    with open(path, newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            cid = (r.get("creative_id") or "").strip()
            if cid:
                out[cid] = (r.get("title") or "").strip()
    return out


def existing_ids(path: str) -> set:
    if not os.path.isfile(path):
        return set()
    with open(path, newline="", encoding="utf-8") as f:
        return {(r.get("creative_id") or "").strip()
                for r in csv.DictReader(f)}


def ocr_one(png: str, engine: str, psms: list[int], lang: str, min_conf: float,
            tmpdir: str, timeout: float = 25.0,
            sweep: bool = True) -> tuple[dict, str, dict]:
    """One image → (row-fields, verdict, read). Never raises: a broken asset
    becomes an ILLEGIBLE row so the count of creatives always matches."""
    try:
        lines = read_lines(png, engine, psms, lang, tmpdir, timeout, sweep)
    except subprocess.TimeoutExpired:
        return ({"headline": "ILLEGIBLE", "description": "", "cta": "",
                 "other_text": f"OCR timed out after {timeout:g}s"}, "timeout",
                {"conf": 0.0, "text": ""})
    except Exception as e:  # noqa: BLE001
        return ({"headline": "ILLEGIBLE", "description": "", "cta": "",
                 "other_text": f"OCR failed: {e}"}, "error",
                {"conf": 0.0, "text": ""})
    read = assemble(lines)
    v = verdict(read, min_conf)
    if v == "no_text":
        fields = {"headline": "ILLEGIBLE", "description": "", "cta": "",
                  "other_text": "no text detected in the render"}
    elif v == "gibberish":
        # Keep what was read so a human (or the fallback transcriber) can see
        # what confused it, but never let it into the vocabulary analysis:
        # ILLEGIBLE in the headline is the charts' skip signal.
        fields = {"headline": "ILLEGIBLE", "description": "", "cta": "",
                  "other_text": f"unverified OCR read: {read['text'][:300]}"}
    else:
        fields = {"headline": read["headline"], "description": read["description"],
                  "cta": read["cta"], "other_text": "; ".join(read["other"])}
    return fields, v, read


def process_dir(cdir: str, run: str, engine: str, args) -> dict:
    """OCR every new PNG in one creatives dir; append rows; return a summary."""
    pngs = sorted(p for p in os.listdir(cdir) if p.lower().endswith(".png"))
    name = os.path.basename(cdir.rstrip("/"))
    out_csv = os.path.join(run, "raw", "ad_copy", f"ocr-{name}.csv")
    done = set() if args.redo else existing_ids(out_csv)
    todo = [p for p in pngs if os.path.splitext(p)[0] not in done]
    summary = {"dir": name, "csv": os.path.relpath(out_csv, run),
               "images": len(pngs), "new": len(todo), "skipped_done": len(pngs) - len(todo),
               "rows": 0, "verdicts": {}, "review": [], "cleared": []}
    if not todo:
        return summary

    titles = load_index(cdir)
    rows = []
    with tempfile.TemporaryDirectory() as tmpdir:
        def work(fname):
            cid = os.path.splitext(fname)[0]
            png = os.path.join(cdir, fname)
            if os.path.getsize(png) == 0:
                return cid, png, ({"headline": "ILLEGIBLE", "description": "",
                                   "cta": "", "other_text": "empty image file"},
                                  "no_text", {"conf": 0.0, "text": ""})
            return cid, png, ocr_one(png, engine, args.psm, args.lang,
                                     args.min_conf, tmpdir, args.timeout,
                                     not args.no_sweep)

        with ThreadPoolExecutor(max_workers=args.jobs) as pool:
            for cid, png, (fields, v, read) in pool.map(work, todo):
                summary["verdicts"][v] = summary["verdicts"].get(v, 0) + 1
                conf = round(read.get("conf", 0.0), 1)
                rows.append({
                    "creative_id": cid,
                    "advertiser_title": titles.get(cid, ""),
                    **fields,
                    "extraction": f"ocr:{engine}" + ("" if v == "ok" else f":{v}"),
                    "ocr_conf": conf,
                })
                if v == "ok":
                    summary["cleared"].append(cid)
                else:
                    summary["review"].append({
                        "creative_id": cid,
                        "png": os.path.relpath(png, run),
                        "advertiser_title": titles.get(cid, ""),
                        "reason": v, "ocr_conf": conf,
                        "text_preview": read.get("text", "")[:160],
                    })

    rows.sort(key=lambda r: r["creative_id"])
    fresh = not os.path.isfile(out_csv) or args.redo
    os.makedirs(os.path.dirname(out_csv), exist_ok=True)
    with open(out_csv, "w" if fresh else "a", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=AD_COPY_HEADER)
        if fresh:
            w.writeheader()
        w.writerows(rows)
    summary["rows"] = len(rows)
    return summary


def merge_review(run: str, entries: list[dict], engine_version: str,
                 path: str, cleared: set = frozenset()) -> int:
    """Keep one review list per run: what the fallback transcriber should be
    pointed at, and nothing that a later re-run read cleanly."""
    old = {}
    if os.path.isfile(path):
        try:
            with open(path, encoding="utf-8") as f:
                for e in json.load(f).get("review", []):
                    old[e.get("creative_id")] = e
        except (json.JSONDecodeError, OSError):
            pass
    for cid in cleared:  # a --redo that read it properly retires the entry
        old.pop(cid, None)
    for e in entries:
        old[e["creative_id"]] = e
    keep = [e for e in old.values()]
    keep.sort(key=lambda e: (e.get("reason", ""), e.get("creative_id", "")))
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump({"generated": now(), "engine": engine_version,
                   "note": "creatives OCR could not read — send these, and only "
                           "these, to a Haiku transcriber (agents/transcriber.md)",
                   "review": keep}, f, indent=2)
    return len(keep)


def self_test(engine: str, args) -> int:
    """OCR the shipped fixtures and check the expected words come back.

    Engines vary by version and language pack; this answers 'is OCR good
    enough on this machine?' in two seconds, before a run depends on it.
    """
    here = os.path.dirname(os.path.abspath(__file__))
    fdir = os.path.join(os.path.dirname(here), "assets", "ocr-selftest")
    spec_path = os.path.join(fdir, "expected.json")
    if not os.path.isfile(spec_path):
        die(f"fixtures missing: {spec_path}")
    with open(spec_path, encoding="utf-8") as f:
        spec = json.load(f)
    failures = 0
    with tempfile.TemporaryDirectory() as tmpdir:
        for case in spec["cases"]:
            png = os.path.join(fdir, case["file"])
            fields, v, read = ocr_one(png, engine, args.psm, args.lang,
                                      args.min_conf, tmpdir, args.timeout,
                                     not args.no_sweep)
            blob = " ".join([fields["headline"], fields["description"],
                             fields["cta"], fields["other_text"]]).lower()
            missing = [w for w in case["expect_words"] if w.lower() not in blob]
            field_bad = [k for k, want in case.get("expect_fields", {}).items()
                         if want.lower() not in (fields[k] or "").lower()]
            want_v = case.get("expect_verdict")
            ok = not missing and not field_bad and (not want_v or want_v == v)
            failures += 0 if ok else 1
            print(f"{'PASS' if ok else 'FAIL'} {case['file']:<24} "
                  f"conf={read['conf']:5.1f} verdict={v}")
            if missing:
                print(f"     missing words: {', '.join(missing)}")
            for k in field_bad:
                print(f"     {k}: expected ~{case['expect_fields'][k]!r}, "
                      f"got {fields[k]!r}")
            if want_v and want_v != v:
                print(f"     verdict: expected {want_v}, got {v}")
    print(f"\n{len(spec['cases']) - failures}/{len(spec['cases'])} fixtures read"
          f" correctly with {engine}.")
    if failures:
        print("A failing fixture means this engine install is weak — either fix "
              "it (language pack? Pillow for upscaling?) or run the Haiku "
              "transcriber path instead.", file=sys.stderr)
    return 1 if failures else 0


def main():
    ap = argparse.ArgumentParser(
        description="OCR downloaded ad creatives into ad_copy rows (free, local).")
    ap.add_argument("--run", help="run directory (research/demandcheck/<slug>)")
    ap.add_argument("--dir", action="append", default=[], metavar="NAME",
                    help="only this creatives subdir (repeatable; default: all)")
    ap.add_argument("--engine", choices=["auto", "tesseract", "rapidocr"],
                    default="auto")
    ap.add_argument("--psm", default="3", metavar="LIST",
                    help="tesseract page-segmentation modes to try, best read "
                         "wins (default 3, automatic layout). Adding 6 or 11 "
                         "costs ~50%% more time and, with the gap sweep on, "
                         "measured no better on this repo's benchmark.")
    ap.add_argument("--lang", default="eng", help="tesseract language (default eng)")
    ap.add_argument("--min-conf", type=float, default=65.0,
                    help="below this mean confidence a row is flagged for the "
                         "fallback transcriber (default 65)")
    ap.add_argument("--jobs", type=int, default=min(8, (os.cpu_count() or 2)),
                    help="parallel images (default: min(8, cpus))")
    ap.add_argument("--timeout", type=float, default=25.0, metavar="SECS",
                    help="give up on one image after this long and flag it for "
                         "the transcriber (default 25)")
    ap.add_argument("--no-sweep", action="store_true",
                    help="skip the second look at regions the layout analyser "
                         "skipped (faster, misses CTA buttons)")
    ap.add_argument("--redo", action="store_true",
                    help="re-read creatives already in the output CSV")
    ap.add_argument("--self-test", action="store_true",
                    help="check the engine against the shipped fixtures and exit")
    args = ap.parse_args()
    try:
        args.psm = [int(p) for p in str(args.psm).replace(" ", "").split(",") if p]
    except ValueError:
        die(f"--psm must be a comma-separated list of integers, got {args.psm!r}")
    if not args.psm:
        die("--psm needs at least one mode")

    engine, version = detect_engine(args.engine)
    if args.self_test:
        sys.exit(self_test(engine, args))
    if not args.run:
        die("--run is required (or use --self-test)")
    run = args.run
    if not os.path.isfile(os.path.join(run, "state.json")):
        die(f"no state.json in {run} — is that the run directory?")
    croot = os.path.join(run, "creatives")
    if not os.path.isdir(croot):
        die(f"no creatives directory in {run} — nothing downloaded yet")
    dirs = [os.path.join(croot, d) for d in sorted(os.listdir(croot))
            if os.path.isdir(os.path.join(croot, d))]
    if args.dir:
        want = {d.rstrip("/") for d in args.dir}
        dirs = [d for d in dirs if os.path.basename(d) in want]
        if not dirs:
            die(f"none of {sorted(want)} under {croot}")
    if not dirs:
        die(f"no creative subdirectories under {croot}")

    t0 = time.time()
    summaries, review, cleared = [], [], set()
    for cdir in dirs:
        s = process_dir(cdir, run, engine, args)
        review += s.pop("review")
        cleared |= set(s.pop("cleared"))
        summaries.append(s)
    review_path = os.path.join(run, "raw", "ad_copy", "ocr-review.json")
    pending = merge_review(run, review, version, review_path, cleared)
    elapsed = time.time() - t0

    imgs = sum(s["new"] for s in summaries)
    rows = sum(s["rows"] for s in summaries)
    verdicts = {}
    for s in summaries:
        for k, n in s["verdicts"].items():
            verdicts[k] = verdicts.get(k, 0) + n
    files = [s["csv"] for s in summaries if s["rows"]]
    print(json.dumps({
        "engine": version, "images_read": imgs, "rows_written": rows,
        "skipped_already_done": sum(s["skipped_done"] for s in summaries),
        "verdicts": verdicts, "seconds": round(elapsed, 1),
        "images_per_second": round(imgs / elapsed, 1) if elapsed and imgs else 0,
        "cost_usd": 0.0, "files": files,
        "needs_transcriber": pending,
        "review_list": os.path.relpath(review_path, run),
    }, indent=2))
    if pending:
        print(f"\n{pending} creative(s) OCR could not read → spawn ~1 Haiku "
              f"transcriber per 25 of them, images listed in "
              f"{os.path.relpath(review_path, run)}", file=sys.stderr)


if __name__ == "__main__":
    main()
