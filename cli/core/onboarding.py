"""Worker onboarding system.

Provides onboarding context and materials to workers on spawn.
Creates briefings, documentation, and welcome messages for new workers.
"""

from pathlib import Path
from typing import Optional
from dataclasses import dataclass
from datetime import datetime

from jinja2 import Environment, FileSystemLoader, select_autoescape

from cli.core.db import Database
from cli.core.worker import Worker


@dataclass
class OnboardingContext:
    """Context for worker onboarding."""

    worker_id: str
    worker_name: str
    worker_role: str
    team_name: str
    manager_id: Optional[str]
    manager_name: Optional[str]
    org_mission: str
    okrs: list[dict]
    budget_allocated: float
    cost_tier: int
    is_ceo: bool
    is_manager: bool
    timestamp: str


def prepare_worker_onboarding(
    db: Database,
    worker_id: str,
    org_path: Path,
) -> OnboardingContext:
    """Prepare onboarding for a worker.

    Creates:
    - Worker directory (workers/{id}/)
    - BRIEFING.md (role-specific mission and guidance)
    - STORAGE.md (storage architecture guide)
    - Symlinks to CLAUDE.md and AGENTS.md
    - Onboarding directory structure

    Args:
        db: Database instance
        worker_id: Worker ID to onboard
        org_path: Path to organization root

    Returns:
        OnboardingContext with all worker info for env vars and welcome
    """
    # 1. Load worker from database
    worker = Worker.get(db, worker_id)

    # 2. Create worker directory
    worker_dir = org_path / "storage" / "workers" / worker_id
    worker_dir.mkdir(parents=True, exist_ok=True)

    # Create onboarding subdirectory
    onboarding_dir = worker_dir / ".onboarding"
    onboarding_dir.mkdir(exist_ok=True)

    # 3. Load onboarding context
    context = _load_onboarding_context(db, worker, org_path)

    # 4. Generate and write briefing
    _create_briefing(worker_dir, context)

    # 5. Create STORAGE.md guide
    _create_storage_guide(worker_dir, context)

    # 6. Symlink architecture docs
    _link_architecture_docs(worker_dir, org_path)

    return context


def _load_onboarding_context(
    db: Database,
    worker: Worker,
    org_path: Path,
) -> OnboardingContext:
    """Load all context needed for onboarding.

    Args:
        db: Database instance
        worker: Worker object
        org_path: Organization root path

    Returns:
        OnboardingContext with all worker data
    """
    # Get manager info if exists
    manager_id = None
    manager_name = None
    if worker.manager_id:
        try:
            manager = Worker.get(db, worker.manager_id)
            manager_id = manager.id
            manager_name = manager.name
        except Exception:
            pass

    # Get team name (default to role if not set)
    team_name = worker.team or worker.role

    # Get org mission from config or use default
    org_mission = _load_org_mission(org_path)

    # Get worker's OKRs from database
    okrs = _load_worker_okrs(db, worker.id)

    # Get budget info
    budget_allocated = 0.0
    try:
        budget_row = db.fetchone(
            "SELECT allocated FROM budget_allocations WHERE worker_id = ?",
            (worker.id,)
        )
        if budget_row:
            budget_allocated = float(budget_row["allocated"])
    except Exception:
        pass

    # Determine worker type
    is_ceo = worker.role.upper() == "CEO"
    is_manager = worker.manager_id is None and not is_ceo  # Has no manager but isn't CEO

    return OnboardingContext(
        worker_id=worker.id,
        worker_name=worker.name,
        worker_role=worker.role,
        team_name=team_name,
        manager_id=manager_id,
        manager_name=manager_name,
        org_mission=org_mission,
        okrs=okrs,
        budget_allocated=budget_allocated,
        cost_tier=worker.cost_tier,
        is_ceo=is_ceo,
        is_manager=is_manager,
        timestamp=datetime.now().strftime("%Y-%m-%d %H:%M"),
    )


def _load_org_mission(org_path: Path) -> str:
    """Load org mission from config/ceo_briefing.md if it exists.

    Args:
        org_path: Organization root path

    Returns:
        Organization mission string
    """
    briefing_path = org_path / "config" / "ceo_briefing.md"

    if briefing_path.exists():
        content = briefing_path.read_text()
        # Extract first context section if exists
        if "## Context" in content:
            lines = content.split("\n")
            in_context = False
            context_lines = []
            for line in lines:
                if line.startswith("## Context"):
                    in_context = True
                    continue
                elif line.startswith("##") and in_context:
                    break
                elif in_context and line.strip():
                    context_lines.append(line.strip())

            if context_lines:
                return " ".join(context_lines)

    # Default mission
    return "Build great products and serve our customers well."


def _load_worker_okrs(db: Database, worker_id: str) -> list[dict]:
    """Load OKRs for a worker from database.

    Args:
        db: Database instance
        worker_id: Worker ID

    Returns:
        List of OKR dicts with title and key_results
    """
    # For now, return empty - will be populated when OKR system is implemented
    # TODO: Query okrs table when it exists
    return []


