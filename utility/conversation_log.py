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
