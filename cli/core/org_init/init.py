"""Top-level orchestrators: init_org() + initialize_org() shim."""

from pathlib import Path

from .bootstrap import create_initial_okrs, create_initial_tasks
from .scaffolding import (
    copy_default_configs,
    create_folder_structure,
    create_org_chart,
    create_org_documentation,
    init_beads,
    init_git_repo,
    write_ceo_briefing,
    write_initial_okrs,
    write_providers_config,
)
from .types import OrgInitConfig, OrgInitResult


def init_org(config: OrgInitConfig) -> OrgInitResult:
    """Initialize a new organization.

    Main entry point for org initialization, used by both the CLI
    (qn org init) and the board UI's new-org wizard.
    """
    from cli.core.db import get_org_db_path, init_database
    from cli.core.org import Org

    org_path = config.path
    db_path = get_org_db_path(org_path)

    try:
        # Already-initialized check
        if db_path.exists():
            return OrgInitResult(
                success=False,
                org_path=org_path,
                db_path=db_path,
                ceo_id="",
                ceo_name="",
                ceo_role="",
                error=(
                    f"Organization already initialized at '{org_path}'. "
                    "Run 'qn org status' to view or 'qn org start' to start it."
                ),
            )

        # 1. Initialize git repository
        init_git_repo(org_path)

        # 2. Create folder structure
        create_folder_structure(org_path)

        # 3. Initialize beads
        init_beads(org_path, reuse_beads=config.reuse_beads)

        # 4. Write config files
        if config.providers:
            write_providers_config(org_path, config.providers)
        else:
            copy_default_configs(org_path)

        # 5. Write initial OKRs (config file form, picked up by create_initial_okrs)
        write_initial_okrs(org_path, config.objectives)

        # 6. Write CEO briefing if provided
        write_ceo_briefing(org_path, config.ceo_briefing)

        # 7. Initialize database
        db = init_database(db_path)

        try:
            # 8. Create CEO worker
            org = Org(db)
            ceo = org.init(config.ceo_name, config.ceo_role)

            # 8.5. Create initial OKRs (GAP 1 fix)
            # skip_okrs=True suppresses both objective-seeded OKRs AND the
            # bootstrap fallback (quinn-ai-6odb).
            if config.skip_okrs:
                okr_ids: list[str] = []
            else:
                okr_ids = create_initial_okrs(org_path, db, ceo.id, config.objectives)

            # 8.6. Create initial CEO tasks linked to bootstrap OKR (GAP 2 fix)
            # No starter tasks make sense without an OKR to anchor them to.
            if okr_ids:
                create_initial_tasks(org_path, db, ceo.id, okr_ids)

            # 9. Create org-chart
            create_org_chart(org_path, ceo)

            # 10. Render org documentation from templates
            create_org_documentation(org_path, config.name)

            return OrgInitResult(
                success=True,
                org_path=org_path,
                db_path=db_path,
                ceo_id=ceo.id,
                ceo_name=ceo.name,
                ceo_role=ceo.role,
            )

        finally:
            db.close()

    except Exception as e:
        return OrgInitResult(
            success=False,
            org_path=org_path,
            db_path=db_path,
            ceo_id="",
            ceo_name="",
            ceo_role="",
            error=str(e),
        )


def initialize_org(
    org_path: Path,
    org_name: str,
    ceo_name: str,
    ceo_role: str,
) -> bool:
    """Convenience wrapper around init_org with flat keyword arguments."""
    config = OrgInitConfig(
        path=org_path,
        name=org_name,
        ceo_name=ceo_name,
        ceo_role=ceo_role,
    )
    return init_org(config).success
