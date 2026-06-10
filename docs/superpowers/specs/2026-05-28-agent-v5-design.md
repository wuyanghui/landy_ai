# Agent V5 Design Spec
**Date:** 2026-05-28 (updated 2026-06-10)
**Project:** Landy.ai — Malaysia Industrial Property AI
**Scope:** Clean-slate rebuild of agent tools, orchestration, and retrieval strategy

---

## Why V5

V4's retrieval has a structural failure: when MongoDB Stage 1 returns 0 candidates, Upstash is never called and the agent silently tells the user nothing exists. Location was used as a hard filter instead of a scoped preference. The agent tracked state as a mental JSON block inside the prompt — fragile over long conversations. Tools carried dead weight and imported from v2 utilities.

V5 is a full clean-slate rebuild targeting the new DB schema (schema_version: 1).

---

## Core Design Decisions

### Show first, guide after
The agent always searches and shows results immediately — even on vague first messages. It asks one open guiding question alongside the results. Users who don't know how to interact with AI learn from reacting to results, not from answering structured questions upfront.

### Top 5 with "why" comments
The agent surfaces the 5 best-matched listings with a short comment per listing explaining why it was recommended, anchored to real listing data and the user's stated needs. The LLM reasons over `extracted_key_features`, `investment_highlights`, and `target_buyer_personas` already present in `find_listings` results — no extra tool calls needed for the comments.

### Listing page URL for overflow
When results exceed 5, the agent drops a URL to the listing page with query parameters encoding the active filters. Users explore the full result set on the website. The agent handles discovery; the website handles browsing.

### Reject and refine
When the user rejects the top 5 — ask why (extract new filter signal) and show the next 5 simultaneously. When all results are exhausted, broaden: drop location first, then price range, then category.

### Location is not a hard gate
Location narrows the candidate pool but does not veto the search. If it returns 0 results, the tool reports honestly — the agent broadens rather than failing silently.

### Location matching is alias-based, not regex
The new schema embeds an `aliases` array at every hierarchy level. Matching uses `$in` against aliases — far more reliable than free-text regex. "HICOM" matches `["hicom-glenmarie", "hicom industrial park", ...]`.

### Proximity is a structured filter, not semantic
`location.nearest.highway/port/airport.distance_km` are indexed fields. "Near a highway", "close to Port Klang" are MongoDB Stage 1 filters — not Upstash query strings.

### No semantic layer — LLM reasons over extracted features
Upstash is dropped entirely. The new schema includes `extracted_key_features` (LLM-extracted bullet points per listing), `investment_highlights` (structured investment tags), and `target_buyer_personas` (buyer intent tags). These are included in `find_listings` results. The agent LLM reads them across all candidates and picks the top 5 most relevant — no vector infrastructure needed.

### Reason from data, hand off speculation
Agent can reason about operational fit using real data: highway access, industrial zone maturity, proximity to port. When pushed into investment analysis ("what's the yield?", "will this appreciate?") — the agent doesn't have that data and surfaces the live agent instead of speculating.

### Human-in-the-loop fallback
Tools return what they find and describe it. The agent reads metadata and decides what to ask the user next. No auto-broadening inside tools.

### SSE everything
No final JSON blob. Everything streams as typed events. Frontend renders incrementally.

### Minimal state in LangGraph
Only persist what conversation history genuinely cannot reconstruct. Filters live in history — the LLM reads them reliably. Only `shown_property_ids`, `live_agent_cta_shown`, and `active_filters` (compaction safety) go into LangGraph state.

### Language matching
Agent responds in the same language the user writes in — English, Malay, or mixed. Property names and spec units stay as-is.

### No imports from v2/v3/v4
Every file in `agent/v5/` is self-contained.

---

## New DB Schema (schema_version: 1)

Key field changes from old schema:

