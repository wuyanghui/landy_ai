"""Read-only lookups the price-page chat uses for places other than the visitor's own page."""
from __future__ import annotations

from typing import Literal, Optional

from langchain_core.tools import tool

from agent.market.data import BASE_PATHS, LEVEL_WORDS, LEVELS, MarketApiError, fetch_index, fetch_page, page_summary, rm
from agent.market.data import property_class as to_class

MAX_FOUND = 15
UNAVAILABLE = "Price data could not be loaded right now ({error}). Say so; do not guess figures."


def _parent_of(path: str) -> Optional[str]:
    if not path:
        return None
    return path.rsplit("/", 1)[0] if "/" in path else ""


def _row(cls: str, entry: dict) -> str:
    return (f"{entry['name']} | {cls} | {LEVEL_WORDS[entry['level']]} | path {entry['path'] or '(Malaysia)'} | "
            f"typical {rm(entry['medianPsf'])} per sq ft | {entry['dealCount']:,} sales")


@tool
def find_price_pages(query: str, property_class: Optional[str] = None) -> str:
    """Find Landy Insights price pages whose name matches a place (state, area, industrial estate or development).

    Use it whenever the visitor names a place other than the current page, to get its exact path before
    get_price_page. Matches both classes unless property_class is given ("industrial"/"factory" or
    "commercial"/"shop"/"office"). Returns name | class | level | path | typical price per sq ft | sales.
    """
    try:
        classes = [to_class(property_class)] if property_class else list(BASE_PATHS)
    except ValueError as exc:
        return str(exc)
    needle = " ".join(query.lower().replace("-", " ").split())
    found = []
    try:
        for cls in classes:
            for entry in fetch_index(cls)["pages"]:
                hay = f"{entry['name']} {entry['path'].replace('-', ' ').replace('/', ' ')}".lower()
                if needle and needle in hay:
                    found.append((LEVELS.index(entry["level"]), cls, entry))
    except MarketApiError as exc:
        return UNAVAILABLE.format(error=exc)
    if not found:
        return (f"No price page matches '{query}'. A place needs about 30 recorded sales (20 for a factory area) "
                "for its own page; try the area or state it sits in.")
    found.sort(key=lambda item: (item[0], -item[2]["dealCount"]))
    rows = [_row(cls, entry) for _, cls, entry in found[:MAX_FOUND]]
    more = f"\n({len(found) - MAX_FOUND} more; ask with a narrower name)" if len(found) > MAX_FOUND else ""
    return "\n".join(rows) + more


def _resolve(index: dict, place: str) -> tuple[Optional[str], list[dict]]:
    """(path, []) for one page; (None, candidates) when the name is ambiguous or unknown."""
    wanted = place.strip().strip("/").lower()
    pages = index["pages"]
    if wanted in ("", "malaysia"):
        return "", []
    for entry in pages:
        if entry["path"] == wanted:
            return entry["path"], []
    # Exact name first, the broadest level winning (Shah Alam the area over an estate named after it).
    exact = [e for e in pages if e["name"].lower() == wanted]
    if exact:
        return min(exact, key=lambda e: LEVELS.index(e["level"]))["path"], []
    words = " ".join(wanted.replace("-", " ").split())
    hits = [e for e in pages if words in e["name"].lower().replace("-", " ")]
    if len(hits) == 1:
        return hits[0]["path"], []
    return None, hits


@tool
def get_price_page(property_class: str, place: str) -> str:
    """Get one full Landy Insights price page: typical price per sq ft, middle half of sales, sales count,
    typical sale price, comparison with its state and Malaysia, prices BY PROPERTY TYPE (terrace, semi-D,
    detached, strata; shop storeys, office, SOHO), tenure, yearly trend and the places under it.

    Call it for every place you quote other than the current page; find_price_pages alone has no type figures.
    property_class: "industrial" (factories, warehouses) or "commercial" (shops, offices).
    place: the place's name ("Puchong", "Kota Elmina") or its path ("selangor/puchong"); "" for Malaysia.
    """
    try:
        cls = to_class(property_class)
    except ValueError as exc:
        return str(exc)
    try:
        path, candidates = _resolve(fetch_index(cls), place)
        if path is None:
            if not candidates:
                return (f"No {cls} price page for '{place}'. A place needs about 30 recorded sales for its own page; "
                        "try find_price_pages or the area or state it sits in.")
            listed = "\n".join(_row(cls, e) for e in candidates[:MAX_FOUND])
            return f"'{place}' matches several {cls} pages; call again with one of these paths:\n{listed}"
        page = fetch_page(cls, path)
    except MarketApiError as exc:
        return UNAVAILABLE.format(error=exc)
    if page is None:
        return f"No {cls} price page at '{path}'. Use find_price_pages to look the place up by name."
    return page_summary(page)


@tool
def list_price_pages(
    property_class: str,
    parent_path: str = "",
    sort_by: Literal["price", "sales", "name"] = "sales",
    limit: int = 30,
) -> str:
    """List the price pages directly under a place, to rank or compare them.

    parent_path "" lists the states; "selangor" lists Selangor's areas; "selangor/shah-alam" lists its
    estates or developments. sort_by "price" ranks from priciest to cheapest per sq ft; "sales" puts the
    busiest first. Use it for "cheapest area in Johor", "rank Selangor areas", "which estates are in Klang".
    """
    try:
        cls = to_class(property_class)
    except ValueError as exc:
        return str(exc)
    try:
        index = fetch_index(cls)
    except MarketApiError as exc:
        return UNAVAILABLE.format(error=exc)
    parent = parent_path.strip("/")
    entries = [e for e in index["pages"] if _parent_of(e["path"]) == parent]
    if not entries:
        return f"No {cls} price pages under '{parent_path}'. Check the path with find_price_pages."
    key = {"price": lambda e: -e["medianPsf"], "sales": lambda e: -e["dealCount"], "name": lambda e: e["name"]}[sort_by]
    entries.sort(key=key)
    rows = [_row(cls, e) for e in entries[: max(1, limit)]]
    more = f"\n({len(entries) - limit} more not shown)" if len(entries) > limit else ""
    return f"{len(entries)} {cls} pages, sorted by {sort_by}:\n" + "\n".join(rows) + more



MARKET_TOOLS = [find_price_pages, get_price_page, list_price_pages]
