from pydantic import BaseModel
from fastapi import FastAPI
from agent.orchestrator import graph


class InvokeRequest(BaseModel):
    user_input: str

app = FastAPI()

@app.post("/invoke")
async def invoke(req: InvokeRequest):
    result = graph.invoke({"user_input": req.user_input})
    return result

if __name__ == "__main__":
    test_inputs = [
        "I am looking for a light industrial factory in Shah Alam around 20,000 sqft with loading bay and 3-phase power. Budget below RM6 million.",

        "Need a warehouse for logistics operations in Klang Valley, preferably near Port Klang, minimum 50,000 sqft, high ceiling, and easy highway access.",

        "Looking to rent an industrial property in Subang or Puchong suitable for food processing. Must have cold room potential and proper drainage.",

        "Searching for a heavy industrial land or factory in Klang Valley for metal fabrication. Require high power supply, crane capacity, and standalone building.",

        "Any small industrial unit around Kepong or Sungai Buloh, about 5,000–8,000 sqft, suitable for e-commerce storage and last-mile distribution?"
    ]
    for test in test_inputs:
        result = graph.invoke(
            {
                "user_input": test
            }
        )
        print(result['graph_output'])

        # Test FastAPI endpoint using TestClient
        from fastapi.testclient import TestClient
        client = TestClient(app)
        api_response = client.post("/invoke", json={"user_input": test})
        print("Invoke endpoint response:", api_response.json()['graph_output'])