"""
Tests for billing app.

These tests demonstrate the billing functionality.
Run with: python manage.py test apps.billing
"""

from decimal import Decimal
from datetime import timedelta

from django.test import TestCase
from django.utils import timezone
from django.contrib.auth import get_user_model

from apps.teams.models import Company
from apps.billing.models import (
    Plan,
    Subscription,
    Invoice,
    UsageType,
    UsageRecord,
    UsageLimit,
)
from apps.billing.services import UsageService

User = get_user_model()


class PlanModelTest(TestCase):
    """Test Plan model."""

    def setUp(self):
        """Set up test data."""
        self.plan = Plan.objects.create(
            name="Professional",
            slug="professional",
            stripe_price_id="price_test_123",
            price=Decimal("99.00"),
            interval=Plan.Interval.MONTH,
            features=["feature1", "feature2", "feature3"],
            limits={
                "api_calls": 10000,
                "storage_gb": 100,
                "seats": 10,
            },
            is_active=True,
            sort_order=1,
        )

    def test_plan_creation(self):
        """Test creating a plan."""
        self.assertEqual(self.plan.name, "Professional")
        self.assertEqual(self.plan.price, Decimal("99.00"))
        self.assertEqual(self.plan.interval, Plan.Interval.MONTH)
        self.assertTrue(self.plan.is_active)

    def test_plan_str(self):
        """Test plan string representation."""
        expected = "Professional ($99.00/month)"
        self.assertEqual(str(self.plan), expected)


class SubscriptionModelTest(TestCase):
    """Test Subscription model."""

    def setUp(self):
        """Set up test data."""
        self.user = User.objects.create_user(
            email="owner@example.com",
            password="testpass123"
        )
        self.company = Company.objects.create(
            name="Test Company",
            slug="test-company",
            owner=self.user,
        )
        self.plan = Plan.objects.create(
            name="Professional",
            slug="professional",
            stripe_price_id="price_test_123",
            price=Decimal("99.00"),
            interval=Plan.Interval.MONTH,
        )
        self.subscription = Subscription.objects.create(
            company=self.company,
            plan=self.plan,
            stripe_subscription_id="sub_test_123",
            stripe_customer_id="cus_test_123",
            status=Subscription.Status.ACTIVE,
            current_period_start=timezone.now(),
            current_period_end=timezone.now() + timedelta(days=30),
        )

    def test_subscription_creation(self):
        """Test creating a subscription."""
        self.assertEqual(self.subscription.company, self.company)
        self.assertEqual(self.subscription.plan, self.plan)
        self.assertEqual(self.subscription.status, Subscription.Status.ACTIVE)

    def test_is_active_property(self):
        """Test is_active property."""
        # Active subscription
        self.assertTrue(self.subscription.is_active)

        # Trialing subscription
        self.subscription.status = Subscription.Status.TRIALING
        self.assertTrue(self.subscription.is_active)

        # Cancelled subscription
        self.subscription.status = Subscription.Status.CANCELLED
        self.assertFalse(self.subscription.is_active)


