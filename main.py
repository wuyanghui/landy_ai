from pydantic import BaseModel
from fastapi import FastAPI
from agent.v1.orchestrator import graph


class InvokeRequest(BaseModel):
    user_input: str

app = FastAPI()

@app.post("/invoke")
async def invoke(req: InvokeRequest):
    result = graph.invoke({"user_input": req.user_input})
    return result

