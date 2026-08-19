from deepagents import create_deep_agent

from agent.v6.config import DEFAULT_MODEL
from agent.v6.prompt.agent_prompt import AGENT_PROMPT
from agent.v6.tools.get_page_content import get_page_content
from agent.v6.tools.read_wiki_file import read_wiki_file
from utility.llm_init import load_llm


def create_agent(checkpointer):
    return create_deep_agent(
        model=load_llm(DEFAULT_MODEL),
        tools=[read_wiki_file, get_page_content],
        system_prompt=AGENT_PROMPT,
        checkpointer=checkpointer,
    )
