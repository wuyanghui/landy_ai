import sys
from pathlib import Path
from unittest.mock import MagicMock, AsyncMock, patch

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from fastapi.testclient import TestClient
from langchain_core.messages import AIMessage, HumanMessage


# from_conn_string is called synchronously and returns an async context manager
def _fake_postgres(*a, **kw):
    cp = AsyncMock()
    cp.__aenter__ = AsyncMock(return_value=cp)
    cp.__aexit__ = AsyncMock(return_value=None)
    cp.setup = AsyncMock()
    return cp


def _parse_sse(text: str):
    import json as _json
    events = []
    for frame in text.split("\n\n"):
        for line in frame.split("\n"):
            if line.startswith("data: "):
                events.append(_json.loads(line[6:]))
    return events


# ── /api/v6/invoke ──────────────────────────────────────────────────────────

def test_v6_invoke_route_is_registered():
    from src.index import app
    routes = [r.path for r in app.routes]
    assert "/api/v6/invoke" in routes


def test_v6_stream_route_is_registered():
    from src.index import app
    routes = [r.path for r in app.routes]
    assert "/api/v6/stream" in routes


def test_v6_invoke_rejects_empty_message():
    from src.index import app
    client = TestClient(app)
    resp = client.post("/api/v6/invoke", json={"message": ""})
    assert resp.status_code == 400


def test_v6_invoke_rejects_missing_message():
    from src.index import app
    client = TestClient(app)
    resp = client.post("/api/v6/invoke", json={})
    assert resp.status_code == 422


def test_v6_invoke_returns_200_with_answer():
    from src.index import app

    agent = MagicMock()
    agent.ainvoke = AsyncMock(return_value={
        "messages": [
            HumanMessage(content="What is the buffer zone for medium industry?"),
            AIMessage(content="The buffer zone for medium industry is 150m."),
        ]
    })

    captured = {}

    def fake_log(**kw):
        captured.update(kw)

    with patch("src.index.AsyncPostgresSaver.from_conn_string", side_effect=_fake_postgres):
        with patch("agent.v6.orchestration.create_agent", return_value=agent):
            with patch("utility.conversation_log.log_turn", side_effect=fake_log):
                client = TestClient(app)
                resp = client.post(
                    "/api/v6/invoke",
                    json={"message": "What is the buffer zone for medium industry?", "session_id": "sess-6"},
                )

    assert resp.status_code == 200
    data = resp.json()
    assert "thread_id" in data
    assert data["answer"] == "The buffer zone for medium industry is 150m."
    assert data["status"] == "success"

    # conversation log dual-write happened with the v6 agent_version tag
    assert captured["agent_version"] == "v6"
    assert captured["session_id"] == "sess-6"
    assert captured["answer"] == "The buffer zone for medium industry is 150m."


def test_v6_invoke_preserves_thread_id_across_turns():
    from src.index import app

    agent = MagicMock()
    agent.ainvoke = AsyncMock(return_value={
        "messages": [AIMessage(content="Light industry buffer is 50m.")]
    })

    with patch("src.index.AsyncPostgresSaver.from_conn_string", side_effect=_fake_postgres):
        with patch("agent.v6.orchestration.create_agent", return_value=agent):
            with patch("utility.conversation_log.log_turn"):
                client = TestClient(app)
                resp = client.post(
                    "/api/v6/invoke",
                    json={"message": "What about light industry?", "thread_id": "t-existing"},
                )

    assert resp.status_code == 200
    assert resp.json()["thread_id"] == "t-existing"


# ── /api/v6/stream ──────────────────────────────────────────────────────────

def _stream_response(astream_gen, payload=None):
    from src.index import app

    agent = MagicMock()
    agent.astream = astream_gen

    with patch("src.index.AsyncPostgresSaver.from_conn_string", side_effect=_fake_postgres):
        with patch("agent.v6.orchestration.create_agent", return_value=agent):
            with patch("utility.conversation_log.log_turn"):
                client = TestClient(app)
                return client.post(
                    "/api/v6/stream",
                    json=payload or {"message": "buffer zone question", "thread_id": "t-123"},
                )


def test_v6_stream_rejects_empty_message():
    from src.index import app
    client = TestClient(app)
    resp = client.post("/api/v6/stream", json={"message": ""})
    assert resp.status_code == 400


def test_v6_stream_emits_thread_id_first():
    async def fake_astream(*a, **kw):
        yield {"type": "custom", "ns": (), "data": {"event": "kb_lookup", "page": "planning-guidelines"}}

    resp = _stream_response(fake_astream)

    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/event-stream")
    events = _parse_sse(resp.text)
    assert events[0]["data"] == {"event": "thread_id", "thread_id": "t-123"}
    assert any(e["data"].get("event") == "kb_lookup" for e in events)


