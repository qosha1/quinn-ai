# B2B SaaS Template - Project Conventions

## Overview

A production-ready B2B SaaS template combining:
- **Django 5.1+** backend with DRF, Celery, PostgreSQL, Redis
- **NextJS 15** landing page with Tailwind/shadcn
- **NextJS 15** app with JWT auth, Stripe, team management
- **Docker Compose** for local development and production
- **Nginx** reverse proxy

## Directory Structure

```
/
├── backend/                    # Django API
│   ├── config/                 # Settings, URLs, ASGI, Celery
│   │   ├── settings/
│   │   │   ├── base.py
│   │   │   ├── local.py
│   │   │   ├── production.py
│   │   │   └── test.py
│   │   ├── api_router.py
│   │   ├── celery_app.py
│   │   └── urls.py
│   ├── apps/                   # Django applications
│   │   ├── users/              # Custom user model
│   │   ├── teams/              # Multi-tenancy
│   │   ├── authentication/     # API keys, tokens
│   │   ├── billing/            # Stripe integration
│   │   └── core/               # Shared utilities
│   ├── requirements/
│   │   ├── base.txt
│   │   ├── local.txt
│   │   └── production.txt
│   └── manage.py
├── landing/                    # NextJS landing page
│   ├── app/
│   ├── components/
│   │   ├── ui/                 # shadcn components
│   │   └── sections/           # Page sections
│   └── lib/
├── app/                        # NextJS dashboard app
│   ├── app/
│   │   ├── (auth)/             # Auth routes
│   │   ├── (dashboard)/        # Protected routes
│   │   └── api/                # API routes
│   ├── components/
│   ├── lib/
│   │   ├── api.ts              # API client
│   │   ├── auth.ts             # Auth utilities
│   │   └── stripe.ts           # Stripe client
│   └── stores/                 # State management
├── compose/                    # Docker configs
│   ├── local/
│   │   ├── django/
│   │   ├── nginx/
│   │   └── node/
│   └── production/
├── docker-compose.local.yml
├── docker-compose.production.yml
└── openspec/
```

## Naming Conventions

### Django
- Apps: lowercase, singular (`user`, `team`, `billing`)
- Models: PascalCase, singular (`User`, `Team`, `Subscription`)
- ViewSets: `{Model}ViewSet`
- Serializers: `{Model}Serializer`, `{Model}DetailSerializer`
- URLs: kebab-case (`/api/v1/team-members/`)

### NextJS
- Components: PascalCase (`UserProfile.tsx`)
- Pages: lowercase folders (`/dashboard/settings/`)
- Utilities: camelCase (`fetchApi.ts`)
- Types: PascalCase with suffix (`UserResponse`, `TeamMember`)

### Docker
- Services: lowercase with hyphens (`django`, `celery-worker`, `redis`)
- Volumes: `{project}-{service}-{type}` (`saas-postgres-data`)

## Technology Stack

### Backend
- Django 5.1+ with DRF 3.14+
- PostgreSQL 16 with psycopg 3
- Redis 7 with hiredis
- Celery 5.3+ with django-celery-beat
- JWT (simplejwt) + API Key authentication
- drf-spectacular for OpenAPI

### Frontend
- NextJS 15 with React 19
- TypeScript 5
- Tailwind CSS 3.4
- shadcn/ui components
- Zustand for state management

### Infrastructure
- Docker + Docker Compose
- Nginx for reverse proxy
- Traefik for production (Let's Encrypt)

## API Conventions

### Authentication
- JWT tokens in `Authorization: Bearer {token}` header
- API keys in `X-API-Key: {key}` header
- Token refresh at `/api/v1/token/refresh/`

### Response Format
```json
{
  "id": "uuid",
  "created_at": "ISO8601",
  "updated_at": "ISO8601",
  // ... resource fields
}
```

### Error Format
```json
{
  "detail": "Error message",
  "code": "error_code"
}
```

### Pagination
```json
{
  "count": 100,
  "next": "url",
  "previous": "url",
  "results": []
}
```

## Multi-Tenancy Model

```
Company (root tenant)
├── Teams (workspaces within company)
│   └── TeamMembers (users with roles)
└── Users (belong to company)
```

Roles: `owner` > `admin` > `member` > `viewer`

## Environment Variables

### Required
- `DATABASE_URL` - PostgreSQL connection
- `REDIS_URL` - Redis connection
- `SECRET_KEY` - Django secret
- `STRIPE_SECRET_KEY` - Stripe API key
- `STRIPE_WEBHOOK_SECRET` - Webhook signature

### Optional
- `SENTRY_DSN` - Error tracking
- `AWS_ACCESS_KEY_ID` - S3 storage
- `SENDGRID_API_KEY` - Email

## Testing & Validation

### systemeval (REQUIRED)

All validation checkpoints use `systemeval` for deterministic success criteria:

```bash
pip install systemeval[pytest]
systemeval test              # Must return exit code 0 (PASS)
systemeval test --json       # Machine-readable output for CI
```

**Exit codes:** 0=PASS, 1=FAIL, 2=ERROR

**Required checkpoints:**
1. Before marking tasks complete in `tasks.md`
2. Before requesting proposal approval
3. Before archiving changes

See: https://pypi.org/project/systemeval/
