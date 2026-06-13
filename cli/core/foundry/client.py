"""Pure-Python model of the start-simpli FOUNDRY provisioning call path.

``FoundryClient`` lets a QuinnAI app-group worker compute a DRY-RUN provisioning
plan for a tenant stack: the ordered list of orchestrator steps plus the derived
identifiers (ECR namespace, terraform state key, secrets bundle ARN, canonical
audience). It performs NO real provisioning — there are no AWS, Django, or
network imports anywhere in this module, so the call path is testable in
isolation.

Trust boundary
--------------
``plan_provision`` defaults to ``mode="local"`` (dry-run) and is always safe to
call. The real ``provision`` path requires an explicit non-dry-run mode AND an
explicit ``allow_apply=True`` gate; even then it raises
``FoundryProvisioningNotAllowed`` because live AWS/central steps are attended and
out of scope for QuinnAI. A worker can model the call without ever touching real
infrastructure.

Validation and derivation mirror start-simpli's
``backend/apps/foundry/provisioning.py`` (the runtime source of truth) and
``scripts/provision_tenant.py`` (the standalone generator). The slug gate is the
single security choke point: a strict lowercase DNS label that keeps the
``-`` -> ``_`` Postgres-identifier map injective and forbids the characters that
would break audience canonicality or allow path traversal in the derived
tfstate / secrets keys.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Optional

# -- modes ------------------------------------------------------------------
# A foundry run mode selects which parts of the orchestrator actually execute.
# QuinnAI only ever drives LOCAL (dry-run); the others are modeled for parity
# with start-simpli's orchestrator but are not runnable from here.
FOUNDRY_MODE_LOCAL = "local"
FOUNDRY_MODE_DOCKER = "docker"
FOUNDRY_MODE_AWS = "aws"
FOUNDRY_MODES = (FOUNDRY_MODE_LOCAL, FOUNDRY_MODE_DOCKER, FOUNDRY_MODE_AWS)

# Only LOCAL is a true dry-run with no real side effects.
DRY_RUN_MODES = (FOUNDRY_MODE_LOCAL,)

# -- audience / namespace prefixes (no magic strings in function bodies) ----
AUDIENCE_PREFIX = "tenant:"
ECR_NAMESPACE_PREFIX = "foundry-tenant-"
TFSTATE_KEY_SUFFIX = "/terraform.tfstate"
SECRETS_BUNDLE_PREFIX = "foundry/"
SECRETS_BUNDLE_SUFFIX = "/runtime"

# -- knob keys (must match deploy/rc.yml.tmpl in start-simpli) --------------
KNOB_SLUG = "SLUG"
KNOB_VPC_CIDR = "VPC_CIDR"
KNOB_DOMAIN = "DOMAIN"
KNOB_ECR_NAMESPACE = "ECR_NAMESPACE"
KNOB_TFSTATE_KEY = "TFSTATE_KEY"
KNOB_SECRETS_BUNDLE_ARN = "SECRETS_BUNDLE_ARN"
KNOB_KEYS = (
    KNOB_SLUG,
    KNOB_VPC_CIDR,
    KNOB_DOMAIN,
    KNOB_ECR_NAMESPACE,
    KNOB_TFSTATE_KEY,
    KNOB_SECRETS_BUNDLE_ARN,
)

# -- step keys (mirror apps.foundry.orchestrator.PROVISION_STEPS) -----------
STEP_VALIDATE = "validate"
STEP_REGISTER_TENANT = "register_tenant"
STEP_PUSH_SECRETS = "push_secrets"
STEP_BUILD_IMAGES = "build_images"
STEP_PROVISION_INFRA = "provision_infra"
STEP_MIGRATE = "migrate"
STEP_VERIFY = "verify"
STEP_FINALIZE = "finalize"

# Ordered provision-step keys — identical sequence to start-simpli's
# orchestrator PROVISION_STEPS. The plan reports this exact order.
FOUNDRY_PROVISION_STEPS = (
    STEP_VALIDATE,
    STEP_REGISTER_TENANT,
    STEP_PUSH_SECRETS,
    STEP_BUILD_IMAGES,
    STEP_PROVISION_INFRA,
    STEP_MIGRATE,
    STEP_VERIFY,
    STEP_FINALIZE,
)

# Plan-step lifecycle markers. In a dry-run nothing actually runs, so every step
# is reported as PLANNED rather than running/succeeded.
STEP_STATUS_PLANNED = "planned"

# -- validation regexes (verbatim from apps.foundry.provisioning) -----------
# Strict lowercase DNS-label slug: 3-40 chars, no underscore (keeps the
# '-'->'_' Postgres-identifier map injective), no '.', '/', space, ':' or '*'.
_SLUG_RE = re.compile(r"^[a-z][a-z0-9-]{1,38}[a-z0-9]$")
# Single RFC-1123 hostname — no commas (multi-host slip), no '/' or '*'.
_DOMAIN_RE = re.compile(
    r"^(?=.{1,253}$)([a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?)(\.[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?)+$"
)


# -- exceptions -------------------------------------------------------------

class FoundryError(Exception):
    """Base class for all foundry-client errors."""


class InvalidFoundrySlug(FoundryError, ValueError):
    """Raised when a tenant slug fails the strict DNS-label gate.

    Subclasses ``ValueError`` so callers that expect a value error from the
    underlying validation still catch it, while ``FoundryError`` lets callers
    handle all foundry problems uniformly.
    """

    def __init__(self, slug: object) -> None:
        self.slug = slug
        super().__init__(
            f"invalid slug {slug!r}: must be a lowercase DNS label (3-40 chars, "
            f"[a-z][a-z0-9-]*[a-z0-9], no underscore/dot/slash/space/':'/'*')"
        )


class InvalidFoundryDomain(FoundryError, ValueError):
    """Raised when a tenant domain is not a single RFC-1123 hostname."""

    def __init__(self, domain: object) -> None:
        self.domain = domain
        super().__init__(
            f"invalid domain {domain!r}: must be a single RFC-1123 hostname"
        )


class FoundryProvisioningNotAllowed(FoundryError):
    """Raised when a real (non-dry-run) provision is attempted.

    Live AWS/central provisioning is attended and out of scope for QuinnAI; the
    real path stays gated so a tenant stack is never created unattended.
    """

    def __init__(self, mode: str, *, reason: str) -> None:
        self.mode = mode
        self.reason = reason
        super().__init__(f"real provisioning (mode={mode!r}) refused: {reason}")


# -- validation + derivation (pure functions) -------------------------------

def validate_slug(slug: str) -> str:
    """Validate a tenant slug against the strict DNS-label gate.

    Args:
        slug: Candidate tenant slug.

    Returns:
        The validated slug, unchanged.

    Raises:
        InvalidFoundrySlug: If ``slug`` is not a lowercase DNS label.
    """
    if not isinstance(slug, str) or not _SLUG_RE.fullmatch(slug):
        raise InvalidFoundrySlug(slug)
    return slug


def validate_domain(domain: str) -> str:
    """Validate a tenant domain as a single RFC-1123 hostname.

    Args:
        domain: Candidate vanity domain.

    Returns:
        The validated domain, unchanged.

    Raises:
        InvalidFoundryDomain: If ``domain`` is not a single RFC-1123 hostname.
    """
    if not isinstance(domain, str) or not _DOMAIN_RE.fullmatch(domain):
        raise InvalidFoundryDomain(domain)
    return domain


def canonical_audience(slug: str) -> str:
    """Derive the canonical cross-tenant audience for a slug.

    There is exactly ONE canonical audience form so a non-canonical or typo'd
    audience can never be emitted. The slug is validated first.

    Args:
        slug: Tenant slug.

    Returns:
        The canonical audience string, e.g. ``"tenant:acme"``.

    Raises:
        InvalidFoundrySlug: If ``slug`` is invalid.
    """
    return f"{AUDIENCE_PREFIX}{validate_slug(slug)}"


def derive_knobs(slug: str, domain: str, vpc_cidr: Optional[str] = None) -> dict[str, str]:
    """Derive the 6 deploy knobs from the operator inputs.

    Mirrors ``apps.foundry.provisioning.derive_knobs`` and the knob block in
    ``scripts/provision_tenant.py``. ``vpc_cidr`` is optional in dry-run (it does
    not affect any derived identifier) and is recorded verbatim when supplied.

    Args:
        slug: Tenant slug (validated).
        domain: Tenant vanity domain (validated).
        vpc_cidr: Optional VPC CIDR block; empty string when omitted.

    Returns:
        Mapping of all six knob keys to their derived values.

    Raises:
        InvalidFoundrySlug: If ``slug`` is invalid.
        InvalidFoundryDomain: If ``domain`` is invalid.
    """
    validate_slug(slug)
    validate_domain(domain)
    return {
        KNOB_SLUG: slug,
        KNOB_VPC_CIDR: vpc_cidr or "",
        KNOB_DOMAIN: domain,
        KNOB_ECR_NAMESPACE: f"{ECR_NAMESPACE_PREFIX}{slug}",
        KNOB_TFSTATE_KEY: f"{ECR_NAMESPACE_PREFIX}{slug}{TFSTATE_KEY_SUFFIX}",
        KNOB_SECRETS_BUNDLE_ARN: f"{SECRETS_BUNDLE_PREFIX}{slug}{SECRETS_BUNDLE_SUFFIX}",
    }


# -- plan dataclasses -------------------------------------------------------

@dataclass(frozen=True)
class ProvisionStep:
    """A single planned orchestrator step in dry-run order.

    Attributes:
        order: Zero-based position of the step in the sequence.
        key: Stable step key (matches the start-simpli orchestrator).
        status: Lifecycle marker; always ``"planned"`` in a dry-run.
    """

    order: int
    key: str
    status: str = STEP_STATUS_PLANNED


@dataclass(frozen=True)
class ProvisionPlan:
    """A DRY-RUN provisioning plan for a single tenant.

    No real provisioning has occurred — this is the modeled call path only.

    Attributes:
        slug: Validated tenant slug.
        domain: Validated tenant vanity domain.
        vpc_cidr: VPC CIDR block (empty string when not supplied).
        mode: Run mode the plan was computed for (``"local"`` by default).
        dry_run: True when ``mode`` performs no real side effects.
        audience: Canonical audience, e.g. ``"tenant:acme"``.
        ecr_namespace: Derived ECR namespace.
        tfstate_key: Derived terraform state key.
        secrets_bundle_arn: Derived secrets bundle ARN.
        knobs: Full 6-knob mapping.
        steps: Ordered planned orchestrator steps.
    """

    slug: str
    domain: str
    vpc_cidr: str
    mode: str
    dry_run: bool
    audience: str
    ecr_namespace: str
    tfstate_key: str
    secrets_bundle_arn: str
    knobs: dict[str, str] = field(default_factory=dict)
    steps: tuple[ProvisionStep, ...] = ()

    @property
    def step_keys(self) -> tuple[str, ...]:
        """The ordered step keys only (convenience for assertions/logging)."""
        return tuple(step.key for step in self.steps)


# -- client -----------------------------------------------------------------

class FoundryClient:
    """Trust-bounded client modeling the foundry provisioning call path.

    The client is pure: it has no AWS, Django, or network dependencies. Use
    ``plan_provision`` (dry-run by default) to compute the ordered step plan and
    derived identifiers. ``provision`` exists for parity but is gated and never
    performs live provisioning from QuinnAI.

    Args:
        default_mode: Mode used when ``plan_provision`` is called without one.
            Must be a known foundry mode; defaults to ``"local"`` (dry-run).

    Raises:
        ValueError: If ``default_mode`` is not a recognized foundry mode.
    """

    def __init__(self, default_mode: str = FOUNDRY_MODE_LOCAL) -> None:
        if default_mode not in FOUNDRY_MODES:
            raise ValueError(
                f"unknown foundry mode {default_mode!r}; expected one of {FOUNDRY_MODES}"
            )
        self._default_mode = default_mode

    @property
    def default_mode(self) -> str:
        """The mode used when ``plan_provision`` is called without one."""
        return self._default_mode

    def plan_provision(
        self,
        slug: str,
        domain: str,
        vpc_cidr: Optional[str] = None,
        mode: str = FOUNDRY_MODE_LOCAL,
    ) -> ProvisionPlan:
        """Compute a DRY-RUN provisioning plan for a tenant.

        Validates the inputs, derives the canonical audience and the six deploy
        knobs, and returns the ordered orchestrator step plan. No provisioning is
        performed and no infrastructure is touched, regardless of ``mode``.

        Args:
            slug: Tenant slug (validated as a strict DNS label).
            domain: Tenant vanity domain (validated as a single RFC-1123 host).
            vpc_cidr: Optional VPC CIDR block; recorded but not required.
            mode: Run mode to compute the plan for. Defaults to ``"local"``.

        Returns:
            A :class:`ProvisionPlan` describing the modeled call path.

        Raises:
            InvalidFoundrySlug: If ``slug`` is invalid.
            InvalidFoundryDomain: If ``domain`` is invalid.
            ValueError: If ``mode`` is not a recognized foundry mode.
        """
        if mode not in FOUNDRY_MODES:
            raise ValueError(
                f"unknown foundry mode {mode!r}; expected one of {FOUNDRY_MODES}"
            )
        # Slug gate FIRST — before any derivation (mirrors build_plan ordering).
        validate_slug(slug)
        validate_domain(domain)

        knobs = derive_knobs(slug, domain, vpc_cidr)
        steps = tuple(
            ProvisionStep(order=i, key=key)
            for i, key in enumerate(FOUNDRY_PROVISION_STEPS)
        )
        return ProvisionPlan(
            slug=slug,
            domain=domain,
            vpc_cidr=knobs[KNOB_VPC_CIDR],
            mode=mode,
            dry_run=mode in DRY_RUN_MODES,
            audience=canonical_audience(slug),
            ecr_namespace=knobs[KNOB_ECR_NAMESPACE],
            tfstate_key=knobs[KNOB_TFSTATE_KEY],
            secrets_bundle_arn=knobs[KNOB_SECRETS_BUNDLE_ARN],
            knobs=knobs,
            steps=steps,
        )

    def provision(
        self,
        slug: str,
        domain: str,
        vpc_cidr: Optional[str] = None,
        mode: str = FOUNDRY_MODE_LOCAL,
        allow_apply: bool = False,
    ) -> ProvisionPlan:
        """Real provisioning entry point — intentionally gated.

        In a dry-run mode this is exactly :meth:`plan_provision` (no side
        effects). For any real mode it refuses: live AWS/central steps are
        attended and out of scope for QuinnAI, so this never creates a tenant
        stack. The ``allow_apply`` flag is an explicit second gate; even with it
        set, a real mode raises rather than touching infrastructure.

        Args:
            slug: Tenant slug.
            domain: Tenant vanity domain.
            vpc_cidr: Optional VPC CIDR block.
            mode: Run mode. ``"local"`` returns the dry-run plan; any other mode
                is treated as a real provision request.
            allow_apply: Must be True to even attempt a real provision. When a
                real mode is requested without it, the call is refused.

        Returns:
            A :class:`ProvisionPlan` (dry-run only).

        Raises:
            FoundryProvisioningNotAllowed: For any non-dry-run mode (regardless
                of ``allow_apply``).
            InvalidFoundrySlug: If ``slug`` is invalid.
            InvalidFoundryDomain: If ``domain`` is invalid.
            ValueError: If ``mode`` is not a recognized foundry mode.
        """
        if mode in DRY_RUN_MODES:
            return self.plan_provision(slug, domain, vpc_cidr, mode)

        if mode not in FOUNDRY_MODES:
            raise ValueError(
                f"unknown foundry mode {mode!r}; expected one of {FOUNDRY_MODES}"
            )
        if not allow_apply:
            raise FoundryProvisioningNotAllowed(
                mode,
                reason="real provisioning requires explicit allow_apply=True",
            )
        # Even with allow_apply, QuinnAI does not run live AWS/central steps.
        raise FoundryProvisioningNotAllowed(
            mode,
            reason=(
                "live AWS/central provisioning is attended and out of scope; "
                "use mode='local' for the dry-run plan"
            ),
        )
