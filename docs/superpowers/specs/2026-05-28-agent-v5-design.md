# Agent V5 Design Spec
**Date:** 2026-05-28 (updated 2026-06-09)
**Project:** Landy.ai — Malaysia Industrial Property AI
**Scope:** Clean-slate rebuild of agent tools and retrieval strategy

---

## Why V5

V4's retrieval has a structural failure: when MongoDB Stage 1 returns 0 candidates, Upstash is never called and the agent silently tells the user nothing exists. Location was used as a hard filter instead of a scoped preference, which means a wrong locality match kills the entire search. The tools also carry dead weight (radius search, newest listings as a separate tool) and import from v2 utilities.

V5 drops all of that and starts clean. It also targets the new DB schema (schema_version: 1) introduced in the June 2026 migration.

---

## Core Design Decisions

### Location is not a hard gate
Location narrows the candidate pool but does not veto the search. If it returns 0 results, the tool reports that honestly — the **agent** asks the user whether to broaden, not the tool. Human-in-the-loop handles fallback.

### Location matching is alias-based, not regex
The new schema embeds an `aliases` array at every hierarchy level inside each listing document. Matching uses `$in` against `aliases` — far more reliable than free-text regex. "HICOM" → `$in ["hicom-glenmarie", "hicom industrial park", ...]`. The agent normalises abbreviations before calling the tool; the tool matches against structured aliases.

### Proximity is a structured filter, not semantic
`location.nearest.highway.distance_km`, `location.nearest.port.distance_km`, and `location.nearest.airport.distance_km` are indexed fields. "Near a highway", "close to Port Klang", "near airport" are MongoDB Stage 1 filters — they do not belong in the Upstash `query` string.

### Semantic search is for qualitative features
Upstash surfaces description-level requirements that no structured field captures: "solar panel ready", "cold storage", "ramp access", "raised floor". If the user has no feature keywords, semantic stage is skipped entirely.

### No internal fallback logic
Tools return what they find and describe it. The agent reads the metadata and decides what to ask the user next. Tools do not auto-broaden, auto-retry, or guess intent.

### SSE streaming for perceived performance
MongoDB results (~100ms) stream immediately as `property_cards`. If semantic runs, re-ranked results stream as `property_cards_reranked`. The user sees listings appear fast; re-ordering happens silently.

### Upstash handles embedding server-side
`data=query` — no pre-embedding step, no OpenAI dependency. Cold starts handled separately via cron warmup job (free tier).

### No imports from v2/v3/v4
Every file in `agent/v5/` is self-contained. No shared utilities from prior versions.

---

## New DB Schema (schema_version: 1)

Key field changes from old schema that v5 tools must use:

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

New structured proximity fields (no old equivalent):
- `location.nearest.highway.slug / name / distance_km / drive_distance_km`
- `location.nearest.port.slug / name / distance_km / drive_distance_km`
- `location.nearest.airport.slug / name / distance_km / drive_distance_km`
- `location.nearest.mrt_station.slug / name / distance_km`
- `location.key_distances.klia.drive_distance_km`
- `location.key_distances.port_klang.northport.drive_distance_km`

New industrial fields:
- `traits.industrial.loading_bays`
- `traits.industrial.overhead_crane`
- `traits.industrial.office_area_sqft`
- `traits.industrial.yard_area_sqft`
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
| `query` | `str` | Qualitative feature keywords only — things no structured field captures. E.g. "solar panel ready", "cold storage", "raised floor". Do NOT put location or proximity here. |
| `offer_type` | `"sale" \| "rent" \| None` | Optional. Don't force if user hasn't specified. |
| `property_category` | `List[str] \| None` | Expanded via category map in `_utils.py`. |
| `locality` | `str \| None` | City/district name or alias slug. Matched against `location.hierarchy.city.aliases` and `location.hierarchy.industrial_park.aliases` using `$in`. |
| `region` | `str \| None` | State name. Matched against `location.hierarchy.state.aliases` using `$in`. |
| `price_min` | `float \| None` | `offer.price` lower bound. |
| `price_max` | `float \| None` | `offer.price` upper bound. |
| `built_up_sqft_min` | `float \| None` | `built_up_area_sqft` lower bound. |
| `built_up_sqft_max` | `float \| None` | `built_up_area_sqft` upper bound. |
| `land_sqft_min` | `float \| None` | `land_size_sqft` lower bound. |
| `land_sqft_max` | `float \| None` | `land_size_sqft` upper bound. |
| `ceiling_height_min` | `float \| None` | `traits.building.ceiling_height_m` lower bound. |
| `floor_loading_min` | `float \| None` | `traits.industrial.floor_loading_kn_m2` lower bound. |
| `max_highway_km` | `float \| None` | `location.nearest.highway.distance_km` upper bound. Use when user says "near highway", "highway access", "near expressway". |
| `max_port_km` | `float \| None` | `location.nearest.port.distance_km` upper bound. Use when user says "near port", "near Port Klang". |
| `max_airport_km` | `float \| None` | `location.nearest.airport.distance_km` upper bound. Use when user says "near airport", "near KLIA", "near Subang airport". |
| `sort_by` | `"newest" \| "price_asc" \| "price_desc" \| None` | Applied to Stage 1 results. Ignored if semantic stage runs — Upstash ranking takes precedence. |

