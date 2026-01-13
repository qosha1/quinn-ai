# Quick Start Guide

Get the B2B SaaS template running in 5 minutes.

## Prerequisites

- Docker Desktop installed and running
- Git
- Make (optional but recommended)

## Step 1: Setup Environment Files

Run the setup command to copy environment templates:

```bash
make setup
```

This creates:
- `.envs/.local/.django`
- `.envs/.local/.postgres`

## Step 2: Configure Environment

Edit `.envs/.local/.django` and update:

```bash
# Minimum required changes:
SECRET_KEY=your-long-random-secret-key-here

# Optional: Add your Stripe test keys if you want billing features
STRIPE_SECRET_KEY=sk_test_your_key
STRIPE_PUBLISHABLE_KEY=pk_test_your_key
```

Generate a secret key:
```bash
python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"
```

## Step 3: Start Services

```bash
make up
```

First run will take 5-10 minutes to:
- Download Docker images
- Build custom images
- Create database
- Run migrations
- Install dependencies

## Step 4: Access Applications

Once running, access:

- **Django API**: http://localhost:8000/api/
- **Django Admin**: http://localhost:8000/admin/ (admin@example.com / admin)
- **Landing Page**: http://localhost:3000
- **App Dashboard**: http://localhost:3001

## Step 5: Verify Everything Works

```bash
# Check all services are healthy
make ps

# View logs
make logs

# Test Django API
curl http://localhost:8000/api/health/
```

## Common Tasks

### View Logs
```bash
# All services
make logs

# Specific service
make logs-django
make logs-landing
make logs-app
```

### Django Management
```bash
# Open Django shell
make shell

# Create a superuser
make createsuperuser

# Run migrations
make migrate

# Run tests
make test
```

### Database Operations
```bash
# Backup database
make backup-db

# Restore from backup
make restore-db file=backup_20240101_120000.sql
```

### Stop Services
```bash
# Stop all containers
make down

# Stop and remove volumes (WARNING: deletes data)
make clean-volumes
```

## Troubleshooting

### Port already in use
```bash
# Find what's using port 8000
lsof -i :8000

# Kill the process or stop other Docker containers
docker ps
docker stop <container_id>
```

### Services not starting
```bash
# Check logs for errors
make logs

# Rebuild containers
make build
make up
```

### Database connection errors
```bash
# Verify PostgreSQL is running
docker ps | grep postgres

# Check credentials match in both .django and .postgres files
cat .envs/.local/.django | grep POSTGRES
cat .envs/.local/.postgres
```

### Permission errors (Linux)
```bash
sudo chown -R $USER:$USER .
make build
```

## Next Steps

1. Explore the Django API at http://localhost:8000/api/
2. Check out the admin interface at http://localhost:8000/admin/
3. Review the OpenSpec documentation in `openspec/`
4. Read the full Docker guide in `DOCKER.md`
5. Start building your features!

## Development Workflow

```bash
# Start your day
make up

# Watch logs while developing
make logs

# Run tests
make test

# Create database migrations
make makemigrations
make migrate

# End of day
make down
```

## Help

Run `make help` to see all available commands.

For detailed documentation, see:
- `DOCKER.md` - Complete Docker infrastructure guide
- `README.md` - Project overview
- `openspec/` - Feature specifications
