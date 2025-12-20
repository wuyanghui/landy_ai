from pydantic import BaseModel
from fastapi import FastAPI
from agent.orchestrator import graph


class InvokeRequest(BaseModel):
    user_input: str

app = FastAPI()

@app.get("/health")
def health():
    return {"status": "ok"}

@app.post("/invoke")
async def invoke(req: InvokeRequest):
    result = await graph.ainvoke({"user_input": req.user_input})
    return result
