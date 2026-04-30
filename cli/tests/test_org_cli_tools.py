"""
Tests for org CLI tool dependencies feature.

These tests define the expected behavior BEFORE implementation exists.
They should all fail until the feature is built.
"""

from pathlib import Path
from unittest.mock import patch

import pytest

from cli.core.org_init import OrgInitConfig, init_org


def _init_org(org_path: Path) -> None:
    config = OrgInitConfig(path=org_path, name=org_path.name, ceo_name="CEO", ceo_role="CEO")
    result = init_org(config)
    assert result.success, result.error


# ---------------------------------------------------------------------------
# ToolDependency dataclass
# ---------------------------------------------------------------------------

def test_tool_dependency_requires_name() -> None:
    from shared.core.tools import ToolDependency

    tool = ToolDependency(name="rc")
    assert tool.name == "rc"
    assert tool.description == ""
    assert tool.install_cmd == ""
    assert tool.check_cmd == ""


def test_tool_dependency_full_fields() -> None:
    from shared.core.tools import ToolDependency

    tool = ToolDependency(
        name="rc",
        description="Remote compose CLI",
        install_cmd="brew install rc",
        check_cmd="which rc",
    )
    assert tool.name == "rc"
    assert tool.description == "Remote compose CLI"
    assert tool.install_cmd == "brew install rc"
    assert tool.check_cmd == "which rc"


# ---------------------------------------------------------------------------
# OrgToolsConfig — load from YAML
# ---------------------------------------------------------------------------

def test_org_tools_config_loads_from_yaml(tmp_path: Path) -> None:
    from shared.core.tools import OrgToolsConfig

    tools_yaml = tmp_path / "tools.yaml"
    tools_yaml.write_text(
        "tools:\n"
        "  - name: rc\n"
        "    description: Remote compose\n"
        "    install_cmd: brew install rc\n"
        "  - name: gh\n"
        "    description: GitHub CLI\n"
    )

    config = OrgToolsConfig.load_from_yaml(tools_yaml)
    assert len(config.tools) == 2
    assert config.tools[0].name == "rc"
    assert config.tools[0].description == "Remote compose"
    assert config.tools[0].install_cmd == "brew install rc"
    assert config.tools[1].name == "gh"


def test_org_tools_config_empty_when_no_tools_key(tmp_path: Path) -> None:
    from shared.core.tools import OrgToolsConfig

    tools_yaml = tmp_path / "tools.yaml"
    tools_yaml.write_text("tools: []\n")

    config = OrgToolsConfig.load_from_yaml(tools_yaml)
    assert config.tools == []


def test_org_tools_config_missing_file_returns_empty(tmp_path: Path) -> None:
    from shared.core.tools import OrgToolsConfig

    config = OrgToolsConfig.load_from_yaml(tmp_path / "nonexistent.yaml")
    assert config.tools == []


# ---------------------------------------------------------------------------
# check_tool_presence
# ---------------------------------------------------------------------------

def test_check_tool_presence_returns_true_for_installed_tool() -> None:
    from shared.core.tools import check_tool_presence, ToolDependency

    # 'python3' is always available in our test environment
    tool = ToolDependency(name="python3")
    assert check_tool_presence(tool) is True


def test_check_tool_presence_returns_false_for_missing_tool() -> None:
    from shared.core.tools import check_tool_presence, ToolDependency

    tool = ToolDependency(name="definitely-not-a-real-tool-xyz123")
    assert check_tool_presence(tool) is False


def test_check_tool_presence_uses_custom_check_cmd() -> None:
    from shared.core.tools import check_tool_presence, ToolDependency

    # Custom check_cmd that always succeeds
    tool = ToolDependency(name="myapp", check_cmd="echo ok")
    assert check_tool_presence(tool) is True


def test_check_tool_presence_custom_check_cmd_failure() -> None:
    from shared.core.tools import check_tool_presence, ToolDependency

    tool = ToolDependency(name="myapp", check_cmd="false")
    assert check_tool_presence(tool) is False


# ---------------------------------------------------------------------------
# merge_tool_lists
# ---------------------------------------------------------------------------

def test_merge_tool_lists_deduplicates_by_name() -> None:
    from shared.core.tools import ToolDependency, merge_tool_lists

    org_tools = [ToolDependency(name="rc"), ToolDependency(name="gh")]
    worker_tools = [ToolDependency(name="gh"), ToolDependency(name="jq")]

    merged = merge_tool_lists(org_tools, worker_tools)
    names = [t.name for t in merged]
    assert names.count("gh") == 1
    assert "rc" in names
    assert "jq" in names


def test_merge_tool_lists_worker_description_wins_on_conflict() -> None:
    from shared.core.tools import ToolDependency, merge_tool_lists

    org_tools = [ToolDependency(name="gh", description="GitHub CLI")]
    worker_tools = [ToolDependency(name="gh", description="Worker override")]

    merged = merge_tool_lists(org_tools, worker_tools)
    gh = next(t for t in merged if t.name == "gh")
    assert gh.description == "Worker override"