**Stage 1 — MongoDB**
- Hard filters: `listing_status = "active"`, category (expanded), price, built-up, land, ceiling height, floor loading, offer_type, proximity (highway/port/airport km)
- Location matching:
  - `locality` → `$or` across `location.hierarchy.city.aliases`, `location.hierarchy.industrial_park.aliases`, `location.hierarchy.suburb.aliases` using `$in` (normalised to lowercase)
  - `region` → `location.hierarchy.state.aliases` using `$in`
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
search_start            → { filters_active: int, has_semantic_query: bool }
property_cards          → { listings: [...], stage: "mongodb" }
property_cards_reranked → { listings: [...], stage: "semantic" }
search_complete         → { total_found: int, comment: str }
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
property_detail_start → { property_id: str }
property_detail_card  → { listing: {...} }
```

---

### `_utils.py`

**`expand_property_category(categories)`**
Maps user-facing category names to full variant sets:
- `"factory"` → `["factory", "cluster-factory", "detached-factory", "semi-d-factory", "terrace-factory"]`
- Other categories return themselves unchanged

**`serialize_property(doc)`**
Shared serializer for search results. New schema field paths:
- `property_id`, `title`, `slug`
- `offer_type` ← `offer.offer_type`
- `price` ← `offer.price`
- `currency` ← `offer.currency`
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

**`serialize_property_detail(doc)`**
Extended serializer for `property_detail` — adds:
- `description`, `key_features`
- `power_supply` ← `traits.industrial.power_supply.amps` + `phase`
- `loading_bays` ← `traits.industrial.loading_bays`
- `office_area_sqft` ← `traits.industrial.office_area_sqft`
- `overhead_crane` ← `traits.industrial.overhead_crane`
- `completion_year` ← `traits.building.completion_year`
- `nearest_highway/port/airport` ← `location.nearest.*`
- `key_distances` ← `location.key_distances`
- `similar_listing_id`

---

## Agent Responsibilities (not tool responsibilities)

- If `total_found = 0` and `locality` was set → ask user if they want to broaden location
- If `total_found` is thin (< 3) → present results, ask if user wants to expand scope
- If semantic ran but re-ranking didn't change much → no need to mention it
- `offer_type` — don't force a choice. Surface both sale and rent options if unspecified, let user gravitate toward affordability
- Proximity thresholds: when user says "near highway" without a distance, default `max_highway_km=5.0`; "near port" → `max_port_km=30.0`; "near airport" → `max_airport_km=20.0`

---

## What Is Dropped from V4

| V4 | V5 | Reason |
|---|---|---|
| `properties_by_radius.py` | Dropped | LLM knows Malaysian geography; "near X" handled by locality + proximity filters |
| `newest_listings.py` | Dropped | Covered by `sort_by="newest"` in `search_properties` |
| Import from `agent.v2.utility` | Dropped | Self-contained serializer in `_utils.py` |
| Hard-gate on Stage 1 zero results | Dropped | Honest return + agent handles fallback |
| Auto-broadening fallback | Dropped | Human-in-the-loop |
| Free-text regex on location fields | Dropped | Alias-based `$in` matching — more reliable |
| "Near highway/port" as semantic query | Dropped | Structured proximity filters in Stage 1 |
