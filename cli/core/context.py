"""
OrgContext - Dependency injection container for org-level services.

Provides centralized access to all org-level services and resources with:
- Lazy initialization of services (created on first access)
- Proper cleanup on context close
- Context manager pattern for automatic resource management

Per CLAUDE.md: "No Config Discovery" - all paths passed explicitly.

Usage:
    # Factory method creates context from org path
    with OrgContext.create(org_path) as ctx:
        # Access services (lazy initialized)
        balance = ctx.budget_service.get_balance(worker_id)
        bead_result = ctx.bead_service.get_bead(worker_id, bead_id)

        # Direct database access when needed
        with ctx.db.transaction() as cursor:
            cursor.execute("SELECT ...")

        # Access config
        default_provider = ctx.config.providers.default
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional, TYPE_CHECKING

from .db import Database, open_database, init_database, get_org_db_path
from .config import OrgConfig, load_org_config, get_org_config_path

if TYPE_CHECKING:
    from .budget import BudgetService
    from .bead_service import BeadService
    from .storage import StorageManager
    from .org import Org
    from shared.escalation.manager import EscalationManager


class OrgContextError(Exception):
    """Base exception for OrgContext errors."""

    pass


class OrgNotFoundError(OrgContextError):
    """Raised when org path doesn't exist or isn't initialized."""

    def __init__(self, org_path: Path):
        self.org_path = org_path
        super().__init__(f"Organization not found or not initialized: {org_path}")


class OrgContext:
    """Dependency injection container for org-level services.

    Holds database connection, config objects, and service instances.
    Services are lazily initialized on first access to avoid unnecessary
    resource allocation.

    Implements context manager pattern for automatic cleanup:
        with OrgContext.create(org_path) as ctx:
            # Use ctx.db, ctx.budget_service, etc.
        # Resources automatically cleaned up

    Attributes:
        org_path: Path to the org folder
        db: Database instance (always available)
        config: OrgConfig instance (always available)
    """

    def __init__(
        self,
        org_path: Path,
        db: Database,
        config: OrgConfig,
    ) -> None:
        """Initialize OrgContext.

        Use OrgContext.create() factory method instead of direct instantiation.

        Args:
            org_path: Path to the org folder
            db: Initialized database instance
            config: Loaded org configuration
        """
        self._org_path = org_path
        self._db = db
        self._config = config

        # Lazy-loaded service instances
        self._budget_service: Optional[BudgetService] = None
        self._bead_service: Optional[BeadService] = None
        self._storage_manager: Optional[StorageManager] = None
        self._org: Optional[Org] = None
        self._escalation_manager: Optional[EscalationManager] = None

        # Track whether context is closed
        self._closed = False

    # ===================
    # CORE PROPERTIES
    # ===================

    @property
    def org_path(self) -> Path:
        """Get the org folder path."""
        return self._org_path

    @property
    def db(self) -> Database:
        """Get the database instance."""
        self._check_closed()
        return self._db

    @property
    def config(self) -> OrgConfig:
        """Get the org configuration."""
        return self._config

    # ===================
    # LAZY-LOADED SERVICES
    # ===================

    @property
    def budget_service(self) -> BudgetService:
        """Get the budget service (lazy initialized)."""
        self._check_closed()
        if self._budget_service is None:
            from .budget import BudgetService

            self._budget_service = BudgetService(
                self._db,
                budget_config=self._config.budget,
            )
        return self._budget_service

    @property
    def bead_service(self) -> BeadService:
        """Get the bead service (lazy initialized)."""
        self._check_closed()
        if self._bead_service is None:
            from .bead_service import BeadService
            from .bd_wrapper import get_bundled_bd_path, get_org_beads_dir

            bd_path = get_bundled_bd_path()
            beads_dir = get_org_beads_dir(self._org_path)
            beads_db = beads_dir / "beads.db"

            self._bead_service = BeadService(
                db=self._db,
                bd_path=str(bd_path),
                beads_db=str(beads_db) if beads_db.exists() else None,
            )
        return self._bead_service

    @property
    def storage(self) -> StorageManager:
        """Get the storage manager (lazy initialized)."""
        self._check_closed()
        if self._storage_manager is None:
            from .storage import StorageManager

            self._storage_manager = StorageManager(self._org_path, self._db)
        return self._storage_manager

    @property
    def org(self) -> Org:
        """Get the Org instance (lazy initialized)."""
        self._check_closed()
        if self._org is None:
            from .org import Org

            self._org = Org.load(self._db)
        return self._org

    @property
    def escalation_manager(self) -> EscalationManager:
        """Get the escalation manager (lazy initialized).

        Builds OrgTopology from workers in the database and initializes
        the EscalationManager with config from escalation.yaml if present.
        """
        self._check_closed()
        if self._escalation_manager is None:
            from shared.escalation.manager import EscalationManager, EscalationConfig
            from shared.escalation.hierarchical import OrgTopology, WorkerNode
            from .queries import get_all_workers_for_topology, is_worker_manager

            # Build topology from database workers
            topology = OrgTopology()
            rows = get_all_workers_for_topology(self._db)
            for row in rows:
                # Determine if worker is a manager (has direct reports)
                has_reports = is_worker_manager(self._db, row["id"])
                node = WorkerNode(
                    id=row["id"],
                    name=row["name"],
                    boss_id=row["manager_id"],
                    is_manager=has_reports,
                )
                topology.add_node(node)

            # Load escalation config if it exists
            escalation_config_path = self._config.config_path / "escalation.yaml"
            if escalation_config_path.exists():
                config = EscalationConfig.load_from_yaml(escalation_config_path)
            else:
                config = EscalationConfig()

            self._escalation_manager = EscalationManager(topology, config)

        return self._escalation_manager

    # ===================
    # ORG METADATA
    # ===================

    @property
    def org_name(self) -> str:
        """Get the org folder name (used as org identifier)."""
        return self._org_path.name

    @property
    def db_path(self) -> Path:
        """Get the database file path."""
        return self._db.db_path

    @property
    def config_path(self) -> Path:
        """Get the config directory path."""
        return self._config.config_path

    # ===================
    # LIFECYCLE
    # ===================

    def _check_closed(self) -> None:
        """Raise if context is closed."""
        if self._closed:
            raise OrgContextError("OrgContext is closed")

    def close(self) -> None:
        """Close the context and release all resources.

        Closes the database connection and clears service references.
        After calling close(), the context cannot be used.
        """
        if self._closed:
            return

        # Stop escalation manager if it was started
        if self._escalation_manager is not None:
            self._escalation_manager.stop()

        # Close database connection
        self._db.close()

        # Clear service references
        self._budget_service = None
        self._bead_service = None
        self._storage_manager = None
        self._org = None
        self._escalation_manager = None

        self._closed = True

    def __enter__(self) -> OrgContext:
        """Context manager entry."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        """Context manager exit - ensures cleanup."""
        self.close()

    # ===================
    # FACTORY METHODS
    # ===================

    @classmethod
    def create(cls, org_path: Path) -> OrgContext:
        """Create OrgContext from org path.

        Factory method that loads database and config from the org folder.
        The org must already be initialized (have quinn.db).

        Args:
            org_path: Path to the org folder

        Returns:
            Initialized OrgContext

        Raises:
            OrgNotFoundError: If org path doesn't exist or isn't initialized
            FileNotFoundError: If required config files are missing
        """
        org_path = Path(org_path).resolve()

        if not org_path.exists():
            raise OrgNotFoundError(org_path)

        # Open database
        db_path = get_org_db_path(org_path)
        if not db_path.exists():
            raise OrgNotFoundError(org_path)

        db = open_database(db_path)

        # Load config
        config_path = get_org_config_path(org_path)
        config = load_org_config(config_path)

        return cls(org_path=org_path, db=db, config=config)

    @classmethod
    def create_new(
        cls,
        org_path: Path,
        *,
        create_config: bool = False,
    ) -> OrgContext:
        """Create OrgContext for a new org (initializes database).

        Use this when creating a new org that doesn't have a database yet.
        For existing orgs, use create() instead.

        Args:
            org_path: Path to the org folder
            create_config: If True, create default config files if missing

        Returns:
            Initialized OrgContext with fresh database

        Raises:
            FileNotFoundError: If config files missing and create_config=False
        """
        org_path = Path(org_path).resolve()
        org_path.mkdir(parents=True, exist_ok=True)

        # Initialize database
        db_path = get_org_db_path(org_path)
        db = init_database(db_path)

        # Load or create config
        config_path = get_org_config_path(org_path)

        if create_config and not config_path.exists():
            # Create minimal config directory structure
            config_path.mkdir(parents=True, exist_ok=True)
            _create_default_providers_config(config_path)

        config = load_org_config(config_path)

        return cls(org_path=org_path, db=db, config=config)


def _create_default_providers_config(config_path: Path) -> None:
    """Create a minimal default providers.yaml file.

    Args:
        config_path: Path to config directory
    """
    providers_yaml = config_path / "providers.yaml"
    if providers_yaml.exists():
        return

    default_config = """\
# QuinnAI Provider Configuration
# API keys should use environment variable references: ${VAR_NAME}

default: anthropic

providers:
  anthropic:
    enabled: true
    api_key: ${ANTHROPIC_API_KEY}

thresholds:
  coding: 80
  reasoning: 60
  research: 80
"""
    providers_yaml.write_text(default_config)
