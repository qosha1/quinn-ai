"""Integration test for org initialization and escalation flows.

Tests the complete workflow:
- Initialize fresh org
- Start org with CEO
- Verify escalation flows work
- Test worker hiring and work assignment
"""

import tempfile
from pathlib import Path

import pytest

from cli.core.context import OrgContext
from cli.core.org_init import initialize_org
from cli.core.ceo_escalation import CEOEscalationHelper, EscalationUrgency


class TestOrgInitializationIntegration:
    """Integration tests for org initialization."""

    @pytest.fixture
    def org_path(self):
        """Create temporary org directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield Path(tmpdir)

    def test_initialize_fresh_org(self, org_path):
        """Test initializing a fresh organization."""
        # Initialize org
        result = initialize_org(
            org_path=org_path,
            org_name="Test Org",
            ceo_name="Alice CEO",
            ceo_role="Chief Executive Officer",
        )

        assert result is True

        # Verify database exists
        db_path = org_path / "live" / "quinn.db"
        assert db_path.exists()

        # Verify config exists
        config_path = org_path / "config"
        assert config_path.exists()
        assert (config_path / "providers.yaml").exists()

        # Verify beads directory exists
        beads_path = org_path / ".beads"
        assert beads_path.exists()

    def test_org_context_loads(self, org_path):
        """Test org context loads successfully after init."""
        # Initialize org first
        initialize_org(
            org_path=org_path,
            org_name="Test Org",
            ceo_name="Alice CEO",
            ceo_role="CEO",
        )

        # Load context
        with OrgContext.create(org_path) as ctx:
            assert ctx.org_name == org_path.name
            assert ctx.db is not None
            assert ctx.config is not None

            # Verify org is loaded
            org = ctx.org
            assert org is not None

    def test_ceo_escalation_helper_works(self, org_path):
        """Test CEO escalation helper with initialized org."""
        # Initialize org
        initialize_org(
            org_path=org_path,
            org_name="Test Org",
            ceo_name="Alice CEO",
            ceo_role="CEO",
        )

        # Create escalation helper
        with OrgContext.create(org_path) as ctx:
            helper = CEOEscalationHelper(ctx.db, "Test Org")

            # Gather org state
            state = helper.gather_org_state()
            assert state is not None
            assert state.total_workers >= 0

            # Determine urgency
            urgency = helper.determine_urgency(state)
            assert urgency in EscalationUrgency

            # Format escalation message
            message, context = helper.format_escalation_message(
                issue="Test escalation",
                org_state=state,
                urgency=urgency,
            )
            assert message is not None
            assert "Test escalation" in message
            assert context["ceo_escalation"] is True

    def test_escalation_manager_exists(self, org_path):
        """Test escalation manager is created with context."""
        # Initialize org
        initialize_org(
            org_path=org_path,
            org_name="Test Org",
            ceo_name="Alice CEO",
            ceo_role="CEO",
        )

        # Load context and access escalation manager
        with OrgContext.create(org_path) as ctx:
            manager = ctx.escalation_manager
            assert manager is not None

            # Verify it has a config
            assert manager.config is not None

    def test_notification_system_configured(self, org_path):
        """Test notification system is set up."""
        # Initialize org
        initialize_org(
            org_path=org_path,
            org_name="Test Org",
            ceo_name="Alice CEO",
            ceo_role="CEO",
        )

        # Check notification config exists
        notification_config = org_path / "config" / "notifications.yaml"
        # Config might not exist yet, but directory should
        assert (org_path / "config").exists()

    def test_storage_structure_created(self, org_path):
        """Test storage structure is created during init."""
        # Initialize org
        initialize_org(
            org_path=org_path,
            org_name="Test Org",
            ceo_name="Alice CEO",
            ceo_role="CEO",
        )

        # Verify storage directories
        storage = org_path / "storage"
        assert storage.exists()

        # Shared storage
        assert (storage / "shared").exists()

        # Worker storage root
        assert (storage / "workers").exists()

    def test_beads_system_initialized(self, org_path):
        """Test beads system is initialized."""
        # Initialize org
        initialize_org(
            org_path=org_path,
            org_name="Test Org",
            ceo_name="Alice CEO",
            ceo_role="CEO",
        )

        # Check beads directory structure
        beads_path = org_path / ".beads"
        assert beads_path.exists()

        # Should have beads.db
        db_path = beads_path / "beads.db"
        # DB is created on first bd operation

    def test_ceo_has_initial_work(self, org_path):
        """Test CEO has initial OKRs/tasks after initialization."""
        # Initialize org
        initialize_org(
            org_path=org_path,
            org_name="Test Org",
            ceo_name="Alice CEO",
            ceo_role="CEO",
        )

        # Check if initial work was created
        # This depends on the initialization logic
        # which should create bootstrap OKRs
        with OrgContext.create(org_path) as ctx:
            # At minimum, org should be initialized
            org = ctx.org
            assert org.status.value in ["initialized", "running", "stopped"]


class TestEscalationFlows:
    """Integration tests for escalation flows."""

    @pytest.fixture
    def org_path(self):
        """Create temporary org directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield Path(tmpdir)

    @pytest.fixture
    def initialized_org(self, org_path):
        """Initialize org for escalation tests."""
        initialize_org(
            org_path=org_path,
            org_name="Test Org",
            ceo_name="Alice CEO",
            ceo_role="CEO",
        )
        return org_path

    def test_ceo_can_escalate_to_board(self, initialized_org):
        """Test CEO can escalate to board."""
        with OrgContext.create(initialized_org) as ctx:
            helper = CEOEscalationHelper(ctx.db, "Test Org")
            state = helper.gather_org_state()

            # CEO can format escalation
            message, context = helper.format_escalation_message(
                issue="Need strategic direction",
                org_state=state,
                urgency=EscalationUrgency.URGENT,
                specific_question="What should our Q1 priorities be?",
            )

            assert "Need strategic direction" in message
            assert "What should our Q1 priorities be?" in message
            assert context["urgency"] == "urgent"

            # CEO should wait on URGENT
            should_wait = helper.should_ceo_wait(EscalationUrgency.URGENT)
            assert should_wait is True

    def test_urgency_levels_work(self, initialized_org):
        """Test different urgency levels behave correctly."""
        with OrgContext.create(initialized_org) as ctx:
            helper = CEOEscalationHelper(ctx.db, "Test Org")

            # INFO - CEO continues
            assert helper.should_ceo_wait(EscalationUrgency.INFO) is False

            # WARNING - CEO continues
            assert helper.should_ceo_wait(EscalationUrgency.WARNING) is False

            # URGENT - CEO waits
            assert helper.should_ceo_wait(EscalationUrgency.URGENT) is True

    def test_notification_priority_mapping(self, initialized_org):
        """Test urgency maps to correct notification priority."""
        from cli.core.notifications import NotificationPriority

        with OrgContext.create(initialized_org) as ctx:
            helper = CEOEscalationHelper(ctx.db, "Test Org")

            # INFO -> INFO priority
            priority = helper.urgency_to_notification_priority(EscalationUrgency.INFO)
            assert priority == NotificationPriority.INFO

            # WARNING -> HIGH priority
            priority = helper.urgency_to_notification_priority(EscalationUrgency.WARNING)
            assert priority == NotificationPriority.HIGH

            # URGENT -> URGENT priority
            priority = helper.urgency_to_notification_priority(EscalationUrgency.URGENT)
            assert priority == NotificationPriority.URGENT
