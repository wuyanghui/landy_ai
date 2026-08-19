# Agent V6 (KB Q&A) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a new, separate agent (`agent/v6/`) and API endpoints (`POST /api/v6/invoke`, `POST /api/v6/stream`) that answer Selangor industrial planning-guideline questions by reading a bundled copy of the OpenKB wiki, following the same construction/auth/logging/streaming patterns already established by V5.

**Architecture:** Two read-only LangChain tools (`read_wiki_file`, `get_page_content`) read a markdown+JSON snapshot of the OpenKB wiki bundled into the repo at `kb/wiki/`. A `deepagents.create_deep_agent` wraps them with a search-strategy system prompt (read `index.md` → summaries → concept/entity pages → raw source only if needed) and the existing Postgres checkpointer. Two FastAPI routes expose it exactly like V5's `/invoke`/`/stream` pair, reusing V5's existing helper functions, auth, and conversation logging.

**Tech Stack:** FastAPI, LangChain (`@tool`), `deepagents.create_deep_agent`, `langgraph-checkpoint-postgres` (`AsyncPostgresSaver`), existing `utility/llm_init.py` (Vercel AI Gateway), existing `utility/conversation_log.py` (MongoDB), pytest (already a declared dependency, currently unused).

**Spec:** `docs/superpowers/specs/2026-08-19-agent-v6-design.md`

## Global Constraints

- LLM calls go through the existing `utility/llm_init.py` `load_llm()` unchanged — no new LLM client, no new provider config.
- Conversation logging goes through the existing `utility/conversation_log.py` `log_turn()` unchanged, called with `agent_version="v6"`.
- Auth reuses the existing `require_api_secret` FastAPI dependency unchanged — no new auth mechanism.
- Agent construction uses `deepagents.create_deep_agent(model=..., tools=[...], system_prompt=..., checkpointer=...)` — the same call shape as `agent/v5/orchestration.py`, not raw LangGraph.
- Thread continuity uses `AsyncPostgresSaver.from_conn_string(DB_URI)`, reusing the existing `DB_URI` env var — consistent with V3/V4/V5.
- No vector DB, no embeddings, no semantic search layer — pure agentic file reads, matching both OpenKB's own design and V5's stated "no semantic layer" philosophy.
- No image support — the wiki's summary/concept/entity pages contain zero image references (verified); images only appear in raw per-page JSON and total ~5.9GB, not bundleable. Not building `get_kb_image`.
- No follow-up-chip / live-agent-CTA extraction — that concept is V5-specific (transaction intent) and doesn't apply here.

---

## Task 1: KB sync script + initial content sync

**Files:**
- Create: `scripts/__init__.py` (empty)
- Create: `scripts/sync_kb.py`
- Create: `tests/scripts/test_sync_kb.py`
- Create (generated, not hand-written): `kb/wiki/` — the actual synced snapshot

**Interfaces:**
- Produces: `sync_kb(source: Path, dest: Path) -> None` — used only by this task and by future manual re-syncs; no other task imports it.
- Produces: the `kb/wiki/` directory on disk, which Task 2 and Task 3's tools read via `agent.v6.config.KB_ROOT`.

- [ ] **Step 1: Write the failing test**

Create `tests/scripts/test_sync_kb.py`:

```python
from scripts.sync_kb import sync_kb


def test_sync_copies_wiki_excluding_images(tmp_path):
    source = tmp_path / "source_wiki"
    dest = tmp_path / "dest_kb"

    (source / "summaries").mkdir(parents=True)
    (source / "summaries" / "doc.md").write_text("# Summary", encoding="utf-8")
    (source / "sources" / "images" / "doc").mkdir(parents=True)
    (source / "sources" / "images" / "doc" / "p1.png").write_bytes(b"fake-image-data")
    (source / "sources" / "doc.json").write_text("[]", encoding="utf-8")
    (source / "index.md").write_text("# Index", encoding="utf-8")

    sync_kb(source, dest)

    assert (dest / "index.md").read_text(encoding="utf-8") == "# Index"
    assert (dest / "summaries" / "doc.md").exists()
    assert (dest / "sources" / "doc.json").exists()
    assert not (dest / "sources" / "images").exists()


def test_sync_replaces_existing_dest(tmp_path):
    source = tmp_path / "source_wiki"
    dest = tmp_path / "dest_kb"
    source.mkdir()
    (source / "index.md").write_text("new content", encoding="utf-8")

    dest.mkdir()
    (dest / "stale.md").write_text("old file that should be removed", encoding="utf-8")

    sync_kb(source, dest)

    assert (dest / "index.md").read_text(encoding="utf-8") == "new content"
    assert not (dest / "stale.md").exists()


def test_sync_raises_if_source_missing(tmp_path):
    import pytest

    with pytest.raises(FileNotFoundError):
        sync_kb(tmp_path / "does-not-exist", tmp_path / "dest")
```

- [ ] **Step 2: Run test to verify it fails**

Run (from the `landy_ai` repo root): `python -m pytest tests/scripts/test_sync_kb.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'scripts'` (or `scripts.sync_kb`).

- [ ] **Step 3: Write minimal implementation**

Create `scripts/__init__.py` (empty file).

Create `scripts/sync_kb.py`:

```python
#!/usr/bin/env python
"""Sync the OpenKB wiki into landy_ai's kb/wiki/ for the V6 agent.

Copies everything under the OpenKB wiki root except sources/images/ (large,
unused by any V6 tool -- see
docs/superpowers/specs/2026-08-19-agent-v6-design.md). Run manually after
adding/recompiling a document in OpenKB, then commit + redeploy.

Usage:
    python scripts/sync_kb.py [--source PATH]
"""
import argparse
import shutil
from pathlib import Path

DEFAULT_SOURCE = Path(r"C:\Users\Yang Hui\Desktop\projects\openkb\my-kb\wiki")
DEST = Path(__file__).resolve().parent.parent / "kb" / "wiki"


def sync_kb(source: Path, dest: Path) -> None:
    if not source.is_dir():
        raise FileNotFoundError(f"Source wiki not found: {source}")
    if dest.exists():
        shutil.rmtree(dest)
    shutil.copytree(source, dest, ignore=shutil.ignore_patterns("images"))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    args = parser.parse_args()
    sync_kb(args.source, DEST)
    print(f"Synced {args.source} -> {DEST}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/scripts/test_sync_kb.py -v`
Expected: PASS (3 tests).

- [ ] **Step 5: Run the real sync to produce the initial `kb/wiki/` snapshot**

Run: `python scripts/sync_kb.py`
Expected output: `Synced C:\Users\Yang Hui\Desktop\projects\openkb\my-kb\wiki -> <repo>\kb\wiki`

Verify the result is small (no images leaked in):
Run: `python -c "import pathlib; p=pathlib.Path('kb/wiki'); print(sum(f.stat().st_size for f in p.rglob('*') if f.is_file())/1024, 'KB')"`
Expected: roughly 700-800 KB (matches the ~745KB measured for the source wiki minus images). If this prints a number in the hundreds of MB or GB, STOP — the images were not excluded — do not commit.

- [ ] **Step 6: Commit**

```bash
git add scripts/__init__.py scripts/sync_kb.py tests/scripts/test_sync_kb.py kb/wiki
git commit -m "feat(v6): add KB sync script and initial wiki snapshot"
```

---

## Task 2: `read_wiki_file` tool

**Files:**
- Create: `agent/v6/__init__.py` (empty)
- Create: `agent/v6/config.py`
- Create: `agent/v6/tools/__init__.py` (empty)
- Create: `agent/v6/tools/read_wiki_file.py`
- Test: `tests/agent/v6/tools/test_read_wiki_file.py`