| Field | Old path | New path |
|---|---|---|
| City/district | `location.address.address_region` | `location.hierarchy.city.name` |
| City aliases | *(none)* | `location.hierarchy.city.aliases` |
| State | `location.address.address_locality` | `location.hierarchy.state.name` |
| State aliases | *(none)* | `location.hierarchy.state.aliases` |
| Industrial park | `location.industrial_park_name` (string) | `location.hierarchy.industrial_park.name` + `.aliases` |
| Street | `location.address.street_address` | `location.address.street` |
| Built-up area | `built_up_area.value` | `built_up_area_sqft` |
| Land size | `land_size.value` | `land_size_sqft` |
| Ceiling height | `ceiling_height` | `traits.building.ceiling_height_m` |
| Floor loading | `floor_loading` | `traits.industrial.floor_loading_kn_m2` |
| Power supply | `power_supply` (string) | `traits.industrial.power_supply.amps` + `.phase` |
| Tenure | `tenure` (string) | `tenure.type` |
| Currency | `offer.price_currency` | `offer.currency` |

New structured proximity fields:
- `location.nearest.highway/port/airport/mrt_station` — slug, name, distance_km, drive_distance_km
- `location.key_distances.klia`, `port_klang.northport`, `port_klang.westports`

New industrial fields:
- `traits.industrial.loading_bays`, `overhead_crane`, `office_area_sqft`, `yard_area_sqft`
- `traits.building.completion_year`

---

## File Structure

```
agent/v5/
├── config.py
├── state.py
├── orchestration.py
├── prompt/
│   └── agent_prompt.py
└── tools/
    ├── _utils.py              # category expansion + serializers
    ├── find_listings.py       # MongoDB structured filter, returns enriched results for LLM reasoning
    └── get_listing_detail.py  # single full document fetch, designed for parallel calls
```

---

## LangGraph State

```python
class OverallState(TypedDict):
    shown_property_ids: List[str]       # IDs already displayed — prevents re-showing
    live_agent_cta_shown: bool          # CTA fires once per trigger
    active_filters: Dict[str, Any]      # Persisted for context compaction safety
```

---

## Tools

### `find_listings`

**Purpose:** Find active industrial property listings matching structured filters and optional feature keywords.

**Parameters:**

| Parameter | Type | Notes |
|---|---|---|
| `query` | `str` | Qualitative feature keywords only. E.g. "solar panel ready", "cold storage". No location, no numbers. |
| `offer_type` | `"sale" \| "rent" \| None` | Optional. Don't force if user hasn't specified. |
| `property_category` | `List[str] \| None` | Expanded via category map in `_utils.py`. |
| `locality` | `str \| None` | Matched against `location.hierarchy.city.aliases` and `location.hierarchy.industrial_park.aliases` using `$in`. |
| `region` | `str \| None` | Matched against `location.hierarchy.state.aliases` using `$in`. |
| `price_min` | `float \| None` | |
| `price_max` | `float \| None` | |
| `built_up_sqft_min` | `float \| None` | |
| `built_up_sqft_max` | `float \| None` | |
| `land_sqft_min` | `float \| None` | |
| `land_sqft_max` | `float \| None` | |
| `ceiling_height_min` | `float \| None` | `traits.building.ceiling_height_m` lower bound. |
| `floor_loading_min` | `float \| None` | `traits.industrial.floor_loading_kn_m2` lower bound. |
| `max_highway_km` | `float \| None` | Use for "near highway", "highway access". Default 5.0 when implied. |
| `max_port_km` | `float \| None` | Use for "near port", "near Port Klang". Default 30.0 when implied. |
| `max_airport_km` | `float \| None` | Use for "near airport", "near KLIA". Default 20.0 when implied. |
| `sort_by` | `"newest" \| "price_asc" \| "price_desc" \| None` | Ignored if semantic stage runs. |

