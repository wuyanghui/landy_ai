"""The three lookups the price-page chat can make about places other than its own page."""
from unittest.mock import patch

from agent.market.tools import MARKET_TOOLS, find_price_pages, get_price_page, list_price_pages


def _indexes(industrial_index, commercial_index):
    return lambda cls: {"industrial": industrial_index, "commercial": commercial_index}[cls]


def test_the_agent_gets_three_read_only_tools():
    assert [t.name for t in MARKET_TOOLS] == ["find_price_pages", "get_price_page", "list_price_pages"]


def test_find_matches_names_in_both_classes(industrial_index, commercial_index):
    with patch("agent.market.tools.fetch_index", side_effect=_indexes(industrial_index, commercial_index)):
        text = find_price_pages.invoke({"query": "shah alam"})
    assert "industrial" in text and "commercial" in text
    assert "selangor/shah-alam" in text
    assert "RM 731" in text and "RM 504" in text
    assert "Kota Elmina" in text  # an estate whose path holds the name


def test_find_can_stick_to_one_class(industrial_index, commercial_index):
    with patch("agent.market.tools.fetch_index", side_effect=_indexes(industrial_index, commercial_index)):
        text = find_price_pages.invoke({"query": "shah alam", "property_class": "shop"})
    assert "RM 504" in text
    assert "RM 731" not in text


def test_find_says_plainly_when_nothing_matches(industrial_index, commercial_index):
    with patch("agent.market.tools.fetch_index", side_effect=_indexes(industrial_index, commercial_index)):
        text = find_price_pages.invoke({"query": "atlantis"})
    assert "No price page" in text


def _get(index, place, page=None):
    with patch("agent.market.tools.fetch_index", return_value=index), \
         patch("agent.market.tools.fetch_page", return_value=page) as fetch:
        text = get_price_page.invoke({"property_class": "factory", "place": place})
    return text, fetch


def test_get_by_path_returns_the_page_summary(industrial_index, shah_alam_page):
    text, fetch = _get(industrial_index, "selangor/shah-alam", shah_alam_page)
    assert "RM 731" in text and "Semi-D factory" in text
    fetch.assert_called_once_with("industrial", "selangor/shah-alam")


def test_get_by_name_finds_the_path(industrial_index, shah_alam_page):
    _, fetch = _get(industrial_index, "Puchong", shah_alam_page)
    fetch.assert_called_once_with("industrial", "selangor/puchong")


def test_get_by_name_prefers_the_area_over_an_estate(industrial_index, shah_alam_page):
    _, fetch = _get(industrial_index, "shah alam", shah_alam_page)
    fetch.assert_called_once_with("industrial", "selangor/shah-alam")


def test_get_lists_choices_for_an_ambiguous_name(industrial_index):
    text, fetch = _get(industrial_index, "ang")  # Selangor, Klang
    assert "several" in text and "selangor/klang" in text
    fetch.assert_not_called()


def test_get_explains_a_place_without_a_page(industrial_index):
    text, fetch = _get(industrial_index, "Atlantis")
    assert "No industrial price page" in text
    fetch.assert_not_called()


def test_list_ranks_a_state_s_areas_by_price(industrial_index):
    with patch("agent.market.tools.fetch_index", return_value=industrial_index):
        text = list_price_pages.invoke({"property_class": "industrial", "parent_path": "selangor", "sort_by": "price"})
    lines = [line for line in text.splitlines() if "selangor/" in line]
    assert [line.split("|")[0].strip() for line in lines] == ["Shah Alam", "Puchong", "Klang"]
    assert "Senai" not in text  # Johor


def test_list_with_no_parent_gives_the_states(industrial_index):
    with patch("agent.market.tools.fetch_index", return_value=industrial_index):
        text = list_price_pages.invoke({"property_class": "industrial"})
    assert "Selangor" in text and "Johor" in text
    assert "Shah Alam" not in text


def test_a_failed_lookup_is_reported_not_raised():
    from agent.market.data import MarketApiError

    with patch("agent.market.tools.fetch_index", side_effect=MarketApiError("down")):
        text = list_price_pages.invoke({"property_class": "industrial"})
    assert "could not be loaded" in text
