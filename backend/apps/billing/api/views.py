"""
API views for billing endpoints.
"""

import logging

from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, AllowAny
from drf_spectacular.utils import extend_schema, extend_schema_view

from apps.billing.models import Plan, Subscription, Invoice
from apps.billing.api.serializers import (
    PlanSerializer,
    SubscriptionSerializer,
    InvoiceSerializer,
    CheckoutSessionSerializer,
    PortalSessionSerializer,
    UsageSummarySerializer,
)
from apps.billing.stripe_client import StripeService
from apps.billing.services import UsageService

logger = logging.getLogger(__name__)


@extend_schema_view(
    list=extend_schema(
        description="List all active subscription plans",
        tags=["Billing"],
    ),
    retrieve=extend_schema(
        description="Get details of a specific plan",
        tags=["Billing"],
    ),
)
class PlanViewSet(viewsets.ReadOnlyModelViewSet):
    """
    ViewSet for listing subscription plans.

    Only supports read operations. Plans are publicly viewable.
    """

    serializer_class = PlanSerializer
    permission_classes = [AllowAny]
    queryset = Plan.objects.filter(is_active=True)
    lookup_field = 'slug'


@extend_schema_view(
    current=extend_schema(
        description="Get current subscription for authenticated user's company",
        tags=["Billing"],
    ),
)
class SubscriptionViewSet(viewsets.ViewSet):
    """
    ViewSet for subscription management.

    Provides endpoints to view and manage company subscriptions.
    """

    permission_classes = [IsAuthenticated]

    @action(detail=False, methods=['get'])
    def current(self, request):
        """
        Get current subscription for user's company.

        Returns subscription details or 404 if no active subscription.
        """
        # Get user's company (assuming user has a primary company)
        # You may need to adjust this based on your company selection logic
        user = request.user

        # Get company from user's team memberships
        team_membership = user.team_memberships.first()
        if not team_membership:
            return Response(
                {'detail': 'User is not a member of any team'},
                status=status.HTTP_404_NOT_FOUND
            )

        company = team_membership.team.company

        if not hasattr(company, 'subscription'):
            return Response(
                {'detail': 'No active subscription found'},
                status=status.HTTP_404_NOT_FOUND
            )

        serializer = SubscriptionSerializer(company.subscription)
        return Response(serializer.data)


@extend_schema_view(
    create=extend_schema(
        description="Create a Stripe checkout session for subscription",
        request=CheckoutSessionSerializer,
        tags=["Billing"],
    ),
)
class CheckoutViewSet(viewsets.ViewSet):
    """
    ViewSet for creating Stripe checkout sessions.
    """

    permission_classes = [IsAuthenticated]

    def create(self, request):
        """
        Create a Stripe checkout session.

        Returns session ID and checkout URL.
        """
        serializer = CheckoutSessionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        # Get user's company
        user = request.user
        team_membership = user.team_memberships.first()

        if not team_membership:
            return Response(
                {'detail': 'User is not a member of any team'},
                status=status.HTTP_400_BAD_REQUEST
            )

        company = team_membership.team.company

        # Check if company already has an active subscription
        if hasattr(company, 'subscription') and company.subscription.is_active:
            return Response(
                {'detail': 'Company already has an active subscription'},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Get plan
        plan = Plan.objects.get(id=serializer.validated_data['plan_id'])

        # Use provided URLs or default to settings
        from django.conf import settings
        success_url = serializer.validated_data.get(
            'success_url',
            getattr(settings, 'STRIPE_SUCCESS_URL', request.build_absolute_uri('/'))
        )
        cancel_url = serializer.validated_data.get(
            'cancel_url',
            getattr(settings, 'STRIPE_CANCEL_URL', request.build_absolute_uri('/'))
        )
        trial_days = serializer.validated_data.get('trial_days')

        try:
            session_data = StripeService.create_checkout_session(
                company=company,
                plan=plan,
                success_url=success_url,
                cancel_url=cancel_url,
                trial_days=trial_days,
            )

            return Response(session_data, status=status.HTTP_201_CREATED)

        except Exception as e:
            logger.error(f"Failed to create checkout session: {e}")
            return Response(
                {'detail': 'Failed to create checkout session'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


@extend_schema_view(
    create=extend_schema(
        description="Create a Stripe customer portal session",
        request=PortalSessionSerializer,
        tags=["Billing"],
    ),
)
class PortalViewSet(viewsets.ViewSet):
    """
    ViewSet for creating Stripe customer portal sessions.
    """

    permission_classes = [IsAuthenticated]

    def create(self, request):
        """
        Create a Stripe customer portal session.

        Returns portal URL for managing subscription.
        """
        serializer = PortalSessionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        # Get user's company
        user = request.user
        team_membership = user.team_memberships.first()

        if not team_membership:
            return Response(
                {'detail': 'User is not a member of any team'},
                status=status.HTTP_400_BAD_REQUEST
            )

        company = team_membership.team.company

        # Check if company has a subscription
        if not hasattr(company, 'subscription'):
            return Response(
                {'detail': 'No subscription found'},
                status=status.HTTP_404_NOT_FOUND
            )

        # Use provided return URL or default
        return_url = serializer.validated_data.get(
            'return_url',
            request.build_absolute_uri('/')
        )

        try:
            portal_url = StripeService.create_portal_session(
                company=company,
                return_url=return_url,
            )

            return Response(
                {'url': portal_url},
                status=status.HTTP_201_CREATED
            )

        except Exception as e:
            logger.error(f"Failed to create portal session: {e}")
            return Response(
                {'detail': 'Failed to create portal session'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


@extend_schema_view(
    list=extend_schema(
        description="List invoices for authenticated user's company",
        tags=["Billing"],
    ),
)
class InvoiceViewSet(viewsets.ReadOnlyModelViewSet):
    """
    ViewSet for listing company invoices.

    Only supports read operations.
    """

    serializer_class = InvoiceSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        """Filter invoices to only show user's company invoices."""
        user = self.request.user

        # Get company from user's team memberships
        team_membership = user.team_memberships.first()
        if not team_membership:
            return Invoice.objects.none()

        company = team_membership.team.company

        return Invoice.objects.filter(company=company).order_by('-created_at')


@extend_schema_view(
    summary=extend_schema(
        description="Get current usage summary for authenticated user's company",
        responses={200: UsageSummarySerializer(many=True)},
        tags=["Billing"],
    ),
)
class UsageViewSet(viewsets.ViewSet):
    """
    ViewSet for viewing usage statistics.
    """

    permission_classes = [IsAuthenticated]

    @action(detail=False, methods=['get'])
    def summary(self, request):
        """
        Get usage summary for current billing period.

        Returns usage statistics for all tracked usage types.
        """
        user = request.user

        # Get company from user's team memberships
        team_membership = user.team_memberships.first()
        if not team_membership:
            return Response(
                {'detail': 'User is not a member of any team'},
                status=status.HTTP_404_NOT_FOUND
            )

        company = team_membership.team.company

        # Check if company has a subscription
        if not hasattr(company, 'subscription'):
            return Response(
                {'detail': 'No subscription found'},
                status=status.HTTP_404_NOT_FOUND
            )

        try:
            usage_summary = UsageService.get_usage_summary(company)
            return Response(usage_summary)

        except Exception as e:
            logger.error(f"Failed to get usage summary: {e}")
            return Response(
                {'detail': 'Failed to retrieve usage summary'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
