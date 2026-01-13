"""
Serializers for billing API endpoints.
"""

from rest_framework import serializers

from apps.billing.models import (
    Plan,
    Subscription,
    Invoice,
    UsageRecord,
    UsageType,
    UsageLimit,
)


class PlanSerializer(serializers.ModelSerializer):
    """Serializer for Plan model."""

    class Meta:
        model = Plan
        fields = [
            'id',
            'name',
            'slug',
            'price',
            'interval',
            'features',
            'limits',
            'is_active',
            'created_at',
        ]
        read_only_fields = ['id', 'created_at']


class SubscriptionSerializer(serializers.ModelSerializer):
    """Serializer for Subscription model."""

    plan = PlanSerializer(read_only=True)
    is_active = serializers.BooleanField(read_only=True)

    class Meta:
        model = Subscription
        fields = [
            'id',
            'company',
            'plan',
            'status',
            'current_period_start',
            'current_period_end',
            'cancel_at_period_end',
            'trial_start',
            'trial_end',
            'is_active',
            'created_at',
            'updated_at',
        ]
        read_only_fields = [
            'id',
            'company',
            'plan',
            'status',
            'current_period_start',
            'current_period_end',
            'cancel_at_period_end',
            'trial_start',
            'trial_end',
            'is_active',
            'created_at',
            'updated_at',
        ]


class InvoiceSerializer(serializers.ModelSerializer):
    """Serializer for Invoice model."""

    class Meta:
        model = Invoice
        fields = [
            'id',
            'stripe_invoice_id',
            'amount',
            'currency',
            'status',
            'invoice_pdf',
            'period_start',
            'period_end',
            'paid_at',
            'created_at',
        ]
        read_only_fields = fields


class UsageTypeSerializer(serializers.ModelSerializer):
    """Serializer for UsageType model."""

    class Meta:
        model = UsageType
        fields = [
            'id',
            'name',
            'slug',
            'unit',
            'description',
        ]
        read_only_fields = fields


class UsageRecordSerializer(serializers.ModelSerializer):
    """Serializer for UsageRecord model."""

    usage_type = UsageTypeSerializer(read_only=True)

    class Meta:
        model = UsageRecord
        fields = [
            'id',
            'usage_type',
            'quantity',
            'recorded_at',
            'billing_period_start',
            'billing_period_end',
            'metadata',
        ]
        read_only_fields = fields


class CheckoutSessionSerializer(serializers.Serializer):
    """Serializer for creating checkout sessions."""

    plan_id = serializers.UUIDField(required=True)
    success_url = serializers.URLField(required=False)
    cancel_url = serializers.URLField(required=False)
    trial_days = serializers.IntegerField(required=False, min_value=0, max_value=365)

    def validate_plan_id(self, value):
        """Validate that plan exists and is active."""
        try:
            plan = Plan.objects.get(id=value, is_active=True)
        except Plan.DoesNotExist:
            raise serializers.ValidationError("Invalid or inactive plan")
        return value


class PortalSessionSerializer(serializers.Serializer):
    """Serializer for creating customer portal sessions."""

    return_url = serializers.URLField(required=False)


class UsageSummarySerializer(serializers.Serializer):
    """Serializer for usage summary response."""

    name = serializers.CharField()
    unit = serializers.CharField()
    current = serializers.FloatField()
    limit = serializers.FloatField()
    remaining = serializers.FloatField(allow_null=True)
    overage_allowed = serializers.BooleanField()
    overage_price = serializers.FloatField(allow_null=True)
