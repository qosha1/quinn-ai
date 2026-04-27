"""
Tests for pyterm SQLite persistence.
"""

import pytest
import sqlite3
import threading
import time
from pathlib import Path

from shared.pyterm.conversation import (
    Message,
    MessageRole,
    ToolCall,
    ToolResult,
    Turn,
    Transcript,
)
from shared.pyterm.persistence import TranscriptStore, TRANSCRIPT_SCHEMA_SQL


class TestTranscriptStore:
    """Tests for TranscriptStore class."""

    def test_init_creates_tables(self, tmp_path: Path):
        """Test that initialization creates all required tables."""
        db_path = tmp_path / "test.db"
        store = TranscriptStore(str(db_path))

        # Check tables exist
        conn = store._get_connection()
        tables = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
        table_names = [t['name'] for t in tables]

        assert 'sessions' in table_names
        assert 'turns' in table_names
        assert 'tool_calls' in table_names
        assert 'tool_results' in table_names

        store.close()

    def test_save_empty_transcript(self, tmp_path: Path):
        """Test saving an empty transcript."""
        db_path = tmp_path / "test.db"
        store = TranscriptStore(str(db_path))

        transcript = Transcript()
        store.save_transcript("session-1", transcript)

        sessions = store.list_sessions()
        assert "session-1" in sessions

        store.close()

    def test_save_and_load_simple_transcript(self, tmp_path: Path):
        """Test basic save/load round-trip."""
        db_path = tmp_path / "test.db"
        store = TranscriptStore(str(db_path))

        # Create transcript
        transcript = Transcript()
        turn = transcript.new_turn("Hello, agent!")
        turn.complete(Message.assistant("Hello, human!"))

        # Save
        store.save_transcript("session-1", transcript, worker_id="ceo")

        # Load
        loaded = store.load_transcript("session-1")

        assert loaded is not None
        assert len(loaded) == 1
        assert loaded.turns[0].prompt.content == "Hello, agent!"
        assert loaded.turns[0].response.content == "Hello, human!"
        assert loaded.turns[0].is_complete

        store.close()

    def test_save_and_load_with_tool_calls(self, tmp_path: Path):
        """Test save/load with tool calls and results."""
        db_path = tmp_path / "test.db"
        store = TranscriptStore(str(db_path))

        # Create transcript with tool use
        transcript = Transcript()
        turn = transcript.new_turn("Read the file /tmp/test.txt")

        tc = ToolCall(
            id="tc-1",
            name="read_file",
            arguments={"path": "/tmp/test.txt", "encoding": "utf-8"}
        )
        turn.add_tool_call(tc)

        tr = ToolResult(
            tool_call_id="tc-1",
            output="Hello World",
            success=True
        )
        turn.add_tool_result(tr)

        turn.complete(Message.assistant("The file contains: Hello World"))

        # Save and load
        store.save_transcript("session-1", transcript)
        loaded = store.load_transcript("session-1")

        assert loaded is not None
        assert len(loaded.turns[0].tool_calls) == 1
        assert len(loaded.turns[0].tool_results) == 1

        loaded_tc = loaded.turns[0].tool_calls[0]
        assert loaded_tc.id == "tc-1"
        assert loaded_tc.name == "read_file"
        assert loaded_tc.arguments == {"path": "/tmp/test.txt", "encoding": "utf-8"}

        loaded_tr = loaded.turns[0].tool_results[0]
        assert loaded_tr.tool_call_id == "tc-1"
        assert loaded_tr.output == "Hello World"
        assert loaded_tr.success is True

        store.close()

    def test_save_and_load_with_failed_tool_result(self, tmp_path: Path):
        """Test save/load with failed tool result."""
        db_path = tmp_path / "test.db"
        store = TranscriptStore(str(db_path))

        transcript = Transcript()
        turn = transcript.new_turn("Delete the file")

        tc = ToolCall(id="tc-1", name="delete_file", arguments={"path": "/root/secret"})
        turn.add_tool_call(tc)

        tr = ToolResult(
            tool_call_id="tc-1",
            output="",
            success=False,
            error="Permission denied"
        )
        turn.add_tool_result(tr)

        turn.complete(Message.assistant("I couldn't delete the file due to permissions."))

        store.save_transcript("session-1", transcript)
        loaded = store.load_transcript("session-1")

        loaded_tr = loaded.turns[0].tool_results[0]
        assert loaded_tr.success is False
        assert loaded_tr.error == "Permission denied"

        store.close()

    def test_save_and_load_multiple_turns(self, tmp_path: Path):
        """Test save/load with multiple turns."""
        db_path = tmp_path / "test.db"
        store = TranscriptStore(str(db_path))

        transcript = Transcript()

        # Turn 1
        t1 = transcript.new_turn("What is 2+2?")
        t1.complete(Message.assistant("4"))

        # Turn 2
        t2 = transcript.new_turn("What is 3+3?")
        t2.complete(Message.assistant("6"))

        # Turn 3
        t3 = transcript.new_turn("Thanks!")
        t3.complete(Message.assistant("You're welcome!"))

        store.save_transcript("session-1", transcript)
        loaded = store.load_transcript("session-1")

        assert len(loaded) == 3
        assert loaded.turns[0].prompt.content == "What is 2+2?"
        assert loaded.turns[1].prompt.content == "What is 3+3?"
        assert loaded.turns[2].prompt.content == "Thanks!"

        store.close()

    def test_update_existing_session(self, tmp_path: Path):
        """Test that saving to existing session replaces content."""
        db_path = tmp_path / "test.db"
        store = TranscriptStore(str(db_path))

        # Save initial transcript
        transcript1 = Transcript()
        transcript1.new_turn("First prompt").complete(Message.assistant("First response"))
        store.save_transcript("session-1", transcript1)

        # Save updated transcript to same session
        transcript2 = Transcript()
        transcript2.new_turn("New prompt").complete(Message.assistant("New response"))
        store.save_transcript("session-1", transcript2)

        # Load and verify it's the new content
        loaded = store.load_transcript("session-1")

        assert len(loaded) == 1
        assert loaded.turns[0].prompt.content == "New prompt"

        store.close()

    def test_list_sessions(self, tmp_path: Path):
        """Test listing all sessions."""
        db_path = tmp_path / "test.db"
        store = TranscriptStore(str(db_path))

        # Create multiple sessions
        for i in range(3):
            transcript = Transcript()
            transcript.new_turn(f"Prompt {i}")
            store.save_transcript(f"session-{i}", transcript)

        sessions = store.list_sessions()

        assert len(sessions) == 3
        assert "session-0" in sessions
        assert "session-1" in sessions
        assert "session-2" in sessions

        store.close()

    def test_list_sessions_empty(self, tmp_path: Path):
        """Test listing sessions when none exist."""
        db_path = tmp_path / "test.db"
        store = TranscriptStore(str(db_path))

        sessions = store.list_sessions()
        assert sessions == []

        store.close()

    def test_delete_transcript(self, tmp_path: Path):
        """Test deleting a transcript."""
        db_path = tmp_path / "test.db"
        store = TranscriptStore(str(db_path))

        # Create and save transcript
        transcript = Transcript()
        turn = transcript.new_turn("Hello")
        turn.add_tool_call(ToolCall(id="tc-1", name="test", arguments={}))
        turn.add_tool_result(ToolResult(tool_call_id="tc-1", output="ok"))
        turn.complete(Message.assistant("Hi"))
        store.save_transcript("session-1", transcript)

        # Verify it exists
        assert store.load_transcript("session-1") is not None

        # Delete
        result = store.delete_transcript("session-1")
        assert result is True

        # Verify it's gone
        assert store.load_transcript("session-1") is None
        assert "session-1" not in store.list_sessions()

        store.close()

    def test_delete_nonexistent_transcript(self, tmp_path: Path):
        """Test deleting a transcript that doesn't exist."""
        db_path = tmp_path / "test.db"
        store = TranscriptStore(str(db_path))

        result = store.delete_transcript("nonexistent")
        assert result is False

        store.close()

    def test_load_nonexistent_transcript(self, tmp_path: Path):
        """Test loading a transcript that doesn't exist."""
        db_path = tmp_path / "test.db"
        store = TranscriptStore(str(db_path))

        loaded = store.load_transcript("nonexistent")
        assert loaded is None

        store.close()

    def test_get_session_metadata(self, tmp_path: Path):
        """Test getting session metadata."""
        db_path = tmp_path / "test.db"
        store = TranscriptStore(str(db_path))

        transcript = Transcript()
        turn = transcript.new_turn("Hello")
        turn.add_tool_call(ToolCall(id="tc-1", name="bash", arguments={}))
        turn.add_tool_result(ToolResult(tool_call_id="tc-1", output="done"))
        turn.complete(Message.assistant("Hi"))

        store.save_transcript(
            "session-1",
            transcript,
            worker_id="ceo",
            metadata={"task": "greeting"}
        )

        meta = store.get_session_metadata("session-1")

        assert meta is not None
        assert meta['session_id'] == "session-1"
        assert meta['worker_id'] == "ceo"
        assert meta['turn_count'] == 1
        assert meta['message_count'] == 4  # prompt + tool_call + tool_result + response
        assert meta['tool_call_count'] == 1
        assert meta['tool_result_count'] == 1
        assert meta['metadata'] == {"task": "greeting"}
        assert 'created_at' in meta
        assert 'updated_at' in meta

        store.close()

    def test_get_session_metadata_nonexistent(self, tmp_path: Path):
        """Test getting metadata for nonexistent session."""
        db_path = tmp_path / "test.db"
        store = TranscriptStore(str(db_path))

        meta = store.get_session_metadata("nonexistent")
        assert meta is None

        store.close()

    def test_preserves_message_metadata(self, tmp_path: Path):
        """Test that message metadata is preserved."""
        db_path = tmp_path / "test.db"
        store = TranscriptStore(str(db_path))

        transcript = Transcript()
        # Create a message with metadata directly
        prompt = Message.user("Hello", source="cli", priority=1)
        turn = Turn(id="turn-1", prompt=prompt)
        turn.complete(Message.assistant("Hi", model="gpt-4", tokens=10))
        transcript._turns.append(turn)
        transcript._turn_counter = 1

        store.save_transcript("session-1", transcript)
        loaded = store.load_transcript("session-1")

        assert loaded.turns[0].prompt.metadata.get("source") == "cli"
        assert loaded.turns[0].prompt.metadata.get("priority") == 1
        assert loaded.turns[0].response.metadata.get("model") == "gpt-4"
        assert loaded.turns[0].response.metadata.get("tokens") == 10

        store.close()

    def test_preserves_turn_metadata(self, tmp_path: Path):
        """Test that turn metadata is preserved."""
        db_path = tmp_path / "test.db"
        store = TranscriptStore(str(db_path))

        transcript = Transcript()
        turn = transcript.new_turn("Hello")
        turn.metadata["task_id"] = "task-123"
        turn.metadata["priority"] = "high"
        turn.complete(Message.assistant("Hi"))

        store.save_transcript("session-1", transcript)
        loaded = store.load_transcript("session-1")

        assert loaded.turns[0].metadata.get("task_id") == "task-123"
        assert loaded.turns[0].metadata.get("priority") == "high"

        store.close()

    def test_preserves_timestamps(self, tmp_path: Path):
        """Test that timestamps are preserved correctly."""
        db_path = tmp_path / "test.db"
        store = TranscriptStore(str(db_path))

        transcript = Transcript()
        turn = transcript.new_turn("Hello")
        original_started_at = turn.started_at
        turn.complete(Message.assistant("Hi"))
        original_completed_at = turn.completed_at

        store.save_transcript("session-1", transcript)
        loaded = store.load_transcript("session-1")

        # Compare timestamps (microsecond precision may differ due to ISO format)
        assert loaded.turns[0].started_at.isoformat() == original_started_at.isoformat()
        assert loaded.turns[0].completed_at.isoformat() == original_completed_at.isoformat()

        store.close()


