"""
Tests for pyterm output parsers.
"""

import pytest

from shared.pyterm.agent_state import AgentState
from shared.pyterm.parsers import (
    ClaudeCodeParser,
    GenericParser,
    ParsedOutput,
    get_parser,
    CLAUDE_CODE_TOOL_NAMES,
)


# Sample outputs for testing
SAMPLE_IDLE_OUTPUT = """
I have completed the task.

>
"""

SAMPLE_THINKING_OUTPUT = """
Let me analyze this codebase to understand the structure.
I will look at the main entry points and understand how the modules
are connected.
"""

SAMPLE_TOOL_CALL_OUTPUT = """
Let me read that file.

<function_calls>
<invoke name="Read">
<parameter name="file_path">/tmp/test.txt</parameter>
</invoke>
</function_calls>
"""

SAMPLE_MULTI_TOOL_OUTPUT = """
I will run these commands.

<function_calls>
<invoke name="Bash">
<parameter name="command">ls -la</parameter>
<parameter name="description">List files</parameter>
</invoke>
<invoke name="Read">
<parameter name="file_path">/etc/hosts</parameter>
</invoke>
</function_calls>
"""

SAMPLE_TOOL_RESULT_OUTPUT = """
<function_results>
<result>
file1.txt
file2.txt
</result>
</function_results>
"""

SAMPLE_ERROR_OUTPUT = """
Error: File not found
The specified path does not exist.
"""

SAMPLE_WAITING_INPUT = """
This will delete all files. Continue? (y/n)
"""


class TestClaudeCodeParser:
    """Tests for ClaudeCodeParser."""

    def test_provider_name(self):
        parser = ClaudeCodeParser()
        assert parser.provider_name == "claude-code"

    def test_detect_idle_state(self):
        parser = ClaudeCodeParser()
        state = parser.detect_state(SAMPLE_IDLE_OUTPUT)
        assert state == AgentState.IDLE

    def test_detect_thinking_state(self):
        parser = ClaudeCodeParser()
        state = parser.detect_state(SAMPLE_THINKING_OUTPUT)
        assert state == AgentState.THINKING

    def test_detect_executing_state_with_results(self):
        parser = ClaudeCodeParser()
        state = parser.detect_state(SAMPLE_TOOL_RESULT_OUTPUT)
        assert state == AgentState.EXECUTING_TOOL

    def test_detect_executing_state_with_invocation(self):
        parser = ClaudeCodeParser()
        state = parser.detect_state(SAMPLE_TOOL_CALL_OUTPUT)
        assert state == AgentState.EXECUTING_TOOL

    def test_detect_error_state(self):
        parser = ClaudeCodeParser()
        state = parser.detect_state(SAMPLE_ERROR_OUTPUT)
        assert state == AgentState.ERROR

    def test_detect_prompt_ready(self):
        parser = ClaudeCodeParser()
        assert parser.detect_prompt_ready(SAMPLE_IDLE_OUTPUT) is True
        assert parser.detect_prompt_ready(SAMPLE_THINKING_OUTPUT) is False
        assert parser.detect_prompt_ready("some text\n>") is True
        assert parser.detect_prompt_ready("some text\n> ") is True
        assert parser.detect_prompt_ready("some text") is False

    def test_extract_single_tool_call(self):
        parser = ClaudeCodeParser()
        tool_calls = parser.extract_tool_calls(SAMPLE_TOOL_CALL_OUTPUT)
        assert len(tool_calls) == 1
        assert tool_calls[0].name == "Read"
        assert tool_calls[0].arguments["file_path"] == "/tmp/test.txt"

    def test_extract_multiple_tool_calls(self):
        parser = ClaudeCodeParser()
        tool_calls = parser.extract_tool_calls(SAMPLE_MULTI_TOOL_OUTPUT)
        assert len(tool_calls) == 2
        assert tool_calls[0].name == "Bash"
        assert tool_calls[0].arguments["command"] == "ls -la"
        assert tool_calls[0].arguments["description"] == "List files"
        assert tool_calls[1].name == "Read"
        assert tool_calls[1].arguments["file_path"] == "/etc/hosts"

    def test_extract_no_tool_calls(self):
        parser = ClaudeCodeParser()
        tool_calls = parser.extract_tool_calls(SAMPLE_THINKING_OUTPUT)
        assert len(tool_calls) == 0

    def test_extract_assistant_response(self):
        parser = ClaudeCodeParser()
        response = parser.extract_assistant_response(SAMPLE_IDLE_OUTPUT)
        assert "completed the task" in response
        assert ">" not in response

    def test_extract_assistant_response_strips_tool_blocks(self):
        parser = ClaudeCodeParser()
        response = parser.extract_assistant_response(SAMPLE_TOOL_CALL_OUTPUT)
        assert "read that file" in response.lower()
        assert "<invoke" not in response
        assert "<parameter" not in response

    def test_parse_output_complete(self):
        parser = ClaudeCodeParser()
        result = parser.parse_output(SAMPLE_TOOL_CALL_OUTPUT)
        assert isinstance(result, ParsedOutput)
        assert result.state == AgentState.EXECUTING_TOOL
        assert len(result.tool_calls) == 1
        assert result.prompt_ready is False
        assert result.metadata["provider"] == "claude-code"

    def test_error_extraction(self):
        parser = ClaudeCodeParser()
        result = parser.parse_output(SAMPLE_ERROR_OUTPUT)
        assert result.state == AgentState.ERROR
        assert result.error_message is not None
        assert "File not found" in result.error_message

    def test_tool_call_ids_are_unique(self):
        parser = ClaudeCodeParser()
        tool_calls = parser.extract_tool_calls(SAMPLE_MULTI_TOOL_OUTPUT)
        ids = [tc.id for tc in tool_calls]
        assert len(ids) == len(set(ids))  # All unique


