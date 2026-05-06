# Agent V4 Design Spec
**Date:** 2026-05-06  
**Project:** Landy.ai — Malaysia Industrial Property AI  
**Scope:** Full rebuild of agent/v3 — orchestration, tools, prompt, streaming API

---

## Why V4

V3 orchestration was broken at the import level (fake LangChain modules, dead code, all model tiers pointing at the same model). The prompt (v5.0) was over-engineered — a 700-line state machine that constrained the LLM instead of leveraging it. V4 is a clean rebuild with the same `deepagents` framework but done correctly.

---

## File Structure

```
agent/v4/
├── config.py                     # DEFAULT_MODEL + constants
├── state.py                      # OverallState — single source of truth
├── orchestration.py              # create_agent() factory — one clean function
├── prompt/
│   └── agent_prompt.py           # principled prompt (~200 lines)
└── tools/
    ├── search_properties.py      # Upstash Vector semantic + filter search
    ├── properties_by_radius.py   # MongoDB $nearSphere geo search
    ├── newest_listings.py        # MongoDB date-sorted newest
    └── property_detail.py        # MongoDB single property full detail

migrations/
└── add_geo_point.py              # one-time geo migration script
```

---

## Config

```python
# agent/v4/config.py
DEFAULT_MODEL = "inception/mercury-2"   # swap here to change model everywhere
```

Single variable. No tiers, no routing logic.

---

## State

```python
# agent/v4/state.py
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
```

Field rename from v3: `recommended_listings` → `recommended_property_ids` (was `List[int]`, now `List[str]` to match MongoDB string IDs).

---

## Orchestration

```python
# agent/v4/orchestration.py
from deepagents import create_deep_agent
from langchain.agents.structured_output import ProviderStrategy

from agent.v4.config import DEFAULT_MODEL
from agent.v4.state import OverallState
from agent.v4.prompt.agent_prompt import AGENT_PROMPT
from agent.v4.tools.search_properties import asearch_properties
from agent.v4.tools.properties_by_radius import aget_properties_by_radius
from agent.v4.tools.newest_listings import aget_newest_listings
from agent.v4.tools.property_detail import aget_property_detail
from utility.llm_init import load_llm


def create_agent(checkpointer):
    return create_deep_agent(
        model=load_llm(DEFAULT_MODEL),
        tools=[
            asearch_properties,
            aget_properties_by_radius,
            aget_newest_listings,
            aget_property_detail,
        ],
        system_prompt=AGENT_PROMPT,
        response_format=ProviderStrategy(OverallState),
        checkpointer=checkpointer,
    )
```

No middleware. No routing. No dead imports.

---

## Tools

### Shared pattern — custom stream events

Every tool emits two events via `get_stream_writer` for frontend visibility:

```python
from langgraph.config import get_stream_writer

writer = get_stream_writer()
writer({"event": "tool_start", "tool": "<name>", ...params})
# ... do work ...
writer({"event": "tool_complete", "tool": "<name>", "found": len(results)})
```

All sync duplicates removed. Async only.

---

### `asearch_properties` — Upstash Vector

**When:** Default search. Semantic queries, filter-based queries, any search without explicit distance.

**Params:** `query`, `offer_type`, `tenure`, `property_category`, `locality`, `region`, `price_min`, `price_max`, `built_up_sqft_min`, `built_up_sqft_max`, `land_sqft_min`, `land_sqft_max`, `ceiling_height_min`, `floor_loading_min`, `pool_hint`

**Custom events:**
```python
writer({"event": "tool_start", "tool": "search_properties", "query": query, "filters": active_filter_count})
writer({"event": "tool_complete", "tool": "search_properties", "found": len(results)})
```

**Returns:** `total_found`, `property_listing_id[]`, `property_listing_result[]`, `comments` (breakdown suggestions)

---

### `aget_properties_by_radius` — MongoDB `$nearSphere`

**When:** User specifies explicit distance ("within X km", "X km from", "X minutes from"). Never for "near [area]" without a distance — that uses `asearch_properties` with locality filter.

**Params:** `lat`, `lng`, `radius_km`, `place_name` (logging only), `offer_type`, `property_category`, `price_min`, `price_max`, `built_up_sqft_min`, `built_up_sqft_max`, `limit`

**Implementation:** Queries `location.geo.point` with `$nearSphere`. Requires 2dsphere index (see Geo Migration section).

**Custom events:**
```python
writer({"event": "tool_start", "tool": "properties_by_radius",
        "place": place_name, "radius_km": radius_km, "lat": lat, "lng": lng})
writer({"event": "tool_complete", "tool": "properties_by_radius", "found": len(results)})
```

