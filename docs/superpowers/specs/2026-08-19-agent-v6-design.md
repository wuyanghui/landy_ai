# Agent V6 Design Spec
**Date:** 2026-08-19
**Project:** Landy.ai — Malaysia Industrial Property AI
**Scope:** New read-only Q&A agent over the Selangor industrial planning-guideline wiki (built separately with OpenKB), exposed as its own versioned endpoint.

---

## Why V6

V1–V5 all answer one kind of question: "what listings match X." None of them can answer "can I legally do X on this land" — buffer-zone distances, worker-housing rules, data-centre siting requirements, plot-ratio standards, and the rest of the regulatory content already compiled into an OpenKB wiki (6 Selangor state planning-guideline PDFs, indexed into cross-linked summaries/concepts/entities markdown at `c:\Users\Yang Hui\Desktop\projects\openkb\my-kb\wiki\`).

V6 is a separate agent and a separate endpoint, not a tool bolted onto V5. The two knowledge domains (property listings vs. planning regulation) have independent retrieval strategies and independent content sources; keeping them apart keeps each simple. They can be merged into one agent later if that's ever wanted — nothing here forecloses it.

---

## Core Design Decisions

**Bundled markdown, no vector DB.** The wiki is copied into the `landy_ai` repo as read-only files. This mirrors both OpenKB's own retrieval design (no embeddings — an agent reads `index.md`, follows wikilinks to summaries and concept/entity pages) and V5's stated "no semantic layer" philosophy (an LLM reasoning over already-extracted content beats vector infrastructure for this scale of corpus — 6 documents, ~20 concepts, ~31 entities).

**Same agentic search strategy as OpenKB's own query agent.** Read `index.md` for the document/concept map → read relevant summary pages → read concept/entity pages for cross-document synthesis → only drop into raw page-range content for long (PageIndex) documents when the summary isn't enough. Ported directly from `openkb/agent/query.py`'s `_QUERY_INSTRUCTIONS_TEMPLATE`.

**`deepagents.create_deep_agent`, not raw LangGraph.** Matches V5's construction pattern exactly (`agent/v5/orchestration.py`) — model, tools, system prompt, checkpointer, nothing more.

**LLM via the existing `utility/llm_init.py` `load_llm()`.** Already wired to Vercel AI Gateway (`AI_GATEWAY_API_KEY`, `https://ai-gateway.vercel.sh/v1`). No new LLM client, no new provider config.

**Postgres checkpointer for thread continuity**, consistent with V3/V4/V5 (`AsyncPostgresSaver.from_conn_string(DB_URI)`, reusing the existing `DB_URI`). Enables multi-turn follow-ups ("what about light industry instead of medium?") without new infrastructure.

**SSE streaming**, same framing as V4/V5 (`_build_sse_line`-style JSON-per-line, `text/event-stream`). No JSON-blob-only mode.

**Conversation logging via the existing `utility/conversation_log.py` `log_turn()`.** Called with `agent_version="v6"`; the property-specific fields (`filters`, `result_count`, `cta_fired`, `cta_trigger`) are simply omitted (all already optional with safe defaults) — no schema change needed. V6 conversations show up in the same `landy_conversations` collection and admin endpoints as V5's.

**No follow-up-chip / live-agent-CTA extraction step.** V5's `extract_v5_state` is built around *transaction* intent (view a property, talk to an agent) — that concept doesn't apply to a regulatory question. V6 returns plain answer text. (Follow-up suggestion chips for KB Q&A specifically could be a real future improvement — not building it now; flagging so it isn't mistaken for an oversight.)

**No image support.** Verified against the actual generated wiki: `summaries/`, `concepts/`, `entities/`, and `index.md` contain zero image references — every `![image](...)` reference lives only in `wiki/sources/*.json` (the raw per-page PageIndex content `get_page_content` reads as a fallback), and those referenced images total ~5.9GB across 508 files (median ~11MB each, full-resolution PDF page renders). That's not bundleable into a repo/deployment, and since images never appear in the primary summary/concept/entity search path, dropping them costs nothing for typical Q&A — only the rare raw-page-content fallback would ever surface one, and V6 simply doesn't support that case. Revisit as a separately-scoped addition (real object storage, not bundling) if it turns out to matter in practice.

---

## KB Content Bundling

```
kb/
└── wiki/                # synced copy of my-kb/wiki/ EXCLUDING sources/images/ (index.md, summaries/, concepts/, entities/, sources/*.json)
```

A sync script (`scripts/sync_kb.py`) copies `wiki/` from the OpenKB project path into `landy_ai/kb/wiki/`, excluding `sources/images/` (see "No image support" above — those files are ~5.9GB and unused by any V6 tool). Run manually after adding/recompiling a document in OpenKB, then commit + redeploy — the KB updates infrequently enough (this round was 6 documents over several days) that this is not a burdensome workflow.

---

## File Structure

```
agent/v6/
├── config.py                  # DEFAULT_MODEL, KB_ROOT path constant
├── orchestration.py           # create_agent(checkpointer)
├── prompt/
│   └── agent_prompt.py        # ported from OpenKB's query-agent search-strategy prompt
└── tools/
    ├── read_wiki_file.py       # read a markdown file from kb/wiki/
    └── get_page_content.py     # page-range content from kb/wiki/sources/*.json (PageIndex docs)

kb/
└── wiki/

scripts/
└── sync_kb.py
```

---

## Tools

### `read_wiki_file`

**Purpose:** Read a markdown file from the bundled KB wiki — `index.md`, a summary page, a concept page, or an entity page.

**Parameters:**

| Parameter | Type | Notes |
|---|---|---|
| `path` | `str` | Relative to `kb/wiki/`, e.g. `"summaries/PEQ-Perindustrian.md"`, `"concepts/buffer-zone-requirements.md"` |

**Returns:** File contents as a string, or `"File not found: {path}"` if missing. Path is resolved and checked to stay inside `kb/wiki/` — an escaping path returns `"Access denied: path escapes wiki root."` rather than reading outside the KB. Mirrors OpenKB's own `read_wiki_file` contract exactly.

### `get_page_content`

**Purpose:** Fetch specific pages of a long (PageIndex-indexed) document by page range, for documents whose full text lives in `kb/wiki/sources/{doc_name}.json`.

**Parameters:**

| Parameter | Type | Notes |
|---|---|---|
| `doc_name` | `str` | Document name without extension, e.g. `"PEQ-alam-sekitar"` |
| `pages` | `str` | Page spec, e.g. `"3-5,7,10-12"` |

**Returns:** Formatted content for the requested pages, or an error string (`"No content found for pages {pages} in {doc_name}."` / `"File not found: sources/{doc_name}.json"`). Page content may itself contain an `![image](...)` markdown reference for a scanned page with no text layer — V6 has no tool to resolve these (see "No image support"); the agent works with whatever text is present and does not attempt to view the image.

---

## API Endpoints

### `POST /api/v6/invoke`

**Request** (mirrors `V5ChatRequest`):
```json
{ "message": "string", "thread_id": "string | null", "session_id": "string | null" }
```

**Response:**
```json
{ "thread_id": "string", "answer": "string", "status": "success" }
```
No `follow_up_chips` / `live_agent_cta` — not applicable to regulatory Q&A (see Core Design Decisions).

### `POST /api/v6/stream`

SSE, same line framing as V5 (`data: {json}\n\n`). Events:
- `{"type": "custom", "data": {"event": "thread_id", "thread_id": ...}}` — announced first, same as V5
- `{"type": "messages", "data": {"content": "..."}}` — answer tokens
- `{"type": "custom", "data": {"event": "stream_error", "error": ...}}`

After the stream completes, dual-writes to the conversation log via `log_turn(agent_version="v6", ...)`, same best-effort/non-blocking pattern V5 uses.

---

## Error Handling

- Missing `message` → `400`, existing pattern (`HTTPException`).
- Auth → existing `require_api_secret` dependency, unchanged — no new auth surface.
- Tool reads a missing file or a path that escapes `kb/wiki/` → graceful string return (see `read_wiki_file` above); the agent says it doesn't have that information rather than the request erroring.
- LLM/AI Gateway errors → `_build_error_response`, the same helper V3/V4/V5 already use.
- Turn-count cap to prevent runaway tool-call loops (OpenKB's own query agent caps at 50 turns — V6 should use a comparable bound; exact number is an implementation detail).

---

## Testing / Validation

- Manual: `curl` against `/api/v6/invoke` with real planning-guideline questions (buffer-zone distances, worker-housing rules, data-centre siting, plot-ratio standards) and confirm the answer cites the specific facts already verified during KB construction (e.g. the 50m/150m/300m buffer distances for light/medium/heavy industry).
- No existing automated test setup was found in `landy_ai` during exploration (no `tests/` directory, no pytest config beyond a stray `.pytest_cache`) — whether to add automated coverage for V6 is an implementation-time decision, not assumed here.

---

## Open Questions (carried into implementation, not blocking this spec)

1. **Follow-up suggestion chips for KB Q&A** — explicitly out of scope now (YAGNI), noted as a plausible future addition.

## Amendment (2026-08-19)

Image support (`get_kb_image`, `kb/images/`) was dropped after checking the actual generated wiki content — see "No image support" under Core Design Decisions. The original version of this spec included image handling based on an unverified assumption about how much image data was involved; the real figure (~5.9GB) made bundling infeasible, and since images never appear in the primary search path, the feature was cut rather than reached for external storage infrastructure outside this spec's scope.
