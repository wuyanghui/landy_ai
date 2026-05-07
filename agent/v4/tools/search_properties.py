import asyncio
import os
import re
from typing import Literal, List, Optional, Dict, Any

from dotenv import load_dotenv
from langchain_core.tools import tool
from langgraph.config import get_stream_writer
from upstash_vector import AsyncIndex

from agent.v4.tools._utils import expand_property_category
from utility.property_listing_init import get_property_listing_collections

load_dotenv()

async_index = AsyncIndex(
    url=os.getenv("UPSTASH_VECTOR_REST_URL"),
    token=os.getenv("UPSTASH_VECTOR_REST_TOKEN"),
)

_MAX_CANDIDATES = 100


def _run_mongodb_query(
    offer_type: Optional[str],
    tenure: Optional[str],
    property_category: Optional[List[str]],
    locality: Optional[str],
    region: Optional[str],
    price_min: Optional[float],
    price_max: Optional[float],
    built_up_sqft_min: Optional[float],
    built_up_sqft_max: Optional[float],
    land_sqft_min: Optional[float],
    land_sqft_max: Optional[float],
    ceiling_height_min: Optional[float],
    floor_loading_min: Optional[float],
) -> List[str]:
    collection = get_property_listing_collections()
    filters: Dict[str, Any] = {"listing_status": "active"}

    def _irx(text: str) -> Dict:
        return {"$regex": re.escape(text), "$options": "i"}

    if offer_type:
        filters["offer.offer_type"] = offer_type
    if tenure:
        filters["tenure"] = _irx(tenure)

    category_clause: Optional[Dict] = None
    if property_category:
        expanded = expand_property_category(property_category)
        category_clause = {"$or": [
            {"main_category": {"$in": expanded}},
            {"sub_categories": {"$in": expanded}},
        ]}

    locality_clause: Optional[Dict] = None
    if locality:
        rx = _irx(locality)
        locality_clause = {"$or": [
            {"location.address.address_region": rx},
            {"location.industrial_park_name": rx},
            {"location.address.street_address": rx},
        ]}

    if region:
        filters["location.address.address_locality"] = _irx(region)

    if category_clause and locality_clause:
        filters["$and"] = [category_clause, locality_clause]
    elif category_clause:
        filters["$or"] = category_clause["$or"]
    elif locality_clause:
        filters["$or"] = locality_clause["$or"]

    price_f: Dict = {}
    if price_min is not None:
        price_f["$gte"] = price_min
    if price_max is not None:
        price_f["$lte"] = price_max
    if price_f:
        filters["offer.price"] = price_f

    built_up_f: Dict = {}
    if built_up_sqft_min is not None:
        built_up_f["$gte"] = built_up_sqft_min
    if built_up_sqft_max is not None:
        built_up_f["$lte"] = built_up_sqft_max
    if built_up_f:
        filters["built_up_area.value"] = built_up_f

    land_f: Dict = {}
    if land_sqft_min is not None:
        land_f["$gte"] = land_sqft_min
    if land_sqft_max is not None:
        land_f["$lte"] = land_sqft_max
    if land_f:
        filters["land_size.value"] = land_f

    if ceiling_height_min is not None:
        filters["ceiling_height"] = {"$gte": ceiling_height_min}
    if floor_loading_min is not None:
        filters["floor_loading"] = {"$gte": floor_loading_min}

    docs = list(
        collection.find(filters, {"property_id": 1, "_id": 0}).limit(_MAX_CANDIDATES)
    )
    return [str(doc["property_id"]) for doc in docs if doc.get("property_id")]


