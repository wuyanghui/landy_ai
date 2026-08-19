import sys
from pathlib import Path
from unittest.mock import MagicMock

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def test_create_agent_returns_agent(monkeypatch):
    mock_agent = MagicMock()
    monkeypatch.setattr("agent.v6.orchestration.create_deep_agent", lambda **kw: mock_agent)
    monkeypatch.setattr("agent.v6.orchestration.load_llm", lambda model, **kw: MagicMock())

    from agent.v6.orchestration import create_agent
    result = create_agent(MagicMock())

    assert result is mock_agent


def test_create_agent_passes_two_tools(monkeypatch):
    captured = {}
    monkeypatch.setattr(
        "agent.v6.orchestration.create_deep_agent",
        lambda **kw: captured.update(kw) or MagicMock(),
    )
    monkeypatch.setattr("agent.v6.orchestration.load_llm", lambda model, **kw: MagicMock())

    from agent.v6.orchestration import create_agent
    create_agent(MagicMock())

    assert len(captured["tools"]) == 2


def test_create_agent_uses_default_model(monkeypatch):
    captured = {}

    def fake_load_llm(model, **kwargs):
        captured["model"] = model
        return MagicMock()

    monkeypatch.setattr("agent.v6.orchestration.create_deep_agent", lambda **kw: MagicMock())
    monkeypatch.setattr("agent.v6.orchestration.load_llm", fake_load_llm)

    from agent.v6.orchestration import create_agent
    from agent.v6.config import DEFAULT_MODEL
    create_agent(MagicMock())

    assert captured["model"] == DEFAULT_MODEL


def test_create_agent_passes_checkpointer(monkeypatch):
    captured = {}
    monkeypatch.setattr(
        "agent.v6.orchestration.create_deep_agent",
        lambda **kw: captured.update(kw) or MagicMock(),
    )
    monkeypatch.setattr("agent.v6.orchestration.load_llm", lambda model, **kw: MagicMock())

    from agent.v6.orchestration import create_agent
    fake_cp = MagicMock()
    create_agent(fake_cp)

    assert captured["checkpointer"] is fake_cp


def test_create_agent_passes_system_prompt(monkeypatch):
    captured = {}
    monkeypatch.setattr(
        "agent.v6.orchestration.create_deep_agent",
        lambda **kw: captured.update(kw) or MagicMock(),
    )
    monkeypatch.setattr("agent.v6.orchestration.load_llm", lambda model, **kw: MagicMock())

    from agent.v6.orchestration import create_agent
    from agent.v6.prompt.agent_prompt import AGENT_PROMPT
    create_agent(MagicMock())

    assert captured["system_prompt"] == AGENT_PROMPT
