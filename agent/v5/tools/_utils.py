from typing import List, Optional, Dict, Any

FACTORY_EXPANSION_MAP = {
    "factory": ["factory", "cluster-factory", "detached-factory", "semi-d-factory", "terrace-factory"],
}


def expand_property_category(categories: List[str]) -> List[str]:
    expanded: set = set()
    for cat in categories:
        if cat in FACTORY_EXPANSION_MAP:
            expanded.update(FACTORY_EXPANSION_MAP[cat])
        else:
            expanded.add(cat)
    return list(expanded)


def serialize_listing(doc: Dict[str, Any]) -> Dict[str, Any]:
    offer = doc.get("offer") or {}
    location = doc.get("location") or {}
    hierarchy = location.get("hierarchy") or {}
    city = hierarchy.get("city") or {}
    state = hierarchy.get("state") or {}
    park = hierarchy.get("industrial_park") or {}
    address = location.get("address") or {}
    nearest = location.get("nearest") or {}
    highway = nearest.get("highway") or {}
    traits = doc.get("traits") or {}
    building = traits.get("building") or {}
    industrial = traits.get("industrial") or {}
    listed_date = doc.get("listed_date")

    return {
        "property_id": str(doc.get("property_id", "")),
        "title": doc.get("title"),
        "slug": doc.get("slug"),
        "thumbnail": doc.get("thumbnail"),
        "offer_type": offer.get("offer_type"),
        "price": offer.get("price"),
        "currency": offer.get("currency"),
        "price_per_sqft": doc.get("price_per_sqft"),
        "city": city.get("name"),
        "state": state.get("name"),
        "industrial_park": park.get("name") if park else None,
        "street": address.get("street"),
        "main_category": doc.get("main_category"),
        "sub_categories": doc.get("sub_categories") or [],
        "tenure": (doc.get("tenure") or {}).get("type"),
        "built_up_sqft": doc.get("built_up_area_sqft"),
        "land_sqft": doc.get("land_size_sqft"),
        "ceiling_height_m": building.get("ceiling_height_m"),
        "floor_loading_kn_m2": industrial.get("floor_loading_kn_m2"),
        "nearest_highway": {"name": highway.get("name"), "distance_km": highway.get("distance_km")} if highway else None,
        "listed_date": listed_date.isoformat() if listed_date else None,
        "ai_summary": doc.get("ai_summary"),
        # enriched_property_listing stores this as key_features
        "extracted_key_features": doc.get("extracted_key_features") or doc.get("key_features") or [],
        "investment_highlights": doc.get("investment_highlights") or [],
        "target_buyer_personas": doc.get("target_buyer_personas") or [],
    }


def serialize_chat_listing(doc: Dict[str, Any]) -> Dict[str, Any]:
    """Shape consumed directly by the frontend ChatListingCard
    (industrialprop_FE app/landy-ai/types.ts ChatListing)."""
    offer = doc.get("offer") or {}
    location = doc.get("location") or {}
    hierarchy = location.get("hierarchy") or {}
    address = location.get("address") or {}
    industrial = (doc.get("traits") or {}).get("industrial") or {}
    power = industrial.get("power_supply") or {}
    updated_at = doc.get("updated_at")

    # GeoJSON point is [lng, lat]
    point = ((location.get("geo") or {}).get("point") or {}).get("coordinates") or []
    lng = point[0] if len(point) > 0 else None
    lat = point[1] if len(point) > 1 else None

    def _name(node: Optional[Dict]) -> Optional[str]:
        return (node or {}).get("name")

    power_spec = None
    if power.get("amps") is not None:
        unit = f"A ({power['phase']}-phase)" if power.get("phase") else "A"
        power_spec = {"value": power["amps"], "unit": unit}

    return {
        "id": str(doc.get("property_id", "")),
        "slug": doc.get("slug", ""),
        "title": doc.get("title", ""),
        "price": offer.get("price"),
        "currency": offer.get("currency"),
        "type": offer.get("offer_type"),
        "category_type": list(dict.fromkeys(
            ([doc["main_category"]] if doc.get("main_category") else [])
            + (doc.get("sub_categories") or [])
        )),
        "location": {
            "address": address.get("street") or None,
            "area": _name(hierarchy.get("industrial_park")),
            "district": _name(hierarchy.get("city")),
            "state": _name(hierarchy.get("state")),
            "coordinates": {"lat": lat, "lng": lng},
        },
        "specifications": {
            "built_size": {"value": doc["built_up_area_sqft"], "unit": "sqft"} if doc.get("built_up_area_sqft") else None,
            "land_area": {"value": doc["land_size_sqft"], "unit": "sqft"} if doc.get("land_size_sqft") else None,
            "power_supply": power_spec,
        },
        "images": doc.get("images") or [],
        "featured": bool(doc.get("is_featured", False)),
        "updated_at": updated_at.isoformat() if hasattr(updated_at, "isoformat") else updated_at,
    }


def serialize_listing_detail(doc: Dict[str, Any]) -> Dict[str, Any]:
    base = serialize_listing(doc)
    location = doc.get("location") or {}
    traits = doc.get("traits") or {}
    industrial = (traits.get("industrial") or {})
    building = (traits.get("building") or {})

    base.update({
        "description": doc.get("description"),
        "unique_value_propositions": doc.get("unique_value_propositions") or [],
        "risk_factors": doc.get("risk_factors") or [],
        "power_supply": industrial.get("power_supply"),
        "loading_bays": industrial.get("loading_bays"),
        "office_area_sqft": industrial.get("office_area_sqft"),
        "overhead_crane": industrial.get("overhead_crane"),
        "yard_area_sqft": industrial.get("yard_area_sqft"),
        "completion_year": building.get("completion_year"),
        "images": doc.get("images") or [],
        "nearest": location.get("nearest"),
        "key_distances": location.get("key_distances"),
        # enriched_property_listing stores this as similar_listing_ids
        "similar_listing_id": doc.get("similar_listing_id") or doc.get("similar_listing_ids") or [],
    })
    return base
