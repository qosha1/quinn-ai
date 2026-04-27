"""
SQLite persistence for conversation transcripts.

Provides durable storage for session transcripts with support for:
- Save/load round-trip
- Session listing and metadata
- Concurrent access via threading locks

TranscriptStore opens its own sqlite connection to a path. The previous
TranscriptRepository wrapper around cli.core.db.Database was deleted in
quinn-ai-277 — it had no production callers and the Database dep would
have re-introduced the shared.pyterm → cli.core back-import that 8la.1
just removed.
"""

import json
import sqlite3
import threading
from datetime import datetime
from pathlib import Path
from typing import Any

from shared.pyterm.conversation import (
    Message,
    MessageRole,
    ToolCall,
    ToolResult,
    Turn,
    Transcript,
)


class TranscriptStore:
    """
    SQLite-backed storage for conversation transcripts.

    Thread-safe via connection-per-thread pattern.
    """

    def __init__(self, db_path: str):
        """
        Initialize store with database path.

        Args:
            db_path: Path to SQLite database file.
        """
        self._db_path = db_path
        self._local = threading.local()
        self._lock = threading.Lock()
        self._init_schema()

    def _get_connection(self) -> sqlite3.Connection:
        """Get thread-local connection."""
        if not hasattr(self._local, 'conn') or self._local.conn is None:
            self._local.conn = sqlite3.connect(self._db_path, timeout=30.0)
            self._local.conn.row_factory = sqlite3.Row
            # Enable foreign keys and WAL mode for better concurrency
            self._local.conn.execute("PRAGMA foreign_keys = ON")
            self._local.conn.execute("PRAGMA journal_mode = WAL")
        return self._local.conn

    def _init_schema(self) -> None:
        """Create database tables if they don't exist."""
        conn = self._get_connection()
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS sessions (
                id TEXT PRIMARY KEY,
                worker_id TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                metadata_json TEXT
            );

            CREATE TABLE IF NOT EXISTS turns (
                id TEXT NOT NULL,
                session_id TEXT NOT NULL,
                turn_number INTEGER NOT NULL,
                prompt_content TEXT NOT NULL,
                prompt_role TEXT NOT NULL,
                prompt_timestamp TEXT NOT NULL,
                prompt_metadata_json TEXT,
                response_content TEXT,
                response_role TEXT,
                response_timestamp TEXT,
                response_metadata_json TEXT,
                started_at TEXT NOT NULL,
                completed_at TEXT,
                metadata_json TEXT,
                ask_id TEXT,
                okr_id TEXT,
                PRIMARY KEY (session_id, id),
                FOREIGN KEY (session_id) REFERENCES sessions(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS tool_calls (
                id TEXT NOT NULL,
                session_id TEXT NOT NULL,
                turn_id TEXT NOT NULL,
                tool_name TEXT NOT NULL,
                arguments_json TEXT,
                timestamp TEXT NOT NULL,
                PRIMARY KEY (session_id, id),
                FOREIGN KEY (session_id, turn_id) REFERENCES turns(session_id, id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS tool_results (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL,
                tool_call_id TEXT NOT NULL,
                turn_id TEXT NOT NULL,
                output TEXT NOT NULL,
                success INTEGER NOT NULL,
                error TEXT,
                timestamp TEXT NOT NULL,
                FOREIGN KEY (session_id, turn_id) REFERENCES turns(session_id, id) ON DELETE CASCADE
            );

            CREATE INDEX IF NOT EXISTS idx_turns_session ON turns(session_id);
            CREATE INDEX IF NOT EXISTS idx_turns_ask_id ON turns(ask_id);
            CREATE INDEX IF NOT EXISTS idx_turns_okr_id ON turns(okr_id);
            CREATE INDEX IF NOT EXISTS idx_tool_calls_session_turn ON tool_calls(session_id, turn_id);
            CREATE INDEX IF NOT EXISTS idx_tool_results_session_turn ON tool_results(session_id, turn_id);
        """)
        conn.commit()

    def save_transcript(
        self,
        session_id: str,
        transcript: Transcript,
        worker_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """
        Save a transcript to the database.

        Args:
            session_id: Unique session identifier.
            transcript: The transcript to save.
            worker_id: Optional worker ID.
            metadata: Optional session metadata.
        """
        with self._lock:
            conn = self._get_connection()
            now = datetime.now().isoformat()

            # Check if session exists
            existing = conn.execute(
                "SELECT id FROM sessions WHERE id = ?",
                (session_id,)
            ).fetchone()

            if existing:
                # Update existing session
                conn.execute(
                    "UPDATE sessions SET updated_at = ?, metadata_json = ? WHERE id = ?",
                    (now, json.dumps(metadata) if metadata else None, session_id)
                )
                # Delete existing turns (cascade will delete tool_calls and tool_results)
                conn.execute("DELETE FROM turns WHERE session_id = ?", (session_id,))
            else:
                # Insert new session
                conn.execute(
                    "INSERT INTO sessions (id, worker_id, created_at, updated_at, metadata_json) VALUES (?, ?, ?, ?, ?)",
                    (session_id, worker_id, now, now, json.dumps(metadata) if metadata else None)
                )

            # Insert turns
            for i, turn in enumerate(transcript.turns):
                self._save_turn(conn, session_id, i, turn)

            conn.commit()

    def _save_turn(
        self,
        conn: sqlite3.Connection,
        session_id: str,
        turn_number: int,
        turn: Turn,
    ) -> None:
        """Save a single turn and its tool calls/results."""
        conn.execute(
            """INSERT INTO turns (
                id, session_id, turn_number,
                prompt_content, prompt_role, prompt_timestamp, prompt_metadata_json,
                response_content, response_role, response_timestamp, response_metadata_json,
                started_at, completed_at, metadata_json,
                ask_id, okr_id
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                turn.id,
                session_id,
                turn_number,
                turn.prompt.content,
                turn.prompt.role.value,
                turn.prompt.timestamp.isoformat(),
                json.dumps(turn.prompt.metadata),
                turn.response.content if turn.response else None,
                turn.response.role.value if turn.response else None,
                turn.response.timestamp.isoformat() if turn.response else None,
                json.dumps(turn.response.metadata) if turn.response else None,
                turn.started_at.isoformat(),
                turn.completed_at.isoformat() if turn.completed_at else None,
                json.dumps(turn.metadata),
                turn.ask_id,
                turn.okr_id,
            )
        )

        # Save tool calls
        for tc in turn.tool_calls:
            conn.execute(
                "INSERT INTO tool_calls (id, session_id, turn_id, tool_name, arguments_json, timestamp) VALUES (?, ?, ?, ?, ?, ?)",
                (tc.id, session_id, turn.id, tc.name, json.dumps(tc.arguments), tc.timestamp.isoformat())
            )

        # Save tool results
        for tr in turn.tool_results:
            conn.execute(
                """INSERT INTO tool_results (session_id, tool_call_id, turn_id, output, success, error, timestamp)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (session_id, tr.tool_call_id, turn.id, tr.output, 1 if tr.success else 0, tr.error, tr.timestamp.isoformat())
            )

    def load_transcript(self, session_id: str) -> Transcript | None:
        """
        Load a transcript from the database.

        Args:
            session_id: The session ID to load.

        Returns:
            The loaded Transcript, or None if not found.
        """
        conn = self._get_connection()

        # Check session exists
        session = conn.execute(
            "SELECT id FROM sessions WHERE id = ?",
            (session_id,)
        ).fetchone()

        if not session:
            return None

        # Load turns
        turns_rows = conn.execute(
            "SELECT * FROM turns WHERE session_id = ? ORDER BY turn_number",
            (session_id,)
        ).fetchall()

        transcript = Transcript()

        for turn_row in turns_rows:
            turn = self._load_turn(conn, turn_row)
            transcript._turns.append(turn)
            transcript._turn_counter += 1

        return transcript

    def _load_turn(self, conn: sqlite3.Connection, turn_row: sqlite3.Row) -> Turn:
        """Load a turn and its tool calls/results from the database."""
        session_id = turn_row['session_id']
        turn_id = turn_row['id']

        # Create prompt message
        prompt = Message(
            role=MessageRole(turn_row['prompt_role']),
            content=turn_row['prompt_content'],
            timestamp=datetime.fromisoformat(turn_row['prompt_timestamp']),
            metadata=json.loads(turn_row['prompt_metadata_json']) if turn_row['prompt_metadata_json'] else {},
        )

        # Create response message if exists
        response = None
        if turn_row['response_content'] is not None:
            response = Message(
                role=MessageRole(turn_row['response_role']),
                content=turn_row['response_content'],
                timestamp=datetime.fromisoformat(turn_row['response_timestamp']),
                metadata=json.loads(turn_row['response_metadata_json']) if turn_row['response_metadata_json'] else {},
            )

        # Load tool calls
        tc_rows = conn.execute(
            "SELECT * FROM tool_calls WHERE session_id = ? AND turn_id = ?",
            (session_id, turn_id)
        ).fetchall()

        tool_calls = []
        for tc_row in tc_rows:
            tool_calls.append(ToolCall(
                id=tc_row['id'],
                name=tc_row['tool_name'],
                arguments=json.loads(tc_row['arguments_json']) if tc_row['arguments_json'] else {},
                timestamp=datetime.fromisoformat(tc_row['timestamp']),
            ))

        # Load tool results
        tr_rows = conn.execute(
            "SELECT * FROM tool_results WHERE session_id = ? AND turn_id = ?",
            (session_id, turn_id)
        ).fetchall()

        tool_results = []
        for tr_row in tr_rows:
            tool_results.append(ToolResult(
                tool_call_id=tr_row['tool_call_id'],
                output=tr_row['output'],
                success=bool(tr_row['success']),
                error=tr_row['error'],
                timestamp=datetime.fromisoformat(tr_row['timestamp']),
            ))

        # Create turn
        turn = Turn(
            id=turn_row['id'],
            prompt=prompt,
            response=response,
            tool_calls=tool_calls,
            tool_results=tool_results,
            started_at=datetime.fromisoformat(turn_row['started_at']),
            completed_at=datetime.fromisoformat(turn_row['completed_at']) if turn_row['completed_at'] else None,
            metadata=json.loads(turn_row['metadata_json']) if turn_row['metadata_json'] else {},
            ask_id=turn_row['ask_id'] if 'ask_id' in turn_row.keys() else None,
            okr_id=turn_row['okr_id'] if 'okr_id' in turn_row.keys() else None,
        )

        return turn

    def delete_transcript(self, session_id: str) -> bool:
        """
        Delete a transcript from the database.

        Args:
            session_id: The session ID to delete.

        Returns:
            True if deleted, False if not found.
        """
        with self._lock:
            conn = self._get_connection()

            # Delete session (cascade will handle turns, tool_calls, tool_results)
            cursor = conn.execute(
                "DELETE FROM sessions WHERE id = ?",
                (session_id,)
            )
            conn.commit()

            return cursor.rowcount > 0

    def list_sessions(self) -> list[str]:
        """
        List all session IDs.

        Returns:
            List of session IDs.
        """
        conn = self._get_connection()
        rows = conn.execute("SELECT id FROM sessions ORDER BY created_at DESC").fetchall()
        return [row['id'] for row in rows]

    def get_session_metadata(self, session_id: str) -> dict | None:
        """
        Get metadata for a session.

        Args:
            session_id: The session ID.

        Returns:
            Dict with turn_count, message_count, created_at, updated_at,
            or None if session not found.
        """
        conn = self._get_connection()

        session = conn.execute(
            "SELECT * FROM sessions WHERE id = ?",
            (session_id,)
        ).fetchone()

        if not session:
            return None

        # Count turns
        turn_count = conn.execute(
            "SELECT COUNT(*) as count FROM turns WHERE session_id = ?",
            (session_id,)
        ).fetchone()['count']

        # Count messages (prompts + responses)
        message_stats = conn.execute(
            """SELECT
                COUNT(*) as turn_count,
                SUM(CASE WHEN response_content IS NOT NULL THEN 1 ELSE 0 END) as response_count
            FROM turns WHERE session_id = ?""",
            (session_id,)
        ).fetchone()

        # Count tool calls
        tool_call_count = conn.execute(
            """SELECT COUNT(*) as count FROM tool_calls tc
               JOIN turns t ON tc.turn_id = t.id
               WHERE t.session_id = ?""",
            (session_id,)
        ).fetchone()['count']

        # Count tool results
        tool_result_count = conn.execute(
            """SELECT COUNT(*) as count FROM tool_results tr
               JOIN turns t ON tr.turn_id = t.id
               WHERE t.session_id = ?""",
            (session_id,)
        ).fetchone()['count']

        # Total messages = prompts + responses + tool_calls + tool_results
        message_count = (
            message_stats['turn_count'] +  # prompts
            message_stats['response_count'] +  # responses
            tool_call_count +  # tool calls
            tool_result_count  # tool results
        )

        return {
            'session_id': session_id,
            'worker_id': session['worker_id'],
            'turn_count': turn_count,
            'message_count': message_count,
            'tool_call_count': tool_call_count,
            'tool_result_count': tool_result_count,
            'created_at': session['created_at'],
            'updated_at': session['updated_at'],
            'metadata': json.loads(session['metadata_json']) if session['metadata_json'] else None,
        }

    def close(self) -> None:
        """Close the database connection for the current thread."""
        if hasattr(self._local, 'conn') and self._local.conn is not None:
            self._local.conn.close()
            self._local.conn = None


# =============================================================================
# Transcript table schema (used by both TranscriptStore and any future
# integrated-mode wrapper; tables live in whichever sqlite db the caller
# points at).
# =============================================================================

TRANSCRIPT_SCHEMA_SQL = """
-- Transcript sessions (one per worker session)
CREATE TABLE IF NOT EXISTS transcript_sessions (
    id TEXT PRIMARY KEY,
    worker_id TEXT NOT NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    metadata_json TEXT,
    FOREIGN KEY (worker_id) REFERENCES workers(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_transcript_sessions_worker ON transcript_sessions(worker_id);

-- Transcript turns (conversation exchanges)
CREATE TABLE IF NOT EXISTS transcript_turns (
    id TEXT NOT NULL,
    session_id TEXT NOT NULL,
    turn_number INTEGER NOT NULL,
    prompt_content TEXT NOT NULL,
    prompt_role TEXT NOT NULL,
    prompt_timestamp DATETIME NOT NULL,
    prompt_metadata_json TEXT,
    response_content TEXT,
    response_role TEXT,
    response_timestamp DATETIME,
    response_metadata_json TEXT,
    started_at DATETIME NOT NULL,
    completed_at DATETIME,
    metadata_json TEXT,
    ask_id TEXT,
    okr_id TEXT,
    PRIMARY KEY (session_id, id),
    FOREIGN KEY (session_id) REFERENCES transcript_sessions(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_transcript_turns_session ON transcript_turns(session_id);
CREATE INDEX IF NOT EXISTS idx_transcript_turns_ask ON transcript_turns(ask_id);
CREATE INDEX IF NOT EXISTS idx_transcript_turns_okr ON transcript_turns(okr_id);

-- Transcript tool calls
CREATE TABLE IF NOT EXISTS transcript_tool_calls (
    id TEXT NOT NULL,
    session_id TEXT NOT NULL,
    turn_id TEXT NOT NULL,
    tool_name TEXT NOT NULL,
    arguments_json TEXT,
    timestamp DATETIME NOT NULL,
    PRIMARY KEY (session_id, id),
    FOREIGN KEY (session_id, turn_id) REFERENCES transcript_turns(session_id, id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_transcript_tool_calls_turn ON transcript_tool_calls(session_id, turn_id);

-- Transcript tool results
CREATE TABLE IF NOT EXISTS transcript_tool_results (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL,
    tool_call_id TEXT NOT NULL,
    turn_id TEXT NOT NULL,
    output TEXT NOT NULL,
    success INTEGER NOT NULL,
    error TEXT,
    timestamp DATETIME NOT NULL,
    FOREIGN KEY (session_id, turn_id) REFERENCES transcript_turns(session_id, id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_transcript_tool_results_turn ON transcript_tool_results(session_id, turn_id);
"""


