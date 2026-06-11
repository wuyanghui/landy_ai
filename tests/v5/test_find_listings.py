import sys, asyncio, re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import agent.v5.tools.find_listings as fl_mod


def _fake_doc(pid, city="Shah Alam", state="Selangor"):
    return {
        "property_id": pid,
        "title": f"Property {pid}",
        "slug": f"prop-{pid}",
        "thumbnail": None,
        "offer": {"offer_type": "sale", "price": 2_000_000, "currency": "MYR"},
        "price_per_sqft": 100.0,
        "location": {
            "hierarchy": {
                "city": {"name": city, "aliases": [city.lower()], "slug": city.lower().replace(" ", "-")},
                "state": {"name": state, "aliases": [state.lower()], "slug": state.lower()},
                "industrial_park": None,
            },
            "address": {"street": "Jalan Test"},
            "nearest": {"highway": {"name": "KESAS", "distance_km": 3.0}},
        },
        "main_category": "factory",
        "sub_categories": [],
        "tenure": {"type": "freehold"},
        "built_up_area_sqft": 10000.0,
        "land_size_sqft": 20000.0,
        "traits": {
            "building": {"ceiling_height_m": 9.0},
            "industrial": {"floor_loading_kn_m2": 20.0},
        },
        "listed_date": None,
        "ai_summary": "A factory.",
        "extracted_key_features": [],
        "investment_highlights": [],
        "target_buyer_personas": [],
    }


def _patch(monkeypatch, docs=None):
    if docs is None:
        docs = []
    monkeypatch.setattr(fl_mod, "_run_query", lambda q, s: docs)
    monkeypatch.setattr(
        "agent.v5.tools.find_listings.get_stream_writer",
        lambda: lambda d: None,
    )


# ── return shape ──────────────────────────────────────────────────────────────

def test_returns_total_found(monkeypatch):
    _patch(monkeypatch, [_fake_doc("1"), _fake_doc("2")])
    result = asyncio.run(fl_mod.find_listings.ainvoke({}))
    assert result["total_found"] == 2


def test_returns_empty_on_no_results(monkeypatch):
    _patch(monkeypatch, [])
    result = asyncio.run(fl_mod.find_listings.ainvoke({}))
    assert result["total_found"] == 0
    assert result["property_listing_result"] == []


def test_results_include_enrichment_fields(monkeypatch):
    doc = _fake_doc("99")
    doc["extracted_key_features"] = ["solar-ready"]
    doc["ai_summary"] = "Great factory."
    _patch(monkeypatch, [doc])
    result = asyncio.run(fl_mod.find_listings.ainvoke({}))
    listing = result["property_listing_result"][0]
    assert listing["extracted_key_features"] == ["solar-ready"]
    assert listing["ai_summary"] == "Great factory."


def test_location_breakdown_in_return(monkeypatch):
    _patch(monkeypatch, [_fake_doc("1", city="Shah Alam"), _fake_doc("2", city="Klang")])
    result = asyncio.run(fl_mod.find_listings.ainvoke({}))
    assert "Shah Alam" in result["location_breakdown"]
    assert "Klang" in result["location_breakdown"]


# ── SSE events ────────────────────────────────────────────────────────────────

def test_emits_search_start_and_complete(monkeypatch):
    events = []
    _patch(monkeypatch, [])
    monkeypatch.setattr(
        "agent.v5.tools.find_listings.get_stream_writer",
        lambda: lambda d: events.append(d),
    )
    asyncio.run(fl_mod.find_listings.ainvoke({}))
    types = [e["event"] for e in events]
    assert "search_start" in types
    assert "search_complete" in types


def test_emits_property_cards_when_results(monkeypatch):
    events = []
    _patch(monkeypatch, [_fake_doc("1")])
    monkeypatch.setattr(
        "agent.v5.tools.find_listings.get_stream_writer",
        lambda: lambda d: events.append(d),
    )
    asyncio.run(fl_mod.find_listings.ainvoke({}))
    card_events = [e for e in events if e["event"] == "property_cards"]
    assert len(card_events) == 1
    assert len(card_events[0]["listings"]) == 1
    # cards carry the frontend ChatListing shape, not the LLM-facing flat shape
    card = card_events[0]["listings"][0]
    assert card["id"] == "1"
    assert card["type"] == "sale"
    assert "specifications" in card
    assert "coordinates" in card["location"]


# ── MongoDB query builder ─────────────────────────────────────────────────────

