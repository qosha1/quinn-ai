# QuinnAI Organization Troubleshooting

## Common Issues

### ❌ "API key is required but not set"

**Problem:** Trying to start the org without setting the Anthropic API key.

**Solution:**
```bash
# Set the API key
export ANTHROPIC_API_KEY='sk-ant-...'

# Verify it's set
echo $ANTHROPIC_API_KEY

# Start the org
./start.sh
```

**Make it permanent:**
```bash
# Add to your shell profile
echo 'export ANTHROPIC_API_KEY="sk-ant-..."' >> ~/.zshrc
source ~/.zshrc
```

---

### ❌ "Organization not initialized"

**Problem:** Trying to start an org that hasn't been initialized.

**Solution:**
```bash
# Initialize the org first
qn --org-path . org init --ceo-name="Quinn" --ceo-role="CEO"

# Then start it
./start.sh
```

---

### ❌ CEO Runtime Status: "crashed"

**Problem:** The CEO session started but immediately crashed.

**Possible causes:**
1. API key not set or invalid
2. No internet connection
3. Provider configuration error

**Solution:**
```bash
# 1. Check API key
echo $ANTHROPIC_API_KEY  # Should output your key

# 2. Test API connection
curl -H "x-api-key: $ANTHROPIC_API_KEY" \
     https://api.anthropic.com/v1/messages \
     -H "anthropic-version: 2023-06-01" \
     -H "content-type: application/json" \
     -d '{"model":"claude-3-sonnet-20240229","max_tokens":10,"messages":[{"role":"user","content":"test"}]}'

# 3. Stop and restart
qn --org-path . org stop
./start.sh

# 4. Check logs
qn --org-path . org logs --worker ceo
```

---

### ❌ Can't connect to org / observe doesn't work

**Problem:** Can't attach to CEO session or see output.

**Solution:**
```bash
# Check if tmux is installed
tmux -V

# Check if session exists
tmux ls

# Check worker sessions
qn --org-path . org status

# View logs instead of live session
qn --org-path . org logs --worker ceo --tail 50
```

---

### ❌ "No such option: --org-path"

**Problem:** Trying to use `--org-path` after the subcommand.

**Solution:**
```bash
# ❌ Wrong order
qn org start --org-path .

# ✅ Correct order
qn --org-path . org start
```

---

### ❌ Commands work in shell but not in scripts

**Problem:** `qn` or `bd` commands not found when running scripts.

**Solution:**
```bash
# Add to your PATH
which qn  # Check if installed
which bd  # Check if installed

# If not found, reinstall
cd /Users/qosha/Repos/small-bizs/agentic-tools/quinnai
python -m pip install -e . --break-system-packages
```

---

## Diagnostic Commands

### Check Org Status
```bash
qn --org-path . org status
```

### View Worker Sessions
```bash
qn --org-path . org status
# Look for "Active" and "Sessions" counts
```

### Check Database
```bash
sqlite3 live/quinn.db "SELECT name, role, lifecycle_status FROM workers;"
```

### View Logs
```bash
# Worker logs
qn --org-path . org logs --worker ceo

# System logs
ls -la live/logs/
```

### Check Beads
```bash
cd org
bd list --status=open
bd stats
bd sync --status
```

---

## Reset and Start Fresh

If things are completely broken:

```bash
# 1. Stop everything
qn --org-path . org stop

# 2. Backup current state (optional)
cp -r live/ live.backup/
cp -r .beads/ .beads.backup/

# 3. Clean databases
rm live/quinn.db
rm .beads/beads.db

# 4. Re-initialize
qn --org-path . org init --ceo-name="Quinn" --ceo-role="CEO"

# 5. Restore beads (your OKRs and tasks)
cp .beads.backup/issues.jsonl .beads/issues.jsonl
bd sync

# 6. Start fresh
./start.sh
```

---

## Getting Help

1. **Check logs:** Always check `qn --org-path . org logs` first
2. **Verify config:** Check `config/providers.yaml` is valid
3. **Test API key:** Make sure your Anthropic API key works
4. **Check versions:** Ensure QuinnAI CLI is latest version

**Still stuck?** Open an issue with:
- Error message
- Output of `qn --org-path . org status`
- Relevant logs
- Steps to reproduce
