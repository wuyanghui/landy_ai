import sys
from pathlib import Path
from unittest.mock import MagicMock, AsyncMock, patch

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from fastapi.testclient import TestClient
from langchain_core.messages import AIMessage, HumanMessage

from agent.v5.state import V5State


# from_conn_string is called synchronously and returns an async context manager
def _fake_postgres(*a, **kw):
    cp = AsyncMock()
    cp.__aenter__ = AsyncMock(return_value=cp)
    cp.__aexit__ = AsyncMock(return_value=None)
    cp.setup = AsyncMock()
    return cp


def _fake_state(**overrides):
    base = {"follow_up_chips": ["Factory in Shah Alam"], "live_agent_cta": False, "live_agent_trigger": None}
    base.update(overrides)
    return V5State(**base)


def test_v5_invoke_returns_200_with_answer():
    from src.index import app

    agent = MagicMock()
    agent.ainvoke = AsyncMock(return_value={
        "messages": [
            HumanMessage(content="factory in Shah Alam"),
            AIMessage(content="Here are the top factories in Shah Alam."),
        ]
    })

    with patch("src.index.AsyncPostgresSaver.from_conn_string", side_effect=_fake_postgres):
        with patch("agent.v5.orchestration.create_agent", return_value=agent):
            with patch("agent.v5.orchestration.extract_v5_state", new=AsyncMock(return_value=_fake_state())):
                client = TestClient(app)
                resp = client.post("/api/v5/invoke", json={"message": "factory in Shah Alam"})

    assert resp.status_code == 200
    data = resp.json()
    assert "thread_id" in data
    assert data["answer"] == "Here are the top factories in Shah Alam."
    assert data["follow_up_chips"] == ["Factory in Shah Alam"]
    assert data["live_agent_cta"] is False


def test_v5_invoke_rejects_empty_message():
    from src.index import app
    client = TestClient(app)
    resp = client.post("/api/v5/invoke", json={"message": ""})
    assert resp.status_code == 400


# ── /api/v5/stream ────────────────────────────────────────────────────────────

def _parse_sse(text: str):
    import json as _json
    events = []
    for frame in text.split("\n\n"):
        for line in frame.split("\n"):
            if line.startswith("data: "):
                events.append(_json.loads(line[6:]))
    return events


def _stream_response(astream_gen, extracted):
    from src.index import app

    agent = MagicMock()
    agent.astream = astream_gen

    with patch("src.index.AsyncPostgresSaver.from_conn_string", side_effect=_fake_postgres):
        with patch("agent.v5.orchestration.create_agent", return_value=agent):
            with patch("agent.v5.orchestration.extract_v5_state", new=AsyncMock(return_value=extracted)):
                client = TestClient(app)
                return client.post("/api/v5/stream", json={"message": "factory", "thread_id": "t-123"})


def test_v5_stream_emits_thread_id_first():
    async def fake_astream(*a, **kw):
        yield {"type": "custom", "ns": (), "data": {"event": "search_complete", "total_found": 3}}

    resp = _stream_response(fake_astream, _fake_state())

    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/event-stream")
    events = _parse_sse(resp.text)
    assert events[0]["data"] == {"event": "thread_id", "thread_id": "t-123"}
    assert any(e["data"].get("event") == "search_complete" for e in events)


def test_v5_stream_streams_ai_tokens_and_filters_tool_chunks():
    from langchain_core.messages import AIMessageChunk, ToolMessage

    async def fake_astream(*a, **kw):
        yield {"type": "messages", "ns": (), "data": (AIMessageChunk(content="Hello "), {})}
        yield {"type": "messages", "ns": (), "data": (ToolMessage(content='{"raw": "json"}', tool_call_id="t"), {})}
        yield {"type": "messages", "ns": (), "data": (AIMessageChunk(content="world"), {})}

    resp = _stream_response(fake_astream, _fake_state())

    events = _parse_sse(resp.text)
    tokens = [e["data"]["content"] for e in events if e["type"] == "messages"]
    assert tokens == ["Hello ", "world"]  # tool chunk filtered out


def test_v5_stream_normalizes_tuple_events_and_drops_updates():
    """Production langgraph yields (namespace, mode, payload) tuples; some versions
    yield (mode, namespace, payload). Both must normalize; updates frames are dropped."""
    from langchain_core.messages import AIMessageChunk

    async def fake_astream(*a, **kw):
        yield ((), "custom", {"event": "search_complete", "total_found": 1})
        yield ((), "messages", (AIMessageChunk(content="Hi"), {}))
        yield ("messages", (), (AIMessageChunk(content=" there"), {}))
        yield ((), "updates", {"model": {"messages": []}})

    resp = _stream_response(fake_astream, _fake_state())
    events = _parse_sse(resp.text)

    assert all(e["type"] != "updates" for e in events)
    tokens = [e["data"]["content"] for e in events if e["type"] == "messages"]
    assert tokens == ["Hi", " there"]
    assert any(
        isinstance(e.get("data"), dict) and e["data"].get("event") == "search_complete"
        for e in events
    )


