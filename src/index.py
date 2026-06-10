from typing import Optional
from uuid import uuid4
import uuid
from pydantic import BaseModel
from fastapi import FastAPI

from agent.v1.orchestrator import graph
from langgraph.checkpoint.postgres import PostgresSaver
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
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

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_thread_id(request) -> str:
    return request.thread_id or str(uuid.uuid4())


def _test_db_connection():
    logger.info("Testing database connection...")
    try:
        with PostgresSaver.from_conn_string(DB_URI) as checkpointer:
            checkpointer.setup()
        logger.info("Database connection successful")
    except Exception as e:
        logger.error(f"Database connection failed: {str(e)}\n{traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"Database connection error: {str(e)}")
    
async def _test_db_connection_async():
    logger.info("Testing async database connection...")
    try:
        async with AsyncPostgresSaver.from_conn_string(DB_URI) as checkpointer:
            await checkpointer.setup()
        logger.info("Async database connection successful")
    except Exception as e:
        logger.error(f"Async database connection failed: {str(e)}\n{traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"Database connection error: {str(e)}")

def _build_error_response(request, e: Exception) -> JSONResponse:
    thread_id = (
        request.thread_id
        if hasattr(request, "thread_id") and request.thread_id
        else "unknown"
    )
    return JSONResponse(
        content={
            "thread_id": thread_id,
            "status": "error",
            "error": str(e),
            "error_type": type(e).__name__,
            "traceback": traceback.format_exc(),
        },
        status_code=500,
    )

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
                    model=load_llm(model="openai/gpt-5.4-mini"),
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
            from agent.v2.prompt.landy_system_prompt import prompt
            from utility.property_listing_init import get_property_listing_collections
            from agent.v2.utility import _serialize_public_listing
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
                    model=load_llm(model="openai/gpt-5.4-mini").bind_tools(tools),
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
    
@app.post("/api/v3/invoke")
async def invoke_v3(request: ChatRequestDict):
    """
    Chat endpoint for property search agent v3.

    Args:
        message:   User's search query
        thread_id: Optional conversation thread ID

    Returns:
        JSON with thread_id, graph_output, agent_referral_shown,
        follow_up_suggestions, recommended_listings, and status
    """
    logger.info(f"Received v3 request: {request}")

    try:
        if not request.message:
            raise HTTPException(status_code=400, detail="Message is required")

        thread_id = _get_thread_id(request)

        await _test_db_connection_async()

        logger.info("Importing v3 agent modules...")
        try:
            from agent.v3.prompt.agent_prompt_v2 import AGENT_PROMPT
            from agent.v3.tools.search_property import asearch_properties
            from agent.v3.tools.newest_listings import aget_newest_listings
            from deepagents import create_deep_agent
            from agent.v3.orchestration import OverallState, adynamic_model_selection, router_model
            from langchain.agents.structured_output import ProviderStrategy
            from utility.property_listing_init import get_property_listing_collections
            from agent.v2.utility import _serialize_public_listing
        except ImportError as e:
            logger.error(f"Import failed: {str(e)}\n{traceback.format_exc()}")
            raise HTTPException(status_code=500, detail=f"Import error: {str(e)}")

        logger.info("Setting up v3 agent...")
        try:
            async with AsyncPostgresSaver.from_conn_string(DB_URI) as checkpointer:
                await checkpointer.setup()

                agent = create_deep_agent(
                    model=router_model,
                    tools=[asearch_properties, aget_newest_listings],
                    middleware=[adynamic_model_selection],
                    system_prompt=AGENT_PROMPT,
                    response_format=ProviderStrategy(OverallState),
                    checkpointer=checkpointer,
                )

                config = {"configurable": {"thread_id": thread_id}}
                response = await agent.ainvoke(
                    {"messages": request.message},
                    config,
                    version="v2",
                )

                structured = response["structured_response"]

                documents = list(
                    get_property_listing_collections().find(
                        {"property_id": {"$in": structured.recommended_listings}}
                    )
                )
                recommended_listings = [_serialize_public_listing(doc) for doc in documents]

                logger.info("V3 agent completed")

        except Exception as e:
            logger.error(f"V3 agent execution error: {str(e)}\n{traceback.format_exc()}")
            raise HTTPException(status_code=500, detail=f"Agent execution error: {str(e)}")

        logger.info(f"Returning v3 response for thread {thread_id}")
        return JSONResponse(
            content={
                "thread_id": thread_id,
                "graph_output": structured.final_output,
                "agent_referral_shown": structured.agent_referral_shown,
                "follow_up_suggestions": structured.follow_up_suggestions,
                "recommended_listings": recommended_listings,
                "status": "success",
            },
            status_code=200,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Unexpected error: {str(e)}\n{traceback.format_exc()}")
        return _build_error_response(request, e)


# ─────────────────────────────────────────
# V4 — shared request model
# ─────────────────────────────────────────
class V4ChatRequest(BaseModel):
    message: str
    thread_id: Optional[str] = None


# ─────────────────────────────────────────
# POST /api/v4/invoke
# ─────────────────────────────────────────
@app.post("/api/v4/invoke")
async def invoke_v4(request: V4ChatRequest):
    if not request.message:
        raise HTTPException(status_code=400, detail="Message is required")

    thread_id = _get_thread_id(request)

    logger.info(f"[v4/invoke] thread={thread_id}")

    try:
        from agent.v4.orchestration import create_agent as create_v4_agent
        from agent.v2.utility import _serialize_public_listing

        async with AsyncPostgresSaver.from_conn_string(DB_URI) as checkpointer:
            await checkpointer.setup()
            agent = create_v4_agent(checkpointer)

            response = await agent.ainvoke(
                {"messages": request.message},
                {"configurable": {"thread_id": thread_id}},
                version="v2",
            )

        structured = response["structured_response"]

        import asyncio as _asyncio
        from utility.property_listing_init import get_property_listing_collections as _get_col

        docs = await _asyncio.to_thread(
            lambda: list(
                _get_col().find({"property_id": {"$in": structured.recommended_property_ids}})
            )
        )
        recommended_listings = [_serialize_public_listing(doc) for doc in docs]

        return JSONResponse(
            content={
                "thread_id": thread_id,
                "graph_output": structured.final_output,
                "agent_referral_shown": structured.agent_referral_shown,
                "follow_up_suggestions": structured.follow_up_suggestions,
                "recommended_listings": recommended_listings,
                "status": "success",
            },
            status_code=200,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[v4/invoke] error: {e}\n{traceback.format_exc()}")
        return _build_error_response(request, e)


# ─────────────────────────────────────────
# V4 SSE helpers
# ─────────────────────────────────────────
def _build_sse_line(payload: dict) -> str:
    return f"data: {json.dumps(payload)}\n\n"


def _extract_property_ids(event: dict) -> list:
    data = event.get("data") or {}
    if not isinstance(data, dict):
        return []
    if data.get("event") != "tool_complete":
        return []
    ids = data.get("ids") or []
    return ids if isinstance(ids, list) else []


# ─────────────────────────────────────────
# POST /api/v4/stream
# ─────────────────────────────────────────
from fastapi.responses import StreamingResponse as _StreamingResponse


@app.post("/api/v4/stream")
async def stream_v4(request: V4ChatRequest):
    if not request.message:
        raise HTTPException(status_code=400, detail="Message is required")

    thread_id = _get_thread_id(request)
    logger.info(f"[v4/stream] thread={thread_id}")

    import asyncio as _asyncio
    from agent.v4.orchestration import create_agent as _create_v4_agent
    from agent.v2.utility import _serialize_public_listing
    from utility.property_listing_init import get_property_listing_collections as _get_col

    async def _event_generator():
        try:
            async with AsyncPostgresSaver.from_conn_string(DB_URI) as checkpointer:
                await checkpointer.setup()
                agent = _create_v4_agent(checkpointer)

                async for raw_event in agent.astream(
                    {"messages": request.message},
                    {"configurable": {"thread_id": thread_id}},
                    stream_mode=["updates", "messages", "custom"],
                    subgraphs=True,
                    version="v2",
                ):
                    # v2 format: (type, ns, data)
                    if not (isinstance(raw_event, tuple) and len(raw_event) == 3):
                        continue
                    type_, ns, data = raw_event
                    event = {"type": type_, "ns": list(ns) if ns else [], "data": data}

                    yield _build_sse_line(event)

                    # Intercept tool_complete to emit property_cards immediately
                    ids = _extract_property_ids(event)
                    if ids:
                        docs = await _asyncio.to_thread(
                            lambda: list(_get_col().find({"property_id": {"$in": ids}}))
                        )
                        listings = [_serialize_public_listing(doc) for doc in docs]
                        cards_event = {
                            "type": "custom",
                            "ns": [],
                            "data": {"event": "property_cards", "listings": listings},
                        }
                        yield _build_sse_line(cards_event)

        except Exception as e:
            logger.error(f"[v4/stream] error: {e}\n{traceback.format_exc()}")
            error_event = {
                "type": "custom",
                "ns": [],
                "data": {"event": "stream_error", "error": str(e)},
            }
            yield _build_sse_line(error_event)

    return _StreamingResponse(
        _event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


# ─────────────────────────────────────────
# POST /api/v5/invoke
# ─────────────────────────────────────────
class V5ChatRequest(BaseModel):
    message: str
    thread_id: Optional[str] = None


@app.post("/api/v5/invoke")
async def invoke_v5(request: V5ChatRequest):
    if not request.message:
        raise HTTPException(status_code=400, detail="Message is required")

    thread_id = _get_thread_id(request)
    logger.info(f"[v5/invoke] thread={thread_id}")

    try:
        from agent.v5.orchestration import create_agent as create_v5_agent

        async with AsyncPostgresSaver.from_conn_string(DB_URI) as checkpointer:
            await checkpointer.setup()
            agent = create_v5_agent(checkpointer)

            response = await agent.ainvoke(
                {"messages": request.message},
                {"configurable": {"thread_id": thread_id}},
                version="v2",
            )

        # model may occasionally skip the structured-output tool call
        try:
            structured = response["structured_response"]
        except KeyError:
            structured = None

        return JSONResponse(
            content={
                "thread_id": thread_id,
                "follow_up_chips": structured.follow_up_chips if structured else [],
                "live_agent_cta": structured.live_agent_cta if structured else False,
                "live_agent_trigger": structured.live_agent_trigger if structured else None,
                "status": "success",
            },
            status_code=200,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[v5/invoke] error: {e}\n{traceback.format_exc()}")
        return _build_error_response(request, e)


# ─────────────────────────────────────────
# POST /api/v5/stream
# ─────────────────────────────────────────
@app.post("/api/v5/stream")
async def stream_v5(request: V5ChatRequest):
    if not request.message:
        raise HTTPException(status_code=400, detail="Message is required")

    thread_id = _get_thread_id(request)
    logger.info(f"[v5/stream] thread={thread_id}")

    from agent.v5.orchestration import create_agent as _create_v5_agent

    def _build_v5_sse_line(payload: dict) -> str:
        # updates/messages payloads contain LangChain message objects
        return f"data: {json.dumps(payload, default=str)}\n\n"

    async def _event_generator():
        try:
            async with AsyncPostgresSaver.from_conn_string(DB_URI) as checkpointer:
                await checkpointer.setup()
                agent = _create_v5_agent(checkpointer)

                structured = None

                async for raw_event in agent.astream(
                    {"messages": request.message},
                    {"configurable": {"thread_id": thread_id}},
                    stream_mode=["updates", "messages", "custom"],
                    subgraphs=True,
                    version="v2",
                ):
                    # langgraph >= 1.1 yields dicts; older versions yield 3-tuples
                    if isinstance(raw_event, dict):
                        type_ = raw_event.get("type")
                        ns = raw_event.get("ns")
                        data = raw_event.get("data")
                    elif isinstance(raw_event, tuple) and len(raw_event) == 3:
                        type_, ns, data = raw_event
                    else:
                        continue

                    # Capture structured response from whichever node emits it
                    if type_ == "updates" and isinstance(data, dict):
                        for node_update in data.values():
                            if isinstance(node_update, dict) and node_update.get("structured_response"):
                                structured = node_update["structured_response"]

                    if type_ == "messages" and isinstance(data, tuple) and data:
                        data = {"content": getattr(data[0], "content", "")}

                    event = {"type": type_, "ns": list(ns) if ns else [], "data": data}
                    yield _build_v5_sse_line(event)

                # After stream: emit follow_up_chips and live_agent_cta
                if structured:
                    if structured.follow_up_chips:
                        yield _build_v5_sse_line({
                            "type": "custom", "ns": [],
                            "data": {"event": "follow_up_chips", "chips": structured.follow_up_chips},
                        })
                    if structured.live_agent_cta:
                        yield _build_v5_sse_line({
                            "type": "custom", "ns": [],
                            "data": {"event": "live_agent_cta", "trigger": structured.live_agent_trigger},
                        })

        except Exception as e:
            logger.error(f"[v5/stream] error: {e}\n{traceback.format_exc()}")
            yield _build_v5_sse_line({
                "type": "custom", "ns": [],
                "data": {"event": "stream_error", "error": str(e)},
            })

    return _StreamingResponse(
        _event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )