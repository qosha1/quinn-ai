"""
Admin interface for billing models.
"""

from django.contrib import admin
from django.utils.html import format_html

from apps.billing.models import (
    Plan,
    Subscription,
    Invoice,
    UsageType,
    UsageRecord,
    UsageLimit,
)


@admin.register(Plan)
class PlanAdmin(admin.ModelAdmin):
    """Admin interface for Plan model."""

    list_display = [
        'name',
        'slug',
        'price',
        'interval',
        'is_active',
        'sort_order',
        'created_at',
    ]
    list_filter = ['is_active', 'interval', 'created_at']
    search_fields = ['name', 'slug', 'stripe_price_id']
    readonly_fields = ['id', 'created_at', 'updated_at']
    ordering = ['sort_order', 'price']

    fieldsets = (
        ('Basic Information', {
            'fields': ('name', 'slug', 'is_active', 'sort_order')
        }),
        ('Pricing', {
            'fields': ('stripe_price_id', 'price', 'interval')
        }),
        ('Features & Limits', {
            'fields': ('features', 'limits')
        }),
        ('Metadata', {
            'fields': ('id', 'created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )


class UsageLimitInline(admin.TabularInline):
    """Inline admin for UsageLimit."""

    model = UsageLimit
    extra = 1
    fields = ['usage_type', 'limit_value', 'overage_allowed', 'overage_price']


@admin.register(Subscription)
class SubscriptionAdmin(admin.ModelAdmin):
    """Admin interface for Subscription model."""

    list_display = [
        'company',
        'plan',
        'status_badge',
        'current_period_end',
        'cancel_at_period_end',
        'created_at',
    ]
    list_filter = ['status', 'cancel_at_period_end', 'created_at']
    search_fields = [
        'company__name',
        'stripe_subscription_id',
        'stripe_customer_id',
    ]
    readonly_fields = [
        'id',
        'stripe_subscription_id',
        'stripe_customer_id',
        'created_at',
        'updated_at',
    ]
    raw_id_fields = ['company', 'plan']
    date_hierarchy = 'created_at'

    fieldsets = (
        ('Subscription Details', {
            'fields': ('company', 'plan', 'status', 'cancel_at_period_end')
        }),
        ('Stripe Information', {
            'fields': ('stripe_subscription_id', 'stripe_customer_id')
        }),
        ('Billing Period', {
            'fields': ('current_period_start', 'current_period_end')
        }),
        ('Trial Period', {
            'fields': ('trial_start', 'trial_end'),
            'classes': ('collapse',)
        }),
        ('Metadata', {
            'fields': ('id', 'created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )

    def status_badge(self, obj):
        """Display status with color badge."""
        colors = {
            'active': 'green',
            'trialing': 'blue',
            'past_due': 'orange',
            'cancelled': 'red',
            'incomplete': 'gray',
        }
        color = colors.get(obj.status, 'gray')
        return format_html(
            '<span style="color: {}; font-weight: bold;">{}</span>',
            color,
            obj.get_status_display()
        )
    status_badge.short_description = 'Status'


@admin.register(Invoice)
class InvoiceAdmin(admin.ModelAdmin):
    """Admin interface for Invoice model."""

    list_display = [
        'stripe_invoice_id',
        'company',
        'amount',
        'currency',
        'status_badge',
        'paid_at',
        'created_at',
    ]
    list_filter = ['status', 'currency', 'paid_at', 'created_at']
    search_fields = [
        'stripe_invoice_id',
        'company__name',
    ]
    readonly_fields = [
        'id',
        'stripe_invoice_id',
        'invoice_pdf_link',
        'created_at',
        'updated_at',
    ]
    raw_id_fields = ['company', 'subscription']
    date_hierarchy = 'created_at'

    fieldsets = (
        ('Invoice Details', {
            'fields': ('company', 'subscription', 'stripe_invoice_id')
        }),
        ('Amount', {
            'fields': ('amount', 'currency', 'status')
        }),
        ('Period', {
            'fields': ('period_start', 'period_end', 'paid_at')
        }),
        ('PDF', {
            'fields': ('invoice_pdf', 'invoice_pdf_link'),
        }),
        ('Metadata', {
            'fields': ('id', 'created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )

    def status_badge(self, obj):
        """Display status with color badge."""
        colors = {
            'paid': 'green',
            'open': 'blue',
            'void': 'gray',
            'uncollectible': 'red',
        }
        color = colors.get(obj.status, 'gray')
        return format_html(
            '<span style="color: {}; font-weight: bold;">{}</span>',
            color,
            obj.get_status_display()
        )
    status_badge.short_description = 'Status'

    def invoice_pdf_link(self, obj):
        """Display clickable link to invoice PDF."""
        if obj.invoice_pdf:
            return format_html(
                '<a href="{}" target="_blank">View PDF</a>',
                obj.invoice_pdf
            )
        return '-'
    invoice_pdf_link.short_description = 'PDF Link'


@admin.register(UsageType)
class UsageTypeAdmin(admin.ModelAdmin):
    """Admin interface for UsageType model."""

    list_display = ['name', 'slug', 'unit', 'created_at']
    search_fields = ['name', 'slug', 'unit']
    readonly_fields = ['id', 'created_at', 'updated_at']
    prepopulated_fields = {'slug': ('name',)}

    fieldsets = (
        ('Basic Information', {
            'fields': ('name', 'slug', 'unit', 'description')
        }),
        ('Metadata', {
            'fields': ('id', 'created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )


@admin.register(UsageRecord)
class UsageRecordAdmin(admin.ModelAdmin):
    """Admin interface for UsageRecord model."""

    list_display = [
        'company',
        'usage_type',
        'quantity',
        'recorded_at',
        'billing_period_start',
    ]
    list_filter = ['usage_type', 'recorded_at', 'billing_period_start']
    search_fields = ['company__name']
    readonly_fields = [
        'id',
        'recorded_at',
        'created_at',
        'updated_at',
    ]
    raw_id_fields = ['company', 'usage_type']
    date_hierarchy = 'recorded_at'

    fieldsets = (
        ('Usage Details', {
            'fields': ('company', 'usage_type', 'quantity')
        }),
        ('Billing Period', {
            'fields': ('billing_period_start', 'billing_period_end')
        }),
        ('Additional Data', {
            'fields': ('metadata',),
            'classes': ('collapse',)
        }),
        ('Metadata', {
            'fields': ('id', 'recorded_at', 'created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )


@admin.register(UsageLimit)
class UsageLimitAdmin(admin.ModelAdmin):
    """Admin interface for UsageLimit model."""

    list_display = [
        'plan',
        'usage_type',
        'limit_value',
        'overage_allowed',
        'overage_price',
    ]
    list_filter = ['plan', 'usage_type', 'overage_allowed']
    search_fields = ['plan__name', 'usage_type__name']
    readonly_fields = ['id', 'created_at', 'updated_at']
    raw_id_fields = ['plan', 'usage_type']

    fieldsets = (
        ('Limit Details', {
            'fields': ('plan', 'usage_type', 'limit_value')
        }),
        ('Overage', {
            'fields': ('overage_allowed', 'overage_price')
        }),
        ('Metadata', {
            'fields': ('id', 'created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
