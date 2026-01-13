"""
Billing models for subscription management with Stripe.
"""

from decimal import Decimal
from django.db import models
from django.utils.translation import gettext_lazy as _
from django.core.validators import MinValueValidator

from apps.core.models import BaseModel
from apps.teams.models import Company


class Plan(BaseModel):
    """
    Subscription plan model.

    Represents a pricing tier with associated features, limits, and Stripe pricing.
    """

    class Interval(models.TextChoices):
        """Billing interval choices."""
        MONTH = "month", _("Monthly")
        YEAR = "year", _("Yearly")

    name = models.CharField(
        _("name"),
        max_length=100,
        help_text=_("Display name for the plan")
    )
    slug = models.SlugField(
        _("slug"),
        max_length=100,
        unique=True,
        db_index=True,
        help_text=_("URL-friendly identifier")
    )
    stripe_price_id = models.CharField(
        _("stripe price ID"),
        max_length=255,
        unique=True,
        db_index=True,
        help_text=_("Stripe price ID for this plan")
    )
    price = models.DecimalField(
        _("price"),
        max_digits=10,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0.00"))],
        help_text=_("Price in dollars")
    )
    interval = models.CharField(
        _("interval"),
        max_length=10,
        choices=Interval.choices,
        default=Interval.MONTH,
        help_text=_("Billing interval")
    )
    features = models.JSONField(
        _("features"),
        default=list,
        blank=True,
        help_text=_("List of feature descriptions")
    )
    limits = models.JSONField(
        _("limits"),
        default=dict,
        blank=True,
        help_text=_("Feature limits and quotas")
    )
    is_active = models.BooleanField(
        _("is active"),
        default=True,
        db_index=True,
        help_text=_("Whether this plan is available for new subscriptions")
    )
    sort_order = models.IntegerField(
        _("sort order"),
        default=0,
        help_text=_("Display order (lower numbers first)")
    )

    class Meta:
        verbose_name = _("plan")
        verbose_name_plural = _("plans")
        db_table = "billing_plans"
        ordering = ["sort_order", "price"]

    def __str__(self):
        """Return string representation of the plan."""
        return f"{self.name} (${self.price}/{self.interval})"


class Subscription(BaseModel):
    """
    Company subscription model.

    Tracks active subscriptions linked to Stripe.
    """

    class Status(models.TextChoices):
        """Subscription status choices matching Stripe statuses."""
        ACTIVE = "active", _("Active")
        CANCELLED = "cancelled", _("Cancelled")
        PAST_DUE = "past_due", _("Past Due")
        TRIALING = "trialing", _("Trialing")
        INCOMPLETE = "incomplete", _("Incomplete")
        INCOMPLETE_EXPIRED = "incomplete_expired", _("Incomplete Expired")
        UNPAID = "unpaid", _("Unpaid")

    company = models.OneToOneField(
        Company,
        on_delete=models.PROTECT,
        related_name="subscription",
        help_text=_("Company that owns this subscription")
    )
    plan = models.ForeignKey(
        Plan,
        on_delete=models.PROTECT,
        related_name="subscriptions",
        help_text=_("Current subscription plan")
    )
    stripe_subscription_id = models.CharField(
        _("stripe subscription ID"),
        max_length=255,
        unique=True,
        db_index=True,
        help_text=_("Stripe subscription ID")
    )
    stripe_customer_id = models.CharField(
        _("stripe customer ID"),
        max_length=255,
        db_index=True,
        help_text=_("Stripe customer ID")
    )
    status = models.CharField(
        _("status"),
        max_length=20,
        choices=Status.choices,
        default=Status.INCOMPLETE,
        db_index=True,
        help_text=_("Current subscription status")
    )
    current_period_start = models.DateTimeField(
        _("current period start"),
        help_text=_("Start of the current billing period")
    )
    current_period_end = models.DateTimeField(
        _("current period end"),
        help_text=_("End of the current billing period")
    )
    cancel_at_period_end = models.BooleanField(
        _("cancel at period end"),
        default=False,
        help_text=_("Whether subscription will cancel at period end")
    )
    trial_start = models.DateTimeField(
        _("trial start"),
        null=True,
        blank=True,
        help_text=_("Start of trial period")
    )
    trial_end = models.DateTimeField(
        _("trial end"),
        null=True,
        blank=True,
        help_text=_("End of trial period")
    )

    class Meta:
        verbose_name = _("subscription")
        verbose_name_plural = _("subscriptions")
        db_table = "billing_subscriptions"
        ordering = ["-created_at"]

    def __str__(self):
        """Return string representation of the subscription."""
        return f"{self.company.name} - {self.plan.name} ({self.status})"

    @property
    def is_active(self):
        """Check if subscription is active."""
        return self.status in [self.Status.ACTIVE, self.Status.TRIALING]


