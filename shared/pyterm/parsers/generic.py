"""
Generic fallback output parser.

Provides reasonable default parsing for unknown CLI providers.
Makes best-effort guesses based on common patterns.
"""

import re
from dataclasses import dataclass, field

from shared.pyterm.agent_state import AgentState
from shared.pyterm.conversation import ToolCall
from shared.pyterm.parsers.base import OutputParser, ParsedOutput


# Common prompt patterns across various CLIs
COMMON_PROMPTS = [
    r"^>\s*$",           # Simple angle bracket
    r"^\$\s*$",          # Dollar sign
    r"^>>>\s*$",         # Python-style
    r"^In \[\d+\]:",     # IPython/Jupyter
    r"^\w+@\w+[\$#]",    # Shell prompt
]


@dataclass
class GenericPatterns:
    """Regex patterns for generic output parsing."""

    # Combined prompt pattern
    prompt_ready: re.Pattern = field(
        default_factory=lambda: re.compile(
            "|".join(COMMON_PROMPTS),
            re.MULTILINE
        )
    )

    # Error patterns
    error_indicator: re.Pattern = field(
        default_factory=lambda: re.compile(
            r"(Error:|error:|ERROR:|Exception:|Traceback|Failed:|FAILED)",
            re.MULTILINE
        )
    )

    # Command execution patterns
    command_indicator: re.Pattern = field(
        default_factory=lambda: re.compile(
            r"^(\$|>|>>>)\s*\S+",  # Line starting with prompt + command
            re.MULTILINE
        )
    )

    # Thinking/processing patterns
    thinking_indicator: re.Pattern = field(
        default_factory=lambda: re.compile(
            r"(thinking|processing|loading|waiting|please wait)",
            re.IGNORECASE
        )
    )

    # Waiting for input patterns
    waiting_input_indicator: re.Pattern = field(
        default_factory=lambda: re.compile(
            r"(\(y/n\)|\[y/n\]|continue\?|confirm|press enter)",
            re.IGNORECASE
        )
    )


class GenericParser(OutputParser):
    """
    Generic fallback parser for unknown CLI providers.
    
    Makes reasonable guesses based on common patterns.
    Should work adequately for most command-line tools.
    """

    def __init__(self):
        self._patterns = GenericPatterns()
        self._tool_call_counter = 0

    @property
    def provider_name(self) -> str:
        return "generic"

    def parse_output(self, raw: str) -> ParsedOutput:
        """Parse raw terminal output using generic heuristics."""
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
        """Detect agent state using generic heuristics."""
        # Check for prompt ready first
        if self.detect_prompt_ready(raw):
            return AgentState.IDLE

        # Check for errors
        if self._patterns.error_indicator.search(raw):
            return AgentState.ERROR

        # Check for waiting for input
        if self._patterns.waiting_input_indicator.search(raw):
            return AgentState.WAITING_INPUT

        # Check for active command execution
        if self._patterns.command_indicator.search(raw):
            return AgentState.EXECUTING_TOOL

        # Check for thinking indicators
        if self._patterns.thinking_indicator.search(raw):
            return AgentState.THINKING

        # Default to idle if we cannot determine
        return AgentState.IDLE

    def extract_tool_calls(self, raw: str) -> list[ToolCall]:
        """
        Extract tool calls from generic output.
        
        Generic parser does not detect tool calls - providers that use
        tool calling should use a specialized parser.
        """
        # Generic parser cannot reliably detect tool calls
        return []

    def extract_assistant_response(self, raw: str) -> str:
        """Extract response text, removing common prompt patterns."""
        text = raw

        # Remove prompt lines at end
        for pattern in COMMON_PROMPTS:
            text = re.sub(pattern, "", text, flags=re.MULTILINE)

        # Clean up whitespace
        text = text.strip()

        return text

    def detect_prompt_ready(self, raw: str) -> bool:
        """Detect if output indicates prompt is ready."""
        # Check if last non-empty line matches a prompt pattern
        lines = raw.rstrip().split("\n")
        if not lines:
            return False

        last_line = lines[-1]
        return self._patterns.prompt_ready.match(last_line) is not None

    def _extract_error(self, raw: str) -> str | None:
        """Extract error message if present."""
        match = self._patterns.error_indicator.search(raw)
        if match:
            start = match.start()
            end = raw.find("\n", start)
            if end == -1:
                end = len(raw)
            return raw[start:end].strip()
        return None
