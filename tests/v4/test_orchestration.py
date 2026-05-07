# tests/v4/test_orchestration.py
import sys
from pathlib import Path
from unittest.mock import MagicMock

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def test_create_agent_calls_create_deep_agent_with_correct_args(monkeypatch):
    mock_agent = MagicMock()
    captured = {}

    def fake_create_deep_agent(**kwargs):
        captured.update(kwargs)
        return mock_agent

    monkeypatch.setattr("agent.v4.orchestration.create_deep_agent", fake_create_deep_agent)
    monkeypatch.setattr("agent.v4.orchestration.load_llm", lambda model: MagicMock())

    from agent.v4.orchestration import create_agent
    fake_checkpointer = MagicMock()
    result = create_agent(fake_checkpointer)

    assert result is mock_agent
    assert "model" in captured
    assert "tools" in captured
    assert len(captured["tools"]) == 4
    assert "system_prompt" in captured
    assert "response_format" in captured
    assert captured["checkpointer"] is fake_checkpointer


def test_create_agent_passes_default_model_to_load_llm(monkeypatch):
    captured_model = {}

    def fake_load_llm(model):
        captured_model["value"] = model
        return MagicMock()

    monkeypatch.setattr("agent.v4.orchestration.load_llm", fake_load_llm)
    monkeypatch.setattr("agent.v4.orchestration.create_deep_agent", lambda **kw: MagicMock())

    from agent.v4.orchestration import create_agent
    from agent.v4.config import DEFAULT_MODEL

    create_agent(MagicMock())
    assert captured_model["value"] == DEFAULT_MODEL
