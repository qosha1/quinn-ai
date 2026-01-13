# Billing System Architecture

Visual overview of the billing system components and data flow.

## System Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────┐
│                         Frontend (Next.js)                       │
│  ┌────────────┐  ┌────────────┐  ┌────────────┐  ┌───────────┐│
│  │  Pricing   │  │  Checkout  │  │  Billing   │  │   Usage   ││
│  │    Page    │  │    Flow    │  │   Portal   │  │  Dashboard││
│  └────────────┘  └────────────┘  └────────────┘  └───────────┘│
└──────────┬───────────────┬────────────┬─────────────┬──────────┘
           │               │            │             │
           │ GET /plans    │ POST       │ POST        │ GET
           │               │ /checkout  │ /portal     │ /usage/summary
           │               │            │             │
┌──────────▼───────────────▼────────────▼─────────────▼──────────┐
│                    Django REST API (DRF)                         │
│  ┌────────────┐  ┌────────────┐  ┌────────────┐  ┌───────────┐│
│  │    Plan    │  │  Checkout  │  │   Portal   │  │   Usage   ││
│  │  ViewSet   │  │  ViewSet   │  │  ViewSet   │  │  ViewSet  ││
│  └────────────┘  └────────────┘  └────────────┘  └───────────┘│
└──────────┬────────────┬─────────────┬──────────────┬───────────┘
           │            │             │              │
           │            │             │              │
┌──────────▼────────────▼─────────────▼──────────────▼───────────┐
│                      Service Layer                               │
│  ┌──────────────────────────────┐  ┌──────────────────────────┐│
│  │      StripeService           │  │     UsageService         ││
│  │  • create_customer()         │  │  • record_usage()        ││
│  │  • create_checkout_session() │  │  • check_limit()         ││
│  │  • create_portal_session()   │  │  • get_remaining()       ││
│  │  • cancel_subscription()     │  │  • get_usage_summary()   ││
│  │  • sync_subscription()       │  │                          ││
│  └──────────────────────────────┘  └──────────────────────────┘│
└──────────┬─────────────────────────────────┬───────────────────┘
           │                                 │
           │                                 │
┌──────────▼─────────────────────────────────▼───────────────────┐
│                      Data Layer (Models)                         │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐       │
│  │   Plan   │  │Subscription│ │ Invoice  │  │UsageRecord│       │
│  │          │  │            │ │          │  │          │       │
│  └──────────┘  └──────────┘  └──────────┘  └──────────┘       │
│  ┌──────────┐  ┌──────────┐                                    │
│  │UsageType │  │UsageLimit│                                    │
│  └──────────┘  └──────────┘                                    │
└────────────────────────────┬────────────────────────────────────┘
                             │
                             ▼
                    ┌─────────────────┐
                    │   PostgreSQL    │
                    └─────────────────┘


┌─────────────────────────────────────────────────────────────────┐
│                         Stripe API                               │
│  ┌────────────┐  ┌────────────┐  ┌────────────┐               │
│  │  Checkout  │  │  Customer  │  │Subscription│               │
│  │  Sessions  │  │   Portal   │  │  & Billing │               │
│  └────────────┘  └────────────┘  └────────────┘               │
└──────────┬──────────────────────────────────────────────────────┘
           │
           │ Webhooks
           │
┌──────────▼───────────────────────────────────────────────────────┐
│              Webhook Handler (webhooks.py)                        │
│  ┌────────────────────────────────────────────────────────────┐ │
│  │  stripe_webhook()                                          │ │
│  │  • Verify signature                                        │ │
│  │  • Route to handler                                        │ │
│  └────────────────────────────────────────────────────────────┘ │
│  ┌────────────┐  ┌────────────┐  ┌────────────┐               │
│  │ checkout   │  │subscription│  │  invoice   │               │
│  │ .completed │  │  .updated  │  │   .paid    │               │
│  └────────────┘  └────────────┘  └────────────┘               │
└──────────────────────────────────────────────────────────────────┘
```

## Data Flow Diagrams

### Checkout Flow

```
User             Frontend          Django API        StripeService       Stripe
 │                  │                  │                  │                │
 │ Select Plan      │                  │                  │                │
 ├─────────────────►│                  │                  │                │
 │                  │ POST /checkout   │                  │                │
 │                  ├─────────────────►│                  │                │
 │                  │                  │ create_checkout  │                │
 │                  │                  ├─────────────────►│                │
 │                  │                  │                  │ Create Session │
 │                  │                  │                  ├───────────────►│
 │                  │                  │                  │ ◄──────────────┤
 │                  │                  │ ◄────────────────┤  session_url   │
 │                  │ ◄────────────────┤  session_url     │                │
 │ Redirect to URL  │                  │                  │                │
 │◄─────────────────┤                  │                  │                │
 │                  │                  │                  │                │
 │──────────────────────────────────────────────────────────────────────►│
 │                     Complete Payment on Stripe Checkout                │
 │◄───────────────────────────────────────────────────────────────────────┤
 │                                                                         │
 │                  │                  │                  │ Webhook Event  │
 │                  │                  │◄─────────────────────────────────┤
 │                  │                  │ sync_subscription│                │
 │                  │                  ├─────────────────►│                │
 │                  │                  │                  │                │
 │ Redirect to      │                  │                  │                │
 │ success_url      │                  │                  │                │
 │◄─────────────────────────────────────────────────────────────────────┤
