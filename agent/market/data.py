"""Landy Insights price data for the price-page chat.

Reads IndustrialProp's public market API (industrialprop_backend_api,
market_data/api.py) with GET requests only:
    GET /api/market/{class}/index        every price page of a class
    GET /api/market/{class}/page?path=   one ready-made price page
and turns a page into the plain-text summary the chat reads.
"""
from __future__ import annotations

import os
import time

import httpx

MARKET_API_URL = os.environ.get("MARKET_API_URL", "https://industrialpropbackendapi.vercel.app").rstrip("/")
SITE_URL = "https://www.industrialprop.com.my"
BASE_PATHS = {"industrial": "/industrial-property-prices", "commercial": "/commercial-property-prices"}

CLASS_WORDS = {
    "industrial": "industrial", "factory": "industrial", "factories": "industrial",
    "warehouse": "industrial", "warehouses": "industrial",
    "commercial": "commercial", "shop": "commercial", "shops": "commercial", "shoplot": "commercial",
    "office": "commercial", "offices": "commercial",
}
# What a sale in each class is called in a sentence.
NOUNS = {"industrial": "factory", "commercial": "shop or office"}
LEVEL_WORDS = {"national": "country", "state": "state", "area": "area", "scheme": "estate or development"}
LEVELS = ("national", "state", "area", "scheme")
MONTHS = ["January", "February", "March", "April", "May", "June",
          "July", "August", "September", "October", "November", "December"]

# The index changes only when a new dataset goes live (a few times a year).
INDEX_TTL_SECONDS = 3600
_TIMEOUT = 20
_index_cache: dict[str, tuple[float, dict]] = {}


class MarketApiError(Exception):
    """The market API could not answer (outage, timeout, bad response)."""


def clear_cache() -> None:
    _index_cache.clear()


def property_class(word: str) -> str:
    """'factory' -> 'industrial', 'shop' -> 'commercial'. Anything else (residential) is refused."""
    key = CLASS_WORDS.get((word or "").strip().lower())
    if key is None:
        raise ValueError(f"{word!r}: Landy Insights covers industrial or commercial property only")
    return key


def page_url(cls: str, path: str) -> str:
    path = path.strip("/")
    return f"{SITE_URL}{BASE_PATHS[cls]}{'/' + path if path else ''}"


def _get(route: str, params: dict | None = None) -> httpx.Response:
    try:
        return httpx.get(f"{MARKET_API_URL}{route}", params=params, timeout=_TIMEOUT)
    except httpx.HTTPError as exc:
        raise MarketApiError(f"market API unreachable: {exc}") from exc


def fetch_index(cls: str) -> dict:
    cached = _index_cache.get(cls)
    if cached and time.monotonic() - cached[0] < INDEX_TTL_SECONDS:
        return cached[1]
    response = _get(f"/api/market/{cls}/index")
    if response.status_code != 200:
        raise MarketApiError(f"market API returned {response.status_code} for the {cls} index")
    index = response.json()
    _index_cache[cls] = (time.monotonic(), index)
    return index


def fetch_page(cls: str, path: str) -> dict | None:
    """One price page, or None when the class has no page at that path."""
    response = _get(f"/api/market/{cls}/page", params={"path": path.strip("/")})
    if response.status_code == 404:
        return None
    if response.status_code != 200:
        raise MarketApiError(f"market API returned {response.status_code} for {cls} '{path}'")
    return response.json()


# -- wording ------------------------------------------------------------------


def rm(value) -> str:
    return f"RM {round(value):,}"


def money(value) -> str:
    if value >= 1_000_000:
        return f"RM {value / 1_000_000:.1f}M"
    return f"RM {round(value / 10_000) * 10_000:,}"


def month_name(month: str) -> str:
    """'2026-06' -> 'June 2026'."""
    year, mon = month.split("-")
    return f"{MONTHS[int(mon) - 1]} {year}"


def _pct(value: int, against: str) -> str:
    return f"{value:+d}% vs {against}"


