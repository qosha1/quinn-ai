"""
Tests for pyterm conversation model.
"""

import pytest
from datetime import datetime

from shared.pyterm.conversation import (
    Message,
    MessageRole,
    ToolCall,
    ToolResult,
    Turn,
    Transcript,
)


class TestMessage:
    """Tests for Message class."""

    def test_user_message_creation(self):
        msg = Message.user("Hello, agent!")
        assert msg.role == MessageRole.USER
        assert msg.content == "Hello, agent!"
        assert msg.tool_call is None
        assert msg.tool_result is None

    def test_assistant_message_creation(self):
        msg = Message.assistant("Hello, human!")
        assert msg.role == MessageRole.ASSISTANT
        assert msg.content == "Hello, human!"

    def test_message_with_metadata(self):
        msg = Message.user("Test", source="cli", worker_id="w1")
        assert msg.metadata["source"] == "cli"
        assert msg.metadata["worker_id"] == "w1"

    def test_message_to_dict(self):
        msg = Message.user("Test")
        d = msg.to_dict()
        assert d["role"] == "user"
        assert d["content"] == "Test"
        assert "timestamp" in d

    def test_message_from_tool_call(self):
        tc = ToolCall(id="tc1", name="read_file", arguments={"path": "/tmp/x"})
        msg = Message.from_tool_call(tc)
        assert msg.role == MessageRole.TOOL_CALL
        assert msg.tool_call == tc
        assert "read_file" in msg.content

    def test_message_from_tool_result(self):
        tr = ToolResult(tool_call_id="tc1", output="file contents here")
        msg = Message.from_tool_result(tr)
        assert msg.role == MessageRole.TOOL_RESULT
        assert msg.tool_result == tr


class TestToolCall:
    """Tests for ToolCall class."""

    def test_tool_call_creation(self):
        tc = ToolCall(id="tc1", name="bash", arguments={"command": "ls"})
        assert tc.id == "tc1"
        assert tc.name == "bash"
        assert tc.arguments == {"command": "ls"}

    def test_tool_call_to_dict(self):
        tc = ToolCall(id="tc1", name="bash", arguments={"command": "ls"})
        d = tc.to_dict()
        assert d["id"] == "tc1"
        assert d["name"] == "bash"
        assert d["arguments"] == {"command": "ls"}
        assert "timestamp" in d


class TestToolResult:
    """Tests for ToolResult class."""

    def test_tool_result_success(self):
        tr = ToolResult(tool_call_id="tc1", output="success output")
        assert tr.tool_call_id == "tc1"
        assert tr.output == "success output"
        assert tr.success is True
        assert tr.error is None

    def test_tool_result_failure(self):
        tr = ToolResult(tool_call_id="tc1", output="", success=False, error="File not found")
        assert tr.success is False
        assert tr.error == "File not found"

    def test_tool_result_to_dict(self):
        tr = ToolResult(tool_call_id="tc1", output="result")
        d = tr.to_dict()
        assert d["tool_call_id"] == "tc1"
        assert d["output"] == "result"
        assert d["success"] is True


class TestTurn:
    """Tests for Turn class."""

    def test_turn_creation(self):
        prompt = Message.user("What is 2+2?")
        turn = Turn(id="t1", prompt=prompt)
        assert turn.id == "t1"
        assert turn.prompt == prompt
        assert turn.response is None
        assert turn.is_complete is False

    def test_turn_completion(self):
        prompt = Message.user("What is 2+2?")
        turn = Turn(id="t1", prompt=prompt)

        response = Message.assistant("4")
        turn.complete(response)

        assert turn.is_complete is True
        assert turn.response == response
        assert turn.completed_at is not None
        assert turn.duration_ms is not None
        assert turn.duration_ms >= 0

    def test_turn_with_tool_calls(self):
        prompt = Message.user("Read the file")
        turn = Turn(id="t1", prompt=prompt)

        tc = ToolCall(id="tc1", name="read_file", arguments={"path": "/tmp/x"})
        turn.add_tool_call(tc)

        tr = ToolResult(tool_call_id="tc1", output="file contents")
        turn.add_tool_result(tr)

        assert len(turn.tool_calls) == 1
        assert len(turn.tool_results) == 1

    def test_turn_get_messages(self):
        prompt = Message.user("Do something")
        turn = Turn(id="t1", prompt=prompt)

        tc = ToolCall(id="tc1", name="bash", arguments={})
        turn.add_tool_call(tc)

        tr = ToolResult(tool_call_id="tc1", output="done")
        turn.add_tool_result(tr)

        response = Message.assistant("I did it")
        turn.complete(response)

        messages = turn.get_messages()
        assert len(messages) == 4  # prompt + tool_call + tool_result + response
        assert messages[0].role == MessageRole.USER
        assert messages[-1].role == MessageRole.ASSISTANT

    def test_turn_to_dict(self):
        prompt = Message.user("Test")
        turn = Turn(id="t1", prompt=prompt)
        d = turn.to_dict()
        assert d["id"] == "t1"
        assert d["prompt"]["content"] == "Test"
        assert d["is_complete"] is False


