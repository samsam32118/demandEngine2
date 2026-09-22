#!/usr/bin/env python3
"""extract_site.py — turn fetched marketing HTML into structured claims. Stdlib only.

Positioning is an argument about what a product says it is versus what its
alternatives say they are, so the raw material of this skill is marketing copy:
hero headlines, feature bullets, pricing tiers, customer logos, and the
vocabulary a company chooses. Reading that out of HTML by hand costs a
thousand tokens a page and comes out inconsistent between competitors — which
is fatal, because the whole method depends on comparing like with like.

Usage:
    # one page
    extract_site.py page raw/site/acme-home.html --url https://acme.com --out extract/

    # every page banked for a domain, merged into one profile
    extract_site.py profile --dir raw/site --domain acme.com --out extract/

    # the vocabulary table across every profile (feeds the vocabulary chart)
    extract_site.py vocab --extract-dir extract/ --out clean/vocabulary_site.csv

What comes out is a candidate set, not a verdict: `claims` and `features` are
what the page asserts, and deciding which of them is a real attribute — let
alone a unique one — is the analyst's job against the competitor matrix.
"""

import argparse
import csv
import glob
import json
import os
import re
import sys
from collections import Counter
from html.parser import HTMLParser

# Words that carry no positioning signal. Kept deliberately small: marketing
# nouns like "platform" or "workflow" ARE the signal here, so only true
# function words and web furniture are dropped.
STOP = set("""a an and or the to of in on for with by at from as is are was were be been
being it its this that these those you your our we us they their he she his her i my me
if then than so but not no nor do does did done have has had can could will would shall
should may might must about into over under up down out off again more most other some
such only own same too very just now also all any each few both how what when where which
who whom why get got make makes made use used using via per vs versus plus etc""".split())

WEB_FURNITURE = set("""home login log sign signin signup register pricing blog careers press
contact support docs documentation privacy terms cookie cookies legal sitemap rss newsletter
menu close search subscribe follow twitter linkedin facebook instagram youtube github
copyright rights reserved reserved. english deutsch download app store google play""".split())

DROP_TAGS = {"script", "style", "noscript", "svg", "template", "iframe"}

PRICE_RE = re.compile(r"(?:^|[\s(])([$€£])\s?(\d[\d,]*(?:\.\d{2})?)\s*(?:/\s*|per\s+)?"
                      r"(mo|month|mth|yr|year|annually|user|seat|k)?", re.I)
TIER_RE = re.compile(r"^(free|freemium|starter|basic|essential|standard|plus|pro|"
                     r"professional|premium|team|teams|business|growth|scale|"
                     r"advanced|enterprise|custom|contact sales|unlimited)\b", re.I)

# "the <X> platform for <Y>" / "<X> software that <Y>" — how a company frames itself.
FRAME_NOUNS = (r"platform|software|tool|tools|app|system|solution|suite|service|os|"
               r"hub|workspace|engine|assistant|copilot|network|marketplace|crm|"
               r"database|dashboard|infrastructure|api|layer|studio|alternative|"
               r"replacement|cms|erp|ide|framework|library|extension|plugin|"
               r"agency|consultancy|community|course|newsletter|generator|tracker|"
               # the category nouns a company actually files itself under
               r"analytics|insights|intelligence|automation|scheduling|scheduler|"
               r"accounting|bookkeeping|payroll|invoicing|billing|hosting|monitoring|"
               r"observability|security|backup|storage|helpdesk|ticketing|inbox|"
               r"forms|surveys|wiki|notes|calendar|planner|tracker|builder|editor|"
               r"manager|management|optimizer|optimiser|router|proxy|gateway|"
               r"lms|ats|hris|dam|pim|esp|sso|iam|etl|bi|"
               # roles a product is sold as — the shape most AI products take
               r"coach|coaching|trainer|training|tutor|mentor|advisor|adviser|"
               r"analyst|recruiter|receptionist|scheduler|bookkeeper|"
               r"notetaker|recorder|transcriber|transcription|summarizer|"
               r"agent|agents|bot|chatbot|companion|sidekick|"
               "assistant")
# Two shapes, because companies name their category both ways:
#   "the <modifiers> <noun> for <audience>"  → the noun phrase before "for"
#   "a <modifiers> <noun>"                   → the noun phrase standing alone
FRAME_RE = re.compile(
    rf"\b((?:[\w\-]+\s+){{0,3}}(?:{FRAME_NOUNS}))\b", re.I)
