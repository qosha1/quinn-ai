"""
Tests to validate landing-page implementation.

These tests verify that all required files from the add-landing-page
OpenSpec change have been created correctly.
"""

import os
import pytest

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LANDING_ROOT = os.path.join(PROJECT_ROOT, "landing")


class TestProjectSetup:
    """Test project setup files."""

    def test_package_json_exists(self):
        """package.json should exist."""
        path = os.path.join(LANDING_ROOT, "package.json")
        assert os.path.exists(path), "package.json not found"

    def test_package_json_has_nextjs(self):
        """package.json should include Next.js."""
        path = os.path.join(LANDING_ROOT, "package.json")
        with open(path, 'r') as f:
            content = f.read()
        assert "next" in content.lower(), "Next.js not in package.json"

    def test_tailwind_config_exists(self):
        """tailwind.config.ts should exist."""
        path = os.path.join(LANDING_ROOT, "tailwind.config.ts")
        assert os.path.exists(path), "tailwind.config.ts not found"

    def test_next_config_exists(self):
        """next.config.mjs should exist."""
        path = os.path.join(LANDING_ROOT, "next.config.mjs")
        assert os.path.exists(path), "next.config.mjs not found"

    def test_components_json_exists(self):
        """components.json should exist."""
        path = os.path.join(LANDING_ROOT, "components.json")
        assert os.path.exists(path), "components.json not found"

    def test_utils_exists(self):
        """lib/utils.ts should exist."""
        path = os.path.join(LANDING_ROOT, "lib/utils.ts")
        assert os.path.exists(path), "lib/utils.ts not found"

    def test_utils_has_cn_helper(self):
        """utils.ts should have cn() helper."""
        path = os.path.join(LANDING_ROOT, "lib/utils.ts")
        with open(path, 'r') as f:
            content = f.read()
        assert "cn" in content, "cn() helper not found in utils.ts"

    def test_tsconfig_exists(self):
        """tsconfig.json should exist."""
        path = os.path.join(LANDING_ROOT, "tsconfig.json")
        assert os.path.exists(path), "tsconfig.json not found"

    def test_postcss_config_exists(self):
        """postcss.config.mjs should exist."""
        path = os.path.join(LANDING_ROOT, "postcss.config.mjs")
        assert os.path.exists(path), "postcss.config.mjs not found"


class TestCoreUIComponents:
    """Test core UI components."""

    def test_button_component_exists(self):
        """components/ui/button.tsx should exist."""
        path = os.path.join(LANDING_ROOT, "components/ui/button.tsx")
        assert os.path.exists(path), "button.tsx not found"

    def test_button_has_variants(self):
        """Button should have variants."""
        path = os.path.join(LANDING_ROOT, "components/ui/button.tsx")
        with open(path, 'r') as f:
            content = f.read()
        assert "variant" in content.lower(), "Button variants not found"

    def test_card_component_exists(self):
        """components/ui/card.tsx should exist."""
        path = os.path.join(LANDING_ROOT, "components/ui/card.tsx")
        assert os.path.exists(path), "card.tsx not found"

    def test_card_has_subcomponents(self):
        """Card should have subcomponents."""
        path = os.path.join(LANDING_ROOT, "components/ui/card.tsx")
        with open(path, 'r') as f:
            content = f.read()
        assert "CardHeader" in content, "CardHeader not found"
        assert "CardContent" in content, "CardContent not found"

    def test_badge_component_exists(self):
        """components/ui/badge.tsx should exist."""
        path = os.path.join(LANDING_ROOT, "components/ui/badge.tsx")
        assert os.path.exists(path), "badge.tsx not found"

    def test_input_component_exists(self):
        """components/ui/input.tsx should exist."""
        path = os.path.join(LANDING_ROOT, "components/ui/input.tsx")
        assert os.path.exists(path), "input.tsx not found"

    def test_theme_provider_exists(self):
        """components/theme-provider.tsx should exist."""
        path = os.path.join(LANDING_ROOT, "components/theme-provider.tsx")
        assert os.path.exists(path), "theme-provider.tsx not found"


class TestLayoutComponents:
    """Test layout components."""

    def test_header_component_exists(self):
        """components/header.tsx should exist."""
        path = os.path.join(LANDING_ROOT, "components/header.tsx")
        assert os.path.exists(path), "header.tsx not found"

    def test_header_has_navigation(self):
        """Header should have navigation."""
        path = os.path.join(LANDING_ROOT, "components/header.tsx")
        with open(path, 'r') as f:
            content = f.read()
        has_nav = "nav" in content.lower() or "menu" in content.lower() or "link" in content.lower()
        assert has_nav, "Navigation not found in header"

    def test_footer_component_exists(self):
        """components/footer.tsx should exist."""
        path = os.path.join(LANDING_ROOT, "components/footer.tsx")
        assert os.path.exists(path), "footer.tsx not found"

    def test_layout_exists(self):
        """app/layout.tsx should exist."""
        path = os.path.join(LANDING_ROOT, "app/layout.tsx")
        assert os.path.exists(path), "app/layout.tsx not found"

    def test_layout_has_metadata(self):
        """Layout should have metadata."""
        path = os.path.join(LANDING_ROOT, "app/layout.tsx")
        with open(path, 'r') as f:
            content = f.read()
        assert "metadata" in content.lower(), "Metadata not found in layout"

    def test_globals_css_exists(self):
        """app/globals.css should exist."""
        path = os.path.join(LANDING_ROOT, "app/globals.css")
        assert os.path.exists(path), "app/globals.css not found"


