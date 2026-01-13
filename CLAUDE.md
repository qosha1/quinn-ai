# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

<!-- OPENSPEC:START -->
# OpenSpec Instructions

These instructions are for AI assistants working in this project.

Always open `@/openspec/AGENTS.md` when the request:
- Mentions planning or proposals (words like proposal, spec, change, plan)
- Introduces new capabilities, breaking changes, architecture shifts, or big performance/security work
- Sounds ambiguous and you need the authoritative spec before coding

Use `@/openspec/AGENTS.md` to learn:
- How to create and apply change proposals
- Spec format and conventions
- Project structure and guidelines

Keep this managed block so 'openspec update' can refresh the instructions.

<!-- OPENSPEC:END -->

## Project Overview

B2B SaaS template with Django backend, two NextJS frontends (landing + app), Docker infrastructure.

**Stack:**
- Backend: Django 5.1+, DRF, Celery, PostgreSQL 16, Redis 7
- Landing: NextJS 15, Tailwind, shadcn/ui
- App: NextJS 15, JWT auth, Stripe, Zustand
- Infrastructure: Docker Compose, Nginx, Traefik (production)

## Development Commands

```bash
# Docker (primary development method)
make up                    # Start all services
make down                  # Stop services (preserves volumes)
make logs                  # View logs
make shell                 # Django shell
make migrate               # Run migrations
make test                  # Run tests

# Manual Docker
docker-compose -f docker-compose.local.yml up --build
docker-compose -f docker-compose.local.yml down  # No -v flag!

# OpenSpec (spec-driven development)
openspec list              # View active changes
openspec list --specs      # View existing capabilities
openspec show <change>     # View change details
openspec validate --strict # Validate specs

# Testing with systemeval (REQUIRED at checkpoints)
pip install systemeval[pytest]
systemeval test                    # Run tests - must PASS before marking tasks complete
systemeval test --json             # Machine-readable output for CI
systemeval test --template markdown # Human-readable report
```

## Validation Checkpoints (systemeval)

All implementation checkpoints MUST use `systemeval` for success criteria:

```bash
# Exit codes: 0=PASS, 1=FAIL, 2=ERROR
systemeval test
```

**Required checkpoints:**
1. Before marking any task as complete in `tasks.md`
2. Before requesting proposal approval
3. Before archiving a change

Do NOT mark tasks complete unless `systemeval test` returns exit code 0 (PASS).

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

### Naming Conventions

**Django:** Apps lowercase singular (`user`, `team`), Models PascalCase (`TeamMember`), ViewSets `{Model}ViewSet`, Serializers `{Model}Serializer`

**NextJS:** Components PascalCase (`UserProfile.tsx`), utilities camelCase (`fetchApi.ts`), types with suffix (`UserResponse`)

**Docker:** Services kebab-case (`celery-worker`), volumes `{project}-{service}-{type}`

## Environment Variables

Required in `.envs/.local/.django`:
- `SECRET_KEY`, `DATABASE_URL`, `REDIS_URL`
- `STRIPE_SECRET_KEY`, `STRIPE_WEBHOOK_SECRET`

## OpenSpec Workflow

This project uses spec-driven development. Before implementing new features:

1. Check existing specs: `openspec list --specs`
2. Check pending changes: `openspec list`
3. For new capabilities, create a proposal in `openspec/changes/<change-id>/`
4. Validate: `openspec validate <change-id> --strict`
5. Get approval before implementing

Skip proposals for: bug fixes, typos, dependency updates, config changes.