class _FakeCursor:
    def __init__(self, docs): self._docs = docs
    def sort(self, *a): return self
    def __iter__(self): return iter(self._docs)


class _FakeCollection:
    def __init__(self):
        self.last_query = None
    def find(self, q, *a, **kw):
        self.last_query = q
        return _FakeCursor([])


def test_build_filters_active_status():
    # listing_status is set by _build_filters, not _run_query
    filters = fl_mod._build_filters(
        offer_type=None, property_category=None, locality=None, region=None,
        price_min=None, price_max=None, built_up_sqft_min=None, built_up_sqft_max=None,
        land_sqft_min=None, land_sqft_max=None, ceiling_height_min=None, floor_loading_min=None,
        max_highway_km=None, max_port_km=None, max_airport_km=None,
    )
    assert filters["listing_status"] == "active"


def test_build_filters_offer_type():
    filters = fl_mod._build_filters(
        offer_type="rent", property_category=None, locality=None, region=None,
        price_min=None, price_max=None, built_up_sqft_min=None, built_up_sqft_max=None,
        land_sqft_min=None, land_sqft_max=None, ceiling_height_min=None, floor_loading_min=None,
        max_highway_km=None, max_port_km=None, max_airport_km=None,
    )
    assert filters["offer.offer_type"] == "rent"


def test_build_filters_price_range():
    filters = fl_mod._build_filters(
        offer_type=None, property_category=None, locality=None, region=None,
        price_min=1_000_000, price_max=5_000_000, built_up_sqft_min=None, built_up_sqft_max=None,
        land_sqft_min=None, land_sqft_max=None, ceiling_height_min=None, floor_loading_min=None,
        max_highway_km=None, max_port_km=None, max_airport_km=None,
    )
    assert filters["offer.price"]["$gte"] == 1_000_000
    assert filters["offer.price"]["$lte"] == 5_000_000


def test_build_filters_ceiling_height_new_schema_field():
    filters = fl_mod._build_filters(
        offer_type=None, property_category=None, locality=None, region=None,
        price_min=None, price_max=None, built_up_sqft_min=None, built_up_sqft_max=None,
        land_sqft_min=None, land_sqft_max=None, ceiling_height_min=9.0, floor_loading_min=None,
        max_highway_km=None, max_port_km=None, max_airport_km=None,
    )
    assert filters["traits.building.ceiling_height_m"] == {"$gte": 9.0}


def test_locality_builds_or_clause(monkeypatch):
    """build_filters with locality should produce $and with city/park name+alias+slug clauses."""
    filters = fl_mod._build_filters(
        offer_type=None, property_category=None, locality="Shah Alam",
        region=None, price_min=None, price_max=None,
        built_up_sqft_min=None, built_up_sqft_max=None,
        land_sqft_min=None, land_sqft_max=None,
        ceiling_height_min=None, floor_loading_min=None,
        max_highway_km=None, max_port_km=None, max_airport_km=None,
    )
    and_clauses = filters.get("$and", [])
    loc_clause = next((c for c in and_clauses if "$or" in c), None)
    assert loc_clause is not None
    or_fields = [list(c.keys())[0] for c in loc_clause["$or"]]
    assert "location.hierarchy.city.name" in or_fields
    assert "location.hierarchy.city.aliases" in or_fields
    assert "location.hierarchy.city.slug" in or_fields
    assert "location.hierarchy.industrial_park.name" in or_fields


def test_category_and_locality_use_and(monkeypatch):
    filters = fl_mod._build_filters(
        offer_type=None, property_category=["factory"], locality="Shah Alam",
        region=None, price_min=None, price_max=None,
        built_up_sqft_min=None, built_up_sqft_max=None,
        land_sqft_min=None, land_sqft_max=None,
        ceiling_height_min=None, floor_loading_min=None,
        max_highway_km=None, max_port_km=None, max_airport_km=None,
    )
    assert "$and" in filters
    assert "$or" not in filters  # no top-level $or — both in $and


def test_proximity_filter_highway(monkeypatch):
    filters = fl_mod._build_filters(
        offer_type=None, property_category=None, locality=None,
        region=None, price_min=None, price_max=None,
        built_up_sqft_min=None, built_up_sqft_max=None,
        land_sqft_min=None, land_sqft_max=None,
        ceiling_height_min=None, floor_loading_min=None,
        max_highway_km=5.0, max_port_km=None, max_airport_km=None,
    )
    assert filters["location.nearest.highway.distance_km"] == {"$lte": 5.0}
