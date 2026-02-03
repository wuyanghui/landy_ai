from typing import Optional
from uuid import uuid4
import uuid
from pydantic import BaseModel
from fastapi import FastAPI

from agent.v1.orchestrator import graph
from langgraph.checkpoint.postgres import PostgresSaver
from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse
from typing import Optional, List, Dict, Any, TypedDict
import json
from langgraph.checkpoint.postgres import PostgresSaver

class InvokeRequest(BaseModel):
    user_input: str
    state_id: Optional[str] = None

app = FastAPI(
    title="Property Search Agent API",
    description="Property Search Agent API",
    version="2.0.0",
    docs_url="/api/docs",
    openapi_url="/api/openapi.json"
    )

DB_URI = 'postgresql://neondb_owner:npg_0tVuL1ygDCPa@ep-old-dust-a1ymzy94-pooler.ap-southeast-1.aws.neon.tech/neondb?sslmode=require'

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

# TypedDict definitions
class ChatRequestDict(BaseModel):
    message: str
    thread_id: Optional[str]

class FilterPreferencesDict(TypedDict, total=False):
    # Add your filter fields based on your tool's output
    location: Optional[str]
    price_min: Optional[float]
    price_max: Optional[float]
    bedrooms: Optional[int]
    property_type: Optional[str]

class PropertyListingDict(TypedDict, total=False):
    property_id: str
    title: Optional[str]
    price: Optional[float]
    bedrooms: Optional[int]
    bathrooms: Optional[int]
    location: Optional[str]
    description: Optional[str]
    url: Optional[str]

class ChatResponseDict(TypedDict):
    thread_id: str
    graph_output: str
    preferences: Optional[Dict[str, Any]]
    recommended_listings: Optional[List[Dict[str, Any]]]
    status: str

class ThreadInfoDict(TypedDict):
    thread_id: str
    status: str
    message: Optional[str]

class ErrorResponseDict(TypedDict):
    thread_id: str
    status: str
    error: str

@app.post("/api/v2/invoke")
async def chat_endpoint(request: ChatRequestDict):
    """
    Main chat endpoint for property search agent
    
    Args:
        message: User's search query
        thread_id: Optional thread ID for conversation continuity
    
    Returns:
        JSON string with thread_id, AI response, preferences, and listings
    """
    try:
        # Extract request data
        message = request.get("message", "")
        if not message:
            raise HTTPException(status_code=400, detail="Message is required")
        
        # Generate or use existing thread_id
        thread_id = request.get("thread_id") or str(uuid.uuid4())
        
        # Initialize variables
        graph_output = ""
        preferences = None
        recommended_listings = None
        
        # Setup PostgreSQL checkpointer
        with PostgresSaver.from_conn_string(DB_URI) as checkpointer:
            checkpointer.setup()
            
            # Import your functions (adjust imports as needed)
            from langchain.agents import create_agent
            from agent.v2.tools.search_listing_database import search_listing_property_from_database
            from agent.v2.utility import _serialize_public_listing
            from agent.v2.prompt.landy_system_prompt import prompt
            from utility.property_listing_init import get_property_listing_collections
            from utility.llm_init import load_llm

            # from your_module import (
            #     search_listing_property_from_database,
            #     create_agent,
            #     load_llm,
            #     get_property_listing_collections,
            #     _serialize_public_listing,
            #     prompt
            # )
            
            tools = [search_listing_property_from_database]
            agent = create_agent(
                system_prompt=prompt,
                model=load_llm(model='gpt-4.1').bind_tools(tools),
                tools=tools,
                checkpointer=checkpointer,
            )
            
            initial_input = {
                "messages": [
                    {"role": "user", "content": message}
                ]
            }
            
            # Stream agent responses
            for chunk in agent.stream(
                initial_input,
                {"configurable": {"thread_id": thread_id}},
            ):
                # Model (LLM) output
                if "model" in chunk:
                    messages = chunk["model"].get("messages", [])
                    if messages:
                        graph_output = messages[0].content
                
                # Tool output
                elif "tools" in chunk:
                    messages = chunk["tools"].get("messages", [])
                    if messages:
                        tool_payload = json.loads(messages[0].content)
                        
                        if "filters_applied" in tool_payload:
                            preferences = tool_payload["filters_applied"]
                        
                        if "property_ids" in tool_payload:
                            property_ids = tool_payload["property_ids"]
                            documents = list(
                                get_property_listing_collections().find(
                                    {"property_id": {'$in': property_ids}}
                                )
                            )
                            recommended_listings = [
                                _serialize_public_listing(doc) for doc in documents
                            ]
        
        # Build response dict
        response: ChatResponseDict = {
            "thread_id": thread_id,
            "graph_output": graph_output,
            "preferences": preferences,
            "recommended_listings": recommended_listings,
            "status": "success"
        }
        
        # Return as JSONResponse with json.dumps
        return JSONResponse(
            content=json.loads(json.dumps(response, default=str)),
            status_code=200
        )
    
    except Exception as e:
        error_response: ErrorResponseDict = {
            "thread_id": request.get("thread_id", "unknown"),
            "status": "error",
            "error": str(e)
        }
        return JSONResponse(
            content=json.loads(json.dumps(error_response)),
            status_code=500
        )
    
@app.get("/api/v2/thread/{thread_id}")
async def get_thread_history(thread_id: str):
    """
    Retrieve conversation history for a specific thread
    """
    try:
        with PostgresSaver.from_conn_string(DB_URI) as checkpointer:
            # Implement thread history retrieval based on your needs
            # This is a placeholder - adjust based on LangGraph's API
            response: ThreadInfoDict = {
                "thread_id": thread_id,
                "status": "success",
                "message": "Thread history retrieval - implement based on your needs"
            }
            
            return JSONResponse(
                content=json.loads(json.dumps(response)),
                status_code=200
            )
    except Exception as e:
        error_response: ErrorResponseDict = {
            "thread_id": thread_id,
            "status": "error",
            "error": str(e)
        }
        return JSONResponse(
            content=json.loads(json.dumps(error_response)),
            status_code=500
        )

@app.delete("/api/v2/thread/{thread_id}")
async def delete_thread(thread_id: str):
    """
    Delete a conversation thread
    """
    try:
        # Implement thread deletion logic
        response: ThreadInfoDict = {
            "thread_id": thread_id,
            "status": "deleted",
            "message": None
        }
        
        return JSONResponse(
            content=json.loads(json.dumps(response)),
            status_code=200
        )
    except Exception as e:
        error_response: ErrorResponseDict = {
            "thread_id": thread_id,
            "status": "error",
            "error": str(e)
        }
        return JSONResponse(
            content=json.loads(json.dumps(error_response)),
            status_code=500
        )
