from deepagents import create_deep_agent
from langchain.agents.structured_output import ToolStrategy

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
        # mercury-2 ignores provider-native json_schema shapes; tool-calling is reliable
        response_format=ToolStrategy(V5State),
        checkpointer=checkpointer,
    )