**MongoDB query**
- Hard filters: `listing_status = "active"`, category (expanded), price, sizes, ceiling height, floor loading, offer_type, proximity
- Location matching (applied as `$or`):
  - `location.hierarchy.city.name` — case-insensitive regex
  - `location.hierarchy.city.aliases` — `$in` (input lowercased)
  - `location.hierarchy.city.slug` — `$in` (input lowercased, spaces → hyphens)
  - `location.hierarchy.industrial_park.name` — case-insensitive regex
  - `location.hierarchy.industrial_park.aliases` — `$in` (input lowercased)
  - `location.hierarchy.industrial_park.slug` — `$in`
  - `location.hierarchy.state.name` — case-insensitive regex (for `region` param)
  - `location.hierarchy.state.aliases` — `$in` (for `region` param)
- No candidate cap — returns all matching documents
- Streams `property_cards` immediately

**Return value:**
```json
{
  "total_found": 12,
  "property_listing_result": [...],
  "filters_applied": "category=factory, locality=Shah Alam, price_max=5000000",
  "location_breakdown": ["Shah Alam", "Bukit Raja"],
  "comment": "12 factories found in Shah Alam under RM5M."
}
```

**SSE events:**
```
search_start   → { filters_active: int }
property_cards → { listings: [...] }
search_complete → { total_found: int, comment: str }
```

---

### `get_listing_detail`

**Purpose:** Fetch full document for a single property. Called in parallel for top 5 listings to provide rich data for "why recommended" comments and comparisons.

**Parameters:**

| Parameter | Type | Notes |
|---|---|---|
| `property_id` | `str` | From search results. |

**Do not call for:** price, size, location — already in search results.

**Returns:** Full property dict or `null` if not found.

**SSE events:**
```
listing_detail_card → { listing: {...} }
```

---

### `_utils.py`

**`expand_property_category(categories)`**
- `"factory"` → `["factory", "cluster-factory", "detached-factory", "semi-d-factory", "terrace-factory"]`
- Other categories return themselves unchanged

**`serialize_listing(doc)`** — for `find_listings` results:
- `property_id`, `title`, `slug`, `thumbnail`
- `offer_type` ← `offer.offer_type`
- `price` ← `offer.price`
- `currency` ← `offer.currency`
- `price_per_sqft` ← `price_per_sqft`
- `city` ← `location.hierarchy.city.name`
- `state` ← `location.hierarchy.state.name`
- `industrial_park` ← `location.hierarchy.industrial_park.name`
- `street` ← `location.address.street`
- `main_category`, `sub_categories`
- `tenure` ← `tenure.type`
- `built_up_sqft` ← `built_up_area_sqft`
- `land_sqft` ← `land_size_sqft`
- `ceiling_height_m` ← `traits.building.ceiling_height_m`
- `floor_loading_kn_m2` ← `traits.industrial.floor_loading_kn_m2`
- `nearest_highway` ← `location.nearest.highway.name + distance_km`
- `listed_date`
- `ai_summary` — one-sentence overview for LLM orientation
- `extracted_key_features` — qualitative feature bullet points for LLM reasoning
- `investment_highlights` — structured investment tags (e.g. "solar-ready", "newly-completed")
- `target_buyer_personas` — intent tags (e.g. "logistics-operators", "ecommerce-fulfillment")

**`serialize_listing_detail(doc)`** — for `get_listing_detail`:
All fields above, plus:
- `description`, `key_features`
- `power_supply` ← `traits.industrial.power_supply.amps + phase`
- `loading_bays` ← `traits.industrial.loading_bays`
- `office_area_sqft` ← `traits.industrial.office_area_sqft`
- `overhead_crane` ← `traits.industrial.overhead_crane`
- `completion_year` ← `traits.building.completion_year`
- `images` ← `images[]`
- `nearest` ← `location.nearest` (highway, port, airport, mrt)
- `key_distances` ← `location.key_distances`
- `similar_listing_id`

---

## Agent Behaviour

### Opening message
Brief, friendly. States regions covered (Klang Valley, Selangor, KL, Negeri Sembilan) and property types available. Gives 2-3 example queries. Does not show listings — nothing to show yet.

