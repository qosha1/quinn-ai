"""Per-layer credential scoping for worker sessions (quinn-ai-a3pg.1.5).

A worker's session env is an allowlist (onboarding.get_worker_env_vars builds a
clean dict), so credentials are DEFAULT-DENY: a worker only receives the
credential env vars its team is scoped for. Scopes are declared in org.yml's
`secrets` block as env var NAMES (never values) and persisted to
<org config>/secrets-scope.yaml. Values are read from the orchestrator's
environment at spawn time — so e.g. only app-group workers get SIMPLI_API_TOKEN
/ VERCEL_TOKEN, while core-infra workers do not.

Maps onto the Simpli architecture: core-infra (auth-web, Django API, shared
packages) vs app-groups (one customer app each). The '*' team grants a
credential to every worker.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Mapping, Optional

from cli.core.constants import SECRETS_SCOPE_FILE, SECRETS_SCOPE_WILDCARD


def resolve_scope(team: Optional[str], policy: Mapping[str, list]) -> list[str]:
    """Env var names a team is allowed to receive (wildcard '*' applies to all).

    Args:
        team: The worker's team name (or None).
        policy: Mapping of team -> list of credential env var names.

    Returns:
        Ordered, de-duplicated list of allowed env var names.
    """
    names: list[str] = []
    for key in (SECRETS_SCOPE_WILDCARD, team):
        if not key or key not in policy:
            continue
        for var in policy[key] or []:
            if var not in names:
                names.append(var)
    return names


def collect_credentials(
    var_names: list[str], environ: Mapping[str, str]
) -> dict[str, str]:
    """Read the named vars from ``environ``, skipping unset/empty ones.

    Never logs values. Returns only the credentials actually present.
    """
    return {
        name: environ[name]
        for name in var_names
        if environ.get(name)
    }


def load_secrets_policy(org_path: Path) -> dict[str, list]:
    """Load the persisted secrets-scope policy; {} when none is set."""
    import yaml

    from cli.core.config import get_org_config_path

    path = get_org_config_path(org_path) / SECRETS_SCOPE_FILE
    if not path.exists():
        return {}
    try:
        data = yaml.safe_load(path.read_text()) or {}
    except Exception:
        return {}
    if not isinstance(data, dict):
        return {}
    return {key: list(value or []) for key, value in data.items()}


def scoped_env_for_team(
    org_path: Path,
    team: Optional[str],
    environ: Optional[Mapping[str, str]] = None,
) -> dict[str, str]:
    """Resolve the credential env vars a worker on ``team`` should receive.

    Args:
        org_path: Org metadata root (holds the persisted policy).
        team: The worker's team name.
        environ: Environment to read values from (defaults to os.environ).

    Returns:
        {var: value} for the team's scoped, currently-set credentials; {} when
        no policy is declared (default behavior — no extra credentials).
    """
    policy = load_secrets_policy(org_path)
    if not policy:
        return {}
    source = environ if environ is not None else os.environ
    return collect_credentials(resolve_scope(team, policy), source)
