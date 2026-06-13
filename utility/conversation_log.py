"""Clean, queryable conversation log — dual-written alongside the LangGraph
checkpointer. The checkpointer owns agent memory (serialized state); this owns
the analytics/lead record (normal columns we control).

Lives in the same Postgres as the checkpointer (DB_URI). Best-effort: a logging
failure must never break a chat turn — callers should still wrap, and every
write here swallows its own errors.
"""
import os
import json
import logging

import psycopg

logger = logging.getLogger(__name__)

_DB_URI = os.environ.get("DB_URI")
_table_ready = False

_CREATE_SQL = """
CREATE TABLE IF NOT EXISTS conversation_turns (
    id            BIGSERIAL PRIMARY KEY,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    session_id    TEXT,
    thread_id     TEXT,
    agent_version TEXT,
    user_message  TEXT,
    filters       JSONB,
    result_count  INTEGER,
    answer        TEXT,
    cta_fired     BOOLEAN,
    cta_trigger   TEXT
);
CREATE INDEX IF NOT EXISTS idx_conv_turns_created ON conversation_turns (created_at DESC);
CREATE INDEX IF NOT EXISTS idx_conv_turns_session ON conversation_turns (session_id);
CREATE INDEX IF NOT EXISTS idx_conv_turns_zero ON conversation_turns (result_count) WHERE result_count = 0;
"""


def _ensure_table(conn) -> None:
    global _table_ready
    if _table_ready:
        return
    with conn.cursor() as cur:
        cur.execute(_CREATE_SQL)
    conn.commit()
    _table_ready = True


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
    """Insert one completed chat turn. Synchronous — call via asyncio.to_thread.
    Never raises; logs and returns on any failure."""
    if not _DB_URI:
        return
    try:
        with psycopg.connect(_DB_URI, connect_timeout=10) as conn:
            _ensure_table(conn)
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO conversation_turns
                        (session_id, thread_id, agent_version, user_message,
                         filters, result_count, answer, cta_fired, cta_trigger)
                    VALUES (%s, %s, %s, %s, %s::jsonb, %s, %s, %s, %s)
                    """,
                    (
                        session_id,
                        thread_id,
                        agent_version,
                        user_message,
                        json.dumps(filters) if filters is not None else None,
                        result_count,
                        answer,
                        cta_fired,
                        cta_trigger,
                    ),
                )
            conn.commit()
    except Exception as exc:  # logging must never break a chat turn
        logger.error(f"[conversation_log] write failed: {exc}")


# ── analytics reads (admin dashboard) ─────────────────────────────────────────

def _iso(v):
    return v.isoformat() if hasattr(v, "isoformat") else v


def get_stats() -> dict:
    """Aggregate metrics for the admin dashboard."""
    empty = {
        "total_turns": 0, "total_conversations": 0, "total_sessions": 0,
        "avg_turns_per_conversation": 0, "zero_result_turns": 0, "cta_turns": 0,
        "by_day": [],
    }
    if not _DB_URI:
        return empty
    try:
        with psycopg.connect(_DB_URI, connect_timeout=10) as conn:
            _ensure_table(conn)
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT count(*),
                           count(DISTINCT thread_id),
                           count(DISTINCT session_id) FILTER (WHERE session_id IS NOT NULL),
                           count(*) FILTER (WHERE result_count = 0),
                           count(*) FILTER (WHERE cta_fired)
                    FROM conversation_turns
                """)
                turns, convos, sessions, zero, cta = cur.fetchone()
                cur.execute("""
                    SELECT date_trunc('day', created_at)::date AS d, count(*)
                    FROM conversation_turns
                    WHERE created_at > now() - interval '14 days'
                    GROUP BY d ORDER BY d
                """)
                by_day = [{"day": str(d), "turns": c} for d, c in cur.fetchall()]
        return {
            "total_turns": turns or 0,
            "total_conversations": convos or 0,
            "total_sessions": sessions or 0,
            "avg_turns_per_conversation": round((turns or 0) / convos, 1) if convos else 0,
            "zero_result_turns": zero or 0,
            "cta_turns": cta or 0,
            "by_day": by_day,
        }
    except Exception as exc:
        logger.error(f"[conversation_log] stats failed: {exc}")
        return empty


def get_conversations(limit: int = 50, offset: int = 0) -> list:
    """One row per conversation (thread), newest first."""
    if not _DB_URI:
        return []
    limit = max(1, min(int(limit), 200))
    offset = max(0, int(offset))
    try:
        with psycopg.connect(_DB_URI, connect_timeout=10) as conn:
            _ensure_table(conn)
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT thread_id,
                           max(session_id)            AS session_id,
                           min(created_at)            AS started_at,
                           max(created_at)            AS last_at,
                           count(*)                   AS turn_count,
                           bool_or(cta_fired)         AS any_cta,
                           (array_agg(user_message ORDER BY created_at))[1] AS first_message
                    FROM conversation_turns
                    GROUP BY thread_id
                    ORDER BY started_at DESC
                    LIMIT %s OFFSET %s
                """, (limit, offset))
                rows = cur.fetchall()
        return [{
            "thread_id": r[0], "session_id": r[1],
            "started_at": _iso(r[2]), "last_at": _iso(r[3]),
            "turn_count": r[4], "cta_fired": r[5], "first_message": r[6],
        } for r in rows]
    except Exception as exc:
        logger.error(f"[conversation_log] list failed: {exc}")
        return []


def get_conversation(thread_id: str) -> list:
    """All turns for one conversation, oldest first."""
    if not _DB_URI or not thread_id:
        return []
    try:
        with psycopg.connect(_DB_URI, connect_timeout=10) as conn:
            _ensure_table(conn)
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT created_at, user_message, answer, result_count,
                           cta_fired, cta_trigger, filters
                    FROM conversation_turns
                    WHERE thread_id = %s
                    ORDER BY created_at
                """, (thread_id,))
                rows = cur.fetchall()
        return [{
            "created_at": _iso(r[0]), "user_message": r[1], "answer": r[2],
            "result_count": r[3], "cta_fired": r[4], "cta_trigger": r[5], "filters": r[6],
        } for r in rows]
    except Exception as exc:
        logger.error(f"[conversation_log] get failed: {exc}")
        return []