FRAME_LEAD = re.compile(r"^(the|a|an|your|our|is|best|most|world'?s|only|new)\s+", re.I)

# A category noun on its own names no category — it needs a modifier in front
# of it to be a frame anyone could compete in.
GENERIC_NOUNS = set("""software platform tool tools app apps solution solutions
suite service services system alternative replacement product vs""".split())

CUSTOMER_HINT = re.compile(r"(logo|customer|client|brand|trusted|partner)", re.I)
FEATURE_HINT = re.compile(r"(feature|capabilit|what you|everything|benefit|why |built[- ]in|"
                          r"how it works|use case|module|includes)", re.I)


class Doc(HTMLParser):
    """A forgiving reader for marketing HTML: text with the structure that matters.

    Marketing pages are div soup, so tag nesting tells you little. What does
    survive is heading level, list membership, link text, and image alt text
    (where logo walls hide their customer names) — that is what this keeps.
    """

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.skip = 0
        self.stack = []
        self.buf = []
        self.headings = {"h1": [], "h2": [], "h3": [], "h4": []}
        self.items = []          # <li> text
        self.links = []          # (text, href)
        self.imgs = []           # alt text
        self.paras = []          # <p> text
        self.title = ""
        self.meta = {}
        self.blocks = []         # (context_class_id, text) — for section hints
        self._ctx = ""

    # -- helpers
    def _flush(self, tag):
        text = norm("".join(self.buf))
        self.buf = []
        if not text:
            return
        if tag in self.headings:
            self.headings[tag].append(text)
        elif tag == "li":
            self.items.append(text)
        elif tag == "p":
            self.paras.append(text)
        elif tag == "a":
            href = self.stack[-1][1].get("href", "") if self.stack else ""
            self.links.append((text, href))
        self.blocks.append((self._ctx, text))

    def handle_starttag(self, tag, attrs):
        d = dict(attrs)
        if tag in DROP_TAGS:
            self.skip += 1
            return
        if tag == "meta":
            name = (d.get("name") or d.get("property") or "").lower()
            if name in ("description", "og:description", "og:title", "twitter:description"):
                self.meta[name] = norm(d.get("content", ""))
            return
        if tag == "img":
            alt = norm(d.get("alt", ""))
            if alt:
                self.imgs.append((alt, f"{d.get('class','')} {d.get('src','')}"))
            return
        cls = f"{d.get('class','')} {d.get('id','')}".strip()
        if cls and tag in ("section", "div", "header", "main", "article", "aside", "footer"):
            self._ctx = cls[:160]
        self.stack.append((tag, d))
        if tag in self.headings or tag in ("li", "p", "a"):
            self.buf = []

    def handle_endtag(self, tag):
        if tag in DROP_TAGS:
            self.skip = max(0, self.skip - 1)
            return
        if tag in self.headings or tag in ("li", "p", "a"):
            self._flush(tag)
        while self.stack:
            t, _ = self.stack.pop()
            if t == tag:
                break

    def handle_data(self, data):
        if self.skip:
            return
        if self.stack and self.stack[-1][0] == "title":
            self.title = norm(self.title + " " + data)
            return
        self.buf.append(data)


def norm(text):
    return re.sub(r"\s+", " ", (text or "").replace(" ", " ")).strip()


def words(text):
    return [w for w in re.findall(r"[a-z][a-z0-9\-\+']*", (text or "").lower())
            if w not in STOP and w not in WEB_FURNITURE and len(w) > 2]


def ngrams(tokens, n):
    return [" ".join(tokens[i:i + n]) for i in range(len(tokens) - n + 1)]


def looks_like_claim(text):
    """A claim is a sentence-length assertion about what the product does.

    Nav labels and legal boilerplate are the noise this filters; a hero
    headline is typically 3-14 words with no trailing period.
    """
    n = len(text.split())
    if not (3 <= n <= 22):
        return False
    if text.count("|") or text.count("·") > 1:
        return False
    low = text.lower()
    if any(k in low for k in ("cookie", "all rights", "privacy policy", "terms of",
                              "©", "sign in", "log in", "read more", "learn more")):
        return False
    return bool(re.search(r"[a-z]", text))