class TestConcurrentAccess:
    """Tests for concurrent access to TranscriptStore."""

    def test_concurrent_saves(self, tmp_path: Path):
        """Test multiple threads saving to different sessions."""
        db_path = tmp_path / "test.db"
        store = TranscriptStore(str(db_path))

        errors = []
        results = []

        def save_session(session_id: str):
            try:
                transcript = Transcript()
                transcript.new_turn(f"Hello from {session_id}")
                store.save_transcript(session_id, transcript)
                results.append(session_id)
            except Exception as e:
                errors.append(e)

        threads = []
        for i in range(10):
            t = threading.Thread(target=save_session, args=(f"session-{i}",))
            threads.append(t)
            t.start()

        for t in threads:
            t.join()

        assert len(errors) == 0, f"Errors occurred: {errors}"
        assert len(results) == 10

        sessions = store.list_sessions()
        assert len(sessions) == 10

        store.close()

    def test_concurrent_reads(self, tmp_path: Path):
        """Test multiple threads reading the same session."""
        db_path = tmp_path / "test.db"
        store = TranscriptStore(str(db_path))

        # Create a session first
        transcript = Transcript()
        transcript.new_turn("Hello")
        store.save_transcript("session-1", transcript)

        errors = []
        results = []

        def read_session():
            try:
                loaded = store.load_transcript("session-1")
                if loaded:
                    results.append(loaded.turns[0].prompt.content)
            except Exception as e:
                errors.append(e)

        threads = []
        for _ in range(10):
            t = threading.Thread(target=read_session)
            threads.append(t)
            t.start()

        for t in threads:
            t.join()

        assert len(errors) == 0, f"Errors occurred: {errors}"
        assert len(results) == 10
        assert all(r == "Hello" for r in results)

        store.close()

    def test_concurrent_read_write(self, tmp_path: Path):
        """Test concurrent reads and writes."""
        db_path = tmp_path / "test.db"
        store = TranscriptStore(str(db_path))

        # Create initial session
        transcript = Transcript()
        transcript.new_turn("Initial")
        store.save_transcript("session-1", transcript)

        errors = []
        read_results = []
        write_results = []

        def reader():
            try:
                for _ in range(5):
                    loaded = store.load_transcript("session-1")
                    if loaded:
                        read_results.append(loaded.turns[0].prompt.content)
                    time.sleep(0.01)
            except Exception as e:
                errors.append(e)

        def writer(suffix: str):
            try:
                for i in range(5):
                    transcript = Transcript()
                    transcript.new_turn(f"Updated-{suffix}-{i}")
                    store.save_transcript("session-1", transcript)
                    write_results.append(f"Updated-{suffix}-{i}")
                    time.sleep(0.01)
            except Exception as e:
                errors.append(e)

        threads = [
            threading.Thread(target=reader),
            threading.Thread(target=writer, args=("A",)),
            threading.Thread(target=reader),
            threading.Thread(target=writer, args=("B",)),
        ]

        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(errors) == 0, f"Errors occurred: {errors}"
        # All reads should return something valid
        assert len(read_results) == 10
        # All writes should complete
        assert len(write_results) == 10

        store.close()