class TestTranscript:
    """Tests for Transcript class."""

    def test_empty_transcript(self):
        transcript = Transcript()
        assert len(transcript) == 0
        assert transcript.current_turn() is None
        assert transcript.get_messages() == []

    def test_new_turn(self):
        transcript = Transcript()
        turn = transcript.new_turn("Hello")

        assert len(transcript) == 1
        assert turn.prompt.content == "Hello"
        assert transcript.current_turn() == turn

    def test_multiple_turns(self):
        transcript = Transcript()
        turn1 = transcript.new_turn("First")
        turn1.complete(Message.assistant("Response 1"))

        turn2 = transcript.new_turn("Second")
        turn2.complete(Message.assistant("Response 2"))

        assert len(transcript) == 2
        assert transcript.current_turn() == turn2

    def test_get_turn_by_id(self):
        transcript = Transcript()
        turn = transcript.new_turn("Test")

        found = transcript.get_turn(turn.id)
        assert found == turn

        not_found = transcript.get_turn("nonexistent")
        assert not_found is None

    def test_get_user_messages(self):
        transcript = Transcript()
        transcript.new_turn("First").complete(Message.assistant("R1"))
        transcript.new_turn("Second").complete(Message.assistant("R2"))

        user_msgs = transcript.get_user_messages()
        assert len(user_msgs) == 2
        assert all(m.role == MessageRole.USER for m in user_msgs)

    def test_get_assistant_messages(self):
        transcript = Transcript()
        transcript.new_turn("First").complete(Message.assistant("R1"))
        transcript.new_turn("Second").complete(Message.assistant("R2"))

        asst_msgs = transcript.get_assistant_messages()
        assert len(asst_msgs) == 2
        assert all(m.role == MessageRole.ASSISTANT for m in asst_msgs)

    def test_get_tool_calls(self):
        transcript = Transcript()
        turn = transcript.new_turn("Do stuff")
        turn.add_tool_call(ToolCall(id="tc1", name="bash", arguments={}))
        turn.add_tool_call(ToolCall(id="tc2", name="read", arguments={}))

        calls = transcript.get_tool_calls()
        assert len(calls) == 2

    def test_transcript_to_dict(self):
        transcript = Transcript()
        turn = transcript.new_turn("Hello")
        turn.add_tool_call(ToolCall(id="tc1", name="test", arguments={}))
        turn.complete(Message.assistant("Hi"))

        d = transcript.to_dict()
        assert d["total_turns"] == 1
        assert d["total_messages"] == 3  # user + tool_call + assistant
        assert d["total_tool_calls"] == 1

    def test_transcript_to_text(self):
        transcript = Transcript()
        turn = transcript.new_turn("What is 2+2?")
        turn.complete(Message.assistant("4"))

        text = transcript.to_text()
        assert "User: What is 2+2?" in text
        assert "Assistant: 4" in text

    def test_transcript_iteration(self):
        transcript = Transcript()
        transcript.new_turn("First")
        transcript.new_turn("Second")

        turns = list(transcript)
        assert len(turns) == 2

    def test_transcript_clear(self):
        transcript = Transcript()
        transcript.new_turn("Test")
        assert len(transcript) == 1

        transcript.clear()
        assert len(transcript) == 0


class TestIntegration:
    """Integration tests for conversation model."""

    def test_full_conversation_flow(self):
        """Test a complete conversation with tool use."""
        transcript = Transcript()

        # Turn 1: Simple question
        turn1 = transcript.new_turn("What time is it?")
        turn1.complete(Message.assistant("It is 3:00 PM"))

        # Turn 2: With tool use
        turn2 = transcript.new_turn("Read /tmp/test.txt")
        tc = ToolCall(id="tc1", name="read_file", arguments={"path": "/tmp/test.txt"})
        turn2.add_tool_call(tc)
        tr = ToolResult(tool_call_id="tc1", output="Hello World")
        turn2.add_tool_result(tr)
        turn2.complete(Message.assistant("The file contains: Hello World"))

        # Turn 3: Follow-up
        turn3 = transcript.new_turn("Thanks!")
        turn3.complete(Message.assistant("You're welcome!"))

        # Verify
        assert len(transcript) == 3
        assert len(transcript.get_tool_calls()) == 1
        assert len(transcript.get_messages()) == 8  # 3 user + 3 assistant + 1 tool_call + 1 tool_result

        # All turns complete
        assert all(t.is_complete for t in transcript)

    def test_conversation_serialization(self):
        """Test that conversation can be serialized and has expected structure."""
        transcript = Transcript()
        turn = transcript.new_turn("Hello", worker_id="ceo")
        turn.add_tool_call(ToolCall(id="tc1", name="bash", arguments={"cmd": "ls"}))
        turn.add_tool_result(ToolResult(tool_call_id="tc1", output="file1.txt"))
        turn.complete(Message.assistant("Done"))

        d = transcript.to_dict()

        # Check structure
        assert "turns" in d
        assert len(d["turns"]) == 1

        turn_dict = d["turns"][0]
        assert "prompt" in turn_dict
        assert "response" in turn_dict
        assert "tool_calls" in turn_dict
        assert "tool_results" in turn_dict
        assert turn_dict["is_complete"] is True