# ------------------------------------------------------------------ page

def parse_page(html, url=""):
    d = Doc()
    try:
        d.feed(html)
    except Exception:
        pass  # forgiving by design: half a parse beats a crash on broken markup
    domain = re.sub(r"^https?://(www\.)?", "", url).split("/")[0] if url else ""

    heads = d.headings
    claims = []
    for tag in ("h1", "h2", "h3"):
        for t in heads[tag]:
            if looks_like_claim(t):
                claims.append({"text": t, "where": tag})
    for t in d.paras[:40]:
        if looks_like_claim(t) and len(t.split()) <= 18:
            claims.append({"text": t, "where": "p"})

    # Features: list items sitting under feature-ish headings or in feature-ish
    # sections. A page's <li> set is mostly navigation, so context is what
    # separates "Unlimited seats" from "Careers".
    features = []
    for ctx, text in d.blocks:
        if text in features or not (2 <= len(text.split()) <= 16):
            continue
        if FEATURE_HINT.search(ctx or "") and text in d.items:
            features.append(text)
    if len(features) < 4:  # fall back to the plausible <li>s anywhere on the page
        for t in d.items:
            if 2 <= len(t.split()) <= 14 and t not in features \
                    and not any(w in t.lower() for w in WEB_FURNITURE):
                features.append(t)

    pricing = []
    seen_tier = set()
    for ctx, text in d.blocks:
        m = PRICE_RE.search(text)
        tier = TIER_RE.match(text)
        if not (m or tier):
            continue
        label = tier.group(1).title() if tier else ""
        price = f"{m.group(1)}{m.group(2)}" if m else ""
        period = (m.group(3) or "").lower() if m else ""
        key = (label, price)
        if key in seen_tier or not (label or price):
            continue
        seen_tier.add(key)
        pricing.append({"tier": label, "price": price, "period": period, "context": text[:120]})

    customers = []
    for alt, meta in d.imgs:
        if CUSTOMER_HINT.search(meta or "") or CUSTOMER_HINT.search(alt):
            name = re.sub(r"\b(logo|logotype|icon|wordmark|brand)\b", "", alt, flags=re.I).strip(" -–—")
            if 2 <= len(name) <= 40 and name.lower() not in WEB_FURNITURE:
                customers.append(name)

    price_points = []
    for _ctx, text in d.blocks:
        if len(text) > 60:
            continue
        for m in PRICE_RE.finditer(text):
            pp = f"{m.group(1)}{m.group(2)}" + (f"/{m.group(3)}" if m.group(3) else "")
            if pp not in price_points:
                price_points.append(pp)

    frames = []
    title_tail = ""
    if d.title:
        parts = re.split(r"\s[|\u2013\u2014\u00b7\-]\s|:\s", d.title)
        if len(parts) > 1:
            title_tail = norm(parts[-1])
    for t in [d.title, title_tail, d.meta.get("description", ""),
              d.meta.get("og:description", "")] + \
             [c["text"] for c in claims[:12]]:
        for m in FRAME_RE.finditer(t or ""):
            phrase = norm(m.group(1)).lower()
            while FRAME_LEAD.match(phrase):
                phrase = FRAME_LEAD.sub("", phrase, count=1)
            toks = phrase.split()
            # Trim modifier words that are pure filler so "lightweight and
            # open-source google analytics alternative" lands as something a
            # human would actually call a category.
            while toks and toks[0] in STOP:
                toks = toks[1:]
            phrase = " ".join(toks)
            brand = re.split(r"[.\-]", domain)[0].lower() if domain else ""
            informative = [w for w in toks if w not in GENERIC_NOUNS]
            if brand and brand in toks:
                continue
            if 1 <= len(toks) <= 4 and phrase and informative:
                frames.append(phrase)

    if not frames and title_tail:
        toks = [w for w in title_tail.lower().split() if w not in STOP][-4:]
        if toks:
            frames.append(" ".join(toks))

    body = " ".join([d.title, d.meta.get("description", "")] +
                    [c["text"] for c in claims] + features + d.paras[:60])
    toks = words(body)
    phrases = Counter(toks)
    phrases.update(ngrams(toks, 2))
    phrases.update(ngrams(toks, 3))

    return {
        "url": url, "domain": domain, "title": d.title,
        "meta_description": d.meta.get("description") or d.meta.get("og:description", ""),
        "h1": heads["h1"][:6], "h2": heads["h2"][:25],
        "claims": dedupe_claims(claims)[:40],
        "features": dedupe(features)[:60],
        "pricing": pricing[:14],
        "price_points": price_points[:16],
        "customers": dedupe(customers)[:40],
        "self_frames": [f for f, _ in Counter(frames).most_common(8)],
        "phrases": dict(phrases.most_common(300)),
        "word_count": len(toks),
    }


