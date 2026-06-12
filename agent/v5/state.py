from typing import List, Optional
from pydantic import BaseModel, Field


class V5State(BaseModel):
    """UI metadata for one chat turn, extracted from the user message and the
    assistant answer."""

    follow_up_chips: List[str] = Field(
        description="2-3 short action strings shown as clickable chips after the response"
    )
    live_agent_cta: bool = Field(
        description="True when the agent has detected a trigger requiring live agent escalation"
    )
    live_agent_trigger: Optional[str] = Field(
        default=None,
        description="Which trigger fired: transact_intent | hyper_specific | exhausted | investment | out_of_coverage"
    )
