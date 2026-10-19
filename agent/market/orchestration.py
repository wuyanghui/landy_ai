"""The price-page chat agent: one Landy Insights page loaded into the prompt, plus lookups for every other place."""
from langchain.agents import create_agent

from agent.market.prompt import build_market_prompt
from agent.market.tools import MARKET_TOOLS
from utility.llm_init import load_llm

# Same model as the listing page's chat (/api/v2/invoke/slug).
MARKET_MODEL = "openai/gpt-5.4-mini"


def create_market_agent(page: dict, checkpointer):
    return create_agent(
        model=load_llm(model=MARKET_MODEL),
        tools=MARKET_TOOLS,
        system_prompt=build_market_prompt(page),
        checkpointer=checkpointer,
    )
