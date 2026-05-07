import sys, asyncio
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import agent.v4.tools.search_properties as sp_mod


def _fake_doc(pid):
    return {
        "property_id": pid,
        "title": f"Property {pid}",
        "slug": f"prop-{pid}",
        "offer_type": "sale",
        "price": 1_000_000,
        "price_currency": "MYR",
        "locality": "Shah Alam",
        "region": "Selangor",
        "full_address": "Jalan Test",
        "main_category": "warehouse",
        "sub_categories": [],
        "tenure": "freehold",
        "built_up_sqft": 3000,
        "land_sqft": 5000,
        "ceiling_height": 6.0,
        "floor_loading": 500,
        "listed_date": None,
    }


class _FakeVecResult:
    def __init__(self, pid, score=0.9):
        self.score = score
        self.metadata = {"property_id": pid}


def _patch_base(monkeypatch, mongo_ids=None):
    if mongo_ids is None:
        mongo_ids = []
    docs_map = {pid: _fake_doc(pid) for pid in mongo_ids}

    monkeypatch.setattr(sp_mod, "_run_mongodb_query", lambda *args: mongo_ids)
    monkeypatch.setattr(sp_mod, "_fetch_by_ids", lambda ids: [docs_map[p] for p in ids if p in docs_map])
    monkeypatch.setattr(
        "agent.v4.tools.search_properties.get_stream_writer",
        lambda: lambda d: None,
    )


# ── basic return shape ────────────────────────────────────────────────────────

def test_search_returns_property_ids(monkeypatch):
    _patch_base(monkeypatch, mongo_ids=["PROP-001", "PROP-002"])
    result = asyncio.run(sp_mod.asearch_properties.ainvoke({"query": ""}))
    assert result["total_found"] == 2
    assert "PROP-001" in result["property_listing_id"]
    assert "PROP-002" in result["property_listing_id"]


def test_search_returns_zero_when_no_mongo_results(monkeypatch):
    upstash_calls = []

    async def fake_upstash(**kwargs):
        upstash_calls.append(True)
        return []

    _patch_base(monkeypatch, mongo_ids=[])
    monkeypatch.setattr(sp_mod.async_index, "query", fake_upstash)

    result = asyncio.run(sp_mod.asearch_properties.ainvoke({"query": "warehouse"}))
    assert result["total_found"] == 0
    assert upstash_calls == []  # Upstash not called when no candidates


# ── SSE events ────────────────────────────────────────────────────────────────

def test_search_emits_tool_start_and_complete(monkeypatch):
    events = []
    _patch_base(monkeypatch, mongo_ids=[])
    monkeypatch.setattr(
        "agent.v4.tools.search_properties.get_stream_writer",
        lambda: lambda d: events.append(d),
    )
    asyncio.run(sp_mod.asearch_properties.ainvoke({"query": "factory"}))
    event_types = [e["event"] for e in events]
    assert "tool_start" in event_types
    assert "tool_complete" in event_types


def test_search_tool_complete_includes_ids(monkeypatch):
    events = []
    _patch_base(monkeypatch, mongo_ids=["PROP-AAA"])
    monkeypatch.setattr(
        "agent.v4.tools.search_properties.get_stream_writer",
        lambda: lambda d: events.append(d),
    )
    asyncio.run(sp_mod.asearch_properties.ainvoke({"query": ""}))
    complete = next(e for e in events if e["event"] == "tool_complete")
    assert "PROP-AAA" in complete["ids"]


# ── MongoDB filter params ─────────────────────────────────────────────────────

def test_search_mongo_receives_offer_type(monkeypatch):
    captured = {}

    def fake_mongo(offer_type, *args):
        captured["offer_type"] = offer_type
        return []

    monkeypatch.setattr(sp_mod, "_run_mongodb_query", fake_mongo)
    monkeypatch.setattr(sp_mod, "_fetch_by_ids", lambda ids: [])
    monkeypatch.setattr("agent.v4.tools.search_properties.get_stream_writer", lambda: lambda d: None)

    asyncio.run(sp_mod.asearch_properties.ainvoke({"query": "", "offer_type": "sale"}))
    assert captured["offer_type"] == "sale"


def test_search_mongo_receives_locality_as_free_text(monkeypatch):
    captured = {}

    def fake_mongo(offer_type, tenure, property_category, locality, *args):
        captured["locality"] = locality
        return []

    monkeypatch.setattr(sp_mod, "_run_mongodb_query", fake_mongo)
    monkeypatch.setattr(sp_mod, "_fetch_by_ids", lambda ids: [])
    monkeypatch.setattr("agent.v4.tools.search_properties.get_stream_writer", lambda: lambda d: None)

    asyncio.run(sp_mod.asearch_properties.ainvoke({"query": "", "locality": "Chan Sow Lin"}))
    assert captured["locality"] == "Chan Sow Lin"