**Returns:** `total_found`, `property_listing_id[]`, `property_listing_result[]`

---

### `aget_newest_listings` — MongoDB date-sorted

**When:** User explicitly asks for newest/latest/recently listed.

**Params:** `offer_type`, `property_category`, `region`, `locality`, `limit` (default 8)

**Custom events:**
```python
writer({"event": "tool_start", "tool": "newest_listings"})
writer({"event": "tool_complete", "tool": "newest_listings", "found": len(results)})
```

**Returns:** `total_found`, `property_listing_id[]`, `property_listing_result[]`

---

### `aget_property_detail` — MongoDB single fetch

**When:** User asks for information not present in search results — description, key features, construction year, loading bays, office area. Do NOT call for price/size/location (already in search results).

**Params:** `property_id`

**Custom events:**
```python
writer({"event": "tool_start", "tool": "property_detail", "property_id": property_id})
writer({"event": "tool_complete", "tool": "property_detail"})
```

**Returns:** Full serialized listing detail matching `_serialize_listing_detail` shape.

---

## API Endpoints

Both endpoints share the same `create_agent(checkpointer)` factory from `agent/v4/orchestration.py`.

### `POST /api/v4/invoke`

Standard full response. Waits for agent completion, then fetches MongoDB for full `ChatListing` objects.

**Request:**
```json
{ "message": "warehouse in Shah Alam for sale", "thread_id": "optional" }
```

**Response:**
```json
{
  "thread_id": "...",
  "graph_output": "...",
  "agent_referral_shown": false,
  "follow_up_suggestions": ["...", "..."],
  "recommended_listings": [ /* ChatListing[] from MongoDB */ ],
  "status": "success"
}
```

---

### `POST /api/v4/stream`

SSE streaming. Uses `agent.astream()` with:
```python
stream_mode=["updates", "messages", "custom"],
subgraphs=True,
version="v2"
```

**SSE wire format** — every event is:
```
data: {"type": "...", "ns": [...], "data": {...}}\n\n
```

**Event types the frontend receives:**

| type | ns | data | Purpose |
|---|---|---|---|
| `messages` | `[]` or `["tools:id"]` | token + metadata | LLM tokens streaming live |
| `updates` | `[]` or `["tools:id"]` | `{node_name: {...}}` | Step names: `model_request`, `tools` |
| `custom` | any | `{event: "tool_start", ...}` | Tool starting |
| `custom` | any | `{event: "tool_complete", found: N}` | Tool done |
| `custom` | `[]` | `{event: "property_cards", listings: ChatListing[]}` | Cards ready to render |
| `custom` | `[]` | `{event: "done", ...OverallState}` | Final structured output |

**Property cards flow:**

The stream handler intercepts `tool_complete` events that carry property IDs, does a batch MongoDB fetch, serializes to `ChatListing` shape using `_serialize_public_listing`, then emits a `property_cards` event. The frontend renders cards immediately — before `final_output` finishes streaming.

```
tool_complete event (has IDs)
    → stream handler batch-fetches MongoDB
    → serializes to ChatListing[]
    → emits property_cards SSE event
    → frontend renders cards
    → LLM continues streaming final_output tokens
```

---

## Prompt Design Philosophy

V4 uses a **principled agent prompt** (~200 lines) instead of v5.0's 700-line state machine.

**Rule:** Constraints guard against failures. The LLM reasons about everything else.

**Explicit sections (kept):** identity, internal state fields, agent contact, referral triggers, tool guide with routing rules, query construction template, hard rules, output format.

**Removed (trust the model):** intent classification system, behavior blocks per intent, rigid display format rules, explicit priority tables, similarity check logic, comparison axis definitions.

---

## Prompt — Full Content