```

### Usage Tracking Flow

```
Request          Decorator         UsageService        Database
  │                  │                  │                  │
  │ API Call         │                  │                  │
  ├─────────────────►│                  │                  │
  │                  │ check_limit()    │                  │
  │                  ├─────────────────►│                  │
  │                  │                  │ Get limit        │
  │                  │                  ├─────────────────►│
  │                  │                  │ Get current      │
  │                  │                  ├─────────────────►│
  │                  │                  │ Calculate        │
  │                  │ ◄────────────────┤ OK/Over limit    │
  │                  │                  │                  │
  │ [if under limit] │                  │                  │
  │ Execute view     │                  │                  │
  ├─────────────────►│                  │                  │
  │ ◄────────────────┤                  │                  │
  │ Response         │                  │                  │
  │                  │ record_usage()   │                  │
  │                  ├─────────────────►│                  │
  │                  │                  │ Create record    │
  │                  │                  ├─────────────────►│
  │                  │                  │ ◄────────────────┤
  │                  │ ◄────────────────┤                  │
  │                  │                  │                  │
```

### Webhook Processing Flow

```
Stripe           Webhook Handler      StripeService       Database
  │                    │                    │                │
  │ Event              │                    │                │
  ├───────────────────►│                    │                │
  │                    │ Verify signature   │                │
  │                    │                    │                │
  │                    │ Route to handler   │                │
  │                    │                    │                │
  │                    │ subscription.updated                │
  │                    ├───────────────────►│                │
  │                    │                    │ Parse data     │
  │                    │                    │ Get company    │
  │                    │                    ├───────────────►│
  │                    │                    │ Get plan       │
  │                    │                    ├───────────────►│
  │                    │                    │ Update/Create  │
  │                    │                    ├───────────────►│
  │                    │ ◄──────────────────┤                │
  │                    │ Send notification  │                │
  │                    │                    │                │
  │ ◄──────────────────┤                    │                │
  │ 200 OK             │                    │                │
```

## Component Relationships

### Model Relationships

```
Company (teams app)
    │
    │ OneToOne
    ▼
Subscription
    │
    ├─── ForeignKey ───► Plan
    │                      │
    │                      │ ManyToMany (through UsageLimit)
    │                      ▼
    │                   UsageType
    │                      ▲
    ├─── ForeignKey       │
    ▼                      │
Invoice              UsageRecord
                           │
                           └─── ForeignKey ───►
```

### Layer Responsibilities

```
┌────────────────────────────────────────────────────────┐
│                   View Layer (API)                      │
│  • Request validation                                   │
│  • Permission checking                                  │
│  • Response serialization                               │
│  • HTTP status codes                                    │
└─────────────────────┬──────────────────────────────────┘
                      │
┌─────────────────────▼──────────────────────────────────┐
│                 Service Layer                           │
│  • Business logic                                       │
│  • Stripe API calls                                     │
│  • Usage calculations                                   │
│  • Transaction management                               │
└─────────────────────┬──────────────────────────────────┘
                      │
┌─────────────────────▼──────────────────────────────────┐
│                   Model Layer                           │
│  • Data validation                                      │
│  • Database constraints                                 │
│  • Model methods                                        │
│  • Relationships                                        │
└────────────────────────────────────────────────────────┘
```

## Security Layers

```
┌────────────────────────────────────────────────────────┐
│              Request Security                           │
│  ┌──────────────────────────────────────────────────┐ │
│  │  1. HTTPS (in production)                        │ │
│  └──────────────────────────────────────────────────┘ │
│  ┌──────────────────────────────────────────────────┐ │
│  │  2. CORS (django-cors-headers)                   │ │
│  └──────────────────────────────────────────────────┘ │
│  ┌──────────────────────────────────────────────────┐ │
│  │  3. Authentication (JWT)                         │ │
│  └──────────────────────────────────────────────────┘ │
│  ┌──────────────────────────────────────────────────┐ │
│  │  4. Authorization (DRF Permissions)              │ │
│  └──────────────────────────────────────────────────┘ │
└────────────────────────────────────────────────────────┘

┌────────────────────────────────────────────────────────┐
│            Webhook Security                             │
│  ┌──────────────────────────────────────────────────┐ │
│  │  1. Stripe Signature Verification                │ │
│  └──────────────────────────────────────────────────┘ │
│  ┌──────────────────────────────────────────────────┐ │
│  │  2. CSRF Exempt (verified by signature)          │ │
│  └──────────────────────────────────────────────────┘ │
│  ┌──────────────────────────────────────────────────┐ │
│  │  3. Idempotent Handlers                          │ │
│  └──────────────────────────────────────────────────┘ │
└────────────────────────────────────────────────────────┘