class TestIntegration:
    """Integration tests for persistence."""

    def test_full_conversation_persistence(self, tmp_path: Path):
        """Test persisting a full conversation with multiple turns and tools."""
        db_path = tmp_path / "test.db"
        store = TranscriptStore(str(db_path))

        # Create complex transcript
        transcript = Transcript()

        # Turn 1: Simple Q&A
        t1 = transcript.new_turn("What time is it?")
        t1.complete(Message.assistant("It's 3:00 PM"))

        # Turn 2: With tool use
        t2 = transcript.new_turn("List files in /tmp")
        t2.add_tool_call(ToolCall(id="tc-1", name="bash", arguments={"command": "ls /tmp"}))
        t2.add_tool_result(ToolResult(tool_call_id="tc-1", output="file1.txt\nfile2.txt"))
        t2.complete(Message.assistant("There are 2 files: file1.txt and file2.txt"))

        # Turn 3: Multiple tool calls
        t3 = transcript.new_turn("Read both files")
        t3.add_tool_call(ToolCall(id="tc-2", name="read_file", arguments={"path": "/tmp/file1.txt"}))
        t3.add_tool_result(ToolResult(tool_call_id="tc-2", output="Content 1"))
        t3.add_tool_call(ToolCall(id="tc-3", name="read_file", arguments={"path": "/tmp/file2.txt"}))
        t3.add_tool_result(ToolResult(tool_call_id="tc-3", output="Content 2"))
        t3.complete(Message.assistant("file1 has 'Content 1', file2 has 'Content 2'"))

        # Save
        store.save_transcript(
            "session-1",
            transcript,
            worker_id="developer",
            metadata={"project": "test"}
        )

        # Load and verify
        loaded = store.load_transcript("session-1")

        assert len(loaded) == 3
        assert len(loaded.get_tool_calls()) == 3
        assert len(loaded.get_tool_results()) == 3

        # Check turn 3 has 2 tool calls
        assert len(loaded.turns[2].tool_calls) == 2
        assert len(loaded.turns[2].tool_results) == 2

        # Check metadata
        meta = store.get_session_metadata("session-1")
        assert meta['turn_count'] == 3
        assert meta['tool_call_count'] == 3
        assert meta['worker_id'] == "developer"

        store.close()

    def test_incomplete_turn_persistence(self, tmp_path: Path):
        """Test persisting an incomplete turn (no response yet)."""
        db_path = tmp_path / "test.db"
        store = TranscriptStore(str(db_path))

        transcript = Transcript()
        turn = transcript.new_turn("Processing...")
        # Don't complete the turn

        store.save_transcript("session-1", transcript)
        loaded = store.load_transcript("session-1")

        assert len(loaded) == 1
        assert loaded.turns[0].is_complete is False
        assert loaded.turns[0].response is None
        assert loaded.turns[0].completed_at is None

        store.close()

    def test_multiple_stores_same_db(self, tmp_path: Path):
        """Test multiple store instances accessing same database."""
        db_path = tmp_path / "test.db"

        # Store 1 creates data
        store1 = TranscriptStore(str(db_path))
        transcript = Transcript()
        transcript.new_turn("Hello")
        store1.save_transcript("session-1", transcript)
        store1.close()

        # Store 2 reads data
        store2 = TranscriptStore(str(db_path))
        loaded = store2.load_transcript("session-1")

        assert loaded is not None
        assert loaded.turns[0].prompt.content == "Hello"

        store2.close()


