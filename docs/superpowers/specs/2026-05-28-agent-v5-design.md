# Agent V5 Design Spec
**Date:** 2026-05-28
**Project:** Landy.ai — Malaysia Industrial Property AI
**Scope:** Clean-slate rebuild of agent tools and retrieval strategy

---

## Why V5

V4's retrieval has a structural failure: when MongoDB Stage 1 returns 0 candidates, Upstash is never called and the agent silently tells the user nothing exists. Location was used as a hard filter instead of a scoped preference, which means a wrong locality match kills the entire search. The tools also carry dead weight (radius search, newest listings as a separate tool) and import from v2 utilities.

V5 drops all of that and starts clean.

---

## Core Design Decisions

### Location is not a hard gate
Location narrows the candidate pool but does not veto the search. If it returns 0 results, the tool reports that honestly — the **agent** asks the user whether to broaden, not the tool. Human-in-the-loop handles fallback.

### Semantic search is for qualitative features
Upstash is not a re-ranker bolted on top. It surfaces description-level requirements that structured fields cannot capture: "solar panel ready", "cold storage", "ramp access", "near highway". If the user has no feature keywords, semantic stage is skipped.

### No internal fallback logic
Tools return what they find and describe it. The agent reads the metadata and decides what to ask the user next. Tools do not auto-broaden, auto-retry, or guess intent.

### SSE streaming for perceived performance
MongoDB results (~100ms) stream immediately as `property_cards`. If semantic runs, re-ranked results stream as `property_cards_reranked`. The user sees listings appear fast; re-ordering happens silently.

### Upstash handles embedding server-side
`data=query` — no pre-embedding step, no OpenAI dependency. Cold starts handled separately via cron warmup job (free tier).

### No imports from v2/v3/v4
Every file in `agent/v5/` is self-contained. No shared utilities from prior versions.

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
    ├── _utils.py              # category expansion + shared property serializer
    ├── search_properties.py   # two-stage hybrid: MongoDB filter + Upstash semantic
    └── property_detail.py     # single property full detail fetch
```

---

## Tools

### `search_properties`

**Purpose:** Find active industrial properties matching structured filters and optional feature keywords.

**Parameters:**

| Parameter | Type | Notes |
|---|---|---|
| `query` | `str` | Feature keywords only — things not in structured fields. Empty = skip semantic stage. |
| `offer_type` | `"sale" \| "rent" \| None` | Optional. Don't force if user hasn't specified. |
| `property_category` | `List[str] \| None` | Expanded via category map in `_utils.py`. |
| `locality` | `str \| None` | City/district. LLM normalises abbreviations ("PJ" → "Petaling Jaya") before calling. |
| `region` | `str \| None` | State. Examples: "Selangor", "Kuala Lumpur". |
| `price_min` | `float \| None` | `offer.price` lower bound. |
| `price_max` | `float \| None` | `offer.price` upper bound. |
| `built_up_sqft_min` | `float \| None` | |
| `built_up_sqft_max` | `float \| None` | |
| `land_sqft_min` | `float \| None` | |
| `land_sqft_max` | `float \| None` | |
| `ceiling_height_min` | `float \| None` | |
| `floor_loading_min` | `float \| None` | |
| `sort_by` | `"newest" \| "price_asc" \| "price_desc" \| None` | Applied to Stage 1 results. Ignored if semantic stage runs — Upstash ranking takes precedence. |

**Stage 1 — MongoDB**
- Hard filters: `listing_status = "active"`, category, price, sizes, ceiling height, floor loading, offer_type
- Location filter (`locality`, `region`) applied as case-insensitive regex if provided — honest 0 if no match
- Returns up to 100 candidate IDs
- Streams `property_cards` event immediately with serialized listings

**Stage 2 — Upstash**
- Only runs when `query.strip()` is non-empty
- Filters: `listing_status = "active" AND property_id IN (candidate_ids)`
- `data=query` — Upstash handles embedding server-side
- `top_k` based on candidate pool size (max 100)
- Deduplicates by `property_id`
- Streams `property_cards_reranked` event with re-ordered listings
- On Upstash failure: silently keeps Stage 1 order, no error raised

**Return value:**
```json
{
  "total_found": 12,
  "property_listing_result": [...],
  "stage": "mongodb+semantic",
  "filters_applied": "category=factory, locality=Shah Alam, price_max=5000000",
  "location_breakdown": ["Shah Alam", "Bukit Raja"],
  "comment": "12 factories found in Shah Alam under RM5M. 8 re-ranked by cold storage relevance."
}
```

**SSE events:**
```
search_start           → { filters_active: int, has_semantic_query: bool }
property_cards         → { listings: [...], stage: "mongodb" }
property_cards_reranked → { listings: [...], stage: "semantic" }
search_complete        → { total_found: int, comment: str }
```

---

### `property_detail`

**Purpose:** Fetch full detail for a single property when the user asks about something not in search results — description, key features, loading bays, construction year, full specifications.

**Parameters:**

| Parameter | Type | Notes |
|---|---|---|
| `property_id` | `str` | From search results. |

**Behaviour:**
- Single MongoDB `find_one` by `property_id`
- Returns full serialized document using v5's own serializer (no v2 imports)
- Streams `property_detail_card` event

**Do not call for:** price, size, location — already in search results.

**Return value:** Full property dict, or `null` if not found.

**SSE events:**
```
property_detail_start  → { property_id: str }
property_detail_card   → { listing: {...} }
```

---

### `_utils.py`

**`expand_property_category(categories)`**
Maps user-facing category names to full variant sets:
- `"factory"` → `["factory", "cluster-factory", "detached-factory", "semi-d-factory", "terrace-factory"]`
- Other categories return themselves unchanged

**`serialize_property(doc)`**
Shared serializer used by both tools. Extracts: `property_id`, `title`, `slug`, `offer_type`, `price`, `price_currency`, `locality`, `region`, `full_address`, `main_category`, `sub_categories`, `tenure`, `built_up_sqft`, `land_sqft`, `ceiling_height`, `floor_loading`, `listed_date`.

**`serialize_property_detail(doc)`**
Extended serializer for `property_detail` — adds: `description`, `key_features`, `power_supply`, `loading_bays`, `office_area`, `construction_year`, `similar_listing_id`.

---

## Agent Responsibilities (not tool responsibilities)

- If `total_found = 0` and `locality` was set → ask user if they want to broaden location
- If `total_found` is thin (< 3) → present results, ask if user wants to expand scope
- If semantic ran but re-ranking didn't change much → no need to mention it
- `offer_type` — don't force a choice. Surface both sale and rent options if unspecified, let user gravitate toward affordability

---

## What Is Dropped from V4

| V4 | V5 | Reason |
|---|---|---|
| `properties_by_radius.py` | Dropped | LLM knows Malaysian geography; "near X" handled by locality filter |
| `newest_listings.py` | Dropped | Covered by `sort_by="newest"` in `search_properties` |
| Import from `agent.v2.utility` | Dropped | Self-contained serializer in `_utils.py` |
| Hard-gate on Stage 1 zero results | Dropped | Honest return + agent handles fallback |
| Auto-broadening fallback | Dropped | Human-in-the-loop |
