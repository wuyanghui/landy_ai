"""The price-page chat's system prompt: the Landy Insights knowledge plus the page the visitor is on."""
from agent.market.knowledge import MARKET_KNOWLEDGE
from agent.market.prompt import build_market_prompt


def test_prompt_carries_the_knowledge_and_the_page(shah_alam_page):
    prompt = build_market_prompt(shah_alam_page)
    assert prompt.startswith(MARKET_KNOWLEDGE)
    assert "Shah Alam" in prompt and "RM 731" in prompt


def test_knowledge_explains_what_the_figures_are():
    for idea in ("NAPIC", "median", "floor space", "middle half", "provisional", "30 sales"):
        assert idea in MARKET_KNOWLEDGE, idea


def test_knowledge_keeps_the_legal_and_honesty_lines():
    text = MARKET_KNOWLEDGE.lower()
    assert "valuation" in text  # never call an answer a valuation
    assert "average" in text  # say typical, not average
    assert "never invent" in text


def test_knowledge_hands_off_to_jay():
    assert "Jay Kew" in MARKET_KNOWLEDGE
    assert "+6011-33199291" in MARKET_KNOWLEDGE


def test_knowledge_names_the_tools():
    for tool in ("find_price_pages", "get_price_page", "list_price_pages"):
        assert tool in MARKET_KNOWLEDGE
