"""qn-CLI subprocess wrappers that return discovery-style result tuples.

Distinct from commanders/lifecycle.py: these are module-level functions
(no OrgContext) used by the no-org view's "Start" button and by tests
that want a result-shaped value rather than a bool. Both this module
and commanders/lifecycle.py delegate to QnCliClient for the actual
subprocess invocation.
"""

from pathlib import Path

from ..logging_config import get_board_logger
from .discovery_types import StartResult, StopResult
from .qn_cli_client import get_default_qn_cli

logger = get_board_logger(__name__)


def check_cli_available() -> tuple[bool, str]:
    """Check if the qn CLI is available. Thin wrapper over QnCliClient."""
    return get_default_qn_cli().available()


def start_org(
    org_path: Path,
    spawn_ceo: bool = True,
    provider: str = "claude_code",
    skip_config_validation: bool = False,
    *,
    validate_path: bool = True,
) -> StartResult:
    """Start an org via `qn org start`. Returns a StartResult.

    Args:
        validate_path: When True (default), pre-validates org_path looks like
            an org folder before invoking qn. Tests pass False to skip.
    """
    if validate_path:
        from .org_discovery import validate_org_path

        is_valid, validation_error = validate_org_path(org_path)
        if not is_valid:
            return StartResult(success=False, message=validation_error, returncode=-1)

    cli_available, cli_error = check_cli_available()
    if not cli_available:
        return StartResult(success=False, message=cli_error, returncode=-1)

    result = get_default_qn_cli().org_start(
        org_path,
        spawn_ceo=spawn_ceo,
        provider=provider,
        skip_config_validation=skip_config_validation,
    )
    if result.success:
        return StartResult(
            success=True,
            message=result.output or "Organization started successfully",
            returncode=0,
        )
    return StartResult(
        success=False,
        message=result.error_message or "Failed to start organization",
        returncode=result.returncode,
    )


def stop_org(
    org_path: Path,
    force: bool = False,
    cleanup: bool = True,
    *,
    validate_path: bool = True,
) -> StopResult:
    """Stop an org via `qn org stop`. Returns a StopResult."""
    if validate_path:
        from .org_discovery import validate_org_path

        is_valid, validation_error = validate_org_path(org_path)
        if not is_valid:
            return StopResult(success=False, message=validation_error, returncode=-1)

    cli_available, cli_error = check_cli_available()
    if not cli_available:
        return StopResult(success=False, message=cli_error, returncode=-1)

    result = get_default_qn_cli().org_stop(org_path, force=force, cleanup=cleanup)
    if result.success:
        return StopResult(
            success=True,
            message=result.output or "Organization stopped successfully",
            returncode=0,
        )
    return StopResult(
        success=False,
        message=result.error_message or "Failed to stop organization",
        returncode=result.returncode,
    )


def restart_org(
    org_path: Path,
    spawn_ceo: bool = True,
    provider: str = "claude_code",
    skip_config_validation: bool = False,
    graceful_timeout: int = 10,
) -> StartResult:
    """Restart an org by stopping then starting it.

    Returns a StartResult capturing whichever phase failed first.
    `graceful_timeout` is accepted for API compatibility but not currently
    plumbed through (qn org stop has its own internal default).
    """
    stop_result = stop_org(org_path, force=False, cleanup=True)
    if not stop_result.success:
        return StartResult(
            success=False,
            message=f"Failed to stop org during restart: {stop_result.message}",
            returncode=stop_result.returncode,
        )

    start_result = start_org(
        org_path,
        spawn_ceo=spawn_ceo,
        provider=provider,
        skip_config_validation=skip_config_validation,
    )
    if start_result.success:
        return StartResult(
            success=True,
            message="Organization restarted successfully",
            returncode=0,
        )
    return StartResult(
        success=False,
        message=f"Org stopped but failed to restart: {start_result.message}",
        returncode=start_result.returncode,
    )