def _fetch_by_ids(ids: List[str]) -> List[Dict[str, Any]]:
    collection = get_property_listing_collections()
    docs = {
        str(doc["property_id"]): doc
        for doc in collection.find({"property_id": {"$in": ids}})
        if doc.get("property_id")
    }
    results = []
    for pid in ids:
        doc = docs.get(pid)
        if not doc:
            continue
        offer = doc.get("offer") or {}
        location = doc.get("location") or {}
        address = location.get("address") or {}
        built_up = doc.get("built_up_area") or {}
        land = doc.get("land_size") or {}
        listed_date = doc.get("listed_date")
        results.append({
            "property_id": pid,
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
            "ceiling_height": doc.get("ceiling_height"),
            "floor_loading": doc.get("floor_loading"),
            "listed_date": listed_date.isoformat() if listed_date else None,
        })
    return results


@tool
async def asearch_properties(
    query: str = "",
    offer_type: Optional[Literal["sale", "rent"]] = None,
    tenure: Optional[str] = None,
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
    pool_hint: str = "medium",
) -> Dict[str, Any]:
    """
    Two-stage hybrid search for active industrial properties.
    Stage 1: MongoDB structured filters → deterministic candidate set.
    Stage 2: Upstash semantic re-ranking within that set (only when query has keywords).

    query: Description-level keywords ONLY — features not captured by structured filters.
           Leave empty when only structured filters apply.
           Examples: "solar panel ready", "ramp access loading bay", "double-storey office".
    locality: City/district free text. Normalise abbreviations before passing:
              "PJ" → "Petaling Jaya" | "CS Lin" → "Chan Sow Lin" | "KL" → "Kuala Lumpur".
    region: State free text. Examples: "Selangor", "Kuala Lumpur", "Negeri Sembilan".
    """
    writer = get_stream_writer()

    active_filter_count = sum([
        offer_type is not None,
        tenure is not None,
        bool(property_category),
        bool(locality),
        bool(region),
        price_min is not None or price_max is not None,
        built_up_sqft_min is not None or built_up_sqft_max is not None,
        land_sqft_min is not None or land_sqft_max is not None,
        ceiling_height_min is not None,
        floor_loading_min is not None,
    ])
    writer({"event": "tool_start", "tool": "search_properties",
            "query": query, "filters": active_filter_count})

    candidate_ids = await asyncio.to_thread(
        _run_mongodb_query,
        offer_type, tenure, property_category, locality, region,
        price_min, price_max, built_up_sqft_min, built_up_sqft_max,
        land_sqft_min, land_sqft_max, ceiling_height_min, floor_loading_min,
    )

    if not candidate_ids:
        writer({"event": "tool_complete", "tool": "search_properties",
                "found": 0, "ids": []})
        return {
            "total_found": 0,
            "property_listing_id": [],
            "property_listing_result": [],
            "comments": "No matching properties found.",
        }

    final_ids = candidate_ids
    if query.strip():
        top_k = {"narrow": 30, "medium": 60, "broad": 100}.get(pool_hint, 60)
        id_list = ", ".join(f'"{pid}"' for pid in candidate_ids)
        upstash_filter = f'listing_status = "active" AND property_id IN ({id_list})'
        try:
            raw = await async_index.query(
                data=query,
                top_k=min(top_k, len(candidate_ids)),
                include_metadata=True,
                filter=upstash_filter,
            )
            seen: set = set()
            semantic_ids: List[str] = []
            for r in raw:
                pid = str((r.metadata or {}).get("property_id", ""))
                if pid and pid not in seen:
                    seen.add(pid)
                    semantic_ids.append(pid)
            if semantic_ids:
                final_ids = semantic_ids
        except Exception:
            pass  # keep Stage 1 results on Upstash failure

    results = await asyncio.to_thread(_fetch_by_ids, final_ids)

    def _unique(key: str) -> List:
        return list(dict.fromkeys(r[key] for r in results if r.get(key)))

    ids = [r["property_id"] for r in results]
    writer({"event": "tool_complete", "tool": "search_properties",
            "found": len(results), "ids": ids})

    return {
        "total_found": len(results),
        "property_listing_id": ids,
        "property_listing_result": results,
        "comments": (
            f"Breakdown — locality: {_unique('locality')}, "
            f"region: {_unique('region')}, "
            f"category: {_unique('main_category')}"
        ),
    }
