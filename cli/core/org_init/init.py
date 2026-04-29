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
    install_bd_shim,
    write_ceo_briefing,
    write_initial_okrs,
    write_providers_config,
)
from .types import OrgInitConfig, OrgInitResult


def init_org(config: OrgInitConfig) -> OrgInitResult:
    """Initialize a new organization.

    Main entry point for org initialization, used by both the CLI
    (qn org init) and the board UI's new-org wizard. In host mode
    (config.host_mode=True), the org metadata is laid out under
    <config.path>/.quinnai/ and the project's existing .beads/ is
    reused; see types.OrgInitConfig.host_mode for the full contract.
    """
    from cli.core.db import get_org_db_path, init_database
    from cli.core.org import Org

    # In host mode, the user-facing path IS the project root; org
    # metadata lands one level down under .quinnai/. In greenfield mode
    # the org_path IS the metadata root.
    project_root = config.path if config.host_mode else None
    org_metadata_root = (config.path / ".quinnai") if config.host_mode else config.path

    db_path = get_org_db_path(org_metadata_root)

    try:
        # Already-initialized check
        if db_path.exists():
            return OrgInitResult(
                success=False,
                org_path=org_metadata_root,
                db_path=db_path,
                ceo_id="",
                ceo_name="",
                ceo_role="",
                error=(
                    f"Organization already initialized at '{org_metadata_root}'. "
                    "Run 'qn org status' to view or 'qn org start' to start it."
                ),
            )

        # 1. Initialize git repository (skip in host mode — project has its own .git/)
        if not config.host_mode:
            init_git_repo(org_metadata_root)

        # 2. Create folder structure
        create_folder_structure(org_metadata_root)

        # 3. Initialize beads (skip in host mode — project's .beads/ is authoritative)
        if not config.host_mode:
            init_beads(org_metadata_root, reuse_beads=config.reuse_beads)
        else:
            # Install the .quinnai/bin/bd PATH shim that enforces per-assignee
            # write isolation for workers (host-mode-init trust boundary).
            install_bd_shim(project_root)

        # 4. Write config files
        if config.providers:
            write_providers_config(org_metadata_root, config.providers)
        else:
            copy_default_configs(org_metadata_root)

        # 5. Write initial OKRs (config file form, picked up by create_initial_okrs)
        write_initial_okrs(org_metadata_root, config.objectives)

        # 6. Write CEO briefing if provided
        write_ceo_briefing(org_metadata_root, config.ceo_briefing)

        # 7. Initialize database
        db = init_database(db_path)

        try:
            # 8. Create CEO worker
            org = Org(db)
            ceo = org.init(
                config.ceo_name,
                config.ceo_role,
                skip_beads_init=config.host_mode,
            )

            # 8.1. Record project_root in org_state for is_host_mode() detection.
            if config.host_mode:
                with db.transaction() as cursor:
                    cursor.execute(
                        "UPDATE org_state SET project_root=? WHERE id='default'",
                        (str(project_root),),
                    )

            # 8.5. Create initial OKRs (GAP 1 fix)
            # skip_okrs=True suppresses both objective-seeded OKRs AND the
            # bootstrap fallback (quinn-ai-6odb).
            if config.skip_okrs:
                okr_ids: list[str] = []
            else:
                okr_ids = create_initial_okrs(org_metadata_root, db, ceo.id, config.objectives)

            # 8.6. Create initial CEO tasks linked to bootstrap OKR (GAP 2 fix)
            # No starter tasks make sense without an OKR to anchor them to.
            if okr_ids:
                create_initial_tasks(org_metadata_root, db, ceo.id, okr_ids)

            # 9. Create org-chart
            create_org_chart(org_metadata_root, ceo)

            # 10. Render org documentation from templates (skip root README
            #     in host mode to avoid clobbering the project's).
            if not config.host_mode:
                create_org_documentation(org_metadata_root, config.name)

            return OrgInitResult(
                success=True,
                org_path=org_metadata_root,
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
            org_path=org_metadata_root,
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
    *,
    host_mode: bool = False,
    skip_okrs: bool = False,
) -> bool:
    """Convenience wrapper around init_org with flat keyword arguments."""
    config = OrgInitConfig(
        path=org_path,
        name=org_name,
        ceo_name=ceo_name,
        ceo_role=ceo_role,
        host_mode=host_mode,
        skip_okrs=skip_okrs,
    )
    return init_org(config).success
