import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from agent.v5.state import V5State


def test_default_state():
    s = V5State(follow_up_chips=[], live_agent_cta=False, live_agent_trigger=None)
    assert s.live_agent_cta is False
    assert s.follow_up_chips == []


def test_chips_populated():
    s = V5State(
        follow_up_chips=["Factories in Shah Alam", "Warehouse near Port Klang"],
        live_agent_cta=False,
        live_agent_trigger=None,
    )
    assert len(s.follow_up_chips) == 2


def test_live_agent_cta_with_trigger():
    s = V5State(follow_up_chips=[], live_agent_cta=True, live_agent_trigger="transact_intent")
    assert s.live_agent_cta is True
    assert s.live_agent_trigger == "transact_intent"
