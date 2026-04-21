import asyncio
from typing import Literal, List, Optional, Dict, Any
from langchain_core.tools import tool
from pymongo import DESCENDING

from utility.property_listing_init import get_property_listing_collections

FACTORY_EXPANSION_MAP = {
    "factory": [
        "factory",
        "cluster-factory",
        "detached-factory",
        "semi-d-factory",
        "terrace-factory",
    ]
}

def _expand_category(categories: List[str]) -> List[str]:
    expanded = set()
    for cat in categories:
        if cat in FACTORY_EXPANSION_MAP:
            expanded.update(FACTORY_EXPANSION_MAP[cat])
        else:
            expanded.add(cat)
    return list(expanded)


@tool
def get_newest_listings(
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
    Fetch the most recently listed active properties from MongoDB, sorted by listed_date descending.
    Use this when the user asks for newest, latest, or recently listed properties.
    """
    collection = get_property_listing_collections()

    filters: Dict[str, Any] = {"listing_status": "active"}

    if offer_type:
        filters["offer.offer_type"] = offer_type

    if property_category:
        expanded = _expand_category(property_category)
        filters["$or"] = [
            {"main_category": {"$in": expanded}},
            {"sub_categories": {"$in": expanded}},
        ]

    if region:
        filters["location.address.address_locality"] = {"$in": region}

    if locality:
        filters["location.address.address_region"] = {
            "$in": locality
        }

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
        geo = location.get("geo") or {}
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
            "tenure": doc.get("tenure"),
            "built_up_sqft": built_up.get("value"),
            "land_sqft": land.get("value"),
            "listed_date": listed_date.isoformat() if listed_date else None,
        })

    return {
        "total_found": len(results),
        "property_listing_id": [r["property_id"] for r in results],
        "property_listing_result": results,
    }


def _run_newest_query(
    offer_type, property_category, region, locality, limit
) -> Dict[str, Any]:
    collection = get_property_listing_collections()

    filters: Dict[str, Any] = {"listing_status": "active"}

    if offer_type:
        filters["offer.offer_type"] = offer_type

    if property_category:
        expanded = _expand_category(property_category)
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
            "tenure": doc.get("tenure"),
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
    Fetch the most recently listed active properties from MongoDB, sorted by listed_date descending.
    Use this when the user asks for newest, latest, or recently listed properties.
    """
    return await asyncio.to_thread(
        _run_newest_query, offer_type, property_category, region, locality, limit
    )
