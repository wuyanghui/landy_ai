from pydantic import BaseModel, Field
from typing import List


class OverallState(BaseModel):
    agent_referral_shown: bool = Field(
        description="True when referral to Jay Kew was shown this turn"
    )
    final_output: str = Field(
        description="Full natural language response shown to the user"
    )
    recommended_property_ids: List[str] = Field(
        description="Ordered list of property_ids for all listings shown in this response"
    )
    follow_up_suggestions: List[str] = Field(
        description="2-3 ready-to-use search strings the user can click"
    )
