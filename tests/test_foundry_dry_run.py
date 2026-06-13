"""Unit tests for the foundry-aware worker capability (dry-run call path).

Verifies that ``FoundryClient.plan_provision`` models start-simpli's FOUNDRY
provisioning purely — the correct ordered orchestrator steps and the correctly
derived identifiers — and that the real ``provision`` path stays gated so no AWS
work runs from a dry-run. Stdlib + pytest only (no AWS, Django, or network).
"""

from __future__ import annotations

import pytest

from cli.core.foundry import (
    FOUNDRY_PROVISION_STEPS,
    FoundryClient,
    FoundryError,
    FoundryProvisioningNotAllowed,
    InvalidFoundryDomain,
    InvalidFoundrySlug,
    ProvisionPlan,
    canonical_audience,
    derive_knobs,
)

SAMPLE_SLUG = "acme"
SAMPLE_DOMAIN = "acme.startsimpli.com"
SAMPLE_VPC_CIDR = "10.20.0.0/16"

# The exact ordered step sequence start-simpli's orchestrator runs.
EXPECTED_STEP_KEYS = (
    "validate",
    "register_tenant",
    "push_secrets",
    "build_images",
    "provision_infra",
    "migrate",
    "verify",
    "finalize",
)


@pytest.fixture
def client() -> FoundryClient:
    """A default (local/dry-run) foundry client."""
    return FoundryClient()


class TestPlanProvisionSteps:
    """The plan returns the expected ordered orchestrator step sequence."""

    def test_step_keys_match_expected_order(self, client: FoundryClient) -> None:
        plan = client.plan_provision(SAMPLE_SLUG, SAMPLE_DOMAIN)
        assert plan.step_keys == EXPECTED_STEP_KEYS

    def test_steps_match_module_constant(self, client: FoundryClient) -> None:
        plan = client.plan_provision(SAMPLE_SLUG, SAMPLE_DOMAIN)
        assert plan.step_keys == FOUNDRY_PROVISION_STEPS

    def test_steps_carry_zero_based_order(self, client: FoundryClient) -> None:
        plan = client.plan_provision(SAMPLE_SLUG, SAMPLE_DOMAIN)
        assert [step.order for step in plan.steps] == list(range(len(EXPECTED_STEP_KEYS)))

    def test_steps_are_planned_not_executed(self, client: FoundryClient) -> None:
        plan = client.plan_provision(SAMPLE_SLUG, SAMPLE_DOMAIN)
        assert {step.status for step in plan.steps} == {"planned"}

    def test_validate_is_first_step(self, client: FoundryClient) -> None:
        plan = client.plan_provision(SAMPLE_SLUG, SAMPLE_DOMAIN)
        assert plan.steps[0].key == "validate"

    def test_finalize_is_last_step(self, client: FoundryClient) -> None:
        plan = client.plan_provision(SAMPLE_SLUG, SAMPLE_DOMAIN)
        assert plan.steps[-1].key == "finalize"


class TestPlanProvisionIdentifiers:
    """Derived identifiers match start-simpli's provisioning derivation."""

    def test_canonical_audience(self, client: FoundryClient) -> None:
        plan = client.plan_provision(SAMPLE_SLUG, SAMPLE_DOMAIN)
        assert plan.audience == "tenant:acme"

    def test_ecr_namespace(self, client: FoundryClient) -> None:
        plan = client.plan_provision(SAMPLE_SLUG, SAMPLE_DOMAIN)
        assert plan.ecr_namespace == "foundry-tenant-acme"

    def test_tfstate_key(self, client: FoundryClient) -> None:
        plan = client.plan_provision(SAMPLE_SLUG, SAMPLE_DOMAIN)
        assert plan.tfstate_key == "foundry-tenant-acme/terraform.tfstate"

    def test_secrets_bundle_arn(self, client: FoundryClient) -> None:
        plan = client.plan_provision(SAMPLE_SLUG, SAMPLE_DOMAIN)
        assert plan.secrets_bundle_arn == "foundry/acme/runtime"

    def test_knobs_full_set(self, client: FoundryClient) -> None:
        plan = client.plan_provision(SAMPLE_SLUG, SAMPLE_DOMAIN, vpc_cidr=SAMPLE_VPC_CIDR)
        assert plan.knobs == {
            "SLUG": "acme",
            "VPC_CIDR": "10.20.0.0/16",
            "DOMAIN": "acme.startsimpli.com",
            "ECR_NAMESPACE": "foundry-tenant-acme",
            "TFSTATE_KEY": "foundry-tenant-acme/terraform.tfstate",
            "SECRETS_BUNDLE_ARN": "foundry/acme/runtime",
        }

    def test_vpc_cidr_optional_defaults_empty(self, client: FoundryClient) -> None:
        plan = client.plan_provision(SAMPLE_SLUG, SAMPLE_DOMAIN)
        assert plan.vpc_cidr == ""
        assert plan.knobs["VPC_CIDR"] == ""

    def test_plan_is_dry_run_by_default(self, client: FoundryClient) -> None:
        plan = client.plan_provision(SAMPLE_SLUG, SAMPLE_DOMAIN)
        assert plan.mode == "local"
        assert plan.dry_run is True

    def test_hyphenated_slug_identifiers(self, client: FoundryClient) -> None:
        plan = client.plan_provision("acme-corp", "acme-corp.startsimpli.com")
        assert plan.audience == "tenant:acme-corp"
        assert plan.ecr_namespace == "foundry-tenant-acme-corp"
        assert plan.secrets_bundle_arn == "foundry/acme-corp/runtime"

    def test_returns_provision_plan_type(self, client: FoundryClient) -> None:
        plan = client.plan_provision(SAMPLE_SLUG, SAMPLE_DOMAIN)
        assert isinstance(plan, ProvisionPlan)


