"""
Tests for pyterm tool tracking and registry.
"""

import pytest
from datetime import datetime, timedelta

from shared.pyterm.conversation import ToolCall, ToolResult
from shared.pyterm.tools import (
    TrackedCall,
    ToolCallTracker,
    ToolParameter,
    ToolDefinition,
    ToolRegistry,
    BASH_TOOL,
    READ_TOOL,
    WRITE_TOOL,
    EDIT_TOOL,
    GLOB_TOOL,
    GREP_TOOL,
    CLAUDE_CODE_TOOLS,
    create_claude_code_registry,
)


class TestTrackedCall:
    """Tests for TrackedCall class."""

    def test_tracked_call_pending(self):
        tc = ToolCall(id="tc1", name="bash", arguments={"command": "ls"})
        tracked = TrackedCall(call=tc)

        assert tracked.is_pending is True
        assert tracked.is_completed is False
        assert tracked.result is None
        assert tracked.duration_ms is None
        assert tracked.success is None

    def test_tracked_call_completed(self):
        tc = ToolCall(id="tc1", name="bash", arguments={"command": "ls"})
        tracked = TrackedCall(call=tc)

        tr = ToolResult(tool_call_id="tc1", output="file1.txt")
        tracked.result = tr
        tracked.completed_at = tr.timestamp

        assert tracked.is_pending is False
        assert tracked.is_completed is True
        assert tracked.success is True

    def test_tracked_call_duration(self):
        start_time = datetime.now()
        tc = ToolCall(id="tc1", name="bash", arguments={"command": "ls"})
        tc.timestamp = start_time

        tracked = TrackedCall(call=tc)

        # Complete 100ms later
        end_time = start_time + timedelta(milliseconds=100)
        tr = ToolResult(tool_call_id="tc1", output="done")
        tr.timestamp = end_time
        tracked.result = tr
        tracked.completed_at = end_time

        assert tracked.duration_ms == 100


