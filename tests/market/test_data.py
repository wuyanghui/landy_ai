"""The market API client and the page summary the chat reads."""
from unittest.mock import MagicMock, patch

import httpx
import pytest

from agent.market import data
from agent.market.data import MarketApiError, page_summary, page_url, property_class


@pytest.fixture(autouse=True)
def _fresh_cache():
    data.clear_cache()
    yield
    data.clear_cache()


def _response(status, payload=None):
    response = MagicMock(spec=httpx.Response)
    response.status_code = status
    response.json.return_value = payload
    return response


def test_property_class_accepts_everyday_words():
    assert property_class("factory") == "industrial"
    assert property_class("Warehouse") == "industrial"
    assert property_class("shop") == "commercial"
    assert property_class("office") == "commercial"
    assert property_class("commercial") == "commercial"


def test_property_class_rejects_residential():
    with pytest.raises(ValueError, match="industrial or commercial"):
        property_class("condo")


def test_page_url_points_at_the_live_price_page():
    assert page_url("industrial", "selangor/shah-alam") == (
        "https://www.industrialprop.com.my/industrial-property-prices/selangor/shah-alam"
    )
    assert page_url("commercial", "") == "https://www.industrialprop.com.my/commercial-property-prices"


def test_fetch_page_reads_the_public_api(shah_alam_page):
    with patch("agent.market.data.httpx.get", return_value=_response(200, shah_alam_page)) as get:
        page = data.fetch_page("industrial", "/selangor/shah-alam/")
    assert page["name"] == "Shah Alam"
    url = get.call_args.args[0]
    assert url.endswith("/api/market/industrial/page")
    assert get.call_args.kwargs["params"] == {"path": "selangor/shah-alam"}


def test_fetch_page_returns_none_for_a_place_without_a_page():
    with patch("agent.market.data.httpx.get", return_value=_response(404)):
        assert data.fetch_page("industrial", "selangor/nowhere") is None


def test_fetch_page_raises_on_an_outage():
    with patch("agent.market.data.httpx.get", return_value=_response(503)):
        with pytest.raises(MarketApiError):
            data.fetch_page("industrial", "selangor")


def test_fetch_index_is_cached(industrial_index):
    with patch("agent.market.data.httpx.get", return_value=_response(200, industrial_index)) as get:
        data.fetch_index("industrial")
        data.fetch_index("industrial")
    assert get.call_count == 1


def test_summary_has_the_figures_a_visitor_asks_about(shah_alam_page):
    text = page_summary(shah_alam_page)
    for fact in (
        "Shah Alam",
        "Malaysia > Selangor > Shah Alam",
        "RM 731",
        "438 sales",
        "RM 523 to RM 959",  # middle half
        "RM 4.5M",  # typical sale price
        "+41% vs Selangor",
        "+80% vs Malaysia",
        "RM 753",  # last two years
        "Semi-D factory",
        "RM 918",
        "Kota Elmina",
        "87% freehold",
        "2026 RM 823 (24 sales, provisional)",
        "June 2026",  # data through
        "https://www.industrialprop.com.my/industrial-property-prices/selangor/shah-alam",
    ):
        assert fact in text, fact


def test_summary_of_an_older_dataset_says_nothing_about_missing_figures(old_page):
    text = page_summary(old_page)
    assert "RM 731" in text
    assert "middle half" not in text.lower()
    assert "last two years" not in text.lower()
    assert "None" not in text
