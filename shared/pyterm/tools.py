"""
Tool call tracking and registry for AI agent sessions.

Provides:
- ToolCallTracker: Track pending/completed tool calls with statistics
- ToolRegistry: Register and validate tool schemas
- ToolConfig: Configurable tool definitions
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from shared.pyterm.conversation import ToolCall, ToolResult


@dataclass
class TrackedCall:
    """A tool call with tracking metadata."""

    call: ToolCall
    result: ToolResult | None = None
    completed_at: datetime | None = None

    @property
    def is_pending(self) -> bool:
        """True if call has not received a result."""
        return self.result is None

    @property
    def is_completed(self) -> bool:
        """True if call has received a result."""
        return self.result is not None

    @property
    def duration_ms(self) -> int | None:
        """Duration from call to result in milliseconds."""
        if not self.completed_at:
            return None
        delta = self.completed_at - self.call.timestamp
        return int(delta.total_seconds() * 1000)

    @property
    def success(self) -> bool | None:
        """Success status from result, or None if pending."""
        return self.result.success if self.result else None


class ToolCallTracker:
    """
    Tracks tool calls and their results.

    Maintains a mapping from tool call IDs to their results,
    with statistics on success rates and durations.
    """

    def __init__(self):
        self._calls: dict[str, TrackedCall] = {}

    def add_call(self, tool_call: ToolCall) -> None:
        """
        Add a tool call to track.

        Args:
            tool_call: The tool call to track.
        """
        self._calls[tool_call.id] = TrackedCall(call=tool_call)

    def add_result(self, tool_result: ToolResult) -> bool:
        """
        Add a result for a tracked call.

        Args:
            tool_result: The result to add.

        Returns:
            True if the result was matched to a call, False otherwise.
        """
        return self.match_result_to_call(tool_result)

    def match_result_to_call(self, result: ToolResult) -> bool:
        """
        Match a result to its corresponding call.

        Args:
            result: The tool result to match.

        Returns:
            True if matched successfully, False if no matching call found.
        """
        if result.tool_call_id not in self._calls:
            return False

        tracked = self._calls[result.tool_call_id]
        tracked.result = result
        tracked.completed_at = result.timestamp
        return True

    def get_pending(self) -> list[ToolCall]:
        """Get all pending tool calls (no result yet)."""
        return [tc.call for tc in self._calls.values() if tc.is_pending]

    def get_completed(self) -> list[TrackedCall]:
        """Get all completed tool calls (with results)."""
        return [tc for tc in self._calls.values() if tc.is_completed]

    def get_call(self, call_id: str) -> TrackedCall | None:
        """Get a tracked call by ID."""
        return self._calls.get(call_id)

    def get_result(self, call_id: str) -> ToolResult | None:
        """Get the result for a call ID."""
        tracked = self._calls.get(call_id)
        return tracked.result if tracked else None

    @property
    def total_calls(self) -> int:
        """Total number of tracked calls."""
        return len(self._calls)

    @property
    def pending_count(self) -> int:
        """Number of pending calls."""
        return len(self.get_pending())

    @property
    def completed_count(self) -> int:
        """Number of completed calls."""
        return len(self.get_completed())

    @property
    def success_rate(self) -> float:
        """
        Success rate of completed calls.

        Returns:
            Float between 0.0 and 1.0, or 0.0 if no completed calls.
        """
        completed = self.get_completed()
        if not completed:
            return 0.0

        successful = sum(1 for tc in completed if tc.success)
        return successful / len(completed)

    @property
    def avg_duration_ms(self) -> float:
        """
        Average duration of completed calls in milliseconds.

        Returns:
            Average duration, or 0.0 if no completed calls with duration.
        """
        completed = self.get_completed()
        durations = [tc.duration_ms for tc in completed if tc.duration_ms is not None]

        if not durations:
            return 0.0

        return sum(durations) / len(durations)

    def get_calls_by_tool(self, tool_name: str) -> list[TrackedCall]:
        """Get all tracked calls for a specific tool."""
        return [tc for tc in self._calls.values() if tc.call.name == tool_name]

    def clear(self) -> None:
        """Clear all tracked calls."""
        self._calls.clear()

    def to_dict(self) -> dict:
        """Serialize tracker state to dict."""
        return {
            "total_calls": self.total_calls,
            "pending_count": self.pending_count,
            "completed_count": self.completed_count,
            "success_rate": self.success_rate,
            "avg_duration_ms": self.avg_duration_ms,
            "calls": {
                call_id: {
                    "tool_name": tc.call.name,
                    "is_pending": tc.is_pending,
                    "success": tc.success,
                    "duration_ms": tc.duration_ms,
                }
                for call_id, tc in self._calls.items()
            },
        }


@dataclass
class ToolParameter:
    """Definition of a tool parameter."""

    name: str
    type: str
    description: str
    required: bool = True
    default: Any = None


@dataclass
class ToolDefinition:
    """Definition of a tool with its schema."""

    name: str
    description: str
    parameters: list[ToolParameter] = field(default_factory=list)

    @property
    def required_params(self) -> list[str]:
        """Get names of required parameters."""
        return [p.name for p in self.parameters if p.required]

    @property
    def optional_params(self) -> list[str]:
        """Get names of optional parameters."""
        return [p.name for p in self.parameters if not p.required]

    def to_schema(self) -> dict:
        """Convert to JSON schema format."""
        properties = {}
        for param in self.parameters:
            properties[param.name] = {
                "type": param.type,
                "description": param.description,
            }
            if param.default is not None:
                properties[param.name]["default"] = param.default

        return {
            "name": self.name,
            "description": self.description,
            "parameters": {
                "type": "object",
                "properties": properties,
                "required": self.required_params,
            },
        }

    def to_dict(self) -> dict:
        """Serialize to dict for config storage."""
        return {
            "name": self.name,
            "description": self.description,
            "parameters": [
                {
                    "name": p.name,
                    "type": p.type,
                    "description": p.description,
                    "required": p.required,
                    "default": p.default,
                }
                for p in self.parameters
            ],
        }

    @classmethod
    def from_dict(cls, data: dict) -> "ToolDefinition":
        """Create from dict."""
        parameters = [
            ToolParameter(
                name=p["name"],
                type=p["type"],
                description=p["description"],
                required=p.get("required", True),
                default=p.get("default"),
            )
            for p in data.get("parameters", [])
        ]
        return cls(
            name=data["name"],
            description=data["description"],
            parameters=parameters,
        )


class ToolRegistry:
    """
    Registry of known tools with their schemas.

    Used to validate tool calls and provide tool metadata.
    """

    def __init__(self):
        self._tools: dict[str, ToolDefinition] = {}

    def register(self, tool: ToolDefinition) -> None:
        """
        Register a tool definition.

        Args:
            tool: The tool definition to register.
        """
        self._tools[tool.name] = tool

    def register_all(self, tools: list[ToolDefinition]) -> None:
        """Register multiple tools at once."""
        for tool in tools:
            self.register(tool)

    def get(self, name: str) -> ToolDefinition | None:
        """Get a tool definition by name."""
        return self._tools.get(name)

    def has(self, name: str) -> bool:
        """Check if a tool is registered."""
        return name in self._tools

    def list_tools(self) -> list[str]:
        """List all registered tool names."""
        return list(self._tools.keys())

    def validate_call(self, tool_call: ToolCall) -> tuple[bool, str | None]:
        """
        Validate a tool call against its schema.

        Args:
            tool_call: The tool call to validate.

        Returns:
            Tuple of (is_valid, error_message).
            error_message is None if valid.
        """
        tool = self._tools.get(tool_call.name)

        if tool is None:
            return (False, f"Unknown tool: {tool_call.name}")

        # Check required parameters
        for param_name in tool.required_params:
            if param_name not in tool_call.arguments:
                return (False, f"Missing required parameter: {param_name}")

        # Check for unknown parameters
        known_params = {p.name for p in tool.parameters}
        for arg_name in tool_call.arguments:
            if arg_name not in known_params:
                return (False, f"Unknown parameter: {arg_name}")

        return (True, None)

    def get_description(self, name: str) -> str | None:
        """Get the description of a tool."""
        tool = self._tools.get(name)
        return tool.description if tool else None

    def get_required_args(self, name: str) -> list[str]:
        """Get required arguments for a tool."""
        tool = self._tools.get(name)
        return tool.required_params if tool else []

    def get_optional_args(self, name: str) -> list[str]:
        """Get optional arguments for a tool."""
        tool = self._tools.get(name)
        return tool.optional_params if tool else []

    def to_schemas(self) -> list[dict]:
        """Get all tool schemas."""
        return [tool.to_schema() for tool in self._tools.values()]

    def to_config(self) -> list[dict]:
        """Export all tools as config dicts."""
        return [tool.to_dict() for tool in self._tools.values()]

    def clear(self) -> None:
        """Clear all registered tools."""
        self._tools.clear()

    @classmethod
    def from_config(cls, tools_config: list[dict]) -> "ToolRegistry":
        """Create a registry from config dicts."""
        registry = cls()
        for tool_dict in tools_config:
            tool = ToolDefinition.from_dict(tool_dict)
            registry.register(tool)
        return registry


# =============================================================================
# Tool Configuration
# =============================================================================

@dataclass
class ToolConfig:
    """
    Configuration for tool definitions.

    Tools can be loaded from config rather than hardcoded.
    """

    tools: list[ToolDefinition]

    def create_registry(self) -> ToolRegistry:
        """Create a ToolRegistry from this config."""
        registry = ToolRegistry()
        registry.register_all(self.tools)
        return registry

    def to_dict(self) -> dict:
        """Serialize to dict."""
        return {
            "tools": [t.to_dict() for t in self.tools],
        }

    @classmethod
    def from_dict(cls, data: dict) -> "ToolConfig":
        """Create from dict."""
        tools = [ToolDefinition.from_dict(t) for t in data.get("tools", [])]
        return cls(tools=tools)


# =============================================================================
# Standard Tool Definitions
# =============================================================================

def _create_standard_tools() -> list[ToolDefinition]:
    """Create the standard Claude Code tool definitions."""
    return [
        ToolDefinition(
            name="Bash",
            description="Execute a bash command in the terminal",
            parameters=[
                ToolParameter(
                    name="command",
                    type="string",
                    description="The command to execute",
                    required=True,
                ),
                ToolParameter(
                    name="description",
                    type="string",
                    description="Description of what the command does",
                    required=False,
                ),
                ToolParameter(
                    name="timeout",
                    type="number",
                    description="Optional timeout in milliseconds (max 600000)",
                    required=False,
                ),
                ToolParameter(
                    name="run_in_background",
                    type="boolean",
                    description="Run command in background",
                    required=False,
                    default=False,
                ),
            ],
        ),
        ToolDefinition(
            name="Read",
            description="Read a file from the filesystem",
            parameters=[
                ToolParameter(
                    name="file_path",
                    type="string",
                    description="The absolute path to the file to read",
                    required=True,
                ),
                ToolParameter(
                    name="offset",
                    type="number",
                    description="Line number to start reading from",
                    required=False,
                ),
                ToolParameter(
                    name="limit",
                    type="number",
                    description="Number of lines to read",
                    required=False,
                ),
            ],
        ),
        ToolDefinition(
            name="Write",
            description="Write content to a file",
            parameters=[
                ToolParameter(
                    name="file_path",
                    type="string",
                    description="The absolute path to the file to write",
                    required=True,
                ),
                ToolParameter(
                    name="content",
                    type="string",
                    description="The content to write to the file",
                    required=True,
                ),
            ],
        ),
        ToolDefinition(
            name="Edit",
            description="Perform exact string replacements in files",
            parameters=[
                ToolParameter(
                    name="file_path",
                    type="string",
                    description="The absolute path to the file to modify",
                    required=True,
                ),
                ToolParameter(
                    name="old_string",
                    type="string",
                    description="The text to replace",
                    required=True,
                ),
                ToolParameter(
                    name="new_string",
                    type="string",
                    description="The replacement text",
                    required=True,
                ),
                ToolParameter(
                    name="replace_all",
                    type="boolean",
                    description="Replace all occurrences",
                    required=False,
                    default=False,
                ),
            ],
        ),
        ToolDefinition(
            name="Glob",
            description="Find files matching a glob pattern",
            parameters=[
                ToolParameter(
                    name="pattern",
                    type="string",
                    description="The glob pattern to match files against",
                    required=True,
                ),
                ToolParameter(
                    name="path",
                    type="string",
                    description="The directory to search in",
                    required=False,
                ),
            ],
        ),
        ToolDefinition(
            name="Grep",
            description="Search for patterns in files using ripgrep",
            parameters=[
                ToolParameter(
                    name="pattern",
                    type="string",
                    description="The regex pattern to search for",
                    required=True,
                ),
                ToolParameter(
                    name="path",
                    type="string",
                    description="File or directory to search in",
                    required=False,
                ),
                ToolParameter(
                    name="glob",
                    type="string",
                    description="Glob pattern to filter files",
                    required=False,
                ),
                ToolParameter(
                    name="output_mode",
                    type="string",
                    description="Output mode: content, files_with_matches, or count",
                    required=False,
                    default="files_with_matches",
                ),
            ],
        ),
        ToolDefinition(
            name="WebFetch",
            description="Fetch and process content from a URL",
            parameters=[
                ToolParameter(
                    name="url",
                    type="string",
                    description="The URL to fetch content from",
                    required=True,
                ),
                ToolParameter(
                    name="prompt",
                    type="string",
                    description="Prompt describing what to extract from the page",
                    required=True,
                ),
            ],
        ),
        ToolDefinition(
            name="WebSearch",
            description="Search the web for information",
            parameters=[
                ToolParameter(
                    name="query",
                    type="string",
                    description="The search query",
                    required=True,
                ),
                ToolParameter(
                    name="allowed_domains",
                    type="array",
                    description="Only include results from these domains",
                    required=False,
                ),
                ToolParameter(
                    name="blocked_domains",
                    type="array",
                    description="Exclude results from these domains",
                    required=False,
                ),
            ],
        ),
        ToolDefinition(
            name="NotebookEdit",
            description="Edit a Jupyter notebook cell",
            parameters=[
                ToolParameter(
                    name="notebook_path",
                    type="string",
                    description="The absolute path to the notebook file",
                    required=True,
                ),
                ToolParameter(
                    name="new_source",
                    type="string",
                    description="The new source for the cell",
                    required=True,
                ),
                ToolParameter(
                    name="cell_id",
                    type="string",
                    description="The ID of the cell to edit",
                    required=False,
                ),
                ToolParameter(
                    name="cell_type",
                    type="string",
                    description="The type of cell (code or markdown)",
                    required=False,
                ),
                ToolParameter(
                    name="edit_mode",
                    type="string",
                    description="Edit mode: replace, insert, or delete",
                    required=False,
                    default="replace",
                ),
            ],
        ),
        ToolDefinition(
            name="TodoWrite",
            description="Create and manage a structured task list",
            parameters=[
                ToolParameter(
                    name="todos",
                    type="array",
                    description="The updated todo list",
                    required=True,
                ),
            ],
        ),
        ToolDefinition(
            name="Skill",
            description="Execute a skill within the main conversation",
            parameters=[
                ToolParameter(
                    name="skill",
                    type="string",
                    description="The skill name to invoke",
                    required=True,
                ),
                ToolParameter(
                    name="args",
                    type="string",
                    description="Optional arguments for the skill",
                    required=False,
                ),
            ],
        ),
    ]


def get_standard_tool_config() -> ToolConfig:
    """
    Get the standard tool configuration for Claude Code.

    This is the explicit way to get default tools.
    """
    return ToolConfig(tools=_create_standard_tools())


def create_claude_code_registry() -> ToolRegistry:
    """Create a ToolRegistry pre-populated with Claude Code tools."""
    return get_standard_tool_config().create_registry()


# For backwards compatibility - but prefer using get_standard_tool_config()
CLAUDE_CODE_TOOLS = _create_standard_tools()

# Individual tool exports for convenience
def _get_tool_by_name(name: str) -> ToolDefinition:
    """Get a standard tool by name."""
    for tool in CLAUDE_CODE_TOOLS:
        if tool.name == name:
            return tool
    raise KeyError(f"Tool not found: {name}")

BASH_TOOL = _get_tool_by_name("Bash")
READ_TOOL = _get_tool_by_name("Read")
WRITE_TOOL = _get_tool_by_name("Write")
EDIT_TOOL = _get_tool_by_name("Edit")
GLOB_TOOL = _get_tool_by_name("Glob")
GREP_TOOL = _get_tool_by_name("Grep")
WEB_FETCH_TOOL = _get_tool_by_name("WebFetch")
WEB_SEARCH_TOOL = _get_tool_by_name("WebSearch")
NOTEBOOK_EDIT_TOOL = _get_tool_by_name("NotebookEdit")
TODO_WRITE_TOOL = _get_tool_by_name("TodoWrite")
SKILL_TOOL = _get_tool_by_name("Skill")