class TestGenericParser:
    """Tests for GenericParser."""

    def test_provider_name(self):
        parser = GenericParser()
        assert parser.provider_name == "generic"

    def test_detect_idle_state(self):
        parser = GenericParser()
        assert parser.detect_state(">\n") == AgentState.IDLE
        assert parser.detect_state("$\n") == AgentState.IDLE
        assert parser.detect_state(">>>\n") == AgentState.IDLE

    def test_detect_error_state(self):
        parser = GenericParser()
        assert parser.detect_state("Error: something broke") == AgentState.ERROR
        assert parser.detect_state("Traceback (most recent call last)") == AgentState.ERROR
        assert parser.detect_state("FAILED to connect") == AgentState.ERROR

    def test_detect_waiting_input(self):
        parser = GenericParser()
        assert parser.detect_state("Continue? (y/n)") == AgentState.WAITING_INPUT
        assert parser.detect_state("Press Enter to continue") == AgentState.WAITING_INPUT

    def test_detect_executing(self):
        parser = GenericParser()
        assert parser.detect_state("$ ls -la") == AgentState.EXECUTING_TOOL
        assert parser.detect_state("> command here") == AgentState.EXECUTING_TOOL

    def test_detect_thinking(self):
        parser = GenericParser()
        assert parser.detect_state("Processing your request...") == AgentState.THINKING
        assert parser.detect_state("Please wait while loading") == AgentState.THINKING

    def test_no_tool_call_extraction(self):
        """Generic parser should not extract tool calls."""
        parser = GenericParser()
        tool_calls = parser.extract_tool_calls(SAMPLE_TOOL_CALL_OUTPUT)
        assert len(tool_calls) == 0

    def test_extract_assistant_response(self):
        parser = GenericParser()
        response = parser.extract_assistant_response("Hello world\n>\n")
        assert "Hello world" in response

    def test_parse_output(self):
        parser = GenericParser()
        result = parser.parse_output("Processing...\nDone\n>\n")
        assert result.prompt_ready is True
        assert result.state == AgentState.IDLE


