"""Canary-specific op handlers — registered into Tier 2's OPS registry.

These ops only make sense in a live LLM context where the CEO session can
actually respond to messages. In Tier 2 (FakeSpawner) they're no-ops.
"""
from __future__ import annotations

import time
from pathlib import Path
from typing import TYPE_CHECKING, Any

from shared.testing.scenarios import OPS, PREDICATES

if TYPE_CHECKING:
    from shared.testing.scenarios import ScenarioRun


def op_start_org(run: "ScenarioRun", op: dict[str, Any]) -> None:
    """qn org start — boots the CEO session via the configured provider.

    Defaults to claude-sonnet-4-6 unless QUINNAI_MODEL is set, so canary
    runs are deterministic and don't drift with the user's Claude Max default.
    """
    import os
    from shared.testing.scenarios.ops import _run_qn

    model = os.environ.get("QUINNAI_MODEL", "claude-sonnet-4-6")
    # --skip-config-validation: claude_code authenticates via its own OAuth
    # (Claude Max), so the providers.yaml api_key requirement is a false
    # failure here; config validation has its own dedicated tests. Canaries
    # exercise live org behavior, not provider-config schema.
    _run_qn(run, ["org", "start", "--model", model, "--skip-config-validation"])


def op_send_to_worker(run: "ScenarioRun", op: dict[str, Any]) -> None:
    """msgr send — deliver a directive to a worker's inbox."""
    from shared.testing.scenarios.ops import _run_qn

    worker_id = run._resolve_worker_id(op["worker"])
    # Use the msgr CLI; assume direct-message channel @<worker_id>
    args = ["msgr", "send", f"@{worker_id}", op["message"]]
    _run_qn(run, args)


def op_wait_until(run: "ScenarioRun", op: dict[str, Any]) -> None:
    """Poll a predicate until it passes or a per-op timeout elapses.

    YAML form:
      - { op: wait_until, predicate: { kind: worker_count, value: 2 }, timeout_seconds: 240 }
    """
    timeout = op.get("timeout_seconds", 60)
    poll_interval = op.get("poll_interval_seconds", 2)
    predicate = op["predicate"]

    deadline = time.monotonic() + timeout
    last_violation: str | None = None
    while time.monotonic() < deadline:
        last_violation = run.check(predicate)
        if last_violation is None:
            return
        time.sleep(poll_interval)
    raise RuntimeError(
        f"wait_until timed out after {timeout}s; last violation: {last_violation}"
    )


def _flatten_for_send_keys(message: str) -> str:
    """Make a message safe to type via 'tmux send-keys'.

    tmux types each character literally, so a newline in the message is
    typed as Enter — which on claude_code's TUI submits the partial input
    and the rest of the message lands in subsequent prompts as fragments
    (quinn-ai-wbgv). Collapse newlines to spaces and squeeze runs of
    whitespace so the message arrives as a single prompt submission.
    """
    if "\n" not in message and "\r" not in message:
        return message
    # Replace \r\n / \r / \n with a single space, then squeeze runs of
    # whitespace. A single explicit Enter is sent separately by the caller.
    flat = message.replace("\r\n", " ").replace("\r", " ").replace("\n", " ")
    return " ".join(flat.split())