def _create_briefing(worker_dir: Path, ctx: OnboardingContext) -> None:
    """Generate BRIEFING.md from template.

    Args:
        worker_dir: Worker's directory path
        ctx: Onboarding context
    """
    template_dir = Path(__file__).parent.parent / "config" / "templates"
    env = Environment(
        loader=FileSystemLoader(str(template_dir)),
        autoescape=select_autoescape()
    )

    template = env.get_template("briefing.md.jinja2")

    content = template.render(
        worker_id=ctx.worker_id,
        worker_name=ctx.worker_name,
        worker_role=ctx.worker_role,
        team_name=ctx.team_name,
        manager_id=ctx.manager_id,
        manager_name=ctx.manager_name,
        org_mission=ctx.org_mission,
        okrs=ctx.okrs,
        worker_storage=str(worker_dir),
        shared_storage=str(worker_dir.parent.parent / "shared"),
        is_ceo=ctx.is_ceo,
        is_manager=ctx.is_manager,
        timestamp=ctx.timestamp,
    )

    (worker_dir / "BRIEFING.md").write_text(content)


def _create_storage_guide(worker_dir: Path, ctx: OnboardingContext) -> None:
    """Create STORAGE.md guide in worker directory.

    Args:
        worker_dir: Worker's directory path
        ctx: Onboarding context (for any customization)
    """
    template_path = Path(__file__).parent.parent / "config" / "templates" / "storage-guide.md"

    if template_path.exists():
        content = template_path.read_text()
        # Replace placeholders
        content = content.replace("{your-id}", ctx.worker_id)
        content = content.replace("{your-team}", ctx.team_name)
        (worker_dir / "STORAGE.md").write_text(content)


def _link_architecture_docs(worker_dir: Path, org_path: Path) -> None:
    """Create symlinks to CLAUDE.md and AGENTS.md.

    Args:
        worker_dir: Worker's directory path
        org_path: Organization root path
    """
    # Find repo root (go up from cli/core/onboarding.py)
    repo_root = Path(__file__).parent.parent.parent

    # Symlink CLAUDE.md
    claude_md = repo_root / "CLAUDE.md"
    if claude_md.exists():
        link = worker_dir / "CLAUDE.md"
        if not link.exists():
            try:
                link.symlink_to(claude_md)
            except (OSError, NotImplementedError):
                # Symlinks might not work on some systems, copy instead
                link.write_text(claude_md.read_text())

    # Symlink AGENTS.md if it exists
    agents_md = repo_root / "backend" / "AGENTS.md"
    if agents_md.exists():
        link = worker_dir / "AGENTS.md"
        if not link.exists():
            try:
                link.symlink_to(agents_md)
            except (OSError, NotImplementedError):
                link.write_text(agents_md.read_text())


def get_worker_env_vars(
    ctx: OnboardingContext,
    org_path: Path,
) -> dict[str, str]:
    """Get environment variables for worker session.

    Args:
        ctx: Onboarding context
        org_path: Organization root path

    Returns:
        Dictionary of environment variable key-value pairs
    """
    worker_dir = org_path / "storage" / "workers" / ctx.worker_id

    return {
        "WORKER_ID": ctx.worker_id,
        "WORKER_NAME": ctx.worker_name,
        "WORKER_ROLE": ctx.worker_role,
        "TEAM_NAME": ctx.team_name,
        "MANAGER_ID": ctx.manager_id or "",
        "ORG_PATH": str(org_path),
        "WORKER_STORAGE": str(worker_dir),
        "SHARED_STORAGE": str(org_path / "storage" / "shared"),
        "ORG_DB": str(org_path / "live" / "quinn.db"),
        "BRIEFING_PATH": str(worker_dir / "BRIEFING.md"),
        "WORKER_BUDGET_ALLOCATED": str(ctx.budget_allocated),
        "WORKER_COST_TIER": str(ctx.cost_tier),
    }


def generate_welcome_message(ctx: OnboardingContext, worker_dir: Path) -> str:
    """Generate welcome message for session spawn.

    Args:
        ctx: Onboarding context
        worker_dir: Worker's directory path

    Returns:
        Formatted welcome message string
    """
    template_dir = Path(__file__).parent.parent / "config" / "templates"
    env = Environment(
        loader=FileSystemLoader(str(template_dir)),
        autoescape=select_autoescape()
    )

    template = env.get_template("welcome.txt.jinja2")

    # Shorten worker storage path for display
    worker_storage_short = f"~/orgs/.../workers/{ctx.worker_id}"

    return template.render(
        worker_id=ctx.worker_id,
        worker_name=ctx.worker_name,
        worker_role=ctx.worker_role,
        team_name=ctx.team_name,
        manager_name=ctx.manager_name,
        org_mission=ctx.org_mission,
        okrs=ctx.okrs,
        worker_storage_short=worker_storage_short,
    )
