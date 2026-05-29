"""
JARVIS Memory System
SQLite-based persistence for commands, responses, preferences, and task history.
"""

import sqlite3
import json
import logging
import time
from pathlib import Path
from typing import List, Dict, Optional, Any

logger = logging.getLogger("jarvis.memory")


class MemorySystem:
    """
    Persistent memory backed by SQLite.
    Stores command history, preferences, and task logs.
    """

    def __init__(self, db_path: str = "~/.jarvis/memory.db"):
        self._db_path = Path(db_path).expanduser()
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(self._db_path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._init_schema()
        logger.info(f"[Memory] Database at {self._db_path}")

    def _init_schema(self):
        cur = self._conn.cursor()
        cur.executescript("""
            CREATE TABLE IF NOT EXISTS command_history (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                command     TEXT NOT NULL,
                response    TEXT,
                timestamp   REAL NOT NULL,
                session_id  TEXT
            );

            CREATE TABLE IF NOT EXISTS task_log (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                command     TEXT NOT NULL,
                steps_json  TEXT,
                success     INTEGER,
                timestamp   REAL NOT NULL
            );

            CREATE TABLE IF NOT EXISTS preferences (
                key         TEXT PRIMARY KEY,
                value       TEXT NOT NULL,
                updated_at  REAL NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_cmd_ts ON command_history(timestamp DESC);
        """)
        self._conn.commit()

    # ── Command History ───────────────────────────────────────────────────────

    def log_command(self, command: str, session_id: str = "default"):
        """Record a new command."""
        try:
            self._conn.execute(
                "INSERT INTO command_history (command, timestamp, session_id) VALUES (?,?,?)",
                (command, time.time(), session_id)
            )
            self._conn.commit()
        except Exception as e:
            logger.error(f"[Memory] log_command error: {e}")

    def log_response(self, command: str, response: str):
        """Update the most recent matching command with a response."""
        try:
            self._conn.execute(
                """UPDATE command_history SET response=?
                   WHERE command=? AND response IS NULL
                   ORDER BY id DESC LIMIT 1""",
                (response, command)
            )
            self._conn.commit()
        except Exception:
            pass

    def get_recent_commands(self, limit: int = 20) -> List[Dict]:
        """Return recent commands."""
        try:
            rows = self._conn.execute(
                "SELECT command, response, timestamp FROM command_history "
                "ORDER BY timestamp DESC LIMIT ?", (limit,)
            ).fetchall()
            return [dict(r) for r in rows]
        except Exception as e:
            logger.error(f"[Memory] get_recent error: {e}")
            return []

    def search_history(self, query: str, limit: int = 10) -> List[Dict]:
        """Full-text search over command history."""
        try:
            rows = self._conn.execute(
                "SELECT command, response, timestamp FROM command_history "
                "WHERE command LIKE ? OR response LIKE ? "
                "ORDER BY timestamp DESC LIMIT ?",
                (f"%{query}%", f"%{query}%", limit)
            ).fetchall()
            return [dict(r) for r in rows]
        except Exception as e:
            logger.error(f"[Memory] search error: {e}")
            return []

    # ── Task Log ──────────────────────────────────────────────────────────────

    def log_task(self, command: str, steps: list, success: bool):
        """Log a completed task plan."""
        try:
            self._conn.execute(
                "INSERT INTO task_log (command, steps_json, success, timestamp) VALUES (?,?,?,?)",
                (command, json.dumps(steps), int(success), time.time())
            )
            self._conn.commit()
        except Exception as e:
            logger.error(f"[Memory] log_task error: {e}")

    # ── Preferences ───────────────────────────────────────────────────────────

    def set_preference(self, key: str, value: Any):
        """Store a user preference."""
        try:
            self._conn.execute(
                "INSERT OR REPLACE INTO preferences (key, value, updated_at) VALUES (?,?,?)",
                (key, json.dumps(value), time.time())
            )
            self._conn.commit()
        except Exception as e:
            logger.error(f"[Memory] set_pref error: {e}")

    def get_preference(self, key: str, default: Any = None) -> Any:
        """Retrieve a user preference."""
        try:
            row = self._conn.execute(
                "SELECT value FROM preferences WHERE key=?", (key,)
            ).fetchone()
            if row:
                return json.loads(row["value"])
            return default
        except Exception as e:
            logger.error(f"[Memory] get_pref error: {e}")
            return default

    # ── Context Builder ───────────────────────────────────────────────────────

    def build_context_snippet(self, limit: int = 5) -> str:
        """Build a short context string of recent interactions for LLM."""
        recent = self.get_recent_commands(limit)
        if not recent:
            return ""
        lines = ["[Recent interactions:]"]
        for r in reversed(recent):
            cmd  = r["command"][:80]
            resp = (r["response"] or "")[:80]
            lines.append(f"  User: {cmd}")
            if resp:
                lines.append(f"  JARVIS: {resp}")
        return "\n".join(lines)

    def close(self):
        try:
            self._conn.close()
        except Exception:
            pass

    def __del__(self):
        self.close()