def test_v6_stream_streams_ai_tokens_and_filters_tool_chunks():
    from langchain_core.messages import AIMessageChunk, ToolMessage

    async def fake_astream(*a, **kw):
        yield {"type": "messages", "ns": (), "data": (AIMessageChunk(content="The buffer "), {})}
        yield {"type": "messages", "ns": (), "data": (ToolMessage(content='{"raw": "wiki"}', tool_call_id="t"), {})}
        yield {"type": "messages", "ns": (), "data": (AIMessageChunk(content="is 150m."), {})}

    resp = _stream_response(fake_astream)

    events = _parse_sse(resp.text)
    tokens = [e["data"]["content"] for e in events if e["type"] == "messages"]
    assert tokens == ["The buffer ", "is 150m."]  # tool chunk filtered out


def test_v6_stream_normalizes_tuple_events_and_drops_updates():
    """Same normalization contract as v5: (ns, type, data) or (type, ns, data)
    3-tuples must both work, and 'updates' frames must never reach the client."""
    from langchain_core.messages import AIMessageChunk

    async def fake_astream(*a, **kw):
        yield ((), "custom", {"event": "kb_lookup", "page": "act-446"})
        yield ((), "messages", (AIMessageChunk(content="Act "), {}))
        yield ("messages", (), (AIMessageChunk(content="446"), {}))
        yield ((), "updates", {"model": {"messages": []}})

    resp = _stream_response(fake_astream)
    events = _parse_sse(resp.text)

    assert all(e["type"] != "updates" for e in events)
    tokens = [e["data"]["content"] for e in events if e["type"] == "messages"]
    assert tokens == ["Act ", "446"]


def test_v6_stream_ends_without_error_event_on_success():
    async def fake_astream(*a, **kw):
        yield {"type": "messages", "ns": (), "data": (AIMessage(content="ok"), {})}

    resp = _stream_response(fake_astream)
    events = _parse_sse(resp.text)
    assert not any(e["data"].get("event") == "stream_error" for e in events if isinstance(e.get("data"), dict))


def test_v6_stream_emits_stream_error_event_on_exception():
    async def fake_astream(*a, **kw):
        raise RuntimeError("boom")
        yield  # pragma: no cover - unreachable, keeps this an async generator

    resp = _stream_response(fake_astream)
    events = _parse_sse(resp.text)
    error_events = [e for e in events if isinstance(e.get("data"), dict) and e["data"].get("event") == "stream_error"]
    assert len(error_events) == 1
    assert "boom" in error_events[0]["data"]["error"]


def test_v6_stream_logs_conversation_turn():
    async def fake_astream(*a, **kw):
        yield {"type": "messages", "ns": (), "data": (AIMessage(content="Here is the answer."), {})}

    captured = {}

    def fake_log(**kw):
        captured.update(kw)

    from src.index import app

    agent = MagicMock()
    agent.astream = fake_astream

    with patch("src.index.AsyncPostgresSaver.from_conn_string", side_effect=_fake_postgres):
        with patch("agent.v6.orchestration.create_agent", return_value=agent):
            with patch("utility.conversation_log.log_turn", side_effect=fake_log):
                client = TestClient(app)
                resp = client.post(
                    "/api/v6/stream",
                    json={"message": "worker dormitory rules", "thread_id": "t-1", "session_id": "sess-9"},
                )

    assert resp.status_code == 200
    assert captured["agent_version"] == "v6"
    assert captured["session_id"] == "sess-9"
    assert captured["thread_id"] == "t-1"
    assert captured["user_message"] == "worker dormitory rules"
    assert captured["answer"] == "Here is the answer."


# ── shared-secret gate (mirrors the v5 gate coverage) ───────────────────────

def test_v6_secret_gate_blocks_without_header(monkeypatch):
    import src.index as idx
    monkeypatch.setattr(idx, "_API_SECRET", "topsecret")
    client = TestClient(idx.app)
    resp = client.post("/api/v6/invoke", json={"message": "buffer zone"})
    assert resp.status_code == 401


def test_v6_secret_gate_allows_with_correct_header(monkeypatch):
    import src.index as idx
    monkeypatch.setattr(idx, "_API_SECRET", "topsecret")

    agent = MagicMock()
    agent.ainvoke = AsyncMock(return_value={"messages": [AIMessage(content="150m.")]})

    with patch("src.index.AsyncPostgresSaver.from_conn_string", side_effect=_fake_postgres):
        with patch("agent.v6.orchestration.create_agent", return_value=agent):
            with patch("utility.conversation_log.log_turn"):
                client = TestClient(idx.app)
                resp = client.post(
                    "/api/v6/invoke",
                    json={"message": "buffer zone"},
                    headers={"x-landy-key": "topsecret"},
                )
    assert resp.status_code == 200
