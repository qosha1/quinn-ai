# Billing App

Stripe-based subscription billing for the B2B SaaS template.

## Features

- Subscription management with Stripe
- Plan-based pricing with features and limits
- Usage tracking and quota enforcement
- Invoice management
- Webhook handling for Stripe events
- Customer portal integration

## Models

### Plan
Defines subscription plans with pricing, features, and limits.

**Fields:**
- `name`: Display name
- `slug`: URL-friendly identifier
- `stripe_price_id`: Stripe price ID
- `price`: Monthly/yearly price
- `interval`: Billing interval (month/year)
- `features`: List of feature descriptions
- `limits`: JSON object with feature limits
- `is_active`: Whether plan is available
- `sort_order`: Display order

### Subscription
Tracks company subscriptions linked to Stripe.

**Fields:**
- `company`: Company that owns subscription
- `plan`: Current plan
- `stripe_subscription_id`: Stripe subscription ID
- `stripe_customer_id`: Stripe customer ID
- `status`: Current status (active/cancelled/past_due/trialing)
- `current_period_start/end`: Billing period
- `cancel_at_period_end`: Cancellation flag
- `trial_start/end`: Trial period

### Invoice
Stores invoice data synced from Stripe.

**Fields:**
- `company`: Company that owns invoice
- `subscription`: Related subscription
- `stripe_invoice_id`: Stripe invoice ID
- `amount`: Invoice amount
- `currency`: Currency code
- `status`: Payment status
- `invoice_pdf`: Link to PDF
- `period_start/end`: Billing period
- `paid_at`: Payment timestamp

### UsageType
Defines types of usage to track (API calls, storage, seats, etc.).

**Fields:**
- `name`: Display name
- `slug`: URL-friendly identifier
- `unit`: Unit of measurement
- `description`: What is being tracked

### UsageRecord
Records individual usage events.

**Fields:**
- `company`: Company incurring usage
- `usage_type`: Type of usage
- `quantity`: Amount of usage
- `recorded_at`: Timestamp
- `billing_period_start/end`: Billing period
- `metadata`: Additional data

### UsageLimit
Links plans to usage types with limits.

**Fields:**
- `plan`: Plan this limit applies to
- `usage_type`: Type of usage limited
- `limit_value`: Maximum allowed
- `overage_allowed`: Allow beyond limit
- `overage_price`: Price per unit over limit

## API Endpoints

### Plans
- `GET /api/v1/plans/` - List all active plans (public)
- `GET /api/v1/plans/{slug}/` - Get plan details (public)

### Subscriptions
- `GET /api/v1/billing/subscription/current/` - Get current subscription

### Checkout
- `POST /api/v1/billing/checkout/` - Create checkout session

**Request:**
```json
{
  "plan_id": "uuid",
  "success_url": "http://example.com/success",
  "cancel_url": "http://example.com/cancel",
  "trial_days": 14
}
```

**Response:**
```json
{
  "session_id": "cs_test_...",
  "url": "https://checkout.stripe.com/..."
}
```

### Portal
- `POST /api/v1/billing/portal/` - Create customer portal session

**Request:**
```json
{
  "return_url": "http://example.com/billing"
}
```

**Response:**
```json
{
  "url": "https://billing.stripe.com/..."
}
```

### Invoices
- `GET /api/v1/billing/invoices/` - List company invoices

### Usage
- `GET /api/v1/billing/usage/summary/` - Get usage summary

**Response:**
```json
{
  "api_calls": {
    "name": "API Calls",
    "unit": "calls",
    "current": 1500,
    "limit": 10000,
    "remaining": 8500,
    "overage_allowed": false,
    "overage_price": null
  }
}
```

### Webhooks
- `POST /api/v1/webhooks/stripe/` - Stripe webhook endpoint (CSRF exempt)

## Services

### StripeService
Handles Stripe API interactions.

**Methods:**
- `create_customer(company)` - Create Stripe customer
- `create_checkout_session(company, plan, success_url, cancel_url)` - Create checkout
- `create_portal_session(company, return_url)` - Create portal session
- `cancel_subscription(subscription, immediate=False)` - Cancel subscription
- `get_invoices(company, limit=10)` - Get invoices
- `sync_subscription(stripe_subscription)` - Sync from webhook
- `sync_invoice(stripe_invoice)` - Sync invoice from webhook

### UsageService
Manages usage tracking and limits.

