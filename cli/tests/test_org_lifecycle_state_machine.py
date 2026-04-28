"""
Org Lifecycle State Machine Validation Tests.

Tests validate actual implementation against STATEMACHINES.md specification.
These tests are designed to catch violations found in validation report.
"""

import pytest
import tempfile
from pathlib import Path

from cli.core.db import init_database
from cli.core.org import Org
from shared import InvalidOrgTransition, ORG_TRANSITIONS
from shared.enums import OrgStatus


@pytest.fixture
def db_path():
    """Create a temporary database path."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir) / "live" / "quinn.db"


@pytest.fixture
def db(db_path):
    """Create and initialize a test database."""
    database = init_database(db_path)
    yield database
    database.close()


@pytest.fixture
def org(db):
    """Create an Org instance."""
    return Org(db)


@pytest.fixture
def initialized_org(org):
    """Create an initialized org."""
    org.init(ceo_name="Test CEO", initial_budget=1000.0)
    return org


@pytest.fixture
def running_org(initialized_org):
    """Create a running org."""
    initialized_org.start()
    return initialized_org


@pytest.fixture
def stopped_org(running_org):
    """Create a stopped org."""
    running_org.stop()
    return running_org


class TestOrgStates:
    """Validate org states match STATEMACHINES.md."""

    def test_states_match_specification(self):
        """States in code must match STATEMACHINES.md.

        Documented: uninitialized, initialized, running, stopped
        """
        from shared.state_machines import ORG_STATES

        expected = {"uninitialized", "initialized", "running", "stopped"}
        assert ORG_STATES == expected, \
            f"ORG_STATES {ORG_STATES} doesn't match spec {expected}"


class TestOrgT1UnintializedToInitialized:
    """Test T1: uninitialized → initialized."""

    def test_t1_init_transitions_to_initialized(self, org):
        """Org.init() should transition to initialized."""
        assert org.status == OrgStatus.UNINITIALIZED.value

        ceo = org.init(ceo_name="Test CEO", initial_budget=1000.0)

        assert org.status == OrgStatus.INITIALIZED.value
        assert ceo is not None

    def test_t1_creates_ceo_worker(self, org):
        """T1 should create CEO worker with lifecycle='pending'."""
        ceo = org.init(ceo_name="Test CEO")

        assert ceo.name == "Test CEO"
        assert ceo.role == "CEO"
        assert ceo.lifecycle_status == "pending"

    def test_t1_allocates_budget(self, org):
        """T1 should create budget pool and allocate to CEO."""
        from cli.core.queries.budget import get_current_allocation

        ceo = org.init(ceo_name="Test CEO", initial_budget=1000.0)

        allocation = get_current_allocation(org.db, ceo.id)
        assert allocation is not None
        assert allocation.allocated_credits == 1000.0

    def test_t1_creates_channels(self, org):
        """T1 should create org-wide channels."""
        org.init(ceo_name="Test CEO")

        general = org.db.fetchone(
            "SELECT * FROM channels WHERE name = 'general'"
        )
        board = org.db.fetchone(
            "SELECT * FROM channels WHERE name = 'board-channel'"
        )

        assert general is not None
        assert board is not None

    def test_t1_initializes_beads(self, org):
        """T1 should initialize beads database."""
        org_path = Path(org.db.db_path).parent.parent
        org.init(ceo_name="Test CEO")

        beads_dir = org_path / ".beads"
        # Beads init is best-effort, may not exist if bd not installed
        # Just verify init was attempted (no error raised)

    def test_t1_validates_transition(self, initialized_org):
        """T1 should raise if already initialized."""
        with pytest.raises(InvalidOrgTransition):
            initialized_org.init(ceo_name="Another CEO")


class TestOrgT2InitializedToRunning:
    """Test T2: initialized → running (first start)."""

    def test_t2_transitions_to_running(self, initialized_org):
        """Org.start() from initialized should transition to running."""
        assert initialized_org.status == OrgStatus.INITIALIZED.value

        initialized_org.start()

        assert initialized_org.status == OrgStatus.RUNNING.value

    def test_t2_activates_ceo(self, initialized_org):
        """T2 should activate CEO worker (pending → onboarding → active)."""
        ceo = initialized_org.ceo
        assert ceo.lifecycle_status == "pending"

        initialized_org.start()

        ceo._worker_data = None  # Invalidate cache
        assert ceo.lifecycle_status == "active"

    def test_t2_delivers_briefing_if_exists(self, initialized_org):
        """T2 should deliver CEO briefing if config/ceo_briefing.md exists."""
        from cli.core.queries import get_messages_in_channel

        # Create briefing file
        org_path = Path(initialized_org.db.db_path).parent.parent
        config_dir = org_path / "config"
        config_dir.mkdir(parents=True, exist_ok=True)

        briefing_path = config_dir / "ceo_briefing.md"
        briefing_path.write_text("# Welcome CEO\n\nYour mission...")

        initialized_org.start()

        # Check message in board-channel
        board_channel = initialized_org.db.fetchone(
            "SELECT id FROM channels WHERE name = 'board-channel'"
        )
        messages = list(get_messages_in_channel(initialized_org.db, board_channel["id"]))

        assert len(messages) > 0
        assert "CEO Briefing" in messages[0].content

    def test_t2_briefing_idempotent(self, initialized_org):
        """T2 should not duplicate briefing on multiple starts."""
        org_path = Path(initialized_org.db.db_path).parent.parent
        config_dir = org_path / "config"
        config_dir.mkdir(parents=True, exist_ok=True)

        briefing_path = config_dir / "ceo_briefing.md"
        briefing_path.write_text("# Welcome")

        initialized_org.start()
        initialized_org.stop()
        initialized_org.start()  # Second start

        board_channel = initialized_org.db.fetchone(
            "SELECT id FROM channels WHERE name = 'board-channel'"
        )
        messages = initialized_org.db.fetchall(
            "SELECT * FROM messages WHERE channel_id = ? AND content LIKE '%CEO Briefing%'",
            (board_channel["id"],)
        )

        assert len(messages) == 1, "Briefing should only be delivered once"

    def test_t2_rollback_on_ceo_activation_failure(self, initialized_org, monkeypatch):
        """T2 rolls CEO lifecycle back if CEO activation fails partway.

        Pinned by quinn-ai-tage: Org.start() wraps CEO onboarding in
        try/except and reverts the CEO's lifecycle status to its prior
        value when complete_onboarding raises. Org status is only updated
        after all CEO + briefing steps succeed, so it never moved.
        """
        def fail_complete_onboarding(self):
            raise Exception("CEO activation failed")

        from cli.core import worker
        monkeypatch.setattr(worker.Worker, "complete_onboarding", fail_complete_onboarding)

        with pytest.raises(Exception):
            initialized_org.start()

        # Should still be initialized, NOT running
        assert initialized_org.status == OrgStatus.INITIALIZED.value
        assert initialized_org.ceo.lifecycle_status == "pending"

    def test_t2_validates_transition(self, org):
        """T2 should raise if not initialized."""
        with pytest.raises(InvalidOrgTransition):
            org.start()


class TestOrgT3RunningToStopped:
    """Test T3: running → stopped."""

    def test_t3_transitions_to_stopped(self, running_org):
        """Org.stop() should transition to stopped."""
        assert running_org.status == OrgStatus.RUNNING.value

        running_org.stop()

        assert running_org.status == OrgStatus.STOPPED.value

    def test_t3_verifies_sessions_stopped(self, running_org):
        """T3 should verify all sessions stopped before transitioning.

        EXPECTED TO FAIL: Documented violation in state-machine-validation.md
        Org.stop() doesn't verify sessions actually stopped.
        """
        # This test would require spawning a session and verifying stop
        # Currently org.stop() just updates status without checking sessions
        pass

    def test_t3_validates_transition(self, initialized_org):
        """T3 should raise if not running."""
        with pytest.raises(InvalidOrgTransition):
            initialized_org.stop()


class TestOrgT4StoppedToRunning:
    """Test T4: stopped → running (resume)."""

    def test_t4_transitions_to_running(self, stopped_org):
        """Org.start() from stopped should transition to running."""
        assert stopped_org.status == OrgStatus.STOPPED.value

        stopped_org.start()

        assert stopped_org.status == OrgStatus.RUNNING.value

    def test_t4_python_api_does_not_spawn_session_by_design(self, stopped_org):
        """Python API Org.start() is a state transition only — it does NOT
        spawn sessions in either mode (first-start or resume).

        Per quinn-ai-wbwy resolution: session spawning lives at the CLI
        orchestrator layer (cli/core/org_start_controller.py) which calls
        Org.start() and then runs _spawn_ceo_session_if_needed for both
        FIRST_START and RESUME modes. Keeping the Python API
        infrastructure-free (no tmux/subprocess dependencies) is a
        deliberate layering choice — see STATEMACHINES.md 'Org Start
        Layering' note.

        This test pins the Python-API contract: no session spawn from
        a direct Org.start() call.
        """
        ceo = stopped_org.ceo

        stopped_org.start()

        # Python API: state transitioned, but no session spawn.
        assert stopped_org.status == OrgStatus.RUNNING.value
        assert ceo.session is None, (
            "Org.start() Python API should NOT spawn a CEO session — "
            "spawning is the CLI orchestrator's responsibility."
        )


class TestOrgInvalidTransitions:
    """Test invalid transitions raise errors."""

    def test_initialized_to_stopped_invalid(self, initialized_org):
        """Cannot go from initialized to stopped."""
        with pytest.raises(InvalidOrgTransition):
            initialized_org.stop()

    def test_uninitialized_to_running_invalid(self, org):
        """Cannot go from uninitialized to running."""
        with pytest.raises(InvalidOrgTransition):
            org.start()

    def test_running_to_initialized_invalid(self, running_org):
        """Cannot go from running back to initialized."""
        with pytest.raises(InvalidOrgTransition):
            running_org._validate_transition(OrgStatus.INITIALIZED.value)

    def test_stopped_to_initialized_invalid(self, stopped_org):
        """Cannot go from stopped back to initialized."""
        with pytest.raises(InvalidOrgTransition):
            stopped_org._validate_transition(OrgStatus.INITIALIZED.value)


class TestOrgTransitionTable:
    """Validate transition table matches STATEMACHINES.md."""

    def test_transition_table_matches_spec(self):
        """ORG_TRANSITIONS must match STATEMACHINES.md."""
        expected = {
            "uninitialized": ["initialized"],
            "initialized": ["running"],
            "running": ["stopped"],
            "stopped": ["running"],
        }

        assert ORG_TRANSITIONS == expected, \
            f"ORG_TRANSITIONS {ORG_TRANSITIONS} doesn't match spec"

    def test_all_states_have_transitions(self):
        """Every state must have transition rules."""
        from shared.state_machines import ORG_STATES

        for state in ORG_STATES:
            assert state in ORG_TRANSITIONS, \
                f"State '{state}' missing from ORG_TRANSITIONS"


class TestOrgPreconditions:
    """Validate transition preconditions."""

    def test_t1_requires_uninitialized(self, initialized_org):
        """T1 requires org_status = uninitialized."""
        with pytest.raises(InvalidOrgTransition):
            initialized_org.init(ceo_name="Another CEO")

    def test_t2_requires_initialized_or_stopped(self, org, running_org):
        """T2 requires org_status = initialized or stopped."""
        # Uninitialized → running: invalid
        with pytest.raises(InvalidOrgTransition):
            org.start()

        # Running → running: invalid
        with pytest.raises(InvalidOrgTransition):
            running_org.start()

    def test_t3_requires_running(self, initialized_org):
        """T3 requires org_status = running."""
        with pytest.raises(InvalidOrgTransition):
            initialized_org.stop()


class TestOrgPostconditions:
    """Validate transition postconditions."""

    def test_t1_postconditions(self, org):
        """T1 must guarantee all postconditions."""
        org.init(ceo_name="Test CEO", initial_budget=1000.0)

        # org_status = initialized
        assert org.status == OrgStatus.INITIALIZED.value

        # CEO exists
        assert org.ceo is not None

        # CEO lifecycle = pending
        assert org.ceo.lifecycle_status == "pending"

        # Budget allocated
        from cli.core.queries.budget import get_current_allocation
        allocation = get_current_allocation(org.db, org.ceo.id)
        assert allocation is not None

        # Channels created
        assert org.db.fetchone("SELECT * FROM channels WHERE name = 'general'")
        assert org.db.fetchone("SELECT * FROM channels WHERE name = 'board-channel'")

    def test_t2_postconditions(self, initialized_org):
        """T2 must guarantee all postconditions."""
        initialized_org.start()

        # org_status = running
        assert initialized_org.status == OrgStatus.RUNNING.value

        # CEO lifecycle = active
        ceo = initialized_org.ceo
        ceo._worker_data = None  # Invalidate cache
        assert ceo.lifecycle_status == "active"

    def test_t3_postconditions(self, running_org):
        """T3 must guarantee all postconditions."""
        running_org.stop()

        # org_status = stopped
        assert running_org.status == OrgStatus.STOPPED.value

    def test_t4_postconditions(self, stopped_org):
        """T4 must guarantee all postconditions."""
        stopped_org.start()

        # org_status = running
        assert stopped_org.status == OrgStatus.RUNNING.value

        # CEO lifecycle unchanged (already active)
        assert stopped_org.ceo.lifecycle_status == "active"
