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
    
    recommended_listings: List[str] = Field(
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
premium_model  = load_llm("anthropic/claude-haiku-4.5")

@wrap_model_call
async def adynamic_model_selection(request: ModelRequest, handler) -> ModelResponse:

    # --- Safely extract last human message from whatever structure arrives ---
    last_user_msg = ""

    # Try all known locations the message might live in
    candidates = []

    # Path 1: request.messages list (most common in deepagents middleware)
    raw_messages = getattr(request, "messages", None) or []
    candidates.extend(raw_messages)

    # Path 2: request.state["messages"] (LangGraph state dict)
    state = getattr(request, "state", None) or {}
    if isinstance(state, dict):
        candidates.extend(state.get("messages", []))

    # Walk backwards — find the last human turn
    for msg in reversed(candidates):
        # Handle both LangChain message objects and raw dicts
        if isinstance(msg, dict):
            role    = msg.get("role", "")
            content = msg.get("content", "")
        else:
            role    = getattr(msg, "type", "") or getattr(msg, "role", "")
            content = getattr(msg, "content", "")

        if role in ("human", "user") and content:
            last_user_msg = content.lower() if isinstance(content, str) else str(content).lower()
            break

    word_count = len(last_user_msg.split())

    print(f"[model_selector] extracted msg ({word_count}w): {last_user_msg[:80]!r}")

    # --- Signals ---
    has_multi_intent = sum([
        any(k in last_user_msg for k in ["compare", "vs", "rank"]),
        any(k in last_user_msg for k in ["summarise", "summarize", "recap", "overview"]),
        any(k in last_user_msg for k in ["report", "shortlist", "share", "forward"]),
        any(k in last_user_msg for k in ["and then", "after that", "also show", "as well as"]),
    ]) >= 2

    has_analysis_intent = any(k in last_user_msg for k in [
        "analyse", "analyze", "explain why", "which is better",
        "recommend", "advise", "should i", "what would you suggest",
    ])

    has_report_intent = any(k in last_user_msg for k in [
        "report", "summary i can share", "format for sharing",
        "send to my", "export", "shortlist all",
    ])

    has_compare_intent = any(k in last_user_msg for k in [
        "compare", "best", "which", "difference", "pros", "cons",
    ])

    has_multi_constraints = sum([
        "near"  in last_user_msg,
        any(k in last_user_msg for k in ["rm", "budget", "price"]),
        any(k in last_user_msg for k in ["sqft", "size", "built-up", "land"]),
    ]) >= 2

    is_long_query      = word_count > 25
    is_very_long_query = word_count > 50

    # --- Select raw model (no .with_structured_output — create_deep_agent owns that) ---
    if has_multi_intent or has_analysis_intent or has_report_intent or is_very_long_query:
        selected_model = premium_model
        tier = "premium"
    elif has_compare_intent or has_multi_constraints or is_long_query:
        selected_model = search_model
        tier = "search"
    else:
        selected_model = router_model
        tier = "router"

    print(f"[model_selector] tier={tier} | multi_intent={has_multi_intent} | "
          f"analysis={has_analysis_intent} | report={has_report_intent}")

    return await handler(request.override(model=selected_model))