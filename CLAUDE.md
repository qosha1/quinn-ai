# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

---

## 🚨 Code Quality Commandments (MANDATORY)

### Test Before Respond
**Before EVERY response that modifies code, run the appropriate test suite:**

```bash
# Python projects
systemeval test

# TypeScript/NextJS projects
npm run test --prefix app
npm run test --prefix e2e
```

Do NOT mark tasks complete until tests pass.

### No Magic Strings
- All configuration values must come from environment variables or config files
- No hardcoded URLs, API keys, secrets, or environment-specific values in code
- Use constants for repeated string literals

### No Duplicate Functionality
- One codebase, one architecture
- Work within existing structures - extend, don't duplicate
- No `enhanced-*`, `improved-*`, `new-*`, or `simple-*` file variants
- Before creating a new file, verify similar functionality doesn't exist

### No Dead Code
- Remove unused imports, functions, and variables
- No commented-out code blocks (use git history)
- No `// TODO` without an associated issue/task

### Type Safety
- TypeScript: strict mode, no `any` types without justification
- Python: type hints on all function signatures
- No implicit type coercion in comparisons

### Error Handling
- No silent failures - log or propagate errors
- No empty catch blocks
- Validate inputs at system boundaries

### File Management
- Never create task-specific MD files in root (no `ARCHITECTURE_REVIEW.md`, etc.)
- `docs/*` is for validated, tested documentation only - no planning docs
- No test output files (logs, snapshots) in root directory

### Commit Discipline
- No "Co-Authored-By" lines
- No hyperbolic language ("critical fix", "important update")
- Atomic commits - one logical change per commit

---

## Template Sync (For Forked Repos)

This project is based on a template. To pull updates from the upstream template:

### Initial Setup (once per fork)
```bash
# Add template as upstream remote
git remote add template https://github.com/YOUR_ORG/b2b-saas-template.git
git fetch template
```

### Syncing Updates
```bash
# Fetch latest template changes
git fetch template main

# Create a sync branch
git checkout -b template-sync

# Merge template changes (resolve conflicts as needed)
git merge template/main --allow-unrelated-histories

# Review changes, run tests
systemeval test

# If all passes, merge to main
git checkout main
git merge template-sync
git branch -d template-sync
```

### What Gets Synced
- Infrastructure configs (Docker, CI/CD)
- Base components and utilities
- Test infrastructure
- CLAUDE.md rules and conventions

### What Stays Local
- Business logic in `apps/`
- Custom components
- Environment-specific configs
- `.envs/` contents

---

## Versioning & Releases

This project follows [Semantic Versioning](https://semver.org/):
- **MAJOR** (x.0.0): Breaking changes, major architecture shifts
- **MINOR** (0.x.0): New features, backward-compatible additions
- **PATCH** (0.0.x): Bug fixes, minor improvements

### Current Version
Check `VERSION` file in project root.

### Version Bump Process

```bash
# Patch release (bug fixes) - auto-generates from commits
./scripts/bump-version.sh patch

# Minor release (new features) - requires changelog + release notes
./scripts/bump-version.sh minor

# Major release (breaking changes) - requires changelog + release notes
./scripts/bump-version.sh major
```

### AI Release Documentation Requirements

**For MAJOR and MINOR releases:**
1. Update `CHANGELOG.md` [Unreleased] section with all changes
2. Create `release-notes/vX.Y.Z.md` with:
   - Overview (2-3 sentence summary)
   - Highlights (key features)
   - Breaking changes (if any)
   - Migration guide (if needed)
   - Detailed feature descriptions
3. Run `systemeval test` - must pass
4. Run `./scripts/bump-version.sh [major|minor]`

**For PATCH releases:**
- Changelog auto-generated from git commit messages
- No release notes file required
- Run `./scripts/bump-version.sh patch`

### Changelog Format (Keep a Changelog)

```markdown
## [Unreleased]

### Added
- New features

### Changed
- Changes to existing features

### Deprecated
- Features to be removed

### Removed
- Removed features

### Fixed
- Bug fixes

### Security
- Security fixes
```

### Tagging Convention
- Tags: `v0.1.0`, `v1.0.0`, `v1.2.3`
- Always use annotated tags: `git tag -a v1.0.0 -m "Release v1.0.0"`

---

## QuinnAI Product Truth
**QuinnAI watches coding CLI sessions - NOT "Claude Code sessions".**

This is a CLI-agnostic AI assistant layer. It monitors ANY terminal where a developer is working (vim, nvim, emacs, vscode terminal, raw shell, aider, claude code, cursor, etc).

Do NOT assume or hardcode Claude Code specifics. The architecture must be terminal/editor agnostic.

## CRITICAL: No Provider Lock-in (Architectural Law)

**WE define the interfaces. Providers implement OUR contracts. Never the reverse.**

### Anti-patterns (NEVER do this):
- "Build AI service" → "Build OpenAI SDK wrapper" ❌
- "Build workflow system" → "Build Claude-to-Claude handoff" ❌
- "Build terminal manager" → "Custom scripts for one machine" ❌

### Correct pattern (ALWAYS do this):
```
Our Abstract Interface (we define)
        ↓
Provider Adapter (they implement our contract)
        ↓
[OpenAI, Anthropic, Ollama, etc.] ← swappable via config
```

**Every external dependency gets wrapped in OUR abstraction:**
- `AIProvider` base class → `OpenAIProvider`, `AnthropicProvider` subclasses
- `TerminalCapture` base class → `AllTermCapture`, `PTYCapture`, `LogCapture` subclasses
- `ResponseInjector` base class → `SocketInjector`, `ClipboardInjector`, `APIInjector` subclasses

**Config-driven provider selection. Zero code changes to swap providers.**

If you find yourself writing `import OpenAI` or `import Anthropic` anywhere except inside a provider adapter, you are doing it wrong.

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
