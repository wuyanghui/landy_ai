import sys, asyncio
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import agent.v4.tools.property_detail as pd_mod


def _full_doc(pid):
    return {
        "property_id": pid,
        "title": "Test Warehouse",
        "slug": f"test-warehouse-{pid}",
        "description": "A great warehouse with good loading bays.",
        "offer": {"offer_type": "sale", "price": 3_000_000, "price_currency": "MYR"},
        "location": {
            "address": {
                "street_address": "Lot 5 Jalan Industri",
                "address_region": "Klang",
                "address_locality": "Selangor",
                "postal_code": "41000",
            },
            "geo": {"point": {"type": "Point", "coordinates": [101.45, 3.05]}},
            "industrial_park_name": "Kapar Industrial Estate",
        },
        "main_category": "warehouse",
        "sub_categories": [],
        "market_status": "active",
        "built_up_area": {"value": 10_000, "unit": "sqft"},
        "land_size": {"value": 15_000, "unit": "sqft"},
        "construction": {"completion_year": 2015},
        "power_supply": {"value": 200, "unit": "amp"},
        "floor_loading": {"value": 1000, "unit": "kg/sqm"},
        "ceiling_height": {"value": 9, "unit": "m"},
        "loading_bays": 4,
        "key_features": ["CCTV", "Fenced"],
        "is_featured": True,
        "listed_date": None,
        "last_updated": None,
        "seo_title": "Test Warehouse for Sale",
        "seo_description": "SEO desc",
        "thumbnail": "https://example.com/img.jpg",
        "images": [],
    }


class _FakeCollection:
    def __init__(self, doc):
        self._doc = doc

    def find_one(self, query):
        if query.get("property_id") == self._doc["property_id"]:
            return self._doc
        return None


def test_detail_returns_serialized_listing(monkeypatch):
    monkeypatch.setattr(
        "agent.v4.tools.property_detail.get_stream_writer",
        lambda: lambda d: None,
    )
    monkeypatch.setattr(
        "agent.v4.tools.property_detail.get_property_listing_collections",
        lambda: _FakeCollection(_full_doc("PROP-XYZ")),
    )

    result = asyncio.run(pd_mod.aget_property_detail.ainvoke({"property_id": "PROP-XYZ"}))

    assert result["id"] == "PROP-XYZ"
    assert result["description"] == "A great warehouse with good loading bays."
    assert result["specifications"]["loading_bays"] == 4


def test_detail_returns_none_for_unknown_id(monkeypatch):
    monkeypatch.setattr(
        "agent.v4.tools.property_detail.get_stream_writer",
        lambda: lambda d: None,
    )
    monkeypatch.setattr(
        "agent.v4.tools.property_detail.get_property_listing_collections",
        lambda: _FakeCollection(_full_doc("PROP-XYZ")),
    )

    result = asyncio.run(pd_mod.aget_property_detail.ainvoke({"property_id": "MISSING"}))
    assert result is None


def test_detail_emits_tool_events(monkeypatch):
    events = []
    monkeypatch.setattr(
        "agent.v4.tools.property_detail.get_stream_writer",
        lambda: lambda d: events.append(d),
    )
    monkeypatch.setattr(
        "agent.v4.tools.property_detail.get_property_listing_collections",
        lambda: _FakeCollection(_full_doc("PROP-XYZ")),
    )

    asyncio.run(pd_mod.aget_property_detail.ainvoke({"property_id": "PROP-XYZ"}))

    assert any(e["event"] == "tool_start" for e in events)
    assert any(e["event"] == "tool_complete" for e in events)
