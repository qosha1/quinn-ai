"""Foundry-aware worker capability for QuinnAI.

A trust-bounded, PURE-PYTHON model of start-simpli's FOUNDRY provisioning call
path. The foundry is start-simpli's control plane that provisions isolated tenant
stacks. This package lets a QuinnAI app-group worker compute a DRY-RUN
provisioning plan (the ordered orchestrator steps + the derived identifiers)
WITHOUT performing any real provisioning — no AWS, no Django, no network.

Real provisioning (`mode != local` with the gated apply flag) is intentionally
NOT implemented here: live AWS/central steps are attended and out of scope.

Mirrors (read-only study sources, not imported):
- start-simpli backend ``apps.foundry.orchestrator`` step sequence.
- start-simpli backend ``apps.foundry.provisioning`` validation + derivation.
- start-simpli ``scripts/provision_tenant.py`` CLI knob derivation.
"""

from __future__ import annotations

from cli.core.foundry.client import (
    FOUNDRY_PROVISION_STEPS,
    FoundryClient,
    FoundryError,
    FoundryProvisioningNotAllowed,
    InvalidFoundryDomain,
    InvalidFoundrySlug,
    ProvisionPlan,
    ProvisionStep,
    canonical_audience,
    derive_knobs,
    validate_domain,
    validate_slug,
)

__all__ = [
    "FOUNDRY_PROVISION_STEPS",
    "FoundryClient",
    "FoundryError",
    "FoundryProvisioningNotAllowed",
    "InvalidFoundryDomain",
    "InvalidFoundrySlug",
    "ProvisionPlan",
    "ProvisionStep",
    "canonical_audience",
    "derive_knobs",
    "validate_domain",
    "validate_slug",
]
