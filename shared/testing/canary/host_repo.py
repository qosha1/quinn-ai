"""Isolated, throwaway host-repo fixtures for host-mode canaries (quinn-ai-a3pg).

A canary that "pushes PRs" must NEVER touch real code. This builds a fully
self-contained, throwaway Simpli-shaped repo whose ONLY git remote is a LOCAL
bare repo — so a live worker can branch, commit, push, and "open a PR" with
zero blast radius. Everything lives under the harness tmpdir and is removed on
teardown; nothing is networked.

The builder + spec writer are pure/deterministic (no LLM), so the scaffolding
gets $0, 100%-repeatable unit tests. Only the live ops (start_org, kickstart)
cost money, and they're gated by QUINNAI_RUN_CANARY=1.
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import TYPE_CHECKING, Any

from shared.testing.scenarios import OPS, PREDICATES

if TYPE_CHECKING:
    from shared.testing.scenarios import ScenarioRun


# Concise Simpli conventions — enough to make the repo genuinely "Simpli-shaped"
# and to exercise the host-mode profile/CLAUDE.md layering.
_SIMPLI_CLAUDE_MD = """# CLAUDE.md (throwaway canary fixture)

This is an ISOLATED throwaway Simpli-shaped repo for a QuinnAI canary.
Conventions: shared code lives in `packages/`; apps in `apps/`; TypeScript must
compile; camelCase on the wire. The only git remote `origin` is a LOCAL bare
repo — pushing here never reaches GitHub.
"""

_PROVIDERS_YAML = """default: claude_code
authorized_providers: [claude_code]
providers:
  claude_code:
    enabled: true
    api_key: ${ANTHROPIC_API_KEY}
"""

_SIMPLI_PROFILE_YAML = """profile: simpli
conventions:
  - "Shared packages over app src"
  - "camelCase on the wire"
  - "TypeScript must compile after every change"
references:
  packages: "packages/* — shared libraries"
  apps: "apps/* — customer-facing apps"