class UsageServiceTest(TestCase):
    """Test UsageService."""

    def setUp(self):
        """Set up test data."""
        self.user = User.objects.create_user(
            email="owner@example.com",
            password="testpass123"
        )
        self.company = Company.objects.create(
            name="Test Company",
            slug="test-company",
            owner=self.user,
        )
        self.plan = Plan.objects.create(
            name="Professional",
            slug="professional",
            stripe_price_id="price_test_123",
            price=Decimal("99.00"),
            interval=Plan.Interval.MONTH,
        )
        self.subscription = Subscription.objects.create(
            company=self.company,
            plan=self.plan,
            stripe_subscription_id="sub_test_123",
            stripe_customer_id="cus_test_123",
            status=Subscription.Status.ACTIVE,
            current_period_start=timezone.now(),
            current_period_end=timezone.now() + timedelta(days=30),
        )
        self.usage_type = UsageType.objects.create(
            name="API Calls",
            slug="api_calls",
            unit="calls",
            description="Number of API calls made",
        )
        self.usage_limit = UsageLimit.objects.create(
            plan=self.plan,
            usage_type=self.usage_type,
            limit_value=Decimal("10000"),
            overage_allowed=False,
        )

    def test_record_usage(self):
        """Test recording usage."""
        record = UsageService.record_usage(
            company=self.company,
            usage_type_slug="api_calls",
            quantity=Decimal("100"),
        )

        self.assertEqual(record.company, self.company)
        self.assertEqual(record.usage_type, self.usage_type)
        self.assertEqual(record.quantity, Decimal("100"))

    def test_get_current_usage(self):
        """Test getting current usage."""
        # Record some usage
        UsageService.record_usage(
            company=self.company,
            usage_type_slug="api_calls",
            quantity=Decimal("100"),
        )
        UsageService.record_usage(
            company=self.company,
            usage_type_slug="api_calls",
            quantity=Decimal("50"),
        )

        # Get current usage
        usage = UsageService.get_current_usage(self.company, "api_calls")
        self.assertEqual(usage, Decimal("150"))

    def test_check_limit(self):
        """Test checking usage limits."""
        # Under limit
        self.assertTrue(
            UsageService.check_limit(self.company, "api_calls", Decimal("100"))
        )

        # Record usage near limit
        UsageService.record_usage(
            company=self.company,
            usage_type_slug="api_calls",
            quantity=Decimal("9900"),
        )

        # Still under limit
        self.assertTrue(
            UsageService.check_limit(self.company, "api_calls", Decimal("50"))
        )

        # Would exceed limit
        self.assertFalse(
            UsageService.check_limit(self.company, "api_calls", Decimal("200"))
        )

    def test_get_remaining(self):
        """Test getting remaining quota."""
        # No usage yet
        remaining = UsageService.get_remaining(self.company, "api_calls")
        self.assertEqual(remaining, Decimal("10000"))

        # Record some usage
        UsageService.record_usage(
            company=self.company,
            usage_type_slug="api_calls",
            quantity=Decimal("3000"),
        )

        # Check remaining
        remaining = UsageService.get_remaining(self.company, "api_calls")
        self.assertEqual(remaining, Decimal("7000"))

    def test_usage_limit_exceeded(self):
        """Test that usage recording fails when limit exceeded."""
        # Record usage up to limit
        UsageService.record_usage(
            company=self.company,
            usage_type_slug="api_calls",
            quantity=Decimal("9900"),
        )

        # Try to exceed limit
        with self.assertRaises(ValueError):
            UsageService.record_usage(
                company=self.company,
                usage_type_slug="api_calls",
                quantity=Decimal("200"),
            )


class InvoiceModelTest(TestCase):
    """Test Invoice model."""

    def setUp(self):
        """Set up test data."""
        self.user = User.objects.create_user(
            email="owner@example.com",
            password="testpass123"
        )
        self.company = Company.objects.create(
            name="Test Company",
            slug="test-company",
            owner=self.user,
        )
        self.plan = Plan.objects.create(
            name="Professional",
            slug="professional",
            stripe_price_id="price_test_123",
            price=Decimal("99.00"),
            interval=Plan.Interval.MONTH,
        )
        self.subscription = Subscription.objects.create(
            company=self.company,
            plan=self.plan,
            stripe_subscription_id="sub_test_123",
            stripe_customer_id="cus_test_123",
            status=Subscription.Status.ACTIVE,
            current_period_start=timezone.now(),
            current_period_end=timezone.now() + timedelta(days=30),
        )
        self.invoice = Invoice.objects.create(
            company=self.company,
            subscription=self.subscription,
            stripe_invoice_id="in_test_123",
            amount=Decimal("99.00"),
            currency="usd",
            status=Invoice.Status.PAID,
            invoice_pdf="https://example.com/invoice.pdf",
            period_start=timezone.now(),
            period_end=timezone.now() + timedelta(days=30),
            paid_at=timezone.now(),
        )

    def test_invoice_creation(self):
        """Test creating an invoice."""
        self.assertEqual(self.invoice.company, self.company)
        self.assertEqual(self.invoice.subscription, self.subscription)
        self.assertEqual(self.invoice.amount, Decimal("99.00"))
        self.assertEqual(self.invoice.status, Invoice.Status.PAID)
