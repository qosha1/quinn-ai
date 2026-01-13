"""
Pytest configuration and fixtures for backend tests.

This module provides reusable fixtures for testing the B2B SaaS API including:
- API clients (authenticated, unauthenticated, API key)
- Factory functions for creating test entities
- Database setup and teardown

Usage:
    pytest --ds=config.settings.test
"""

from datetime import timedelta
from decimal import Decimal
from typing import Optional
from uuid import uuid4

import pytest
from django.utils import timezone
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

from apps.users.models import User
from apps.teams.models import Company, Team, TeamMember, TeamInvitation
from apps.authentication.models import APIKey
from apps.billing.models import Plan, Subscription, Invoice, UsageType, UsageLimit


# ==============================================================================
# API Client Fixtures
# ==============================================================================

@pytest.fixture
def api_client() -> APIClient:
    """
    Provide an unauthenticated DRF APIClient instance.

    Returns:
        APIClient: Fresh API client for making requests
    """
    return APIClient()


@pytest.fixture
def authenticated_client(api_client: APIClient, user: User) -> APIClient:
    """
    Provide an API client authenticated with JWT token.

    Args:
        api_client: Base API client
        user: User to authenticate as

    Returns:
        APIClient: Client with JWT authentication header set
    """
    refresh = RefreshToken.for_user(user)
    api_client.credentials(HTTP_AUTHORIZATION=f"Bearer {refresh.access_token}")
    return api_client


@pytest.fixture
def owner_client(api_client: APIClient, owner_user: User) -> APIClient:
    """
    Provide an API client authenticated as company owner.

    Args:
        api_client: Base API client
        owner_user: User with owner role

    Returns:
        APIClient: Client authenticated as owner
    """
    refresh = RefreshToken.for_user(owner_user)
    api_client.credentials(HTTP_AUTHORIZATION=f"Bearer {refresh.access_token}")
    return api_client


@pytest.fixture
def admin_client(api_client: APIClient, admin_user: User) -> APIClient:
    """
    Provide an API client authenticated as team admin.

    Args:
        api_client: Base API client
        admin_user: User with admin role

    Returns:
        APIClient: Client authenticated as admin
    """
    refresh = RefreshToken.for_user(admin_user)
    api_client.credentials(HTTP_AUTHORIZATION=f"Bearer {refresh.access_token}")
    return api_client


@pytest.fixture
def member_client(api_client: APIClient, member_user: User) -> APIClient:
    """
    Provide an API client authenticated as team member.

    Args:
        api_client: Base API client
        member_user: User with member role

    Returns:
        APIClient: Client authenticated as member
    """
    refresh = RefreshToken.for_user(member_user)
    api_client.credentials(HTTP_AUTHORIZATION=f"Bearer {refresh.access_token}")
    return api_client


@pytest.fixture
def viewer_client(api_client: APIClient, viewer_user: User) -> APIClient:
    """
    Provide an API client authenticated as team viewer.

    Args:
        api_client: Base API client
        viewer_user: User with viewer role

    Returns:
        APIClient: Client authenticated as viewer
    """
    refresh = RefreshToken.for_user(viewer_user)
    api_client.credentials(HTTP_AUTHORIZATION=f"Bearer {refresh.access_token}")
    return api_client


@pytest.fixture
def api_key_client(api_client: APIClient, api_key_raw: str) -> APIClient:
    """
    Provide an API client authenticated with API key.

    Args:
        api_client: Base API client
        api_key_raw: Raw API key string

    Returns:
        APIClient: Client with X-API-Key header set
    """
    api_client.credentials(HTTP_X_API_KEY=api_key_raw)
    return api_client


@pytest.fixture
def other_company_client(api_client: APIClient, other_company_user: User) -> APIClient:
    """
    Provide an API client authenticated as user from different company.

    Used for testing cross-company isolation.

    Args:
        api_client: Base API client
        other_company_user: User from a different company

    Returns:
        APIClient: Client authenticated as other company user
    """
    refresh = RefreshToken.for_user(other_company_user)
    api_client.credentials(HTTP_AUTHORIZATION=f"Bearer {refresh.access_token}")
    return api_client


# ==============================================================================
# User Factory Fixtures
# ==============================================================================

@pytest.fixture
def user_factory(db):
    """
    Factory function for creating test users.

    Returns:
        Callable: Function that creates User instances

    Usage:
        user = user_factory(email="test@example.com")
        user = user_factory(first_name="John", last_name="Doe")
    """
    def create_user(
        email: Optional[str] = None,
        password: str = "testpass123",
        first_name: str = "Test",
        last_name: str = "User",
        is_email_verified: bool = True,
        is_active: bool = True,
        company: Optional[Company] = None,
        **kwargs
    ) -> User:
        if email is None:
            email = f"user_{uuid4().hex[:8]}@example.com"

        user = User.objects.create_user(
            email=email,
            password=password,
            first_name=first_name,
            last_name=last_name,
            is_email_verified=is_email_verified,
            is_active=is_active,
            **kwargs
        )

        if company:
            user.company = company
            user.save(update_fields=["company"])

        return user

    return create_user


