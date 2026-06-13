# start-simpli — Host-Mode Org on a Real Monorepo

A host-mode QuinnAI org pointed at the **start-simpli** monorepo. Unlike the
toy examples, this org operates on a real codebase and is described
declaratively in `org.yml` (loaded via `qn org init --from org.yml`).

It demonstrates a **hybrid structure**:
- a **declared** Core Infra team that exists from day one, and
- **self-forming** App Groups whose Leads do discovery first, then hire.

## The Two-Layer Model

start-simpli is a pnpm + Django monorepo with two layers:

```
CORE INFRA  (the platform everyone builds on)
  auth-web            central Next.js auth host
  start-simpli-api    Django / DRF / Postgres / Celery backend
  packages/@startsimpli/*   shared: ui, auth, billing, api, hooks,
                            forms, funnels, utils

APP GROUPS  (customer-facing Next.js apps that consume the shared layer)
  apps/raise    VC fundraising
  apps/market   GTM / leads
  apps/vault    secrets
  apps/foundry  control plane that provisions tenant stacks
```

The org structure mirrors this:

```
Board (You)
    │
    ▼  Kickoff directive + OKRs
   CEO (Quinn)
    │
    ├── Core Infra  (declared)        ── Dana (Director)
    │     ├── backend-engineer        Django/DRF/Postgres/Celery
    │     ├── platform-engineer       auth-web host, CI, infra
    │     └── package-maintainer      @startsimpli/* shared packages
    │
    ├── raise   (self-forming)        ── Remy (Lead) → hires ICs after discovery
    │
    └── market  (self-forming)        ── Mara (Lead) → hires ICs after discovery
```

**Core Infra is declared** because the platform foundations are known up front
and stable. **App Groups self-form** because each Lead should make sense of its
slice (raise, market) before committing to a team shape — discovery, then
execution.

## Quick Start

```bash
# 1. Set up your API key
export ANTHROPIC_API_KEY="sk-ant-..."

# 2. Make sure the host monorepo is present at /Users/qosha/Repos/start-simpli

# 3. Initialize the org from org.yml
./setup.sh

# 4. Start the org and send the kickoff directive
./run.sh

# 5. Watch Core Infra work and the app groups self-form
./observe.sh

# 6. Clean up when done (host repo is never touched)
./cleanup.sh
```

## How It Runs (Host Mode)

This org runs against the live monorepo declared in `org.yml`:

```yaml
host:
  project_root: /Users/qosha/Repos/start-simpli
```

Workers operate inside that repo rather than a generated scratch project. The
QuinnAI org state (db, channels, org-chart) lives separately under
`generated-orgs/start-simpli/` and is the only thing `cleanup.sh` removes.

> **Note:** `qn org init --from org.yml` is provided by the org.yml loader being
> built in parallel (bead quinn-ai-a3pg.2.4.3). Until that loader lands,
> `setup.sh` will fail at the init step — `org.yml` is the source of truth for
> the intended structure in the meantime.

## What This Demonstrates

| Concept | How It's Shown |
|---------|----------------|
| Declarative org spec | Whole org defined in `org.yml` (quinnai/v1) |
| Host mode | Workers run against a real monorepo, not a scratch dir |
| Hybrid structure | Core Infra declared; app groups self-form |
| Team templates | `core-infra` + `app-group` in `config/templates.yaml` |
| Delegated budgets | Director gets 20k; each Lead gets 5k |
| OKRs with owners | One owner per objective, key results with targets |
| Profile conventions | `profiles/simpli.yaml` injects house rules into briefings |

## Configuration

| File | Purpose |
|------|---------|
| `org.yml` | Declarative org spec (host, toolchain, structure, delegations, OKRs) |
| `config/providers.yaml` | Authorized providers (claude_code default, anthropic via `${ANTHROPIC_API_KEY}`) |
| `config/worker-templates.yaml` | Role profiles (skills/cost/authority) for Simpli roles |
| `config/templates.yaml` | Team templates: `core-infra` (declared) and `app-group` (self-forming) |
| `profiles/simpli.yaml` | Simpli conventions injected into worker briefings |

### Simpli conventions (`profiles/simpli.yaml`)

- Shared packages over app src
- camelCase on the wire (Django DRF + `@startsimpli/api`)
- TypeScript must compile after every change
- MCP browser verification is the default for UI changes
- Server-side pagination for all tables
- Generic, reusable data models
- Foundry (`apps/foundry`) is the control plane for tenant stacks

## Troubleshooting

| Problem | Solution |
|---------|----------|
| "host project not found" | Clone start-simpli to `/Users/qosha/Repos/start-simpli` |
| `qn org init --from` fails | Loader still in progress (bead quinn-ai-a3pg.2.4.3) |
| "ANTHROPIC_API_KEY not set" | `export ANTHROPIC_API_KEY="sk-ant-..."` before `./run.sh` |
| App groups never form | Leads do discovery first; give them context, check their sessions |

## Next Steps

- [startup-team](../startup-team/) — simpler multi-worker hiring flow
- [okr-driven](../okr-driven/) — OKR cascade in a scratch org
- Adapt `org.yml` to point at your own monorepo and roles