**Interfaces:**
- Consumes: nothing from other tasks.
- Produces: `agent.v6.config.KB_ROOT: Path` — an absolute `Path` to `kb/wiki/`, consumed by Task 3's `get_page_content` tool and Task 4's orchestration.
- Produces: `agent.v6.tools.read_wiki_file.read_wiki_file` — a LangChain `@tool`-decorated callable, consumed by Task 4's `create_agent`.

- [ ] **Step 1: Write the failing test**

Create `tests/agent/v6/tools/test_read_wiki_file.py`:

```python
import agent.v6.tools.read_wiki_file as read_wiki_file_module
from agent.v6.tools.read_wiki_file import read_wiki_file


def test_reads_existing_file(tmp_path, monkeypatch):
    (tmp_path / "index.md").write_text("# KB Index", encoding="utf-8")
    monkeypatch.setattr(read_wiki_file_module, "KB_ROOT", tmp_path)

    result = read_wiki_file.invoke({"path": "index.md"})

    assert result == "# KB Index"


def test_reads_nested_file(tmp_path, monkeypatch):
    (tmp_path / "concepts").mkdir()
    (tmp_path / "concepts" / "buffer-zone-requirements.md").write_text(
        "# Buffer Zones", encoding="utf-8"
    )
    monkeypatch.setattr(read_wiki_file_module, "KB_ROOT", tmp_path)

    result = read_wiki_file.invoke({"path": "concepts/buffer-zone-requirements.md"})

    assert result == "# Buffer Zones"


def test_missing_file_returns_message(tmp_path, monkeypatch):
    monkeypatch.setattr(read_wiki_file_module, "KB_ROOT", tmp_path)

    result = read_wiki_file.invoke({"path": "nope.md"})

    assert result == "File not found: nope.md"


def test_path_escape_denied(tmp_path, monkeypatch):
    monkeypatch.setattr(read_wiki_file_module, "KB_ROOT", tmp_path)

    result = read_wiki_file.invoke({"path": "../../etc/passwd"})

    assert result == "Access denied: path escapes wiki root."
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/agent/v6/tools/test_read_wiki_file.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'agent.v6'`.

- [ ] **Step 3: Write minimal implementation**

Create `agent/v6/__init__.py` (empty).

Create `agent/v6/config.py`:

```python
from pathlib import Path

DEFAULT_MODEL = "openai/gpt-5.4-mini"

# Resolves relative to this file's own location so it works both locally
# (repo root as cwd) and on Vercel's Python runtime (whatever cwd it uses).
KB_ROOT = (Path(__file__).resolve().parent.parent.parent / "kb" / "wiki").resolve()
```

Create `agent/v6/tools/__init__.py` (empty).

Create `agent/v6/tools/read_wiki_file.py`:

```python
from langchain_core.tools import tool

from agent.v6.config import KB_ROOT


@tool
def read_wiki_file(path: str) -> str:
    """
    Read a Markdown file from the planning-guideline knowledge base wiki.

    Args:
        path: File path relative to the wiki root, e.g. "index.md",
            "summaries/PEQ-Perindustrian.md", "concepts/buffer-zone-requirements.md".
    """
    full_path = (KB_ROOT / path).resolve()
    if not full_path.is_relative_to(KB_ROOT):
        return "Access denied: path escapes wiki root."
    if not full_path.exists():
        return f"File not found: {path}"
    return full_path.read_text(encoding="utf-8")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/agent/v6/tools/test_read_wiki_file.py -v`
Expected: PASS (4 tests).

- [ ] **Step 5: Sanity-check against the real bundled KB**

Run:
```bash
python -c "
from agent.v6.tools.read_wiki_file import read_wiki_file
print(read_wiki_file.invoke({'path': 'index.md'})[:300])
"
```
Expected: prints the start of the real `index.md` content (document/concept/entity listing) — confirms `KB_ROOT` resolves correctly against the snapshot Task 1 produced.

- [ ] **Step 6: Commit**