class TestLandingSections:
    """Test landing page sections."""

    def test_hero_section_exists(self):
        """components/sections/hero.tsx should exist."""
        path = os.path.join(LANDING_ROOT, "components/sections/hero.tsx")
        assert os.path.exists(path), "hero.tsx not found"

    def test_features_section_exists(self):
        """components/sections/features.tsx should exist."""
        path = os.path.join(LANDING_ROOT, "components/sections/features.tsx")
        assert os.path.exists(path), "features.tsx not found"

    def test_pricing_section_exists(self):
        """components/sections/pricing.tsx should exist."""
        path = os.path.join(LANDING_ROOT, "components/sections/pricing.tsx")
        assert os.path.exists(path), "pricing.tsx not found"

    def test_pricing_has_tiers(self):
        """Pricing should have multiple tiers."""
        path = os.path.join(LANDING_ROOT, "components/sections/pricing.tsx")
        with open(path, 'r') as f:
            content = f.read()
        has_tiers = "free" in content.lower() or "pro" in content.lower() or "enterprise" in content.lower()
        assert has_tiers, "Pricing tiers not found"

    def test_testimonials_section_exists(self):
        """components/sections/testimonials.tsx should exist."""
        path = os.path.join(LANDING_ROOT, "components/sections/testimonials.tsx")
        assert os.path.exists(path), "testimonials.tsx not found"

    def test_faq_section_exists(self):
        """components/sections/faq.tsx should exist."""
        path = os.path.join(LANDING_ROOT, "components/sections/faq.tsx")
        assert os.path.exists(path), "faq.tsx not found"

    def test_cta_section_exists(self):
        """components/sections/cta.tsx should exist."""
        path = os.path.join(LANDING_ROOT, "components/sections/cta.tsx")
        assert os.path.exists(path), "cta.tsx not found"


class TestPages:
    """Test landing pages."""

    def test_home_page_exists(self):
        """app/page.tsx should exist."""
        path = os.path.join(LANDING_ROOT, "app/page.tsx")
        assert os.path.exists(path), "app/page.tsx not found"

    def test_home_page_has_sections(self):
        """Home page should compose sections."""
        path = os.path.join(LANDING_ROOT, "app/page.tsx")
        with open(path, 'r') as f:
            content = f.read()
        has_hero = "hero" in content.lower()
        has_features = "features" in content.lower()
        has_pricing = "pricing" in content.lower()
        assert has_hero or has_features or has_pricing, "Sections not found in home page"

    def test_pricing_page_exists(self):
        """app/pricing/page.tsx should exist."""
        path = os.path.join(LANDING_ROOT, "app/pricing/page.tsx")
        assert os.path.exists(path), "app/pricing/page.tsx not found"

    def test_privacy_policy_page_exists(self):
        """app/privacy-policy/page.tsx should exist."""
        path = os.path.join(LANDING_ROOT, "app/privacy-policy/page.tsx")
        assert os.path.exists(path), "app/privacy-policy/page.tsx not found"

    def test_terms_of_service_page_exists(self):
        """app/terms-of-service/page.tsx should exist."""
        path = os.path.join(LANDING_ROOT, "app/terms-of-service/page.tsx")
        assert os.path.exists(path), "app/terms-of-service/page.tsx not found"


class TestSEO:
    """Test SEO files."""

    def test_robots_exists(self):
        """app/robots.ts should exist."""
        path = os.path.join(LANDING_ROOT, "app/robots.ts")
        assert os.path.exists(path), "app/robots.ts not found"

    def test_sitemap_exists(self):
        """app/sitemap.ts should exist."""
        path = os.path.join(LANDING_ROOT, "app/sitemap.ts")
        assert os.path.exists(path), "app/sitemap.ts not found"

    def test_layout_has_structured_data(self):
        """Layout should have JSON-LD structured data."""
        path = os.path.join(LANDING_ROOT, "app/layout.tsx")
        with open(path, 'r') as f:
            content = f.read()
        has_jsonld = "json-ld" in content.lower() or "ld+json" in content.lower() or "schema" in content.lower()
        assert has_jsonld, "JSON-LD structured data not found"


class TestDarkMode:
    """Test dark mode support."""

    def test_theme_provider_has_next_themes(self):
        """Theme provider should use next-themes."""
        path = os.path.join(LANDING_ROOT, "components/theme-provider.tsx")
        with open(path, 'r') as f:
            content = f.read()
        assert "next-themes" in content or "ThemeProvider" in content, "next-themes not found"

    def test_globals_css_has_dark_mode(self):
        """globals.css should have dark mode variables."""
        path = os.path.join(LANDING_ROOT, "app/globals.css")
        with open(path, 'r') as f:
            content = f.read()
        assert ".dark" in content or "dark:" in content, "Dark mode styles not found"


class TestTailwindConfig:
    """Test Tailwind configuration."""

    def test_tailwind_has_css_variables(self):
        """Tailwind config should use CSS variables."""
        path = os.path.join(LANDING_ROOT, "tailwind.config.ts")
        with open(path, 'r') as f:
            content = f.read()
        has_vars = "var(--" in content or "hsl" in content.lower()
        assert has_vars, "CSS variables not found in Tailwind config"