@pytest.fixture
def user(user_factory) -> User:
    """Create a basic test user without company."""
    return user_factory(email="testuser@example.com")


# ==============================================================================
# Company Factory Fixtures
# ==============================================================================

@pytest.fixture
def company_factory(db, user_factory):
    """
    Factory function for creating test companies.

    Returns:
        Callable: Function that creates Company instances with owner

    Usage:
        company = company_factory(name="Acme Corp")
        company, owner = company_factory(name="Test Co", return_owner=True)
    """
    def create_company(
        name: Optional[str] = None,
        owner: Optional[User] = None,
        settings: Optional[dict] = None,
        return_owner: bool = False,
        **kwargs
    ):
        if name is None:
            name = f"Company {uuid4().hex[:8]}"

        if owner is None:
            owner = user_factory(email=f"owner_{uuid4().hex[:8]}@example.com")

        company = Company.objects.create(
            name=name,
            owner=owner,
            settings=settings or {},
            **kwargs
        )

        # Assign company to owner
        owner.company = company
        owner.save(update_fields=["company"])

        if return_owner:
            return company, owner
        return company

    return create_company


@pytest.fixture
def company(company_factory) -> Company:
    """Create a test company with owner."""
    return company_factory(name="Test Company")


@pytest.fixture
def company_with_owner(company_factory):
    """Create a test company and return both company and owner."""
    return company_factory(name="Test Company", return_owner=True)


# ==============================================================================
# Team Factory Fixtures
# ==============================================================================

@pytest.fixture
def team_factory(db, company_factory, user_factory):
    """
    Factory function for creating test teams with members.

    Returns:
        Callable: Function that creates Team instances with optional members

    Usage:
        team = team_factory(name="Engineering")
        team = team_factory(company=existing_company)
        team = team_factory(add_members=[("admin", admin_user)])
    """
    def create_team(
        name: Optional[str] = None,
        company: Optional[Company] = None,
        settings: Optional[dict] = None,
        add_members: Optional[list] = None,
        **kwargs
    ) -> Team:
        if name is None:
            name = f"Team {uuid4().hex[:8]}"

        if company is None:
            company = company_factory()

        team = Team.objects.create(
            name=name,
            company=company,
            settings=settings or {},
            **kwargs
        )

        # Add members if specified
        # Format: [(role, user), ...]
        if add_members:
            for role, member_user in add_members:
                TeamMember.objects.create(
                    user=member_user,
                    team=team,
                    role=role,
                    invited_by=company.owner
                )

        return team

    return create_team


@pytest.fixture
def team(team_factory, company: Company) -> Team:
    """Create a test team in the test company."""
    return team_factory(name="Test Team", company=company)


# ==============================================================================
# Team Member Fixtures
# ==============================================================================

@pytest.fixture
def owner_user(user_factory, company: Company) -> User:
    """
    Create a user with owner role in the test company.

    Note: The company owner is automatically created with the company.
    This returns the company's owner.
    """
    return company.owner


@pytest.fixture
def admin_user(user_factory, company: Company, team: Team) -> User:
    """Create a user with admin role in the test team."""
    user = user_factory(
        email="admin@example.com",
        first_name="Admin",
        company=company
    )
    TeamMember.objects.create(
        user=user,
        team=team,
        role=TeamMember.Role.ADMIN,
        invited_by=company.owner
    )
    return user


@pytest.fixture
def member_user(user_factory, company: Company, team: Team) -> User:
    """Create a user with member role in the test team."""
    user = user_factory(
        email="member@example.com",
        first_name="Member",
        company=company
    )
    TeamMember.objects.create(
        user=user,
        team=team,
        role=TeamMember.Role.MEMBER,
        invited_by=company.owner
    )
    return user


@pytest.fixture
def viewer_user(user_factory, company: Company, team: Team) -> User:
    """Create a user with viewer role in the test team."""
    user = user_factory(
        email="viewer@example.com",
        first_name="Viewer",
        company=company
    )
    TeamMember.objects.create(
        user=user,
        team=team,
        role=TeamMember.Role.VIEWER,
        invited_by=company.owner
    )
    return user


# ==============================================================================
# Cross-Company Isolation Fixtures
# ==============================================================================

@pytest.fixture
def other_company(company_factory) -> Company:
    """Create a separate company for testing isolation."""
    return company_factory(name="Other Company")


