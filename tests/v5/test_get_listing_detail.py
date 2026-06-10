import sys, asyncio
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import agent.v5.tools.get_listing_detail as gld_mod


def _full_doc():
    return {
        "property_id": 7,
        "title": "Factory in Klang",
        "slug": "factory-klang",
        "thumbnail": None,
        "offer": {"offer_type": "rent", "price": 50000, "currency": "MYR"},
        "price_per_sqft": 2.5,
        "location": {
            "hierarchy": {
                "city": {"name": "Klang"},
                "state": {"name": "Selangor"},
                "industrial_park": None,
            },
            "address": {"street": "Jalan Meru"},
            "nearest": {"highway": {"name": "KESAS", "distance_km": 1.2}},
            "key_distances": {"klia": {"drive_distance_km": 60.0}},
        },
        "main_category": "factory",
        "sub_categories": [],
        "tenure": {"type": "leasehold"},
        "built_up_area_sqft": 8000.0,
        "land_size_sqft": 12000.0,
        "traits": {
            "building": {"ceiling_height_m": 7.62, "completion_year": 2019},
            "industrial": {
                "floor_loading_kn_m2": 15.0,
                "power_supply": {"amps": 100, "phase": 3},
                "loading_bays": {"count": 1},
                "office_area_sqft": 1000.0,
                "overhead_crane": None,
                "yard_area_sqft": None,
            },
        },
        "listed_date": None,
        "ai_summary": "Factory in Klang.",
        "extracted_key_features": ["loading bay"],
        "investment_highlights": [],
        "target_buyer_personas": ["manufacturing"],
        "description": "Full description.",
        "unique_value_propositions": ["Near highway"],
        "risk_factors": ["Leasehold"],
        "images": [],
        "similar_listing_id": [5, 6],
    }


def _patch(monkeypatch, doc):
    monkeypatch.setattr(gld_mod, "_fetch_doc", lambda pid: doc)
    monkeypatch.setattr(
        "agent.v5.tools.get_listing_detail.get_stream_writer",
        lambda: lambda d: None,
    )


def test_returns_full_detail(monkeypatch):
    _patch(monkeypatch, _full_doc())
    result = asyncio.run(gld_mod.get_listing_detail.ainvoke({"property_id": "7"}))
    assert result["property_id"] == "7"
    assert result["description"] == "Full description."
    assert result["power_supply"]["amps"] == 100
    assert result["similar_listing_id"] == [5, 6]


def test_returns_none_when_not_found(monkeypatch):
    _patch(monkeypatch, None)
    result = asyncio.run(gld_mod.get_listing_detail.ainvoke({"property_id": "999"}))
    assert result is None


def test_emits_listing_detail_card_event(monkeypatch):
    events = []
    _patch(monkeypatch, _full_doc())
    monkeypatch.setattr(
        "agent.v5.tools.get_listing_detail.get_stream_writer",
        lambda: lambda d: events.append(d),
    )
    asyncio.run(gld_mod.get_listing_detail.ainvoke({"property_id": "7"}))
    card_events = [e for e in events if e["event"] == "listing_detail_card"]
    assert len(card_events) == 1
    assert card_events[0]["listing"]["property_id"] == "7"


def test_no_event_emitted_when_not_found(monkeypatch):
    events = []
    _patch(monkeypatch, None)
    monkeypatch.setattr(
        "agent.v5.tools.get_listing_detail.get_stream_writer",
        lambda: lambda d: events.append(d),
    )
    asyncio.run(gld_mod.get_listing_detail.ainvoke({"property_id": "999"}))
    assert not any(e["event"] == "listing_detail_card" for e in events)
