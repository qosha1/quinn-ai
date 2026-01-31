"""
Provider capability definitions.

Defines standard capabilities that CLI providers may support.
Used for capability-based provider selection and validation.
"""

from enum import Enum
from typing import Set


class ProviderCapability(str, Enum):
    """Standard capabilities that CLI providers may support.

    These capabilities are used to:
    1. Document what each provider can do
    2. Select providers based on task requirements
    3. Validate provider configuration
    """

    # Core capabilities
    SHELL = "shell"
    """Can execute shell commands."""

    FILE_EDIT = "file_edit"
    """Can read and modify files."""

    FILE_READ = "file_read"
    """Can read files (read-only)."""

    WEB_SEARCH = "web_search"
    """Can search the web."""

    WEB_BROWSE = "web_browse"
    """Can browse web pages."""

    # AI capabilities
    VISION = "vision"
    """Can process images."""

    EXTENDED_THINKING = "extended_thinking"
    """Supports extended thinking/reasoning mode."""

    FUNCTION_CALLING = "function_calling"
    """Supports structured function/tool calling."""

    # Collaboration capabilities
    MCP = "mcp"
    """Supports Model Context Protocol."""

    MULTI_TURN = "multi_turn"
    """Supports multi-turn conversation."""

    STREAMING = "streaming"
    """Supports streaming responses."""

    # Development capabilities
    CODE_INTERPRETER = "code_interpreter"
    """Can run code in a sandbox."""

    GIT = "git"
    """Can interact with git repositories."""

    TESTING = "testing"
    """Can run tests."""

    # Context capabilities
    LARGE_CONTEXT = "large_context"
    """Supports large context windows (>100k tokens)."""

    CONTEXT_CACHING = "context_caching"
    """Supports context caching for efficiency."""


# Provider capability profiles
# Maps provider names to their supported capabilities
PROVIDER_CAPABILITIES: dict[str, Set[ProviderCapability]] = {
    "claude_code": {
        ProviderCapability.SHELL,
        ProviderCapability.FILE_EDIT,
        ProviderCapability.FILE_READ,
        ProviderCapability.WEB_SEARCH,
        ProviderCapability.WEB_BROWSE,
        ProviderCapability.VISION,
        ProviderCapability.EXTENDED_THINKING,
        ProviderCapability.FUNCTION_CALLING,
        ProviderCapability.MCP,
        ProviderCapability.MULTI_TURN,
        ProviderCapability.STREAMING,
        ProviderCapability.CODE_INTERPRETER,
        ProviderCapability.GIT,
        ProviderCapability.TESTING,
        ProviderCapability.LARGE_CONTEXT,
        ProviderCapability.CONTEXT_CACHING,
    },
    "codex": {
        ProviderCapability.SHELL,
        ProviderCapability.FILE_EDIT,
        ProviderCapability.FILE_READ,
        ProviderCapability.FUNCTION_CALLING,
        ProviderCapability.MULTI_TURN,
        ProviderCapability.STREAMING,
        ProviderCapability.GIT,
    },
    "gemini": {
        ProviderCapability.FILE_READ,
        ProviderCapability.WEB_SEARCH,
        ProviderCapability.WEB_BROWSE,
        ProviderCapability.VISION,
        ProviderCapability.FUNCTION_CALLING,
        ProviderCapability.MULTI_TURN,
        ProviderCapability.STREAMING,
        ProviderCapability.LARGE_CONTEXT,
    },
    "openai": {
        ProviderCapability.FILE_READ,
        ProviderCapability.WEB_SEARCH,
        ProviderCapability.VISION,
        ProviderCapability.FUNCTION_CALLING,
        ProviderCapability.MULTI_TURN,
        ProviderCapability.STREAMING,
        ProviderCapability.CODE_INTERPRETER,
    },
    "cursor": {
        ProviderCapability.SHELL,
        ProviderCapability.FILE_EDIT,
        ProviderCapability.FILE_READ,
        ProviderCapability.FUNCTION_CALLING,
        ProviderCapability.MULTI_TURN,
        ProviderCapability.STREAMING,
        ProviderCapability.GIT,
        ProviderCapability.TESTING,
    },
    "aider": {
        ProviderCapability.SHELL,
        ProviderCapability.FILE_EDIT,
        ProviderCapability.FILE_READ,
        ProviderCapability.MULTI_TURN,
        ProviderCapability.GIT,
    },
}


def get_provider_capabilities(provider_name: str) -> Set[ProviderCapability]:
    """Get capabilities for a provider.

    Args:
        provider_name: Provider name (e.g., 'claude_code', 'cursor')

    Returns:
        Set of ProviderCapability values, empty set if unknown provider
    """
    return PROVIDER_CAPABILITIES.get(provider_name, set())


def has_capability(provider_name: str, capability: ProviderCapability) -> bool:
    """Check if a provider has a specific capability.

    Args:
        provider_name: Provider name
        capability: Capability to check

    Returns:
        True if provider has the capability
    """
    return capability in get_provider_capabilities(provider_name)


def find_providers_with_capability(capability: ProviderCapability) -> list[str]:
    """Find all providers with a specific capability.

    Args:
        capability: Capability to search for

    Returns:
        List of provider names that have the capability
    """
    return [
        name for name, caps in PROVIDER_CAPABILITIES.items()
        if capability in caps
    ]


def find_providers_with_all_capabilities(
    capabilities: Set[ProviderCapability]
) -> list[str]:
    """Find providers that have ALL specified capabilities.

    Args:
        capabilities: Set of required capabilities

    Returns:
        List of provider names that have all capabilities
    """
    return [
        name for name, caps in PROVIDER_CAPABILITIES.items()
        if capabilities.issubset(caps)
    ]


def find_providers_with_any_capabilities(
    capabilities: Set[ProviderCapability]
) -> list[str]:
    """Find providers that have ANY of the specified capabilities.

    Args:
        capabilities: Set of capabilities to search for

    Returns:
        List of provider names that have at least one capability
    """
    return [
        name for name, caps in PROVIDER_CAPABILITIES.items()
        if capabilities.intersection(caps)
    ]