def test_merge_tool_lists_empty_inputs() -> None:
    from shared.core.tools import merge_tool_lists

    assert merge_tool_lists([], []) == []


# ---------------------------------------------------------------------------
# OnboardingContext gets available_tools
# ---------------------------------------------------------------------------

def test_onboarding_context_has_available_tools_field(tmp_path: Path) -> None:
    from cli.core.db import open_database, get_org_db_path
    from cli.core.onboarding import load_onboarding_context
    from cli.core.queries import get_worker_by_name

    org_path = tmp_path / "org"
    org_path.mkdir()
    _init_org(org_path)

    db = open_database(get_org_db_path(org_path))
    try:
        ceo = get_worker_by_name(db, "ceo")
        assert ceo is not None
        ctx = load_onboarding_context(db, ceo.id, org_path)
        # Field must exist (may be empty list if no tools.yaml)
        assert hasattr(ctx, "available_tools")
        assert isinstance(ctx.available_tools, list)
    finally:
        db.close()


def test_onboarding_context_loads_tools_from_yaml(tmp_path: Path) -> None:
    from cli.core.db import open_database, get_org_db_path
    from cli.core.onboarding import load_onboarding_context
    from cli.core.queries import get_worker_by_name

    org_path = tmp_path / "org"
    org_path.mkdir()
    _init_org(org_path)

    # Write a tools.yaml to the org config dir
    tools_yaml = org_path / "config" / "tools.yaml"
    tools_yaml.write_text(
        "tools:\n"
        "  - name: rc\n"
        "    description: Remote compose\n"
    )

    db = open_database(get_org_db_path(org_path))
    try:
        ceo = get_worker_by_name(db, "ceo")
        assert ceo is not None
        ctx = load_onboarding_context(db, ceo.id, org_path)
        assert any(t.name == "rc" for t in ctx.available_tools)
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Briefing renders available tools section
# ---------------------------------------------------------------------------

def _get_worker_briefing(org_path: Path, worker_id: str, db) -> str:
    from cli.core.storage import StorageManager
    storage = StorageManager(org_path, db=db)
    worker_dir = storage.get_worker_path(worker_id)
    return (worker_dir / "BRIEFING.md").read_text()


def test_briefing_renders_tools_section_when_tools_present(tmp_path: Path) -> None:
    from cli.core.db import open_database, get_org_db_path
    from cli.core.onboarding import prepare_worker_onboarding
    from cli.core.queries import get_worker_by_name

    org_path = tmp_path / "org"
    org_path.mkdir()
    _init_org(org_path)

    tools_yaml = org_path / "config" / "tools.yaml"
    tools_yaml.write_text(
        "tools:\n"
        "  - name: rc\n"
        "    description: Remote compose CLI — deploy services\n"
    )

    db = open_database(get_org_db_path(org_path))
    try:
        ceo = get_worker_by_name(db, "ceo")
        assert ceo is not None
        prepare_worker_onboarding(db, ceo.id, org_path)

        briefing = _get_worker_briefing(org_path, ceo.id, db)
        assert "rc" in briefing
        assert "Remote compose CLI" in briefing
    finally:
        db.close()


def test_briefing_omits_tools_section_when_no_tools(tmp_path: Path) -> None:
    from cli.core.db import open_database, get_org_db_path
    from cli.core.onboarding import prepare_worker_onboarding
    from cli.core.queries import get_worker_by_name

    org_path = tmp_path / "org"
    org_path.mkdir()
    _init_org(org_path)

    db = open_database(get_org_db_path(org_path))
    try:
        ceo = get_worker_by_name(db, "ceo")
        assert ceo is not None
        prepare_worker_onboarding(db, ceo.id, org_path)

        briefing = _get_worker_briefing(org_path, ceo.id, db)
        assert "Available CLI Tools" not in briefing
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Worker-level tools stored in DB
# ---------------------------------------------------------------------------

def test_worker_tools_stored_and_retrieved_from_db(tmp_path: Path) -> None:
    from cli.core.db import open_database, get_org_db_path
    from cli.core.queries import get_worker_by_name, set_worker_tools, get_worker_tools

    org_path = tmp_path / "org"
    org_path.mkdir()
    _init_org(org_path)

    db = open_database(get_org_db_path(org_path))
    try:
        ceo = get_worker_by_name(db, "ceo")
        assert ceo is not None

        set_worker_tools(db, ceo.id, [{"name": "jq", "description": "JSON processor"}])
        tools = get_worker_tools(db, ceo.id)
        assert len(tools) == 1
        assert tools[0]["name"] == "jq"
    finally:
        db.close()