```bash
git add agent/v6/__init__.py agent/v6/config.py agent/v6/tools/__init__.py agent/v6/tools/read_wiki_file.py tests/agent/v6/tools/test_read_wiki_file.py
git commit -m "feat(v6): add read_wiki_file tool"
```

---

## Task 3: `get_page_content` tool

**Files:**
- Create: `agent/v6/tools/get_page_content.py`
- Test: `tests/agent/v6/tools/test_get_page_content.py`

**Interfaces:**
- Consumes: `agent.v6.config.KB_ROOT` (Task 2).
- Produces: `agent.v6.tools.get_page_content.get_page_content` — a LangChain `@tool`-decorated callable, consumed by Task 4's `create_agent`.
- Produces: `agent.v6.tools.get_page_content.parse_pages(pages: str) -> list[int]` — a plain function, tested directly, not consumed elsewhere.

- [ ] **Step 1: Write the failing test**

Create `tests/agent/v6/tools/test_get_page_content.py`:

```python
import json

import agent.v6.tools.get_page_content as get_page_content_module
from agent.v6.tools.get_page_content import get_page_content, parse_pages


def test_parse_pages_handles_ranges_and_singles():
    assert parse_pages("3-5,7,10-12") == [3, 4, 5, 7, 10, 11, 12]


def test_parse_pages_dedupes_and_sorts():
    assert parse_pages("5,3,4-5,3") == [3, 4, 5]


def test_returns_matching_page_content(tmp_path, monkeypatch):
    monkeypatch.setattr(get_page_content_module, "KB_ROOT", tmp_path)
    sources_dir = tmp_path / "sources"
    sources_dir.mkdir()
    doc = [
        {"page": 1, "content": "Page one text"},
        {"page": 2, "content": "Page two text"},
        {"page": 3, "content": "Page three text"},
    ]
    (sources_dir / "test-doc.json").write_text(json.dumps(doc), encoding="utf-8")

    result = get_page_content.invoke({"doc_name": "test-doc", "pages": "1,3"})

    assert "Page one text" in result
    assert "Page three text" in result
    assert "Page two text" not in result


def test_missing_document_returns_message(tmp_path, monkeypatch):
    monkeypatch.setattr(get_page_content_module, "KB_ROOT", tmp_path)

    result = get_page_content.invoke({"doc_name": "nope", "pages": "1"})

    assert result == "File not found: sources/nope.json"


def test_no_matching_pages_returns_message(tmp_path, monkeypatch):
    monkeypatch.setattr(get_page_content_module, "KB_ROOT", tmp_path)
    sources_dir = tmp_path / "sources"
    sources_dir.mkdir()
    (sources_dir / "test-doc.json").write_text(
        json.dumps([{"page": 1, "content": "x"}]), encoding="utf-8"
    )

    result = get_page_content.invoke({"doc_name": "test-doc", "pages": "99"})

    assert result == "No content found for pages 99 in test-doc."
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/agent/v6/tools/test_get_page_content.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'agent.v6.tools.get_page_content'`.

- [ ] **Step 3: Write minimal implementation**

Create `agent/v6/tools/get_page_content.py`:

```python
import json

from langchain_core.tools import tool

from agent.v6.config import KB_ROOT


def parse_pages(pages: str) -> list[int]:
    """Parse a page spec like "3-5,7,10-12" into a sorted, deduped list of page numbers."""
    result: set[int] = set()
    for part in pages.split(","):
        part = part.strip()
        if not part:
            continue
        if "-" in part:
            start_str, end_str = part.split("-", 1)
            result.update(range(int(start_str), int(end_str) + 1))
        else:
            result.add(int(part))
    return sorted(result)


@tool
def get_page_content(doc_name: str, pages: str) -> str:
    """
    Get the raw text content of specific pages from a long planning-guideline
    document. Only use this when a summary or concept page doesn't have
    enough detail -- prefer read_wiki_file for summaries/concepts/entities first.

    Args:
        doc_name: Document name without extension, e.g. "PEQ-alam-sekitar".
        pages: Page spec, e.g. "3-5,7,10-12".
    """
    target = (KB_ROOT / "sources" / f"{doc_name}.json").resolve()
    if not target.is_relative_to(KB_ROOT):
        return "Access denied: path escapes wiki root."
    if not target.exists():
        return f"File not found: sources/{doc_name}.json"

    data = json.loads(target.read_text(encoding="utf-8"))
    requested = set(parse_pages(pages))
    matches = [entry for entry in data if entry.get("page") in requested]

    if not matches:
        return f"No content found for pages {pages} in {doc_name}."

    parts = [f"--- Page {entry['page']} ---\n{entry.get('content', '')}" for entry in matches]
    return "\n\n".join(parts)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/agent/v6/tools/test_get_page_content.py -v`
