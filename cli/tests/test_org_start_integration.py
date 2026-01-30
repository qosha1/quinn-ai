"""Tests for integrated org start with session spawning (GAP 2 fix)."""

import tempfile
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock

import pytest

from core.org import Org
from core.db import init_database
from core.session import SessionConfig
from shared import SessionSpawnError, InvalidOrgTransition
from shared.enums import OrgStatus


@pytest.fixture
def temp_org_dir():
    """Create a temporary org directory."""
    with tempfile.TemporaryDirectory() as tmpdir:
        org_path = Path(tmpdir)
        (org_path / "live").mkdir(parents=True)
        (org_path / "config").mkdir(parents=True)
        (org_path / "storage" / "workers").mkdir(parents=True)
        (org_path / "storage" / "shared").mkdir(parents=True)
        (org_path / ".beads").mkdir(parents=True)
        yield org_path


@pytest.fixture
def test_db(temp_org_dir):
    """Create a test database."""
    db_path = temp_org_dir / "live" / "quinn.db"
    db = init_database(db_path)
    yield db
    db.close()


@pytest.fixture
def initialized_org(test_db, temp_org_dir):
    """Create an initialized org with CEO."""
    org = Org(test_db, temp_org_dir)
    ceo = org.init("TestCEO", "CEO")
    return org


def test_start_with_session_without_spawning(initialized_org):
    """Test start_with_session with spawn_ceo=False."""
    # Start without spawning CEO session
    old_status, new_status = initialized_org.start_with_session(spawn_ceo=False)
    
    assert old_status == OrgStatus.INITIALIZED.value
    assert new_status == OrgStatus.RUNNING.value
    assert initialized_org.status == OrgStatus.RUNNING.value


@patch('core.sessions.registry.get_default_registry')
@patch('core.onboarding.prepare_worker_onboarding')
@patch('core.onboarding.get_worker_env_vars')
def test_start_with_session_spawns_ceo(
    mock_env_vars,
    mock_prep_onboarding,
    mock_registry,
    initialized_org,
    temp_org_dir
):
    """Test that start_with_session spawns CEO by default."""
    # Setup mocks
    mock_env_vars.return_value = {}
    mock_prep_onboarding.return_value = Mock()
    mock_reg_instance = MagicMock()
    mock_registry.return_value = mock_reg_instance

    # Mock CEO spawn method
    initialized_org.ceo.spawn = Mock()
    initialized_org.ceo.set_registry = Mock()

    # Start with session spawning
    old_status, new_status = initialized_org.start_with_session(spawn_ceo=True)

    # Verify org transitioned
    assert old_status == OrgStatus.INITIALIZED.value
    assert new_status == OrgStatus.RUNNING.value

    # Verify CEO session was spawned
    initialized_org.ceo.set_registry.assert_called_once()
    initialized_org.ceo.spawn.assert_called_once()


@patch('core.sessions.registry.get_default_registry')
@patch('core.onboarding.prepare_worker_onboarding')
@patch('core.onboarding.get_worker_env_vars')
def test_start_with_session_rollback_on_spawn_failure(
    mock_env_vars,
    mock_prep_onboarding,
    mock_registry,
    initialized_org
):
    """Test rollback when session spawn fails."""
    # Setup mocks
    mock_env_vars.return_value = {}
    mock_prep_onboarding.return_value = Mock()
    mock_reg_instance = MagicMock()
    mock_registry.return_value = mock_reg_instance
    
    # Mock CEO spawn to fail
    initialized_org.ceo.spawn = Mock(side_effect=Exception("Spawn failed"))
    initialized_org.ceo.set_registry = Mock()
    
    # Verify initial status
    assert initialized_org.status == OrgStatus.INITIALIZED.value
    
    # Attempt to start with session spawning
    with pytest.raises(SessionSpawnError):
        initialized_org.start_with_session(spawn_ceo=True)
    
    # Verify rollback occurred
    assert initialized_org.status == OrgStatus.INITIALIZED.value


@patch('core.escalation_monitor.EscalationMonitor')
def test_start_with_session_starts_escalation_monitor(mock_monitor_class, initialized_org):
    """Test that escalation monitor is started."""
    mock_monitor_instance = Mock()
    mock_monitor_instance.is_running.return_value = False
    mock_monitor_class.return_value = mock_monitor_instance
    
    # Start org without spawning CEO (simpler test)
    initialized_org.start_with_session(spawn_ceo=False)
    
    # Verify escalation monitor was created and started
    mock_monitor_class.assert_called_once()
    mock_monitor_instance.start.assert_called_once()


@patch('core.escalation_monitor.EscalationMonitor')
def test_stop_stops_escalation_monitor(mock_monitor_class, initialized_org):
    """Test that stopping org stops escalation monitor."""
    mock_monitor_instance = Mock()
    mock_monitor_instance.is_running.return_value = True
    mock_monitor_class.return_value = mock_monitor_instance
    
    # Start org (which starts monitor)
    initialized_org.start_with_session(spawn_ceo=False)
    
    # Stop org
    initialized_org.stop()
    
    # Verify monitor was stopped
    mock_monitor_instance.stop.assert_called_once()
    assert initialized_org.status == OrgStatus.STOPPED.value


def test_start_with_session_with_custom_config(initialized_org):
    """Test start_with_session with custom SessionConfig."""
    # Create custom session config
    custom_config = SessionConfig(
        worker_id=initialized_org.ceo.id,
        provider="test_provider",
        command="test_command",
        args=["--test"],
        working_directory=Path("/tmp"),
        env_vars={"TEST": "value"},
    )
    
    # Mock spawn to avoid actual session creation
    initialized_org.ceo.spawn = Mock()
    initialized_org.ceo.set_registry = Mock()
    
    # Mock registry
    with patch('core.sessions.registry.get_default_registry') as mock_registry:
        mock_reg = MagicMock()
        mock_registry.return_value = mock_reg
        
        # Start with custom config
        old_status, new_status = initialized_org.start_with_session(
            session_config=custom_config,
            spawn_ceo=True
        )
        
        # Verify spawn was called with custom config
        initialized_org.ceo.spawn.assert_called_once_with(custom_config)


def test_org_path_property(initialized_org, temp_org_dir):
    """Test that org_path property works correctly."""
    assert initialized_org.org_path == temp_org_dir


def test_org_derives_path_from_db(test_db, temp_org_dir):
    """Test that org can derive path from database."""
    org = Org(test_db)  # No org_path provided
    
    # Should derive from db_path
    assert org.org_path == temp_org_dir


@patch('core.sessions.registry.get_default_registry')
@patch('core.onboarding.prepare_worker_onboarding')
@patch('core.onboarding.get_worker_env_vars')
def test_multiple_start_calls_idempotent(
    mock_env_vars,
    mock_prep_onboarding,
    mock_registry,
    initialized_org
):
    """Test that calling start_with_session when already running is handled."""
    # Setup mocks
    mock_env_vars.return_value = {}
    mock_prep_onboarding.return_value = Mock()
    mock_reg_instance = MagicMock()
    mock_registry.return_value = mock_reg_instance
    initialized_org.ceo.spawn = Mock()
    initialized_org.ceo.set_registry = Mock()
    
    # First start
    initialized_org.start_with_session(spawn_ceo=True)
    assert initialized_org.status == OrgStatus.RUNNING.value
    
    # Second start should raise (org already running)
    with pytest.raises(InvalidOrgTransition):
        initialized_org.start_with_session(spawn_ceo=True)
