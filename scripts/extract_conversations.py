"""One-off salvage: dump readable conversations from the existing LangGraph
checkpoints (the 319 threads already in Postgres) to a JSONL file.

This reads the checkpoint tables directly — it's a best-effort export of
history that predates the conversation_turns log. Going forward, query
conversation_turns instead (clean, purpose-built).

Usage:
    python scripts/extract_conversations.py [output.jsonl]

Requires DB_URI in the environment / .env.
"""
import asyncio
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv

load_dotenv()

DB_URI = os.environ.get("DB_URI")


def _msg_to_dict(msg):
    """Best-effort flatten of a LangChain message to {role, text}."""
    role = getattr(msg, "type", None) or msg.__class__.__name__
    content = getattr(msg, "content", "")
    if isinstance(content, list):
        content = "".join(
            b.get("text", "") if isinstance(b, dict) else str(b) for b in content
        )
    return {"role": role, "text": content}


async def main(out_path: str) -> None:
    if not DB_URI:
        print("DB_URI not set; aborting.")
        return

    from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
    import psycopg

    # distinct thread_ids, newest activity first
    with psycopg.connect(DB_URI, connect_timeout=15) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT DISTINCT thread_id FROM checkpoints")
            thread_ids = [r[0] for r in cur.fetchall()]

    print(f"Found {len(thread_ids)} threads. Extracting messages...")

    written = 0
    skipped = 0
    async with AsyncPostgresSaver.from_conn_string(DB_URI) as cp:
        with open(out_path, "w", encoding="utf-8") as f:
            for tid in thread_ids:
                config = {"configurable": {"thread_id": tid}}
                try:
                    tup = await cp.aget_tuple(config)
                except Exception as exc:
                    print(f"  skip {tid[:20]}: {exc}")
                    skipped += 1
                    continue
                if not tup or not tup.checkpoint:
                    skipped += 1
                    continue
                messages = (tup.checkpoint.get("channel_values") or {}).get("messages") or []
                turns = [_msg_to_dict(m) for m in messages]
                # drop empty / test-noise threads with no real text
                if not any(t["text"] for t in turns):
                    skipped += 1
                    continue
                f.write(json.dumps({"thread_id": tid, "messages": turns}, ensure_ascii=False) + "\n")
                written += 1

    print(f"Done. Wrote {written} conversations, skipped {skipped}. -> {out_path}")


if __name__ == "__main__":
    out = sys.argv[1] if len(sys.argv) > 1 else "conversations_export.jsonl"
    # async psycopg needs the selector loop on Windows (not the default proactor)
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(main(out))