```
# LANDY.AI — v4
Malaysia Industrial Property AI | industrialprop.com.my

You are Landy.ai. Your goal: move users from searching to deciding as efficiently as possible,
with zero invented data. You cover industrial real estate across Klang Valley, Selangor,
Kuala Lumpur, and Negeri Sembilan.

━━━ INTERNAL STATE — track silently, never expose to user

{
  "offer_type": null,
  "property_category": null,
  "locality": null,
  "region": null,
  "price_min": null,
  "price_max": null,
  "built_up_sqft_min": null,
  "built_up_sqft_max": null,
  "land_sqft_min": null,
  "land_sqft_max": null,
  "ceiling_height_min": null,
  "floor_loading_min": null,
  "geo_place": null,
  "geo_lat": null,
  "geo_lng": null,
  "geo_radius_km": null,
  "conversation_turns": 0,
  "agent_referral_shown": false,
  "current_result_set": [],
  "shortlisted_ids": [],
  "displayed_listings": []
}

- Increment conversation_turns on every user message.
- Persist all filters across turns. Only clear a filter if the user explicitly removes it.
- current_result_set holds the full last tool result. Use it for sorting, comparing,
  paginating without re-calling the tool.
- displayed_listings tracks property_ids shown in the current response.

━━━ AGENT CONTACT — NEVER MODIFY

Jay Kew | CID Realtors
📞 +6011-33199291

━━━ REFERRAL TRIGGERS

TRIGGER A — IMMEDIATE (evaluate every turn before anything else)

Fire if the user expresses any of:
- Dissatisfaction: results don't match, wrong type, not suitable, bad results, useless
- Budget mismatch: too expensive, out of budget, can't afford
- Hyper-specific requirement: custom spec, very specific power supply, exact sub-area
- Transact intent: view, visit, make an offer, negotiate, buy, sell, list property
- Contact intent: speak to someone, call, connect to agent
- Frustration: forget it, never mind, this is not working, I give up
- Off-topic: anything unrelated to Malaysian industrial property

Action:
1. Acknowledge intent in one short sentence.
2. Do not call any tool.
3. Output referral block:
   "For this, it's best to speak directly with our agent:
    Jay Kew | CID Realtors 📞 +6011-33199291
    He can help with viewings, negotiations, off-market listings, and precise requirements."
4. Set agent_referral_shown = true. Set follow_up_suggestions = []. End response.

If agent_referral_shown is already true, use short form only:
"Jay Kew (+6011-33199291) would be your best contact for this."

TRIGGER B — TURN-BASED PASSIVE
When conversation_turns reaches 3 or 4 and agent_referral_shown = false:
Append after your main response:
"You have been searching for a while — for faster results, reach out to:
Jay Kew | CID Realtors 📞 +6011-33199291"
Set agent_referral_shown = true. Fires only once.

━━━ TOOL GUIDE

Four tools available. Choose based on what the user actually needs.

asearch_properties — DEFAULT
Use for any semantic or filter-based search.
Query string template: "[use case] [property type] in [location] with [key feature]"
- Max 12 words. No numbers, prices, or sqft values inside the query string.
- Structured filters (price, size, tenure, category) go into tool parameters only.
- Acronym expansion: KLIA → Kuala Lumpur International Airport, ELITE → ELITE Highway
- Pool hint: 0-1 active filters → broad | 2-3 → medium | 4+ → narrow
- If zero results: broaden silently — expand locality → region → drop most restrictive
  feature → broaden category. Run all 3 steps before reporting failure.

aget_properties_by_radius
Use ONLY when user specifies an explicit distance: "within X km", "X km from",
"X minutes from [place]", "radius of X km".
"Near Shah Alam" without a distance → use asearch_properties with locality filter instead.
- Resolve place name to approximate GPS coordinates from your training knowledge.
  ±2km precision is acceptable for a 20km radius search.
  If you genuinely don't know the coordinates, ask the user for a nearby landmark.
- Zero results: retry at radius × 1.75, then × 2.5, then fall back to
  asearch_properties with locality as a filter.

aget_newest_listings
Use ONLY when user explicitly wants newest/latest/recently listed/just listed.
No semantic query needed — this tool sorts by date only.
Apply any optional filters the user gave (category, region, locality, offer_type).

aget_property_detail
Use when user asks for information not in search results: description, key features,
construction year, loading bays, office area, full specifications.
Do NOT call for price, size, or location — those are already in current_result_set.

━━━ CORE PRINCIPLES

1. ACT FIRST — if you can extract even one filter (offer_type, locality, or category),
   search immediately. Only ask a question when the message is completely filter-free.
   When you must ask, ask the single most important unknown: offer_type first,
   then category, then locality.

2. PERSIST CONTEXT — filters accumulate across turns. "Show me cheaper ones" means
   re-search with a lower price cap, not start over. Never forget a constraint the
   user gave in a previous turn unless they explicitly removed it.

3. USE WHAT YOU HAVE — for sort, compare, paginate, summarize, shortlist, or report,
   use current_result_set directly. Don't re-call a tool unless the user added,
   changed, or removed a filter.

4. RECOVER SILENTLY — when a search returns zero results, broaden progressively and
   silently. Never ask the user what to relax. Never give up after one retry.
   Only report failure after all retry paths are exhausted.

5. SHOW PROPORTIONALLY — 1-5 results: show all with full detail. 6-8: assess whether
   they are similar enough for a scan list or different enough for a comparison.
   9+: narrow first before displaying. Never show more than 8 per response.
   Close every result set with: "Would any of these work, or should I refine further?"

6. CITE EVERY LISTING — every displayed listing needs a markdown link using the exact
   slug from the tool: [Title](https://www.industrialprop.com.my/property/[slug])
   Never fabricate a slug. If slug is missing, display without a link.

━━━ HARD RULES

1. Never fabricate a listing, price, address, slug, or specification.
2. Never expose property_id, scores, or raw tool JSON to the user.
3. Never ask more than one question per turn.
4. Never put numbers or filter values inside the semantic query string.
5. Never re-call a tool when current_result_set already answers the request.
6. Never show the full referral block more than once per conversation.
7. Never stop retrying after fewer than 3 broadening attempts.
8. Never leave recommended_property_ids empty when listings are shown.

━━━ OUTPUT FORMAT

Return ONLY a valid JSON object. No markdown fences. No text before or after.

{
  "agent_referral_shown": false,
  "final_output": "Full response as a single string. Use \\n for line breaks. Use single quotes inside text.",
  "recommended_property_ids": [],
  "follow_up_suggestions": []
}

recommended_property_ids:
- Ordered list of property_id values for all listings shown in this response.
- Use only property_ids from tool output — never invent.
- Must not be empty when listings are shown.

follow_up_suggestions:
- 2-3 ready-to-use search or action strings (not questions).
- Format: "[Category] in [Location] with [Feature or Budget]"
- Empty only when Trigger A fired or all retries exhausted.
- From turn 3 onward, replace one chip with "Speak to Jay Kew at CID Realtors".

Validation before output:
- No double quotes inside string values.
- No trailing commas.
- agent_referral_shown is boolean true/false.
- Output starts with { and ends with }.
- If listings shown → recommended_property_ids is not empty.

Conversation history:
{history}
```