def dedupe(seq):
    out, seen = [], set()
    for s in seq:
        k = re.sub(r"[^a-z0-9]", "", s.lower())
        if k and k not in seen:
            seen.add(k)
            out.append(s)
    return out


def dedupe_claims(claims):
    out, seen = [], set()
    for c in claims:
        k = re.sub(r"[^a-z0-9]", "", c["text"].lower())
        if k and k not in seen:
            seen.add(k)
            out.append(c)
    return out


# --------------------------------------------------------------- profile

def merge_profile(pages, domain):
    """One company, many pages → one profile. Pricing and customers come from
    whichever page has them; vocabulary is summed so a word used across the
    whole site outranks one used loudly on a single page."""
    prof = {
        "domain": domain, "pages": [p["url"] for p in pages],
        "title": "", "meta_description": "",
        "h1": [], "claims": [], "features": [], "pricing": [], "customers": [],
        "price_points": [],
        "self_frames": [], "phrases": {}, "word_count": 0,
    }
    phrases = Counter()
    frames = Counter()
    for p in sorted(pages, key=lambda p: (0 if p["url"].rstrip("/").count("/") <= 2 else 1)):
        prof["title"] = prof["title"] or p["title"]
        prof["meta_description"] = prof["meta_description"] or p["meta_description"]
        prof["h1"] += p["h1"]
        prof["claims"] += p["claims"]
        prof["features"] += p["features"]
        prof["pricing"] += p["pricing"]
        prof["customers"] += p["customers"]
        prof["price_points"] += [x for x in p.get("price_points", []) if x not in prof["price_points"]]
        phrases.update(p["phrases"])
        frames.update(p["self_frames"])
        prof["word_count"] += p["word_count"]
    prof["h1"] = dedupe(prof["h1"])[:8]
    prof["claims"] = dedupe_claims(prof["claims"])[:60]
    prof["features"] = dedupe(prof["features"])[:120]
    prof["customers"] = dedupe(prof["customers"])[:60]
    seen = set()
    prof["pricing"] = [p for p in prof["pricing"]
                       if not ((p["tier"], p["price"]) in seen or seen.add((p["tier"], p["price"])))][:16]
    prof["self_frames"] = [f for f, _ in frames.most_common(10)]
    prof["phrases"] = dict(phrases.most_common(400))
    return prof


# ------------------------------------------------------------------- cli

def read(path):
    with open(path, encoding="utf-8", errors="replace") as f:
        return f.read()