@pytest.fixture
def other_company_user(user_factory, other_company: Company) -> User:
    """Create a user in a different company for testing isolation."""
    user = user_factory(
        email="other_company@example.com",
        first_name="Other",
        company=other_company
    )
    return user


@pytest.fixture
def other_team(team_factory, other_company: Company) -> Team:
    """Create a team in the other company for testing isolation."""
    return team_factory(name="Other Team", company=other_company)


# ==============================================================================
# API Key Fixtures
# ==============================================================================

@pytest.fixture
def api_key_instance(db, company: Company, owner_user: User):
    """
    Create an API key and return the instance.

    Note: The raw key is hashed on save, so this fixture
    creates the key and returns the instance.
    """
    api_key, raw_key = APIKey.create_key(
        name="Test API Key",
        company=company,
        created_by=owner_user,
        scopes=["read", "write"],
    )
    return api_key


@pytest.fixture
def api_key_raw(db, company: Company, owner_user: User) -> str:
    """
    Create an API key and return the raw (unhashed) key.

    This is needed for authentication testing since the
    hashed key cannot be used directly.
    """
    api_key, raw_key = APIKey.create_key(
        name="Test API Key",
        company=company,
        created_by=owner_user,
        scopes=["read", "write"],
    )
    return raw_key


# ==============================================================================
# Team Invitation Fixtures
# ==============================================================================

@pytest.fixture
def invitation_factory(db):
    """
    Factory function for creating test invitations.

    Returns:
        Callable: Function that creates TeamInvitation instances
    """
    def create_invitation(
        email: Optional[str] = None,
        team: Team = None,
        invited_by: User = None,
        role: str = TeamMember.Role.MEMBER,
        expires_in_days: int = 7,
        **kwargs
    ) -> TeamInvitation:
        if email is None:
            email = f"invite_{uuid4().hex[:8]}@example.com"

        invitation = TeamInvitation.objects.create(
            email=email,
            team=team,
            role=role,
            invited_by=invited_by,
            expires_at=timezone.now() + timedelta(days=expires_in_days),
            **kwargs
        )
        return invitation

    return create_invitation


@pytest.fixture
def invitation(invitation_factory, team: Team, owner_user: User) -> TeamInvitation:
    """Create a test invitation."""
    return invitation_factory(
        email="invited@example.com",
        team=team,
        invited_by=owner_user,
    )


@pytest.fixture
def expired_invitation(invitation_factory, team: Team, owner_user: User) -> TeamInvitation:
    """Create an expired invitation for testing."""
    invitation = invitation_factory(
        email="expired@example.com",
        team=team,
        invited_by=owner_user,
    )
    # Set expiration to past
    invitation.expires_at = timezone.now() - timedelta(days=1)
    invitation.save(update_fields=["expires_at"])
    return invitation


# ==============================================================================
# Billing and Subscription Fixtures
# ==============================================================================

@pytest.fixture
def plan_factory(db):
    """
    Factory function for creating test plans.

    Returns:
        Callable: Function that creates Plan instances
    """
    def create_plan(
        name: Optional[str] = None,
        slug: Optional[str] = None,
        price: Decimal = Decimal("29.99"),
        interval: str = Plan.Interval.MONTH,
        features: Optional[list] = None,
        limits: Optional[dict] = None,
        stripe_price_id: Optional[str] = None,
        is_active: bool = True,
        sort_order: int = 0,
        **kwargs
    ) -> Plan:
        if name is None:
            name = f"Plan {uuid4().hex[:8]}"
        if slug is None:
            slug = name.lower().replace(" ", "-")
        if stripe_price_id is None:
            stripe_price_id = f"price_{uuid4().hex}"

        return Plan.objects.create(
            name=name,
            slug=slug,
            price=price,
            interval=interval,
            features=features or ["Basic support", "API access"],
            limits=limits or {"api_calls": 10000, "storage_mb": 5000},
            stripe_price_id=stripe_price_id,
            is_active=is_active,
            sort_order=sort_order,
            **kwargs
        )

    return create_plan


@pytest.fixture
def plan(plan_factory) -> Plan:
    """Create a test plan."""
    return plan_factory(
        name="Pro Plan",
        slug="pro",
        price=Decimal("49.99"),
    )


@pytest.fixture
def free_plan(plan_factory) -> Plan:
    """Create a free tier plan."""
    return plan_factory(
        name="Free",
        slug="free",
        price=Decimal("0.00"),
        sort_order=0,
    )


@pytest.fixture
def enterprise_plan(plan_factory) -> Plan:
    """Create an enterprise plan."""
    return plan_factory(
        name="Enterprise",
        slug="enterprise",
        price=Decimal("299.99"),
        features=["Priority support", "API access", "SSO", "Custom integrations"],
        limits={"api_calls": 1000000, "storage_mb": 100000},
        sort_order=100,
    )