┌────────────────────────────────────────────────────────┐
│              Data Security                              │
│  ┌──────────────────────────────────────────────────┐ │
│  │  1. No payment data stored                       │ │
│  └──────────────────────────────────────────────────┘ │
│  ┌──────────────────────────────────────────────────┐ │
│  │  2. Environment-based secrets                    │ │
│  └──────────────────────────────────────────────────┘ │
│  ┌──────────────────────────────────────────────────┐ │
│  │  3. Database constraints                         │ │
│  └──────────────────────────────────────────────────┘ │
└────────────────────────────────────────────────────────┘
```

## Scalability Considerations

```
┌────────────────────────────────────────────────────────┐
│                Database Layer                           │
│  ┌──────────────────────────────────────────────────┐ │
│  │  • Indexed Stripe IDs                            │ │
│  │  • Composite indexes on usage queries            │ │
│  │  • Connection pooling (CONN_MAX_AGE)             │ │
│  │  • Read replicas (for reporting)                 │ │
│  └──────────────────────────────────────────────────┘ │
└────────────────────────────────────────────────────────┘

┌────────────────────────────────────────────────────────┐
│                 Caching Layer                           │
│  ┌──────────────────────────────────────────────────┐ │
│  │  • Plan data (rarely changes)                    │ │
│  │  • Usage limits per plan                         │ │
│  │  • Current subscription per company              │ │
│  │  • Redis for session/cache                       │ │
│  └──────────────────────────────────────────────────┘ │
└────────────────────────────────────────────────────────┘

┌────────────────────────────────────────────────────────┐
│               Async Processing                          │
│  ┌──────────────────────────────────────────────────┐ │
│  │  • Celery for heavy operations                   │ │
│  │  • Batch usage recording                         │ │
│  │  • Async webhook processing                      │ │
│  │  • Email sending                                 │ │
│  └──────────────────────────────────────────────────┘ │
└────────────────────────────────────────────────────────┘
```

## Extension Points

### Where to Add Custom Logic

```
┌────────────────────────────────────────────────────────┐
│             Signals (signals.py)                        │
│  • After subscription created                           │
│  • After subscription updated                           │
│  • Custom business logic triggers                       │
└────────────────────────────────────────────────────────┘

┌────────────────────────────────────────────────────────┐
│           Service Layer Extensions                      │
│  • Custom pricing logic                                 │
│  • Discount calculations                                │
│  • Enterprise custom terms                              │
└────────────────────────────────────────────────────────┘

┌────────────────────────────────────────────────────────┐
│            Webhook Handlers                             │
│  • Custom notification logic                            │
│  • Analytics tracking                                   │
│  • Integration with other services                      │
└────────────────────────────────────────────────────────┘

┌────────────────────────────────────────────────────────┐
│              Model Methods                              │
│  • Custom validation                                    │
│  • Computed properties                                  │
│  • Business rules                                       │
└────────────────────────────────────────────────────────┘
```

## Monitoring & Observability

```
┌────────────────────────────────────────────────────────┐
│                  Logging Points                         │
│  • All Stripe API calls                                 │
│  • Webhook events                                       │
│  • Usage recording                                      │
│  • Errors and exceptions                                │
└────────────────────────────────────────────────────────┘

┌────────────────────────────────────────────────────────┐
│                Metrics to Track                         │
│  • Subscription conversion rate                         │
│  • Churn rate                                           │
│  • Usage patterns                                       │
│  • Webhook processing time                              │
│  • Payment success/failure rate                         │
└────────────────────────────────────────────────────────┘

┌────────────────────────────────────────────────────────┐
│                  Health Checks                          │
│  • Database connectivity                                │
│  • Stripe API availability                              │
│  • Webhook processing status                            │
│  • Usage tracking functionality                         │
└────────────────────────────────────────────────────────┘
```

## Technology Stack

```
┌────────────────────────────────────────────────────────┐
│                   Backend Stack                         │
│  • Django 5.1+                                          │
│  • Django REST Framework 3.14+                          │
│  • PostgreSQL (primary database)                        │
│  • Redis (caching, celery)                              │
│  • Stripe Python SDK 7.0+                               │
└────────────────────────────────────────────────────────┘

┌────────────────────────────────────────────────────────┐
│              External Services                          │
│  • Stripe (payments, subscriptions)                     │
│  • Email service (notifications)                        │
│  • Sentry (error tracking - optional)                   │
└────────────────────────────────────────────────────────┘

┌────────────────────────────────────────────────────────┐
│                Infrastructure                           │
│  • Docker (containerization)                            │
│  • Nginx (reverse proxy)                                │
│  • Gunicorn (WSGI server)                               │
│  • Celery (async tasks)                                 │
└────────────────────────────────────────────────────────┘
```

This architecture provides:
- Clear separation of concerns
- Scalable design
- Secure payment processing
- Flexible usage tracking
- Easy maintenance and extension
