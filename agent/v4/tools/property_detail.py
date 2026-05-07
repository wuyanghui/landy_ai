import asyncio
from typing import Optional, Dict, Any

from langchain_core.tools import tool
from langgraph.config import get_stream_writer

from agent.v2.utility import _serialize_listing_detail
from utility.property_listing_init import get_property_listing_collections


def _fetch_detail(property_id: str) -> Optional[Dict[str, Any]]:
    collection = get_property_listing_collections()
    doc = collection.find_one({"property_id": property_id})
    if doc is None:
        return None
    return _serialize_listing_detail(doc)


@tool
async def aget_property_detail(property_id: str) -> Optional[Dict[str, Any]]:
    """
    Fetch full detail for a single industrial property by property_id.
    Use when user asks for info not in search results: description, key features,
    construction year, loading bays, office area, full specifications.
    Do NOT call for price, size, or location — those are already in search results.
    """
    writer = get_stream_writer()
    writer({"event": "tool_start", "tool": "property_detail", "property_id": property_id})

    result = await asyncio.to_thread(_fetch_detail, property_id)

    writer({"event": "tool_complete", "tool": "property_detail"})
    return result
