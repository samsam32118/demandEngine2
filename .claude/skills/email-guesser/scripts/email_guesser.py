#!/usr/bin/env python3
"""email-guesser — infer a company's email pattern and guess a person's address.

Evidence sources: direct HTTPS fetch of the company's own /contact, /about,
/team, /press pages (free), plus Bright Data SERP (paid, via the
`brightdata-serp` skill). Each SERP query is one billable BrightData call —
see `--max-queries` to cap spend per run.

Usage:
  email_guesser.py --domain acme.com [--first Jane --last Doe] [--pretty]
                   [--no-cache] [--max-queries 5] [--max-results-per-query 10]
                   [--skip-direct-fetch]

Emits a JSON object on stdout (always — even on errors, with an `error` key).

Exit codes:
  0  success
  2  bad args
  3  SERP subprocess failure after retries
  4  unexpected exception
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
import time
import unicodedata
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

# Repo root: .../rivas/.claude/skills/email-guesser/scripts/email_guesser.py
# parents: 0=scripts, 1=email-guesser, 2=skills, 3=.claude, 4=rivas
REPO = Path(__file__).resolve().parents[4]
CACHE_DIR = REPO / "workspace" / "cache" / "email-guesser"
SERP_SCRIPT = REPO / ".claude" / "skills" / "brightdata-serp" / "scripts" / "search.py"

CACHE_TTL_SECONDS = 14 * 24 * 3600

DIRECT_FETCH_PATHS = [
    "/", "/contact", "/contact-us", "/about", "/about-us",
    "/team", "/leadership", "/press",
]
DIRECT_FETCH_TIMEOUT = 3
DIRECT_FETCH_WORKERS = 8
USER_AGENT = "Rivas-Will-email-guesser/1.0"

SERP_QUERIES = [
    '"@{domain}" contact',
    '"@{domain}" press',
    # Self-restricted site search. Catches per-person bio pages that the
    # fixed DIRECT_FETCH_PATHS list misses — e.g. arcadeagroup.com/ryan-beaver/
    # is linked from /team but never directly visited. Google has already
    # indexed those pages; this query surfaces them without needing a
    # link-crawler.
    '"@{domain}" site:{domain}',
    '"@{domain}" site:github.com',
    '"@{domain}" site:sec.gov',
    '"@{domain}" investor relations',
]

# Name-seeded queries fire only when the caller supplies first+last. They are
# strong signal — SERP returns pages that mention the specific person, which
# is where their email format most often appears (conference bios, paper
# author lists, podcast guest notes, press quote-lines). Not counted against
# the domain-only cache because results would leak across different names.
SERP_NAME_QUERIES = [
    '"{first} {last}" "@{domain}"',
    '"{first} {last}" email "{domain}"',
]

# Third-party SEO-bait pages that publish <company>'s email pattern + share-%
# right in their SERP snippet body. Page itself is usually bot-protected, but
# the snippet is the payload. RocketReach is the only one that returns
# reliable machine-readable snippets — Pareto: one query, one regex, strong
# signal when it hits.
AGGREGATOR_QUERIES = [
    '"{domain}" "email format" site:rocketreach.co',
]

ROLE_LOCALS = {
    "info", "contact", "hello", "sales", "press", "support", "help", "hi",
    "team", "admin", "administrator", "administrators", "careers", "jobs",
    "pr", "media", "ir", "investor", "investors", "relations", "legal",
    "marketing", "billing", "conflicts", "export", "exports",
    "noreply", "no-reply", "office", "hr", "recruiting", "feedback",
    "enquiries", "inquiries",
    # Added after autodesk.com real-world run: regulator-inquiries,
    # board-administrator, dpo@, disclosure@ all slipped through as
    # non-role. Split-aware is_role_local() catches them via any-part match.
    "dpo", "privacy", "compliance", "security", "disclosure", "abuse",
    "dmca", "webmaster", "postmaster", "board", "ops", "operations",
    "privacyofficer", "compliance-officer",
    # Added after the batch run on 22 domains: tribute-technology surfaced
    # websites@, tributearchive surfaced accounting@.
    "websites", "accounting",
}

# Sentinel local-parts that aggregator sites (LeadIQ, RocketReach, SignalHire)
# use as placeholders in their example "email pattern" text. These are not
# real addresses — they're the literal words `first`, `last`, `firstlast`,
# etc. inserted into SEO-bait pages. Discovered during the 22-domain batch:
# `last@arcadeagroup.com` showed up as a LeadIQ placeholder.
BLACKLIST_LOCALS = {
    "first", "last", "firstname", "lastname",
    "firstlast", "lastfirst",
    "first.last", "last.first", "first_last", "first-last",
    "flast", "fl", "firstl", "lastf",
    "firstinitial", "firstinitiallast", "firstlastinitial",
    "example", "sample", "name",
}

PATTERN_TEMPLATES = [
    "{first}.{last}",
    "{first}",
    "{f}{last}",
    "{first}{last}",
    "{first}_{last}",
    "{first}-{last}",
    "{last}",
    "{last}.{first}",
    "{f}.{last}",
    "{first}{l}",
    "{last}{f}",
]

# Global prior probabilities — used for Laplace smoothing and the no-evidence
# fallback ranking. Derived from common industry surveys.
PATTERN_PRIORS = {
    "{first}.{last}": 0.35,
    "{first}":         0.15,
    "{f}{last}":       0.12,
    "{first}{last}":   0.08,
    "{first}_{last}":  0.05,
    "{first}-{last}":  0.04,
    "{last}":          0.04,
    "{last}.{first}":  0.04,
    "{f}.{last}":      0.06,
    "{first}{l}":      0.04,
    "{last}{f}":       0.03,
}


# ---------------------------------------------------------------------------
# Canonicalization
# ---------------------------------------------------------------------------

def canon_name(s: str) -> str:
    if not s:
        return ""
    s = unicodedata.normalize("NFKD", s)
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = s.lower()
    return re.sub(r"[^a-z]", "", s)


def canon_domain(d: str) -> str:
    d = d.strip().lower()
    d = re.sub(r"^https?://", "", d)
    d = d.split("/", 1)[0]
    d = re.sub(r"^www\.", "", d)
    return d


# ---------------------------------------------------------------------------
# Cache
# ---------------------------------------------------------------------------

def cache_path(domain: str) -> Path:
    h = hashlib.sha256(domain.encode("utf-8")).hexdigest()
    return CACHE_DIR / f"{h}.json"


def cache_read(domain: str):
    p = cache_path(domain)
    if not p.exists():
        return None
    try:
        data = json.loads(p.read_text())
    except (json.JSONDecodeError, OSError):
        return None
    ts = data.get("_cached_at_epoch")
    if not ts or (time.time() - ts) > CACHE_TTL_SECONDS:
        return None
    return data


def cache_write(domain: str, payload: dict) -> None:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    payload = dict(payload)
    payload["_cached_at_epoch"] = time.time()
    payload["_cached_at"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    cache_path(domain).write_text(json.dumps(payload, indent=2))


# ---------------------------------------------------------------------------
# Direct fetch
# ---------------------------------------------------------------------------

def http_get(url: str, timeout: int = DIRECT_FETCH_TIMEOUT) -> str | None:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            ct = resp.headers.get("Content-Type", "")
            if "text" not in ct and "html" not in ct and ct:
                return None
            data = resp.read(1_000_000)  # 1 MB cap
            enc = resp.headers.get_content_charset() or "utf-8"
            return data.decode(enc, errors="replace")
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, ConnectionError, OSError, UnicodeError):
        return None


def direct_fetch(domain: str, query_log: list) -> list[dict]:
    """Fetch the candidate pages on the company's own site and extract emails.

    Returns a list of raw harvest records with `source_type='direct'`. A single
    URL failing is not fatal — it's logged and the others proceed in parallel.

    Fetches are issued concurrently through a ThreadPoolExecutor (8 workers).
    At the prior serial + 10s timeout configuration, a fully-unreachable
    domain (e.g. arcadeagroup.com) spent 160s here before SERP even started.
    With 3s timeout × 8-way concurrency, the worst case drops to ~6s.
    """
    urls = []
    seen_urls = set()
    for host in (domain, f"www.{domain}"):
        for path in DIRECT_FETCH_PATHS:
            url = f"https://{host}{path}"
            if url in seen_urls:
                continue
            seen_urls.add(url)
            urls.append(url)

    hits: list[dict] = []
    with ThreadPoolExecutor(max_workers=DIRECT_FETCH_WORKERS) as ex:
        bodies = list(ex.map(http_get, urls))
    for url, body in zip(urls, bodies):
        if body is None:
            query_log.append({"source": "direct", "url": url, "status": "fetch_failed"})
            continue
        records = harvest_emails(body, domain, source_url=url, source_type="direct")
        if records:
            hits.extend(records)
        query_log.append({"source": "direct", "url": url, "status": "ok", "emails_found": len(records)})
    return hits


# ---------------------------------------------------------------------------
# Bright Data SERP
# ---------------------------------------------------------------------------

def serp_query(query: str, max_results: int, query_log: list) -> list[dict]:
    """Run one Bright Data SERP query via subprocess into the brightdata-serp skill.

    Each call is one billable BrightData request. Retries once on timeout or
    non-zero exit. On total failure returns [] and records the error in
    query_log — one bad query must not abort the run.

    Results are normalised to {title, href, body} so callers that previously
    consumed the previous DDG output shape keep working unchanged.
    """
    if not SERP_SCRIPT.exists():
        query_log.append({
            "source": "serp",
            "query": query,
            "status": "serp_not_installed",
            "hint": f"expected script at {SERP_SCRIPT}",
        })
        return []

    cmd = [
        sys.executable, str(SERP_SCRIPT), query,
        "--format", "parsed",
        "--num", str(max_results),
    ]
    for attempt in (1, 2):
        try:
            proc = subprocess.run(cmd, capture_output=True, text=True, timeout=60, check=False)
        except subprocess.TimeoutExpired:
            if attempt == 1:
                time.sleep(5)
                continue
            query_log.append({"source": "serp", "query": query, "status": "timeout"})
            return []
        if proc.returncode == 0:
            try:
                payload = json.loads(proc.stdout) or {}
            except json.JSONDecodeError:
                payload = {}
            raw = payload.get("results") or []
            results = [
                {
                    "title": r.get("title") or "",
                    "href": r.get("url") or r.get("href") or "",
                    "body": r.get("snippet") or r.get("description") or "",
                }
                for r in raw
            ]
            query_log.append({"source": "serp", "query": query, "status": "ok", "results": len(results)})
            return results
        if attempt == 1:
            time.sleep(5)
            continue
        query_log.append({
            "source": "serp",
            "query": query,
            "status": f"nonzero_exit:{proc.returncode}",
            "stderr": (proc.stderr or "")[:300],
        })
    return []


def serp_harvest(domain: str, max_queries: int, max_results_per_query: int,
                 query_log: list) -> list[dict]:
    hits = []
    for template in SERP_QUERIES[:max_queries]:
        query = template.format(domain=domain)
        results = serp_query(query, max_results_per_query, query_log)
        for r in results:
            body = r.get("body") or ""
            title = r.get("title") or ""
            url = r.get("href") or ""
            combined = f"{title}\n{body}"
            records = harvest_emails(combined, domain, source_url=url, source_type="serp")
            hits.extend(records)
    return hits


def serp_name_harvest(domain: str, first: str, last: str,
                      max_results_per_query: int, query_log: list) -> list[dict]:
    """Issue name-seeded SERP queries when the caller supplied both first and
    last. Returns records with source_type='serp' like the domain-wide harvester
    — they get the same 1× (vs 2× direct) weighting in scoring. Not cached.
    """
    if not first or not last:
        return []
    hits = []
    for template in SERP_NAME_QUERIES:
        query = template.format(domain=domain, first=first, last=last)
        results = serp_query(query, max_results_per_query, query_log)
        for r in results:
            body = r.get("body") or ""
            title = r.get("title") or ""
            url = r.get("href") or ""
            combined = f"{title}\n{body}"
            records = harvest_emails(combined, domain, source_url=url, source_type="serp")
            hits.extend(records)
    return hits


# ---------------------------------------------------------------------------
# Aggregator (RocketReach) signal
# ---------------------------------------------------------------------------

AGGREGATOR_BRACKET_RE = re.compile(r"\[([a-z_]+)\]")
AGGREGATOR_PATTERN_RE = re.compile(
    r"email format is\s+((?:\[[a-z_]+\][\._\-]?)+)",
    re.IGNORECASE,
)
AGGREGATOR_PCT_RE = re.compile(r"(\d+(?:\.\d+)?)\s*%")


def bracket_to_template(bracket_expr: str) -> str | None:
    """Convert RocketReach's `[first].[last]` notation to `{first}.{last}` and
    validate it's one of the 11 known templates. Unknown aliases (e.g.
    `[first_initial]`) return None."""
    converted = AGGREGATOR_BRACKET_RE.sub(lambda m: "{" + m.group(1) + "}", bracket_expr)
    return converted if converted in PATTERN_TEMPLATES else None


def parse_aggregator_snippet(text: str) -> tuple[str, float] | None:
    """Pull (template, percentage) from an aggregator snippet.

    Example snippet body:
      "The most common Autodesk email format is [first].[last] (ex.
       jane.doe@autodesk.com), which is being used by 91.8% of ..."

    Returns None if no bracketed pattern is found or the pattern is unknown.
    Returns (template, 50.0) if the pattern is found but no percentage nearby.
    """
    m = AGGREGATOR_PATTERN_RE.search(text)
    if not m:
        return None
    template = bracket_to_template(m.group(1))
    if not template:
        return None
    window = text[m.end(): m.end() + 250]
    pct_m = AGGREGATOR_PCT_RE.search(window)
    pct = float(pct_m.group(1)) if pct_m else 50.0
    return (template, pct)


def aggregator_harvest(domain: str, max_results: int, query_log: list) -> list[dict]:
    """Issue the RocketReach SERP query and parse pattern+percentage from each
    result snippet. The page itself is bot-protected — the snippet is the
    payload.

    Filter: only keep results whose title or body contains `@<domain>`.
    RocketReach pages that are actually about <domain> always include an
    example email address like "jane.doe@<domain>" in the snippet body.
    A bare-domain-in-body match is too loose (tangential mentions leak in);
    the `@<domain>` form is tight because it only appears in the "ex. ..."
    clause of the pattern sentence.
    """
    marker = f"@{domain}"
    hits = []
    for template in AGGREGATOR_QUERIES:
        query = template.format(domain=domain)
        results = serp_query(query, max_results, query_log)
        for r in results:
            body = r.get("body") or ""
            title = r.get("title") or ""
            url = r.get("href") or ""
            if marker not in body.lower() and marker not in title.lower():
                continue
            parsed = parse_aggregator_snippet(f"{title}\n{body}")
            if parsed:
                template_match, pct = parsed
                hits.append({
                    "template": template_match,
                    "percentage": pct,
                    "source_url": url,
                    "source_type": "aggregator",
                })
    return hits


# ---------------------------------------------------------------------------
# Email harvesting
# ---------------------------------------------------------------------------

EMAIL_RE_TEMPLATE = r"(?<![\w.+\-])([\w.+\-]+)@{domain}\b"
NAME_PAIR_RE = re.compile(r"\b([A-Z][a-z]{1,20})\s+([A-Z][a-z]{1,20})\b")


def is_role_local(local: str) -> bool:
    """Return True if the local-part looks like a role account.

    Matches full local-part against ROLE_LOCALS, and also splits on `.-_` and
    checks whether any part is a role word. Catches `board-administrator`,
    `regulator-inquiries`, `privacy.officer`, etc. — which slipped through
    an exact-match filter during the autodesk.com run.
    """
    if not local:
        return False
    if local in ROLE_LOCALS:
        return True
    parts = [p for p in re.split(r"[-._]", local) if p]
    return any(p in ROLE_LOCALS for p in parts)


def structural_match(local: str) -> list[str]:
    """Return pattern templates whose delimiter structure is compatible with
    this local-part, inferred from the delimiters alone.

    Used as a fallback signal when the name-pair probe fails — the SERP snippet
    window often doesn't contain a proper-noun pair adjacent to the email
    (autodesk.com surfaced carl.bass@, simon.mays-smith@, john.clancy@ with no
    nearby "Carl Bass" / "Simon Mays-Smith" / "John Clancy" strings in the
    snippet). Structural inference covers those cases with split credit.

    Returns [] when no delimiter-based inference is possible (e.g. plain local
    like `carl` could be {first}, {last}, or several concatenated patterns —
    undecidable without name info).
    """
    if "." in local:
        parts = local.split(".")
        if len(parts) != 2 or not parts[0] or not parts[1]:
            return []
        left = parts[0]
        if len(left) == 1:
            return ["{f}.{last}"]
        return ["{first}.{last}", "{last}.{first}"]
    if "_" in local:
        parts = local.split("_")
        if len(parts) == 2 and all(parts):
            return ["{first}_{last}"]
        return []
    if "-" in local:
        parts = local.split("-")
        if len(parts) == 2 and all(parts):
            return ["{first}-{last}"]
        return []
    # Bare word — no delimiter. Could be {first}, {last}, {f}{last},
    # {first}{last}, {first}{l}, {last}{f}. Without name info we can't tell,
    # but split credit between {first} and {last} is better than zero credit:
    # a harvest of `yancich@` / `eisen@` at arcadeagroup.com scored 0 before
    # this branch existed. The split gets diluted in scoring, so bare words
    # never reach `high` alone, which is the right outcome.
    if local.isalpha() and len(local) >= 2:
        return ["{first}", "{last}"]
    return []


def harvest_emails(text: str, domain: str, *, source_url: str, source_type: str) -> list[dict]:
    """Extract emails matching <local>@domain from `text` along with a nearby
    name pair, if any.
    """
    if not text:
        return []
    pattern = re.compile(EMAIL_RE_TEMPLATE.format(domain=re.escape(domain)), re.IGNORECASE)
    records = []
    for m in pattern.finditer(text):
        local = m.group(1).lower()
        # Sentinel placeholders from aggregator SEO pages (LeadIQ, RocketReach
        # tangential mentions). Discovered on the 22-domain batch when
        # `last@arcadeagroup.com` leaked in from a LeadIQ pattern explainer.
        if local in BLACKLIST_LOCALS:
            continue
        start, end = m.span()
        # Grab a window around the hit for name-pair probing.
        window_start = max(0, start - 200)
        window_end = min(len(text), end + 200)
        window = text[window_start:window_end]
        name_pair = None
        for nm in NAME_PAIR_RE.finditer(window):
            candidate = (nm.group(1), nm.group(2))
            # Reject obvious non-name pairs: common English words, company
            # suffixes, months, and place-name prefixes. Caught after the
            # 22-domain batch saw "Arcadea Group" and "Complete Flight" pass.
            head = candidate[0].lower()
            tail = candidate[1].lower()
            rejects = {
                "the", "this", "that", "san", "new", "los", "north",
                "south", "east", "west", "complete", "private",
            }
            suffixes = {
                "group", "company", "corp", "corporation", "inc", "llc",
                "ltd", "limited", "partners", "capital", "holdings",
                "ventures", "associates", "management", "technologies",
                "technology", "systems", "solutions", "software",
                "services", "industries", "enterprises", "international",
            }
            months = {
                "january", "february", "march", "april", "may", "june",
                "july", "august", "september", "october", "november",
                "december", "jan", "feb", "mar", "apr", "jun", "jul",
                "aug", "sep", "oct", "nov", "dec",
            }
            if head in rejects or head in months:
                continue
            if tail in suffixes or tail in months:
                continue
            name_pair = candidate
            break
        records.append({
            "local": local,
            "email": f"{local}@{domain}",
            "role_account": is_role_local(local),
            "source_url": source_url,
            "source_type": source_type,
            "name_pair": name_pair,
        })
    return records


# ---------------------------------------------------------------------------
# Pattern inference
# ---------------------------------------------------------------------------

def render_pattern(template: str, first: str, last: str) -> str | None:
    """Render a pattern template with canonicalized name parts. Returns None if
    a required component is missing (e.g. {f} when first is empty).
    """
    needs_first = "{first}" in template or "{f}" in template
    needs_last = "{last}" in template or "{l}" in template
    if needs_first and not first:
        return None
    if needs_last and not last:
        return None
    f = first[0] if first else ""
    l = last[0] if last else ""
    try:
        return template.format(first=first, last=last, f=f, l=l)
    except (IndexError, KeyError):
        return None


def infer_patterns(records: list[dict],
                   aggregator_hits: list[dict] | None = None
                   ) -> tuple[list[dict], list[dict]]:
    """Score each pattern based on matches in harvested (non-role) records.

    Three signals combined (in priority order, first winning for per-record):
      - name_pair: a proper-noun pair in the snippet window rendered through a
        template reproduces the local-part exactly. High confidence, full
        weight, can be a unique winner.
      - structural: the local-part's delimiter structure alone is compatible
        with one or more templates. Lower confidence, credit is split evenly
        among compatible templates. Covers the autodesk.com case where SERP
        snippets harvest carl.bass@, simon.mays-smith@, john.clancy@ but the
        snippet window doesn't contain a nearby "Carl Bass" / etc. string.
      - aggregator: a third-party SEO page (RocketReach) publishes the pattern
        + share-% directly in its SERP snippet. Weighted pct/10 (so a 90%
        aggregator hit counts like ~9 direct matches). A single aggregator hit
        with pct >= 60 is strong enough to label the template `high` on its
        own — RocketReach has seen thousands of samples we haven't.

    Returns (ranked_patterns, non_role_records_with_matches).
    """
    non_role = [r for r in records if not r["role_account"]]
    # Record which templates match each non-role record, and how.
    for r in non_role:
        r["matched_patterns"] = []
        r["match_source"] = None
        # Signal 1 — name-pair probe.
        if r.get("name_pair"):
            first_c = canon_name(r["name_pair"][0])
            last_c = canon_name(r["name_pair"][1])
            for t in PATTERN_TEMPLATES:
                rendered = render_pattern(t, first_c, last_c)
                if rendered and rendered == r["local"]:
                    r["matched_patterns"].append(t)
            if r["matched_patterns"]:
                r["match_source"] = "name_pair"
        # Signal 2 — structural fallback.
        if not r["matched_patterns"]:
            structural = structural_match(r["local"])
            if structural:
                r["matched_patterns"] = structural
                r["match_source"] = "structural"

    # Weighted evidence count per template.
    #   Direct-source hits weighted 2x SERP (primary-source rule).
    #   Name-pair matches: each matched template gets full source_weight.
    #   Structural matches: source_weight is split evenly among compatible
    #     templates (so `carl.bass` with no name-pair splits 50/50 between
    #     `{first}.{last}` and `{last}.{first}` — the global prior breaks
    #     the tie in the Laplace-smoothed ranking).
    template_counts: dict[str, float] = {t: 0.0 for t in PATTERN_TEMPLATES}
    template_hits: dict[str, int] = {t: 0 for t in PATTERN_TEMPLATES}
    for r in non_role:
        if not r["matched_patterns"]:
            continue
        source_weight = 2.0 if r["source_type"] == "direct" else 1.0
        if r["match_source"] == "name_pair":
            per_template = source_weight
        else:
            per_template = source_weight / len(r["matched_patterns"])
        for t in r["matched_patterns"]:
            template_counts[t] += per_template
            template_hits[t] += 1

    # Aggregator signal: fold RocketReach snippet hits in. Weight pct/10 so a
    # 90% hit counts like ~9 direct matches. Track best pct per template so we
    # can promote to `high` confidence when RocketReach is strongly sure.
    best_aggregator_pct: dict[str, float] = {}
    for a in (aggregator_hits or []):
        t = a["template"]
        if t not in template_counts:
            continue
        template_counts[t] += a["percentage"] / 10.0
        template_hits[t] += 1
        best_aggregator_pct[t] = max(best_aggregator_pct.get(t, 0.0), a["percentage"])

    total_weight = sum(template_counts.values())

    ranked = []
    for t in PATTERN_TEMPLATES:
        hits = template_hits[t]
        weighted = template_counts[t]
        raw = (weighted / total_weight) if total_weight > 0 else 0.0
        # Laplace-smoothed score with the global prior as the smoothing target.
        smoothed = (weighted + PATTERN_PRIORS[t]) / (total_weight + 1.0)
        agg_pct = best_aggregator_pct.get(t, 0.0)
        if agg_pct >= 60.0 or (hits >= 3 and raw >= 0.6):
            confidence = "high"
        elif hits >= 1:
            confidence = "medium"
        else:
            confidence = "low — no evidence"
        ranked.append({
            "pattern": t,
            "evidence_count": hits,
            "weighted_evidence": round(weighted, 2),
            "score": round(smoothed, 4),
            "confidence": confidence,
        })

    # Sort: evidence_count desc, then smoothed score desc.
    ranked.sort(key=lambda x: (x["evidence_count"], x["score"]), reverse=True)
    return ranked, non_role


# ---------------------------------------------------------------------------
# Guess generation
# ---------------------------------------------------------------------------

def generate_guesses(ranked: list[dict], first: str, last: str, domain: str) -> list[dict]:
    if not first or not last:
        return []
    first_c = canon_name(first)
    last_c = canon_name(last)
    if not first_c or not last_c:
        return []

    total_evidence = sum(p["evidence_count"] for p in ranked)
    guesses: list[dict] = []
    seen: set[str] = set()

    # Take top candidates: prefer evidence-backed patterns; fall back to priors.
    if total_evidence == 0:
        # No evidence — return the top 3 priors.
        prior_sorted = sorted(PATTERN_PRIORS.items(), key=lambda kv: kv[1], reverse=True)
        for t, _ in prior_sorted:
            rendered = render_pattern(t, first_c, last_c)
            if not rendered:
                continue
            email = f"{rendered}@{domain}"
            if email in seen:
                continue
            seen.add(email)
            guesses.append({
                "email": email,
                "pattern": t,
                "confidence": "low — no evidence",
                "rationale": "no emails discovered at this domain; global prior",
            })
            if len(guesses) >= 3:
                break
        return guesses

    for p in ranked:
        if p["evidence_count"] == 0:
            continue
        rendered = render_pattern(p["pattern"], first_c, last_c)
        if not rendered:
            continue
        email = f"{rendered}@{domain}"
        if email in seen:
            continue
        seen.add(email)
        guesses.append({
            "email": email,
            "pattern": p["pattern"],
            "confidence": p["confidence"],
            "rationale": f"{p['evidence_count']} matching harvested email(s), weighted {p['weighted_evidence']}",
        })
        if len(guesses) >= 3:
            break

    # Top up with priors if we have fewer than 3.
    if len(guesses) < 3:
        prior_sorted = sorted(PATTERN_PRIORS.items(), key=lambda kv: kv[1], reverse=True)
        for t, _ in prior_sorted:
            rendered = render_pattern(t, first_c, last_c)
            if not rendered:
                continue
            email = f"{rendered}@{domain}"
            if email in seen:
                continue
            seen.add(email)
            guesses.append({
                "email": email,
                "pattern": t,
                "confidence": "low — no evidence",
                "rationale": "fallback prior",
            })
            if len(guesses) >= 3:
                break

    return guesses


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------

def run(args: argparse.Namespace) -> dict:
    domain = canon_domain(args.domain)
    if not domain or "." not in domain:
        return {
            "domain": args.domain,
            "error": "invalid domain",
        }

    cache_hit = None
    if not args.no_cache:
        cache_hit = cache_read(domain)

    if cache_hit:
        discovered = cache_hit["discovered_emails"]
        aggregator_hits = cache_hit.get("aggregator_hits", [])
        query_log = cache_hit.get("query_log", [])
        cached_at = cache_hit.get("_cached_at")
        cached = True
        # Name-seeded queries are deliberately NOT cached under the domain-only
        # key (would leak across different names). Fire them fresh even when we
        # have a cache hit on the domain-wide harvest.
        if args.first and args.last:
            name_hits = serp_name_harvest(
                domain, args.first, args.last,
                max_results_per_query=args.max_results_per_query,
                query_log=query_log,
            )
            seen = {(r["local"], r.get("source_url")) for r in discovered}
            for r in name_hits:
                key = (r["local"], r.get("source_url"))
                if key not in seen:
                    seen.add(key)
                    discovered.append(r)
    else:
        query_log: list = []
        raw_records: list[dict] = []
        if not args.skip_direct_fetch:
            raw_records.extend(direct_fetch(domain, query_log))
        raw_records.extend(serp_harvest(
            domain,
            max_queries=args.max_queries,
            max_results_per_query=args.max_results_per_query,
            query_log=query_log,
        ))
        aggregator_hits = aggregator_harvest(
            domain,
            max_results=args.max_results_per_query,
            query_log=query_log,
        )
        # Dedupe domain-wide records by (local, source_url); this is what gets
        # cached under the domain-only key.
        seen = set()
        discovered: list[dict] = []
        for r in raw_records:
            key = (r["local"], r.get("source_url"))
            if key in seen:
                continue
            seen.add(key)
            discovered.append(r)

        cached_at = None
        cached = False
        if not args.no_cache:
            cache_write(domain, {
                "domain": domain,
                "discovered_emails": discovered,
                "aggregator_hits": aggregator_hits,
                "query_log": query_log,
            })
            cached_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

        # Name-seeded SERP hits are appended AFTER the cache write so the cache
        # holds only domain-wide evidence — name-specific results would leak
        # across different names on subsequent cache reads.
        if args.first and args.last:
            name_hits = serp_name_harvest(
                domain, args.first, args.last,
                max_results_per_query=args.max_results_per_query,
                query_log=query_log,
            )
            for r in name_hits:
                key = (r["local"], r.get("source_url"))
                if key not in seen:
                    seen.add(key)
                    discovered.append(r)

    ranked, _non_role = infer_patterns(discovered, aggregator_hits)

    guesses = generate_guesses(ranked, args.first or "", args.last or "", domain)

    # Strip internal-only fields from discovered for a clean payload.
    discovered_clean = [
        {
            "email": r["email"],
            "role_account": r["role_account"],
            "source_url": r.get("source_url"),
            "source_type": r.get("source_type"),
        }
        for r in discovered
    ]

    out = {
        "domain": domain,
        "name": {"first": args.first, "last": args.last} if (args.first or args.last) else None,
        "discovered_emails": discovered_clean,
        "aggregator_hits": aggregator_hits,
        "inferred_patterns": ranked,
        "guesses": guesses,
        "query_log": query_log,
        "cached": cached,
        "cached_at": cached_at,
    }
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="email_guesser.py",
        description="Guess a person's work email and infer a company's email pattern.",
    )
    parser.add_argument("--domain", required=True, help="company domain, e.g. acme.com")
    parser.add_argument("--first", help="first name of target person")
    parser.add_argument("--last", help="last name of target person")
    parser.add_argument("--no-cache", action="store_true", help="bypass cache read and write")
    parser.add_argument("--max-queries", type=int, default=5, help="cap on SERP queries (default 5)")
    parser.add_argument("--max-results-per-query", type=int, default=10,
                        help="results per SERP query (default 10)")
    parser.add_argument("--skip-direct-fetch", action="store_true",
                        help="skip the /contact /about /team /press HTTP fetch")
    parser.add_argument("--pretty", action="store_true", help="pretty-print JSON output")

    try:
        args = parser.parse_args(argv)
    except SystemExit as e:
        # argparse already wrote a usage message to stderr. Emit a JSON stub
        # on stdout so downstream tools always see parsable output.
        print(json.dumps({"error": "bad args"}))
        return 2

    try:
        out = run(args)
    except Exception as e:  # noqa: BLE001 — must always emit JSON
        out = {"domain": args.domain, "error": f"unexpected: {type(e).__name__}: {e}"}
        print(json.dumps(out, indent=2 if args.pretty else None))
        return 4

    print(json.dumps(out, indent=2 if args.pretty else None))
    return 0


if __name__ == "__main__":
    sys.exit(main())
