"""Worker onboarding system.

Provides onboarding context and materials to workers on spawn.
Creates briefings, documentation, and welcome messages for new workers.
"""

import json
import logging
import sqlite3
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional

from jinja2 import Environment, FileSystemLoader, select_autoescape

from cli.core.db import Database, get_org_db_path
from cli.core.worker import Worker
from cli.core.queries import get_team, get_worker, get_worker_allocated_budget, get_okrs_by_owner
from cli.core.storage import StorageManager
from cli.core.constants import SHARED_DIR, STORAGE_DIR
from shared.exceptions import WorkerNotFound

_logger = logging.getLogger(__name__)


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
    first_actions: list[str]  # Actionable first steps for worker
    escalation_timeout_minutes: int  # How long before idle triggers escalation


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
    - Initialization marker

    Args:
        db: Database instance
        worker_id: Worker ID to onboard
        org_path: Path to organization root

    Returns:
        OnboardingContext with all worker info for env vars and welcome
    """
    # 1. Load worker from database
    worker = Worker.get(db, worker_id)

    # 2. Create worker directory using StorageManager (hierarchical structure)
    storage = StorageManager(org_path, db)
    worker_dir = storage.ensure_worker_storage(worker_id)

    # Create onboarding subdirectory
    onboarding_dir = worker_dir / ".onboarding"
    onboarding_dir.mkdir(exist_ok=True)

    # 3. Load onboarding context
    context = _load_onboarding_context(db, worker, org_path)

    # 4. Generate and write briefing
    _create_briefing(worker_dir, context)

    # 5. Create STORAGE.md guide
    _create_storage_guide(worker_dir, context)

    # 6. Create WELCOME.md file
    _create_welcome_file(worker_dir, context)

    # 7. Symlink architecture docs
    _link_architecture_docs(worker_dir, org_path)

    # 8. Record onboarding initialization marker
    marker_path = onboarding_dir / "initialized"
    if not marker_path.exists():
        marker_path.write_text(context.timestamp)

    return context


def load_onboarding_context(
    db: Database,
    worker_id: str,
    org_path: Path,
) -> OnboardingContext:
    """Load onboarding context without writing files."""
    worker = Worker.get(db, worker_id)
    return _load_onboarding_context(db, worker, org_path)


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
        except (sqlite3.Error, WorkerNotFound) as e:
            # Manager lookup failed - use defaults
            _logger.debug(f"Failed to load manager info: {e}")
            pass

    # Get team name (default to role if team lookup fails)
    team_name = worker.role
    try:
        team = get_team(db, worker.team_id)
        if team and team.name:
            team_name = team.name
    except sqlite3.Error as e:
        # Team lookup failed - use role as team name
        _logger.debug(f"Failed to load team info: {e}")
        pass

    # Get org mission from config or use default
    org_mission = _load_org_mission(org_path)

    # Get worker's OKRs from database
    okrs = _load_worker_okrs(db, worker.id)

    # Get budget info
    budget_allocated = 0.0
    try:
        budget_allocated = get_worker_allocated_budget(db, worker.id)
    except (sqlite3.Error, ValueError) as e:
        # Budget lookup failed - use default
        _logger.debug(f"Failed to load budget info: {e}")
        pass

    # Determine worker type
    is_ceo = worker.role.upper() == "CEO"
    is_manager = worker.manager_id is None and not is_ceo  # Has no manager but isn't CEO

    # Generate context-aware first actions (GAP 3 fix)
    first_actions = _generate_first_actions(
        worker_role=worker.role,
        worker_id=worker.id,
        is_ceo=is_ceo,
        is_manager=is_manager,
        has_okrs=len(okrs) > 0,
        manager_name=manager_name,
        manager_id=manager_id,
        team_name=team_name,
    )

    # Get escalation timeout based on role (GAP 4 setup)
    escalation_timeout = _get_escalation_timeout(worker.role, is_ceo, is_manager)

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
        first_actions=first_actions,
        escalation_timeout_minutes=escalation_timeout,
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
    try:
        okr_objects = get_okrs_by_owner(db, worker_id)
    except sqlite3.Error as e:
        # OKR query failed - return empty list
        _logger.debug(f"Failed to load OKRs: {e}")
        return []

    # Convert OKR dataclasses to dicts for template rendering
    okrs: list[dict] = []
    for okr in okr_objects:
        # key_results is already parsed as list[KeyResult] dataclasses
        kr_list = []
        if okr.key_results:
            for kr in okr.key_results:
                kr_list.append({
                    "metric": kr.metric,
                    "target": kr.target,
                    "current": kr.current,
                    "unit": kr.unit,
                })

        okrs.append(
            {
                "id": okr.id,
                "title": okr.title,
                "description": okr.description or "",
                "status": okr.status,
                "key_results": kr_list,
            }
        )
    return okrs


def _generate_first_actions(
    worker_role: str,
    worker_id: str,
    is_ceo: bool,
    is_manager: bool,
    has_okrs: bool,
    manager_name: Optional[str],
    manager_id: Optional[str] = None,
    team_name: str = "team",
) -> list[str]:
    """Generate context-aware first actions for worker.

    This fixes GAP 3: Workers need specific, actionable first steps
    rather than generic instructions.

    Args:
        worker_role: Worker's role
        worker_id: Worker ID
        is_ceo: Whether worker is CEO
        is_manager: Whether worker is a manager
        has_okrs: Whether worker has OKRs assigned
        manager_name: Manager's name if exists
        manager_id: Manager's ID if exists
        team_name: Team name for channel references

    Returns:
        List of specific action items to start immediately
    """
    actions = []

    if is_ceo:
        if has_okrs:
            actions = [
                "Introduce yourself to team: run `msgr send #general \"Hi! I'm the CEO, starting work on our OKRs now.\"`",
                "Review your OKRs: run `qn org okr list` to see objectives and progress",
                "Check assigned work: run `bd ready` to see tasks ready for you",
                "Review team status: check workers with `qn org status`",
                "Start on highest priority OKR: pick key result to advance today",
                "Document your plan: create bead with `bd create --title='Today's plan: ...' --type=task`",
                "Post regular updates: use `msgr send #general \"Progress update: ...\"` every 30-60 minutes",
            ]
        else:
            actions = [
                "Introduce yourself to team: run `msgr send #general \"Hi! I'm the CEO, starting work on setting up our org.\"`",
                "Create your first OKR: run `qn org okr create --title='Your objective' --owner=me`",
                "Define key results: add metrics with `qn org okr add-kr {okr-id} --metric='...' --target=N`",
                "Break down into tasks: create beads linked to OKR with `bd create --deps='serves:{okr-id}'`",
                "Start execution: run `bd ready` and claim first task",
                "Hire initial team: plan who you need with `qn org hire --help`",
                "Post regular updates: use `msgr send #general \"Progress update: ...\"` every 30-60 minutes",
            ]
    elif is_manager:
        if has_okrs:
            actions = [
                f"Introduce yourself: run `msgr send #{team_name} \"Hi team! I'm your manager, ready to support our goals.\"`",
                "Review your OKRs: run `qn org okr list` to see your objectives",
                "Break down OKRs into tasks: create tasks that serve each key result",
                "Check team capacity: run `qn org status` to see who's available",
                f"Sync with manager: message {manager_name} about your plan with `msgr send @{manager_id}` if needed" if manager_id else f"Sync with {manager_name} if needed",
                "Start on first task: run `bd ready` and begin work",
                f"Post progress updates: use `msgr send #{team_name} \"Update: ...\"` every 30-60 minutes",
            ]
        else:
            actions = [
                f"Check in with manager: run `msgr send @{manager_id} \"Ready to work, awaiting OKRs\"`" if manager_id else f"Check in with {manager_name}",
                f"Get OKRs from {manager_name}: check if objectives have been delegated",
                "Create team plan: outline what your team needs to deliver",
                "Document dependencies: note what you're blocked on in beads",
                "Request delegation: ask manager for hiring authority if you need to grow team",
            ]
    else:
        # Regular worker
        actions = [
            f"Introduce yourself: run `msgr send @{manager_id} \"Hi {manager_name}, I'm ready to work. What should I prioritize?\"`" if manager_id and manager_name else f"Introduce yourself to {manager_name}",
            "Check assigned work: run `bd ready` to see tasks assigned to you",
            "Review your OKRs: run `qn org okr list` to understand your goals",
            "Read architecture docs: run `cat CLAUDE.md` to understand coding standards",
            "Start first task: run `bd update {task-id} --status=in_progress` to claim work",
            f"Post when starting work: run `msgr send #{team_name} \"Starting: [task title]\"`",
            f"Post status updates: use `msgr send #{team_name} \"Update: ...\"` as you progress",
        ]

    return actions


def _get_escalation_timeout(worker_role: str, is_ceo: bool, is_manager: bool) -> int:
    """Get escalation timeout in minutes based on worker role.

    This supports GAP 4: Escalation monitoring needs role-specific timeouts.

    Args:
        worker_role: Worker's role
        is_ceo: Whether worker is CEO
        is_manager: Whether worker is a manager

    Returns:
        Timeout in minutes before idle triggers escalation
    """
    from cli.core.constants import (
        DEFAULT_ESCALATION_TIMEOUT_CEO,
        DEFAULT_ESCALATION_TIMEOUT_MANAGER,
        DEFAULT_ESCALATION_TIMEOUT_WORKER,
    )

    if is_ceo:
        return DEFAULT_ESCALATION_TIMEOUT_CEO
    elif is_manager:
        return DEFAULT_ESCALATION_TIMEOUT_MANAGER
    else:
        return DEFAULT_ESCALATION_TIMEOUT_WORKER


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
        shared_storage=str(worker_dir.parent.parent / SHARED_DIR),
        is_ceo=ctx.is_ceo,
        is_manager=ctx.is_manager,
        timestamp=ctx.timestamp,
        first_actions=ctx.first_actions,
        escalation_timeout_minutes=ctx.escalation_timeout_minutes,
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


def _create_welcome_file(worker_dir: Path, ctx: OnboardingContext) -> None:
    """Create WELCOME.md file in worker directory.

    Args:
        worker_dir: Worker's directory path
        ctx: Onboarding context
    """
    template_dir = Path(__file__).parent.parent / "config" / "templates"
    env = Environment(
        loader=FileSystemLoader(str(template_dir)),
        autoescape=select_autoescape()
    )

    template = env.get_template("welcome.md.jinja2")

    # Shorten worker storage path for display
    worker_storage_short = f"~/orgs/.../workers/{ctx.worker_id}"

    content = template.render(
        worker_id=ctx.worker_id,
        worker_name=ctx.worker_name,
        worker_role=ctx.worker_role,
        team_name=ctx.team_name,
        manager_name=ctx.manager_name,
        org_mission=ctx.org_mission,
        okrs=ctx.okrs,
        worker_storage_short=worker_storage_short,
        is_ceo=ctx.is_ceo,
        is_manager=ctx.is_manager,
    )

    (worker_dir / "WELCOME.md").write_text(content)


def _link_architecture_docs(worker_dir: Path, org_path: Path) -> None:
    """Create symlinks to CLAUDE.md and AGENTS.md.

    Args:
        worker_dir: Worker's directory path
        org_path: Organization root path
    """
    # Find repo root (go up from cli/core/onboarding.py)
    repo_root = Path(__file__).resolve().parent.parent.parent
    onboarding_configs = repo_root / "shared" / "onboarding" / "configs"

    # Symlink CLAUDE.md (deployment rules)
    claude_md = onboarding_configs / "CLAUDE.md"
    if claude_md.exists():
        link = worker_dir / "CLAUDE.md"
        if not link.exists():
            try:
                link.symlink_to(claude_md)
            except (OSError, NotImplementedError):
                # Symlinks might not work on some systems, copy instead
                link.write_text(claude_md.read_text())

    # Symlink AGENTS.md if it exists
    agents_md = onboarding_configs / "AGENTS.md"
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
    db: Database,
) -> dict[str, str]:
    """Get environment variables for worker session.

    Args:
        ctx: Onboarding context
        org_path: Organization root path
        db: Database instance for storage hierarchy lookup

    Returns:
        Dictionary of environment variable key-value pairs
    """
    # Use StorageManager to get hierarchical worker path
    storage = StorageManager(org_path, db)
    worker_dir = storage.get_worker_path(ctx.worker_id)

    # Determine session mode - CEOs and managers default to autonomous
    session_mode = "autonomous" if (ctx.is_ceo or ctx.is_manager) else "interactive"

    return {
        "WORKER_ID": ctx.worker_id,
        "QUINN_WORKER_ID": ctx.worker_id,
        "WORKER_NAME": ctx.worker_name,
        "WORKER_ROLE": ctx.worker_role,
        "TEAM_NAME": ctx.team_name,
        "MANAGER_ID": ctx.manager_id or "",
        "ORG_PATH": str(org_path),
        "QUINN_ORG_PATH": str(org_path),  # For qn-bd command
        "WORKER_STORAGE": str(worker_dir),
        "SHARED_STORAGE": str(org_path / STORAGE_DIR / SHARED_DIR),
        "ORG_DB": str(get_org_db_path(org_path)),
        "BRIEFING_PATH": str(worker_dir / "BRIEFING.md"),
        "WORKER_BUDGET_ALLOCATED": str(ctx.budget_allocated),
        "WORKER_COST_TIER": str(ctx.cost_tier),
        "QUINN_SESSION_MODE": session_mode,
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

    template = env.get_template("welcome.md.jinja2")

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
        is_ceo=ctx.is_ceo,
        is_manager=ctx.is_manager,
    )


def generate_returning_message(ctx: OnboardingContext) -> str:
    """Generate a brief welcome-back message for new sessions."""
    mode_reminder = ""
    if ctx.is_ceo or ctx.is_manager:
        mode_reminder = (
            "\nMode: AUTONOMOUS - Continue working based on OKRs.\n"
            "Make best-guess decisions, document in beads, only stop for critical blockers.\n"
        )

    return (
        "New workday started.\n\n"
        f"Worker: {ctx.worker_name} ({ctx.worker_role})\n"
        f"Team: {ctx.team_name}\n"
        f"{mode_reminder}\n"
        "Quick start:\n"
        "- Review your briefing: cat BRIEFING.md\n"
        "- Check tasks: bd ready\n"
        "- Store durable work: shared/\n"
    )