class TestWorkDimensions:
    """Tests for Work dimensions (ask_id, okr_id) in Turn persistence."""

    def test_save_and_load_with_ask_id(self, tmp_path: Path):
        """Test that ask_id is persisted correctly."""
        db_path = tmp_path / "test.db"
        store = TranscriptStore(str(db_path))

        transcript = Transcript()
        turn = transcript.new_turn("Do this task", ask_id="ask-123")
        turn.complete(Message.assistant("Done!"))

        store.save_transcript("session-1", transcript)
        loaded = store.load_transcript("session-1")

        assert loaded.turns[0].ask_id == "ask-123"
        store.close()

    def test_save_and_load_with_okr_id(self, tmp_path: Path):
        """Test that okr_id is persisted correctly."""
        db_path = tmp_path / "test.db"
        store = TranscriptStore(str(db_path))

        transcript = Transcript()
        turn = transcript.new_turn("Improve conversion rate", okr_id="okr-456")
        turn.complete(Message.assistant("Implementing optimization"))

        store.save_transcript("session-1", transcript)
        loaded = store.load_transcript("session-1")

        assert loaded.turns[0].okr_id == "okr-456"
        store.close()

    def test_save_and_load_with_both_dimensions(self, tmp_path: Path):
        """Test that both ask_id and okr_id are persisted together."""
        db_path = tmp_path / "test.db"
        store = TranscriptStore(str(db_path))

        transcript = Transcript()
        turn = transcript.new_turn(
            "Complete quarterly goal task",
            ask_id="ask-789",
            okr_id="okr-q4-revenue"
        )
        turn.complete(Message.assistant("Working on it"))

        store.save_transcript("session-1", transcript)
        loaded = store.load_transcript("session-1")

        assert loaded.turns[0].ask_id == "ask-789"
        assert loaded.turns[0].okr_id == "okr-q4-revenue"
        store.close()

    def test_null_work_dimensions(self, tmp_path: Path):
        """Test that null work dimensions are handled correctly."""
        db_path = tmp_path / "test.db"
        store = TranscriptStore(str(db_path))

        transcript = Transcript()
        turn = transcript.new_turn("Just a regular task")
        turn.complete(Message.assistant("Done"))

        store.save_transcript("session-1", transcript)
        loaded = store.load_transcript("session-1")

        assert loaded.turns[0].ask_id is None
        assert loaded.turns[0].okr_id is None
        store.close()

    def test_work_dimensions_in_to_dict(self, tmp_path: Path):
        """Test that work dimensions appear in to_dict output."""
        transcript = Transcript()
        turn = transcript.new_turn("Task", ask_id="ask-1", okr_id="okr-1")
        turn.complete(Message.assistant("Done"))

        d = turn.to_dict()
        assert d["ask_id"] == "ask-1"
        assert d["okr_id"] == "okr-1"

