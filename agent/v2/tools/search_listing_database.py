from langchain.agents import create_agent
from langchain_openai import ChatOpenAI
from utility.llm_init import load_llm
from langgraph.checkpoint.memory import InMemorySaver  

from typing import Optional, Literal, TypedDict, Dict, Any, List
from langchain.tools import tool
from utility.property_listing_init import get_property_listing_collections
# ----------------------------
# TypedDict (NO defaults here)
# ----------------------------

class ListingFilter(TypedDict, total=False):
    offer_type: Literal['sale', 'rent']
    tenure: Literal['leasehold', 'freehold']
    market_status: Literal['subsales', 'primary']
    category: List[Literal[
        'factory',
        'industrial-land',
        'warehouse',
        'cluster-factory',
        'semi-d-factory',
        'detached-factory',
        'terrace-factory',
        'agricultural-land',
        'shoplot',
        'showroom',
        'car-showroom'
    ]]
    min_price: float
    max_price: float
    currency: str
    min_land_size: float
    max_land_size: float
    min_office_area: float
    max_office_area: float
    min_built_up_size: float
    max_built_up_size: float
    min_ceiling_height: float
    max_ceiling_height: float
    min_power_supply: float
    max_power_supply: float
    location: List[str]


# ----------------------------
# Tool
# ----------------------------

from typing import Dict, Any
from langchain.tools import tool
import json
from agent.v2.utility import _serialize_listing_detail, _serialize_public_listing
from agent.v2.utility import _serialize_listing_detail, get_listing_by_ids

@tool(
    "search_listing_property_from_database",
    description="Search property listings using structured optional filters"
)
def search_listing_property_from_database(input: ListingFilter) -> Dict[str, Any]:

    query: Dict[str, Any] = {}

    # ----------------------------
    # Offer & category
    # ----------------------------

    if 'offer_type' in input:
        query['offer.offer_type'] = input['offer_type']

    if 'category' in input and input['category']:
        query['$or'] = [
            {'main_category': {'$in': input['category']}},
            {'sub_categories': {'$in': input['category']}}
        ]

    if 'tenure' in input:
        query['tenure'] = input['tenure']

    if 'market_status' in input:
        query['market_status'] = input['market_status']

    # ----------------------------
    # Price range
    # ----------------------------

    if 'min_price' in input or 'max_price' in input:
        price_q = {}
        if 'min_price' in input:
            price_q['$gte'] = input['min_price']
        if 'max_price' in input:
            price_q['$lte'] = input['max_price']
        query['offer.price'] = price_q

    if 'currency' in input:
        query['offer.price_currency'] = input['currency']

    # ----------------------------
    # Land size
    # ----------------------------

    if 'min_land_size' in input or 'max_land_size' in input:
        land_q = {}
        if 'min_land_size' in input:
            land_q['$gte'] = input['min_land_size']
        if 'max_land_size' in input:
            land_q['$lte'] = input['max_land_size']
        query['land_size.value'] = land_q

    # ----------------------------
    # Built-up area
    # ----------------------------

    if 'min_built_up_size' in input or 'max_built_up_size' in input:
        built_q = {}
        if 'min_built_up_size' in input:
            built_q['$gte'] = input['min_built_up_size']
        if 'max_built_up_size' in input:
            built_q['$lte'] = input['max_built_up_size']
        query['built_up_area.value'] = built_q

    # ----------------------------
    # Office area
    # ----------------------------

    if 'min_office_area' in input or 'max_office_area' in input:
        office_q = {}
        if 'min_office_area' in input:
            office_q['$gte'] = input['min_office_area']
        if 'max_office_area' in input:
            office_q['$lte'] = input['max_office_area']
        query['office_area.value'] = office_q

    # ----------------------------
    # Ceiling height
    # ----------------------------

    if 'min_ceiling_height' in input or 'max_ceiling_height' in input:
        height_q = {}
        if 'min_ceiling_height' in input:
            height_q['$gte'] = input['min_ceiling_height']
        if 'max_ceiling_height' in input:
            height_q['$lte'] = input['max_ceiling_height']
        query['ceiling_height.value'] = height_q

    # ----------------------------
    # Power supply
    # ----------------------------

    if 'min_power_supply' in input or 'max_power_supply' in input:
        power_q = {}
        if 'min_power_supply' in input:
            power_q['$gte'] = input['min_power_supply']
        if 'max_power_supply' in input:
            power_q['$lte'] = input['max_power_supply']
        query['power_supply.value'] = power_q

    # ----------------------------
    # Location (fuzzy match)
    # ----------------------------

    if input.get('location'):
        location_or = []

        for loc in input['location']:
            location_or.extend([
                {'location.industrial_park_name': {'$regex': loc, '$options': 'i'}},
                {'location.address.address_locality': {'$regex': loc, '$options': 'i'}},
                {'location.address.street_address': {'$regex': loc, '$options': 'i'}},
                {'location.address.address_region': {'$regex': loc, '$options': 'i'}},
                {'description': {'$regex': loc, '$options': 'i'}},
            ])

        query['$or'] = location_or

    # ----------------------------
    # Execute query
    # ----------------------------

    cursor = get_property_listing_collections().find(
        query
    )

    results = list(cursor)

    # ----------------------------
    # Output shaping (LLM-friendly)
    # ----------------------------

    if len(results) > 10:
        return json.dumps({
            "filters_applied": query,
            "listing_count": len(results),
            "property_ids": [r['property_id'] for r in results]
        })
    
    all_industrial_listing = list(get_property_listing_collections().find())

    return json.dumps({
        "filters_applied": query,
        "listing_count": len(results),
        "property_ids": [r['property_id'] for r in results],
        "recommended_listing": get_listing_by_ids(all_industrial_listing, [r['property_id'] for r in results])
    })
