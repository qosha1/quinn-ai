"""Write Claude Code PreToolUse hook config into a worker's working directory.

Called at worker spawn time so every tool use in their session runs through
the rule engine before executing.

Claude Code hook protocol:
- hooks are configured in .claude/settings.json
- PreToolUse hook receives JSON on stdin: {"tool_name": "...", "tool_input": {...}}
- Exit 0 → allow, exit 1 → block (stdout shown to model), exit 2 → ignore error
"""

from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

# Basename of the console-script installed by pyproject.toml [project.scripts].
TOOL_GUARD_EXECUTABLE = "qn-tool-guard"


def resolve_tool_guard_command() -> str:
    """Return an invocation for the qn-tool-guard hook that does not depend on
    the spawned session's PATH.

    The worker 'claude' session shell is launched without the quinnai venv bin
    on its PATH, so a bare 'qn-tool-guard' resolves to
    '/bin/sh: qn-tool-guard: command not found' and every Bash tool call emits
    'Error: Exit code 1' noise (quinn-ai-8hh7). The console-script is installed
    alongside the running interpreter, so resolve it from there first;
    shutil.which is unreliable because the venv bin is typically not on PATH
    even inside the venv's own interpreter.
    """
    # Prefer the console-script next to the running interpreter (venv bin).
    candidate = Path(sys.executable).parent / TOOL_GUARD_EXECUTABLE
    if candidate.exists():
        return str(candidate)
    # Fall back to a PATH lookup (covers system-wide / non-venv installs).
    found = shutil.which(TOOL_GUARD_EXECUTABLE)
    if found:
        return found
    # Last resort: bare name (old behavior). No worse than before if the
    # console-script can't be located by either method above.
    return TOOL_GUARD_EXECUTABLE


def write_tool_guard_hook_config(
    *,
    working_dir: Path,
    org_path: Path,
    worker_id: str,
) -> None:
    """Write .claude/settings.json with PreToolUse hook into working_dir.

    If a settings.json already exists, merges the hook into it without
    overwriting other settings.

    Args:
        working_dir: The worker session's working directory (cwd at spawn)
        org_path: Absolute path to the org root (passed to the hook via env)
        worker_id: Worker ID (passed to the hook via env)
    """
    claude_dir = working_dir / ".claude"
    claude_dir.mkdir(parents=True, exist_ok=True)
    settings_path = claude_dir / "settings.json"

    # Load existing settings or start fresh
    if settings_path.exists():
        try:
            settings: dict = json.loads(settings_path.read_text())
        except Exception:
            settings = {}
    else:
        settings = {}

    # Build the hook command. The hook receives stdin JSON from Claude Code
    # and calls qn-tool-guard which reads ORG_PATH + WORKER_ID from env.
    # Resolve to an absolute path so it works even though the session shell's
    # PATH does not include the venv bin (quinn-ai-8hh7).
    command = resolve_tool_guard_command()
    hook_entry = {
        "hooks": {
            "PreToolUse": [
                {
                    "matcher": "",  # empty = match all tools
                    "hooks": [
                        {
                            "type": "command",
                            "command": command,
                        }
                    ],
                }
            ]
        }
    }

    # Merge: don't clobber existing hooks, just add ours
    existing_hooks = settings.get("hooks", {})
    new_hooks = hook_entry["hooks"]
    for event, entries in new_hooks.items():
        if event not in existing_hooks:
            existing_hooks[event] = entries
        else:
            # Append if our guard isn't already registered. Match on the
            # executable basename so a previously-written bare or absolute
            # command both count as "already present" (no duplicates).
            existing_cmds = {
                h.get("command")
                for entry in existing_hooks[event]
                for h in entry.get("hooks", [])
            }
            already_present = any(
                cmd and Path(str(cmd).split()[0]).name == TOOL_GUARD_EXECUTABLE
                for cmd in existing_cmds
            )
            if not already_present:
                existing_hooks[event].extend(entries)
    settings["hooks"] = existing_hooks

    settings_path.write_text(json.dumps(settings, indent=2))
