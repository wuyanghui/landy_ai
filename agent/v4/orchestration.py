# agent/v4/orchestration.py
from deepagents import create_deep_agent
from langchain.agents.structured_output import ProviderStrategy

from agent.v4.config import DEFAULT_MODEL
from agent.v4.state import OverallState
from agent.v4.prompt.agent_prompt import AGENT_PROMPT
from agent.v4.tools.search_properties import asearch_properties
from agent.v4.tools.properties_by_radius import aget_properties_by_radius
from agent.v4.tools.newest_listings import aget_newest_listings
from agent.v4.tools.property_detail import aget_property_detail
from utility.llm_init import load_llm


def create_agent(checkpointer):
    return create_deep_agent(
        model=load_llm(DEFAULT_MODEL),
        tools=[
            asearch_properties,
            aget_properties_by_radius,
            aget_newest_listings,
            aget_property_detail,
        ],
        system_prompt=AGENT_PROMPT,
        response_format=ProviderStrategy(OverallState),
        checkpointer=checkpointer,
    )
