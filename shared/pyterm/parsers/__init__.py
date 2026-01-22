"""
pyterm output parsers - Provider-specific output parsing.

Parsers extract structured information from raw terminal output:
- Agent state detection (idle, thinking, executing)
- Tool call extraction
- Response text extraction
- Prompt readiness detection

Uses registry pattern for parser lookup - no string dispatch.
"""

from shared.pyterm.agent_state import AgentState
from shared.pyterm.parsers.base import (
    OutputParser,
    ParsedOutput,
)
from shared.pyterm.parsers.claude_code import (
    ClaudeCodeParser,
    ClaudeCodePatterns,
    CLAUDE_CODE_TOOL_NAMES,
)
from shared.pyterm.parsers.generic import (
    GenericParser,
    GenericPatterns,
    COMMON_PROMPTS,
)
from shared.pyterm.parsers.registry import (
    ParserRegistry,
    get_default_registry,
    create_default_registry,
    set_default_registry,
    reset_default_registry,
)


def get_parser(provider_name: str) -> OutputParser:
    """
    Get an appropriate parser for the given provider.

    Uses the default registry to look up parsers.
    This is a convenience function - for more control, use
    the registry directly.

    Args:
        provider_name: Name of the provider (e.g., 'claude-code', 'generic')

    Returns:
        OutputParser instance for the provider

    Raises:
        KeyError: If parser not found in registry
    """
    registry = get_default_registry()

    # If not found, fall back to generic
    if not registry.has(provider_name):
        return registry.get("generic")

    return registry.get(provider_name)


__all__ = [
    # Base types (AgentState re-exported from agent_state module)
    "AgentState",
    "OutputParser",
    "ParsedOutput",
    # Claude Code parser
    "ClaudeCodeParser",
    "ClaudeCodePatterns",
    "CLAUDE_CODE_TOOL_NAMES",
    # Generic parser
    "GenericParser",
    "GenericPatterns",
    "COMMON_PROMPTS",
    # Registry
    "ParserRegistry",
    "get_default_registry",
    "create_default_registry",
    "set_default_registry",
    "reset_default_registry",
    # Factory (convenience)
    "get_parser",
]
