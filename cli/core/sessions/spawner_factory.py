"""
SpawnerFactory - Registry and factory for spawn strategies.

Provides:
- Registration of spawn strategies
- Config-driven strategy selection
- Default strategy management
"""

from typing import Optional, Type

from .spawner import SpawnStrategy, SpawnerConfig, SpawnResult


class SpawnerNotFoundError(Exception):
    """Raised when requested spawner doesn't exist."""

    def __init__(self, name: str, available: list[str]):
        self.name = name
        self.available = available
        super().__init__(
            f"Spawner not found: {name}. Available: {available}"
        )


class SpawnerFactory:
    """Factory and registry for spawn strategies.

    Manages available spawners and provides config-driven selection.

    Example:
        factory = SpawnerFactory()
        factory.register_defaults()

        # Get spawner by name
        spawner = factory.get("tmux")
        result = spawner.spawn(config)

        # Or use config-driven selection
        spawner = factory.get_for_config(config)
    """

    def __init__(self):
        """Initialize empty factory."""
        self._spawners: dict[str, SpawnStrategy] = {}
        self._default: Optional[str] = None

    def register(self, spawner: SpawnStrategy) -> None:
        """Register a spawn strategy.

        Args:
            spawner: SpawnStrategy instance
        """
        self._spawners[spawner.name] = spawner

    def register_class(self, name: str, spawner_class: Type[SpawnStrategy], **kwargs) -> None:
        """Register a spawn strategy by class.

        Args:
            name: Strategy name
            spawner_class: SpawnStrategy class to instantiate
            **kwargs: Arguments to pass to spawner constructor
        """
        spawner = spawner_class(**kwargs)
        self._spawners[name] = spawner

    def unregister(self, name: str) -> None:
        """Unregister a spawn strategy.

        Args:
            name: Strategy name to remove
        """
        if name in self._spawners:
            del self._spawners[name]
            if self._default == name:
                self._default = None

    def get(self, name: str) -> SpawnStrategy:
        """Get a spawn strategy by name.

        Args:
            name: Strategy name

        Returns:
            SpawnStrategy instance

        Raises:
            SpawnerNotFoundError: If strategy not found
        """
        if name not in self._spawners:
            raise SpawnerNotFoundError(name, self.list())
        return self._spawners[name]

    def has(self, name: str) -> bool:
        """Check if strategy is registered.

        Args:
            name: Strategy name

        Returns:
            True if registered
        """
        return name in self._spawners

    def list(self) -> list[str]:
        """List registered strategy names.

        Returns:
            List of strategy names
        """
        return list(self._spawners.keys())

    def set_default(self, name: str) -> None:
        """Set the default spawn strategy.

        Args:
            name: Strategy name

        Raises:
            SpawnerNotFoundError: If strategy not found
        """
        if name not in self._spawners:
            raise SpawnerNotFoundError(name, self.list())
        self._default = name

    @property
    def default(self) -> Optional[SpawnStrategy]:
        """Get default spawn strategy.

        Returns:
            Default SpawnStrategy or None
        """
        if self._default:
            return self._spawners.get(self._default)
        return None

    @property
    def default_name(self) -> Optional[str]:
        """Get default strategy name.

        Returns:
            Default strategy name or None
        """
        return self._default

    def get_for_config(self, config: SpawnerConfig) -> SpawnStrategy:
        """Get appropriate spawner for config.

        Uses config.options.get("spawn_strategy") if set,
        otherwise uses default.

        Args:
            config: Spawner configuration

        Returns:
            SpawnStrategy instance

        Raises:
            SpawnerNotFoundError: If no appropriate strategy found
        """
        # Check config for explicit strategy
        strategy_name = config.options.get("spawn_strategy")
        if strategy_name:
            return self.get(strategy_name)

        # Use default
        if self._default:
            return self.get(self._default)

        # No default, return first available
        if self._spawners:
            return next(iter(self._spawners.values()))

        raise SpawnerNotFoundError("(none)", [])

    def register_defaults(self) -> None:
        """Register default spawn strategies.

        Registers:
        - subprocess: Always available
        - tmux: If tmux is installed
        """
        # Subprocess is always available
        from .subprocess_spawner import SubprocessSpawner
        self.register(SubprocessSpawner())

        # Tmux if available
        import shutil
        if shutil.which("tmux"):
            from .tmux_spawner import TmuxSpawner
            self.register(TmuxSpawner())

        # Set default based on availability
        if self.has("tmux"):
            self.set_default("tmux")
        elif self.has("subprocess"):
            self.set_default("subprocess")


# Module-level factory instance
_default_factory: Optional[SpawnerFactory] = None


def get_default_factory() -> SpawnerFactory:
    """Get the default spawner factory.

    Creates and initializes factory if not exists.

    Returns:
        Default SpawnerFactory instance
    """
    global _default_factory
    if _default_factory is None:
        _default_factory = SpawnerFactory()
        _default_factory.register_defaults()
    return _default_factory


def set_default_factory(factory: Optional[SpawnerFactory]) -> None:
    """Set the default spawner factory.

    Args:
        factory: Factory to set as default (or None to reset)
    """
    global _default_factory
    _default_factory = factory


def reset_default_factory() -> None:
    """Reset the default spawner factory."""
    global _default_factory
    _default_factory = None
