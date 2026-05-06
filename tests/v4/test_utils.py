import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from agent.v4.tools._utils import expand_property_category, FACTORY_EXPANSION_MAP


def test_factory_expands_to_all_subtypes():
    result = expand_property_category(["factory"])
    expected = {"factory", "cluster-factory", "detached-factory", "semi-d-factory", "terrace-factory"}
    assert set(result) == expected


def test_non_factory_passthrough():
    result = expand_property_category(["warehouse"])
    assert result == ["warehouse"]


def test_mixed_categories_expanded_and_passthrough():
    result = expand_property_category(["factory", "warehouse"])
    expected = {"factory", "cluster-factory", "detached-factory", "semi-d-factory", "terrace-factory", "warehouse"}
    assert set(result) == expected


def test_empty_list_returns_empty():
    assert expand_property_category([]) == []