class TestPureHelpers:
    """The pure derivation helpers behave consistently with the plan."""

    def test_canonical_audience_helper(self) -> None:
        assert canonical_audience("acme") == "tenant:acme"

    def test_derive_knobs_helper(self) -> None:
        knobs = derive_knobs("acme", "acme.startsimpli.com", "10.0.0.0/16")
        assert knobs["ECR_NAMESPACE"] == "foundry-tenant-acme"
        assert knobs["TFSTATE_KEY"] == "foundry-tenant-acme/terraform.tfstate"
        assert knobs["SECRETS_BUNDLE_ARN"] == "foundry/acme/runtime"


class TestSlugValidation:
    """Invalid slugs raise a specific exception (the security choke point)."""

    @pytest.mark.parametrize(
        "bad_slug",
        [
            "ab",  # too short (< 3)
            "a" * 41,  # too long (> 40)
            "Acme",  # uppercase
            "acme_corp",  # underscore (breaks injective DB-identifier map)
            "acme.corp",  # dot
            "acme/corp",  # slash (path traversal)
            "acme corp",  # space
            "acme:corp",  # colon
            "acme*",  # glob
            "-acme",  # leading hyphen
            "acme-",  # trailing hyphen
            "",  # empty
        ],
    )
    def test_invalid_slug_raises(self, client: FoundryClient, bad_slug: str) -> None:
        with pytest.raises(InvalidFoundrySlug):
            client.plan_provision(bad_slug, SAMPLE_DOMAIN)

    def test_invalid_slug_is_foundry_error(self, client: FoundryClient) -> None:
        with pytest.raises(FoundryError):
            client.plan_provision("acme_corp", SAMPLE_DOMAIN)

    def test_invalid_slug_is_value_error(self, client: FoundryClient) -> None:
        # Subclasses ValueError so underlying-validation callers still catch it.
        with pytest.raises(ValueError):
            client.plan_provision("acme_corp", SAMPLE_DOMAIN)

    def test_non_string_slug_raises(self, client: FoundryClient) -> None:
        with pytest.raises(InvalidFoundrySlug):
            client.plan_provision(None, SAMPLE_DOMAIN)  # type: ignore[arg-type]

    def test_invalid_slug_never_emits_audience(self) -> None:
        with pytest.raises(InvalidFoundrySlug):
            canonical_audience("bad/slug")


class TestDomainValidation:
    """Invalid domains raise a specific exception."""

    @pytest.mark.parametrize(
        "bad_domain",
        [
            "not a domain",
            "acme",  # single label, no dot
            "acme.startsimpli.com,evil.com",  # multi-host slip
            "acme.startsimpli.com/path",  # path
            "*.startsimpli.com",  # wildcard
            "",
        ],
    )
    def test_invalid_domain_raises(self, client: FoundryClient, bad_domain: str) -> None:
        with pytest.raises(InvalidFoundryDomain):
            client.plan_provision(SAMPLE_SLUG, bad_domain)

    def test_slug_gate_runs_before_domain(self, client: FoundryClient) -> None:
        # Both invalid -> slug gate fires first (matches build_plan ordering).
        with pytest.raises(InvalidFoundrySlug):
            client.plan_provision("bad_slug", "also not a domain")


class TestRealProvisionGating:
    """The real provision path is gated and runs no AWS in dry-run."""

    def test_local_mode_returns_dry_run_plan(self, client: FoundryClient) -> None:
        plan = client.provision(SAMPLE_SLUG, SAMPLE_DOMAIN, mode="local")
        assert isinstance(plan, ProvisionPlan)
        assert plan.dry_run is True
        assert plan.step_keys == EXPECTED_STEP_KEYS

    def test_aws_mode_without_allow_apply_refused(self, client: FoundryClient) -> None:
        with pytest.raises(FoundryProvisioningNotAllowed):
            client.provision(SAMPLE_SLUG, SAMPLE_DOMAIN, mode="aws")

    def test_aws_mode_even_with_allow_apply_refused(self, client: FoundryClient) -> None:
        # Out of scope: live AWS/central steps are attended.
        with pytest.raises(FoundryProvisioningNotAllowed):
            client.provision(SAMPLE_SLUG, SAMPLE_DOMAIN, mode="aws", allow_apply=True)

    def test_docker_mode_refused(self, client: FoundryClient) -> None:
        with pytest.raises(FoundryProvisioningNotAllowed):
            client.provision(SAMPLE_SLUG, SAMPLE_DOMAIN, mode="docker", allow_apply=True)

    def test_provision_refusal_reports_mode(self, client: FoundryClient) -> None:
        with pytest.raises(FoundryProvisioningNotAllowed) as excinfo:
            client.provision(SAMPLE_SLUG, SAMPLE_DOMAIN, mode="aws", allow_apply=True)
        assert excinfo.value.mode == "aws"

    def test_unknown_mode_raises_value_error(self, client: FoundryClient) -> None:
        with pytest.raises(ValueError):
            client.plan_provision(SAMPLE_SLUG, SAMPLE_DOMAIN, mode="quantum")

    def test_unknown_default_mode_rejected(self) -> None:
        with pytest.raises(ValueError):
            FoundryClient(default_mode="quantum")
