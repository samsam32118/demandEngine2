#!/usr/bin/env python3
"""Generate a varied synthetic ad-creative benchmark with ground truth.

Covers the layouts a Google ad library actually returns: search text ads,
display banners in every IAB size, dark mode, buttons, price lines, display
URLs, sitelinks, app-install ads, photo overlays, low contrast, serif faces.
"""
import json, os, random
from PIL import Image, ImageDraw, ImageFont, ImageFilter

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "creatives")
LIB = "/usr/share/fonts/truetype/liberation/LiberationSans-{}.ttf"
SERIF = "/usr/share/fonts/truetype/liberation/LiberationSerif-{}.ttf"
NARROW = "/usr/share/fonts/truetype/liberation/LiberationSansNarrow-{}.ttf"


def f(sz, bold=False, fam=LIB):
    p = fam.format("Bold" if bold else "Regular")
    if not os.path.isfile(p):
        p = LIB.format("Bold" if bold else "Regular")
    return ImageFont.truetype(p, sz)


CASES = []


def case(name, img, headline, description, cta, other, verdict="ok"):
    img.save(os.path.join(OUT, f"{name}.png"))
    CASES.append({"file": f"{name}.png", "headline": headline,
                  "description": description, "cta": cta, "other": other,
                  "verdict": verdict})


def noise_bg(w, h, lo, hi, seed):
    random.seed(seed)
    im = Image.new("RGB", (w, h))
    px = im.load()
    for y in range(h):
        for x in range(w):
            v = random.randint(lo, hi)
            px[x, y] = (v, int(v * 0.8), int(v * 0.6))
    return im.filter(ImageFilter.GaussianBlur(2))


