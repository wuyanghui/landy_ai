# tests/v4/test_api_v4.py
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from fastapi.testclient import TestClient
from src.index import app


def test_v4_invoke_route_is_registered():
    routes = [r.path for r in app.routes]
    assert "/api/v4/invoke" in routes


def test_v4_invoke_rejects_missing_message():
    client = TestClient(app)
    resp = client.post("/api/v4/invoke", json={})
    assert resp.status_code == 422  # FastAPI validation error for missing required field


def test_v4_invoke_rejects_empty_message():
    client = TestClient(app)
    resp = client.post("/api/v4/invoke", json={"message": ""})
    assert resp.status_code == 400


def test_v4_stream_route_is_registered():
    routes = [r.path for r in app.routes]
    assert "/api/v4/stream" in routes


def test_v4_stream_rejects_empty_message():
    client = TestClient(app)
    resp = client.post("/api/v4/stream", json={"message": ""})
    assert resp.status_code == 400


def test_build_sse_line_formats_correctly():
    import json
    from src.index import _build_sse_line
    payload = {"type": "custom", "ns": [], "data": {"event": "tool_start"}}
    line = _build_sse_line(payload)
    assert line.startswith("data: ")
    assert line.endswith("\n\n")
    parsed = json.loads(line[len("data: "):-2])
    assert parsed["type"] == "custom"


def test_extract_property_ids_from_tool_complete():
    from src.index import _extract_property_ids
    event = {"type": "custom", "ns": [], "data": {"event": "tool_complete", "ids": ["A", "B"]}}
    assert _extract_property_ids(event) == ["A", "B"]


def test_extract_property_ids_returns_empty_for_non_complete():
    from src.index import _extract_property_ids
    event = {"type": "custom", "ns": [], "data": {"event": "tool_start"}}
    assert _extract_property_ids(event) == []
