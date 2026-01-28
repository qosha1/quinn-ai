"""
Base output parser protocol and types.

Defines the interface for provider-specific output parsers that extract
structured information from raw terminal output.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

from shared.pyterm.agent_state import AgentState
from shared.pyterm.conversation import ToolCall


@dataclass
class ParsedOutput:
    """
    Structured result from parsing raw terminal output.

    Contains extracted components: state, tool calls, response text, etc.
    """

    raw: str
    state: AgentState
    tool_calls: list[ToolCall] = field(default_factory=list)
    assistant_response: str = ""
    prompt_ready: bool = False
    error_message: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "raw": self.raw,
            "state": self.state.value,
            "tool_calls": [tc.to_dict() for tc in self.tool_calls],
            "assistant_response": self.assistant_response,
            "prompt_ready": self.prompt_ready,
            "error_message": self.error_message,
            "metadata": self.metadata,
        }


class OutputParser(ABC):
    """
    Abstract base class for provider-specific output parsers.

    Each provider has different output formats that need parsing.
    Parsers extract structured information from raw terminal output.
    """

    @property
    @abstractmethod
    def provider_name(self) -> str:
        """Name of the provider this parser handles."""
        ...

    @abstractmethod
    def parse_output(self, raw: str) -> ParsedOutput:
        """
        Parse raw terminal output into structured form.

        This is the main entry point. Combines all detection methods
        to produce a complete ParsedOutput.

        Args:
            raw: Raw terminal output text

        Returns:
            ParsedOutput with extracted state, tool calls, etc.
        """
        ...

    @abstractmethod
    def detect_state(self, raw: str) -> AgentState:
        """
        Detect the current agent state from output.

        Args:
            raw: Raw terminal output text

        Returns:
            Detected AgentState
        """
        ...

    @abstractmethod
    def extract_tool_calls(self, raw: str) -> list[ToolCall]:
        """
        Extract tool calls from output.

        Args:
            raw: Raw terminal output text

        Returns:
            List of detected ToolCall objects
        """
        ...

    @abstractmethod
    def extract_assistant_response(self, raw: str) -> str:
        """
        Extract the assistant's response text from output.

        Strips tool call formatting, prompts, etc. to get just
        the natural language response.

        Args:
            raw: Raw terminal output text

        Returns:
            Clean assistant response text
        """
        ...

    @abstractmethod
    def detect_prompt_ready(self, raw: str) -> bool:
        """
        Detect if the output indicates prompt is ready for input.

        Args:
            raw: Raw terminal output text

        Returns:
            True if agent is waiting at prompt
        """
        ...
