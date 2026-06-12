import asyncio
import re
from typing import Literal, List, Optional, Dict, Any

from langchain_core.tools import tool
from langgraph.config import get_stream_writer

from agent.v5.tools._utils import expand_property_category, serialize_chat_listing, serialize_listing
from utility.property_listing_init import get_enriched_property_listing_collections


def _build_location_clause(locality: str) -> Dict:
    rx = {"$regex": re.escape(locality), "$options": "i"}
    slug = locality.lower().replace(" ", "-")
    lower = locality.lower()
    return {"$or": [
        {"location.hierarchy.city.name": rx},
        {"location.hierarchy.city.aliases": lower},
        {"location.hierarchy.city.slug": slug},
        {"location.hierarchy.industrial_park.name": rx},
        {"location.hierarchy.industrial_park.aliases": lower},
        {"location.hierarchy.industrial_park.slug": slug},
    ]}


def _build_region_clause(region: str) -> Dict:
    rx = {"$regex": re.escape(region), "$options": "i"}
    lower = region.lower()
    return {"$or": [
        {"location.hierarchy.state.name": rx},
        {"location.hierarchy.state.aliases": lower},
    ]}


def _build_filters(
    offer_type, property_category, locality, region,
    price_min, price_max, built_up_sqft_min, built_up_sqft_max,
    land_sqft_min, land_sqft_max, ceiling_height_min, floor_loading_min,
    max_highway_km, max_port_km, max_airport_km,
) -> Dict:
    filters: Dict[str, Any] = {"listing_status": "active"}

    if offer_type:
        filters["offer.offer_type"] = offer_type

    clauses = []
    if property_category:
        expanded = expand_property_category(property_category)
        clauses.append({"$or": [
            {"main_category": {"$in": expanded}},
            {"sub_categories": {"$in": expanded}},
        ]})
    if locality:
        clauses.append(_build_location_clause(locality))
    if region:
        clauses.append(_build_region_clause(region))
    if clauses:
        filters["$and"] = clauses

    if price_min is not None or price_max is not None:
        f: Dict = {}
        if price_min is not None: f["$gte"] = price_min
        if price_max is not None: f["$lte"] = price_max
        filters["offer.price"] = f

    if built_up_sqft_min is not None or built_up_sqft_max is not None:
        f = {}
        if built_up_sqft_min is not None: f["$gte"] = built_up_sqft_min
        if built_up_sqft_max is not None: f["$lte"] = built_up_sqft_max
        filters["built_up_area_sqft"] = f

    if land_sqft_min is not None or land_sqft_max is not None:
        f = {}
        if land_sqft_min is not None: f["$gte"] = land_sqft_min
        if land_sqft_max is not None: f["$lte"] = land_sqft_max
        filters["land_size_sqft"] = f

    if ceiling_height_min is not None:
        filters["traits.building.ceiling_height_m"] = {"$gte": ceiling_height_min}
    if floor_loading_min is not None:
        filters["traits.industrial.floor_loading_kn_m2"] = {"$gte": floor_loading_min}
    if max_highway_km is not None:
        filters["location.nearest.highway.distance_km"] = {"$lte": max_highway_km}
    if max_port_km is not None:
        filters["location.nearest.port.distance_km"] = {"$lte": max_port_km}
    if max_airport_km is not None:
        filters["location.nearest.airport.distance_km"] = {"$lte": max_airport_km}

    return filters


_SORT_MAP = {
    "newest": [("listed_date", -1), ("property_id", -1)],
    "price_asc": [("offer.price", 1)],
    "price_desc": [("offer.price", -1)],
}


def _run_query(filters: Dict, sort_by: Optional[str]) -> List[Dict]:
    collection = get_enriched_property_listing_collections()
    cursor = collection.find(filters)
    if sort_by and sort_by in _SORT_MAP:
        cursor = cursor.sort(_SORT_MAP[sort_by])
    return list(cursor)


