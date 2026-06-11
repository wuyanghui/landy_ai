from deepagents import create_deep_agent

from agent.v5.config import DEFAULT_MODEL
from agent.v5.state import V5State
from agent.v5.prompt.agent_prompt import AGENT_PROMPT
from agent.v5.tools.find_listings import find_listings
from agent.v5.tools.get_listing_detail import get_listing_detail
from utility.llm_init import load_llm


def create_agent(checkpointer):
    # No response_format here: langchain's ToolStrategy binds tool_choice="any" on
    # every model call, under which the model emits only tool calls and never writes
    # the user-facing answer text. The agent ends turns with plain text (which
    # streams), and V5State is extracted afterwards by extract_v5_state.
    return create_deep_agent(
        model=load_llm(DEFAULT_MODEL),
        tools=[find_listings, get_listing_detail],
        system_prompt=AGENT_PROMPT,
        checkpointer=checkpointer,
    )


_EXTRACTOR_PROMPT = """You extract UI metadata from one turn of Landy AI, an industrial property chat for Malaysia.
Given the USER message and the ASSISTANT answer, produce:

follow_up_chips: 2-3 short tappable next actions in the conversation's language, e.g.
"Factories in Shah Alam under RM3M" | "Show me bigger options" | "Speak to our property agent".

live_agent_cta + live_agent_trigger: true with the matching trigger ONLY when the turn shows:
- transact_intent: user wants to view, make an offer, negotiate, or book a visit
- hyper_specific: a requirement so specific the listings cannot match it
- exhausted: no results remain even after broadening the search
- investment: user asked for yield, appreciation, ROI, or market forecast figures
Otherwise live_agent_cta=false, live_agent_trigger=null."""


async def extract_v5_state(user_message: str, answer_text: str) -> V5State:
    llm = load_llm(DEFAULT_MODEL).with_structured_output(V5State, method="function_calling")
    return await llm.ainvoke([
        ("system", _EXTRACTOR_PROMPT),
        ("human", f"USER: {user_message}\n\nASSISTANT: {answer_text}"),
    ])