def test_reasoning_patch_preserves_reasoning_delta():
    from agent.v5.reasoning_patch import apply_reasoning_patch
    from langchain_openai.chat_models import base as oai_base
    from langchain_core.messages import AIMessageChunk

    apply_reasoning_patch()
    chunk = oai_base._convert_delta_to_message_chunk(
        {"role": "assistant", "content": "", "reasoning": "User wants a warehouse..."},
        AIMessageChunk,
    )
    assert chunk.additional_kwargs["reasoning"] == "User wants a warehouse..."
    # idempotent — applying again must not double-wrap
    apply_reasoning_patch()
    assert getattr(oai_base._convert_delta_to_message_chunk, "_v5_reasoning_patch", False)


def test_v5_stream_emits_reasoning_frames_separately():
    from langchain_core.messages import AIMessageChunk

    async def fake_astream(*a, **kw):
        yield {"type": "messages", "ns": (), "data": (
            AIMessageChunk(content="", additional_kwargs={"reasoning": "thinking about Klang..."}), {})}
        yield {"type": "messages", "ns": (), "data": (AIMessageChunk(content="Here are"), {})}

    resp = _stream_response(fake_astream, _fake_state())
    events = _parse_sse(resp.text)

    reasoning = [e["data"]["content"] for e in events if e["type"] == "reasoning"]
    tokens = [e["data"]["content"] for e in events if e["type"] == "messages"]
    assert reasoning == ["thinking about Klang..."]
    assert tokens == ["Here are"]  # reasoning never leaks into answer tokens


def test_v5_stream_logs_conversation_turn():
    from langchain_core.messages import AIMessageChunk

    async def fake_astream(*a, **kw):
        yield {"type": "custom", "ns": (), "data": {"event": "search_start", "filters": {"region": "Selangor"}}}
        yield {"type": "messages", "ns": (), "data": (AIMessageChunk(content="Here are 3."), {})}
        yield {"type": "custom", "ns": (), "data": {"event": "search_complete", "total_found": 3}}

    agent = MagicMock()
    agent.astream = fake_astream
    captured = {}

    def fake_log(**kw):
        captured.update(kw)

    with patch("src.index.AsyncPostgresSaver.from_conn_string", side_effect=_fake_postgres):
        with patch("agent.v5.orchestration.create_agent", return_value=agent):
            with patch("agent.v5.orchestration.extract_v5_state",
                       new=AsyncMock(return_value=_fake_state(live_agent_cta=True, live_agent_trigger="investment"))):
                with patch("utility.conversation_log.log_turn", side_effect=fake_log):
                    from src.index import app
                    client = TestClient(app)
                    resp = client.post(
                        "/api/v5/stream",
                        json={"message": "warehouse in Selangor", "thread_id": "t-1", "session_id": "sess-9"},
                    )

    assert resp.status_code == 200
    assert captured["session_id"] == "sess-9"
    assert captured["thread_id"] == "t-1"
    assert captured["user_message"] == "warehouse in Selangor"
    assert captured["filters"] == {"region": "Selangor"}
    assert captured["result_count"] == 3
    assert captured["answer"] == "Here are 3."
    assert captured["cta_fired"] is True
    assert captured["cta_trigger"] == "investment"


def test_v5_stream_emits_extracted_chips_and_cta():
    async def fake_astream(*a, **kw):
        yield {"type": "messages", "ns": (), "data": ()}

    resp = _stream_response(
        fake_astream,
        _fake_state(live_agent_cta=True, live_agent_trigger="transact_intent"),
    )

    events = _parse_sse(resp.text)
    names = [e["data"].get("event") for e in events if isinstance(e.get("data"), dict)]
    assert "follow_up_chips" in names
    assert "live_agent_cta" in names


def test_v5_stream_rejects_empty_message():
    from src.index import app
    client = TestClient(app)
    resp = client.post("/api/v5/stream", json={"message": ""})
    assert resp.status_code == 400


# ── shared-secret gate ────────────────────────────────────────────────────────

def test_secret_gate_blocks_without_header(monkeypatch):
    import src.index as idx
    monkeypatch.setattr(idx, "_API_SECRET", "topsecret")
    client = TestClient(idx.app)
    resp = client.post("/api/v5/invoke", json={"message": "factory"})
    assert resp.status_code == 401


def test_secret_gate_allows_with_correct_header(monkeypatch):
    import src.index as idx
    monkeypatch.setattr(idx, "_API_SECRET", "topsecret")

    agent = MagicMock()
    agent.ainvoke = AsyncMock(return_value={
        "messages": [AIMessage(content="Here you go.")]
    })

    with patch("src.index.AsyncPostgresSaver.from_conn_string", side_effect=_fake_postgres):
        with patch("agent.v5.orchestration.create_agent", return_value=agent):
            with patch("agent.v5.orchestration.extract_v5_state", new=AsyncMock(return_value=_fake_state())):
                client = TestClient(idx.app)
                resp = client.post(
                    "/api/v5/invoke",
                    json={"message": "factory"},
                    headers={"x-landy-key": "topsecret"},
                )
    assert resp.status_code == 200


def test_secret_gate_exempts_health(monkeypatch):
    import src.index as idx
    monkeypatch.setattr(idx, "_API_SECRET", "topsecret")
    client = TestClient(idx.app)
    assert client.get("/health").status_code == 200


def test_secret_gate_disabled_when_unset(monkeypatch):
    import src.index as idx
    monkeypatch.setattr(idx, "_API_SECRET", None)
    client = TestClient(idx.app)
    # empty message still 400 (validation), not 401 — gate is off
    resp = client.post("/api/v5/invoke", json={"message": ""})
    assert resp.status_code == 400