class Invoice(BaseModel):
    """
    Invoice model tracking Stripe invoices.

    Stores invoice data synced from Stripe.
    """

    class Status(models.TextChoices):
        """Invoice status choices matching Stripe statuses."""
        PAID = "paid", _("Paid")
        OPEN = "open", _("Open")
        VOID = "void", _("Void")
        UNCOLLECTIBLE = "uncollectible", _("Uncollectible")
        DRAFT = "draft", _("Draft")

    company = models.ForeignKey(
        Company,
        on_delete=models.PROTECT,
        related_name="invoices",
        help_text=_("Company that owns this invoice")
    )
    subscription = models.ForeignKey(
        Subscription,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="invoices",
        help_text=_("Subscription this invoice is for")
    )
    stripe_invoice_id = models.CharField(
        _("stripe invoice ID"),
        max_length=255,
        unique=True,
        db_index=True,
        help_text=_("Stripe invoice ID")
    )
    amount = models.DecimalField(
        _("amount"),
        max_digits=10,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0.00"))],
        help_text=_("Invoice amount in dollars")
    )
    currency = models.CharField(
        _("currency"),
        max_length=3,
        default="usd",
        help_text=_("Three-letter ISO currency code")
    )
    status = models.CharField(
        _("status"),
        max_length=20,
        choices=Status.choices,
        db_index=True,
        help_text=_("Current invoice status")
    )
    invoice_pdf = models.URLField(
        _("invoice PDF"),
        max_length=500,
        blank=True,
        help_text=_("URL to invoice PDF")
    )
    period_start = models.DateTimeField(
        _("period start"),
        help_text=_("Start of billing period")
    )
    period_end = models.DateTimeField(
        _("period end"),
        help_text=_("End of billing period")
    )
    paid_at = models.DateTimeField(
        _("paid at"),
        null=True,
        blank=True,
        help_text=_("Timestamp when invoice was paid")
    )

    class Meta:
        verbose_name = _("invoice")
        verbose_name_plural = _("invoices")
        db_table = "billing_invoices"
        ordering = ["-created_at"]

    def __str__(self):
        """Return string representation of the invoice."""
        return f"Invoice {self.stripe_invoice_id} - {self.company.name} (${self.amount})"


class UsageType(BaseModel):
    """
    Usage type model for tracking different types of usage.

    Examples: API calls, storage MB, seats, etc.
    """

    name = models.CharField(
        _("name"),
        max_length=100,
        help_text=_("Display name for this usage type")
    )
    slug = models.SlugField(
        _("slug"),
        max_length=100,
        unique=True,
        db_index=True,
        help_text=_("URL-friendly identifier")
    )
    unit = models.CharField(
        _("unit"),
        max_length=50,
        help_text=_("Unit of measurement (e.g., 'api_calls', 'storage_mb', 'seats')")
    )
    description = models.TextField(
        _("description"),
        blank=True,
        help_text=_("Detailed description of what is being tracked")
    )

    class Meta:
        verbose_name = _("usage type")
        verbose_name_plural = _("usage types")
        db_table = "billing_usage_types"
        ordering = ["name"]

    def __str__(self):
        """Return string representation of the usage type."""
        return f"{self.name} ({self.unit})"


class UsageRecord(BaseModel):
    """
    Usage record model for tracking company usage.

    Records individual usage events for billing and quota tracking.
    """

    company = models.ForeignKey(
        Company,
        on_delete=models.CASCADE,
        related_name="usage_records",
        help_text=_("Company that incurred this usage")
    )
    usage_type = models.ForeignKey(
        UsageType,
        on_delete=models.PROTECT,
        related_name="records",
        help_text=_("Type of usage being recorded")
    )
    quantity = models.DecimalField(
        _("quantity"),
        max_digits=15,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0.00"))],
        help_text=_("Amount of usage")
    )
    recorded_at = models.DateTimeField(
        _("recorded at"),
        auto_now_add=True,
        db_index=True,
        help_text=_("When this usage was recorded")
    )
    billing_period_start = models.DateTimeField(
        _("billing period start"),
        db_index=True,
        help_text=_("Start of billing period for this usage")
    )
    billing_period_end = models.DateTimeField(
        _("billing period end"),
        db_index=True,
        help_text=_("End of billing period for this usage")
    )
    metadata = models.JSONField(
        _("metadata"),
        default=dict,
        blank=True,
        help_text=_("Additional metadata about this usage")
    )

    class Meta:
        verbose_name = _("usage record")
        verbose_name_plural = _("usage records")
        db_table = "billing_usage_records"
        ordering = ["-recorded_at"]
        indexes = [
            models.Index(fields=["company", "usage_type", "billing_period_start"]),
            models.Index(fields=["company", "recorded_at"]),
        ]

    def __str__(self):
        """Return string representation of the usage record."""
        return f"{self.company.name} - {self.usage_type.name}: {self.quantity}"


class UsageLimit(BaseModel):
    """
    Usage limit model defining quotas per plan.

    Links plans to usage types with specific limits and overage pricing.
    """

    plan = models.ForeignKey(
        Plan,
        on_delete=models.CASCADE,
        related_name="usage_limits",
        help_text=_("Plan this limit applies to")
    )
    usage_type = models.ForeignKey(
        UsageType,
        on_delete=models.PROTECT,
        related_name="limits",
        help_text=_("Type of usage being limited")
    )
    limit_value = models.DecimalField(
        _("limit value"),
        max_digits=15,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0.00"))],
        help_text=_("Maximum allowed usage")
    )
    overage_allowed = models.BooleanField(
        _("overage allowed"),
        default=False,
        help_text=_("Whether usage beyond limit is allowed")
    )
    overage_price = models.DecimalField(
        _("overage price"),
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(Decimal("0.00"))],
        help_text=_("Price per unit over limit (if overage allowed)")
    )

    class Meta:
        verbose_name = _("usage limit")
        verbose_name_plural = _("usage limits")
        db_table = "billing_usage_limits"
        ordering = ["plan", "usage_type"]
        unique_together = [["plan", "usage_type"]]

    def __str__(self):
        """Return string representation of the usage limit."""
        return f"{self.plan.name} - {self.usage_type.name}: {self.limit_value}"
