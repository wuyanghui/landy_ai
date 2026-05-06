import asyncio
from typing import Literal, List, Optional, Dict, Any

from langchain_core.tools import tool
from langgraph.config import get_stream_writer

from agent.v4.tools._utils import expand_property_category
from utility.property_listing_init import get_property_listing_collections


def _run_radius_query(
    lat: float,
    lng: float,
    radius_km: float,
    offer_type: Optional[str],
    property_category: Optional[List[str]],
    price_min: Optional[float],
    price_max: Optional[float],
    built_up_sqft_min: Optional[float],
    built_up_sqft_max: Optional[float],
    limit: int,
) -> Dict[str, Any]:
    collection = get_property_listing_collections()

    query: Dict[str, Any] = {
        "listing_status": "active",
        "location.geo.point": {
            "$nearSphere": {
                "$geometry": {"type": "Point", "coordinates": [lng, lat]},
                "$maxDistance": int(radius_km * 1000),
            }
        },
    }

    if offer_type:
        query["offer.offer_type"] = offer_type
    if property_category:
        expanded = expand_property_category(property_category)
        query["$or"] = [
            {"main_category": {"$in": expanded}},
            {"sub_categories": {"$in": expanded}},
        ]
    if price_min is not None:
        query["offer.price"] = {"$gte": price_min}
    if price_max is not None:
        query.setdefault("offer.price", {})["$lte"] = price_max
    if built_up_sqft_min is not None:
        query["built_up_area.value"] = {"$gte": built_up_sqft_min}
    if built_up_sqft_max is not None:
        query.setdefault("built_up_area.value", {})["$lte"] = built_up_sqft_max

    docs = list(collection.find(query).limit(limit))

    results = []
    for doc in docs:
        offer = doc.get("offer") or {}
        location = doc.get("location") or {}
        address = location.get("address") or {}
        built_up = doc.get("built_up_area") or {}
        land = doc.get("land_size") or {}
        listed_date = doc.get("listed_date")
        results.append({
            "property_id": doc.get("property_id"),
            "title": doc.get("title"),
            "slug": doc.get("slug"),
            "offer_type": offer.get("offer_type"),
            "price": offer.get("price"),
            "price_currency": offer.get("price_currency"),
            "locality": address.get("address_region"),
            "region": address.get("address_locality"),
            "main_category": doc.get("main_category"),
            "sub_categories": doc.get("sub_categories") or [],
            "built_up_sqft": built_up.get("value"),
            "land_sqft": land.get("value"),
            "listed_date": listed_date.isoformat() if listed_date else None,
        })

    return {
        "total_found": len(results),
        "property_listing_id": [r["property_id"] for r in results],
        "property_listing_result": results,
    }


@tool
async def aget_properties_by_radius(
    lat: float,
    lng: float,
    radius_km: float,
    place_name: str = "",
    offer_type: Optional[Literal["sale", "rent"]] = None,
    property_category: Optional[List[Literal[
        "agricultural-land", "cluster-factory", "detached-factory",
        "factory", "industrial-land", "semi-d-factory", "shoplot",
        "showroom", "terrace-factory", "warehouse"
    ]]] = None,
    price_min: Optional[float] = None,
    price_max: Optional[float] = None,
    built_up_sqft_min: Optional[float] = None,
    built_up_sqft_max: Optional[float] = None,
    limit: int = 20,
) -> Dict[str, Any]:
    """
    Find active industrial properties within a GPS radius using MongoDB $nearSphere.
    Use ONLY when user specifies explicit distance: 'within X km', 'X km from', 'X minutes from [place]'.
    Resolve place_name to approximate lat/lng from training knowledge. ±2km is acceptable for 20km radius.
    'Near Shah Alam' without a distance → use asearch_properties with locality filter instead.
    """
    writer = get_stream_writer()
    writer({"event": "tool_start", "tool": "properties_by_radius",
            "place": place_name, "radius_km": radius_km, "lat": lat, "lng": lng})

    result = await asyncio.to_thread(
        _run_radius_query,
        lat, lng, radius_km, offer_type, property_category,
        price_min, price_max, built_up_sqft_min, built_up_sqft_max, limit,
    )

    writer({"event": "tool_complete", "tool": "properties_by_radius",
            "found": result["total_found"], "ids": result["property_listing_id"]})
    return result
