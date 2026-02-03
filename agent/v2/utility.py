from typing import Dict, Any

def _serialize_public_listing(doc: Dict[str, Any]) -> Dict[str, Any]:
    offer = doc.get("offer") or {}
    location = doc.get("location") or {}
    address = location.get("address") or {}
    geo = location.get("geo") or {}

    return {
        "id":       doc.get("property_id", ""),
        "slug":     doc.get("slug", ""),
        "title":    doc.get("title", ""),
        "price":    offer.get("price", ""),
        "currency": offer.get("price_currency", ""),
        "type":     offer.get("offer_type", ""),

        "category_type": (
            [doc["main_category"]] if doc.get("main_category") else []
        ) + doc.get("sub_categories", []),

        "location": {
            "address":  address.get("street_address", ""),
            "area":     location.get("industrial_park_name", ""),
            "district": address.get("address_region", ""),
            "state":    address.get("address_locality", ""),
            "coordinates": {
                "lat": geo.get("latitude", ""),
                "lng": geo.get("longitude", ""),
            },
        },

        "specifications": {
            "built_size":   doc.get("built_up_area", ""),
            "land_area":    doc.get("land_size", ""),
            "power_supply": doc.get("power_supply", ""),
        },

        "images":     doc.get("images", []),
        "featured":   doc.get("is_featured", False),
        "updated_at": doc.get("last_updated", ""),
    }



def _serialize_listing_detail(doc: Dict[str, Any]) -> Dict[str, Any]:
    offer = doc.get("offer") or {}
    location = doc.get("location") or {}
    address = location.get("address") or {}
    geo = location.get("geo") or {}
    construction = doc.get("construction") or {}

    return {
        "id":          doc.get("property_id", ""),
        "slug":        doc.get("slug", ""),
        "title":       doc.get("title", ""),
        "description": doc.get("description", ""),

        "price":    offer.get("price", ""),
        "currency": offer.get("price_currency", ""),
        "type":     offer.get("offer_type", ""),

        "category_type": (
            [doc["main_category"]] if doc.get("main_category") else []
        ) + doc.get("sub_categories", []),

        "status": doc.get("market_status", ""),

        "location": {
            "address":  address.get("street_address", ""),
            "area":     location.get("industrial_park_name", ""),
            "district": address.get("address_region", ""),
            "state":    address.get("address_locality", ""),
            "postcode": address.get("postal_code", ""),
            "coordinates": {
                "lat": geo.get("latitude", ""),
                "lng": geo.get("longitude", ""),
            },
        },

        "specifications": {
            "built_size":     doc.get("built_up_area", ""),
            "land_area":      doc.get("land_size", ""),
            "built_year":     construction.get("completion_year", ""),
            "power_supply":   doc.get("power_supply", ""),
            "floor_loading":  doc.get("floor_loading", ""),
            "ceiling_height": doc.get("ceiling_height", ""),
            "loading_bays":   doc.get("loading_bays", ""),
        },

        "features":        doc.get("key_features", []),
        "business_nature": "",

        "images":     doc.get("images", []),
        "floor_plan": "",

        "seo": {
            "meta_title":       doc.get("seo_title", ""),
            "meta_description": doc.get("seo_description", ""),
            "og_image":         doc.get("thumbnail", ""),
        },

        "featured":   doc.get("is_featured", False),
        "views":      0,

        "created_at": doc.get("listed_date", ""),
        "updated_at": doc.get("last_updated", ""),
    }


def get_listing_by_ids(all_industrial_listing, property_ids):
    """
    Filter a list of listings and return only those whose property_id is in property_ids.

    Args:
        all_industrial_listing (List[dict]): List of all listings.
        property_ids (List[str]): List of property_id strings to filter.

    Returns:
        List[dict]: Filtered listings matching the given property_ids.
    """
    property_id_set = set(property_ids)  # for O(1) lookups

    filtered_listings = [
        listing for listing in all_industrial_listing
        if listing.get("property_id") in property_id_set
    ]

    return [_serialize_listing_detail(x) for x in filtered_listings]