Expected: PASS (5 tests).

- [ ] **Step 5: Sanity-check against the real bundled KB**

Run:
```bash
python -c "
from agent.v6.tools.get_page_content import get_page_content
print(get_page_content.invoke({'doc_name': 'PEQ-Perindustrian', 'pages': '1'}))
"
```
Expected: prints `--- Page 1 ---` followed by the page-1 content of the real `PEQ-Perindustrian.json` (an `![image](...)` markdown reference, since page 1 is a scanned cover page with no text layer — this is expected and fine, V6 just won't be able to view it).

- [ ] **Step 6: Commit**

```bash
git add agent/v6/tools/get_page_content.py tests/agent/v6/tools/test_get_page_content.py
git commit -m "feat(v6): add get_page_content tool"
```

---

## Task 4: Agent prompt + orchestration

**Files:**
- Create: `agent/v6/prompt/__init__.py` (empty)
- Create: `agent/v6/prompt/agent_prompt.py`
- Create: `agent/v6/orchestration.py`
- Test: `tests/agent/v6/test_orchestration.py`

**Interfaces:**
- Consumes: `agent.v6.config.DEFAULT_MODEL` (Task 2), `agent.v6.tools.read_wiki_file.read_wiki_file` (Task 2), `agent.v6.tools.get_page_content.get_page_content` (Task 3), `utility.llm_init.load_llm(model: str) -> ChatOpenAI` (existing).
- Produces: `agent.v6.orchestration.create_agent(checkpointer) -> CompiledGraph` — consumed by Task 5's FastAPI routes.

- [ ] **Step 1: Write the failing test**

Create `tests/agent/v6/test_orchestration.py`:

```python
from unittest.mock import MagicMock

from agent.v6.orchestration import create_agent


def test_create_agent_builds_without_error(monkeypatch):
    monkeypatch.setenv("AI_GATEWAY_API_KEY", "test-key")
    fake_checkpointer = MagicMock()

    agent = create_agent(fake_checkpointer)

    assert agent is not None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/agent/v6/test_orchestration.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'agent.v6.orchestration'`.

- [ ] **Step 3: Write minimal implementation**

Create `agent/v6/prompt/__init__.py` (empty).

Create `agent/v6/prompt/agent_prompt.py`:

```python
AGENT_PROMPT = """You are Landy AI's planning-guidelines assistant. You answer questions \
about industrial property planning regulations in Selangor, Malaysia, by searching a \
knowledge base wiki compiled from official state planning-guideline documents.

## Knowledge base structure

- `index.md` -- lists every document, concept, and entity page in the wiki with a brief description.
- `summaries/{doc}.md` -- one summary per source document, with a `full_text:` frontmatter \
field pointing to the raw source if more detail is needed.
- `concepts/{slug}.md` -- cross-document synthesis of a recurring topic (e.g. buffer-zone \
requirements, worker welfare facilities).
- `entities/{slug}.md` -- a specific named thing (an act, a plan, an agency) referenced across documents.
- `sources/{doc}.json` -- the raw page-by-page text of a document, for when a summary or \
concept page doesn't have enough detail.

## Search strategy

1. Read `index.md` first to see what documents, concepts, and entities exist.
2. Read the relevant summary page(s) for document-level context.
3. Read concept or entity pages when the question spans multiple documents or asks about \
a specific named thing.
4. Only use get_page_content (raw source pages) when the summary and concept pages don't \
have the specific detail asked for -- follow the summary's `full_text:` frontmatter field \
to know which document to pull from, and keep page ranges tight.
5. Synthesize a clear, concise answer grounded in what you actually read. Cite specific \
figures (distances, percentages, standards) exactly as written in the source.

Some source pages are scanned images with no text layer -- if a page's content is just an \
`![image](...)` reference with no other text, you cannot view it; say the specific detail \
isn't available in the readable text rather than guessing.

If the knowledge base doesn't have the answer, say so clearly rather than guessing. Answer \
in the same language the user asked in -- English or Malay.
"""
```

Create `agent/v6/orchestration.py`:

```python
from deepagents import create_deep_agent

from agent.v6.config import DEFAULT_MODEL
from agent.v6.prompt.agent_prompt import AGENT_PROMPT
from agent.v6.tools.get_page_content import get_page_content
from agent.v6.tools.read_wiki_file import read_wiki_file
from utility.llm_init import load_llm


def create_agent(checkpointer):
    return create_deep_agent(
        model=load_llm(DEFAULT_MODEL),
        tools=[read_wiki_file, get_page_content],
        system_prompt=AGENT_PROMPT,
        checkpointer=checkpointer,
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/agent/v6/test_orchestration.py -v`
Expected: PASS (1 test).

- [ ] **Step 5: Run the full V6 test suite together**

Run: `python -m pytest tests/scripts tests/agent/v6 -v`
Expected: all tests from Tasks 1-4 PASS (13 tests total).

- [ ] **Step 6: Commit**

```bash
git add agent/v6/prompt/__init__.py agent/v6/prompt/agent_prompt.py agent/v6/orchestration.py tests/agent/v6/test_orchestration.py
git commit -m "feat(v6): add agent prompt and orchestration"
```

---

## Task 5: FastAPI endpoints (`/api/v6/invoke`, `/api/v6/stream`)

**Files:**
- Modify: `src/index.py` (append after the V5 admin endpoints block, i.e. after the existing `v5_admin_conversation` function at the end of the file)

**Interfaces:**
- Consumes: `agent.v6.orchestration.create_agent(checkpointer)` (Task 4), plus already-existing `src/index.py` helpers: `_get_thread_id`, `_build_error_response`, `_v5_final_answer`, `_v5_message_text`, `AsyncPostgresSaver`, `DB_URI`, `_StreamingResponse`, `logger`, `json`, `traceback`, and `utility.conversation_log.log_turn` (existing).
- Produces: `POST /api/v6/invoke`, `POST /api/v6/stream` — no other task consumes these; they are the final deliverable.

This task has no automated test — it needs a live Postgres connection (`DB_URI`) and a live AI Gateway key, neither of which any existing test in this codebase mocks (no automated test infra covers `/invoke`/`/stream` for V3, V4, or V5 either — this matches established practice, not a gap introduced here). Verification is manual, via a locally running server.

- [ ] **Step 1: Add the V6 request model and routes**

Open `src/index.py`. After the last function in the file (`v5_admin_conversation`, the `/api/v5/admin/conversation` handler), append:

```python
# ─────────────────────────────────────────
# V6 -- KB Q&A agent (Selangor planning guidelines)
# ─────────────────────────────────────────
class V6ChatRequest(BaseModel):
    message: str
    thread_id: Optional[str] = None
    session_id: Optional[str] = None


@app.post("/api/v6/invoke")
async def invoke_v6(request: V6ChatRequest):
    if not request.message:
        raise HTTPException(status_code=400, detail="Message is required")

    thread_id = _get_thread_id(request)
    logger.info(f"[v6/invoke] thread={thread_id}")

    try:
        from agent.v6.orchestration import create_agent as create_v6_agent

        async with AsyncPostgresSaver.from_conn_string(DB_URI) as checkpointer:
            await checkpointer.setup()
            agent = create_v6_agent(checkpointer)

            response = await agent.ainvoke(
                {"messages": request.message},
                {"configurable": {"thread_id": thread_id}, "recursion_limit": 50},
                version="v2",
            )

        output = getattr(response, "value", response)
        answer = _v5_final_answer(output.get("messages") or [])

        import asyncio as _asyncio
        from utility.conversation_log import log_turn

        await _asyncio.to_thread(
            log_turn,
            session_id=request.session_id,
            thread_id=thread_id,
            agent_version="v6",
            user_message=request.message,
            answer=answer,
        )

        return JSONResponse(
            content={"thread_id": thread_id, "answer": answer, "status": "success"},
            status_code=200,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[v6/invoke] error: {e}\n{traceback.format_exc()}")
        return _build_error_response(request, e)


@app.post("/api/v6/stream")
async def stream_v6(request: V6ChatRequest):
    if not request.message:
        raise HTTPException(status_code=400, detail="Message is required")

    thread_id = _get_thread_id(request)
    logger.info(f"[v6/stream] thread={thread_id}")

    from agent.v6.orchestration import create_agent as _create_v6_agent
    from utility.conversation_log import log_turn

    def _build_v6_sse_line(payload: dict) -> str:
        return f"data: {json.dumps(payload, default=str)}\n\n"

    async def _event_generator():
        try:
            yield _build_v6_sse_line({
                "type": "custom", "ns": [],
                "data": {"event": "thread_id", "thread_id": thread_id},
            })

            async with AsyncPostgresSaver.from_conn_string(DB_URI) as checkpointer:
                await checkpointer.setup()
                agent = _create_v6_agent(checkpointer)

                answer_parts: list = []

                async for raw_event in agent.astream(
                    {"messages": request.message},
                    {"configurable": {"thread_id": thread_id}, "recursion_limit": 50},
                    stream_mode=["updates", "messages", "custom"],
                    subgraphs=True,
                    version="v2",
                ):
                    if isinstance(raw_event, dict):
                        type_ = raw_event.get("type")
                        ns = raw_event.get("ns")
                        data = raw_event.get("data")
                    elif isinstance(raw_event, tuple) and len(raw_event) == 3:
                        first, second, data = raw_event
                        if isinstance(first, str):
                            type_, ns = first, second
                        else:
                            ns, type_ = first, second
                    else:
                        continue

                    if type_ not in ("messages", "custom"):
                        continue

                    if type_ == "messages" and isinstance(data, tuple) and data:
                        msg = data[0]
                        mtype = str(getattr(msg, "type", ""))
                        if not (mtype == "ai" or mtype.startswith("AIMessage")):
                            continue
                        content = _v5_message_text(msg)
                        if not content:
                            continue
                        answer_parts.append(content)
                        data = {"content": content}

                    event = {"type": type_, "ns": list(ns) if ns else [], "data": data}
                    yield _build_v6_sse_line(event)

                import asyncio as _asyncio
                await _asyncio.to_thread(
                    log_turn,
                    session_id=request.session_id,
                    thread_id=thread_id,
                    agent_version="v6",
                    user_message=request.message,
                    answer="".join(answer_parts),
                )

        except Exception as e:
            logger.error(f"[v6/stream] error: {e}\n{traceback.format_exc()}")
            yield _build_v6_sse_line({
                "type": "custom", "ns": [],
                "data": {"event": "stream_error", "error": str(e)},
            })

    return _StreamingResponse(
        _event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
```

- [ ] **Step 2: Start the server locally**

Run: `uvicorn src.index:app --reload --port 8000`

Requires `DB_URI` (Postgres) and `AI_GATEWAY_API_KEY` set in `.env` — these already exist in the project's `.env` per the existing V3/V4/V5 endpoints, no new env vars needed.

Expected: server starts without import errors; `GET http://localhost:8000/health` returns `{"status": "ok"}`.

- [ ] **Step 3: Verify `/api/v6/invoke` with a real planning-guideline question**

Run:
```bash
curl -s -X POST http://localhost:8000/api/v6/invoke \
  -H "Content-Type: application/json" \
  -d '{"message": "What is the buffer zone requirement for medium industry near residential areas in Selangor?"}'
```

Expected: JSON response with `"status": "success"` and an `"answer"` field that specifically states the buffer distance for medium industry (150m, per the KB content verified during OpenKB construction) — not a generic non-answer. If `LANDY_API_SECRET` is set in the environment, add `-H "x-landy-key: <the secret>"` to the command.

- [ ] **Step 4: Verify `/api/v6/stream` produces SSE events**

Run:
```bash
curl -s -N -X POST http://localhost:8000/api/v6/stream \
  -H "Content-Type: application/json" \
  -d '{"message": "What are the worker dormitory requirements under Act 446?"}'
```

Expected: a stream of `data: {...}\n\n` lines — first a `thread_id` custom event, then `messages` events carrying answer tokens, ending cleanly (no `stream_error` event) with an answer that references Act 446 / worker housing specifics.

- [ ] **Step 5: Verify multi-turn continuity**

Take the `thread_id` from Step 3's response and send a follow-up on the same thread:

```bash
curl -s -X POST http://localhost:8000/api/v6/invoke \
  -H "Content-Type: application/json" \
  -d '{"message": "What about for light industry instead?", "thread_id": "<thread_id from step 3>"}'
```

Expected: the answer correctly interprets "instead" as still asking about buffer-zone distance (light industry: 50m), showing the Postgres checkpointer preserved conversation context.

- [ ] **Step 6: Verify conversation logging**

Run:
```bash
curl -s "http://localhost:8000/api/v5/admin/conversation?thread_id=<thread_id from step 3>"
```

Expected: returns the logged turns for that thread, each with `user_message` and `answer` populated — confirms V6 turns are landing in the same `landy_conversations` collection via `log_turn(agent_version="v6", ...)`.

- [ ] **Step 7: Commit**

```bash
git add src/index.py
git commit -m "feat(v6): add /api/v6/invoke and /api/v6/stream endpoints"
```

---

## Task 6: Deploy and verify on Vercel

**Files:** none (deployment-only task)

- [ ] **Step 1: Push the branch and deploy**

Push the current branch (or open a PR per the project's normal flow) so Vercel builds a preview deployment. Confirm `kb/wiki/` is present at build time (it's a real committed directory, not gitignored — no `.vercelignore` entry excludes it per the current repo state).

- [ ] **Step 2: Re-run Task 5's Step 3 curl verification against the deployed URL**

```bash
curl -s -X POST https://<preview-url>/api/v6/invoke \
  -H "Content-Type: application/json" \
  -H "x-landy-key: <LANDY_API_SECRET>" \
  -d '{"message": "What is the buffer zone requirement for medium industry near residential areas in Selangor?"}'
```

Expected: same correct, specific answer as the local run. This confirms `agent.v6.config.KB_ROOT`'s path resolution (relative to `__file__`, not a hardcoded local path) works correctly under Vercel's Python runtime, and that `kb/wiki/` was actually included in the deployed bundle.

- [ ] **Step 3: If `KB_ROOT` resolution fails on Vercel**

If Step 2 returns a "File not found" for `index.md` specifically (not a planning-guideline miss, but the tool itself failing), the deployed function's filesystem layout differs from local. Debug by temporarily adding a diagnostic: call `read_wiki_file.invoke({"path": "."})` is not valid (it's a file read, not a listing) -- instead check `agent.v6.config.KB_ROOT` and `KB_ROOT.exists()` via a scratch print in a `GET /health`-adjacent debug path, or check Vercel's function logs for the resolved path. This is a genuine open risk flagged in Task 5's design (see spec's file-structure section) -- not expected to fail, but not verified against a real Vercel Python deployment before this plan was written.
