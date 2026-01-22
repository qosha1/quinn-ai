"""
Claude Code CLI output parser.

Parses terminal output from the Claude Code CLI to extract:
- Agent state (idle, thinking, executing)
- Tool calls (Bash, Read, Edit, Write, Grep, Glob, etc.)
- Assistant responses
- Prompt readiness
"""

import re
import uuid
from dataclasses import dataclass, field
from typing import Any

from shared.pyterm.agent_state import AgentState
from shared.pyterm.conversation import ToolCall
from shared.pyterm.parsers.base import OutputParser, ParsedOutput


# Known Claude Code tool names
CLAUDE_CODE_TOOL_NAMES = frozenset([
    "Bash",
    "Read",
    "Write",
    "Edit",
    "Glob",
    "Grep",
    "WebFetch",
    "WebSearch",
    "TodoWrite",
    "NotebookEdit",
    "Skill",
])


# Tag patterns for parsing
TAG_FUNCTION_CALLS_OPEN = "<function_calls>"
TAG_FUNCTION_CALLS_CLOSE = "</function_calls>"
TAG_FUNCTION_RESULTS_OPEN = "<function_results>"
TAG_FUNCTION_RESULTS_CLOSE = "</function_results>"
TAG_INVOKE_CLOSE = "</invoke>"

# Regex patterns as raw strings
TAG_INVOKE_PATTERN = r'<invoke\s+name=\"([^\"]+)\"[^>]*>'
TAG_PARAMETER_PATTERN = r'<parameter\s+name=\"([^\"]+)\">([\s\S]*?)</parameter>'


@dataclass
class ClaudeCodePatterns:
    """Regex patterns for Claude Code CLI output parsing."""

    # Prompt patterns - indicates ready for input
    prompt_ready: re.Pattern = field(
        default_factory=lambda: re.compile(r"^>\s*$", re.MULTILINE)
    )

    # Thinking indicator patterns
    thinking_indicator: re.Pattern = field(
        default_factory=lambda: re.compile(
            r"(Thinking|Processing|Analyzing|Let me)",
            re.IGNORECASE
        )
    )

    # Error patterns
    error_indicator: re.Pattern = field(
        default_factory=lambda: re.compile(
            r"(Error:|error:|ERROR:|Exception:|Failed:)",
            re.MULTILINE
        )
    )


class ClaudeCodeParser(OutputParser):
    """
    Parser for Claude Code CLI terminal output.
    
    Claude Code uses a specific output format with:
    - ">" prompt when ready for input
    - XML-like tags for tool invocations and results
    - Markdown formatting in responses
    """

    def __init__(self):
        self._patterns = ClaudeCodePatterns()
        self._tool_call_counter = 0

    @property
    def provider_name(self) -> str:
        return "claude-code"

    def parse_output(self, raw: str) -> ParsedOutput:
        """Parse raw Claude Code CLI output."""
        state = self.detect_state(raw)
        tool_calls = self.extract_tool_calls(raw)
        response = self.extract_assistant_response(raw)
        prompt_ready = self.detect_prompt_ready(raw)
        error_msg = self._extract_error(raw)

        return ParsedOutput(
            raw=raw,
            state=state,
            tool_calls=tool_calls,
            assistant_response=response,
            prompt_ready=prompt_ready,
            error_message=error_msg,
            metadata={"provider": self.provider_name},
        )

    def detect_state(self, raw: str) -> AgentState:
        """Detect agent state from Claude Code output."""
        # Check for prompt ready first (highest priority)
        if self.detect_prompt_ready(raw):
            return AgentState.IDLE

        # Check for errors
        if self._patterns.error_indicator.search(raw):
            return AgentState.ERROR

        # Check for tool execution (look for function_results)
        if TAG_FUNCTION_RESULTS_OPEN in raw:
            return AgentState.EXECUTING_TOOL

        # Check for tool invocation in progress
        if self._has_tool_invocation(raw):
            return AgentState.EXECUTING_TOOL

        # Check for thinking indicators
        if self._patterns.thinking_indicator.search(raw):
            return AgentState.THINKING

        # If there is substantial text, assume thinking
        if len(raw.strip()) > 50:
            return AgentState.THINKING

        # Check for waiting input patterns
        waiting_patterns = ["(y/n)", "[y/n]", "continue?", "confirm"]
        raw_lower = raw.lower()
        if any(p in raw_lower for p in waiting_patterns):
            return AgentState.WAITING_INPUT

        return AgentState.IDLE

    def extract_tool_calls(self, raw: str) -> list[ToolCall]:
        """Extract tool calls from Claude Code output."""
        tool_calls = []

        # Build pattern for full invoke block
        invoke_block_pattern = re.compile(
            TAG_INVOKE_PATTERN + r'([\s\S]*?)' + TAG_INVOKE_CLOSE,
            re.DOTALL
        )
        param_pattern = re.compile(TAG_PARAMETER_PATTERN, re.DOTALL)

        for match in invoke_block_pattern.finditer(raw):
            tool_name = match.group(1)
            invoke_body = match.group(2)

            # Extract parameters
            arguments: dict[str, Any] = {}
            for param_match in param_pattern.finditer(invoke_body):
                param_name = param_match.group(1)
                param_value = param_match.group(2).strip()
                arguments[param_name] = param_value

            self._tool_call_counter += 1
            tc = ToolCall(
                id=f"tc-{self._tool_call_counter}-{uuid.uuid4().hex[:8]}",
                name=tool_name,
                arguments=arguments,
            )
            tool_calls.append(tc)

        return tool_calls

    def extract_assistant_response(self, raw: str) -> str:
        """Extract assistant response text, stripping tool formatting."""
        text = raw

        # Remove function_calls blocks
        fc_pattern = re.compile(
            re.escape(TAG_FUNCTION_CALLS_OPEN) + r'[\s\S]*?' + re.escape(TAG_FUNCTION_CALLS_CLOSE),
            re.DOTALL
        )
        text = fc_pattern.sub("", text)

        # Remove function_results blocks
        fr_pattern = re.compile(
            re.escape(TAG_FUNCTION_RESULTS_OPEN) + r'[\s\S]*?' + re.escape(TAG_FUNCTION_RESULTS_CLOSE),
            re.DOTALL
        )
        text = fr_pattern.sub("", text)

        # Remove prompt character at end
        text = re.sub(r"^>\s*$", "", text, flags=re.MULTILINE)

        # Clean up whitespace
        text = "\n".join(line for line in text.split("\n") if line.strip())
        text = text.strip()

        return text

    def detect_prompt_ready(self, raw: str) -> bool:
        """Detect if Claude Code is at the prompt ready for input."""
        # Check if the last non-empty line is just ">"
        lines = raw.rstrip().split("\n")
        if not lines:
            return False

        last_line = lines[-1].strip()
        return last_line == ">"

    def _has_tool_invocation(self, raw: str) -> bool:
        """Check if output contains tool invocation markers."""
        return TAG_FUNCTION_CALLS_OPEN in raw or re.search(TAG_INVOKE_PATTERN, raw) is not None

    def _extract_error(self, raw: str) -> str | None:
        """Extract error message if present."""
        match = self._patterns.error_indicator.search(raw)
        if match:
            # Extract the line containing the error
            start = match.start()
            end = raw.find("\n", start)
            if end == -1:
                end = len(raw)
            return raw[start:end].strip()
        return None
