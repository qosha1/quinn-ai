"""
SessionRegistry - Registry for CLI session adapters.

Follows the registry pattern - adapters register themselves,
callers retrieve by provider name. No string dispatch with if/else.

Example:
    registry = SessionRegistry()
    registry.register("claude_code", ClaudeCodeSession)
    session = registry.create("claude_code", config)
"""

from typing import Type, Optional

from cli.core.session import SessionInterface, SessionConfig
from shared.pyterm import PytermConfig


class AdapterNotFoundError(Exception):
    """Raised when a session adapter is not found in the registry."""

    def __init__(self, provider: str, available: list[str]):
        self.provider = provider
        self.available = available
        super().__init__(
            f"Session adapter '{provider}' not found. "
            f"Available: {', '.join(sorted(available))}"
        )


class SessionRegistry:
    """
    Registry of session adapters.

    Manages CLI session adapter classes (ClaudeCodeSession, etc.) and
    creates instances on demand. Uses the registry pattern to avoid
    string-based dispatch.

    Example:
        registry = SessionRegistry()
        registry.register("claude_code", ClaudeCodeSession)
        registry.register("codex", CodexSession, aliases=["openai"])

        session = registry.create("claude_code", config)
    """

    def __init__(self):
        self._adapters: dict[str, Type[SessionInterface]] = {}
        self._aliases: dict[str, str] = {}

    def register(
        self,
        name: str,
        adapter_class: Type[SessionInterface],
        aliases: Optional[list[str]] = None,
    ) -> None:
        """
        Register a session adapter class.

        Args:
            name: Canonical name for the adapter (e.g., "claude_code")
            adapter_class: SessionInterface subclass
            aliases: Alternative names that resolve to this adapter
        """
        self._adapters[name] = adapter_class

        if aliases:
            for alias in aliases:
                self._aliases[alias] = name

    def get(self, name: str) -> Type[SessionInterface]:
        """
        Get an adapter class by name.

        Args:
            name: Adapter name (canonical or alias)

        Returns:
            SessionInterface subclass

        Raises:
            AdapterNotFoundError: If adapter not found
        """
        # Normalize to lowercase for case-insensitive lookup
        name = name.lower()

        # Resolve alias if needed
        canonical = self._aliases.get(name, name)

        if canonical not in self._adapters:
            raise AdapterNotFoundError(name, self.list_adapters())

        return self._adapters[canonical]

    def create(self, name: str, config: SessionConfig, **kwargs) -> SessionInterface:
        """
        Create a session adapter instance.

        Args:
            name: Adapter name (canonical or alias)
            config: SessionConfig for the session
            **kwargs: Additional arguments to pass to adapter constructor

        Returns:
            New SessionInterface instance

        Raises:
            AdapterNotFoundError: If adapter not found
        """
        adapter_class = self.get(name)
        return adapter_class(config, **kwargs)

    def has(self, name: str) -> bool:
        """Check if an adapter is registered."""
        name = name.lower()
        canonical = self._aliases.get(name, name)
        return canonical in self._adapters

    def list_adapters(self) -> list[str]:
        """List all registered adapter names (canonical only)."""
        return list(self._adapters.keys())

    def list_all(self) -> list[str]:
        """List all names including aliases."""
        return list(self._adapters.keys()) + list(self._aliases.keys())

    def get_canonical_name(self, name: str) -> Optional[str]:
        """Get canonical name for an adapter (resolves aliases)."""
        name = name.lower()
        if name in self._adapters:
            return name
        return self._aliases.get(name)

    def clear(self) -> None:
        """Clear all registrations."""
        self._adapters.clear()
        self._aliases.clear()

    def create_for_worker(
        self,
        worker_id: str,
        provider_name: str,
        command: str,
        working_directory: Optional[str] = None,
        args: Optional[list[str]] = None,
        env_vars: Optional[dict[str, str]] = None,
        pyterm_config: Optional[PytermConfig] = None,
        **kwargs,
    ) -> SessionInterface:
        """
        Create a session for a worker with the given provider.

        Convenience factory method that builds SessionConfig and creates
        the appropriate session adapter in one step.

        Args:
            worker_id: Worker ID to bind the session to
            provider_name: Provider name (used for adapter lookup)
            command: CLI command to execute
            working_directory: Optional working directory path
            args: Optional command arguments
            env_vars: Optional environment variables
            pyterm_config: Terminal configuration (defaults to PytermConfig.standard())
            **kwargs: Additional arguments for adapter constructor

        Returns:
            New SessionInterface instance

        Raises:
            AdapterNotFoundError: If no adapter for provider_name
        """
        config = SessionConfig(
            worker_id=worker_id,
            provider=provider_name,
            command=command,
            args=args or [],
            working_directory=working_directory,
            env_vars=env_vars or {},
        )
        # Factory provides the standard config if not specified
        effective_pyterm_config = pyterm_config or PytermConfig.standard()
        return self.create(provider_name, config, pyterm_config=effective_pyterm_config, **kwargs)


# =============================================================================
# Default Registry
# =============================================================================

# Global default registry - populated by initialize_defaults()
_default_registry: Optional[SessionRegistry] = None


def get_default_registry() -> SessionRegistry:
    """
    Get the default session registry.

    Lazily initializes with standard adapters on first call.
    """
    global _default_registry
    if _default_registry is None:
        _default_registry = create_default_registry()
    return _default_registry


def create_default_registry() -> SessionRegistry:
    """
    Create a new registry with standard adapters.

    This is the explicit way to get a populated registry.
    """
    from cli.core.sessions.claude_code import ClaudeCodeSession

    registry = SessionRegistry()

    # Register Claude Code adapter
    registry.register(
        "claude_code",
        ClaudeCodeSession,
        aliases=["claude", "anthropic", "claude-code"],
    )

    return registry


def initialize_defaults() -> SessionRegistry:
    """
    Initialize the default registry.

    Call this at application startup to ensure adapters are registered.
    Returns the initialized registry.
    """
    global _default_registry
    _default_registry = create_default_registry()
    return _default_registry


def set_default_registry(registry: SessionRegistry) -> None:
    """
    Set the default registry.

    Use this for testing or to inject a custom registry.
    """
    global _default_registry
    _default_registry = registry


def reset_default_registry() -> None:
    """Reset default registry to None (will be recreated on next access)."""
    global _default_registry
    _default_registry = None
