"""Domains that require Bright Data's `web_unlocker_premium` zone instead of
the default `web_unlocker1` zone.

This list is operator-supplied, not derived from a Bright Data API — Bright
Data doesn't expose a "which zone does this domain need" lookup. These sites
are the ones Bright Data currently gates behind the premium tier (major
retailers, marketplaces, travel sites, people-search sites, and similar
high-defense targets). If a fetch through web_unlocker1 comes back
blocked/challenged for a domain that isn't in this list, that's a signal
Bright Data has moved it into the premium tier — add it here (and to
../references/premium-domains.md, to keep the human-readable copy in sync)
rather than routing around it per-call.

Mirrored for quick reading in references/premium-domains.md.
"""
from __future__ import annotations

import os
import urllib.parse

DEFAULT_ZONE = os.environ.get("BRIGHTDATA_UNLOCKER_ZONE", "web_unlocker1")
PREMIUM_ZONE = os.environ.get("BRIGHTDATA_UNLOCKER_PREMIUM_ZONE", "web_unlocker_premium")

PREMIUM_DOMAINS = frozenset(
    {
        "advanceautoparts.com",
        "affitto.it",
        "agoda.cn",
        "albertsons.com",
        "allpeople.com",
        "autozone.com",
        "bestbuy.com",
        "bestwestern.com",
        "billiger.de",
        "bottlerover.com",
        "carousell.com",
        "carousell.com.hk",
        "carousell.com.my",
        "carousell.ph",
        "carousell.sg",
        "carsales.com.au",
        "cdiscount.com",
        "chewy.com",
        "costco.com",
        "cvs.com",
        "despegar.com.mx",
        "dickssportinggoods.com",
        "dynos.es",
        "emaxme.com",
        "familytreenow.com",
        "feuvert.fr",
        "flooranddecor.com",
        "foodlion.com",
        "footlocker.co.uk",
        "footlocker.com",
        "giantfoodstores.com",
        "gopuff.com",
        "gplay.bg",
        "hermes.com",
        "hyatt.com",
        "idealo.de",
        "immobilienscout24.de",
        "ingatlan.com",
        "instacart.com",
        "intersport.fr",
        "joann.com",
        "kroger.com",
        "lazada.co.id",
        "lazada.co.th",
        "lazada.com.my",
        "lazada.com.ph",
        "lazada.sg",
        "lazada.vn",
        "lowes.ca",
        "lowes.com",
        "mcmaster.com",
        "mediamarkt.de",
        "mediamarkt.es",
        "medline.com",
        "mscdirect.com",
        "napaonline.com",
        "nofrills.ca",
        "peoplefinders.com",
        "platt.com",
        "publicdatausa.com",
        "realcanadiansuperstore.ca",
        "realestate.com.au",
        "restaurantguru.com",
        "searchpeoplefree.com",
        "shopee.cl",
        "shopee.co.id",
        "shopee.co.th",
        "shopee.com.br",
        "shopee.com.co",
        "shopee.com.mx",
        "shopee.com.my",
        "shopee.ph",
        "shopee.sg",
        "shopee.tw",
        "shopee.vn",
        "similarweb.com",
        "skyscanner.co.kr",
        "skyscanner.net",
        "stopandshop.com",
        "target.com",
        "temu.com",
        "ticketmaster.com",
        "totalwine.com",
        "tractorsupply.com",
        "walmart.com.mx",
        "wayfair.com",
        "weismarkets.com",
        "wizzair.com",
        "worten.pt",
    }
)


def _host(url: str) -> str:
    """Extract the lowercase hostname from a URL, tolerating bare domains
    (no scheme) since callers may pass either "target.com" or
    "https://www.target.com/product/123"."""
    parsed = urllib.parse.urlsplit(url if "//" in url else f"//{url}")
    host = (parsed.netloc or "").lower()
    if "@" in host:
        host = host.rsplit("@", 1)[1]
    host = host.split(":", 1)[0]
    if host.startswith("www."):
        host = host[4:]
    return host


def is_premium_domain(url: str) -> bool:
    """True if url's host is a premium domain, or a subdomain of one."""
    host = _host(url)
    if not host:
        return False
    if host in PREMIUM_DOMAINS:
        return True
    return any(host.endswith("." + d) for d in PREMIUM_DOMAINS)


def zone_for_url(url: str) -> str:
    """Resolve which zone a URL should use, absent an explicit --zone override."""
    return PREMIUM_ZONE if is_premium_domain(url) else DEFAULT_ZONE
