import asyncio
from typing import Literal, List, Optional, Dict, Any

from langchain_core.tools import tool
from langgraph.config import get_stream_writer
from pymongo import DESCENDING

from agent.v4.tools._utils import expand_property_category
from utility.property_listing_init import get_property_listing_collections


def _run_newest_query(
    offer_type: Optional[str],
    property_category: Optional[List[str]],
    region: Optional[List[str]],
    locality: Optional[List[str]],
    limit: int,
) -> Dict[str, Any]:
    collection = get_property_listing_collections()
    filters: Dict[str, Any] = {"listing_status": "active"}

    if offer_type:
        filters["offer.offer_type"] = offer_type
    if property_category:
        expanded = expand_property_category(property_category)
        filters["$or"] = [
            {"main_category": {"$in": expanded}},
            {"sub_categories": {"$in": expanded}},
        ]
    if region:
        filters["location.address.address_locality"] = {"$in": region}
    if locality:
        filters["location.address.address_region"] = {"$in": locality}

    cursor = (
        collection.find(filters)
        .sort([("listed_date", DESCENDING), ("property_id", DESCENDING)])
        .limit(limit)
    )

    results = []
    for doc in cursor:
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
            "full_address": address.get("street_address"),
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
async def aget_newest_listings(
    offer_type: Optional[Literal["sale", "rent"]] = None,
    property_category: Optional[List[Literal[
        "agricultural-land", "cluster-factory", "detached-factory",
        "factory", "industrial-land", "semi-d-factory", "shoplot",
        "showroom", "terrace-factory", "warehouse"
    ]]] = None,
    region: Optional[List[Literal["Selangor", "Kuala Lumpur", "Negeri Sembilan"]]] = None,
    locality: Optional[List[str]] = None,
    limit: int = 8,
) -> Dict[str, Any]:
    """
    Fetch the most recently listed active industrial properties sorted by listed_date descending.
    Use ONLY when user explicitly asks for newest, latest, recently listed, or just listed.
    No semantic query needed — this tool sorts by date only.
    Apply any optional filters the user gave (category, region, locality, offer_type).
    """
    writer = get_stream_writer()
    writer({"event": "tool_start", "tool": "newest_listings"})

    result = await asyncio.to_thread(
        _run_newest_query, offer_type, property_category, region, locality, limit
    )

    writer({"event": "tool_complete", "tool": "newest_listings",
            "found": result["total_found"], "ids": result["property_listing_id"]})
    return result
