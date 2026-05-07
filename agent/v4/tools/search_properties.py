import os
from typing import Literal, List, Optional, Dict, Any

from dotenv import load_dotenv
from langchain_core.tools import tool
from langgraph.config import get_stream_writer
from upstash_vector import AsyncIndex

from agent.v4.tools._utils import expand_property_category

load_dotenv()

async_index = AsyncIndex(
    url=os.getenv("UPSTASH_VECTOR_REST_URL"),
    token=os.getenv("UPSTASH_VECTOR_REST_TOKEN"),
)


@tool
async def asearch_properties(
    query: str,
    offer_type: Optional[Literal["sale", "rent"]] = None,
    tenure: Optional[Literal["leasehold", "freehold"]] = None,
    property_category: Optional[List[Literal[
        "agricultural-land", "cluster-factory", "detached-factory",
        "factory", "industrial-land", "semi-d-factory", "shoplot",
        "showroom", "terrace-factory", "warehouse"
    ]]] = None,
    locality: Optional[List[Literal[
        "Balakong", "Bandar Baru Bangi", "Bangi", "Banting", "Beranang",
        "Cheras", "Dengkil", "Dengkil, Sepang", "Hulu Langat", "Klang",
        "Kuala Langat", "Kuala Lumpur",
        "Lapangan Terbang Antarabangsa Kuala Lumpur", "Nilai",
        "Olak Lempit", "Petaling Jaya", "Semenyih", "Sepang", "Seputeh",
        "Seremban", "Seri Kembangan", "Shah Alam", "Shah Alam, Petaling",
        "Subang Jaya", "Telok Panglima Garang",
        "Teluk Panglima Garang, Kuala Langat"
    ]]] = None,
    region: Optional[List[Literal["Selangor", "Kuala Lumpur", "Negeri Sembilan"]]] = None,
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
    Search industrial property listings using Upstash Vector hybrid search.
    Default tool for any semantic or filter-based search. Use for queries without explicit distance.
    Query string template: '[use case] [property type] in [location] with [key feature]'.
    Max 12 words. Put numbers and prices in structured filter parameters only — not in the query string.
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

    top_k = {"narrow": 30, "medium": 60, "broad": 100}.get(pool_hint, 60)
    clauses: List[str] = []

    def _or_clause(field: str, values: List[str]) -> str:
        return "(" + " OR ".join([f'{field} = "{v}"' for v in values]) + ")"

    if offer_type:
        clauses.append(f'offer_type = "{offer_type}"')
    if tenure:
        clauses.append(f'tenure = "{tenure}"')
    if property_category:
        expanded = expand_property_category(property_category)
        clauses.append("(" + " OR ".join(
            [f'main_category = "{v}" OR sub_categories CONTAINS "{v}"' for v in expanded]
        ) + ")")
    if locality:
        clauses.append("(" + " OR ".join(
            [f'locality GLOB "*{loc}*"' for loc in locality]
        ) + ")")
    if region:
        clauses.append(_or_clause("region", region))
    if price_min is not None:
        clauses.append(f"price >= {price_min}")
    if price_max is not None:
        clauses.append(f"price <= {price_max}")
    if built_up_sqft_min is not None:
        clauses.append(f"built_up_sqft >= {built_up_sqft_min}")
    if built_up_sqft_max is not None:
        clauses.append(f"built_up_sqft <= {built_up_sqft_max}")
    if land_sqft_min is not None:
        clauses.append(f"land_sqft >= {land_sqft_min}")
    if land_sqft_max is not None:
        clauses.append(f"land_sqft <= {land_sqft_max}")
    if ceiling_height_min is not None:
        clauses.append(f"ceiling_height >= {ceiling_height_min}")
    if floor_loading_min is not None:
        clauses.append(f"floor_loading >= {floor_loading_min}")
    clauses.append('listing_status = "active"')

    filter_str = " AND ".join(clauses)
    raw = await async_index.query(
        data=query, top_k=top_k, include_metadata=True, filter=filter_str
    )

    seen: set = set()
    results = []
    for r in raw:
        meta = r.metadata or {}
        pid = meta.get("property_id")
        if not pid or pid in seen:
            continue
        seen.add(pid)
        results.append({
            "property_id": pid,
            "title": meta.get("title"),
            "slug": meta.get("slug"),
            "offer_type": meta.get("offer_type"),
            "price": meta.get("price"),
            "locality": meta.get("locality"),
            "region": meta.get("region"),
            "main_category": meta.get("main_category"),
            "sub_categories": meta.get("sub_categories"),
            "tenure": meta.get("tenure"),
            "land_sqft": meta.get("land_sqft"),
            "built_up_sqft": meta.get("built_up_sqft"),
            "ceiling_height": meta.get("ceiling_height"),
            "floor_loading": meta.get("floor_loading"),
            "matched_text": meta.get("parent_text") or "",
            "score": r.score,
        })

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