**Methods:**
- `record_usage(company, usage_type_slug, quantity)` - Record usage
- `get_usage(company, usage_type_slug, period_start, period_end)` - Get usage
- `get_current_usage(company, usage_type_slug)` - Get current period usage
- `get_limit(company, usage_type_slug)` - Get usage limit
- `check_limit(company, usage_type_slug, additional_quantity)` - Check if within limit
- `get_remaining(company, usage_type_slug)` - Get remaining quota
- `get_usage_summary(company)` - Get full usage summary

## Webhook Events

Handled Stripe events:
- `checkout.session.completed` - Create subscription
- `customer.subscription.created` - Create subscription record
- `customer.subscription.updated` - Update subscription
- `customer.subscription.deleted` - Mark cancelled
- `invoice.paid` - Create/update invoice
- `invoice.payment_failed` - Update status, notify

## Setup

### 1. Environment Variables

Add to `.env`:
```bash
STRIPE_SECRET_KEY=sk_test_...
STRIPE_PUBLISHABLE_KEY=pk_test_...
STRIPE_WEBHOOK_SECRET=whsec_...
STRIPE_SUCCESS_URL=http://localhost:3000/billing/success
STRIPE_CANCEL_URL=http://localhost:3000/billing/cancel
```

### 2. Install Dependencies

```bash
pip install -r requirements/base.txt
```

### 3. Run Migrations

```bash
python manage.py makemigrations billing
python manage.py migrate
```

### 4. Create Plans

```python
from apps.billing.models import Plan

Plan.objects.create(
    name="Starter",
    slug="starter",
    stripe_price_id="price_...",  # From Stripe Dashboard
    price=29.00,
    interval="month",
    features=["Feature 1", "Feature 2"],
    limits={"api_calls": 1000, "storage_gb": 10},
    is_active=True,
    sort_order=1,
)
```

### 5. Create Usage Types

```python
from apps.billing.models import UsageType, UsageLimit

usage_type = UsageType.objects.create(
    name="API Calls",
    slug="api_calls",
    unit="calls",
    description="Number of API calls made",
)

# Link to plan
UsageLimit.objects.create(
    plan=plan,
    usage_type=usage_type,
    limit_value=10000,
    overage_allowed=False,
)
```

### 6. Configure Stripe Webhook

In Stripe Dashboard:
1. Go to Developers > Webhooks
2. Add endpoint: `https://yourdomain.com/api/v1/webhooks/stripe/`
3. Select events:
   - checkout.session.completed
   - customer.subscription.created
   - customer.subscription.updated
   - customer.subscription.deleted
   - invoice.paid
   - invoice.payment_failed
4. Copy webhook signing secret to `STRIPE_WEBHOOK_SECRET`

## Usage Examples

### Recording Usage

```python
from apps.billing.services import UsageService

# Record API call
UsageService.record_usage(
    company=company,
    usage_type_slug="api_calls",
    quantity=1,
    metadata={"endpoint": "/api/v1/users/", "method": "GET"}
)
```

### Checking Limits

```python
from apps.billing.services import UsageService

# Check if company can make API call
if UsageService.check_limit(company, "api_calls", quantity=1):
    # Process request
    UsageService.record_usage(company, "api_calls", quantity=1)
else:
    # Return quota exceeded error
    return Response({"error": "Quota exceeded"}, status=429)
```

### Checking Features

```python
from apps.billing.utils import can_use_feature

# Check if company can use advanced analytics
if can_use_feature(company, "advanced_analytics"):
    # Show advanced analytics
    pass
else:
    # Show upgrade prompt
    pass
```

## Testing

Run tests:
```bash
python manage.py test apps.billing
```

## Admin Interface

The billing app includes a full admin interface at `/admin/billing/` with:
- Plan management
- Subscription monitoring with status badges
- Invoice viewing with PDF links
- Usage type configuration
- Usage record browsing
- Usage limit configuration

## Notes

- All monetary values use `DecimalField` with 2 decimal places
- Stripe IDs are indexed for fast lookups
- Webhook endpoint is CSRF exempt (verified by Stripe signature)
- All webhook handlers use `transaction.atomic` for data consistency
- Usage tracking supports metadata for audit trails
- Subscriptions use OneToOneField with Company (one subscription per company)

## Future Enhancements

Potential additions:
- Multi-currency support
- Proration handling
- Discount codes
- Usage-based billing
- Custom pricing for enterprise
- Subscription scheduling
- Payment method management
- Dunning management
