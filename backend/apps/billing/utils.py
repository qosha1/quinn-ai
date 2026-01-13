"""
Utility functions for billing operations.
"""

from typing import Optional

from apps.teams.models import Company


def can_use_feature(company: Company, feature_slug: str) -> bool:
    """
    Check if company can use a specific feature based on their plan.

    Args:
        company: Company to check
        feature_slug: Feature identifier to check

    Returns:
        True if company can use the feature, False otherwise

    Example:
        >>> company = Company.objects.get(slug='acme-corp')
        >>> can_use_feature(company, 'advanced_analytics')
        True
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


def get_plan_features(company: Company) -> list:
    """
    Get list of features available on company's current plan.

    Args:
        company: Company to get features for

    Returns:
        List of feature names

    Example:
        >>> company = Company.objects.get(slug='acme-corp')
        >>> get_plan_features(company)
        ['feature1', 'feature2', 'feature3']
    """
    if not hasattr(company, 'subscription'):
        return []

    return company.subscription.plan.features


def get_subscription_status(company: Company) -> Optional[str]:
    """
    Get subscription status for a company.

    Args:
        company: Company to check

    Returns:
        Subscription status string or None if no subscription

    Example:
        >>> company = Company.objects.get(slug='acme-corp')
        >>> get_subscription_status(company)
        'active'
    """
    if not hasattr(company, 'subscription'):
        return None

    return company.subscription.status


def has_active_subscription(company: Company) -> bool:
    """
    Check if company has an active subscription.

    Args:
        company: Company to check

    Returns:
        True if subscription is active or trialing, False otherwise

    Example:
        >>> company = Company.objects.get(slug='acme-corp')
        >>> has_active_subscription(company)
        True
    """
    if not hasattr(company, 'subscription'):
        return False

    return company.subscription.is_active
