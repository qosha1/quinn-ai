"""
Decorators for billing-based feature gating and rate limiting.
"""

from functools import wraps
from rest_framework.response import Response
from rest_framework import status

from apps.billing.services import UsageService
from apps.billing.utils import can_use_feature, has_active_subscription


def require_active_subscription(view_func):
    """
    Decorator to require an active subscription for view access.

    Returns 402 Payment Required if company has no active subscription.

    Usage:
        @require_active_subscription
        def my_view(request):
            # Only accessible with active subscription
            pass
    """
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        # Get user's company
        user = request.user
        team_membership = user.team_memberships.first()

        if not team_membership:
            return Response(
                {'detail': 'User is not a member of any team'},
                status=status.HTTP_403_FORBIDDEN
            )

        company = team_membership.team.company

        if not has_active_subscription(company):
            return Response(
                {
                    'detail': 'Active subscription required',
                    'error_code': 'subscription_required'
                },
                status=status.HTTP_402_PAYMENT_REQUIRED
            )

        return view_func(request, *args, **kwargs)

    return wrapper


def require_feature(feature_slug):
    """
    Decorator to require a specific feature from the subscription plan.

    Returns 403 Forbidden if company's plan doesn't include the feature.

    Usage:
        @require_feature('advanced_analytics')
        def analytics_view(request):
            # Only accessible with advanced_analytics feature
            pass
    """
    def decorator(view_func):
        @wraps(view_func)
        def wrapper(request, *args, **kwargs):
            # Get user's company
            user = request.user
            team_membership = user.team_memberships.first()

            if not team_membership:
                return Response(
                    {'detail': 'User is not a member of any team'},
                    status=status.HTTP_403_FORBIDDEN
                )

            company = team_membership.team.company

            if not can_use_feature(company, feature_slug):
                return Response(
                    {
                        'detail': f'Feature "{feature_slug}" not available on your plan',
                        'error_code': 'feature_not_available',
                        'feature': feature_slug
                    },
                    status=status.HTTP_403_FORBIDDEN
                )

            return view_func(request, *args, **kwargs)

        return wrapper
    return decorator


def track_usage(usage_type_slug, quantity=1, metadata_func=None):
    """
    Decorator to track usage and enforce limits.

    Automatically records usage and checks limits before executing view.
    Returns 429 Too Many Requests if limit would be exceeded.

    Args:
        usage_type_slug: Usage type to track (e.g., 'api_calls')
        quantity: Amount to record (default 1)
        metadata_func: Optional function to generate metadata from request

    Usage:
        @track_usage('api_calls', quantity=1)
        def my_api_view(request):
            # Usage automatically tracked
            pass

        # With metadata
        @track_usage('api_calls', metadata_func=lambda req: {'endpoint': req.path})
        def my_api_view(request):
            pass
    """
    def decorator(view_func):
        @wraps(view_func)
        def wrapper(request, *args, **kwargs):
            # Get user's company
            user = request.user
            team_membership = user.team_memberships.first()

            if not team_membership:
                return Response(
                    {'detail': 'User is not a member of any team'},
                    status=status.HTTP_403_FORBIDDEN
                )

            company = team_membership.team.company

            # Check if company has active subscription
            if not has_active_subscription(company):
                return Response(
                    {
                        'detail': 'Active subscription required',
                        'error_code': 'subscription_required'
                    },
                    status=status.HTTP_402_PAYMENT_REQUIRED
                )

            # Check limit before recording
            try:
                if not UsageService.check_limit(company, usage_type_slug, quantity):
                    remaining = UsageService.get_remaining(company, usage_type_slug)
                    limit = UsageService.get_limit(company, usage_type_slug)

                    return Response(
                        {
                            'detail': 'Usage quota exceeded',
                            'error_code': 'quota_exceeded',
                            'usage_type': usage_type_slug,
                            'limit': float(limit) if limit else None,
                            'remaining': float(remaining) if remaining else 0,
                        },
                        status=status.HTTP_429_TOO_MANY_REQUESTS
                    )
            except ValueError as e:
                # No subscription or usage type not found
                return Response(
                    {'detail': str(e), 'error_code': 'usage_check_failed'},
                    status=status.HTTP_500_INTERNAL_SERVER_ERROR
                )

            # Generate metadata if function provided
            metadata = None
            if metadata_func:
                try:
                    metadata = metadata_func(request)
                except Exception:
                    # Don't fail request if metadata generation fails
                    pass

            # Execute view
            response = view_func(request, *args, **kwargs)

            # Only record usage if request was successful (2xx status)
            if 200 <= response.status_code < 300:
                try:
                    UsageService.record_usage(
                        company=company,
                        usage_type_slug=usage_type_slug,
                        quantity=quantity,
                        metadata=metadata,
                    )
                except Exception as e:
                    # Log error but don't fail the request
                    import logging
                    logger = logging.getLogger(__name__)
                    logger.error(f"Failed to record usage: {e}")

            return response

        return wrapper
    return decorator


# Example usage in views:
"""
from apps.billing.decorators import (
    require_active_subscription,
    require_feature,
    track_usage,
)

# Require active subscription
@require_active_subscription
@api_view(['GET'])
def protected_view(request):
    return Response({'data': 'protected content'})

# Require specific feature
@require_feature('advanced_analytics')
@api_view(['GET'])
def analytics_view(request):
    return Response({'analytics': 'advanced data'})

# Track API usage
@track_usage('api_calls')
@api_view(['GET'])
def api_view(request):
    return Response({'data': 'result'})

# Track with metadata
@track_usage('api_calls', metadata_func=lambda req: {
    'endpoint': req.path,
    'method': req.method,
})
@api_view(['POST'])
def create_view(request):
    return Response({'created': True})

# Combine decorators
@require_active_subscription
@require_feature('api_access')
@track_usage('api_calls')
@api_view(['GET'])
def advanced_api_view(request):
    return Response({'data': 'advanced result'})
"""
