import sys, asyncio
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import agent.v4.tools.properties_by_radius as pr_mod


def _make_doc(pid):
    return {
        "property_id": pid,
        "title": f"Property {pid}",
        "slug": f"prop-{pid}",
        "offer": {"offer_type": "sale", "price": 1_500_000, "price_currency": "MYR"},
        "location": {
            "address": {"address_region": "Shah Alam", "address_locality": "Selangor", "street_address": "Lot 5"},
            "geo": {"point": {"type": "Point", "coordinates": [101.5, 3.07]}},
        },
        "main_category": "warehouse",
        "sub_categories": [],
        "built_up_area": {"value": 5000, "unit": "sqft"},
        "land_size": {"value": 8000, "unit": "sqft"},
        "listed_date": None,
    }


class _FakeCollection:
    def __init__(self, docs):
        self._docs = docs
        self.last_query = None

    def find(self, query):
        self.last_query = query
        return self

    def limit(self, n):
        return iter(self._docs)


def test_radius_returns_property_ids(monkeypatch):
    monkeypatch.setattr(
        "agent.v4.tools.properties_by_radius.get_stream_writer",
        lambda: lambda d: None,
    )
    fake_col = _FakeCollection([_make_doc("PROP-001"), _make_doc("PROP-002")])
    monkeypatch.setattr(
        "agent.v4.tools.properties_by_radius.get_property_listing_collections",
        lambda: fake_col,
    )

    result = asyncio.run(pr_mod.aget_properties_by_radius.ainvoke(
        {"lat": 3.07, "lng": 101.5, "radius_km": 5.0, "place_name": "Shah Alam"}
    ))

    assert result["total_found"] == 2
    assert "PROP-001" in result["property_listing_id"]


def test_radius_query_uses_near_sphere(monkeypatch):
    monkeypatch.setattr(
        "agent.v4.tools.properties_by_radius.get_stream_writer",
        lambda: lambda d: None,
    )
    fake_col = _FakeCollection([])
    monkeypatch.setattr(
        "agent.v4.tools.properties_by_radius.get_property_listing_collections",
        lambda: fake_col,
    )

    asyncio.run(pr_mod.aget_properties_by_radius.ainvoke(
        {"lat": 3.07, "lng": 101.5, "radius_km": 10.0, "place_name": "Klang"}
    ))

    geo_query = fake_col.last_query["location.geo.point"]
    assert "$nearSphere" in geo_query
    near = geo_query["$nearSphere"]
    assert near["$geometry"]["type"] == "Point"
    assert near["$geometry"]["coordinates"] == [101.5, 3.07]
    assert near["$maxDistance"] == 10_000  # 10 km in metres


def test_radius_emits_tool_events(monkeypatch):
    events = []
    monkeypatch.setattr(
        "agent.v4.tools.properties_by_radius.get_stream_writer",
        lambda: lambda d: events.append(d),
    )
    monkeypatch.setattr(
        "agent.v4.tools.properties_by_radius.get_property_listing_collections",
        lambda: _FakeCollection([]),
    )

    asyncio.run(pr_mod.aget_properties_by_radius.ainvoke(
        {"lat": 3.0, "lng": 101.0, "radius_km": 5.0}
    ))

    assert any(e["event"] == "tool_start" for e in events)
    assert any(e["event"] == "tool_complete" for e in events)


def test_radius_applies_offer_type_filter(monkeypatch):
    monkeypatch.setattr(
        "agent.v4.tools.properties_by_radius.get_stream_writer",
        lambda: lambda d: None,
    )
    fake_col = _FakeCollection([])
    monkeypatch.setattr(
        "agent.v4.tools.properties_by_radius.get_property_listing_collections",
        lambda: fake_col,
    )

    asyncio.run(pr_mod.aget_properties_by_radius.ainvoke(
        {"lat": 3.0, "lng": 101.0, "radius_km": 5.0, "offer_type": "rent"}
    ))

    assert fake_col.last_query.get("offer.offer_type") == "rent"