### First message handling
Always search immediately. Show top 5 with "why recommended" comments. Ask one open question: *"Do any of these look close to what you need, or what are you after?"*

Exception: if first search returns 0 results, broaden silently once (drop location). If still 0, surface live agent immediately.

### Top 5 recommendation comments
- Generated from enrichment fields already in `find_listings` results: `extracted_key_features`, `investment_highlights`, `target_buyer_personas`, `ai_summary`
- Anchored to user's stated needs vs real listing data — no hallucination
- Skipped when user has stated no requirements yet (first broad search)
- `get_listing_detail` called only when user asks for deeper detail on a specific listing

### Overflow URL
When `total_found > 5`, append a listing page URL encoding active filters:
```
https://www.industrialprop.com.my/api/listings?category=factory&location=Shah+Alam&max_price=5000000
```
Note: `ceiling_height` parameter in URL is in **feet** — convert from `ceiling_height_m` before constructing URL (1m = 3.281ft).

### Refinement loop
- User rejects top 5 → ask why + show next 5 simultaneously
- Filters change → always re-call `find_listings` (never filter in-memory)
- Sort/compare/describe existing results → use conversation context + `shown_property_ids`
- All results exhausted → broaden: drop location first, then price range, then category

### Live agent CTA
Emitted as `live_agent_cta` SSE event. Fires once per trigger, agent continues helping regardless.

**Triggers:**
1. Transact intent — viewing, offer, negotiation
2. Hyper-specific requirement the AI can't match from data
3. No match after all broadening attempts exhausted
4. Investment analysis beyond what listing data supports ("yield?", "will this appreciate?")
5. Context window full — agent cannot maintain conversation reliably

### Language
Respond in the same language the user writes in. Property names, spec units, and URLs stay in their original form.

### Off-topic
Hard boundary. Redirect to industrial property search. Do not engage with unrelated topics.

### Conversation reset
*"Start over"* / *"Forget everything"* → clear `shown_property_ids` and `active_filters` from LangGraph state, restart fresh.

### Property comparison
Call `get_listing_detail` in parallel for both properties. Present as structured side-by-side comparison in text stream.

### Follow-up chips
2-3 short action strings emitted as `follow_up_chips` SSE event after every response.
Format: *"Factories in Shah Alam under RM3M"*, *"Show me bigger options"*, *"Speak to our agent"* (from turn 3 onward).

---

## SSE Output Events

```
text_chunk          → streaming text words
property_cards      → { listings: [...] }   (find_listings results)
listing_detail_card → { listing: {...} }    (get_listing_detail result)
follow_up_chips     → { chips: ["...", "..."] }
live_agent_cta      → { trigger: str }
search_complete     → { total_found: int }
```

No final JSON blob. Frontend assembles UI entirely from the event stream.

---

## What Is Dropped from V4

| V4 | V5 | Reason |
|---|---|---|
| `search_properties` | Renamed `find_listings` | Clearer agent tool selection |
| `property_detail` | Renamed `get_listing_detail` | Clearer agent tool selection |
| `properties_by_radius.py` | Dropped | Proximity filters in `find_listings` cover this |
| `newest_listings.py` | Dropped | Covered by `sort_by="newest"` in `find_listings` |
| Imports from `agent.v2.utility` | Dropped | Self-contained `_utils.py` |
| Hard-gate on Stage 1 zero results | Dropped | Honest return + agent broadens |
| 100-candidate cap | Dropped | Returns all matching documents |
| Free-text regex on location | Dropped | Alias-based `$in` matching |
| "Near highway/port" as semantic query | Dropped | Structured proximity filters |
| Prompt-level JSON state block | Dropped | LangGraph state + conversation history |
| Silent auto-broadening inside tools | Dropped | Agent-level broadening with human-in-the-loop |
| Final JSON blob output | Dropped | Full SSE event stream |