def test_search_mongo_receives_category(monkeypatch):
    captured = {}

    def fake_mongo(offer_type, tenure, property_category, *args):
        captured["property_category"] = property_category
        return []

    monkeypatch.setattr(sp_mod, "_run_mongodb_query", fake_mongo)
    monkeypatch.setattr(sp_mod, "_fetch_by_ids", lambda ids: [])
    monkeypatch.setattr("agent.v4.tools.search_properties.get_stream_writer", lambda: lambda d: None)

    asyncio.run(sp_mod.asearch_properties.ainvoke(
        {"query": "", "property_category": ["warehouse"]}
    ))
    assert captured["property_category"] == ["warehouse"]


# ── MongoDB query builder unit tests ─────────────────────────────────────────

class _FakeCollection:
    """Minimal MongoDB collection stub — find() returns a cursor with .limit()."""

    def __init__(self):
        self.calls = []

    def find(self, q, *a, **kw):
        self.calls.append(q)

        class _Cursor:
            def limit(self_, n):
                return iter([])

        return _Cursor()


def test_mongo_query_includes_active_status(monkeypatch):
    col = _FakeCollection()
    monkeypatch.setattr(sp_mod, "get_property_listing_collections", lambda: col)

    sp_mod._run_mongodb_query(None, None, None, None, None,
                              None, None, None, None, None, None, None, None)
    assert col.calls[0].get("listing_status") == "active"


def test_mongo_query_offer_type_filter(monkeypatch):
    col = _FakeCollection()
    monkeypatch.setattr(sp_mod, "get_property_listing_collections", lambda: col)

    sp_mod._run_mongodb_query("sale", None, None, None, None,
                              None, None, None, None, None, None, None, None)
    assert col.calls[0]["offer.offer_type"] == "sale"


def test_mongo_query_locality_uses_regex(monkeypatch):
    col = _FakeCollection()
    monkeypatch.setattr(sp_mod, "get_property_listing_collections", lambda: col)

    sp_mod._run_mongodb_query(None, None, None, "Klang", None,
                              None, None, None, None, None, None, None, None)
    q = col.calls[0]
    or_clause = q.get("$or", [])
    assert any("$regex" in str(c) for c in or_clause)
    fields_searched = [list(c.keys())[0] for c in or_clause]
    assert "location.address.address_region" in fields_searched


def test_mongo_query_category_and_locality_use_and(monkeypatch):
    col = _FakeCollection()
    monkeypatch.setattr(sp_mod, "get_property_listing_collections", lambda: col)

    sp_mod._run_mongodb_query(None, None, ["warehouse"], "Shah Alam", None,
                              None, None, None, None, None, None, None, None)
    q = col.calls[0]
    assert "$and" in q
    assert "$or" not in q  # both clauses wrapped in $and; no top-level $or


# ── Upstash stage-2 behaviour ─────────────────────────────────────────────────

def test_search_skips_upstash_when_query_empty(monkeypatch):
    upstash_calls = []

    async def fake_upstash(**kwargs):
        upstash_calls.append(True)
        return []

    _patch_base(monkeypatch, mongo_ids=["PROP-001"])
    monkeypatch.setattr(sp_mod.async_index, "query", fake_upstash)

    asyncio.run(sp_mod.asearch_properties.ainvoke({"query": ""}))
    assert upstash_calls == []


def test_search_calls_upstash_when_query_nonempty(monkeypatch):
    upstash_calls = []

    async def fake_upstash(**kwargs):
        upstash_calls.append(kwargs)
        return [_FakeVecResult("PROP-001")]

    _patch_base(monkeypatch, mongo_ids=["PROP-001"])
    monkeypatch.setattr(sp_mod.async_index, "query", fake_upstash)

    asyncio.run(sp_mod.asearch_properties.ainvoke({"query": "solar panel ready"}))
    assert len(upstash_calls) == 1
    assert upstash_calls[0]["data"] == "solar panel ready"


def test_search_upstash_filter_contains_candidate_ids(monkeypatch):
    captured = {}

    async def fake_upstash(**kwargs):
        captured["filter"] = kwargs.get("filter", "")
        return [_FakeVecResult("PROP-001")]

    _patch_base(monkeypatch, mongo_ids=["PROP-001", "PROP-002"])
    monkeypatch.setattr(sp_mod.async_index, "query", fake_upstash)

    asyncio.run(sp_mod.asearch_properties.ainvoke({"query": "high ceiling"}))
    assert "PROP-001" in captured["filter"]
    assert "PROP-002" in captured["filter"]
    assert "property_id IN" in captured["filter"]


def test_search_falls_back_to_mongo_when_upstash_empty(monkeypatch):
    async def fake_upstash(**kwargs):
        return []

    _patch_base(monkeypatch, mongo_ids=["PROP-001", "PROP-002"])
    monkeypatch.setattr(sp_mod.async_index, "query", fake_upstash)

    result = asyncio.run(sp_mod.asearch_properties.ainvoke({"query": "solar panel"}))
    assert result["total_found"] == 2


def test_search_falls_back_to_mongo_on_upstash_error(monkeypatch):
    async def fake_upstash(**kwargs):
        raise RuntimeError("Upstash unavailable")

    _patch_base(monkeypatch, mongo_ids=["PROP-001"])
    monkeypatch.setattr(sp_mod.async_index, "query", fake_upstash)

    result = asyncio.run(sp_mod.asearch_properties.ainvoke({"query": "solar panel"}))
    assert result["total_found"] == 1
