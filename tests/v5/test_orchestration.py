import sys
from pathlib import Path
from unittest.mock import MagicMock

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def test_create_agent_returns_agent(monkeypatch):
    mock_agent = MagicMock()
    captured = {}

    def fake_create_deep_agent(**kwargs):
        captured.update(kwargs)
        return mock_agent

    monkeypatch.setattr("agent.v5.orchestration.create_deep_agent", fake_create_deep_agent)
    monkeypatch.setattr("agent.v5.orchestration.load_llm", lambda model: MagicMock())

    from agent.v5.orchestration import create_agent
    result = create_agent(MagicMock())
    assert result is mock_agent


def test_create_agent_passes_two_tools(monkeypatch):
    captured = {}
    monkeypatch.setattr(
        "agent.v5.orchestration.create_deep_agent",
        lambda **kw: captured.update(kw) or MagicMock(),
    )
    monkeypatch.setattr("agent.v5.orchestration.load_llm", lambda model: MagicMock())

    from agent.v5.orchestration import create_agent
    create_agent(MagicMock())
    assert len(captured["tools"]) == 2


def test_create_agent_uses_default_model(monkeypatch):
    captured_model = {}

    def fake_load_llm(model):
        captured_model["value"] = model
        return MagicMock()

    monkeypatch.setattr("agent.v5.orchestration.create_deep_agent", lambda **kw: MagicMock())
    monkeypatch.setattr("agent.v5.orchestration.load_llm", fake_load_llm)

    from agent.v5.orchestration import create_agent
    from agent.v5.config import DEFAULT_MODEL
    create_agent(MagicMock())
    assert captured_model["value"] == DEFAULT_MODEL


def test_create_agent_passes_checkpointer(monkeypatch):
    captured = {}
    monkeypatch.setattr(
        "agent.v5.orchestration.create_deep_agent",
        lambda **kw: captured.update(kw) or MagicMock(),
    )
    monkeypatch.setattr("agent.v5.orchestration.load_llm", lambda model: MagicMock())

    from agent.v5.orchestration import create_agent
    fake_cp = MagicMock()
    create_agent(fake_cp)
    assert captured["checkpointer"] is fake_cp
