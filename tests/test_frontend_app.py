"""
Tests to validate frontend-app implementation.

These tests verify that all required files from the add-frontend-app
OpenSpec change have been created correctly.
"""

import os
import pytest

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP_ROOT = os.path.join(PROJECT_ROOT, "app")


class TestProjectSetup:
    """Test project setup files."""

    def test_package_json_exists(self):
        """package.json should exist."""
        path = os.path.join(APP_ROOT, "package.json")
        assert os.path.exists(path), "package.json not found"

    def test_package_json_has_nextjs(self):
        """package.json should include Next.js."""
        path = os.path.join(APP_ROOT, "package.json")
        with open(path, 'r') as f:
            content = f.read()
        assert "next" in content.lower(), "Next.js not in package.json"

    def test_package_json_has_zustand(self):
        """package.json should include Zustand."""
        path = os.path.join(APP_ROOT, "package.json")
        with open(path, 'r') as f:
            content = f.read()
        assert "zustand" in content.lower(), "Zustand not in package.json"

    def test_tailwind_config_exists(self):
        """tailwind.config.ts should exist."""
        path = os.path.join(APP_ROOT, "tailwind.config.ts")
        assert os.path.exists(path), "tailwind.config.ts not found"

    def test_next_config_exists(self):
        """next.config.mjs should exist."""
        path = os.path.join(APP_ROOT, "next.config.mjs")
        assert os.path.exists(path), "next.config.mjs not found"

    def test_tsconfig_exists(self):
        """tsconfig.json should exist."""
        path = os.path.join(APP_ROOT, "tsconfig.json")
        assert os.path.exists(path), "tsconfig.json not found"

    def test_components_json_exists(self):
        """components.json should exist."""
        path = os.path.join(APP_ROOT, "components.json")
        assert os.path.exists(path), "components.json not found"


class TestLibraryFiles:
    """Test library files."""

    def test_api_client_exists(self):
        """lib/api.ts should exist."""
        path = os.path.join(APP_ROOT, "lib/api.ts")
        assert os.path.exists(path), "lib/api.ts not found"

    def test_api_client_has_interceptors(self):
        """API client should have interceptors."""
        path = os.path.join(APP_ROOT, "lib/api.ts")
        with open(path, 'r') as f:
            content = f.read()
        has_interceptor = "interceptor" in content.lower() or "authorization" in content.lower()
        assert has_interceptor, "API interceptors not found"

    def test_auth_utils_exists(self):
        """lib/auth.ts should exist."""
        path = os.path.join(APP_ROOT, "lib/auth.ts")
        assert os.path.exists(path), "lib/auth.ts not found"

    def test_auth_utils_has_token_functions(self):
        """Auth utils should have token functions."""
        path = os.path.join(APP_ROOT, "lib/auth.ts")
        with open(path, 'r') as f:
            content = f.read()
        has_token = "token" in content.lower()
        assert has_token, "Token functions not found"

    def test_utils_exists(self):
        """lib/utils.ts should exist."""
        path = os.path.join(APP_ROOT, "lib/utils.ts")
        assert os.path.exists(path), "lib/utils.ts not found"

    def test_stripe_utils_exists(self):
        """lib/stripe.ts should exist."""
        path = os.path.join(APP_ROOT, "lib/stripe.ts")
        assert os.path.exists(path), "lib/stripe.ts not found"


class TestAuthStore:
    """Test Zustand auth store."""

    def test_auth_store_exists(self):
        """stores/auth-store.ts should exist."""
        path = os.path.join(APP_ROOT, "stores/auth-store.ts")
        assert os.path.exists(path), "stores/auth-store.ts not found"

    def test_auth_store_uses_zustand(self):
        """Auth store should use Zustand."""
        path = os.path.join(APP_ROOT, "stores/auth-store.ts")
        with open(path, 'r') as f:
            content = f.read()
        assert "zustand" in content.lower() or "create" in content, "Zustand not used in auth store"


class TestAuthPages:
    """Test authentication pages."""

    def test_auth_layout_exists(self):
        """app/(auth)/layout.tsx should exist."""
        path = os.path.join(APP_ROOT, "app/(auth)/layout.tsx")
        assert os.path.exists(path), "Auth layout not found"

    def test_login_page_exists(self):
        """app/(auth)/login/page.tsx should exist."""
        path = os.path.join(APP_ROOT, "app/(auth)/login/page.tsx")
        assert os.path.exists(path), "Login page not found"

    def test_register_page_exists(self):
        """app/(auth)/register/page.tsx should exist."""
        path = os.path.join(APP_ROOT, "app/(auth)/register/page.tsx")
        assert os.path.exists(path), "Register page not found"

    def test_forgot_password_page_exists(self):
        """app/(auth)/forgot-password/page.tsx should exist."""
        path = os.path.join(APP_ROOT, "app/(auth)/forgot-password/page.tsx")
        assert os.path.exists(path), "Forgot password page not found"


class TestMiddleware:
    """Test middleware."""

    def test_middleware_exists(self):
        """middleware.ts should exist."""
        path = os.path.join(APP_ROOT, "middleware.ts")
        assert os.path.exists(path), "middleware.ts not found"

    def test_middleware_protects_routes(self):
        """Middleware should protect dashboard routes."""
        path = os.path.join(APP_ROOT, "middleware.ts")
        with open(path, 'r') as f:
            content = f.read()
        has_protection = "dashboard" in content.lower() or "matcher" in content.lower()
        assert has_protection, "Route protection not found in middleware"


