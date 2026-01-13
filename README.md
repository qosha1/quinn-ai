# B2B SaaS Template

Production-ready B2B SaaS template with Django backend and NextJS frontends.

## Stack

- **Backend**: Django 5.1+, DRF, Celery, PostgreSQL 16, Redis 7
- **Landing**: NextJS 15, Tailwind, shadcn/ui
- **App**: NextJS 15, JWT auth, Stripe, team management
- **Infrastructure**: Docker Compose, Nginx, Traefik (production)

## Quick Start

```bash
# Start all services
make up

# Or manually
docker-compose -f docker-compose.local.yml up --build
```

## Project Structure

```
backend/          # Django API
landing/          # Marketing landing page
app/              # Dashboard application
compose/          # Docker configurations
openspec/         # Specifications and changes
```

## Development

```bash
make up           # Start services
make down         # Stop services (preserves data)
make logs         # View logs
make shell        # Django shell
make migrate      # Run migrations
make test         # Run tests
```

## Testing & Validation

This project uses [systemeval](https://pypi.org/project/systemeval/) for deterministic test validation:

```bash
pip install systemeval[pytest]
systemeval test                    # Run tests (exit 0=PASS, 1=FAIL, 2=ERROR)
systemeval test --json             # Machine-readable output
systemeval test --template markdown # Human-readable report
```

**Required checkpoints:**
1. Before marking tasks complete
2. Before requesting proposal approval
3. Before archiving changes

## Environment Variables

Copy `.envs/.local/.django.example` to `.envs/.local/.django` and configure:

| Variable | Description |
|----------|-------------|
| `SECRET_KEY` | Django secret key |
| `DATABASE_URL` | PostgreSQL connection |
| `REDIS_URL` | Redis connection |
| `STRIPE_SECRET_KEY` | Stripe API key |
| `STRIPE_WEBHOOK_SECRET` | Webhook signature |

## Architecture

### Multi-Tenancy Model

```
Company (root tenant)
├── Teams (workspaces)
│   └── TeamMembers (user + role)
└── Users
```

Roles: `owner` > `admin` > `member` > `viewer`

### API Conventions

- JWT: `Authorization: Bearer {token}`
- API keys: `X-API-Key: {key}`
- Token refresh: `/api/v1/token/refresh/`
- URLs: kebab-case (`/api/v1/team-members/`)

## OpenSpec Workflow

This project uses OpenSpec for spec-driven development:

```bash
openspec list              # View active changes
openspec list --specs      # View existing capabilities
openspec show <change>     # View change details
openspec validate --strict # Validate specs
```

See `openspec/AGENTS.md` for full workflow documentation.
