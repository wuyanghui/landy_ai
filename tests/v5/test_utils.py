import sys
from pathlib import Path
from datetime import datetime

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from agent.v5.tools._utils import expand_property_category, serialize_listing, serialize_listing_detail


def _make_doc(**overrides):
    doc = {
        "property_id": 42,
        "title": "Factory in Shah Alam",
        "slug": "factory-shah-alam",
        "thumbnail": "https://example.com/img.webp",
        "offer": {"offer_type": "sale", "price": 3_000_000, "currency": "MYR"},
        "price_per_sqft": 150.0,
        "location": {
            "hierarchy": {
                "city": {"name": "Shah Alam"},
                "state": {"name": "Selangor"},
                "industrial_park": {"name": "Hicom-Glenmarie Industrial Park"},
            },
            "address": {"street": "Jalan Perindustrian 1"},
            "nearest": {
                "highway": {"name": "KESAS", "distance_km": 2.1},
                "port": {"name": "Northport", "distance_km": 18.0},
                "airport": {"name": "Subang Airport", "distance_km": 12.0},
                "mrt_station": {"name": "USJ 7", "distance_km": 3.0},
            },
            "key_distances": {"klia": {"drive_distance_km": 55.0}},
        },
        "main_category": "factory",
        "sub_categories": ["detached-factory"],
        "tenure": {"type": "freehold"},
        "built_up_area_sqft": 20000.0,
        "land_size_sqft": 35000.0,
        "traits": {
            "building": {"ceiling_height_m": 9.14, "completion_year": 2022},
            "industrial": {
                "floor_loading_kn_m2": 29.42,
                "power_supply": {"amps": 200, "phase": 3},
                "loading_bays": {"count": 2},
                "office_area_sqft": 3000.0,
                "overhead_crane": None,
            },
        },
        "listed_date": datetime(2025, 1, 1),
        "ai_summary": "Factory in Shah Alam with 40ft ceiling.",
        "extracted_key_features": ["40ft ceiling", "solar-ready"],
        "investment_highlights": ["newly-completed"],
        "target_buyer_personas": ["manufacturing"],
        "description": "Full description here.",
        "unique_value_propositions": ["Prime location"],
        "risk_factors": [],
        "images": [{"url": "https://example.com/img.webp", "is_primary": True}],
        "similar_listing_id": [10, 11],
    }
    doc.update(overrides)
    return doc


# ── category expansion ────────────────────────────────────────────────────────

def test_factory_expands():
    result = expand_property_category(["factory"])
    assert set(result) == {"factory", "cluster-factory", "detached-factory", "semi-d-factory", "terrace-factory"}


def test_warehouse_passthrough():
    assert expand_property_category(["warehouse"]) == ["warehouse"]


def test_mixed_expansion():
    result = expand_property_category(["factory", "warehouse"])
    assert "warehouse" in result
    assert "detached-factory" in result


def test_empty_list():
    assert expand_property_category([]) == []


# ── serialize_listing ─────────────────────────────────────────────────────────

def test_serialize_listing_core_fields():
    s = serialize_listing(_make_doc())
    assert s["property_id"] == "42"
    assert s["title"] == "Factory in Shah Alam"
    assert s["slug"] == "factory-shah-alam"
    assert s["offer_type"] == "sale"
    assert s["price"] == 3_000_000
    assert s["currency"] == "MYR"
    assert s["city"] == "Shah Alam"
    assert s["state"] == "Selangor"
    assert s["industrial_park"] == "Hicom-Glenmarie Industrial Park"
    assert s["tenure"] == "freehold"
    assert s["built_up_sqft"] == 20000.0
    assert s["land_sqft"] == 35000.0
    assert s["ceiling_height_m"] == 9.14
    assert s["floor_loading_kn_m2"] == 29.42


def test_serialize_listing_enrichment_fields():
    s = serialize_listing(_make_doc())
    assert s["ai_summary"] == "Factory in Shah Alam with 40ft ceiling."
    assert "solar-ready" in s["extracted_key_features"]
    assert "newly-completed" in s["investment_highlights"]
    assert "manufacturing" in s["target_buyer_personas"]


def test_serialize_listing_nearest_highway():
    s = serialize_listing(_make_doc())
    assert s["nearest_highway"]["name"] == "KESAS"
    assert s["nearest_highway"]["distance_km"] == 2.1


def test_serialize_listing_listed_date_isoformat():
    s = serialize_listing(_make_doc())
    assert s["listed_date"] == "2025-01-01T00:00:00"


def test_serialize_listing_null_date():
    doc = _make_doc()
    doc["listed_date"] = None
    s = serialize_listing(doc)
    assert s["listed_date"] is None


def test_serialize_listing_missing_hierarchy_graceful():
    doc = _make_doc()
    doc["location"]["hierarchy"]["industrial_park"] = None
    s = serialize_listing(doc)
    assert s["industrial_park"] is None


# ── serialize_listing_detail ──────────────────────────────────────────────────

def test_serialize_detail_includes_description():
    d = serialize_listing_detail(_make_doc())
    assert d["description"] == "Full description here."


def test_serialize_detail_includes_power_supply():
    d = serialize_listing_detail(_make_doc())
    assert d["power_supply"]["amps"] == 200
    assert d["power_supply"]["phase"] == 3


def test_serialize_detail_includes_images():
    d = serialize_listing_detail(_make_doc())
    assert len(d["images"]) == 1


def test_serialize_detail_includes_similar_listing_id():
    d = serialize_listing_detail(_make_doc())
    assert d["similar_listing_id"] == [10, 11]


def test_serialize_detail_includes_nearest():
    d = serialize_listing_detail(_make_doc())
    assert d["nearest"]["highway"]["name"] == "KESAS"
    assert d["nearest"]["port"]["name"] == "Northport"