class TestDashboardLayout:
    """Test dashboard layout."""

    def test_dashboard_layout_exists(self):
        """app/(dashboard)/layout.tsx should exist."""
        path = os.path.join(APP_ROOT, "app/(dashboard)/layout.tsx")
        assert os.path.exists(path), "Dashboard layout not found"

    def test_dashboard_page_exists(self):
        """app/(dashboard)/page.tsx should exist."""
        path = os.path.join(APP_ROOT, "app/(dashboard)/page.tsx")
        assert os.path.exists(path), "Dashboard page not found"

    def test_sidebar_exists(self):
        """components/sidebar.tsx should exist."""
        path = os.path.join(APP_ROOT, "components/sidebar.tsx")
        assert os.path.exists(path), "Sidebar not found"

    def test_header_exists(self):
        """components/dashboard-header.tsx should exist."""
        path = os.path.join(APP_ROOT, "components/dashboard-header.tsx")
        assert os.path.exists(path), "Dashboard header not found"


class TestTeamPages:
    """Test team management pages."""

    def test_team_page_exists(self):
        """app/(dashboard)/team/page.tsx should exist."""
        path = os.path.join(APP_ROOT, "app/(dashboard)/team/page.tsx")
        assert os.path.exists(path), "Team page not found"

    def test_team_members_page_exists(self):
        """app/(dashboard)/team/members/page.tsx should exist."""
        path = os.path.join(APP_ROOT, "app/(dashboard)/team/members/page.tsx")
        assert os.path.exists(path), "Team members page not found"

    def test_team_invitations_page_exists(self):
        """app/(dashboard)/team/invitations/page.tsx should exist."""
        path = os.path.join(APP_ROOT, "app/(dashboard)/team/invitations/page.tsx")
        assert os.path.exists(path), "Team invitations page not found"

    def test_team_settings_page_exists(self):
        """app/(dashboard)/team/settings/page.tsx should exist."""
        path = os.path.join(APP_ROOT, "app/(dashboard)/team/settings/page.tsx")
        assert os.path.exists(path), "Team settings page not found"


class TestBillingPages:
    """Test billing pages."""

    def test_billing_page_exists(self):
        """app/(dashboard)/billing/page.tsx should exist."""
        path = os.path.join(APP_ROOT, "app/(dashboard)/billing/page.tsx")
        assert os.path.exists(path), "Billing page not found"

    def test_billing_plans_page_exists(self):
        """app/(dashboard)/billing/plans/page.tsx should exist."""
        path = os.path.join(APP_ROOT, "app/(dashboard)/billing/plans/page.tsx")
        assert os.path.exists(path), "Billing plans page not found"

    def test_billing_invoices_page_exists(self):
        """app/(dashboard)/billing/invoices/page.tsx should exist."""
        path = os.path.join(APP_ROOT, "app/(dashboard)/billing/invoices/page.tsx")
        assert os.path.exists(path), "Billing invoices page not found"


class TestSettingsPages:
    """Test settings pages."""

    def test_settings_page_exists(self):
        """app/(dashboard)/settings/page.tsx should exist."""
        path = os.path.join(APP_ROOT, "app/(dashboard)/settings/page.tsx")
        assert os.path.exists(path), "Settings page not found"

    def test_settings_profile_page_exists(self):
        """app/(dashboard)/settings/profile/page.tsx should exist."""
        path = os.path.join(APP_ROOT, "app/(dashboard)/settings/profile/page.tsx")
        assert os.path.exists(path), "Profile settings page not found"

    def test_settings_security_page_exists(self):
        """app/(dashboard)/settings/security/page.tsx should exist."""
        path = os.path.join(APP_ROOT, "app/(dashboard)/settings/security/page.tsx")
        assert os.path.exists(path), "Security settings page not found"

    def test_settings_api_keys_page_exists(self):
        """app/(dashboard)/settings/api-keys/page.tsx should exist."""
        path = os.path.join(APP_ROOT, "app/(dashboard)/settings/api-keys/page.tsx")
        assert os.path.exists(path), "API keys page not found"


class TestUIComponents:
    """Test UI components."""

    def test_button_component_exists(self):
        """components/ui/button.tsx should exist."""
        path = os.path.join(APP_ROOT, "components/ui/button.tsx")
        assert os.path.exists(path), "Button component not found"

    def test_card_component_exists(self):
        """components/ui/card.tsx should exist."""
        path = os.path.join(APP_ROOT, "components/ui/card.tsx")
        assert os.path.exists(path), "Card component not found"

    def test_input_component_exists(self):
        """components/ui/input.tsx should exist."""
        path = os.path.join(APP_ROOT, "components/ui/input.tsx")
        assert os.path.exists(path), "Input component not found"

    def test_badge_component_exists(self):
        """components/ui/badge.tsx should exist."""
        path = os.path.join(APP_ROOT, "components/ui/badge.tsx")
        assert os.path.exists(path), "Badge component not found"

    def test_table_component_exists(self):
        """components/ui/table.tsx should exist."""
        path = os.path.join(APP_ROOT, "components/ui/table.tsx")
        assert os.path.exists(path), "Table component not found"

    def test_dialog_component_exists(self):
        """components/ui/dialog.tsx should exist."""
        path = os.path.join(APP_ROOT, "components/ui/dialog.tsx")
        assert os.path.exists(path), "Dialog component not found"

    def test_theme_provider_exists(self):
        """components/theme-provider.tsx should exist."""
        path = os.path.join(APP_ROOT, "components/theme-provider.tsx")
        assert os.path.exists(path), "Theme provider not found"


class TestRootLayout:
    """Test root layout."""

    def test_root_layout_exists(self):
        """app/layout.tsx should exist."""
        path = os.path.join(APP_ROOT, "app/layout.tsx")
        assert os.path.exists(path), "Root layout not found"

    def test_globals_css_exists(self):
        """app/globals.css should exist."""
        path = os.path.join(APP_ROOT, "app/globals.css")
        assert os.path.exists(path), "globals.css not found"
