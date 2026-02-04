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
import logging
import traceback
import os
from dotenv import load_dotenv

load_dotenv()

# Configure logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

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

DB_URI = os.environ.get("DB_URI")

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

# FIXED: ChatRequestDict should be BaseModel, not using .get()
class ChatRequestDict(BaseModel):
    message: str
    thread_id: Optional[str] = None

# FIXED: ChatRequestDict should be BaseModel, not using .get()
class ChatSlugRequestDict(BaseModel):
    message: str
    slug: str
    thread_id: Optional[str] = None

class FilterPreferencesDict(TypedDict, total=False):
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

@app.post("/api/v2/invoke/slug")
async def chat_endpoint(request: ChatSlugRequestDict):
    """
    Main chat endpoint for property search agent
    
    Args:
        message: User's search query
        thread_id: Optional thread ID for conversation continuity
        slug: slug of the property

    Returns:
        JSON string with thread_id, AI response, preferences, and listings
    """
    logger.info(f"Received request: {request}")
    try:
        # FIXED: Use Pydantic model attributes instead of .get()
        message = request.message
        if not message:
            logger.error("Empty message received")
            raise HTTPException(status_code=400, detail="Message is required")
        
        # Generate or use existing thread_id
        thread_id = request.thread_id or str(uuid.uuid4())
        logger.info(f"Processing message for thread_id: {thread_id}")
        
        slug = request.slug
        if not slug:
            logger.error("Empty slug received")
            raise HTTPException(status_code=400, detail="Slug is required")
        
        # Initialize variables
        graph_output = ""
        
        # STEP 1: Test database connection first
        logger.info("Testing database connection...")
        try:
            with PostgresSaver.from_conn_string(DB_URI) as checkpointer:
                checkpointer.setup()
                logger.info("Database connection successful")
        except Exception as db_error:
            logger.error(f"Database connection failed: {str(db_error)}")
            logger.error(traceback.format_exc())
            raise HTTPException(status_code=500, detail=f"Database connection error: {str(db_error)}")
        
        # STEP 2: Try imports
        logger.info("Importing required modules...")
        try:
            from langchain.agents import create_agent
            from agent.v2.prompt.landy_slug_prompt import get_slug_prompt
            from utility.property_listing_init import get_property_listing_collections
            from utility.llm_init import load_llm
            logger.info("All imports successful")
        except ImportError as import_error:
            logger.error(f"Import failed: {str(import_error)}")
            logger.error(traceback.format_exc())
            raise HTTPException(status_code=500, detail=f"Import error: {str(import_error)}")
        
        # STEP 3: Setup agent
        logger.info("Setting up slug agent...")
        try:
            with PostgresSaver.from_conn_string(DB_URI) as checkpointer:
                checkpointer.setup()
                get_property_by_slug = get_property_listing_collections().find_one({"slug": slug})
                slug_agent = create_agent(
                    system_prompt=get_slug_prompt(get_property_by_slug),
                    model=load_llm(model='gpt-4.1-mini'),
                    checkpointer=checkpointer,
                )
                logger.info("Agent created successfully")
                
                initial_input = {
                    "messages": [
                        {"role": "user", "content": message}
                    ]
                }
                
                # Stream agent responses
                logger.info("Starting agent stream...")
                chunk_count = 0
                for chunk in slug_agent.stream(
                    initial_input,
                    {"configurable": {"thread_id": thread_id}},
                ):
                    chunk_count += 1
                    logger.debug(f"Processing chunk {chunk_count}: {chunk.keys()}")
                    
                    # Model (LLM) output
                    if "model" in chunk:
                        messages = chunk["model"].get("messages", [])
                        if messages:
                            graph_output = messages[0].content
                            logger.info(f"Model output received: {graph_output[:100]}...")
                    
                logger.info(f"Agent stream completed. Processed {chunk_count} chunks")
        
        except Exception as agent_error:
            logger.error(f"Agent execution error: {str(agent_error)}")
            logger.error(traceback.format_exc())
            raise HTTPException(status_code=500, detail=f"Agent execution error: {str(agent_error)}")
        
        # Return response
        response_data = {
            "thread_id": thread_id,
            "graph_output": graph_output,
            "status": "success"
        }
        
        logger.info(f"Returning successful response for slug agent thread {thread_id}")
        return JSONResponse(content=response_data, status_code=200)
    
    except HTTPException:
        # Re-raise HTTP exceptions
        raise
    
    except Exception as e:
        # Log the full error
        logger.error(f"Unexpected error: {str(e)}")
        logger.error(traceback.format_exc())
        
        error_response = {
            "thread_id": request.thread_id if hasattr(request, 'thread_id') and request.thread_id else "unknown",
            "status": "error",
            "error": str(e),
            "error_type": type(e).__name__,
            "traceback": traceback.format_exc()
        }
        
        return JSONResponse(content=error_response, status_code=500)
        
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
    logger.info(f"Received request: {request}")
    
    try:
        # FIXED: Use Pydantic model attributes instead of .get()
        message = request.message
        if not message:
            logger.error("Empty message received")
            raise HTTPException(status_code=400, detail="Message is required")
        
        # Generate or use existing thread_id
        thread_id = request.thread_id or str(uuid.uuid4())
        logger.info(f"Processing message for thread_id: {thread_id}")
        
        # Initialize variables
        graph_output = ""
        preferences = None
        recommended_listings = None
        
        # STEP 1: Test database connection first
        logger.info("Testing database connection...")
        try:
            with PostgresSaver.from_conn_string(DB_URI) as checkpointer:
                checkpointer.setup()
                logger.info("Database connection successful")
        except Exception as db_error:
            logger.error(f"Database connection failed: {str(db_error)}")
            logger.error(traceback.format_exc())
            raise HTTPException(status_code=500, detail=f"Database connection error: {str(db_error)}")
        
        # STEP 2: Try imports
        logger.info("Importing required modules...")
        try:
            from langchain.agents import create_agent
            from agent.v2.tools.search_listing_database import search_listing_property_from_database
            from agent.v2.utility import _serialize_public_listing
            from agent.v2.prompt.landy_system_prompt import prompt
            from utility.property_listing_init import get_property_listing_collections
            from utility.llm_init import load_llm
            logger.info("All imports successful")
        except ImportError as import_error:
            logger.error(f"Import failed: {str(import_error)}")
            logger.error(traceback.format_exc())
            raise HTTPException(status_code=500, detail=f"Import error: {str(import_error)}")
        
        # STEP 3: Setup agent
        logger.info("Setting up agent...")
        try:
            with PostgresSaver.from_conn_string(DB_URI) as checkpointer:
                checkpointer.setup()
                
                tools = [search_listing_property_from_database]
                agent = create_agent(
                    system_prompt=prompt,
                    model=load_llm(model='gpt-5-mini').bind_tools(tools),
                    tools=tools,
                    checkpointer=checkpointer,
                )
                logger.info("Agent created successfully")
                
                initial_input = {
                    "messages": [
                        {"role": "user", "content": message}
                    ]
                }
                
                # Stream agent responses
                logger.info("Starting agent stream...")
                chunk_count = 0
                for chunk in agent.stream(
                    initial_input,
                    {"configurable": {"thread_id": thread_id}},
                ):
                    chunk_count += 1
                    logger.debug(f"Processing chunk {chunk_count}: {chunk.keys()}")
                    
                    # Model (LLM) output
                    if "model" in chunk:
                        messages = chunk["model"].get("messages", [])
                        if messages:
                            graph_output = messages[0].content
                            logger.info(f"Model output received: {graph_output[:100]}...")
                    
                    # Tool output
                    elif "tools" in chunk:
                        messages = chunk["tools"].get("messages", [])
                        if messages:
                            try:
                                tool_payload = json.loads(messages[0].content)
                                logger.info(f"Tool payload: {tool_payload}")
                                
                                if "filters_applied" in tool_payload:
                                    preferences = tool_payload["filters_applied"]
                                    logger.info(f"Preferences extracted: {preferences}")
                                
                                if "property_ids" in tool_payload:
                                    property_ids = tool_payload["property_ids"]
                                    logger.info(f"Fetching properties for IDs: {property_ids}")
                                    
                                    documents = list(
                                        get_property_listing_collections().find(
                                            {"property_id": {'$in': property_ids}}
                                        )
                                    )
                                    recommended_listings = [
                                        _serialize_public_listing(doc) for doc in documents
                                    ]
                                    logger.info(f"Found {len(recommended_listings)} listings")
                            except json.JSONDecodeError as json_error:
                                logger.error(f"JSON decode error: {str(json_error)}")
                                logger.error(f"Content: {messages[0].content}")
                
                logger.info(f"Agent stream completed. Processed {chunk_count} chunks")
        
        except Exception as agent_error:
            logger.error(f"Agent execution error: {str(agent_error)}")
            logger.error(traceback.format_exc())
            raise HTTPException(status_code=500, detail=f"Agent execution error: {str(agent_error)}")
        
        # Return response
        response_data = {
            "thread_id": thread_id,
            "graph_output": graph_output,
            "preferences": preferences,
            "recommended_listings": recommended_listings,
            "status": "success"
        }
        
        logger.info(f"Returning successful response for thread {thread_id}")
        return JSONResponse(content=response_data, status_code=200)
    
    except HTTPException:
        # Re-raise HTTP exceptions
        raise
    
    except Exception as e:
        # Log the full error
        logger.error(f"Unexpected error: {str(e)}")
        logger.error(traceback.format_exc())
        
        error_response = {
            "thread_id": request.thread_id if hasattr(request, 'thread_id') and request.thread_id else "unknown",
            "status": "error",
            "error": str(e),
            "error_type": type(e).__name__,
            "traceback": traceback.format_exc()
        }
        
        return JSONResponse(content=error_response, status_code=500)
    