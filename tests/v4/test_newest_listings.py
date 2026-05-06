import sys, asyncio
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import agent.v4.tools.newest_listings as nl_mod


def _make_doc(pid):
    return {
        "property_id": pid,
        "title": f"Property {pid}",
        "slug": f"prop-{pid}",
        "offer": {"offer_type": "sale", "price": 2_000_000, "price_currency": "MYR"},
        "location": {
            "address": {
                "address_region": "Klang",
                "address_locality": "Selangor",
                "street_address": "123 Jalan Industri",
            }
        },
        "main_category": "warehouse",
        "sub_categories": [],
        "built_up_area": {"value": 5000, "unit": "sqft"},
        "land_size": {"value": 8000, "unit": "sqft"},
        "listed_date": None,
    }


class _FakeSortingCollection:
    """Mimics collection.find().sort().limit()."""
    def __init__(self, docs):
        self._docs = docs
        self.last_filter = None
        self.last_sort = None
        self.last_limit = None

    def find(self, query):
        self.last_filter = query
        return self

    def sort(self, key):
        self.last_sort = key
        return self

    def limit(self, n):
        self.last_limit = n
        return iter(self._docs)


def test_newest_returns_property_ids(monkeypatch):
    monkeypatch.setattr(
        "agent.v4.tools.newest_listings.get_stream_writer",
        lambda: lambda d: None,
    )
    fake_col = _FakeSortingCollection([_make_doc("PROP-A"), _make_doc("PROP-B")])
    monkeypatch.setattr(
        "agent.v4.tools.newest_listings.get_property_listing_collections",
        lambda: fake_col,
    )

    result = asyncio.run(nl_mod.aget_newest_listings.ainvoke({}))
    assert result["total_found"] == 2
    assert "PROP-A" in result["property_listing_id"]


def test_newest_applies_offer_type_filter(monkeypatch):
    monkeypatch.setattr(
        "agent.v4.tools.newest_listings.get_stream_writer",
        lambda: lambda d: None,
    )
    fake_col = _FakeSortingCollection([])
    monkeypatch.setattr(
        "agent.v4.tools.newest_listings.get_property_listing_collections",
        lambda: fake_col,
    )

    asyncio.run(nl_mod.aget_newest_listings.ainvoke({"offer_type": "rent"}))
    assert fake_col.last_filter["offer.offer_type"] == "rent"


def test_newest_applies_region_filter(monkeypatch):
    monkeypatch.setattr(
        "agent.v4.tools.newest_listings.get_stream_writer",
        lambda: lambda d: None,
    )
    fake_col = _FakeSortingCollection([])
    monkeypatch.setattr(
        "agent.v4.tools.newest_listings.get_property_listing_collections",
        lambda: fake_col,
    )

    asyncio.run(nl_mod.aget_newest_listings.ainvoke({"region": ["Selangor"]}))
    assert fake_col.last_filter["location.address.address_locality"] == {"$in": ["Selangor"]}


def test_newest_emits_tool_events(monkeypatch):
    events = []
    monkeypatch.setattr(
        "agent.v4.tools.newest_listings.get_stream_writer",
        lambda: lambda d: events.append(d),
    )
    fake_col = _FakeSortingCollection([])
    monkeypatch.setattr(
        "agent.v4.tools.newest_listings.get_property_listing_collections",
        lambda: fake_col,
    )

    asyncio.run(nl_mod.aget_newest_listings.ainvoke({}))
    assert any(e["event"] == "tool_start" for e in events)
    assert any(e["event"] == "tool_complete" for e in events)