class TestToolCallTracker:
    """Tests for ToolCallTracker class."""

    def test_empty_tracker(self):
        tracker = ToolCallTracker()

        assert tracker.total_calls == 0
        assert tracker.pending_count == 0
        assert tracker.completed_count == 0
        assert tracker.get_pending() == []
        assert tracker.get_completed() == []

    def test_add_call(self):
        tracker = ToolCallTracker()
        tc = ToolCall(id="tc1", name="bash", arguments={"command": "ls"})

        tracker.add_call(tc)

        assert tracker.total_calls == 1
        assert tracker.pending_count == 1
        assert len(tracker.get_pending()) == 1
        assert tracker.get_pending()[0] == tc

    def test_add_result(self):
        tracker = ToolCallTracker()
        tc = ToolCall(id="tc1", name="bash", arguments={"command": "ls"})
        tracker.add_call(tc)

        tr = ToolResult(tool_call_id="tc1", output="file1.txt")
        matched = tracker.add_result(tr)

        assert matched is True
        assert tracker.pending_count == 0
        assert tracker.completed_count == 1

    def test_match_result_to_call(self):
        tracker = ToolCallTracker()
        tc = ToolCall(id="tc1", name="bash", arguments={"command": "ls"})
        tracker.add_call(tc)

        tr = ToolResult(tool_call_id="tc1", output="file1.txt")
        matched = tracker.match_result_to_call(tr)

        assert matched is True
        assert tracker.get_result("tc1") == tr

    def test_match_result_no_matching_call(self):
        tracker = ToolCallTracker()

        tr = ToolResult(tool_call_id="nonexistent", output="file1.txt")
        matched = tracker.match_result_to_call(tr)

        assert matched is False

    def test_multiple_calls_and_results(self):
        tracker = ToolCallTracker()

        # Add multiple calls
        tc1 = ToolCall(id="tc1", name="bash", arguments={"command": "ls"})
        tc2 = ToolCall(id="tc2", name="read", arguments={"file_path": "/tmp/x"})
        tc3 = ToolCall(id="tc3", name="write", arguments={"file_path": "/tmp/y", "content": "hello"})

        tracker.add_call(tc1)
        tracker.add_call(tc2)
        tracker.add_call(tc3)

        assert tracker.total_calls == 3
        assert tracker.pending_count == 3

        # Complete first two
        tr1 = ToolResult(tool_call_id="tc1", output="file1.txt")
        tr2 = ToolResult(tool_call_id="tc2", output="content", success=True)

        tracker.add_result(tr1)
        tracker.add_result(tr2)

        assert tracker.pending_count == 1
        assert tracker.completed_count == 2
        assert tracker.get_pending()[0] == tc3

    def test_get_call(self):
        tracker = ToolCallTracker()
        tc = ToolCall(id="tc1", name="bash", arguments={"command": "ls"})
        tracker.add_call(tc)

        tracked = tracker.get_call("tc1")
        assert tracked is not None
        assert tracked.call == tc

        missing = tracker.get_call("nonexistent")
        assert missing is None

    def test_success_rate_all_successful(self):
        tracker = ToolCallTracker()

        for i in range(3):
            tc = ToolCall(id=f"tc{i}", name="bash", arguments={})
            tracker.add_call(tc)
            tr = ToolResult(tool_call_id=f"tc{i}", output="ok", success=True)
            tracker.add_result(tr)

        assert tracker.success_rate == 1.0

    def test_success_rate_mixed(self):
        tracker = ToolCallTracker()

        # 2 successful, 2 failed
        for i in range(4):
            tc = ToolCall(id=f"tc{i}", name="bash", arguments={})
            tracker.add_call(tc)
            success = i < 2
            tr = ToolResult(
                tool_call_id=f"tc{i}",
                output="" if not success else "ok",
                success=success,
                error=None if success else "failed",
            )
            tracker.add_result(tr)

        assert tracker.success_rate == 0.5

    def test_success_rate_no_completed(self):
        tracker = ToolCallTracker()
        tc = ToolCall(id="tc1", name="bash", arguments={})
        tracker.add_call(tc)

        assert tracker.success_rate == 0.0

    def test_avg_duration_ms(self):
        tracker = ToolCallTracker()

        # Create calls with known durations
        base_time = datetime.now()
        durations = [100, 200, 300]

        for i, duration in enumerate(durations):
            tc = ToolCall(id=f"tc{i}", name="bash", arguments={})
            tc.timestamp = base_time
            tracker.add_call(tc)

            tr = ToolResult(tool_call_id=f"tc{i}", output="ok")
            tr.timestamp = base_time + timedelta(milliseconds=duration)
            tracker.add_result(tr)

        assert tracker.avg_duration_ms == 200.0  # (100 + 200 + 300) / 3

    def test_avg_duration_no_completed(self):
        tracker = ToolCallTracker()
        assert tracker.avg_duration_ms == 0.0

    def test_get_calls_by_tool(self):
        tracker = ToolCallTracker()

        # Add mixed tool calls
        tracker.add_call(ToolCall(id="tc1", name="bash", arguments={}))
        tracker.add_call(ToolCall(id="tc2", name="read", arguments={}))
        tracker.add_call(ToolCall(id="tc3", name="bash", arguments={}))

        bash_calls = tracker.get_calls_by_tool("bash")
        read_calls = tracker.get_calls_by_tool("read")
        write_calls = tracker.get_calls_by_tool("write")

        assert len(bash_calls) == 2
        assert len(read_calls) == 1
        assert len(write_calls) == 0

    def test_clear(self):
        tracker = ToolCallTracker()
        tracker.add_call(ToolCall(id="tc1", name="bash", arguments={}))
        tracker.add_call(ToolCall(id="tc2", name="read", arguments={}))

        assert tracker.total_calls == 2

        tracker.clear()

        assert tracker.total_calls == 0
        assert tracker.get_pending() == []

    def test_to_dict(self):
        tracker = ToolCallTracker()
        tc = ToolCall(id="tc1", name="bash", arguments={"command": "ls"})
        tracker.add_call(tc)

        tr = ToolResult(tool_call_id="tc1", output="file.txt")
        tracker.add_result(tr)

        d = tracker.to_dict()

        assert d["total_calls"] == 1
        assert d["pending_count"] == 0
        assert d["completed_count"] == 1
        assert d["success_rate"] == 1.0
        assert "calls" in d
        assert "tc1" in d["calls"]
        assert d["calls"]["tc1"]["tool_name"] == "bash"
        assert d["calls"]["tc1"]["is_pending"] is False


