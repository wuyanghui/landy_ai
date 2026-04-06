from utility.llm_init import load_llm

from deepagents import create_deep_agent
from langchain.agents.middleware import wrap_model_call, ModelRequest, ModelResponse
from typing import TypedDict
from langchain.agents.structured_output import ProviderStrategy
from pydantic import BaseModel, Field
from typing import List

from pydantic import BaseModel, Field
from typing import List
from agent.v3.prompt.agent_prompt import AGENT_PROMPT
from agent.v3.tools.search_property import search_properties

class OverallState(BaseModel):
    agent_referral_shown : bool = Field(
        description="boolean for agent information Jay Kew | CID Realtors 📞 +6011-33199291 contact information"
    )

    final_output: str = Field(
        description="Final natural language response shown to the user"
    )
    
    recommended_property_ids: List[str] = Field(
        description="List of recommended property IDs from search results"
    )

    follow_up_suggestions: List[str] = Field(
        description=(
            "2-3 ready-to-use search queries that the user can click to refine their results. "
            "Each must be a standalone search string (e.g., 'Warehouse in Klang below RM 5M'). "
            "Do NOT phrase as questions or instructions to the user."
        )
    )

# --- Models (role-based, not size-based) ---
router_model    = load_llm("openai/gpt-5.4-nano")
search_model    = load_llm("openai/gpt-5.4-mini")
response_model  = load_llm("openai/gpt-5.4")


# --- Dynamic Model Selection ---
@wrap_model_call
def dynamic_model_selection(request: ModelRequest, handler) -> ModelResponse:
    """
    Production-ready selector:
    1. Task-driven (primary)
    2. Lightweight complexity (search only)
    """

    state = request.state or {}
    task = state.get("task", "default")
    messages = state.get("messages") or getattr(request, "messages", [])

    # --- Extract last user message ---
    last_user_msg = ""
    if messages:
        last_user_msg = getattr(messages[-1], "content", "").lower()

    word_count = len(last_user_msg.split())

    # --- Lightweight complexity signals ---
    is_long_query = word_count > 25

    has_compare_intent = any(k in last_user_msg for k in [
        "compare", "best", "which", "difference", "pros", "cons"
    ])

    has_multi_constraints = sum([
        "near" in last_user_msg,
        any(k in last_user_msg for k in ["rm", "budget", "price"]),
        any(k in last_user_msg for k in ["sqft", "size", "built-up", "land"])
    ]) >= 2

    # --- Model Selection (Task-first) ---
    if task == "routing":
        model = router_model

    elif task == "search":
        if has_compare_intent or has_multi_constraints or is_long_query:
            model = search_model
        else:
            model = router_model  # cheap shortcut

    elif task == "response":
        model = response_model

    else:
        # safe fallback
        model = router_model

    return handler(request.override(model=model))

# --- Dynamic Model Selection ---
@wrap_model_call
async def adynamic_model_selection(request: ModelRequest, handler) -> ModelResponse:
    """
    Async Production-ready selector:
    1. Task-driven (primary)
    2. Lightweight complexity (search only)
    """

    state = request.state or {}
    task = state.get("task", "default")
    messages = state.get("messages") or getattr(request, "messages", [])

    # --- Extract last user message ---
    last_user_msg = ""
    if messages:
        # Standardize content extraction for async context
        msg_obj = messages[-1]
        last_user_msg = getattr(msg_obj, "content", "")
        if not isinstance(last_user_msg, str):
            last_user_msg = str(last_user_msg)
        last_user_msg = last_user_msg.lower()

    word_count = len(last_user_msg.split())

    # --- Lightweight complexity signals ---
    is_long_query = word_count > 25

    has_compare_intent = any(k in last_user_msg for k in [
        "compare", "best", "which", "difference", "pros", "cons"
    ])

    has_multi_constraints = sum([
        "near" in last_user_msg,
        any(k in last_user_msg for k in ["rm", "budget", "price"]),
        any(k in last_user_msg for k in ["sqft", "size", "built-up", "land"])
    ]) >= 2

    # --- Model Selection (Task-first) ---
    if task == "routing":
        selected_model = router_model

    elif task == "search":
        if has_compare_intent or has_multi_constraints or is_long_query:
            selected_model = search_model
        else:
            selected_model = router_model  # cheap shortcut

    elif task == "response":
        selected_model = response_model

    else:
        # safe fallback
        selected_model = router_model

# --- Agent Setup ---
from langgraph.checkpoint.memory import InMemorySaver

agent = create_deep_agent(
    model=router_model,  # default fallback model
    tools=[search_properties],
    middleware=[dynamic_model_selection],
    system_prompt=AGENT_PROMPT,
    response_format=ProviderStrategy(OverallState),
    checkpointer=InMemorySaver()
)

import json
for chunk in agent.stream(
    {
        "messages": [{"role": "user", "content": "not accurate"}],
    },
    {"configurable": {"thread_id": "003"}},
    stream_mode="updates",
    version="v2",
):
    if chunk["type"] == "updates":
        if chunk["ns"]:
            # Subagent event - namespace identifies the source
            print(f"[subagent: {chunk['ns']}]")
        else:
            # Main agent event
            print("[main agent]")
            if "model" in chunk['data']:
                # 1. Get the raw string content from the message
                raw_content = chunk['data']['model']['messages'][0].content
                
                try:
                    # 2. Parse that string into a real Python dictionary
                    dict_output = json.loads(raw_content)
                    
                    # 3. Now you can access keys safely
                    print(f"Contact Agent: {dict_output.get('agent_referral_shown')}")
                    print(f"Final Output: {dict_output.get('final_output')}")
                    print(f"Follow Up: {dict_output.get('follow_up_suggestions')}")
                    print({dict_output.get('recommended_property_ids')})

                except (json.JSONDecodeError, TypeError):
                    # Handle cases where the model returns plain text instead of JSON
                    print("Output was not a valid JSON string:")
                    print(raw_content)
