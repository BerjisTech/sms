"""SQLite-backed message queue and send log.

A single connection guarded by a lock keeps things simple and safe for
the single-process FastAPI server plus its background worker.
"""

from __future__ import annotations

import sqlite3
import threading
from datetime import datetime, timezone
from typing import Any, Optional

_conn: Optional[sqlite3.Connection] = None
_lock = threading.Lock()


SCHEMA = """
CREATE TABLE IF NOT EXISTS messages (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    recipient   TEXT    NOT NULL,
    body        TEXT    NOT NULL,
    status      TEXT    NOT NULL DEFAULT 'queued',  -- queued|sent|failed
    gateway_id  TEXT,
    error       TEXT,
    attempts    INTEGER NOT NULL DEFAULT 0,
    created_at  TEXT    NOT NULL,
    sent_at     TEXT
);

CREATE INDEX IF NOT EXISTS idx_messages_status ON messages(status);
CREATE INDEX IF NOT EXISTS idx_messages_sent_at ON messages(sent_at);

CREATE TABLE IF NOT EXISTS send_log (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    message_id  INTEGER,
    recipient   TEXT,
    status      TEXT,
    error       TEXT,
    timestamp   TEXT    NOT NULL
);
"""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def init_db(db_path: str) -> None:
    global _conn
    with _lock:
        _conn = sqlite3.connect(db_path, check_same_thread=False)
        _conn.row_factory = sqlite3.Row
        _conn.executescript(SCHEMA)
        _conn.commit()


def close_db() -> None:
    global _conn
    with _lock:
        if _conn is not None:
            _conn.close()
            _conn = None


def _db() -> sqlite3.Connection:
    if _conn is None:
        raise RuntimeError("Database not initialized; call init_db() first.")
    return _conn


def enqueue(recipient: str, body: str) -> int:
    """Add a message to the queue, returning its id."""
    with _lock:
        cur = _db().execute(
            "INSERT INTO messages (recipient, body, status, created_at) "
            "VALUES (?, ?, 'queued', ?)",
            (recipient, body, _now()),
        )
        _db().commit()
        return int(cur.lastrowid)


def next_queued() -> Optional[sqlite3.Row]:
    """Oldest message still waiting to be sent."""
    with _lock:
        cur = _db().execute(
            "SELECT * FROM messages WHERE status = 'queued' "
            "ORDER BY id ASC LIMIT 1"
        )
        return cur.fetchone()


def mark_sent(message_id: int, gateway_id: str | None) -> None:
    with _lock:
        _db().execute(
            "UPDATE messages SET status='sent', gateway_id=?, sent_at=?, "
            "attempts=attempts+1, error=NULL WHERE id=?",
            (gateway_id, _now(), message_id),
        )
        _db().commit()


def mark_attempt_failed(message_id: int, error: str, max_attempts: int) -> str:
    """Record a failed attempt. Mark 'failed' once attempts hit max.

    Returns the resulting status ('queued' for retry, or 'failed').
    """
    with _lock:
        row = _db().execute(
            "SELECT attempts FROM messages WHERE id=?", (message_id,)
        ).fetchone()
        attempts = (row["attempts"] if row else 0) + 1
        status = "failed" if attempts >= max_attempts else "queued"
        _db().execute(
            "UPDATE messages SET status=?, attempts=?, error=? WHERE id=?",
            (status, attempts, error, message_id),
        )
        _db().commit()
        return status


def add_log(
    message_id: int | None, recipient: str, status: str, error: str | None
) -> None:
    with _lock:
        _db().execute(
            "INSERT INTO send_log (message_id, recipient, status, error, timestamp) "
            "VALUES (?, ?, ?, ?, ?)",
            (message_id, recipient, status, error, _now()),
        )
        _db().commit()


def sent_today_count() -> int:
    """Number of messages successfully sent since local midnight."""
    start = datetime.now().astimezone().replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    start_utc = start.astimezone(timezone.utc).isoformat()
    with _lock:
        row = _db().execute(
            "SELECT COUNT(*) AS c FROM messages "
            "WHERE status='sent' AND sent_at >= ?",
            (start_utc,),
        ).fetchone()
        return int(row["c"])


def queue_length() -> int:
    with _lock:
        row = _db().execute(
            "SELECT COUNT(*) AS c FROM messages WHERE status='queued'"
        ).fetchone()
        return int(row["c"])


def last_sent_at() -> Optional[datetime]:
    with _lock:
        row = _db().execute(
            "SELECT sent_at FROM messages WHERE status='sent' "
            "ORDER BY sent_at DESC LIMIT 1"
        ).fetchone()
    if row and row["sent_at"]:
        return datetime.fromisoformat(row["sent_at"])
    return None


def get_message(message_id: int) -> Optional[dict[str, Any]]:
    with _lock:
        row = _db().execute(
            "SELECT * FROM messages WHERE id=?", (message_id,)
        ).fetchone()
        return dict(row) if row else None


def list_messages(limit: int = 50) -> list[dict[str, Any]]:
    """Most recent messages first (for the web UI)."""
    limit = max(1, min(limit, 500))
    with _lock:
        rows = _db().execute(
            "SELECT * FROM messages ORDER BY id DESC LIMIT ?", (limit,)
        ).fetchall()
        return [dict(r) for r in rows]
