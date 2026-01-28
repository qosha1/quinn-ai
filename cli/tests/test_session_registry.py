"""
Tests for SessionRegistry.
"""

import pytest
from unittest.mock import Mock

from cli.core.session import SessionInterface, SessionConfig
from cli.core.sessions.registry import (
    SessionRegistry,
    AdapterNotFoundError,
    get_default_registry,
    create_default_registry,
    initialize_defaults,
    set_default_registry,
    reset_default_registry,
)
from cli.core.sessions import ClaudeCodeSession


class MockSessionAdapter(SessionInterface):
    """Mock session adapter for testing."""

    def __init__(self, config: SessionConfig, **kwargs):
        super().__init__(config)
        self.kwargs = kwargs

    @property
    def provider_name(self) -> str:
        return "mock"

    @property
    def pid(self):
        return None

    def _spawn_process(self) -> None:
        pass

    def _terminate_process(self, force: bool = False) -> None:
        pass

    def _send_input(self, text: str) -> None:
        pass

    def _read_output(self, timeout_ms=None):
        from cli.core.session import SessionOutput
        from datetime import datetime
        return SessionOutput(content="", timestamp=datetime.now())

    def _detect_ready(self, output: str) -> bool:
        return True

    def _detect_completion(self, output: str) -> bool:
        return True

    def _get_context_usage(self) -> int:
        return 0

    def _send_interrupt(self) -> None:
        pass

    def _create_state_monitor(self):
        return None


class AnotherMockAdapter(SessionInterface):
    """Another mock adapter for testing multiple registrations."""

    def __init__(self, config: SessionConfig, **kwargs):
        super().__init__(config)

    @property
    def provider_name(self) -> str:
        return "another"

    @property
    def pid(self):
        return None

    def _spawn_process(self) -> None:
        pass

    def _terminate_process(self, force: bool = False) -> None:
        pass

    def _send_input(self, text: str) -> None:
        pass

    def _read_output(self, timeout_ms=None):
        from cli.core.session import SessionOutput
        from datetime import datetime
        return SessionOutput(content="", timestamp=datetime.now())

    def _detect_ready(self, output: str) -> bool:
        return True

    def _detect_completion(self, output: str) -> bool:
        return True

    def _get_context_usage(self) -> int:
        return 0

    def _send_interrupt(self) -> None:
        pass

    def _create_state_monitor(self):
        return None


class TestSessionRegistry:
    """Tests for SessionRegistry class."""

    def test_register_adapter(self):
        """Should register an adapter by name."""
        registry = SessionRegistry()
        registry.register("mock", MockSessionAdapter)

        assert registry.has("mock")
        assert registry.get("mock") is MockSessionAdapter

    def test_register_with_aliases(self):
        """Should register adapter with aliases."""
        registry = SessionRegistry()
        registry.register("mock", MockSessionAdapter, aliases=["m", "test"])

        assert registry.has("mock")
        assert registry.has("m")
        assert registry.has("test")

        # All resolve to same class
        assert registry.get("mock") is MockSessionAdapter
        assert registry.get("m") is MockSessionAdapter
        assert registry.get("test") is MockSessionAdapter

    def test_case_insensitive_lookup(self):
        """Should support case-insensitive lookup."""
        registry = SessionRegistry()
        registry.register("mock", MockSessionAdapter)

        assert registry.has("MOCK")
        assert registry.has("Mock")
        assert registry.has("mOcK")
        assert registry.get("MOCK") is MockSessionAdapter

    def test_get_nonexistent_raises(self):
        """Should raise AdapterNotFoundError for unknown adapter."""
        registry = SessionRegistry()
        registry.register("mock", MockSessionAdapter)

        with pytest.raises(AdapterNotFoundError) as exc_info:
            registry.get("unknown")

        assert exc_info.value.provider == "unknown"
        assert "mock" in exc_info.value.available

    def test_has_returns_false_for_unknown(self):
        """Should return False for unknown adapters."""
        registry = SessionRegistry()
        assert not registry.has("unknown")

    def test_create_instance(self):
        """Should create adapter instance with config."""
        registry = SessionRegistry()
        registry.register("mock", MockSessionAdapter)

        config = SessionConfig(
            worker_id="test-worker",
            provider="mock",
            command="/usr/bin/mock-cli",
        )

        session = registry.create("mock", config)

        assert isinstance(session, MockSessionAdapter)
        assert session.config == config

    def test_create_with_kwargs(self):
        """Should pass kwargs to adapter constructor."""
        registry = SessionRegistry()
        registry.register("mock", MockSessionAdapter)

        config = SessionConfig(
            worker_id="test-worker",
            provider="mock",
            command="/usr/bin/mock-cli",
        )

        session = registry.create("mock", config, extra_param="value")

        assert session.kwargs["extra_param"] == "value"

    def test_list_adapters(self):
        """Should list canonical adapter names."""
        registry = SessionRegistry()
        registry.register("mock", MockSessionAdapter, aliases=["m"])
        registry.register("another", AnotherMockAdapter)

        adapters = registry.list_adapters()

        assert "mock" in adapters
        assert "another" in adapters
        assert "m" not in adapters  # Alias not in canonical list

    def test_list_all_includes_aliases(self):
        """Should list all names including aliases."""
        registry = SessionRegistry()
        registry.register("mock", MockSessionAdapter, aliases=["m", "test"])

        all_names = registry.list_all()

        assert "mock" in all_names
        assert "m" in all_names
        assert "test" in all_names

    def test_get_canonical_name(self):
        """Should resolve alias to canonical name."""
        registry = SessionRegistry()
        registry.register("mock", MockSessionAdapter, aliases=["m"])

        assert registry.get_canonical_name("mock") == "mock"
        assert registry.get_canonical_name("m") == "mock"
        assert registry.get_canonical_name("unknown") is None

    def test_clear(self):
        """Should clear all registrations."""
        registry = SessionRegistry()
        registry.register("mock", MockSessionAdapter, aliases=["m"])

        registry.clear()

        assert not registry.has("mock")
        assert not registry.has("m")
        assert registry.list_adapters() == []