def cmd_page(a):
    doc = parse_page(read(a.html), a.url or "")
    os.makedirs(a.out, exist_ok=True)
    name = re.sub(r"[^a-z0-9]+", "-", (a.url or os.path.basename(a.html)).lower()).strip("-")[:70]
    path = os.path.join(a.out, f"page-{name}.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(doc, f, indent=2, ensure_ascii=False)
    print(json.dumps({"wrote": path, "claims": len(doc["claims"]),
                      "features": len(doc["features"]), "pricing": len(doc["pricing"]),
                      "customers": len(doc["customers"]),
                      "self_frames": doc["self_frames"][:4]}, indent=2))


def cmd_profile(a):
    pages = []
    pats = [os.path.join(a.dir, f"*{a.domain.replace('.', '-')}*.html"),
            os.path.join(a.dir, f"*{a.domain}*.html")]
    files = sorted({f for p in pats for f in glob.glob(p)})
    if not files:
        files = sorted(glob.glob(os.path.join(a.dir, "*.html")))
        files = [f for f in files if a.domain.split(".")[0] in os.path.basename(f).lower()]
    if not files:
        print(f"error: no banked HTML for {a.domain} under {a.dir}", file=sys.stderr)
        sys.exit(3)
    for fn in files:
        url = url_of(fn, a.domain)
        pages.append(parse_page(read(fn), url))
    prof = merge_profile(pages, a.domain)
    os.makedirs(a.out, exist_ok=True)
    path = os.path.join(a.out, f"{a.domain}.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(prof, f, indent=2, ensure_ascii=False)
    print(json.dumps({"wrote": path, "pages": len(files), "claims": len(prof["claims"]),
                      "features": len(prof["features"]), "pricing_rows": len(prof["pricing"]),
                      "customers": len(prof["customers"]),
                      "self_frames": prof["self_frames"][:5],
                      "top_phrases": list(prof["phrases"])[:12]}, indent=2))


def url_of(path, domain):
    """Recover the page URL from the banked filename, falling back to a sidecar
    .url file if the collector wrote one."""
    side = os.path.splitext(path)[0] + ".url"
    if os.path.isfile(side):
        return read(side).strip()
    base = os.path.splitext(os.path.basename(path))[0]
    slug = base.replace(domain.replace(".", "-"), "").strip("-")
    return f"https://{domain}/{slug}".rstrip("/")


def cmd_vocab(a):
    """The site-vocabulary table: which company uses which word, how loudly.

    This is half of the vocabulary chart — the other half is search volume,
    which `keywords.py search-volume` prices for these same terms."""
    profs = sorted(glob.glob(os.path.join(a.extract_dir, "*.json")))
    profs = [p for p in profs if not os.path.basename(p).startswith("page-")]
    if not profs:
        print(f"error: no profiles in {a.extract_dir}", file=sys.stderr)
        sys.exit(3)
    rows, domains = {}, []
    for path in profs:
        with open(path, encoding="utf-8") as f:
            prof = json.load(f)
        dom = prof["domain"]
        domains.append(dom)
        total = max(1, sum(prof["phrases"].values()))
        for term, n in prof["phrases"].items():
            if len(term.split()) > 3 or n < a.min_count:
                continue
            r = rows.setdefault(term, {"term": term, "used_by": set(), "total": 0})
            r["used_by"].add(dom)
            r["total"] += n
            r[f"n_{dom}"] = n
            r[f"per1k_{dom}"] = round(1000 * n / total, 2)
    os.makedirs(os.path.dirname(a.out) or ".", exist_ok=True)
    cols = ["term", "total_mentions", "used_by_count", "used_by"] + \
           [f"n_{d}" for d in domains] + [f"per1k_{d}" for d in domains]
    out = sorted(rows.values(), key=lambda r: (-len(r["used_by"]), -r["total"]))
    with open(a.out, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        for r in out[:a.limit]:
            r = dict(r)
            r["used_by_count"] = len(r["used_by"])
            r["used_by"] = ";".join(sorted(r["used_by"]))
            r["total_mentions"] = r.pop("total")
            w.writerow(r)
    shared = [r["term"] for r in out if len(r["used_by"]) == len(domains)][:15]
    print(json.dumps({"wrote": a.out, "terms": min(len(out), a.limit),
                      "domains": domains,
                      "used_by_everyone": shared,
                      "note": "terms every site uses are table-stakes vocabulary; "
                              "terms only one site uses are that company's own framing"},
                     indent=2))


def main():
    p = argparse.ArgumentParser(description="marketing HTML → structured positioning input")
    sub = p.add_subparsers(dest="cmd", required=True)

    a = sub.add_parser("page", help="parse one banked HTML file")
    a.add_argument("html"); a.add_argument("--url", default=""); a.add_argument("--out", default="extract")
    a.set_defaults(fn=cmd_page)

    b = sub.add_parser("profile", help="merge every banked page for a domain")
    b.add_argument("--dir", default="raw/site"); b.add_argument("--domain", required=True)
    b.add_argument("--out", default="extract")
    b.set_defaults(fn=cmd_profile)

    c = sub.add_parser("vocab", help="cross-company vocabulary table")
    c.add_argument("--extract-dir", default="extract")
    c.add_argument("--out", default="clean/vocabulary_site.csv")
    c.add_argument("--min-count", type=int, default=2); c.add_argument("--limit", type=int, default=800)
    c.set_defaults(fn=cmd_vocab)

    args = p.parse_args()
    args.fn(args)


if __name__ == "__main__":
    main()
