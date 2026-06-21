"""
Tests for session-tool guardrails — rule engine fires on Claude Code tool calls.

All tests FAIL until implementation exists.
"""

import json
import tempfile
from pathlib import Path

import pytest
from click.testing import CliRunner

from cli.core.org_init import OrgInitConfig, init_org


@pytest.fixture
def org(tmp_path):
    org_path = tmp_path / "org"
    org_path.mkdir()
    cfg = OrgInitConfig(path=org_path, name="GuardTest", ceo_name="Alice", ceo_role="CEO")
    result = init_org(cfg)
    assert result.success, result.error
    return org_path


# ---------------------------------------------------------------------------
# qn-tool-guard CLI: stdin JSON → rule evaluation → exit code
# ---------------------------------------------------------------------------

def test_tool_guard_command_exists() -> None:
    from cli.commands.qn_tool_guard import tool_guard_main
    assert callable(tool_guard_main)


def test_tool_guard_allows_safe_bash(org: Path) -> None:
    from cli.commands.qn_tool_guard import evaluate_tool_call

    result = evaluate_tool_call(
        tool_name="Bash",
        tool_input={"command": "ls -la"},
        org_path=org,
        worker_id="wrkr-test",
    )
    assert result.allowed is True


def test_tool_guard_blocks_rm_rf_storage(org: Path) -> None:
    from cli.commands.qn_tool_guard import evaluate_tool_call

    result = evaluate_tool_call(
        tool_name="Bash",
        tool_input={"command": "rm -rf storage/workers/ceo"},
        org_path=org,
        worker_id="wrkr-test",
    )
    assert result.allowed is False
    assert "no-rm-rf-storage" in result.rule_id


def test_tool_guard_blocks_force_push_main(org: Path) -> None:
    from cli.commands.qn_tool_guard import evaluate_tool_call

    result = evaluate_tool_call(
        tool_name="Bash",
        tool_input={"command": "git push --force origin main"},
        org_path=org,
        worker_id="wrkr-test",
    )
    assert result.allowed is False
    assert "no-force-push-main" in result.rule_id


def test_tool_guard_blocks_drop_table_in_bash(org: Path) -> None:
    from cli.commands.qn_tool_guard import evaluate_tool_call

    result = evaluate_tool_call(
        tool_name="Bash",
        tool_input={"command": "sqlite3 live/quinn.db 'DROP TABLE workers'"},
        org_path=org,
        worker_id="wrkr-test",
    )
    assert result.allowed is False
    assert "no-drop-database" in result.rule_id


def test_tool_guard_allows_write_to_safe_path(org: Path) -> None:
    from cli.commands.qn_tool_guard import evaluate_tool_call

    result = evaluate_tool_call(
        tool_name="Write",
        tool_input={"file_path": "/tmp/notes.md", "content": "my notes"},
        org_path=org,
        worker_id="wrkr-test",
    )
    assert result.allowed is True


def test_tool_guard_blocks_secret_file_write(org: Path) -> None:
    from cli.commands.qn_tool_guard import evaluate_tool_call

    result = evaluate_tool_call(
        tool_name="Write",
        tool_input={"file_path": "/tmp/credentials.json", "content": "{}"},
        org_path=org,
        worker_id="wrkr-test",
    )
    assert result.allowed is False
    assert "no-secret-commit" in result.rule_id


def test_tool_guard_blocked_result_has_message(org: Path) -> None:
    from cli.commands.qn_tool_guard import evaluate_tool_call

    result = evaluate_tool_call(
        tool_name="Bash",
        tool_input={"command": "rm -rf storage"},
        org_path=org,
        worker_id="wrkr-test",
    )
    assert result.allowed is False
    assert result.message  # non-empty
    assert result.rule_id  # non-empty


def test_tool_guard_unknown_tool_allows(org: Path) -> None:
    from cli.commands.qn_tool_guard import evaluate_tool_call

    result = evaluate_tool_call(
        tool_name="SomeUnknownTool",
        tool_input={"whatever": "data"},
        org_path=org,
        worker_id="wrkr-test",
    )
    assert result.allowed is True


# ---------------------------------------------------------------------------
# GuardResult dataclass
# ---------------------------------------------------------------------------

def test_guard_result_dataclass_exists() -> None:
    from cli.commands.qn_tool_guard import GuardResult

    r = GuardResult(allowed=True, rule_id=None, message=None)
    assert r.allowed is True

    r2 = GuardResult(allowed=False, rule_id="no-rm-rf-storage", message="blocked")
    assert r2.allowed is False
    assert r2.rule_id == "no-rm-rf-storage"


# ---------------------------------------------------------------------------
# Hook config generation
# ---------------------------------------------------------------------------

def test_hook_config_writer_exists() -> None:
    from cli.core.session.tool_guard import write_tool_guard_hook_config
    assert callable(write_tool_guard_hook_config)


def test_hook_config_written_to_working_dir(tmp_path: Path, org: Path) -> None:
    from cli.core.session.tool_guard import write_tool_guard_hook_config

    working_dir = tmp_path / "worker_cwd"
    working_dir.mkdir()

    write_tool_guard_hook_config(working_dir=working_dir, org_path=org, worker_id="wrkr-123")

    settings = working_dir / ".claude" / "settings.json"
    assert settings.exists(), f"Expected {settings} to exist"


