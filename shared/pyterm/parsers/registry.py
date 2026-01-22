"""
Parser registry - Registry pattern for output parsers.

Eliminates string-based dispatch. Parsers register themselves,
callers get instances via the registry.
"""

from typing import Type

from shared.pyterm.parsers.base import OutputParser


class ParserRegistry:
    """
    Registry of output parsers.

    Follows the registry pattern - parsers register themselves,
    callers retrieve by key. No string dispatch with if/else.

    Example:
        registry = ParserRegistry()
        registry.register("claude-code", ClaudeCodeParser)
        parser = registry.get("claude-code")
    """

    def __init__(self):
        self._parsers: dict[str, Type[OutputParser]] = {}
        self._aliases: dict[str, str] = {}

    def register(
        self,
        name: str,
        parser_class: Type[OutputParser],
        aliases: list[str] | None = None,
    ) -> None:
        """
        Register a parser class.

        Args:
            name: Canonical name for the parser
            parser_class: Parser class (not instance)
            aliases: Alternative names that resolve to this parser
        """
        self._parsers[name] = parser_class

        if aliases:
            for alias in aliases:
                self._aliases[alias] = name

    def get(self, name: str) -> OutputParser:
        """
        Get a parser instance by name.

        Args:
            name: Parser name (canonical or alias)

        Returns:
            New parser instance

        Raises:
            KeyError: If parser not found
        """
        # Normalize to lowercase for case-insensitive lookup
        name = name.lower()
        # Resolve alias if needed
        canonical = self._aliases.get(name, name)

        if canonical not in self._parsers:
            available = list(self._parsers.keys()) + list(self._aliases.keys())
            raise KeyError(
                f"Parser '{name}' not found. Available: {', '.join(sorted(available))}"
            )

        return self._parsers[canonical]()

    def has(self, name: str) -> bool:
        """Check if a parser is registered."""
        name = name.lower()
        canonical = self._aliases.get(name, name)
        return canonical in self._parsers

    def list_parsers(self) -> list[str]:
        """List all registered parser names (canonical only)."""
        return list(self._parsers.keys())

    def list_all(self) -> list[str]:
        """List all names including aliases."""
        return list(self._parsers.keys()) + list(self._aliases.keys())

    def get_canonical_name(self, name: str) -> str | None:
        """Get canonical name for a parser (resolves aliases)."""
        name = name.lower()
        if name in self._parsers:
            return name
        return self._aliases.get(name)

    def clear(self) -> None:
        """Clear all registrations."""
        self._parsers.clear()
        self._aliases.clear()


# =============================================================================
# Default Registry
# =============================================================================

# Global default registry - populated by __init__.py
_default_registry: ParserRegistry | None = None


def get_default_registry() -> ParserRegistry:
    """
    Get the default parser registry.

    Lazily initializes with standard parsers on first call.
    """
    global _default_registry
    if _default_registry is None:
        _default_registry = create_default_registry()
    return _default_registry


def create_default_registry() -> ParserRegistry:
    """
    Create a new registry with standard parsers.

    This is the explicit way to get a populated registry.
    """
    # Import here to avoid circular imports
    from shared.pyterm.parsers.claude_code import ClaudeCodeParser
    from shared.pyterm.parsers.generic import GenericParser

    registry = ParserRegistry()

    # Register Claude Code parser
    registry.register(
        "claude-code",
        ClaudeCodeParser,
        aliases=["claude_code", "claude", "anthropic"],
    )

    # Register Generic parser
    registry.register(
        "generic",
        GenericParser,
        aliases=["default"],
    )

    return registry


def set_default_registry(registry: ParserRegistry) -> None:
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
