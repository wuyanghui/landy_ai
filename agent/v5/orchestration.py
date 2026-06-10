from deepagents import create_deep_agent
from langchain.agents.structured_output import ProviderStrategy

from agent.v5.config import DEFAULT_MODEL
from agent.v5.state import V5State
from agent.v5.prompt.agent_prompt import AGENT_PROMPT
from agent.v5.tools.find_listings import find_listings
from agent.v5.tools.get_listing_detail import get_listing_detail
from utility.llm_init import load_llm


def create_agent(checkpointer):
    return create_deep_agent(
        model=load_llm(DEFAULT_MODEL),
        tools=[find_listings, get_listing_detail],
        system_prompt=AGENT_PROMPT,
        response_format=ProviderStrategy(V5State),
        checkpointer=checkpointer,
    )
