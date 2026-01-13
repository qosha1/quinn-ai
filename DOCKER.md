# Docker Infrastructure Guide

Complete Docker setup for the B2B SaaS template with development and production configurations.

## Architecture Overview

### Development Environment
- Django API (localhost:8000)
- PostgreSQL database
- Redis (cache and Celery broker)
- Celery worker and beat scheduler
- NextJS Landing page (localhost:3000)
- NextJS App dashboard (localhost:3001)
- Nginx reverse proxy (localhost:80)

### Production Environment
- All development services plus:
- Traefik reverse proxy with automatic SSL (Let's Encrypt)
- Multi-stage builds for optimized images
- Separate networks for security
- Production-grade Gunicorn configuration
- Static/media file serving via CDN-ready Nginx

## Quick Start

### Initial Setup

1. Copy environment files:
```bash
make setup
```

2. Edit environment files:
```bash
# Edit local Django settings
vim .envs/.local/.django

# Edit local PostgreSQL settings
vim .envs/.local/.postgres
```

3. Start all services:
```bash
make up
```

4. Access the services:
- Django API: http://localhost:8000/api/
- Landing page: http://localhost:3000
- App dashboard: http://localhost:3001
- Django admin: http://localhost:8000/admin/

## Development Commands

```bash
# Container management
make up              # Start all services
make down            # Stop all services
make restart         # Restart all services
make ps              # List running containers
make logs            # View all logs
make logs-django     # View Django logs only

# Django management
make shell           # Open Django shell
make bash            # Open bash in Django container
make migrate         # Run database migrations
make makemigrations  # Create new migrations
make createsuperuser # Create superuser
make test            # Run tests

# Database operations
make backup-db       # Backup database to SQL file
make restore-db file=backup.sql  # Restore from backup

# Cleanup
make clean           # Remove all containers and images
make clean-volumes   # Remove volumes (WARNING: deletes data)
```

## Environment Configuration

### Local Development (.envs/.local/)

Required files (created from .example templates):
- `.django` - Django settings (SECRET_KEY, database, APIs)
- `.postgres` - PostgreSQL credentials

### Production (.envs/.production/)

Required files:
- `.django` - Production Django settings with SSL, S3, etc.
- `.postgres` - Production database credentials
- `.traefik` - Domain and Let's Encrypt configuration

## Service Details

### Django (Backend API)
- **Port**: 8000 (local), 5000 (production via Gunicorn)
- **Hot reload**: Enabled in development
- **Health check**: /api/health/
- **Dependencies**: PostgreSQL, Redis

### PostgreSQL
- **Port**: 5432 (exposed locally for tools)
- **Data persistence**: Named volume
- **Backups**: Use `make backup-db`

### Redis
- **Port**: 6379 (not exposed)
- **Usage**: Cache and Celery broker
- **Persistence**: AOF enabled in production

### Celery
- **Worker**: Handles async tasks
- **Beat**: Scheduled tasks
- **Monitoring**: Logs via `make logs-celery`

### NextJS Applications
- **Landing**: Port 3000
- **App**: Port 3001
- **Hot reload**: Full support with webpack HMR
- **Production**: Static builds with standalone output

### Nginx (Development)
- **Port**: 80
- **Purpose**: Reverse proxy for all services
- **Features**: Gzip, caching, WebSocket support

### Traefik (Production)
- **Ports**: 80 (HTTP), 443 (HTTPS)
- **Features**: Auto SSL via Let's Encrypt
- **Dashboard**: traefik.yourdomain.com (auth protected)
- **Monitoring**: Prometheus metrics enabled

## Production Deployment

### Prerequisites
1. Domain name pointing to your server
2. Docker and Docker Compose installed
3. Environment files configured

### Deployment Steps

1. Create production environment files:
```bash
cp .envs/.production/.django.example .envs/.production/.django
cp .envs/.production/.postgres.example .envs/.production/.postgres
cp .envs/.production/.traefik.example .envs/.production/.traefik
```

2. Update all production environment files with real values:
- Set strong SECRET_KEY
- Configure database credentials
- Add domain name and Let's Encrypt email
- Configure Stripe live keys
- Set up S3 credentials (recommended)

3. Build and start production services:
```bash
make build-prod
make up-prod
```

4. Verify SSL certificates:
```bash
make logs-prod | grep "traefik"
```

### Production Environment Variables

Critical settings in `.envs/.production/.django`:
- `DEBUG=False`
- `SECRET_KEY` - Strong random string
- `ALLOWED_HOSTS` - Your domain(s)
- `DATABASE_URL` - PostgreSQL connection string
- `STRIPE_SECRET_KEY` - Live Stripe key
- `AWS_*` - S3 credentials for media storage
- SSL and security headers enabled

### SSL Certificates

Traefik automatically obtains and renews Let's Encrypt certificates for:
- yourdomain.com (Landing page)
- app.yourdomain.com (Dashboard)
- api.yourdomain.com (Django API)
- cdn.yourdomain.com (Static/media files)
- traefik.yourdomain.com (Traefik dashboard)

Certificates are stored in the `saas-traefik-certs` volume.

## Network Architecture

### Development
Single network with all services accessible to each other.

### Production
Two isolated networks:
- `backend` - Database, Redis, Django, Celery
- `traefik` - External-facing services

Only services that need external access are in the traefik network.

## Volume Management

### Development Volumes
- `saas-postgres-data` - PostgreSQL data
- `saas-redis-data` - Redis persistence

### Production Volumes
- `saas-postgres-prod-data` - Database
- `saas-postgres-prod-backups` - Backup storage
- `saas-redis-prod-data` - Redis
- `saas-static-prod` - Static files
- `saas-media-prod` - User uploads
- `saas-traefik-certs` - SSL certificates

### Backup Strategy

Development:
```bash
make backup-db  # Creates timestamped SQL backup
```

Production:
```bash
# Backup database
docker-compose -f docker-compose.production.yml exec -T postgres \
  pg_dump -U username dbname > backup.sql

# Backup volumes
docker run --rm -v saas-postgres-prod-data:/data \
  -v $(pwd):/backup alpine tar czf /backup/postgres-data.tar.gz /data
```

## Health Checks

All services include health checks:
- Django: HTTP check on /api/health/
- PostgreSQL: pg_isready
- Redis: redis-cli ping
- NextJS: HTTP check on /api/health
- Nginx: nginx -t

Monitor health:
```bash
docker-compose -f docker-compose.local.yml ps
```

## Troubleshooting

### Services won't start
```bash
# Check logs
make logs

# Check specific service
make logs-django

# Verify environment files exist
ls .envs/.local/
```

### Database connection errors
```bash
# Check PostgreSQL is healthy
docker-compose -f docker-compose.local.yml ps postgres

# Check credentials in .envs/.local/.postgres
# Ensure they match in .envs/.local/.django
```

### Port already in use
```bash
# Check what's using the port
lsof -i :8000

# Stop conflicting service or change port in docker-compose
```

### Permission errors
```bash
# Fix ownership (Linux)
sudo chown -R $USER:$USER .

# Rebuild containers
make build
```

### NextJS hot reload not working
```bash
# Ensure volumes are correctly mounted
docker-compose -f docker-compose.local.yml exec landing ls -la /app

# Restart the service
docker-compose -f docker-compose.local.yml restart landing
```

### Production SSL issues
```bash
# Check Traefik logs
make logs-prod | grep "traefik"

# Verify DNS points to server
dig yourdomain.com

# Check Let's Encrypt rate limits
# Test with staging first by editing traefik.yml
```

## Security Best Practices

1. Never commit actual .env files (only .example files)
2. Use strong SECRET_KEY (50+ random characters)
3. Change default database passwords
4. Enable security headers in production
5. Use S3 or similar for media in production
6. Regularly update base images
7. Scan images for vulnerabilities: `make security-scan`
8. Obscure admin URL in production
9. Enable Sentry or logging service
10. Regular database backups

## Performance Optimization

### Development
- Use volumes for hot reload
- Minimize number of layers in Dockerfiles
- Use .dockerignore to exclude unnecessary files

### Production
- Multi-stage builds reduce image size
- Gunicorn workers tuned for CPU cores
- Static files served directly by Nginx
- Gzip compression enabled
- Browser caching headers set
- Use CDN for static/media (S3 + CloudFront)

## Monitoring

### Logs
```bash
# All services
make logs

# Specific service
make logs-django
make logs-celery

# Production
make logs-prod
```

### Metrics
Traefik exposes Prometheus metrics at `/metrics`:
- Request counts
- Response times
- Error rates

Integrate with Grafana for visualization.

## Maintenance

### Update dependencies
```bash
# Backend
docker-compose -f docker-compose.local.yml exec django pip install -U -r /requirements/local.txt

# Frontend
docker-compose -f docker-compose.local.yml exec landing npm update
```

### Update base images
```bash
# Pull latest base images
docker pull python:3.12-slim
docker pull node:20-alpine
docker pull postgres:16-alpine

# Rebuild
make build
```

### Database maintenance
```bash
# Vacuum database
docker-compose -f docker-compose.production.yml exec postgres \
  vacuumdb -U username -d dbname -v

# Analyze tables
docker-compose -f docker-compose.production.yml exec postgres \
  vacuumdb -U username -d dbname --analyze
```

## Additional Resources

- [Docker Compose documentation](https://docs.docker.com/compose/)
- [Traefik documentation](https://doc.traefik.io/traefik/)
- [Django deployment checklist](https://docs.djangoproject.com/en/5.0/howto/deployment/checklist/)
- [NextJS deployment](https://nextjs.org/docs/deployment)