class TestToolParameter:
    """Tests for ToolParameter class."""

    def test_required_parameter(self):
        param = ToolParameter(
            name="command",
            type="string",
            description="The command to execute",
            required=True,
        )
        assert param.name == "command"
        assert param.type == "string"
        assert param.required is True
        assert param.default is None

    def test_optional_parameter_with_default(self):
        param = ToolParameter(
            name="timeout",
            type="number",
            description="Timeout in ms",
            required=False,
            default=5000,
        )
        assert param.required is False
        assert param.default == 5000


class TestToolDefinition:
    """Tests for ToolDefinition class."""

    def test_tool_definition_creation(self):
        tool = ToolDefinition(
            name="test_tool",
            description="A test tool",
            parameters=[
                ToolParameter(name="arg1", type="string", description="First arg", required=True),
                ToolParameter(name="arg2", type="number", description="Second arg", required=False),
            ],
        )

        assert tool.name == "test_tool"
        assert tool.description == "A test tool"
        assert len(tool.parameters) == 2

    def test_required_params(self):
        tool = ToolDefinition(
            name="test_tool",
            description="A test tool",
            parameters=[
                ToolParameter(name="required1", type="string", description="", required=True),
                ToolParameter(name="optional1", type="string", description="", required=False),
                ToolParameter(name="required2", type="string", description="", required=True),
            ],
        )

        assert tool.required_params == ["required1", "required2"]

    def test_optional_params(self):
        tool = ToolDefinition(
            name="test_tool",
            description="A test tool",
            parameters=[
                ToolParameter(name="required1", type="string", description="", required=True),
                ToolParameter(name="optional1", type="string", description="", required=False),
                ToolParameter(name="optional2", type="number", description="", required=False),
            ],
        )

        assert tool.optional_params == ["optional1", "optional2"]

    def test_to_schema(self):
        tool = ToolDefinition(
            name="test_tool",
            description="A test tool",
            parameters=[
                ToolParameter(name="command", type="string", description="Command to run", required=True),
                ToolParameter(name="timeout", type="number", description="Timeout", required=False, default=5000),
            ],
        )

        schema = tool.to_schema()

        assert schema["name"] == "test_tool"
        assert schema["description"] == "A test tool"
        assert "parameters" in schema
        assert schema["parameters"]["type"] == "object"
        assert "command" in schema["parameters"]["properties"]
        assert schema["parameters"]["properties"]["timeout"]["default"] == 5000
        assert schema["parameters"]["required"] == ["command"]