def page_summary(page: dict) -> str:
    """Everything a price page shows, as compact text for the model. Figures a dataset lacks are left out."""
    cls = page["class"]
    s = page["stats"]
    ds = page["dataset"]
    crumbs = [c["name"] for c in page.get("breadcrumbs") or []]
    parent = crumbs[-1] if crumbs else None
    trail = " > ".join(crumbs + [page["name"]])
    lines = [
        f"{page['name']} ({cls} property, {LEVEL_WORDS[page['level']]} level): {trail}",
        f"Page: {page_url(cls, page['path'])}",
        f"Source: {ds['source']['name']}, recorded sales {month_name(s['period']['from'])} to "
        f"{month_name(s['period']['to'])}; data through {month_name(ds['dataThrough'])}.",
    ]
    if page.get("districts"):
        lines.append(f"NAPIC districts in this area: {', '.join(page['districts'])}.")
    lines.append(
        f"Typical (median) price: {rm(s['medianPsf'])} per sq ft of floor space, from {s['dealCount']:,} sales. "
        f"Typical sale price {money(s['medianPrice'])}."
    )
    if s.get("p25Psf") is not None and s.get("p75Psf") is not None:
        lines.append(f"Middle half of sales: {rm(s['p25Psf'])} to {rm(s['p75Psf'])} per sq ft.")
    compare = []
    if s.get("vsParentPct") is not None and page["level"] in ("area", "scheme") and parent:
        compare.append(_pct(s["vsParentPct"], parent))
    if s.get("vsNationalPct") is not None and page["level"] != "national":
        compare.append(_pct(s["vsNationalPct"], "Malaysia"))
    if compare:
        lines.append("Compared with: " + ", ".join(compare) + ".")
    recent = s.get("recent")
    if recent:
        lines.append(
            f"Last two years ({month_name(recent['from'])} to {month_name(recent['to'])}): "
            f"{rm(recent['medianPsf'])} per sq ft from {recent['dealCount']:,} sales."
        )
    if s.get("byType"):
        banded = any(row.get("p25Psf") is not None for row in s["byType"])
        lines.append(f"By type (sales, typical psf,{' middle half,' if banded else ''} typical sale price):")
        for row in s["byType"]:
            band = f", {rm(row['p25Psf'])} to {rm(row['p75Psf'])}" if row.get("p25Psf") is not None else ""
            lines.append(f"- {row['label']}: {row['dealCount']:,} sales, {rm(row['medianPsf'])}{band}, "
                         f"{money(row['medianPrice'])}")
    tenure = s.get("tenure")
    if tenure:
        parts = [f"{tenure['freeholdSharePct']}% freehold ({tenure['freeholdDeals']:,} freehold, "
                 f"{tenure['leaseholdDeals']:,} leasehold sales)"]
        if tenure.get("freeholdMedianPsf") is not None:
            parts.append(f"freehold typical {rm(tenure['freeholdMedianPsf'])}")
        if tenure.get("leaseholdMedianPsf") is not None:
            parts.append(f"leasehold typical {rm(tenure['leaseholdMedianPsf'])}")
        lines.append("Tenure: " + ", ".join(parts) + " per sq ft.")
    if s.get("landPsf"):
        lines.append(f"Implied land value: {rm(s['landPsf']['medianPsf'])} per sq ft of land "
                     f"({s['landPsf']['dealCount']:,} landed sales; a proxy, the price also pays for the building).")
    if s.get("yearlyPsf"):
        years = [
            f"{y['year']} {rm(y['medianPsf'])} ({y['dealCount']} sales{', provisional' if y['provisional'] else ''})"
            for y in s["yearlyPsf"]
        ]
        lines.append("Typical psf by year: " + "; ".join(years) + ".")
    children = page.get("children") or []
    if children:
        kind = {"national": "States", "state": "Areas", "area": "Estates and developments"}.get(page["level"], "Places")
        lines.append(f"{kind} with their own page (most sales first): " + "; ".join(
            f"{c['name']} {rm(c['medianPsf'])} ({c['dealCount']:,} sales, path {c['path']})" for c in children
        ) + ".")
    small = page.get("smallAreas") or []
    if small:
        lines.append("Smaller areas, too few sales for a page: " + "; ".join(
            f"{a['name']} {rm(a['medianPsf'])} ({a['dealCount']} sales)" for a in small
        ) + ".")
    return "\n".join(lines)