@pytest.fixture
def subscription_factory(db, plan_factory, company_factory):
    """
    Factory function for creating test subscriptions.

    Returns:
        Callable: Function that creates Subscription instances
    """
    def create_subscription(
        company: Optional[Company] = None,
        plan: Optional[Plan] = None,
        status: str = Subscription.Status.ACTIVE,
        stripe_subscription_id: Optional[str] = None,
        stripe_customer_id: Optional[str] = None,
        trial_days: int = 0,
        **kwargs
    ) -> Subscription:
        if company is None:
            company = company_factory()
        if plan is None:
            plan = plan_factory()
        if stripe_subscription_id is None:
            stripe_subscription_id = f"sub_{uuid4().hex}"
        if stripe_customer_id is None:
            stripe_customer_id = f"cus_{uuid4().hex}"

        now = timezone.now()

        subscription = Subscription.objects.create(
            company=company,
            plan=plan,
            status=status,
            stripe_subscription_id=stripe_subscription_id,
            stripe_customer_id=stripe_customer_id,
            current_period_start=now,
            current_period_end=now + timedelta(days=30),
            trial_start=now if trial_days > 0 else None,
            trial_end=now + timedelta(days=trial_days) if trial_days > 0 else None,
            **kwargs
        )
        return subscription

    return create_subscription


@pytest.fixture
def subscription(subscription_factory, company: Company, plan: Plan) -> Subscription:
    """Create a test subscription for the test company."""
    return subscription_factory(company=company, plan=plan)


# ==============================================================================
# Usage Tracking Fixtures
# ==============================================================================

@pytest.fixture
def usage_type_factory(db):
    """
    Factory function for creating usage types.

    Returns:
        Callable: Function that creates UsageType instances
    """
    def create_usage_type(
        name: Optional[str] = None,
        slug: Optional[str] = None,
        unit: str = "api_calls",
        description: str = "",
        **kwargs
    ) -> UsageType:
        if name is None:
            name = f"Usage Type {uuid4().hex[:8]}"
        if slug is None:
            slug = name.lower().replace(" ", "-")

        return UsageType.objects.create(
            name=name,
            slug=slug,
            unit=unit,
            description=description,
            **kwargs
        )

    return create_usage_type


@pytest.fixture
def api_calls_usage_type(usage_type_factory) -> UsageType:
    """Create an API calls usage type."""
    return usage_type_factory(
        name="API Calls",
        slug="api-calls",
        unit="calls",
        description="Number of API calls made"
    )


@pytest.fixture
def usage_limit_factory(db):
    """
    Factory function for creating usage limits.

    Returns:
        Callable: Function that creates UsageLimit instances
    """
    def create_usage_limit(
        plan: Plan,
        usage_type: UsageType,
        limit_value: Decimal = Decimal("10000"),
        overage_allowed: bool = False,
        overage_price: Optional[Decimal] = None,
        **kwargs
    ) -> UsageLimit:
        return UsageLimit.objects.create(
            plan=plan,
            usage_type=usage_type,
            limit_value=limit_value,
            overage_allowed=overage_allowed,
            overage_price=overage_price,
            **kwargs
        )

    return create_usage_limit


# ==============================================================================
# Invoice Fixtures
# ==============================================================================

@pytest.fixture
def invoice_factory(db):
    """
    Factory function for creating test invoices.

    Returns:
        Callable: Function that creates Invoice instances
    """
    def create_invoice(
        company: Company,
        subscription: Optional[Subscription] = None,
        amount: Decimal = Decimal("49.99"),
        status: str = Invoice.Status.PAID,
        stripe_invoice_id: Optional[str] = None,
        **kwargs
    ) -> Invoice:
        if stripe_invoice_id is None:
            stripe_invoice_id = f"in_{uuid4().hex}"

        now = timezone.now()

        return Invoice.objects.create(
            company=company,
            subscription=subscription,
            amount=amount,
            status=status,
            stripe_invoice_id=stripe_invoice_id,
            currency="usd",
            period_start=now - timedelta(days=30),
            period_end=now,
            paid_at=now if status == Invoice.Status.PAID else None,
            **kwargs
        )

    return create_invoice


# ==============================================================================
# Utility Fixtures
# ==============================================================================

@pytest.fixture
def jwt_token(user: User) -> str:
    """Generate a JWT access token for a user."""
    refresh = RefreshToken.for_user(user)
    return str(refresh.access_token)


@pytest.fixture
def jwt_refresh_token(user: User) -> str:
    """Generate a JWT refresh token for a user."""
    refresh = RefreshToken.for_user(user)
    return str(refresh)
