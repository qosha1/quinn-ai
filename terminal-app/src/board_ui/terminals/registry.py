"""
Terminal provider registry.

Auto-detects available terminal emulators and returns the best one.
No string dispatch - providers register themselves in a type-safe registry.
"""

from typing import Optional

from ..interfaces.terminal import TerminalProvider, TerminalType


# Registry of provider classes by type
# Populated by provider modules on import
_PROVIDERS: dict[TerminalType, type[TerminalProvider]] = {}


def register_provider(
    terminal_type: TerminalType,
    provider_class: type[TerminalProvider],
) -> None:
    """Register a terminal provider class.

    Called by provider modules to register themselves.

    Args:
        terminal_type: Which terminal this provider handles
        provider_class: The provider class to instantiate
    """
    _PROVIDERS[terminal_type] = provider_class


def get_available_terminals() -> list[TerminalType]:
    """Get list of available terminal emulators.

    Checks each registered provider to see if it's available on this system.

    Returns:
        List of available terminal types, in preference order
    """
    available = []

    # Check each registered provider
    for terminal_type, provider_class in _PROVIDERS.items():
        try:
            provider = provider_class()
            if provider.is_available():
                available.append(terminal_type)
        except Exception:
            # Provider failed to instantiate - skip
            continue

    # Sort by preference (Kitty > iTerm > macOS Terminal > Generic)
    preference_order = [
        TerminalType.KITTY,
        TerminalType.ITERM2,
        TerminalType.ALACRITTY,
        TerminalType.MACOS_TERMINAL,
        TerminalType.GNOME_TERMINAL,
        TerminalType.WINDOWS_TERMINAL,
        TerminalType.GENERIC,
    ]

    return sorted(
        available,
        key=lambda t: preference_order.index(t) if t in preference_order else 999
    )


def get_terminal_provider(
    preferred: Optional[TerminalType] = None,
) -> Optional[TerminalProvider]:
    """Get a terminal provider instance.

    If preferred is specified and available, returns that provider.
    Otherwise returns the best available provider.

    Args:
        preferred: Preferred terminal type (optional)

    Returns:
        TerminalProvider instance or None if no terminals available
    """
    # If preferred is specified and available, use it
    if preferred is not None:
        if preferred in _PROVIDERS:
            provider = _PROVIDERS[preferred]()
            if provider.is_available():
                return provider

    # Otherwise, get best available
    available = get_available_terminals()
    if not available:
        return None

    best_type = available[0]
    return _PROVIDERS[best_type]()