class TestAdapterNotFoundError:
    """Tests for AdapterNotFoundError exception."""

    def test_error_message(self):
        """Should have informative error message."""
        error = AdapterNotFoundError("unknown", ["claude_code", "openai"])

        assert "unknown" in str(error)
        assert "claude_code" in str(error)
        assert "openai" in str(error)

    def test_attributes(self):
        """Should store provider and available list."""
        error = AdapterNotFoundError("bad", ["good1", "good2"])

        assert error.provider == "bad"
        assert error.available == ["good1", "good2"]


class TestDefaultRegistry:
    """Tests for default registry functions."""

    def setup_method(self):
        """Reset registry before each test."""
        reset_default_registry()

    def teardown_method(self):
        """Reset registry after each test."""
        reset_default_registry()

    def test_get_default_registry_lazy_init(self):
        """Should lazily initialize default registry."""
        registry = get_default_registry()

        assert registry is not None
        assert isinstance(registry, SessionRegistry)
        # Should have claude_code registered
        assert registry.has("claude_code")

    def test_get_default_registry_singleton(self):
        """Should return same instance on subsequent calls."""
        registry1 = get_default_registry()
        registry2 = get_default_registry()

        assert registry1 is registry2

    def test_create_default_registry(self):
        """Should create new registry with defaults each time."""
        registry1 = create_default_registry()
        registry2 = create_default_registry()

        assert registry1 is not registry2
        assert registry1.has("claude_code")
        assert registry2.has("claude_code")

    def test_default_registry_has_claude_code_aliases(self):
        """Should register claude_code with aliases."""
        registry = create_default_registry()

        assert registry.has("claude_code")
        assert registry.has("claude")
        assert registry.has("anthropic")
        assert registry.has("claude-code")

        # All resolve to ClaudeCodeSession
        assert registry.get("claude") is ClaudeCodeSession
        assert registry.get("anthropic") is ClaudeCodeSession

    def test_initialize_defaults(self):
        """Should initialize and return default registry."""
        registry = initialize_defaults()

        assert registry is not None
        assert registry.has("claude_code")

        # Should be set as default
        assert get_default_registry() is registry

    def test_set_default_registry(self):
        """Should allow setting custom default registry."""
        custom = SessionRegistry()
        custom.register("custom", MockSessionAdapter)

        set_default_registry(custom)

        assert get_default_registry() is custom
        assert get_default_registry().has("custom")

    def test_reset_default_registry(self):
        """Should reset to None for lazy re-initialization."""
        # Get initial registry
        initial = get_default_registry()

        # Reset
        reset_default_registry()

        # Next call should create new registry
        new = get_default_registry()
        assert new is not initial
