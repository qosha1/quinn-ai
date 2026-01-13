"""
Tests to validate billing-stripe implementation.

These tests verify that all required files from the add-billing-stripe
OpenSpec change have been created correctly.
"""

import os
import pytest

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BACKEND_ROOT = os.path.join(PROJECT_ROOT, "backend")


class TestBillingAppStructure:
    """Test billing app structure."""

    def test_billing_models_exists(self):
        """apps/billing/models.py should exist."""
        path = os.path.join(BACKEND_ROOT, "apps/billing/models.py")
        assert os.path.exists(path), "Billing models.py not found"

    def test_billing_views_exists(self):
        """apps/billing/api/views.py should exist."""
        path = os.path.join(BACKEND_ROOT, "apps/billing/api/views.py")
        assert os.path.exists(path), "Billing views.py not found"

    def test_billing_serializers_exists(self):
        """apps/billing/api/serializers.py should exist."""
        path = os.path.join(BACKEND_ROOT, "apps/billing/api/serializers.py")
        assert os.path.exists(path), "Billing serializers.py not found"

    def test_billing_services_exists(self):
        """apps/billing/services.py should exist."""
        path = os.path.join(BACKEND_ROOT, "apps/billing/services.py")
        assert os.path.exists(path), "Billing services.py not found"


class TestBillingModels:
    """Test billing model content."""

    def test_plan_model_exists(self):
        """Plan model should exist."""
        path = os.path.join(BACKEND_ROOT, "apps/billing/models.py")
        with open(path, 'r') as f:
            content = f.read()
        assert "class Plan" in content, "Plan model not found"

    def test_subscription_model_exists(self):
        """Subscription model should exist."""
        path = os.path.join(BACKEND_ROOT, "apps/billing/models.py")
        with open(path, 'r') as f:
            content = f.read()
        assert "class Subscription" in content, "Subscription model not found"

    def test_invoice_model_exists(self):
        """Invoice model should exist."""
        path = os.path.join(BACKEND_ROOT, "apps/billing/models.py")
        with open(path, 'r') as f:
            content = f.read()
        assert "class Invoice" in content, "Invoice model not found"

    def test_usage_type_model_exists(self):
        """UsageType model should exist."""
        path = os.path.join(BACKEND_ROOT, "apps/billing/models.py")
        with open(path, 'r') as f:
            content = f.read()
        assert "UsageType" in content, "UsageType model not found"

    def test_usage_record_model_exists(self):
        """UsageRecord model should exist."""
        path = os.path.join(BACKEND_ROOT, "apps/billing/models.py")
        with open(path, 'r') as f:
            content = f.read()
        assert "UsageRecord" in content, "UsageRecord model not found"

    def test_stripe_fields_exist(self):
        """Models should have stripe ID fields."""
        path = os.path.join(BACKEND_ROOT, "apps/billing/models.py")
        with open(path, 'r') as f:
            content = f.read()
        assert "stripe" in content.lower(), "Stripe fields not found"


class TestStripeIntegration:
    """Test Stripe integration files."""

    def test_stripe_client_exists(self):
        """apps/billing/stripe_client.py should exist."""
        path = os.path.join(BACKEND_ROOT, "apps/billing/stripe_client.py")
        assert os.path.exists(path), "stripe_client.py not found"

    def test_stripe_client_has_service_class(self):
        """StripeService class should exist."""
        path = os.path.join(BACKEND_ROOT, "apps/billing/stripe_client.py")
        with open(path, 'r') as f:
            content = f.read()
        assert "StripeService" in content or "class Stripe" in content, "StripeService not found"

    def test_checkout_session_method(self):
        """Checkout session method should exist."""
        path = os.path.join(BACKEND_ROOT, "apps/billing/stripe_client.py")
        with open(path, 'r') as f:
            content = f.read()
        assert "checkout" in content.lower(), "Checkout session method not found"

    def test_portal_session_method(self):
        """Portal session method should exist."""
        path = os.path.join(BACKEND_ROOT, "apps/billing/stripe_client.py")
        with open(path, 'r') as f:
            content = f.read()
        assert "portal" in content.lower(), "Portal session method not found"