def test_hook_config_contains_pretooluse_hook(tmp_path: Path, org: Path) -> None:
    from cli.core.session.tool_guard import write_tool_guard_hook_config

    working_dir = tmp_path / "worker_cwd"
    working_dir.mkdir()
    write_tool_guard_hook_config(working_dir=working_dir, org_path=org, worker_id="wrkr-123")

    settings = working_dir / ".claude" / "settings.json"
    data = json.loads(settings.read_text())
    assert "hooks" in data
    hooks = data["hooks"]
    assert "PreToolUse" in hooks or any("PreToolUse" in str(h) for h in hooks)


def test_hook_config_includes_qn_tool_guard_command(tmp_path: Path, org: Path) -> None:
    from cli.core.session.tool_guard import write_tool_guard_hook_config

    working_dir = tmp_path / "worker_cwd"
    working_dir.mkdir()
    write_tool_guard_hook_config(working_dir=working_dir, org_path=org, worker_id="wrkr-123")

    settings = working_dir / ".claude" / "settings.json"
    content = settings.read_text()
    assert "qn-tool-guard" in content


def test_hook_command_is_path_resolvable_without_session_path(
    tmp_path: Path, org: Path
) -> None:
    """The PreToolUse hook command must resolve without relying on the
    spawned session's PATH (quinn-ai-8hh7).

    The worker 'claude' session shell does not inherit the quinnai venv bin
    on its PATH, so a bare 'qn-tool-guard' resolves to
    '/bin/sh: qn-tool-guard: command not found' and every Bash tool call
    emits 'Error: Exit code 1' noise. The command's executable token must be
    an absolute path that actually exists on disk.
    """
    import os

    from cli.core.session.tool_guard import write_tool_guard_hook_config

    working_dir = tmp_path / "worker_cwd"
    working_dir.mkdir()
    write_tool_guard_hook_config(working_dir=working_dir, org_path=org, worker_id="wrkr-123")

    settings = working_dir / ".claude" / "settings.json"
    data = json.loads(settings.read_text())
    command = data["hooks"]["PreToolUse"][0]["hooks"][0]["command"]

    executable_token = command.split()[0]
    assert os.path.isabs(executable_token), (
        f"hook command must be an absolute path (session PATH lacks venv bin), "
        f"got: {command!r}"
    )
    assert os.path.exists(executable_token), (
        f"hook command does not exist on disk: {executable_token!r}"
    )


def test_hook_config_write_is_idempotent(tmp_path: Path, org: Path) -> None:
    """Writing the hook twice must not register the guard twice — the dedup
    matches on the executable basename so a re-spawn into the same cwd doesn't
    accumulate duplicate PreToolUse hooks.
    """
    from cli.core.session.tool_guard import write_tool_guard_hook_config

    working_dir = tmp_path / "worker_cwd"
    working_dir.mkdir()
    write_tool_guard_hook_config(working_dir=working_dir, org_path=org, worker_id="wrkr-123")
    write_tool_guard_hook_config(working_dir=working_dir, org_path=org, worker_id="wrkr-123")

    data = json.loads((working_dir / ".claude" / "settings.json").read_text())
    guard_cmds = [
        h.get("command")
        for entry in data["hooks"]["PreToolUse"]
        for h in entry.get("hooks", [])
        if h.get("command", "").endswith("qn-tool-guard")
    ]
    assert len(guard_cmds) == 1, f"expected one guard hook, got {guard_cmds!r}"


# ---------------------------------------------------------------------------
# default_rules.yaml: ABSOLUTE rules include shell.bash
# ---------------------------------------------------------------------------

def test_absolute_rules_include_shell_bash_action() -> None:
    from cli.core.rules.loader import load_rules
    from pathlib import Path

    # Load the bundled default rules (no org-specific override)
    ruleset = load_rules(Path("/nonexistent"))  # triggers fallback to default

    absolute_rules = [r for r in ruleset.rules if r.severity.value == "ABSOLUTE"]
    assert absolute_rules, "No ABSOLUTE rules found"

    for rule in absolute_rules:
        assert "shell.bash" in rule.actions, (
            f"Rule {rule.id} missing shell.bash action. Got: {rule.actions}"
        )


def test_rm_rf_rule_fires_on_shell_bash(org: Path) -> None:
    from cli.core.rules.engine import RuleEngine
    from cli.core.rules.loader import load_rules
    from cli.core.rules.audit import AuditLogger
    from cli.core.rules.types import DecisionKind

    ruleset = load_rules(org)
    audit = AuditLogger(org / "live" / "rules-audit.jsonl")
    engine = RuleEngine(ruleset, db=None, audit_logger=audit)

    decision = engine.evaluate(
        "shell.bash",
        {"body": "rm -rf storage/workers", "worker_id": "w1", "env": "dev",
         "args": {}, "target_paths": [], "command": "rm -rf storage/workers"},
    )
    assert decision.kind in (DecisionKind.BLOCK,), f"Expected BLOCK, got {decision.kind}"


def test_force_push_rule_fires_on_shell_bash(org: Path) -> None:
    from cli.core.rules.engine import RuleEngine
    from cli.core.rules.loader import load_rules
    from cli.core.rules.audit import AuditLogger
    from cli.core.rules.types import DecisionKind

    ruleset = load_rules(org)
    audit = AuditLogger(org / "live" / "rules-audit.jsonl")
    engine = RuleEngine(ruleset, db=None, audit_logger=audit)

    decision = engine.evaluate(
        "shell.bash",
        {"body": "git push --force origin main", "worker_id": "w1", "env": "dev",
         "args": {}, "target_paths": [], "command": "git push --force origin main"},
    )
    assert decision.kind in (DecisionKind.BLOCK,), f"Expected BLOCK, got {decision.kind}"
