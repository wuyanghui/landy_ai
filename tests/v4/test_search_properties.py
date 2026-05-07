import sys, asyncio
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import agent.v4.tools.search_properties as sp_mod


class _FakeResult:
    def __init__(self, pid, score=0.9):
        self.score = score
        self.metadata = {
            "property_id": pid,
            "title": f"Property {pid}",
            "slug": f"prop-{pid}",
            "offer_type": "sale",
            "price": 1_000_000,
            "locality": "Shah Alam",
            "region": "Selangor",
            "main_category": "warehouse",
            "sub_categories": [],
            "tenure": "freehold",
            "land_sqft": 5000,
            "built_up_sqft": 3000,
            "ceiling_height": 6.0,
            "floor_loading": 500,
            "parent_text": "description text",
        }


def test_search_returns_property_ids(monkeypatch):
    monkeypatch.setattr(
        "agent.v4.tools.search_properties.get_stream_writer",
        lambda: lambda d: None,
    )

    async def fake_query(**kwargs):
        return [_FakeResult("PROP-001"), _FakeResult("PROP-002")]

    monkeypatch.setattr(sp_mod.async_index, "query", fake_query)

    result = asyncio.run(sp_mod.asearch_properties.ainvoke({"query": "warehouse Shah Alam"}))

    assert result["total_found"] == 2
    assert "PROP-001" in result["property_listing_id"]
    assert "PROP-002" in result["property_listing_id"]


def test_search_deduplicates_results(monkeypatch):
    monkeypatch.setattr(
        "agent.v4.tools.search_properties.get_stream_writer",
        lambda: lambda d: None,
    )

    async def fake_query(**kwargs):
        return [_FakeResult("PROP-001"), _FakeResult("PROP-001")]  # duplicate

    monkeypatch.setattr(sp_mod.async_index, "query", fake_query)

    result = asyncio.run(sp_mod.asearch_properties.ainvoke({"query": "warehouse"}))
    assert result["total_found"] == 1


def test_search_emits_tool_start_and_complete(monkeypatch):
    events = []
    monkeypatch.setattr(
        "agent.v4.tools.search_properties.get_stream_writer",
        lambda: lambda d: events.append(d),
    )

    async def fake_query(**kwargs):
        return []

    monkeypatch.setattr(sp_mod.async_index, "query", fake_query)

    asyncio.run(sp_mod.asearch_properties.ainvoke({"query": "factory"}))

    event_types = [e["event"] for e in events]
    assert "tool_start" in event_types
    assert "tool_complete" in event_types


def test_search_filter_includes_offer_type(monkeypatch):
    captured = {}
    monkeypatch.setattr(
        "agent.v4.tools.search_properties.get_stream_writer",
        lambda: lambda d: None,
    )

    async def fake_query(**kwargs):
        captured["filter"] = kwargs.get("filter", "")
        return []

    monkeypatch.setattr(sp_mod.async_index, "query", fake_query)

    asyncio.run(sp_mod.asearch_properties.ainvoke({"query": "warehouse", "offer_type": "sale"}))
    assert 'offer_type = "sale"' in captured["filter"]


def test_search_tool_complete_includes_ids(monkeypatch):
    events = []
    monkeypatch.setattr(
        "agent.v4.tools.search_properties.get_stream_writer",
        lambda: lambda d: events.append(d),
    )

    async def fake_query(**kwargs):
        return [_FakeResult("PROP-AAA")]

    monkeypatch.setattr(sp_mod.async_index, "query", fake_query)

    asyncio.run(sp_mod.asearch_properties.ainvoke({"query": "warehouse"}))

    complete = next(e for e in events if e["event"] == "tool_complete")
    assert "PROP-AAA" in complete["ids"]


def test_search_filter_always_includes_active_status(monkeypatch):
    captured = {}
    monkeypatch.setattr(
        "agent.v4.tools.search_properties.get_stream_writer",
        lambda: lambda d: None,
    )

    async def fake_query(**kwargs):
        captured["filter"] = kwargs.get("filter", "")
        return []

    monkeypatch.setattr(sp_mod.async_index, "query", fake_query)

    # No filters passed — only listing_status should be present
    asyncio.run(sp_mod.asearch_properties.ainvoke({"query": "warehouse"}))
    assert 'listing_status = "active"' in captured["filter"]


def test_search_property_category_uses_contains_for_sub_categories(monkeypatch):
    captured = {}
    monkeypatch.setattr(
        "agent.v4.tools.search_properties.get_stream_writer",
        lambda: lambda d: None,
    )

    async def fake_query(**kwargs):
        captured["filter"] = kwargs.get("filter", "")
        return []

    monkeypatch.setattr(sp_mod.async_index, "query", fake_query)

    asyncio.run(sp_mod.asearch_properties.ainvoke(
        {"query": "warehouse", "property_category": ["warehouse"]}
    ))
    assert "CONTAINS" in captured["filter"]
    assert 'sub_categories CONTAINS "warehouse"' in captured["filter"]
