import sys
from pathlib import Path
from unittest.mock import MagicMock, AsyncMock, patch

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from fastapi.testclient import TestClient


def _mock_agent(structured: dict):
    agent = MagicMock()
    agent.ainvoke = AsyncMock(return_value={
        "structured_response": MagicMock(**structured)
    })
    return agent


def test_v5_invoke_returns_200(monkeypatch):
    from src.index import app

    # from_conn_string is called synchronously and returns an async context manager
    def fake_postgres(*a, **kw):
        cp = AsyncMock()
        cp.__aenter__ = AsyncMock(return_value=cp)
        cp.__aexit__ = AsyncMock(return_value=None)
        cp.setup = AsyncMock()
        return cp

    with patch("src.index.AsyncPostgresSaver.from_conn_string", side_effect=fake_postgres):
        with patch("agent.v5.orchestration.create_agent") as mock_create:
            mock_create.return_value = _mock_agent({
                "follow_up_chips": ["Factory in Shah Alam"],
                "live_agent_cta": False,
                "live_agent_trigger": None,
            })
            client = TestClient(app)
            resp = client.post("/api/v5/invoke", json={"message": "factory in Shah Alam"})
    assert resp.status_code == 200
    data = resp.json()
    assert "thread_id" in data
    assert "follow_up_chips" in data


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


def test_v5_stream_emits_thread_id_first(monkeypatch):
    from src.index import app

    def fake_postgres(*a, **kw):
        cp = AsyncMock()
        cp.__aenter__ = AsyncMock(return_value=cp)
        cp.__aexit__ = AsyncMock(return_value=None)
        cp.setup = AsyncMock()
        return cp

    async def fake_astream(*a, **kw):
        yield {"type": "custom", "ns": (), "data": {"event": "search_complete", "total_found": 3}}

    agent = MagicMock()
    agent.astream = fake_astream

    with patch("src.index.AsyncPostgresSaver.from_conn_string", side_effect=fake_postgres):
        with patch("agent.v5.orchestration.create_agent", return_value=agent):
            client = TestClient(app)
            resp = client.post("/api/v5/stream", json={"message": "factory", "thread_id": "t-123"})

    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/event-stream")
    events = _parse_sse(resp.text)
    assert events[0]["data"] == {"event": "thread_id", "thread_id": "t-123"}
    assert any(e["data"].get("event") == "search_complete" for e in events)


def test_v5_stream_rejects_empty_message():
    from src.index import app
    client = TestClient(app)
    resp = client.post("/api/v5/stream", json={"message": ""})
    assert resp.status_code == 400
