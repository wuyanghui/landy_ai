"""The price-page chat's system prompt: the Landy Insights knowledge, then the page the visitor is on."""
from agent.market.data import page_summary
from agent.market.knowledge import MARKET_KNOWLEDGE


def build_market_prompt(page: dict) -> str:
    return (
        f"{MARKET_KNOWLEDGE}\n"
        "# THE PAGE THE VISITOR IS ON\n"
        "These are the figures on screen. Answer from them first; use the tools for any other place.\n\n"
        f"{page_summary(page)}\n"
    )
