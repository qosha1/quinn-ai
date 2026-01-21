"""
Business logic services for usage tracking and billing operations.
"""

import logging
from datetime import datetime
from decimal import Decimal
from typing import Optional, Dict, Any

from django.db import transaction
from django.db.models import Sum, Q
from django.utils import timezone

from apps.teams.models import Company
from apps.billing.models import (
    UsageRecord,
    UsageType,
    UsageLimit,
    Plan,
)

logger = logging.getLogger(__name__)


class UsageService:
    """
    Service for tracking and managing company usage.

    Handles recording usage, checking limits, and calculating remaining quotas.
    """

    @staticmethod
    @transaction.atomic
    def record_usage(
        company: Company,
        usage_type_slug: str,
        quantity: Decimal = Decimal("1.00"),
        metadata: Optional[Dict[str, Any]] = None,
    ) -> UsageRecord:
        """
        Record usage for a company.

        Args:
            company: Company incurring the usage
            usage_type_slug: Slug identifier for the usage type
            quantity: Amount of usage to record
            metadata: Optional additional metadata

        Returns:
            Created UsageRecord instance

        Raises:
            UsageType.DoesNotExist: If usage type not found
            ValueError: If company has no subscription or quota exceeded
        """
        try:
            usage_type = UsageType.objects.get(slug=usage_type_slug)
        except UsageType.DoesNotExist:
            logger.error(f"Usage type '{usage_type_slug}' not found")
            raise

        # Check if company has an active subscription
        if not hasattr(company, 'subscription') or not company.subscription.is_active:
            raise ValueError(f"Company {company.id} has no active subscription")

        # Get current billing period from subscription
        subscription = company.subscription
        billing_period_start = subscription.current_period_start
        billing_period_end = subscription.current_period_end

        # Check if usage would exceed limit
        if not UsageService.check_limit(company, usage_type_slug, quantity):
            current_usage = UsageService.get_usage(
                company,
                usage_type_slug,
                billing_period_start,
                billing_period_end
            )
            limit = UsageService.get_limit(company, usage_type_slug)
            raise ValueError(
                f"Usage would exceed limit. Current: {current_usage}, "
                f"Limit: {limit}, Attempted: {quantity}"
            )

        # Create usage record
        usage_record = UsageRecord.objects.create(
            company=company,
            usage_type=usage_type,
            quantity=quantity,
            billing_period_start=billing_period_start,
            billing_period_end=billing_period_end,
            metadata=metadata or {},
        )

        logger.info(
            f"Recorded {quantity} {usage_type.unit} usage for company {company.id}"
        )

        return usage_record

    @staticmethod
    def get_usage(
        company: Company,
        usage_type_slug: str,
        period_start: datetime,
        period_end: datetime,
    ) -> Decimal:
        """
        Get total usage for a company within a period.

        Args:
            company: Company to get usage for
            usage_type_slug: Slug identifier for the usage type
            period_start: Start of period
            period_end: End of period

        Returns:
            Total usage quantity

        Raises:
            UsageType.DoesNotExist: If usage type not found
        """
        try:
            usage_type = UsageType.objects.get(slug=usage_type_slug)
        except UsageType.DoesNotExist:
            logger.error(f"Usage type '{usage_type_slug}' not found")
            raise

        total = UsageRecord.objects.filter(
            company=company,
            usage_type=usage_type,
            recorded_at__gte=period_start,
            recorded_at__lt=period_end,
        ).aggregate(
            total=Sum('quantity')
        )['total']

        return total or Decimal("0.00")

    @staticmethod
    def get_current_usage(company: Company, usage_type_slug: str) -> Decimal:
        """
        Get usage for the current billing period.

        Args:
            company: Company to get usage for
            usage_type_slug: Slug identifier for the usage type

        Returns:
            Total usage quantity for current period

        Raises:
            ValueError: If company has no subscription
        """
        if not hasattr(company, 'subscription'):
            raise ValueError(f"Company {company.id} has no subscription")

        subscription = company.subscription
        return UsageService.get_usage(
            company,
            usage_type_slug,
            subscription.current_period_start,
            subscription.current_period_end,
        )

    @staticmethod
    def get_limit(company: Company, usage_type_slug: str) -> Optional[Decimal]:
        """
        Get usage limit for a company based on their plan.

        Args:
            company: Company to get limit for
            usage_type_slug: Slug identifier for the usage type

        Returns:
            Limit value or None if no limit exists

        Raises:
            ValueError: If company has no subscription
        """
        if not hasattr(company, 'subscription'):
            raise ValueError(f"Company {company.id} has no subscription")

        try:
            usage_type = UsageType.objects.get(slug=usage_type_slug)
        except UsageType.DoesNotExist:
            logger.error(f"Usage type '{usage_type_slug}' not found")
            return None

        try:
            limit = UsageLimit.objects.get(
                plan=company.subscription.plan,
                usage_type=usage_type,
            )
            return limit.limit_value
        except UsageLimit.DoesNotExist:
            # No limit defined for this usage type on this plan
            return None

    @staticmethod
    def check_limit(
        company: Company,
        usage_type_slug: str,
        additional_quantity: Decimal = Decimal("0.00"),
    ) -> bool:
        """
        Check if company is within usage limits.

        Args:
            company: Company to check
            usage_type_slug: Slug identifier for the usage type
            additional_quantity: Additional usage to check (for pre-validation)

        Returns:
            True if within limits or no limit exists, False otherwise

        Raises:
            ValueError: If company has no subscription
        """
        if not hasattr(company, 'subscription'):
            raise ValueError(f"Company {company.id} has no subscription")

        limit = UsageService.get_limit(company, usage_type_slug)

        # No limit means unlimited
        if limit is None:
            return True

        # Check if overage is allowed
        try:
            usage_type = UsageType.objects.get(slug=usage_type_slug)
            usage_limit = UsageLimit.objects.get(
                plan=company.subscription.plan,
                usage_type=usage_type,
            )
            if usage_limit.overage_allowed:
                return True
        except (UsageType.DoesNotExist, UsageLimit.DoesNotExist):
            # No limit config found - proceed to standard limit check below
            logger.debug(f"No overage config for {usage_type_slug}, checking standard limit")

        # Check current usage
        current_usage = UsageService.get_current_usage(company, usage_type_slug)
        total_usage = current_usage + additional_quantity

        return total_usage <= limit

    @staticmethod
    def get_remaining(company: Company, usage_type_slug: str) -> Optional[Decimal]:
        """
        Get remaining usage quota for current period.

        Args:
            company: Company to check
            usage_type_slug: Slug identifier for the usage type

        Returns:
            Remaining quota or None if unlimited

        Raises:
            ValueError: If company has no subscription
        """
        if not hasattr(company, 'subscription'):
            raise ValueError(f"Company {company.id} has no subscription")

        limit = UsageService.get_limit(company, usage_type_slug)

        # No limit means unlimited
        if limit is None:
            return None

        current_usage = UsageService.get_current_usage(company, usage_type_slug)
        remaining = limit - current_usage

        return max(remaining, Decimal("0.00"))

    @staticmethod
    def get_usage_summary(company: Company) -> Dict[str, Dict[str, Any]]:
        """
        Get usage summary for all usage types for current period.

        Args:
            company: Company to get summary for

        Returns:
            Dictionary mapping usage type slugs to usage data

        Raises:
            ValueError: If company has no subscription
        """
        if not hasattr(company, 'subscription'):
            raise ValueError(f"Company {company.id} has no subscription")

        summary = {}

        # Get all usage types that have limits on this plan
        usage_limits = UsageLimit.objects.filter(
            plan=company.subscription.plan
        ).select_related('usage_type')

        for usage_limit in usage_limits:
            usage_type = usage_limit.usage_type
            current_usage = UsageService.get_current_usage(company, usage_type.slug)
            remaining = UsageService.get_remaining(company, usage_type.slug)

            summary[usage_type.slug] = {
                "name": usage_type.name,
                "unit": usage_type.unit,
                "current": float(current_usage),
                "limit": float(usage_limit.limit_value),
                "remaining": float(remaining) if remaining is not None else None,
                "overage_allowed": usage_limit.overage_allowed,
                "overage_price": (
                    float(usage_limit.overage_price)
                    if usage_limit.overage_price else None
                ),
            }

        return summary


class CompanyBillingMixin:
    """
    Mixin to add billing-related methods to Company model.

    Note: Add this to Company model or create these as standalone functions.
    """

    @staticmethod
    def can_use_feature(company: Company, feature_slug: str) -> bool:
        """
        Check if company can use a specific feature based on their plan.

        Args:
            company: Company to check
            feature_slug: Feature identifier to check

        Returns:
            True if company can use the feature, False otherwise
        """
        # If no subscription, deny access
        if not hasattr(company, 'subscription'):
            return False

        # If subscription is not active, deny access
        if not company.subscription.is_active:
            return False

        # Check if feature is in plan's features list
        plan = company.subscription.plan
        features = plan.limits.get('features', [])

        return feature_slug in features

    @staticmethod
    def get_plan_features(company: Company) -> list:
        """
        Get list of features available on company's current plan.

        Args:
            company: Company to get features for

        Returns:
            List of feature names
        """
        if not hasattr(company, 'subscription'):
            return []

        return company.subscription.plan.features