class TestToolRegistry:
    """Tests for ToolRegistry class."""

    def test_empty_registry(self):
        registry = ToolRegistry()

        assert registry.list_tools() == []
        assert registry.has("bash") is False
        assert registry.get("bash") is None

    def test_register_tool(self):
        registry = ToolRegistry()
        tool = ToolDefinition(name="test", description="Test tool")

        registry.register(tool)

        assert registry.has("test") is True
        assert registry.get("test") == tool
        assert "test" in registry.list_tools()

    def test_validate_call_valid(self):
        registry = ToolRegistry()
        registry.register(
            ToolDefinition(
                name="read",
                description="Read file",
                parameters=[
                    ToolParameter(name="file_path", type="string", description="Path", required=True),
                ],
            )
        )

        tc = ToolCall(id="tc1", name="read", arguments={"file_path": "/tmp/x"})
        valid, error = registry.validate_call(tc)

        assert valid is True
        assert error is None

    def test_validate_call_unknown_tool(self):
        registry = ToolRegistry()

        tc = ToolCall(id="tc1", name="unknown", arguments={})
        valid, error = registry.validate_call(tc)

        assert valid is False
        assert "Unknown tool" in error

    def test_validate_call_missing_required(self):
        registry = ToolRegistry()
        registry.register(
            ToolDefinition(
                name="write",
                description="Write file",
                parameters=[
                    ToolParameter(name="file_path", type="string", description="Path", required=True),
                    ToolParameter(name="content", type="string", description="Content", required=True),
                ],
            )
        )

        tc = ToolCall(id="tc1", name="write", arguments={"file_path": "/tmp/x"})
        valid, error = registry.validate_call(tc)

        assert valid is False
        assert "Missing required parameter" in error
        assert "content" in error

    def test_validate_call_unknown_parameter(self):
        registry = ToolRegistry()
        registry.register(
            ToolDefinition(
                name="bash",
                description="Run command",
                parameters=[
                    ToolParameter(name="command", type="string", description="Command", required=True),
                ],
            )
        )

        tc = ToolCall(id="tc1", name="bash", arguments={"command": "ls", "unknown_arg": "value"})
        valid, error = registry.validate_call(tc)

        assert valid is False
        assert "Unknown parameter" in error
        assert "unknown_arg" in error

    def test_get_description(self):
        registry = ToolRegistry()
        registry.register(ToolDefinition(name="bash", description="Execute bash commands"))

        assert registry.get_description("bash") == "Execute bash commands"
        assert registry.get_description("nonexistent") is None

    def test_get_required_args(self):
        registry = ToolRegistry()
        registry.register(
            ToolDefinition(
                name="write",
                description="Write file",
                parameters=[
                    ToolParameter(name="file_path", type="string", description="", required=True),
                    ToolParameter(name="content", type="string", description="", required=True),
                    ToolParameter(name="mode", type="string", description="", required=False),
                ],
            )
        )

        required = registry.get_required_args("write")
        assert required == ["file_path", "content"]

    def test_get_optional_args(self):
        registry = ToolRegistry()
        registry.register(
            ToolDefinition(
                name="bash",
                description="Run command",
                parameters=[
                    ToolParameter(name="command", type="string", description="", required=True),
                    ToolParameter(name="timeout", type="number", description="", required=False),
                    ToolParameter(name="description", type="string", description="", required=False),
                ],
            )
        )

        optional = registry.get_optional_args("bash")
        assert optional == ["timeout", "description"]

    def test_to_schemas(self):
        registry = ToolRegistry()
        registry.register(ToolDefinition(name="tool1", description="First tool"))
        registry.register(ToolDefinition(name="tool2", description="Second tool"))

        schemas = registry.to_schemas()

        assert len(schemas) == 2
        names = [s["name"] for s in schemas]
        assert "tool1" in names
        assert "tool2" in names

    def test_clear(self):
        registry = ToolRegistry()
        registry.register(ToolDefinition(name="tool1", description="First tool"))
        registry.register(ToolDefinition(name="tool2", description="Second tool"))

        assert len(registry.list_tools()) == 2

        registry.clear()

        assert len(registry.list_tools()) == 0


