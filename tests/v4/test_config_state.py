import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from agent.v4.config import DEFAULT_MODEL
from agent.v4.state import OverallState


def test_default_model_is_string():
    assert isinstance(DEFAULT_MODEL, str)
    assert len(DEFAULT_MODEL) > 0


def test_overall_state_fields():
    state = OverallState(
        agent_referral_shown=False,
        final_output="hello",
        recommended_property_ids=["PROP-001"],
        follow_up_suggestions=["Warehouse in Shah Alam"],
    )
    assert state.agent_referral_shown is False
    assert state.final_output == "hello"
    assert state.recommended_property_ids == ["PROP-001"]
    assert state.follow_up_suggestions == ["Warehouse in Shah Alam"]


def test_recommended_property_ids_is_list_of_strings():
    state = OverallState(
        agent_referral_shown=True,
        final_output="done",
        recommended_property_ids=["A", "B"],
        follow_up_suggestions=[],
    )
    assert all(isinstance(pid, str) for pid in state.recommended_property_ids)
