# quinn-ai

A QuinnAI organization - hierarchical AI workers collaborating on strategic objectives.

## Quick Start

### Start the Organization
```bash
qn org start
```

### Check Status
```bash
qn org status
```

### Stop the Organization
```bash
qn org stop
```

## Organization Structure

View the org chart:
```bash
qn org chart show
```

## Workers

### Hire a Worker
```bash
qn org hire --name="Alice" --role="Engineer" --manager=ceo
```

### Fire a Worker
```bash
qn org fire <worker-id> --reason="Performance issues"
```

### View Worker Status
```bash
qn wrkr list
```

## Work Tracking

All work is tracked in **beads** (our issue tracker):

```bash
# View all work
qn-bd list --status=open

# View ready work (no blockers)
qn-bd ready

# View strategic objectives (OKRs)
qn-bd list --label=okr
```

## Storage

Organization storage structure:
- `storage/shared/company/` - Org-wide documentation
- `storage/shared/{team}/` - Team collaboration spaces
- `storage/workers/{path}/` - Worker personal storage (mirrors org chart)

## Configuration

- `config/providers.yaml` - AI service providers
- `config/workflow.yaml` - Workflow rules and automation
- `config/worker-templates.yaml` - Worker session templates

## Documentation

- `storage/shared/company/QUICKSTART.md` - Worker quick reference
- `storage/shared/company/BEADS_WORKFLOW.md` - Complete beads guide
- `storage/shared/company/OKR_GUIDE.md` - Understanding OKRs

## Database

Organization state: `live/quinn.db`

View org status:
```bash
qn org status
```

## Monitoring

Launch the dashboard:
```bash
qn board ui
```

## Getting Help

Run `qn --help` for full command reference.