class TestGetParser:
    """Tests for get_parser factory function."""

    def test_get_claude_code_parser(self):
        parser = get_parser("claude-code")
        assert isinstance(parser, ClaudeCodeParser)

    def test_get_claude_alias(self):
        parser = get_parser("claude")
        assert isinstance(parser, ClaudeCodeParser)

    def test_get_generic_parser_for_unknown(self):
        parser = get_parser("unknown-provider")
        assert isinstance(parser, GenericParser)

    def test_case_insensitive(self):
        parser = get_parser("CLAUDE-CODE")
        assert isinstance(parser, ClaudeCodeParser)


class TestParsedOutput:
    """Tests for ParsedOutput dataclass."""

    def test_to_dict(self):
        parser = ClaudeCodeParser()
        result = parser.parse_output(SAMPLE_TOOL_CALL_OUTPUT)
        d = result.to_dict()
        assert "raw" in d
        assert "state" in d
        assert "tool_calls" in d
        assert "assistant_response" in d
        assert "prompt_ready" in d

    def test_state_serialization(self):
        parser = ClaudeCodeParser()
        result = parser.parse_output(SAMPLE_IDLE_OUTPUT)
        d = result.to_dict()
        assert d["state"] == "idle"


class TestEdgeCases:
    """Tests for edge cases and error handling."""

    def test_empty_input(self):
        parser = ClaudeCodeParser()
        result = parser.parse_output("")
        assert result.state == AgentState.IDLE
        assert len(result.tool_calls) == 0
        assert result.assistant_response == ""

    def test_whitespace_only_input(self):
        parser = ClaudeCodeParser()
        result = parser.parse_output("   \n\n   ")
        assert result.state == AgentState.IDLE

    def test_malformed_tool_call(self):
        """Parser should handle malformed XML gracefully."""
        parser = ClaudeCodeParser()
        malformed = "<invoke name=\"Bash\">no closing tag"
        result = parser.parse_output(malformed)
        # Should not crash, may or may not extract tool call
        assert isinstance(result, ParsedOutput)

    def test_partial_tool_call(self):
        """Parser should handle incomplete tool calls."""
        parser = ClaudeCodeParser()
        partial = "<function_calls>\n<invoke name=\"Read\""
        result = parser.parse_output(partial)
        assert isinstance(result, ParsedOutput)
        # State should indicate execution in progress
        assert result.state == AgentState.EXECUTING_TOOL

    def test_nested_content_in_parameter(self):
        """Parameters may contain special characters."""
        parser = ClaudeCodeParser()
        content = """
<function_calls>
<invoke name="Write">
<parameter name="content">def hello():\n    print("hi")</parameter>
</invoke>
</function_calls>
"""
        tool_calls = parser.extract_tool_calls(content)
        assert len(tool_calls) == 1
        assert "def hello" in tool_calls[0].arguments.get("content", "")

    def test_unicode_content(self):
        """Parser should handle unicode content."""
        parser = ClaudeCodeParser()
        result = parser.parse_output("Processing... \u2713 Done!")
        assert isinstance(result, ParsedOutput)

    def test_very_long_output(self):
        """Parser should handle very long outputs."""
        parser = ClaudeCodeParser()
        long_output = "x" * 100000 + "\n>"
        result = parser.parse_output(long_output)
        assert result.state == AgentState.IDLE
        assert result.prompt_ready is True


class TestClaudeCodeToolNames:
    """Tests for CLAUDE_CODE_TOOL_NAMES constant."""

    def test_contains_expected_tools(self):
        expected = ["Bash", "Read", "Write", "Edit", "Glob", "Grep"]
        for tool in expected:
            assert tool in CLAUDE_CODE_TOOL_NAMES

    def test_is_immutable(self):
        """Tool names set should be a frozenset."""
        assert isinstance(CLAUDE_CODE_TOOL_NAMES, frozenset)

