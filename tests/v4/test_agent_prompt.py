import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from agent.v4.prompt.agent_prompt import AGENT_PROMPT


def test_prompt_is_non_empty_string():
    assert isinstance(AGENT_PROMPT, str)
    assert len(AGENT_PROMPT) > 500


def test_prompt_contains_key_sections():
    for section in ["INTERNAL STATE", "REFERRAL TRIGGERS", "TOOL GUIDE",
                     "CORE PRINCIPLES", "HARD RULES", "OUTPUT FORMAT"]:
        assert section in AGENT_PROMPT, f"Missing section: {section}"


def test_prompt_references_all_four_tools():
    for tool_name in ["asearch_properties", "aget_properties_by_radius",
                      "aget_newest_listings", "aget_property_detail"]:
        assert tool_name in AGENT_PROMPT, f"Missing tool reference: {tool_name}"


def test_prompt_uses_correct_state_field_name():
    assert "recommended_property_ids" in AGENT_PROMPT
    assert "recommended_listings" not in AGENT_PROMPT


def test_prompt_contains_referral_contact():
    assert "Jay Kew" in AGENT_PROMPT
    assert "+6011-33199291" in AGENT_PROMPT
