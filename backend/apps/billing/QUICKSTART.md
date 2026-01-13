# Billing Quick Start Guide

Get the billing system up and running in 5 minutes.

## Prerequisites

- Django project running
- Stripe account (test mode)
- PostgreSQL database

## Step 1: Install Dependencies

```bash
cd backend
pip install -r requirements/base.txt
```

## Step 2: Configure Environment

Add to your `.env` file:

```bash
# Stripe Keys (from Stripe Dashboard > Developers > API keys)
STRIPE_SECRET_KEY=sk_test_your_key_here
STRIPE_PUBLISHABLE_KEY=pk_test_your_key_here
STRIPE_WEBHOOK_SECRET=whsec_your_webhook_secret_here

# Redirect URLs (adjust for your frontend)
STRIPE_SUCCESS_URL=http://localhost:3000/billing/success
STRIPE_CANCEL_URL=http://localhost:3000/billing/cancel
```

## Step 3: Run Migrations

```bash
python manage.py makemigrations billing
python manage.py migrate
```

## Step 4: Create Sample Plans

```bash
python manage.py create_sample_plans
```

This creates:
- 3 monthly plans (Starter, Professional, Enterprise)
- 2 annual plans (Starter, Professional)
- 3 usage types (API Calls, Storage, Seats)
- Usage limits for each plan

## Step 5: Configure Stripe Products

### Option A: Create in Stripe Dashboard

1. Go to Stripe Dashboard > Products
2. Create products matching your plans:
   - Starter - $29/month
   - Professional - $99/month
   - Enterprise - $299/month
3. Copy price IDs for each product

### Option B: Use Stripe CLI

```bash
# Install Stripe CLI
brew install stripe/stripe-cli/stripe

# Login
stripe login

# Create products and prices
stripe prices create \
  --unit-amount 2900 \
  --currency usd \
  --recurring[interval]=month \
  --product-data[name]="Starter"

# Copy the price ID (starts with price_...)
```

## Step 6: Update Plan Price IDs

In Django admin or shell:

```python
from apps.billing.models import Plan

# Update each plan with real Stripe price ID
Plan.objects.filter(slug='starter').update(
    stripe_price_id='price_xxx_from_stripe'
)
Plan.objects.filter(slug='professional').update(
    stripe_price_id='price_yyy_from_stripe'
)
Plan.objects.filter(slug='enterprise').update(
    stripe_price_id='price_zzz_from_stripe'
)
```

## Step 7: Test Checkout Flow

### Using Django Shell

```python
from apps.teams.models import Company
from apps.billing.models import Plan
from apps.billing.stripe_client import StripeService

# Get a company and plan
company = Company.objects.first()
plan = Plan.objects.get(slug='professional')

# Create checkout session
session = StripeService.create_checkout_session(
    company=company,
    plan=plan,
    success_url='http://localhost:3000/success',
    cancel_url='http://localhost:3000/cancel',
)

print(f"Checkout URL: {session['url']}")
# Visit this URL to test checkout
```

### Using API

```bash
# Get auth token first
TOKEN=$(curl -X POST http://localhost:8000/api/v1/auth/token/ \
  -H "Content-Type: application/json" \
  -d '{"email":"user@example.com","password":"password"}' \
  | jq -r .access)

# Get plans
curl http://localhost:8000/api/v1/plans/ | jq

# Create checkout session
curl -X POST http://localhost:8000/api/v1/billing/checkout/ \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "plan_id": "plan-uuid-here",
    "success_url": "http://localhost:3000/success",
    "cancel_url": "http://localhost:3000/cancel"
  }' | jq
```

## Step 8: Configure Webhooks (Optional for Testing)

### For Local Development

Use Stripe CLI to forward webhooks:

```bash
# Forward webhooks to local server
stripe listen --forward-to localhost:8000/api/v1/webhooks/stripe/

# Copy the webhook signing secret (starts with whsec_)
# Add to your .env as STRIPE_WEBHOOK_SECRET
```

### For Production

1. Go to Stripe Dashboard > Developers > Webhooks
2. Add endpoint: `https://yourdomain.com/api/v1/webhooks/stripe/`
3. Select events to listen for:
   - `checkout.session.completed`
   - `customer.subscription.created`
   - `customer.subscription.updated`
   - `customer.subscription.deleted`
   - `invoice.paid`
   - `invoice.payment_failed`
4. Copy webhook signing secret to `STRIPE_WEBHOOK_SECRET`

## Step 9: Test Complete Flow

1. Create a test user and company
2. Visit checkout URL from Step 7
3. Use test card: `4242 4242 4242 4242`
4. Complete checkout
5. Webhook fires (if configured)
6. Subscription created in database

Verify in Django admin:
- Go to `/admin/billing/subscription/`
- You should see the new subscription

## Step 10: Use in Your Code

### Check if company can use a feature

```python
from apps.billing.utils import can_use_feature

if can_use_feature(company, 'advanced_analytics'):
    # Show advanced analytics
    return render_advanced_analytics()
else:
    # Show upgrade prompt
    return render_upgrade_prompt()
```

### Track API usage

```python
from apps.billing.decorators import track_usage

@track_usage('api_calls')
@api_view(['GET'])
def my_api_view(request):
    # Usage automatically tracked
    return Response({'data': 'result'})
```

### Check usage limits

```python
from apps.billing.services import UsageService

# Check if under limit
if UsageService.check_limit(company, 'api_calls', quantity=1):
    # Process request
    UsageService.record_usage(company, 'api_calls', quantity=1)
else:
    # Return quota exceeded error
    return Response(
        {'error': 'API quota exceeded'},
        status=429
    )
```

## Common Test Cards

Use these in Stripe test mode:

- Success: `4242 4242 4242 4242`
- Decline: `4000 0000 0000 0002`
- Requires authentication: `4000 0025 0000 3155`

Any future expiry date and any 3-digit CVC.

## Troubleshooting

### Checkout session creation fails
- Verify `STRIPE_SECRET_KEY` is correct
- Check plan has valid `stripe_price_id`
- Ensure company exists

### Webhook signature verification fails
- Verify `STRIPE_WEBHOOK_SECRET` matches Stripe
- Check webhook endpoint is publicly accessible
- Ensure request body is not modified by middleware

### Subscription not created after checkout
- Check webhook is configured and firing
- Look for errors in Django logs
- Verify webhook handler is receiving events

### Usage tracking fails
- Ensure company has active subscription
- Verify usage type exists
- Check usage limit is configured for plan

## Next Steps

1. Customize plans in admin
2. Add usage tracking to your API endpoints
3. Implement feature gating in frontend
4. Set up proper Stripe webhook endpoint
5. Configure email notifications
6. Add monitoring for webhook processing

## API Documentation

Once running, visit:
- Swagger UI: `http://localhost:8000/api/schema/swagger-ui/`
- ReDoc: `http://localhost:8000/api/schema/redoc/`

Look for "Billing" tag to see all billing endpoints.

## Support

For issues:
1. Check logs: `docker-compose logs backend`
2. Review Django admin for subscription/invoice data
3. Check Stripe Dashboard > Developers > Events
4. Review webhook logs in Stripe Dashboard

## Resources

- Full docs: `apps/billing/README.md`
- Implementation details: `apps/billing/IMPLEMENTATION.md`
- Stripe docs: https://stripe.com/docs
- Test mode: https://stripe.com/docs/testing