def op_kickstart_ceo(run: "ScenarioRun", op: dict[str, Any]) -> None:
    """Inject a directive into the CEO's tmux session via send-keys.

    The CEO's auto-delivered INITIAL_TASK.md is best-effort — sometimes the
    model acknowledges but doesn't act. This op explicitly nudges the CEO
    with an action-oriented message that's known to wake claude up and
    drive it through the OKR queue.

    YAML form:
      - { op: kickstart_ceo, message: "Read INITIAL_TASK.md and act on the highest-priority OKR right now." }

    Multi-line messages (YAML 'message: |' block scalars) are flattened to
    a single line before delivery; see _flatten_for_send_keys.

    Reuses the same _wait_for_pane_ready + retry helpers used by qn org start.
    Verifies delivery by capturing the pane after send-keys and confirming
    the message landed; warns loudly if not (qim4 diagnostic).
    """
    import subprocess

    ceo = run.db.find_worker_by_name("ceo")
    if ceo is None:
        raise RuntimeError("kickstart_ceo: no CEO worker found")
    tmux_session = f"qn-{ceo['id']}"
    raw_message = op.get(
        "message",
        "Read INITIAL_TASK.md and act on the highest-priority OKR right now.",
    )
    message = _flatten_for_send_keys(raw_message)

    def _capture():
        try:
            r = subprocess.run(
                ["tmux", "capture-pane", "-t", tmux_session, "-p"],
                capture_output=True, text=True, timeout=2, check=False,
            )
            return r.stdout if r.returncode == 0 else ""
        except Exception:
            return ""

    # Best-effort: reuse production helpers if importable; otherwise inline.
    try:
        from cli.core.org_start_controller import (
            _tmux_send_keys_with_retry,
            _wait_for_pane_ready,
        )
        ready = _wait_for_pane_ready(tmux_session, timeout=15.0)
        before = _capture()
        cmd_ok = _tmux_send_keys_with_retry(tmux_session, message)
        time.sleep(0.5)
        enter_ok = _tmux_send_keys_with_retry(tmux_session, "Enter")
        time.sleep(1.0)
        after = _capture()
        # qim4 diagnostic: verify the message actually landed in the pane.
        # We look for a recognizable substring (first 30 chars of message).
        marker = message[:30].strip()
        landed = bool(marker) and marker in after
        if not landed:
            print(
                f"[kickstart_ceo] WARNING: message did NOT appear in pane.\n"
                f"  ready={ready} cmd_ok={cmd_ok} enter_ok={enter_ok}\n"
                f"  marker={marker!r}\n"
                f"  pane_before_len={len(before)} pane_after_len={len(after)}\n"
                f"  pane_after_tail={after[-300:]!r}"
            )
    except ImportError:
        subprocess.run(["tmux", "send-keys", "-t", tmux_session, message], check=False)
        time.sleep(0.5)
        subprocess.run(["tmux", "send-keys", "-t", tmux_session, "Enter"], check=False)


def op_kickstart_worker(run: "ScenarioRun", op: dict[str, Any]) -> None:
    """Same as kickstart_ceo but for a non-CEO worker.

    Optionally substitutes worker IDs into the message via {self_id} and
    {other_id} format placeholders, which is useful when sending msgr
    directives to peers (the model otherwise has to figure out IDs).

    YAML form:
      - op: kickstart_worker
        worker: bob
        other_worker: carol      # optional; resolves to {other_id}
        message: "Run: msgr --worker-id {self_id} send @{other_id} 'Hi'"
    """
    import subprocess

    worker_name = op["worker"]
    worker = run.db.find_worker_by_name(worker_name)
    if worker is None:
        raise RuntimeError(f"kickstart_worker: no worker named {worker_name!r}")
    tmux_session = f"qn-{worker['id']}"

    fmt = {"self_id": worker["id"]}
    if "other_worker" in op:
        other = run.db.find_worker_by_name(op["other_worker"])
        if other is None:
            raise RuntimeError(
                f"kickstart_worker: no other_worker named {op['other_worker']!r}"
            )
        fmt["other_id"] = other["id"]

    raw_msg = op["message"]
    try:
        formatted = raw_msg.format(**fmt)
    except KeyError:
        # Message used a placeholder we didn't supply — pass through as-is so
        # the operator sees the literal placeholder rather than crashing.
        formatted = raw_msg
    message = _flatten_for_send_keys(formatted)

    try:
        from cli.core.org_start_controller import (
            _tmux_send_keys_with_retry,
            _wait_for_pane_ready,
        )
        _wait_for_pane_ready(tmux_session, timeout=15.0)
        _tmux_send_keys_with_retry(tmux_session, message)
        time.sleep(0.5)
        _tmux_send_keys_with_retry(tmux_session, "Enter")
    except ImportError:
        subprocess.run(["tmux", "send-keys", "-t", tmux_session, message], check=False)
        time.sleep(0.5)
        subprocess.run(["tmux", "send-keys", "-t", tmux_session, "Enter"], check=False)


