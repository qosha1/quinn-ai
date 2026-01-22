"""
Concrete SessionInterface implementations and registry.
"""

from .claude_code import ClaudeCodeSession
from .registry import (
    SessionRegistry,
    AdapterNotFoundError,
    get_default_registry,
    create_default_registry,
    initialize_defaults,
    set_default_registry,
    reset_default_registry,
)

__all__ = [
    # Adapters
    "ClaudeCodeSession",
    # Registry
    "SessionRegistry",
    "AdapterNotFoundError",
    "get_default_registry",
    "create_default_registry",
    "initialize_defaults",
    "set_default_registry",
    "reset_default_registry",
]
