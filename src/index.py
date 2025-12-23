from typing import Optional
from uuid import uuid4

from pydantic import BaseModel
from fastapi import FastAPI

from agent.orchestrator import graph


class InvokeRequest(BaseModel):
    user_input: str
    state_id: Optional[str] = None

app = FastAPI()

@app.get("/health")
def health():
    return {"status": "ok"}

@app.post("/invoke")
async def invoke(req: InvokeRequest):
    state_id = req.state_id or str(uuid4())

    initial_state = {
        "state_id": state_id,
        "user_input": req.user_input,
    }

    result = await graph.ainvoke(
        initial_state,
        config={"configurable": {"thread_id": state_id}},
    )

    result["state_id"] = state_id
    return result
