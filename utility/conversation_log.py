"""Conversation log — stored in MongoDB alongside the other business data
(leads, listings), one document per conversation (thread) with a `turns` array.

Document shape (collection: landy_conversations, _id = thread_id):
    {
        _id: <thread_id>, session_id, agent_version,
        started_at, last_at, cta_fired (set true once any turn fires),
        turns: [{ at, user_message, answer, filters, result_count, cta_fired, cta_trigger }]
    }

This is the queryable lead/analytics record and the easy export surface
(`find()` / mongoexport gives whole conversations). The LangGraph Postgres
checkpointer still owns agent memory separately. All functions are best-effort:
a logging failure must never break a chat turn.
"""
import logging
from datetime import datetime, timezone, timedelta

from utility.property_listing_init import _ensure_client

logger = logging.getLogger(__name__)

_COLLECTION = "landy_conversations"
_indexed = False


def _collection():
    return _ensure_client()["property"][_COLLECTION]


def _ensure_indexes(col) -> None:
    global _indexed
    if _indexed:
        return
    try:
        col.create_index("started_at")
        col.create_index("session_id")
        _indexed = True
    except Exception:  # index creation is best-effort
        pass


def _iso(v):
    return v.isoformat() if hasattr(v, "isoformat") else v


def log_turn(
    *,
    session_id=None,
    thread_id=None,
    agent_version="v5",
    user_message=None,
    filters=None,
    result_count=None,
    answer=None,
    cta_fired=False,
    cta_trigger=None,
) -> None:
    """Append one completed turn to its conversation document (upsert).
    Synchronous — call via asyncio.to_thread. Never raises."""
    if not thread_id:
        return
    try:
        col = _collection()
        _ensure_indexes(col)
        now = datetime.now(timezone.utc)
        turn = {
            "at": now,
            "user_message": user_message,
            "answer": answer,
            "filters": filters,
            "result_count": result_count,
            "cta_fired": bool(cta_fired),
            "cta_trigger": cta_trigger,
        }
        set_fields = {"last_at": now}
        if session_id:
            set_fields["session_id"] = session_id
        if cta_fired:
            set_fields["cta_fired"] = True  # sticky once any turn fires
        col.update_one(
            {"_id": thread_id},
            {
                "$setOnInsert": {"agent_version": agent_version, "started_at": now},
                "$set": set_fields,
                "$push": {"turns": turn},
            },
            upsert=True,
        )
    except Exception as exc:  # logging must never break a chat turn
        logger.error(f"[conversation_log] write failed: {exc}")


# ── analytics reads (admin dashboard) ─────────────────────────────────────────

def get_stats() -> dict:
    empty = {
        "total_turns": 0, "total_conversations": 0, "total_sessions": 0,
        "avg_turns_per_conversation": 0, "zero_result_turns": 0, "cta_turns": 0,
        "by_day": [],
    }
    try:
        col = _collection()
        # metrics cover live v5 data only — legacy imports are browsable but
        # excluded so they don't skew averages/rates
        live = {"legacy": {"$ne": True}}
        total_conversations = col.count_documents(live)

        totals = list(col.aggregate([
            {"$match": live},
            {"$project": {
                "n": {"$size": {"$ifNull": ["$turns", []]}},
                "session_id": 1,
            }},
            {"$group": {
                "_id": None,
                "total_turns": {"$sum": "$n"},
                "sessions": {"$addToSet": "$session_id"},
            }},
        ]))
        total_turns = totals[0]["total_turns"] if totals else 0
        total_sessions = len([s for s in (totals[0]["sessions"] if totals else []) if s])

        per_turn = list(col.aggregate([
            {"$match": live},
            {"$unwind": "$turns"},
            {"$group": {
                "_id": None,
                "zero": {"$sum": {"$cond": [{"$eq": ["$turns.result_count", 0]}, 1, 0]}},
                "cta": {"$sum": {"$cond": ["$turns.cta_fired", 1, 0]}},
            }},
        ]))
        zero = per_turn[0]["zero"] if per_turn else 0
        cta = per_turn[0]["cta"] if per_turn else 0

        cutoff = datetime.now(timezone.utc) - timedelta(days=14)
        by_day = [
            {"day": r["_id"], "turns": r["turns"]}
            for r in col.aggregate([
                {"$match": live},
                {"$unwind": "$turns"},
                {"$match": {"turns.at": {"$gte": cutoff}}},
                {"$group": {
                    "_id": {"$dateToString": {"format": "%Y-%m-%d", "date": "$turns.at"}},
                    "turns": {"$sum": 1},
                }},
                {"$sort": {"_id": 1}},
            ])
        ]

        return {
            "total_turns": total_turns,
            "total_conversations": total_conversations,
            "total_sessions": total_sessions,
            "avg_turns_per_conversation": round(total_turns / total_conversations, 1) if total_conversations else 0,
            "zero_result_turns": zero,
            "cta_turns": cta,
            "by_day": by_day,
        }
    except Exception as exc:
        logger.error(f"[conversation_log] stats failed: {exc}")
        return empty


def get_conversations(limit: int = 50, offset: int = 0) -> list:
    limit = max(1, min(int(limit), 200))
    offset = max(0, int(offset))
    try:
        col = _collection()
        rows = col.aggregate([
            {"$sort": {"started_at": -1}},
            {"$skip": offset},
            {"$limit": limit},
            {"$project": {
                "_id": 0,
                "thread_id": "$_id",
                "session_id": 1,
                "started_at": 1,
                "last_at": 1,
                "turn_count": {"$size": {"$ifNull": ["$turns", []]}},
                "cta_fired": {"$ifNull": ["$cta_fired", False]},
                "legacy": {"$ifNull": ["$legacy", False]},
                "first_message": {"$arrayElemAt": ["$turns.user_message", 0]},
            }},
        ])
        return [{
            **r,
            "started_at": _iso(r.get("started_at")),
            "last_at": _iso(r.get("last_at")),
        } for r in rows]
    except Exception as exc:
        logger.error(f"[conversation_log] list failed: {exc}")
        return []


def get_conversation(thread_id: str) -> list:
    if not thread_id:
        return []
    try:
        doc = _collection().find_one({"_id": thread_id})
        if not doc:
            return []
        return [{
            "created_at": _iso(t.get("at")),
            "user_message": t.get("user_message"),
            "answer": t.get("answer"),
            "result_count": t.get("result_count"),
            "cta_fired": t.get("cta_fired", False),
            "cta_trigger": t.get("cta_trigger"),
            "filters": t.get("filters"),
        } for t in (doc.get("turns") or [])]
    except Exception as exc:
        logger.error(f"[conversation_log] get failed: {exc}")
        return []
