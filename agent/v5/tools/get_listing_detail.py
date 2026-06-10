import asyncio
from typing import Optional, Dict, Any

from langchain_core.tools import tool
from langgraph.config import get_stream_writer

from agent.v5.tools._utils import serialize_listing_detail
from utility.property_listing_init import get_enriched_property_listing_collections


def _fetch_doc(property_id: str) -> Optional[Dict[str, Any]]:
    collection = get_enriched_property_listing_collections()
    try:
        pid = int(property_id)
    except (ValueError, TypeError):
        pid = property_id
    return collection.find_one({"property_id": pid})


@tool
async def get_listing_detail(property_id: str) -> Optional[Dict[str, Any]]:
    """
    Fetch full details for a single property by property_id.
    Use when the user asks about information not in search results:
    full description, loading bay specs, construction details, risk factors, images.
    Do NOT call for price, size, or location — those are already in find_listings results.
    """
    writer = get_stream_writer()

    doc = await asyncio.to_thread(_fetch_doc, property_id)
    if doc is None:
        return None

    detail = serialize_listing_detail(doc)
    writer({"event": "listing_detail_card", "listing": detail})
    return detail
