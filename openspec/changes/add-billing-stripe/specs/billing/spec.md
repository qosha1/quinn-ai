# Billing Specification

## ADDED Requirements

### Requirement: Subscription Plans
The system SHALL define subscription plans with features and limits.

#### Scenario: Plan tiers
- **GIVEN** plans: free, pro, enterprise
- **WHEN** company subscribes to pro
- **THEN** company.subscription.plan is pro
- **AND** plan limits are enforced

### Requirement: Stripe Checkout
The system SHALL integrate with Stripe Checkout for subscriptions.

#### Scenario: Subscribe to plan
- **WHEN** POST /api/v1/billing/checkout/ with plan_id
- **THEN** Stripe checkout session is created
- **AND** checkout URL is returned
- **AND** on completion, webhook updates subscription

### Requirement: Stripe Webhooks
The system SHALL handle Stripe webhook events for subscription lifecycle.

#### Scenario: Subscription created
- **WHEN** checkout.session.completed webhook received
- **THEN** Subscription record is created
- **AND** company subscription_tier is updated

#### Scenario: Subscription cancelled
- **WHEN** customer.subscription.deleted webhook received
- **THEN** Subscription status is set to cancelled
- **AND** company reverts to free tier

### Requirement: Usage Tracking
The system SHALL track usage per company for billing and quotas.

#### Scenario: Record usage
- **WHEN** company uses billable feature
- **THEN** UsageRecord is created
- **AND** usage is aggregated for billing period

#### Scenario: Quota enforcement
- **WHEN** company exceeds usage limit
- **THEN** can_use_feature() returns False
- **AND** appropriate error is returned

### Requirement: Customer Portal
The system SHALL provide access to Stripe customer portal.

#### Scenario: Manage subscription
- **WHEN** POST /api/v1/billing/portal/
- **THEN** portal session URL is returned
- **AND** user can manage payment methods and subscription

### Requirement: Invoice History
The system SHALL track invoice history.

#### Scenario: List invoices
- **WHEN** GET /api/v1/billing/invoices/
- **THEN** company's invoices are returned
- **AND** includes status, amount, PDF URL
