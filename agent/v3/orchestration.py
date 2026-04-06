import json
from typing import List

from pydantic import BaseModel, Field
from langchain.agents.middleware import wrap_model_call, ModelRequest, ModelResponse
from langchain.agents.structured_output import ProviderStrategy
from langgraph.checkpoint.memory import InMemorySaver
from deepagents import create_deep_agent

from utility.llm_init import load_llm
from agent.v3.prompt.agent_prompt import AGENT_PROMPT
from agent.v3.tools.search_property import search_properties


# ---------------------------------------------------------------------------
# Response schema
# ---------------------------------------------------------------------------

class OverallState(BaseModel):
    agent_referral_shown: bool = Field(
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


# ---------------------------------------------------------------------------
# Models (role-based, not size-based)
# ---------------------------------------------------------------------------

router_model   = load_llm("openai/gpt-5.4-nano")
search_model   = load_llm("openai/gpt-5.4-mini")
response_model = load_llm("openai/gpt-5.4")


# ---------------------------------------------------------------------------
# Shared complexity signals
# ---------------------------------------------------------------------------

def _select_model(task: str, last_user_msg: str):
    word_count = len(last_user_msg.split())

    is_long_query = word_count > 25
    has_compare_intent = any(k in last_user_msg for k in [
        "compare", "best", "which", "difference", "pros", "cons"
    ])
    has_multi_constraints = sum([
        "near" in last_user_msg,
        any(k in last_user_msg for k in ["rm", "budget", "price"]),
        any(k in last_user_msg for k in ["sqft", "size", "built-up", "land"]),
    ]) >= 2

    if task == "routing":
        return router_model
    elif task == "search":
        return search_model if (has_compare_intent or has_multi_constraints or is_long_query) else router_model
    elif task == "response":
        return response_model
    else:
        return router_model


def _extract_last_user_msg(request: ModelRequest) -> str:
    state = request.state or {}
    messages = state.get("messages") or getattr(request, "messages", [])
    if not messages:
        return ""
    content = getattr(messages[-1], "content", "")
    return (content if isinstance(content, str) else str(content)).lower()


# ---------------------------------------------------------------------------
# Middleware
# ---------------------------------------------------------------------------

@wrap_model_call
def dynamic_model_selection(request: ModelRequest, handler) -> ModelResponse:
    task = (request.state or {}).get("task", "default")
    last_user_msg = _extract_last_user_msg(request)
    model = _select_model(task, last_user_msg)
    return handler(request.override(model=model))


@wrap_model_call
async def adynamic_model_selection(request: ModelRequest, handler) -> ModelResponse:
    task = (request.state or {}).get("task", "default")
    last_user_msg = _extract_last_user_msg(request)
    model = _select_model(task, last_user_msg)
    return await handler(request.override(model=model))  # FIXED: was missing return


