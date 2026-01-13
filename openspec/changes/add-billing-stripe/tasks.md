## 1. Billing Models
- [x] 1.1 Create backend/apps/billing/models.py (Plan, Subscription, Invoice)
- [x] 1.2 Create backend/apps/billing/models.py (UsageType, UsageRecord, UsageLimit)
- [x] 1.3 Create backend/apps/billing/services.py (StripeService, UsageService)

## 2. Stripe Integration
- [x] 2.1 Configure Stripe settings in base.py
- [x] 2.2 Create backend/apps/billing/stripe_client.py
- [x] 2.3 Create checkout session endpoints
- [x] 2.4 Create customer portal endpoints

## 3. Webhooks
- [x] 3.1 Create backend/apps/billing/webhooks.py
- [x] 3.2 Handle checkout.session.completed
- [x] 3.3 Handle customer.subscription.updated
- [x] 3.4 Handle customer.subscription.deleted
- [x] 3.5 Handle invoice.paid and invoice.payment_failed

## 4. Usage Tracking
- [x] 4.1 Create UsageService for recording usage
- [x] 4.2 Create UsageEnforcer for quota checks
- [x] 4.3 Create usage aggregation for billing
- [x] 4.4 Add company.can_use_feature() method

## 5. API Endpoints
- [x] 5.1 Create backend/apps/billing/api/views.py
- [x] 5.2 Create backend/apps/billing/api/serializers.py
- [x] 5.3 Add billing endpoints to router
