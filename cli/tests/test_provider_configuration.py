"""
Tests for multi-CLI provider configuration system.

Tests cover:
1. Worker preferred_provider field in database
2. Provider preference inheritance (worker -> org default -> fallback)
3. CLI commands for provider management
4. Provider capability detection
5. Configuration validation
"""

import pytest
from pathlib import Path
from unittest.mock import MagicMock, patch
from click.testing import CliRunner

from cli.core.db import init_database, Database
from cli.core.queries.worker import (
    create_worker,
    get_worker,
    update_worker_preferred_provider,
    get_worker_preferred_provider,
)
from cli.core.queries.team import create_team
from cli.core.sessions.capabilities import (
    ProviderCapability,
    get_provider_capabilities,
    has_capability,
    find_providers_with_capability,
    find_providers_with_all_capabilities,
)


@pytest.fixture
def db(tmp_path):
    """Create a test database."""
    db_path = tmp_path / "test.db"
    database = init_database(db_path)
    yield database
    database.close()


@pytest.fixture
def team(db):
    """Create a test team."""
    return create_team(db, name="Test Team")


@pytest.fixture
def worker(db, team):
    """Create a test worker."""
    return create_worker(
        db=db,
        name="Alice",
        role="developer",
        team_id=team.id,
        cost=50,
    )


class TestWorkerPreferredProvider:
    """Tests for worker.preferred_provider field."""

    def test_worker_created_without_preferred_provider(self, db, team):
        """Workers are created with no preferred_provider by default."""
        worker = create_worker(
            db=db,
            name="Bob",
            role="developer",
            team_id=team.id,
            cost=50,
        )

        assert worker.preferred_provider is None

    def test_worker_created_with_preferred_provider(self, db, team):
        """Workers can be created with a preferred_provider."""
        worker = create_worker(
            db=db,
            name="Carol",
            role="developer",
            team_id=team.id,
            cost=50,
            preferred_provider="cursor",
        )

        assert worker.preferred_provider == "cursor"

    def test_update_worker_preferred_provider(self, db, worker):
        """Can update a worker's preferred_provider."""
        assert worker.preferred_provider is None

        update_worker_preferred_provider(db, worker.id, "claude_code")

        updated = get_worker(db, worker.id)
        assert updated.preferred_provider == "claude_code"

    def test_clear_worker_preferred_provider(self, db, team):
        """Can clear a worker's preferred_provider."""
        worker = create_worker(
            db=db,
            name="Dave",
            role="developer",
            team_id=team.id,
            cost=50,
            preferred_provider="cursor",
        )
        assert worker.preferred_provider == "cursor"

        update_worker_preferred_provider(db, worker.id, None)

        updated = get_worker(db, worker.id)
        assert updated.preferred_provider is None

    def test_get_worker_preferred_provider(self, db, team):
        """get_worker_preferred_provider returns correct value."""
        worker = create_worker(
            db=db,
            name="Eve",
            role="developer",
            team_id=team.id,
            cost=50,
            preferred_provider="gemini",
        )

        provider = get_worker_preferred_provider(db, worker.id)
        assert provider == "gemini"

    def test_get_worker_preferred_provider_none(self, db, worker):
        """get_worker_preferred_provider returns None when not set."""
        provider = get_worker_preferred_provider(db, worker.id)
        assert provider is None

    def test_get_worker_preferred_provider_nonexistent(self, db):
        """get_worker_preferred_provider returns None for nonexistent worker."""
        provider = get_worker_preferred_provider(db, "nonexistent-worker-id")
        assert provider is None


class TestProviderCapabilities:
    """Tests for provider capability detection."""

    def test_claude_code_has_shell_capability(self):
        """Claude Code has shell capability."""
        assert has_capability("claude_code", ProviderCapability.SHELL)

    def test_claude_code_has_file_edit_capability(self):
        """Claude Code has file edit capability."""
        assert has_capability("claude_code", ProviderCapability.FILE_EDIT)

    def test_claude_code_has_mcp_capability(self):
        """Claude Code has MCP capability."""
        assert has_capability("claude_code", ProviderCapability.MCP)

    def test_claude_code_full_capabilities(self):
        """Claude Code has comprehensive capabilities."""
        caps = get_provider_capabilities("claude_code")

        # Core capabilities
        assert ProviderCapability.SHELL in caps
        assert ProviderCapability.FILE_EDIT in caps
        assert ProviderCapability.FILE_READ in caps

        # AI capabilities
        assert ProviderCapability.VISION in caps
        assert ProviderCapability.EXTENDED_THINKING in caps

        # Collaboration
        assert ProviderCapability.MCP in caps

    def test_codex_capabilities(self):
        """Codex has appropriate capabilities."""
        caps = get_provider_capabilities("codex")

        assert ProviderCapability.SHELL in caps
        assert ProviderCapability.FILE_EDIT in caps
        assert ProviderCapability.GIT in caps

        # Should NOT have
        assert ProviderCapability.MCP not in caps
        assert ProviderCapability.VISION not in caps

    def test_gemini_capabilities(self):
        """Gemini has appropriate capabilities."""
        caps = get_provider_capabilities("gemini")

        assert ProviderCapability.LARGE_CONTEXT in caps
        assert ProviderCapability.VISION in caps
        assert ProviderCapability.WEB_SEARCH in caps

        # Should NOT have
        assert ProviderCapability.SHELL not in caps
        assert ProviderCapability.FILE_EDIT not in caps

    def test_openai_capabilities(self):
        """OpenAI has appropriate capabilities."""
        caps = get_provider_capabilities("openai")

        assert ProviderCapability.VISION in caps
        assert ProviderCapability.CODE_INTERPRETER in caps
        assert ProviderCapability.FUNCTION_CALLING in caps

        # Should NOT have
        assert ProviderCapability.SHELL not in caps
        assert ProviderCapability.MCP not in caps

    def test_unknown_provider_empty_capabilities(self):
        """Unknown provider returns empty capabilities."""
        caps = get_provider_capabilities("unknown_provider")
        assert caps == set()

    def test_find_providers_with_shell(self):
        """Find providers with shell capability."""
        providers = find_providers_with_capability(ProviderCapability.SHELL)

        assert "claude_code" in providers
        assert "codex" in providers
        assert "aider" in providers
        assert "cursor" in providers

        # Should NOT include
        assert "gemini" not in providers
        assert "openai" not in providers

    def test_find_providers_with_vision(self):
        """Find providers with vision capability."""
        providers = find_providers_with_capability(ProviderCapability.VISION)

        assert "claude_code" in providers
        assert "gemini" in providers
        assert "openai" in providers

    def test_find_providers_with_all_capabilities(self):
        """Find providers with all specified capabilities."""
        required = {
            ProviderCapability.SHELL,
            ProviderCapability.FILE_EDIT,
            ProviderCapability.GIT,
        }
        providers = find_providers_with_all_capabilities(required)

        assert "claude_code" in providers
        assert "codex" in providers
        assert "cursor" in providers
        assert "aider" in providers

        # Gemini and OpenAI don't have SHELL
        assert "gemini" not in providers
        assert "openai" not in providers


