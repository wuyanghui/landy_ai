"""Backfill the salvaged historical conversations (conversations_export.jsonl)
into the landy_conversations MongoDB collection, tagged legacy=True.

Legacy docs are browsable in the admin dashboard but excluded from the
headline metrics (see get_stats), so pre-v5 data doesn't skew avg turns /
CTA-rate / zero-result numbers. Idempotent: existing thread docs are never
overwritten (uses $setOnInsert).

Usage:
    python scripts/backfill_conversations.py [conversations_export.jsonl]
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv

load_dotenv()

from utility.property_listing_init import _ensure_client

COLLECTION = "landy_conversations"


def _result_count_from_tool(text: str):
    try:
        return json.loads(text).get("total_found")
    except Exception:
        return None


def _reconstruct_turns(messages: list) -> list:
    """Walk role/text messages into {user_message, answer, result_count} turns."""
    turns = []
    cur_user = None
    cur_results = None

    def flush(answer):
        turns.append({
            "at": None,
            "user_message": cur_user,
            "answer": answer,
            "filters": None,
            "result_count": cur_results,
            "cta_fired": False,
            "cta_trigger": None,
        })

    for m in messages:
        role = m.get("role")
        text = (m.get("text") or "")
        if role == "human":
            if cur_user is not None:
                flush(None)  # previous user turn had no answer
            cur_user = text
            cur_results = None
        elif role == "tool":
            rc = _result_count_from_tool(text)
            if rc is not None:
                cur_results = rc
        elif role == "ai" and text.strip():
            flush(text)
            cur_user = None
            cur_results = None
    if cur_user is not None:
        flush(None)
    return turns


def main(path: str) -> None:
    src = Path(path)
    if not src.exists():
        print(f"Export not found: {path}. Run scripts/extract_conversations.py first.")
        return

    col = _ensure_client()["property"][COLLECTION]

    inserted = 0
    skipped_existing = 0
    skipped_empty = 0
    with src.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            rec = json.loads(line)
            tid = rec.get("thread_id")
            turns = _reconstruct_turns(rec.get("messages") or [])
            if not tid or not any(t["user_message"] for t in turns):
                skipped_empty += 1
                continue
            res = col.update_one(
                {"_id": tid},
                {"$setOnInsert": {
                    "legacy": True,
                    "agent_version": "legacy",
                    "session_id": None,
                    "started_at": None,
                    "last_at": None,
                    "cta_fired": False,
                    "turns": turns,
                }},
                upsert=True,
            )
            if res.upserted_id is not None:
                inserted += 1
            else:
                skipped_existing += 1

    print(f"Done. Inserted {inserted} legacy conversations, "
          f"skipped {skipped_existing} already-present, {skipped_empty} empty.")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "conversations_export.jsonl")