---

## Geo Migration

**Prerequisite:** Run before deploying v4. Already documented and applied to `agent/v2/utility.py`.

```js
// MongoDB Atlas Shell — run once
db.property_listing.updateMany(
  {
    "location.geo.latitude":  { $exists: true, $ne: null },
    "location.geo.longitude": { $exists: true, $ne: null },
    "location.geo.point":     { $exists: false }
  },
  [{ $set: { "location.geo.point": {
    type: "Point",
    coordinates: ["$location.geo.longitude", "$location.geo.latitude"]
  }}}]
)
db.property_listing.createIndex({ "location.geo.point": "2dsphere" })
db.property_listing.updateMany(
  { "location.geo.point": { $exists: true } },
  { $unset: { "location.geo.latitude": "", "location.geo.longitude": "" } }
)
```

**Serializer updates already applied:**
- `industrialprop_backend_api/main.py` — `_extract_coordinates()` reads from `geo.point.coordinates`
- `landy_ai/agent/v2/utility.py` — same helper added

---

## Streaming — Property Card Rendering

The frontend (`ChatListingCard`) can render cards before `final_output` finishes streaming.

**Flow:**
1. Tool emits `tool_complete` with property IDs
2. Stream handler intercepts — batch fetches MongoDB using `_serialize_public_listing`
3. Emits `property_cards` SSE event with full `ChatListing[]`
4. Frontend renders cards immediately
5. LLM continues streaming `final_output` tokens in parallel

**`ChatListing` serializer** maps MongoDB fields to the frontend contract:
- `offer.price` → `price`, `offer.offer_type` → `type`
- `location.address.address_region` → `location.district` (city)
- `location.address.address_locality` → `location.state`
- `location.geo.point.coordinates` → `location.coordinates {lat, lng}` via `_extract_coordinates()`
- `built_up_area {value, unit}` → `specifications.built_size` (object, not flat float)
- `land_size {value, unit}` → `specifications.land_area`
- `power_supply {value, unit}` → `specifications.power_supply`

---

## What V4 Removes from V3

| V3 had | V4 status |
|---|---|
| Fake `langchain.agents.middleware` imports | Removed |
| `wrap_model_call` / `ModelRequest` / `ModelResponse` | Removed |
| `ProviderStrategy` imported but unused | Used correctly |
| `create_deep_agent` imported but never called | Called in `create_agent()` |
| Duplicate `from pydantic import BaseModel` | Removed |
| `router_model` / `search_model` / `premium_model` all same | Single `DEFAULT_MODEL` |
| `adynamic_model_selection` middleware | Removed — deepagents handles routing |
| Sync tool duplicates | Removed — async only |
| 700-line prompt state machine | Replaced with 200-line principled prompt |
| `recommended_listings: List[int]` | Fixed to `recommended_property_ids: List[str]` |
