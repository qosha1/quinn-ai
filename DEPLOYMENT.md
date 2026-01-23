# QuinnAI Deployment Guide

Running QuinnAI orgs in different environments.

## Overview

QuinnAI runs AI worker organizations locally. Each org is self-contained in a folder with its own database, config, and worker sessions. This guide covers deployment scenarios from local development to running orgs on a server.

## Deployment Scenarios

### 1. Local Development (Your Machine)

The simplest setup. Run orgs directly on your laptop.

**Requirements:**
- Python 3.11+
- tmux
- At least one provider API key

**Setup:**
```bash
# Install QuinnAI
pip install quinnai

# Set API key
export ANTHROPIC_API_KEY="sk-ant-..."

# Run an org
cd example_orgs/org-scripts/hello-world
./setup.sh && ./run.sh
```

**Pros:** Zero config, immediate feedback, easy debugging
**Cons:** Stops when laptop sleeps/closes

---

### 2. Single-Machine Server

Run orgs on a Linux server for continuous operation. Good for personal use or small teams.

**Requirements:**
- Linux server (Ubuntu 22.04 LTS recommended)
- Python 3.11+
- tmux
- SSH access

#### Initial Setup

```bash
# On server - install dependencies
sudo apt update
sudo apt install -y python3.11 python3.11-venv tmux git

# Create a dedicated user (optional but recommended)
sudo useradd -m -s /bin/bash quinnai
sudo -u quinnai -i

# Install QuinnAI
python3.11 -m venv ~/.quinnai-venv
source ~/.quinnai-venv/bin/activate
pip install quinnai
```

#### Environment Variables

Create `/home/quinnai/.quinnai-env`:

```bash
# Provider API keys
export ANTHROPIC_API_KEY="sk-ant-..."
export OPENAI_API_KEY="sk-..."

# Optional: logging level
export QUINN_LOG_LEVEL="INFO"
```

Source it in `.bashrc`:
```bash
echo 'source ~/.quinnai-env' >> ~/.bashrc
```

#### Running Orgs

```bash
# SSH into server
ssh your-server

# Activate environment
source ~/.quinnai-venv/bin/activate

# Initialize org in dedicated location
mkdir -p ~/orgs
cd ~/orgs
qn org init my-startup

# Start org (runs in tmux)
qn org start my-startup
```

#### Persisting Across SSH Disconnects

Worker sessions run in tmux, which persists after SSH disconnect. However, you need a way to restart orgs after server reboot.

**Option A: Manual start after reboot**
```bash
# After reboot, reconnect and start
qn org start my-startup
```

**Option B: systemd service (recommended)**

Create `/etc/systemd/system/quinnai-org@.service`:

```ini
[Unit]
Description=QuinnAI Org: %i
After=network.target

[Service]
Type=forking
User=quinnai
Environment="PATH=/home/quinnai/.quinnai-venv/bin:/usr/bin"
EnvironmentFile=/home/quinnai/.quinnai-env
WorkingDirectory=/home/quinnai/orgs/%i
ExecStart=/home/quinnai/.quinnai-venv/bin/qn org start
ExecStop=/home/quinnai/.quinnai-venv/bin/qn org stop
Restart=on-failure
RestartSec=10

[Install]
WantedBy=multi-user.target
```

Enable and start:
```bash
sudo systemctl daemon-reload
sudo systemctl enable quinnai-org@my-startup
sudo systemctl start quinnai-org@my-startup
```

---

### 3. Multiple Orgs on One Server

Run several independent orgs on the same machine.

#### Folder Structure

```
/home/quinnai/orgs/
├── startup-alpha/
│   ├── config/
│   ├── live/
│   ├── org-chart/
│   └── storage/
├── startup-beta/
│   └── ...
└── research-lab/
    └── ...
```

#### Resource Considerations

Each active worker is a tmux session with an LLM context. Memory usage depends on:
- Number of active workers across all orgs
- Provider context sizes
- Worker activity patterns

**Rough sizing:**
- Small org (CEO + 2 workers): ~500MB RAM active
- Medium org (10 workers): ~2GB RAM active
- Large org (50+ workers): Consider dedicated server or multiple machines

#### Managing Multiple Orgs

```bash
# Check status of all orgs
for org in ~/orgs/*/; do
  echo "=== $(basename $org) ==="
  qn org status "$(basename $org)"
done

# Stop all orgs
for org in ~/orgs/*/; do
  qn org stop "$(basename $org)"
done
```

---

## Worker Session Management

Workers run in tmux sessions. Understanding tmux is key to debugging.

### Viewing Worker Sessions

```bash
# List all tmux sessions
tmux ls

# Attach to a specific worker
tmux attach -t org-name-worker-id

# Detach without stopping: Ctrl+B, D
```

### Session Persistence

- **On SSH disconnect:** Sessions continue running
- **On server reboot:** Sessions are lost (restart org with `qn org start`)
- **On `qn org stop`:** Sessions are cleanly terminated

### Debugging a Stuck Worker

```bash
# Attach to worker session
tmux attach -t my-org-ceo

# View what it's doing (you'll see the Claude/OpenAI conversation)
# Detach: Ctrl+B, D

# If truly stuck, kill and restart
tmux kill-session -t my-org-ceo
qn wrkr restart ceo  # Respawn the worker
```

---

## Environment Variables

### Required

| Variable | Description |
|----------|-------------|
| `ANTHROPIC_API_KEY` | Anthropic API key (for Claude-based workers) |