"""


def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True, text=True)


def build_simpli_host_repo(project_root: Path, *, app: str = "raise") -> str:
    """Create a throwaway Simpli-shaped git repo with a LOCAL bare remote.

    Args:
        project_root: Directory to populate as the project root (host target).
        app: Name of a sample app dir under apps/.

    Returns:
        Absolute path to the local bare remote (origin) — never networked.
    """
    project_root = Path(project_root)
    (project_root / "packages" / "utils" / "src").mkdir(parents=True, exist_ok=True)
    (project_root / "apps" / app).mkdir(parents=True, exist_ok=True)
    (project_root / "CLAUDE.md").write_text(_SIMPLI_CLAUDE_MD)
    (project_root / "pnpm-workspace.yaml").write_text(
        "packages:\n  - 'packages/*'\n  - 'apps/*'\n"
    )
    (project_root / "packages" / "utils" / "src" / "index.ts").write_text(
        'export const VERSION = "0.0.1";\n'
    )

    bare = project_root.parent / "origin.git"
    subprocess.run(["git", "init", "--bare", "-q", str(bare)], check=True, capture_output=True)

    _git(project_root, "init", "-q")
    _git(project_root, "config", "user.email", "canary@example.com")
    _git(project_root, "config", "user.name", "Canary")
    _git(project_root, "config", "commit.gpgsign", "false")
    _git(project_root, "add", "-A")
    _git(project_root, "commit", "-qm", "init throwaway simpli repo")
    _git(project_root, "branch", "-M", "main")
    _git(project_root, "remote", "add", "origin", str(bare))
    _git(project_root, "push", "-u", "origin", "main")
    return str(bare)


def write_host_org_spec(
    spec_dir: Path, project_root: Path, *, app_worker: bool = False
) -> Path:
    """Write a host-mode org.yml (+ config + simpli profile) for the canary.

    Args:
        spec_dir: Directory to write the spec + its $ref'd config files into.
        project_root: The host target repo (becomes host.project_root).
        app_worker: If True, declare one app-group engineer the CEO can delegate
            to / that gets hired; otherwise CEO-only.

    Returns:
        Path to the written org.yml.
    """
    spec_dir = Path(spec_dir)
    (spec_dir / "config").mkdir(parents=True, exist_ok=True)
    (spec_dir / "profiles").mkdir(parents=True, exist_ok=True)
    (spec_dir / "config" / "providers.yaml").write_text(_PROVIDERS_YAML)
    (spec_dir / "profiles" / "simpli.yaml").write_text(_SIMPLI_PROFILE_YAML)

    structure = ""
    if app_worker:
        structure = (
            "structure:\n"
            "  teams:\n"
            "    - name: raise\n"
            "      manager: { name: Remy, role: engineer }\n"
        )
    org_yml = spec_dir / "org.yml"
    org_yml.write_text(
        "apiVersion: quinnai/v1\n"
        "metadata: { name: simpli-canary, profile: simpli }\n"
        f"host: {{ project_root: {project_root} }}\n"
        "providers: { $ref: config/providers.yaml }\n"
        "ceo: { name: Quinn, role: CEO }\n"
        + structure
    )
    return org_yml


def op_setup_host_repo(run: "ScenarioRun", op: dict[str, Any]) -> None:
    """Build the isolated throwaway repo + bare remote, then build the host org.

    Requires the harness to have been entered with setup.host_mode: true, so
    run.org_path is <project>/.quinnai. Populates <project>, creates the local
    bare remote, and applies a generated org.yml in host mode.

    YAML form:
      - { op: setup_host_repo }                 # CEO-only
      - { op: setup_host_repo, app_worker: true }  # + one app-group engineer
    """
    from cli.core.org_spec import apply_org_spec, load_org_spec

    project_root = run.org_path.parent  # host_mode: org_path = <project>/.quinnai
    bare = build_simpli_host_repo(project_root, app=op.get("app", "raise"))
    run.context["bare_remote"] = bare
    run.context["project_root"] = str(project_root)
    run.context["deliverable"] = str(
        project_root / "packages" / "utils" / "src" / "index.ts"
    )

    spec_dir = project_root.parent / "spec"
    org_yml = write_host_org_spec(
        spec_dir, project_root, app_worker=bool(op.get("app_worker", False))
    )
    apply_org_spec(load_org_spec(org_yml), update=True)


def pred_branch_on_remote(run: "ScenarioRun", a: dict[str, Any]) -> str | None:
    """Assert the local bare remote has a branch matching a pattern.

    This is the isolated stand-in for "a PR was opened": a worker pushed a
    branch to the throwaway origin. Never inspects any networked remote.

    YAML form:
      - { kind: branch_on_remote, pattern: "quinnai/" }
    """
    bare = run.context.get("bare_remote")
    if not bare:
        return "branch_on_remote: no bare_remote in context (run setup_host_repo first)"
    pattern = a.get("pattern", "quinnai/")
    result = subprocess.run(
        ["git", "ls-remote", "--heads", str(bare)],
        capture_output=True, text=True, check=False,
    )
    if result.returncode != 0:
        return f"branch_on_remote: git ls-remote failed: {result.stderr.strip()}"
    branches = [
        line.split("refs/heads/", 1)[1]
        for line in result.stdout.splitlines()
        if "refs/heads/" in line
    ]
    matching = [b for b in branches if pattern in b]
    if matching:
        return None
    return (
        f"branch_on_remote: no branch matching {pattern!r} on the bare remote "
        f"(have: {branches})"
    )


def pred_deliverable_contains(run: "ScenarioRun", a: dict[str, Any]) -> str | None:
    """Assert the runtime deliverable file contains a substring.

    The deliverable path is dynamic (under the harness tmpdir), so it's read
    from run.context['deliverable'] set by setup_host_repo — specs can't
    hardcode it.

    YAML form:
      - { kind: deliverable_contains, substring: "CANARY_OK" }
    """
    path = run.context.get("deliverable")
    if not path:
        return "deliverable_contains: no deliverable in context (run setup_host_repo first)"
    substring = a["substring"]
    try:
        text = Path(path).read_text()
    except FileNotFoundError:
        return f"deliverable_contains: {path} not found"
    if substring in text:
        return None
    return f"deliverable_contains: {substring!r} not in {path}"


OPS.setdefault("setup_host_repo", op_setup_host_repo)
PREDICATES.setdefault("branch_on_remote", pred_branch_on_remote)
PREDICATES.setdefault("deliverable_contains", pred_deliverable_contains)