class TestSessionAdapterCapabilities:
    """Tests for capabilities on session adapter classes."""

    def test_claude_code_session_has_capabilities(self):
        """ClaudeCodeSession class has CAPABILITIES attribute."""
        from cli.core.sessions.claude_code import ClaudeCodeSession

        assert hasattr(ClaudeCodeSession, "CAPABILITIES")
        assert isinstance(ClaudeCodeSession.CAPABILITIES, list)
        assert "shell" in ClaudeCodeSession.CAPABILITIES
        assert "file_edit" in ClaudeCodeSession.CAPABILITIES
        assert "mcp" in ClaudeCodeSession.CAPABILITIES

    def test_codex_session_has_capabilities(self):
        """CodexSession class has CAPABILITIES attribute."""
        from cli.core.sessions.codex import CodexSession

        assert hasattr(CodexSession, "CAPABILITIES")
        assert "shell" in CodexSession.CAPABILITIES
        assert "git" in CodexSession.CAPABILITIES

    def test_gemini_session_has_capabilities(self):
        """GeminiSession class has CAPABILITIES attribute."""
        from cli.core.sessions.gemini import GeminiSession

        assert hasattr(GeminiSession, "CAPABILITIES")
        assert "large_context" in GeminiSession.CAPABILITIES
        assert "vision" in GeminiSession.CAPABILITIES

    def test_openai_session_has_capabilities(self):
        """OpenAISession class has CAPABILITIES attribute."""
        from cli.core.sessions.openai import OpenAISession

        assert hasattr(OpenAISession, "CAPABILITIES")
        assert "vision" in OpenAISession.CAPABILITIES
        assert "code_interpreter" in OpenAISession.CAPABILITIES


class TestProviderCLICommands:
    """Tests for provider CLI commands."""

    @pytest.fixture
    def runner(self):
        """Create CLI test runner."""
        return CliRunner()

    @pytest.fixture
    def org_path(self, tmp_path, db, team, worker):
        """Create test org structure."""
        org = tmp_path / "test-org"
        org.mkdir()

        # Create required directories
        (org / "config").mkdir()
        (org / "live").mkdir()
        (org / "storage" / "shared").mkdir(parents=True)
        (org / "storage" / "workers").mkdir(parents=True)

        # Move database
        import shutil
        db.close()
        shutil.copy(tmp_path / "test.db", org / "live" / "quinn.db")

        # Create providers.yaml
        providers_yaml = org / "config" / "providers.yaml"
        providers_yaml.write_text("""
default: claude_code
authorized_providers:
  - claude_code
  - openai
providers:
  claude_code:
    enabled: true
""")

        return org

    def test_provider_list_command(self, runner, org_path):
        """qn org provider list shows available providers."""
        from cli.commands.main import qn

        result = runner.invoke(qn, ["--org-path", str(org_path), "org", "provider", "list"])

        assert result.exit_code == 0
        assert "Available CLI Providers" in result.output
        assert "claude_code" in result.output

    def test_provider_default_show(self, runner, org_path):
        """qn org provider default shows current default."""
        from cli.commands.main import qn

        result = runner.invoke(qn, ["--org-path", str(org_path), "org", "provider", "default"])

        assert result.exit_code == 0
        assert "claude_code" in result.output

    def test_provider_validate_success(self, runner, org_path):
        """qn org provider validate passes with valid config."""
        from cli.commands.main import qn

        result = runner.invoke(qn, ["--org-path", str(org_path), "org", "provider", "validate"])

        assert result.exit_code == 0
        assert "passed" in result.output.lower()