@tool
async def find_listings(
    offer_type: Optional[Literal["sale", "rent"]] = None,
    property_category: Optional[List[Literal[
        "agricultural-land", "cluster-factory", "detached-factory",
        "factory", "industrial-land", "semi-d-factory", "shoplot",
        "showroom", "terrace-factory", "warehouse"
    ]]] = None,
    locality: Optional[str] = None,
    region: Optional[str] = None,
    price_min: Optional[float] = None,
    price_max: Optional[float] = None,
    built_up_sqft_min: Optional[float] = None,
    built_up_sqft_max: Optional[float] = None,
    land_sqft_min: Optional[float] = None,
    land_sqft_max: Optional[float] = None,
    ceiling_height_min: Optional[float] = None,
    floor_loading_min: Optional[float] = None,
    max_highway_km: Optional[float] = None,
    max_port_km: Optional[float] = None,
    max_airport_km: Optional[float] = None,
    sort_by: Optional[Literal["newest", "price_asc", "price_desc"]] = None,
) -> Dict[str, Any]:
    """
    Find active industrial property listings using structured filters.

    locality: City or district name. Expand abbreviations before calling:
              "PJ" → "Petaling Jaya" | "KL" → "Kuala Lumpur" | "CS Lin" → "Chan Sow Lin"
    region: State name. Examples: "Selangor", "Kuala Lumpur", "Negeri Sembilan".
    max_highway_km: Use when user says "near highway" or "expressway access". Default 5.0.
    max_port_km: Use when user says "near port" or "near Port Klang". Default 30.0.
    max_airport_km: Use when user says "near airport" or "near KLIA". Default 20.0.
    sort_by: Only applies when no natural relevance ordering is needed.
    """
    writer = get_stream_writer()

    active_filters = sum([
        offer_type is not None, bool(property_category), bool(locality), bool(region),
        price_min is not None or price_max is not None,
        built_up_sqft_min is not None or built_up_sqft_max is not None,
        land_sqft_min is not None or land_sqft_max is not None,
        ceiling_height_min is not None, floor_loading_min is not None,
        max_highway_km is not None, max_port_km is not None, max_airport_km is not None,
    ])
    # applied filters let the frontend show the inference process to the user
    applied = {k: v for k, v in {
        "offer_type": offer_type, "category": property_category,
        "locality": locality, "region": region,
        "price_min": price_min, "price_max": price_max,
        "built_up_sqft_min": built_up_sqft_min, "built_up_sqft_max": built_up_sqft_max,
        "land_sqft_min": land_sqft_min, "land_sqft_max": land_sqft_max,
        "ceiling_height_min": ceiling_height_min, "floor_loading_min": floor_loading_min,
        "max_highway_km": max_highway_km, "max_port_km": max_port_km,
        "max_airport_km": max_airport_km,
    }.items() if v is not None}
    writer({"event": "search_start", "filters_active": active_filters, "filters": applied})

    filters = _build_filters(
        offer_type, property_category, locality, region,
        price_min, price_max, built_up_sqft_min, built_up_sqft_max,
        land_sqft_min, land_sqft_max, ceiling_height_min, floor_loading_min,
        max_highway_km, max_port_km, max_airport_km,
    )

    docs = await asyncio.to_thread(_run_query, filters, sort_by)
    results = [serialize_listing(doc) for doc in docs]

    if results:
        # frontend ChatListingCard shape — the LLM gets the flat `results` instead
        writer({"event": "property_cards", "listings": [serialize_chat_listing(doc) for doc in docs]})

    def _unique(key):
        return list(dict.fromkeys(r[key] for r in results if r.get(key)))

    location_breakdown = _unique("city")
    filters_summary = ", ".join(filter(None, [
        f"category={','.join(property_category)}" if property_category else None,
        f"locality={locality}" if locality else None,
        f"region={region}" if region else None,
        f"price_max={price_max}" if price_max else None,
    ]))

    writer({"event": "search_complete", "total_found": len(results)})

    return {
        "total_found": len(results),
        "property_listing_result": results,
        "filters_applied": filters_summary or "none",
        "location_breakdown": location_breakdown,
        "comment": f"{len(results)} listing(s) found. Locations: {location_breakdown}." if results else "No matching listings found.",
    }