def _seed_config_file(run: "ScenarioRun", filename: str, content: str) -> Path:
    """Write `content` to <org>/config/<filename>, creating the dir if needed.

    Used by rules_yaml_seed and templates_yaml_seed to plant configuration that
    the org's loaders pick up at startup. Both ops must run BEFORE start_org so
    the rules/templates engine sees the file when it boots.
    """
    config_dir = run.org_path / "config"
    config_dir.mkdir(parents=True, exist_ok=True)
    target = config_dir / filename
    target.write_text(content)
    return target


def op_rules_yaml_seed(run: "ScenarioRun", op: dict[str, Any]) -> None:
    """Seed <org>/config/rules.yaml so the rule engine loads it on org start.

    YAML form:
      - op: rules_yaml_seed
        content: |
          version: 1
          rules:
            - id: no-drop-database
              severity: ABSOLUTE
              ...

    Must run BEFORE start_org. The op only writes the file — it does not
    validate the YAML schema; the rule loader is responsible for that.
    """
    content = op.get("content")
    if not isinstance(content, str):
        raise ValueError(
            "rules_yaml_seed: 'content' is required and must be a string"
        )
    _seed_config_file(run, "rules.yaml", content)


def op_templates_yaml_seed(run: "ScenarioRun", op: dict[str, Any]) -> None:
    """Seed <org>/config/templates.yaml so the templates registry loads it on org start.

    YAML form:
      - op: templates_yaml_seed
        content: |
          version: 1
          templates:
            - name: product_team
              ...

    Must run BEFORE start_org. The op only writes the file — it does not
    validate the YAML schema; the templates loader is responsible for that.
    """
    content = op.get("content")
    if not isinstance(content, str):
        raise ValueError(
            "templates_yaml_seed: 'content' is required and must be a string"
        )
    _seed_config_file(run, "templates.yaml", content)


def op_invoke_qn_bd(run: "ScenarioRun", op: dict[str, Any]) -> None:
    """Directly invoke qn-bd from the harness (not via CEO) to test rules engine.

    Calls qn_bd.main() with patched sys.argv so the rules engine evaluates
    the action against the scenario org. Does NOT spawn a CEO session.

    YAML form:
      - op: invoke_qn_bd
        args: ["create", "--type=task", "--title=foo", "--notes=ARCH-FREEZE tag"]
        expect_exit: 1   # optional; if set, asserts the exit code matches

    Use this to probe the rules engine directly without relying on the CEO.
    The audit log is written regardless of exit code.
    """
    import os
    import sys
    from cli.commands.qn_bd import main as qn_bd_main

    bd_args = op.get("args", [])
    expected_exit = op.get("expect_exit")

    ceo = run.db.find_worker_by_name("ceo")
    worker_id = ceo["id"] if ceo else "test-harness"

    # Patch sys.argv and env, call main(), capture SystemExit.
    saved_argv = sys.argv[:]
    old_env = {}
    for k in ("QUINN_ORG_PATH", "QUINN_WORKER_ID"):
        old_env[k] = os.environ.get(k)

    actual_exit = 0
    try:
        sys.argv = [
            "qn-bd",
            "--org-path", str(run.org_path),
            "--worker-id", worker_id,
        ] + list(bd_args)
        os.environ["QUINN_ORG_PATH"] = str(run.org_path)
        os.environ["QUINN_WORKER_ID"] = worker_id
        qn_bd_main()
    except SystemExit as e:
        actual_exit = int(e.code) if e.code is not None else 0
    finally:
        sys.argv = saved_argv
        for k, v in old_env.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v

    if expected_exit is not None and actual_exit != int(expected_exit):
        raise RuntimeError(
            f"invoke_qn_bd: expected exit {expected_exit}, got {actual_exit}."
        )


# Register into Tier 2's shared registry. Idempotent — safe to import multiple times.
OPS.setdefault("start_org", op_start_org)
OPS.setdefault("send_to_worker", op_send_to_worker)
OPS.setdefault("wait_until", op_wait_until)
OPS.setdefault("kickstart_ceo", op_kickstart_ceo)
OPS.setdefault("kickstart_worker", op_kickstart_worker)
OPS.setdefault("rules_yaml_seed", op_rules_yaml_seed)
OPS.setdefault("templates_yaml_seed", op_templates_yaml_seed)
OPS.setdefault("invoke_qn_bd", op_invoke_qn_bd)