def build():
    os.makedirs(OUT, exist_ok=True)
    for old in os.listdir(OUT):
        os.remove(os.path.join(OUT, old))

    # 1. Classic Google search text ad
    im = Image.new("RGB", (600, 250), "white"); d = ImageDraw.Draw(im)
    d.text((22, 20), "Ad", font=f(15, True), fill="#202124")
    d.text((48, 20), "· hubspot.com/crm/free", font=f(15), fill="#202124")
    d.text((22, 52), "Free CRM Software For Small", font=f(28), fill="#1a0dab")
    d.text((22, 88), "Teams", font=f(28), fill="#1a0dab")
    d.text((22, 140), "Track every deal in one pipeline. No credit card, no",
           font=f(17), fill="#4d5156")
    d.text((22, 164), "seat limits, free forever.", font=f(17), fill="#4d5156")
    d.text((22, 204), "Get Started Free", font=f(16, True), fill="#1a73e8")
    case("01-search-text-ad", im, "Free CRM Software For Small Teams",
         "Track every deal in one pipeline. No credit card, no seat limits, free forever.",
         "Get Started Free", ["hubspot.com/crm/free"])

    # 2. Search ad with sitelinks
    im = Image.new("RGB", (620, 300), "white"); d = ImageDraw.Draw(im)
    d.text((22, 18), "Sponsored - shopify.com", font=f(14), fill="#5f6368")
    d.text((22, 48), "Start Your Online Store Today", font=f(27), fill="#1a0dab")
    d.text((22, 96), "Everything you need to sell online, in person and on social.",
           font=f(16), fill="#4d5156")
    d.text((22, 120), "3 day free trial then $1 a month.", font=f(16), fill="#4d5156")
    d.text((22, 176), "Pricing Plans", font=f(15), fill="#1a0dab")
    d.text((160, 176), "Free Themes", font=f(15), fill="#1a0dab")
    d.text((300, 176), "POS Systems", font=f(15), fill="#1a0dab")
    case("02-search-sitelinks", im, "Start Your Online Store Today",
         "Everything you need to sell online, in person and on social. 3 day free trial then $1 a month.",
         "", ["shopify.com"])

    # 3. 300x250 dark banner, button CTA, price + domain footer
    im = Image.new("RGB", (300, 250), "#0f172a"); d = ImageDraw.Draw(im)
    d.text((18, 24), "Sleep Cooler", font=f(30, True), fill="white")
    d.text((18, 62), "All Summer", font=f(30, True), fill="white")
    d.text((18, 118), "Cooling mattress with 100", font=f(13), fill="#cbd5e1")
    d.text((18, 136), "night risk free trial.", font=f(13), fill="#cbd5e1")
    d.rectangle([18, 170, 150, 204], fill="#38bdf8")
    d.text((38, 179), "Shop Now", font=f(16, True), fill="#0f172a")
    d.text((18, 222), "From $899 · sleepcool.com", font=f(11), fill="#94a3b8")
    case("03-banner-300x250", im, "Sleep Cooler All Summer",
         "Cooling mattress with 100 night risk free trial.",
         "Shop Now", ["From $899 · sleepcool.com"])

    # 4. 728x90 leaderboard: logo | headline | button (horizontal layout)
    im = Image.new("RGB", (728, 90), "#fef3c7"); d = ImageDraw.Draw(im)
    d.text((20, 34), "ACME", font=f(24, True), fill="#92400e")
    d.text((140, 22), "Business Insurance From $29 A Month", font=f(22, True), fill="#1c1917")
    d.text((140, 54), "Get a quote in under three minutes.", font=f(15), fill="#57534e")
    d.rectangle([580, 28, 700, 62], fill="#b45309")
    d.text((602, 37), "Get Quote", font=f(15, True), fill="white")
    case("04-leaderboard-728x90", im, "Business Insurance From $29 A Month",
         "Get a quote in under three minutes.", "Get Quote", ["ACME"])

    # 5. 160x600 skyscraper, narrow column
    im = Image.new("RGB", (160, 600), "white"); d = ImageDraw.Draw(im)
    d.rectangle([0, 0, 159, 599], outline="#e5e7eb")
    d.text((14, 40), "Learn", font=f(26, True, NARROW), fill="#111827")
    d.text((14, 72), "Spanish", font=f(26, True, NARROW), fill="#111827")
    d.text((14, 104), "Fast", font=f(26, True, NARROW), fill="#111827")
    d.text((14, 170), "Ten minutes a", font=f(13), fill="#4b5563")
    d.text((14, 188), "day is enough.", font=f(13), fill="#4b5563")
    d.rectangle([14, 240, 146, 274], fill="#16a34a")
    d.text((36, 249), "Try Free", font=f(14, True), fill="white")
    d.text((14, 560), "lingoapp.com", font=f(11), fill="#9ca3af")
    case("05-skyscraper-160x600", im, "Learn Spanish Fast",
         "Ten minutes a day is enough.", "Try Free", ["lingoapp.com"])

    # 6. Big social square, headline over photo, button
    im = noise_bg(600, 600, 30, 90, 5); d = ImageDraw.Draw(im)
    d.rectangle([0, 330, 599, 599], fill=(17, 24, 39))
    d.text((36, 360), "Your Kitchen,", font=f(46, True), fill="white")
    d.text((36, 412), "Renovated In A Week", font=f(46, True), fill="white")
    d.text((36, 486), "Fixed price quotes from vetted local fitters.",
           font=f(20), fill="#d1d5db")
    d.rectangle([36, 526, 210, 570], fill="#f59e0b")
    d.text((60, 538), "Book A Visit", font=f(18, True), fill="#1f2937")
    case("06-social-square", im, "Your Kitchen, Renovated In A Week",
         "Fixed price quotes from vetted local fitters.", "Book A Visit", [])

    # 7. App install ad with rating text
    im = Image.new("RGB", (400, 400), "white"); d = ImageDraw.Draw(im)
    d.rounded_rectangle([150, 40, 250, 140], 22, fill="#7c3aed")
    d.text((178, 74), "Fit", font=f(34, True), fill="white")
    d.text((100, 170), "FitPlan Workouts", font=f(26, True), fill="#111827")
    d.text((132, 210), "4.8 stars · 120K ratings", font=f(14), fill="#6b7280")
    d.text((78, 246), "Personal training plans that adapt", font=f(15), fill="#374151")
    d.text((110, 268), "to the equipment you own.", font=f(15), fill="#374151")
    d.rounded_rectangle([140, 306, 260, 348], 8, fill="#7c3aed")
    d.text((168, 317), "Install", font=f(17, True), fill="white")
    case("07-app-install", im, "FitPlan Workouts",
         "Personal training plans that adapt to the equipment you own.",
         "Install", ["4.8 stars · 120K ratings"])

    # 8. All caps + fine print
    im = Image.new("RGB", (640, 360), "#111827"); d = ImageDraw.Draw(im)
    d.text((32, 48), "BLACK FRIDAY", font=f(48, True), fill="#fbbf24")
    d.text((32, 108), "50% OFF EVERYTHING", font=f(38, True), fill="white")
    d.text((32, 186), "Every frame, every lens, both pairs. Ends Monday night.",
           font=f(19), fill="#e5e7eb")
    d.text((32, 250), "Shop The Sale", font=f(20, True), fill="#fbbf24")
    d.text((32, 320), "Terms apply. Excludes prescription sunglasses.",
           font=f(12), fill="#6b7280")
    case("08-allcaps-fineprint", im, "BLACK FRIDAY",
         "Every frame, every lens, both pairs. Ends Monday night.",
         "Shop The Sale", ["Terms apply. Excludes prescription sunglasses."])

    # 9. No CTA at all
    im = Image.new("RGB", (500, 300), "#ecfdf5"); d = ImageDraw.Draw(im)
    d.text((28, 60), "Solar Panels Paid Monthly", font=f(30, True), fill="#065f46")
    d.text((28, 130), "No upfront cost. Average household saves", font=f(17), fill="#047857")
    d.text((28, 154), "1,100 pounds a year on bills.", font=f(17), fill="#047857")
    d.text((28, 240), "brightroof.co.uk", font=f(14), fill="#10b981")
    case("09-no-cta", im, "Solar Panels Paid Monthly",
         "No upfront cost. Average household saves 1,100 pounds a year on bills.",
         "", ["brightroof.co.uk"])

    # 10. Two CTAs
    im = Image.new("RGB", (520, 300), "white"); d = ImageDraw.Draw(im)
    d.text((26, 44), "New Season Running Shoes", font=f(28, True), fill="#0f172a")
    d.text((26, 110), "Carbon plate racers and daily trainers, in stock.",
           font=f(16), fill="#475569")
    d.rectangle([26, 170, 176, 210], fill="#0f172a")
    d.text((58, 180), "Shop Men", font=f(16, True), fill="white")
    d.rectangle([196, 170, 366, 210], fill="#0f172a")
    d.text((226, 180), "Shop Women", font=f(16, True), fill="white")
    case("10-two-ctas", im, "New Season Running Shoes",
         "Carbon plate racers and daily trainers, in stock.",
         "Shop Men", ["Shop Women"])

    # 11. Price is the biggest thing on the ad
    im = Image.new("RGB", (400, 300), "white"); d = ImageDraw.Draw(im)
    d.text((28, 30), "Flights To Lisbon", font=f(22, True), fill="#334155")
    d.text((28, 78), "$149", font=f(64, True), fill="#dc2626")
    d.text((28, 168), "One way from Boston, October dates.", font=f(15), fill="#475569")
    d.rectangle([28, 210, 158, 248], fill="#dc2626")
    d.text((54, 220), "See Dates", font=f(15, True), fill="white")
    case("11-price-hero", im, "$149",
         "One way from Boston, October dates.", "See Dates", ["Flights To Lisbon"])

    # 12. URL on top, headline below
    im = Image.new("RGB", (560, 260), "white"); d = ImageDraw.Draw(im)
    d.text((24, 22), "www.leakfixers.com/emergency", font=f(15), fill="#0f766e")
    d.text((24, 62), "Emergency Plumber Near You", font=f(30, True), fill="#0f172a")
    d.text((24, 130), "Burst pipe? We are 30 minutes away, 24 hours a day.",
           font=f(17), fill="#334155")
    d.text((24, 190), "Call Now", font=f(18, True), fill="#0f766e")
    case("12-url-on-top", im, "Emergency Plumber Near You",
         "Burst pipe? We are 30 minutes away, 24 hours a day.",
         "Call Now", ["www.leakfixers.com/emergency"])

    # 13. Low contrast grey on white
    im = Image.new("RGB", (500, 280), "white"); d = ImageDraw.Draw(im)
    d.text((26, 48), "Minimalist Watches", font=f(30, True), fill="#9ca3af")
    d.text((26, 120), "Swiss movement, sapphire glass, under 200 dollars.",
           font=f(16), fill="#b6bcc5")
    d.text((26, 200), "View Collection", font=f(16, True), fill="#9ca3af")
    case("13-low-contrast", im, "Minimalist Watches",
         "Swiss movement, sapphire glass, under 200 dollars.",
         "View Collection", [])

    # 14. Serif brand ad
    im = Image.new("RGB", (560, 300), "#fdf4ff"); d = ImageDraw.Draw(im)
    d.text((30, 50), "The Wine Club For", font=f(32, True, SERIF), fill="#4a044e")
    d.text((30, 92), "Curious Drinkers", font=f(32, True, SERIF), fill="#4a044e")
    d.text((30, 160), "Six bottles a month, chosen by a real sommelier.",
           font=f(18, False, SERIF), fill="#701a75")
    d.text((30, 226), "Join Now", font=f(18, True, SERIF), fill="#a21caf")
    d.text((30, 264), "cellarclub.com", font=f(13, False, SERIF), fill="#86198f")
    case("14-serif", im, "The Wine Club For Curious Drinkers",
         "Six bottles a month, chosen by a real sommelier.",
         "Join Now", ["cellarclub.com"])

    # 15. Text over photography, decent contrast
    im = noise_bg(640, 400, 20, 70, 9); d = ImageDraw.Draw(im)
    d.text((34, 120), "Hike More, Carry Less", font=f(40, True), fill="white")
    d.text((34, 190), "34 litre pack, 890 grams, lifetime warranty.",
           font=f(20), fill="#f1f5f9")
    d.rectangle([34, 250, 200, 296], fill="#ffffff")
    d.text((58, 262), "Shop Packs", font=f(18, True), fill="#111827")
    case("15-photo-overlay", im, "Hike More, Carry Less",
         "34 litre pack, 890 grams, lifetime warranty.", "Shop Packs", [])

    # 16. Video thumbnail style, small caption
    im = noise_bg(600, 338, 25, 75, 13); d = ImageDraw.Draw(im)
    d.ellipse([270, 130, 330, 190], fill=(255, 255, 255, 200))
    d.polygon([(292, 145), (292, 175), (316, 160)], fill="#111827")
    d.rectangle([0, 270, 599, 337], fill=(0, 0, 0))
    d.text((20, 286), "How Founders Hire Their First Salesperson",
           font=f(20, True), fill="white")
    d.text((20, 312), "Watch the 6 minute guide · closedeal.io",
           font=f(13), fill="#cbd5e1")
    case("16-video-thumb", im, "How Founders Hire Their First Salesperson",
         "", "", ["Watch the 6 minute guide · closedeal.io"])

    # 17. Photo only, no text
    case("17-photo-only", noise_bg(400, 400, 40, 160, 21), "", "", "", [],
         verdict="no_text")

    # 18. Tiny 9px type, 300x100
    im = Image.new("RGB", (300, 100), "white"); d = ImageDraw.Draw(im)
    d.text((10, 12), "Cheap Van Insurance", font=f(15, True), fill="#111827")
    d.text((10, 38), "Compare 40 insurers in one search.", font=f(9), fill="#4b5563")
    d.text((10, 54), "Average saving 218 pounds.", font=f(9), fill="#4b5563")
    d.text((10, 78), "Compare Now", font=f(10, True), fill="#1d4ed8")
    case("18-tiny-type", im, "Cheap Van Insurance",
         "Compare 40 insurers in one search. Average saving 218 pounds.",
         "Compare Now", [])

    with open(os.path.join(HERE, "truth.json"), "w") as fh:
        json.dump({"cases": CASES}, fh, indent=2)
    print(f"{len(CASES)} creatives → {OUT}")


if __name__ == "__main__":
    build()