class TestClaudeCodeTools:
    """Tests for Claude Code tool definitions."""

    def test_bash_tool_definition(self):
        assert BASH_TOOL.name == "Bash"
        assert "command" in BASH_TOOL.required_params
        assert "timeout" in BASH_TOOL.optional_params

    def test_read_tool_definition(self):
        assert READ_TOOL.name == "Read"
        assert "file_path" in READ_TOOL.required_params
        assert "offset" in READ_TOOL.optional_params
        assert "limit" in READ_TOOL.optional_params

    def test_write_tool_definition(self):
        assert WRITE_TOOL.name == "Write"
        assert set(WRITE_TOOL.required_params) == {"file_path", "content"}

    def test_edit_tool_definition(self):
        assert EDIT_TOOL.name == "Edit"
        assert set(EDIT_TOOL.required_params) == {"file_path", "old_string", "new_string"}
        assert "replace_all" in EDIT_TOOL.optional_params

    def test_glob_tool_definition(self):
        assert GLOB_TOOL.name == "Glob"
        assert "pattern" in GLOB_TOOL.required_params
        assert "path" in GLOB_TOOL.optional_params

    def test_grep_tool_definition(self):
        assert GREP_TOOL.name == "Grep"
        assert "pattern" in GREP_TOOL.required_params
        assert "path" in GREP_TOOL.optional_params
        assert "glob" in GREP_TOOL.optional_params

    def test_claude_code_tools_list(self):
        assert len(CLAUDE_CODE_TOOLS) >= 10

        tool_names = [t.name for t in CLAUDE_CODE_TOOLS]
        expected = ["Bash", "Read", "Write", "Edit", "Glob", "Grep", "WebFetch", "WebSearch"]
        for name in expected:
            assert name in tool_names

    def test_create_claude_code_registry(self):
        registry = create_claude_code_registry()

        assert registry.has("Bash")
        assert registry.has("Read")
        assert registry.has("Write")
        assert registry.has("Edit")
        assert registry.has("Glob")
        assert registry.has("Grep")

    def test_validate_bash_call(self):
        registry = create_claude_code_registry()

        # Valid call
        tc = ToolCall(id="tc1", name="Bash", arguments={"command": "ls -la"})
        valid, error = registry.validate_call(tc)
        assert valid is True

        # Invalid - missing command
        tc2 = ToolCall(id="tc2", name="Bash", arguments={})
        valid2, error2 = registry.validate_call(tc2)
        assert valid2 is False

    def test_validate_read_call(self):
        registry = create_claude_code_registry()

        tc = ToolCall(id="tc1", name="Read", arguments={"file_path": "/tmp/test.txt"})
        valid, error = registry.validate_call(tc)
        assert valid is True

        # With optional params
        tc2 = ToolCall(id="tc2", name="Read", arguments={"file_path": "/tmp/x", "offset": 10, "limit": 50})
        valid2, error2 = registry.validate_call(tc2)
        assert valid2 is True

    def test_validate_edit_call(self):
        registry = create_claude_code_registry()

        tc = ToolCall(
            id="tc1",
            name="Edit",
            arguments={
                "file_path": "/tmp/test.txt",
                "old_string": "foo",
                "new_string": "bar",
            },
        )
        valid, error = registry.validate_call(tc)
        assert valid is True


class TestIntegration:
    """Integration tests for tool tracking and registry."""

    def test_track_tool_calls_with_validation(self):
        """Test tracking tool calls that are validated against registry."""
        registry = create_claude_code_registry()
        tracker = ToolCallTracker()

        # Simulate a sequence of tool calls
        calls = [
            ToolCall(id="tc1", name="Read", arguments={"file_path": "/tmp/a.txt"}),
            ToolCall(id="tc2", name="Edit", arguments={"file_path": "/tmp/a.txt", "old_string": "x", "new_string": "y"}),
            ToolCall(id="tc3", name="Bash", arguments={"command": "cat /tmp/a.txt"}),
        ]

        # Validate and track
        for call in calls:
            valid, error = registry.validate_call(call)
            assert valid is True, f"Validation failed for {call.name}: {error}"
            tracker.add_call(call)

        assert tracker.total_calls == 3
        assert tracker.pending_count == 3

        # Add results
        tracker.add_result(ToolResult(tool_call_id="tc1", output="file contents"))
        tracker.add_result(ToolResult(tool_call_id="tc2", output="edit successful"))
        tracker.add_result(ToolResult(tool_call_id="tc3", output="y"))

        assert tracker.pending_count == 0
        assert tracker.completed_count == 3
        assert tracker.success_rate == 1.0

    def test_track_failed_tool_calls(self):
        """Test tracking tool calls with failures."""
        tracker = ToolCallTracker()

        tc1 = ToolCall(id="tc1", name="Read", arguments={"file_path": "/nonexistent"})
        tc2 = ToolCall(id="tc2", name="Bash", arguments={"command": "invalid_command"})

        tracker.add_call(tc1)
        tracker.add_call(tc2)

        tracker.add_result(
            ToolResult(tool_call_id="tc1", output="", success=False, error="File not found")
        )
        tracker.add_result(
            ToolResult(tool_call_id="tc2", output="", success=False, error="Command not found")
        )

        assert tracker.success_rate == 0.0
        assert tracker.completed_count == 2

        completed = tracker.get_completed()
        assert all(tc.success is False for tc in completed)
