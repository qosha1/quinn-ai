"""
CLI tool dependency declarations for orgs and workers.
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml


@dataclass
class ToolDependency:
    name: str
    description: str = ""
    install_cmd: str = ""
    check_cmd: str = ""


@dataclass
class OrgToolsConfig:
    tools: list[ToolDependency] = field(default_factory=list)

    @classmethod
    def load_from_yaml(cls, path: Path) -> OrgToolsConfig:
        if not path.exists():
            return cls()
        with open(path) as f:
            data = yaml.safe_load(f) or {}
        raw_tools: list[dict[str, Any]] = data.get("tools") or []
        tools = [
            ToolDependency(
                name=t["name"],
                description=t.get("description", ""),
                install_cmd=t.get("install_cmd", ""),
                check_cmd=t.get("check_cmd", ""),
            )
            for t in raw_tools
        ]
        return cls(tools=tools)


def check_tool_presence(tool: ToolDependency) -> bool:
    """Return True if the tool is available on the current PATH."""
    if tool.check_cmd:
        result = subprocess.run(tool.check_cmd, shell=True, capture_output=True)
        return result.returncode == 0
    result = subprocess.run(["which", tool.name], capture_output=True)
    return result.returncode == 0


def merge_tool_lists(
    org_tools: list[ToolDependency],
    worker_tools: list[ToolDependency],
) -> list[ToolDependency]:
    """Merge org and worker tool lists. Worker entries override org entries by name."""
    merged: dict[str, ToolDependency] = {t.name: t for t in org_tools}
    for tool in worker_tools:
        merged[tool.name] = tool
    return list(merged.values())
