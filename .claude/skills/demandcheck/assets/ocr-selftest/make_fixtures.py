#!/usr/bin/env python3
"""Regenerate the OCR self-test fixtures.

The fixtures are *synthetic* ad renders — invented brands, drawn here — not
creatives scraped from Google's library. They mimic the four shapes
`ocr_creatives.py` has to survive: a search text ad, a small display banner, a
headline over photography, and a blank file. Needs Pillow; only run when the
fixtures need changing (the PNGs are committed).

    python3 .claude/skills/demandcheck/assets/ocr-selftest/make_fixtures.py
"""

import glob
import json
import os
import random

from PIL import Image, ImageDraw, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
FONTS = ["/usr/share/fonts/truetype/liberation/LiberationSans-{}.ttf",
         "/usr/share/fonts/truetype/dejavu/DejaVuSans{}.ttf"]


def font(size: int, bold: bool = False):
    for pat in FONTS:
        for style in ((("Bold",) if bold else ("Regular",)) if "Liberation" in pat
                      else (("-Bold",) if bold else ("",))):
            path = pat.format(style)
            if os.path.isfile(path):
                return ImageFont.truetype(path, size)
    return ImageFont.load_default()


def text_ad(path):
    """A Google search text ad as the transparency library renders it."""
    im = Image.new("RGB", (600, 260), "white")
    d = ImageDraw.Draw(im)
    d.rectangle([0, 0, 599, 259], outline="#dadce0")
    d.text((24, 24), "Ad", font=font(15, True), fill="#202124")
    d.text((52, 24), "· plunge.com/cold-plunge", font=font(15), fill="#202124")
    d.text((24, 60), "Cold Plunge Tubs Built For", font=font(30), fill="#1a0dab")
    d.text((24, 98), "Daily Recovery", font=font(30), fill="#1a0dab")
    d.text((24, 152), "Chiller cools to 39F in under an hour. Free shipping",
           font=font(18), fill="#4d5156")
    d.text((24, 178), "and a 30 day home trial on every tub.",
           font=font(18), fill="#4d5156")
    d.text((24, 216), "Shop Now", font=font(17, True), fill="#1a73e8")
    im.save(path)


def banner(path):
    """A 300x250 display banner — small type, a button, a price line."""
    im = Image.new("RGB", (300, 250), "#0b3d2e")
    d = ImageDraw.Draw(im)
    d.text((18, 26), "Recover", font=font(34, True), fill="white")
    d.text((18, 64), "Faster", font=font(34, True), fill="white")
    d.text((18, 120), "Ice bath therapy at home,", font=font(14), fill="#d1fae5")
    d.text((18, 140), "no plumbing required.", font=font(14), fill="#d1fae5")
    d.rectangle([18, 176, 148, 212], fill="#34d399")
    d.text((38, 186), "Learn More", font=font(16, True), fill="#062e22")
    d.text((18, 226), "From $1,299 · icebarrel.com", font=font(11), fill="#a7f3d0")
    im.save(path)


def photo_overlay(path):
    """Headline over photography — the hard case that keeps the fallback
    transcriber in the skill. Noise stands in for the photo."""
    random.seed(7)
    im = Image.new("RGB", (640, 360))
    px = im.load()
    for y in range(360):  # coarse noisy gradient
        for x in range(0, 640, 4):
            v = random.randint(40, 120) + int(y * 0.25)
            for dx in range(4):
                px[x + dx, y] = (v, v - 10, max(0, v - 40))
    d = ImageDraw.Draw(im)
    d.rectangle([0, 210, 639, 359], fill=(15, 23, 42))
    d.text((30, 232), "Sauna Kits Delivered", font=font(38, True), fill="white")
    d.text((30, 288), "Assemble in a weekend. 5 year warranty.",
           font=font(19), fill="#e2e8f0")
    d.text((30, 322), "redwoodoutdoors.com", font=font(15), fill="#94a3b8")
    im.save(path)


def blank(path):
    Image.new("RGB", (300, 250), "white").save(path)


EXPECTED = {
    "note": "Synthetic ad renders drawn by make_fixtures.py — not real Google "
            "creatives. Checked by `ocr_creatives.py --self-test`.",
    "cases": [
        {"file": "text-ad.png",
         "expect_words": ["cold plunge tubs", "recovery", "chiller",
                          "plunge.com", "shop now"],
         "expect_fields": {"headline": "Cold Plunge Tubs Built For",
                           "cta": "Shop Now"}},
        {"file": "banner-300x250.png",
         "expect_words": ["recover", "ice bath therapy", "1,299", "learn more"],
         "expect_fields": {"headline": "Recover", "cta": "Learn More"}},
        {"file": "photo-overlay.png",
         "expect_words": ["sauna kits delivered", "warranty",
                          "redwoodoutdoors.com"],
         "expect_fields": {"headline": "Sauna Kits Delivered"}},
        {"file": "blank.png", "expect_words": [], "expect_fields": {},
         "expect_verdict": "no_text"},
    ],
}


def main():
    for f in glob.glob(os.path.join(HERE, "*.png")):
        os.remove(f)
    text_ad(os.path.join(HERE, "text-ad.png"))
    banner(os.path.join(HERE, "banner-300x250.png"))
    photo_overlay(os.path.join(HERE, "photo-overlay.png"))
    blank(os.path.join(HERE, "blank.png"))
    with open(os.path.join(HERE, "expected.json"), "w", encoding="utf-8") as f:
        json.dump(EXPECTED, f, indent=2)
        f.write("\n")
    print(f"fixtures written to {HERE}")


if __name__ == "__main__":
    main()
