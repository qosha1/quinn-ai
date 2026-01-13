"""
Management command to create sample billing plans.

Usage:
    python manage.py create_sample_plans
"""

from decimal import Decimal
from django.core.management.base import BaseCommand
from django.db import transaction

from apps.billing.models import Plan, UsageType, UsageLimit


class Command(BaseCommand):
    """Create sample billing plans for testing."""

    help = "Create sample billing plans with usage types and limits"

    def handle(self, *args, **options):
        """Execute the command."""
        self.stdout.write("Creating sample billing plans...")

        with transaction.atomic():
            # Create usage types
            api_calls = self._create_usage_type(
                name="API Calls",
                slug="api_calls",
                unit="calls",
                description="Number of API calls made per month",
            )

            storage = self._create_usage_type(
                name="Storage",
                slug="storage_gb",
                unit="GB",
                description="Storage space in gigabytes",
            )

            seats = self._create_usage_type(
                name="Team Seats",
                slug="seats",
                unit="seats",
                description="Number of team member seats",
            )

            # Create Starter plan
            starter = self._create_plan(
                name="Starter",
                slug="starter",
                price=Decimal("29.00"),
                interval="month",
                features=[
                    "Basic API access",
                    "Email support",
                    "Standard analytics",
                    "Single workspace",
                ],
                limits={
                    "features": ["basic_api", "email_support", "standard_analytics"],
                    "workspaces": 1,
                },
                sort_order=1,
            )

            # Starter usage limits
            self._create_usage_limit(starter, api_calls, 1000, False, None)
            self._create_usage_limit(starter, storage, 10, False, None)
            self._create_usage_limit(starter, seats, 3, False, None)

            # Create Professional plan
            professional = self._create_plan(
                name="Professional",
                slug="professional",
                price=Decimal("99.00"),
                interval="month",
                features=[
                    "Advanced API access",
                    "Priority email support",
                    "Advanced analytics",
                    "Multiple workspaces",
                    "Custom integrations",
                ],
                limits={
                    "features": [
                        "advanced_api",
                        "priority_support",
                        "advanced_analytics",
                        "custom_integrations",
                    ],
                    "workspaces": 5,
                },
                sort_order=2,
            )

            # Professional usage limits
            self._create_usage_limit(professional, api_calls, 10000, True, Decimal("0.01"))
            self._create_usage_limit(professional, storage, 100, True, Decimal("1.00"))
            self._create_usage_limit(professional, seats, 10, False, None)

            # Create Enterprise plan
            enterprise = self._create_plan(
                name="Enterprise",
                slug="enterprise",
                price=Decimal("299.00"),
                interval="month",
                features=[
                    "Unlimited API access",
                    "24/7 phone & email support",
                    "Custom analytics",
                    "Unlimited workspaces",
                    "Advanced integrations",
                    "Dedicated account manager",
                    "SLA guarantees",
                ],
                limits={
                    "features": [
                        "unlimited_api",
                        "premium_support",
                        "custom_analytics",
                        "advanced_integrations",
                        "account_manager",
                        "sla",
                    ],
                    "workspaces": 999,
                },
                sort_order=3,
            )

            # Enterprise usage limits
            self._create_usage_limit(enterprise, api_calls, 100000, True, Decimal("0.005"))
            self._create_usage_limit(enterprise, storage, 1000, True, Decimal("0.50"))
            self._create_usage_limit(enterprise, seats, 50, True, Decimal("10.00"))

            # Create annual variants
            starter_annual = self._create_plan(
                name="Starter (Annual)",
                slug="starter-annual",
                price=Decimal("290.00"),
                interval="year",
                features=starter.features,
                limits=starter.limits,
                sort_order=4,
            )
            self._create_usage_limit(starter_annual, api_calls, 1000, False, None)
            self._create_usage_limit(starter_annual, storage, 10, False, None)
            self._create_usage_limit(starter_annual, seats, 3, False, None)

            professional_annual = self._create_plan(
                name="Professional (Annual)",
                slug="professional-annual",
                price=Decimal("990.00"),
                interval="year",
                features=professional.features,
                limits=professional.limits,
                sort_order=5,
            )
            self._create_usage_limit(professional_annual, api_calls, 10000, True, Decimal("0.01"))
            self._create_usage_limit(professional_annual, storage, 100, True, Decimal("1.00"))
            self._create_usage_limit(professional_annual, seats, 10, False, None)

        self.stdout.write(
            self.style.SUCCESS("Successfully created sample billing plans!")
        )
        self.stdout.write("\nCreated plans:")
        self.stdout.write("  - Starter ($29/month)")
        self.stdout.write("  - Professional ($99/month)")
        self.stdout.write("  - Enterprise ($299/month)")
        self.stdout.write("  - Starter Annual ($290/year)")
        self.stdout.write("  - Professional Annual ($990/year)")
        self.stdout.write("\nCreated usage types:")
        self.stdout.write("  - API Calls")
        self.stdout.write("  - Storage (GB)")
        self.stdout.write("  - Team Seats")
        self.stdout.write(
            self.style.WARNING(
                "\nWARNING: Remember to set stripe_price_id for each plan "
                "after creating prices in Stripe Dashboard!"
            )
        )

    def _create_usage_type(self, name, slug, unit, description):
        """Create or get usage type."""
        usage_type, created = UsageType.objects.get_or_create(
            slug=slug,
            defaults={
                "name": name,
                "unit": unit,
                "description": description,
            }
        )
        if created:
            self.stdout.write(f"  Created usage type: {name}")
        else:
            self.stdout.write(f"  Usage type already exists: {name}")
        return usage_type

    def _create_plan(self, name, slug, price, interval, features, limits, sort_order):
        """Create or get plan."""
        plan, created = Plan.objects.get_or_create(
            slug=slug,
            defaults={
                "name": name,
                "stripe_price_id": f"price_{slug}_placeholder",
                "price": price,
                "interval": interval,
                "features": features,
                "limits": limits,
                "is_active": True,
                "sort_order": sort_order,
            }
        )
        if created:
            self.stdout.write(f"  Created plan: {name}")
        else:
            self.stdout.write(f"  Plan already exists: {name}")
        return plan

    def _create_usage_limit(self, plan, usage_type, limit_value, overage_allowed, overage_price):
        """Create or get usage limit."""
        limit, created = UsageLimit.objects.get_or_create(
            plan=plan,
            usage_type=usage_type,
            defaults={
                "limit_value": limit_value,
                "overage_allowed": overage_allowed,
                "overage_price": overage_price,
            }
        )
        if created:
            self.stdout.write(
                f"    Created limit: {plan.name} - {usage_type.name} ({limit_value})"
            )
        return limit