class TestWebhooks:
    """Test webhook implementation."""

    def test_webhooks_file_exists(self):
        """apps/billing/webhooks.py should exist."""
        path = os.path.join(BACKEND_ROOT, "apps/billing/webhooks.py")
        assert os.path.exists(path), "webhooks.py not found"

    def test_webhook_handlers_exist(self):
        """Webhook handlers should exist."""
        path = os.path.join(BACKEND_ROOT, "apps/billing/webhooks.py")
        with open(path, 'r') as f:
            content = f.read()
        # Check for at least some webhook handling
        has_checkout = "checkout" in content.lower()
        has_subscription = "subscription" in content.lower()
        has_invoice = "invoice" in content.lower()
        assert has_checkout or has_subscription or has_invoice, "No webhook handlers found"

    def test_signature_verification(self):
        """Webhook should verify signature."""
        path = os.path.join(BACKEND_ROOT, "apps/billing/webhooks.py")
        with open(path, 'r') as f:
            content = f.read()
        has_verify = "verify" in content.lower() or "signature" in content.lower() or "construct_event" in content.lower()
        assert has_verify, "Signature verification not found"


class TestUsageTracking:
    """Test usage tracking implementation."""

    def test_usage_service_exists(self):
        """UsageService should exist in services.py."""
        path = os.path.join(BACKEND_ROOT, "apps/billing/services.py")
        with open(path, 'r') as f:
            content = f.read()
        assert "UsageService" in content or "usage" in content.lower(), "UsageService not found"

    def test_record_usage_method(self):
        """record_usage method should exist."""
        path = os.path.join(BACKEND_ROOT, "apps/billing/services.py")
        with open(path, 'r') as f:
            content = f.read()
        assert "record" in content.lower(), "record_usage method not found"

    def test_check_limit_method(self):
        """check_limit or similar method should exist."""
        path = os.path.join(BACKEND_ROOT, "apps/billing/services.py")
        with open(path, 'r') as f:
            content = f.read()
        has_limit = "limit" in content.lower() or "quota" in content.lower() or "check" in content.lower()
        assert has_limit, "Limit checking method not found"


class TestBillingAPIEndpoints:
    """Test billing API endpoints."""

    def test_plan_viewset_exists(self):
        """PlanViewSet should exist."""
        path = os.path.join(BACKEND_ROOT, "apps/billing/api/views.py")
        with open(path, 'r') as f:
            content = f.read()
        assert "Plan" in content, "Plan ViewSet not found"

    def test_subscription_viewset_exists(self):
        """Subscription ViewSet should exist."""
        path = os.path.join(BACKEND_ROOT, "apps/billing/api/views.py")
        with open(path, 'r') as f:
            content = f.read()
        assert "Subscription" in content, "Subscription ViewSet not found"

    def test_checkout_endpoint_exists(self):
        """Checkout endpoint should exist."""
        path = os.path.join(BACKEND_ROOT, "apps/billing/api/views.py")
        with open(path, 'r') as f:
            content = f.read()
        assert "checkout" in content.lower(), "Checkout endpoint not found"

    def test_portal_endpoint_exists(self):
        """Portal endpoint should exist."""
        path = os.path.join(BACKEND_ROOT, "apps/billing/api/views.py")
        with open(path, 'r') as f:
            content = f.read()
        assert "portal" in content.lower(), "Portal endpoint not found"


class TestSettingsUpdated:
    """Test that settings were updated for billing."""

    def test_billing_app_in_installed_apps(self):
        """billing app should be in INSTALLED_APPS."""
        path = os.path.join(BACKEND_ROOT, "config/settings/base.py")
        with open(path, 'r') as f:
            content = f.read()
        assert "billing" in content, "billing app not in INSTALLED_APPS"

    def test_stripe_settings_exist(self):
        """Stripe settings should exist."""
        path = os.path.join(BACKEND_ROOT, "config/settings/base.py")
        with open(path, 'r') as f:
            content = f.read()
        assert "STRIPE" in content, "Stripe settings not found"


class TestRequirementsUpdated:
    """Test that requirements include stripe."""

    def test_stripe_in_requirements(self):
        """stripe should be in requirements."""
        path = os.path.join(BACKEND_ROOT, "requirements/base.txt")
        with open(path, 'r') as f:
            content = f.read()
        assert "stripe" in content.lower(), "stripe not in requirements"


class TestAPIRouterUpdated:
    """Test that API router includes billing."""

    def test_billing_in_router(self):
        """Billing ViewSets should be in router."""
        path = os.path.join(BACKEND_ROOT, "config/api_router.py")
        with open(path, 'r') as f:
            content = f.read()
        has_billing = "billing" in content.lower() or "plan" in content.lower() or "subscription" in content.lower()
        assert has_billing, "Billing not registered in router"
