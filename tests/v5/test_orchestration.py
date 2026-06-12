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
    monkeypatch.setattr("agent.v5.orchestration.load_llm", lambda model, **kw: MagicMock())

    from agent.v5.orchestration import create_agent
    result = create_agent(MagicMock())
    assert result is mock_agent


def test_create_agent_passes_two_tools(monkeypatch):
    captured = {}
    monkeypatch.setattr(
        "agent.v5.orchestration.create_deep_agent",
        lambda **kw: captured.update(kw) or MagicMock(),
    )
    monkeypatch.setattr("agent.v5.orchestration.load_llm", lambda model, **kw: MagicMock())

    from agent.v5.orchestration import create_agent
    create_agent(MagicMock())
    assert len(captured["tools"]) == 2


def test_create_agent_uses_default_model_and_reasoning_effort(monkeypatch):
    captured = {}

    def fake_load_llm(model, **kwargs):
        captured["model"] = model
        captured.update(kwargs)
        return MagicMock()

    monkeypatch.setattr("agent.v5.orchestration.create_deep_agent", lambda **kw: MagicMock())
    monkeypatch.setattr("agent.v5.orchestration.load_llm", fake_load_llm)

    from agent.v5.orchestration import create_agent
    from agent.v5.config import DEFAULT_MODEL, REASONING_EFFORT
    create_agent(MagicMock())
    assert captured["model"] == DEFAULT_MODEL
    assert captured["reasoning_effort"] == REASONING_EFFORT


def test_extract_v5_state_uses_forced_structured_output(monkeypatch):
    import asyncio
    from unittest.mock import AsyncMock
    from agent.v5.state import V5State

    captured = {}
    structured_llm = MagicMock()
    structured_llm.ainvoke = AsyncMock(
        return_value=V5State(follow_up_chips=["a"], live_agent_cta=False, live_agent_trigger=None)
    )
    fake_llm = MagicMock()

    def fake_with_structured_output(schema, method=None):
        captured["schema"] = schema
        captured["method"] = method
        return structured_llm

    fake_llm.with_structured_output = fake_with_structured_output
    monkeypatch.setattr("agent.v5.orchestration.load_llm", lambda model, **kw: fake_llm)

    from agent.v5.orchestration import extract_v5_state
    result = asyncio.run(extract_v5_state("user msg", "answer text"))

    assert result.follow_up_chips == ["a"]
    assert captured["schema"] is V5State
    assert captured["method"] == "function_calling"


def test_create_agent_passes_checkpointer(monkeypatch):
    captured = {}
    monkeypatch.setattr(
        "agent.v5.orchestration.create_deep_agent",
        lambda **kw: captured.update(kw) or MagicMock(),
    )
    monkeypatch.setattr("agent.v5.orchestration.load_llm", lambda model, **kw: MagicMock())

    from agent.v5.orchestration import create_agent
    fake_cp = MagicMock()
    create_agent(fake_cp)
    assert captured["checkpointer"] is fake_cp