### Optional

| Variable | Default | Description |
|----------|---------|-------------|
| `OPENAI_API_KEY` | - | OpenAI API key (for GPT-based workers) |
| `QUINN_LOG_LEVEL` | `INFO` | Logging verbosity: DEBUG, INFO, WARNING, ERROR |
| `QUINN_DATA_DIR` | `~/.quinnai` | Default location for CLI data |

### Per-Org Environment

Each org can have its own `.env` file:

```
my-org/
├── .env           # Org-specific overrides
└── config/
    └── providers.yaml
```

Org `.env` overrides system environment for that org only.

---

## Secrets Management

**Never commit API keys to git.**

### Local Development

Use shell environment or `.envrc` with direnv:

```bash
# .envrc (gitignored)
export ANTHROPIC_API_KEY="sk-ant-..."
```

### Server Deployment

**Option A: Environment file**
```bash
# /home/quinnai/.quinnai-env (chmod 600)
export ANTHROPIC_API_KEY="sk-ant-..."
```

**Option B: Secrets manager**

For production, consider:
- HashiCorp Vault
- AWS Secrets Manager
- 1Password CLI

Example with 1Password:
```bash
export ANTHROPIC_API_KEY=$(op read "op://QuinnAI/Anthropic/api-key")
```

---

## Monitoring and Logs

### Org Status

```bash
# Quick status check
qn org status my-org

# Output shows:
# - Org state (initialized, running, stopped)
# - Active workers
# - Recent activity
```

### Log Locations

```
my-org/
└── live/
    ├── quinn.db        # SQLite - all org data
    ├── logs/
    │   ├── org.log     # Org-level events
    │   └── workers/
    │       ├── ceo.log
    │       └── dev-1.log
    └── workers/
        └── ceo/
            └── session.log  # Raw tmux output
```

### Watching Logs

```bash
# Tail org log
tail -f my-org/live/logs/org.log

# Watch specific worker
tail -f my-org/live/logs/workers/ceo.log
```

### Health Checks

Simple cron-based monitoring:

```bash
# /etc/cron.d/quinnai-health
*/5 * * * * quinnai /home/quinnai/.quinnai-venv/bin/qn org status my-org | grep -q "running" || echo "Org down" | mail -s "QuinnAI Alert" you@email.com
```

---

## Backup and Recovery

### What to Backup

```
my-org/
├── config/           # BACKUP: Provider and worker settings
├── live/
│   └── quinn.db      # BACKUP: All org state (beads, messages, workers)
├── org-chart/        # BACKUP: Hierarchy snapshots (git-tracked anyway)
└── storage/          # BACKUP: Persistent org files
```

### Backup Script

```bash
#!/bin/bash
# /usr/local/bin/backup-quinnai.sh

ORG_DIR="/home/quinnai/orgs/my-org"
BACKUP_DIR="/var/backups/quinnai"
DATE=$(date +%Y%m%d_%H%M%S)

mkdir -p "$BACKUP_DIR"

# Stop org briefly for consistent backup
qn org stop my-org

# Backup critical files
tar -czf "$BACKUP_DIR/my-org-$DATE.tar.gz" \
  "$ORG_DIR/config" \
  "$ORG_DIR/live/quinn.db" \
  "$ORG_DIR/org-chart" \
  "$ORG_DIR/storage"

# Restart org
qn org start my-org

# Keep last 7 days
find "$BACKUP_DIR" -name "my-org-*.tar.gz" -mtime +7 -delete
```

Add to crontab:
```bash
0 3 * * * /usr/local/bin/backup-quinnai.sh
```

### Recovery

```bash
# Extract backup
tar -xzf my-org-20240115_030000.tar.gz -C /

# Restart org
qn org start my-org
```

---

## Troubleshooting

### Org Won't Start

```bash
# Check org state
qn org status my-org

# Common issues:
# 1. Missing API key
echo $ANTHROPIC_API_KEY  # Should show key

# 2. tmux not installed
which tmux  # Should return path

# 3. Python environment not activated
which qn  # Should show venv path
```

### Workers Not Responding

```bash
# List tmux sessions
tmux ls

# If sessions exist but workers unresponsive:
# 1. Check provider API status
curl -s https://status.anthropic.com

# 2. Check API key is valid
qn provider test anthropic

# 3. View worker session for errors
tmux attach -t my-org-ceo
```

### High Memory Usage

```bash
# Check memory per worker
ps aux | grep tmux

# If runaway:
# 1. Stop specific worker
qn wrkr stop worker-id

# 2. Or stop entire org
qn org stop my-org
```

### Database Locked

```bash
# SQLite lock issues (rare)
# 1. Stop all org activity
qn org stop my-org

# 2. Check for stale locks
lsof my-org/live/quinn.db

# 3. Kill any orphaned processes
kill <pid>

# 4. Restart
qn org start my-org
```

---

## Security Considerations

1. **API Keys**: Store securely, never commit to git
2. **Server Access**: Use SSH keys, disable password auth
3. **Worker Sessions**: Workers can execute commands - understand your provider's sandbox
4. **Network**: Orgs make outbound API calls only; no inbound ports required
5. **Backups**: Encrypt if storing off-server (backups contain org history)

---

## What's NOT Covered

This deployment model is for CLI-based QuinnAI orgs. For future features:

- **Web Dashboard**: Will have separate deployment docs when built
- **Multi-Machine Clusters**: Not yet supported
- **Kubernetes**: Not applicable to tmux-based workers
