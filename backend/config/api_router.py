"""
API Router for versioned API endpoints.

All API v1 endpoints are registered here.
"""

from django.urls import path
from rest_framework.routers import DefaultRouter
from rest_framework_simplejwt.views import (
    TokenObtainPairView,
    TokenRefreshView,
    TokenVerifyView,
)

from apps.core.api.views import health_check

# Create router for ViewSets
router = DefaultRouter()

# Import ViewSets
from apps.users.api.views import UserViewSet
from apps.teams.api.views import (
    CompanyViewSet,
    TeamViewSet,
    TeamMemberViewSet,
    TeamInvitationViewSet,
)
from apps.authentication.api.views import APIKeyViewSet
from apps.billing.api.views import (
    PlanViewSet,
    SubscriptionViewSet,
    CheckoutViewSet,
    PortalViewSet,
    InvoiceViewSet,
    UsageViewSet,
)

# Register ViewSets
router.register(r"users", UserViewSet, basename="user")
router.register(r"companies", CompanyViewSet, basename="company")
router.register(r"teams", TeamViewSet, basename="team")
router.register(r"team-members", TeamMemberViewSet, basename="team-member")
router.register(r"team-invitations", TeamInvitationViewSet, basename="team-invitation")
router.register(r"api-keys", APIKeyViewSet, basename="api-key")

# Billing ViewSets
router.register(r"plans", PlanViewSet, basename="plan")
router.register(r"billing/subscription", SubscriptionViewSet, basename="subscription")
router.register(r"billing/checkout", CheckoutViewSet, basename="checkout")
router.register(r"billing/portal", PortalViewSet, basename="portal")
router.register(r"billing/invoices", InvoiceViewSet, basename="invoice")
router.register(r"billing/usage", UsageViewSet, basename="usage")

# URL patterns for non-ViewSet endpoints
urlpatterns = [
    # Health check
    path("health/", health_check, name="health-check"),

    # JWT Authentication
    path("auth/token/", TokenObtainPairView.as_view(), name="token-obtain-pair"),
    path("auth/token/refresh/", TokenRefreshView.as_view(), name="token-refresh"),
    path("auth/token/verify/", TokenVerifyView.as_view(), name="token-verify"),
]

# Include router URLs
urlpatterns += router.urls
