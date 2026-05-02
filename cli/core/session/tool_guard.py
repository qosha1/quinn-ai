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
from pathlib import Path


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
    hook_entry = {
        "hooks": {
            "PreToolUse": [
                {
                    "matcher": "",  # empty = match all tools
                    "hooks": [
                        {
                            "type": "command",
                            "command": "qn-tool-guard",
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
            # Append if our command isn't already registered
            existing_cmds = {
                h.get("command")
                for entry in existing_hooks[event]
                for h in entry.get("hooks", [])
            }
            if "qn-tool-guard" not in existing_cmds:
                existing_hooks[event].extend(entries)
    settings["hooks"] = existing_hooks

    settings_path.write_text(json.dumps(settings, indent=2))
