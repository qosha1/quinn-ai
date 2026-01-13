# Production Deployment Checklist

Complete guide for deploying the B2B SaaS template to production.

## Pre-Deployment Checklist

### Infrastructure Requirements
- [ ] Linux server (Ubuntu 22.04 LTS recommended)
- [ ] Minimum 2GB RAM, 2 CPU cores
- [ ] 20GB+ storage
- [ ] Domain name with DNS access
- [ ] Docker and Docker Compose installed
- [ ] Firewall configured (ports 80, 443 open)

### Service Accounts
- [ ] Stripe account (live mode enabled)
- [ ] Email service (SendGrid, Mailgun, or SMTP)
- [ ] AWS account for S3 (recommended)
- [ ] Sentry account (optional but recommended)

### DNS Configuration
Point your domain records to your server IP:

```
A     @               -> YOUR_SERVER_IP
A     www             -> YOUR_SERVER_IP
A     app             -> YOUR_SERVER_IP
A     api             -> YOUR_SERVER_IP
A     cdn             -> YOUR_SERVER_IP
A     traefik         -> YOUR_SERVER_IP (optional)
```

Wait for DNS propagation (check with `dig yourdomain.com`).

## Server Setup

### 1. Install Docker
```bash
# Update system
sudo apt update && sudo apt upgrade -y

# Install Docker
curl -fsSL https://get.docker.com -o get-docker.sh
sudo sh get-docker.sh

# Install Docker Compose
sudo curl -L "https://github.com/docker/compose/releases/latest/download/docker-compose-$(uname -s)-$(uname -m)" -o /usr/local/bin/docker-compose
sudo chmod +x /usr/local/bin/docker-compose

# Add user to docker group
sudo usermod -aG docker $USER
newgrp docker
```

### 2. Clone Repository
```bash
git clone <your-repo-url>
cd b2b-saas-template
```

### 3. Configure Firewall
```bash
# UFW (Ubuntu)
sudo ufw allow 22/tcp   # SSH
sudo ufw allow 80/tcp   # HTTP
sudo ufw allow 443/tcp  # HTTPS
sudo ufw enable
```

## Environment Configuration

### 1. Create Production Environment Files

```bash
# Create directories
mkdir -p .envs/.production

# Copy templates
cp .envs/.production/.django.example .envs/.production/.django
cp .envs/.production/.postgres.example .envs/.production/.postgres
cp .envs/.production/.traefik.example .envs/.production/.traefik
```

### 2. Configure Django (.envs/.production/.django)

```bash
# Generate a secure secret key
python3 -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"
```

Critical settings:
```env
DEBUG=False
SECRET_KEY=<generated-secret-key>
ALLOWED_HOSTS=yourdomain.com,api.yourdomain.com,app.yourdomain.com

# Database (use strong password)
DATABASE_URL=postgres://saas_prod_user:STRONG_PASSWORD_HERE@postgres:5432/saas_production

# Email (example with SendGrid)
EMAIL_BACKEND=django.core.mail.backends.smtp.EmailBackend
EMAIL_HOST=smtp.sendgrid.net
EMAIL_PORT=587
EMAIL_USE_TLS=True
EMAIL_HOST_USER=apikey
EMAIL_HOST_PASSWORD=<sendgrid-api-key>
DEFAULT_FROM_EMAIL=noreply@yourdomain.com

# CORS
CORS_ALLOWED_ORIGINS=https://yourdomain.com,https://app.yourdomain.com

# Security
CSRF_TRUSTED_ORIGINS=https://yourdomain.com,https://api.yourdomain.com,https://app.yourdomain.com
SECURE_SSL_REDIRECT=True
SESSION_COOKIE_SECURE=True
CSRF_COOKIE_SECURE=True

# Stripe (LIVE keys)
STRIPE_SECRET_KEY=sk_live_<your-live-key>
STRIPE_PUBLISHABLE_KEY=pk_live_<your-live-key>
STRIPE_WEBHOOK_SECRET=whsec_<your-webhook-secret>

# AWS S3 (recommended for production)
USE_S3=True
AWS_ACCESS_KEY_ID=<your-access-key>
AWS_SECRET_ACCESS_KEY=<your-secret-key>
AWS_STORAGE_BUCKET_NAME=<your-bucket-name>
AWS_S3_REGION_NAME=us-east-1

# Sentry (optional)
SENTRY_DSN=https://<your-sentry-dsn>

# Domain
DOMAIN_NAME=yourdomain.com
```

### 3. Configure PostgreSQL (.envs/.production/.postgres)

```env
POSTGRES_HOST=postgres
POSTGRES_PORT=5432
POSTGRES_DB=saas_production
POSTGRES_USER=saas_prod_user
POSTGRES_PASSWORD=<generate-strong-password>
```

Generate strong password:
```bash
openssl rand -base64 32
```

### 4. Configure Traefik (.envs/.production/.traefik)

```env
DOMAIN_NAME=yourdomain.com
LETSENCRYPT_EMAIL=admin@yourdomain.com

# Generate basic auth password
# htpasswd -nb admin your_password | sed -e s/\\$/\\$\\$/g
TRAEFIK_DASHBOARD_AUTH=admin:$$apr1$$...
```

## Build and Deploy

### 1. Build Production Images
```bash
docker-compose -f docker-compose.production.yml build
```

### 2. Start Services
```bash
docker-compose -f docker-compose.production.yml up -d
```

### 3. Monitor Startup
```bash
# Watch logs
docker-compose -f docker-compose.production.yml logs -f

# Check service health
docker-compose -f docker-compose.production.yml ps
```

### 4. Verify SSL Certificates
```bash
# Check Traefik logs for Let's Encrypt
docker-compose -f docker-compose.production.yml logs traefik | grep -i "certificate"

# Test HTTPS
curl -I https://yourdomain.com
curl -I https://api.yourdomain.com
```

## Post-Deployment

### 1. Create Django Superuser
```bash
docker-compose -f docker-compose.production.yml exec django python manage.py createsuperuser
```

### 2. Configure Stripe Webhooks
1. Go to https://dashboard.stripe.com/webhooks
2. Add endpoint: `https://api.yourdomain.com/api/webhooks/stripe/`
3. Select events to listen for
4. Copy webhook secret to `.envs/.production/.django`

### 3. Set Up Database Backups

Create backup script `/usr/local/bin/backup-saas-db.sh`:
```bash
#!/bin/bash
BACKUP_DIR="/var/backups/saas"
DATE=$(date +%Y%m%d_%H%M%S)

mkdir -p $BACKUP_DIR

docker-compose -f /path/to/b2b-saas-template/docker-compose.production.yml exec -T postgres \
  pg_dump -U saas_prod_user saas_production | gzip > $BACKUP_DIR/backup_$DATE.sql.gz

# Keep only last 7 days of backups
find $BACKUP_DIR -name "backup_*.sql.gz" -mtime +7 -delete
```

Add to crontab:
```bash
# Daily backup at 2 AM
0 2 * * * /usr/local/bin/backup-saas-db.sh
```

### 4. Configure Monitoring

Set up basic monitoring with cron:
```bash
# Health check every 5 minutes
*/5 * * * * curl -f https://yourdomain.com/api/health/ || echo "Health check failed" | mail -s "Site Down" admin@yourdomain.com
```

## Security Hardening

### 1. Update Traefik Dashboard Auth
```bash
# Generate new password
htpasswd -nb admin new_secure_password | sed -e s/\\$/\\$\\$/g

# Update .envs/.production/.traefik
# Restart Traefik
docker-compose -f docker-compose.production.yml restart traefik
```

### 2. Enable Automatic Updates
```bash
sudo apt install unattended-upgrades
sudo dpkg-reconfigure --priority=low unattended-upgrades
```

### 3. Set Up Fail2Ban
```bash
sudo apt install fail2ban
sudo systemctl enable fail2ban
sudo systemctl start fail2ban
```

### 4. Regular Security Scans
```bash
# Install Trivy
curl -sfL https://raw.githubusercontent.com/aquasecurity/trivy/main/contrib/install.sh | sh -s -- -b /usr/local/bin

# Scan images
trivy image <image-name>
```

## Maintenance

### Update Application
```bash
# Pull latest code
git pull

# Rebuild images
docker-compose -f docker-compose.production.yml build

# Rolling update (zero downtime)
docker-compose -f docker-compose.production.yml up -d --no-deps --build django

# Run migrations
docker-compose -f docker-compose.production.yml exec django python manage.py migrate
```

### View Logs
```bash
# All services
docker-compose -f docker-compose.production.yml logs -f

# Specific service
docker-compose -f docker-compose.production.yml logs -f django

# Last 100 lines
docker-compose -f docker-compose.production.yml logs --tail=100
```

### Database Maintenance
```bash
# Backup
docker-compose -f docker-compose.production.yml exec -T postgres \
  pg_dump -U saas_prod_user saas_production > backup.sql

# Restore
cat backup.sql | docker-compose -f docker-compose.production.yml exec -T postgres \
  psql -U saas_prod_user saas_production

# Vacuum
docker-compose -f docker-compose.production.yml exec postgres \
  vacuumdb -U saas_prod_user -d saas_production -v
```

### Scale Services
```bash
# Scale Celery workers
docker-compose -f docker-compose.production.yml up -d --scale celery-worker=4
```

## Disaster Recovery

### Full Backup
```bash
#!/bin/bash
BACKUP_DIR="/var/backups/saas/full_$(date +%Y%m%d)"
mkdir -p $BACKUP_DIR

# Backup database
docker-compose -f docker-compose.production.yml exec -T postgres \
  pg_dump -U saas_prod_user saas_production | gzip > $BACKUP_DIR/database.sql.gz

# Backup volumes
docker run --rm \
  -v saas-postgres-prod-data:/data \
  -v $BACKUP_DIR:/backup \
  alpine tar czf /backup/postgres-data.tar.gz /data

docker run --rm \
  -v saas-media-prod:/data \
  -v $BACKUP_DIR:/backup \
  alpine tar czf /backup/media-data.tar.gz /data

# Backup config
cp -r .envs $BACKUP_DIR/

echo "Backup complete in $BACKUP_DIR"
```

### Restore
```bash
# Stop services
docker-compose -f docker-compose.production.yml down

# Restore volumes
docker run --rm \
  -v saas-postgres-prod-data:/data \
  -v /path/to/backup:/backup \
  alpine tar xzf /backup/postgres-data.tar.gz -C /

# Restore database
cat backup.sql | docker-compose -f docker-compose.production.yml exec -T postgres \
  psql -U saas_prod_user saas_production

# Start services
docker-compose -f docker-compose.production.yml up -d
```

## Rollback Procedure

If deployment fails:

```bash
# Stop new version
docker-compose -f docker-compose.production.yml down

# Checkout previous version
git checkout <previous-commit>

# Rebuild
docker-compose -f docker-compose.production.yml build

# Start
docker-compose -f docker-compose.production.yml up -d

# If database migrations were run, restore from backup
cat backup.sql | docker-compose -f docker-compose.production.yml exec -T postgres \
  psql -U saas_prod_user saas_production
```

## Performance Optimization

### Enable CDN
1. Set up CloudFront or similar CDN
2. Point CDN to `cdn.yourdomain.com`
3. Update `AWS_S3_CUSTOM_DOMAIN` in Django settings

### Database Optimization
```bash
# Create indexes
docker-compose -f docker-compose.production.yml exec django python manage.py sqlsequencereset app_name

# Analyze query performance
docker-compose -f docker-compose.production.yml exec postgres psql -U saas_prod_user saas_production -c "SELECT * FROM pg_stat_statements ORDER BY total_time DESC LIMIT 10;"
```

### Monitor Resource Usage
```bash
# Container stats
docker stats

# Disk usage
docker system df
```

## Troubleshooting

### SSL Certificate Issues
```bash
# Check Traefik logs
docker-compose -f docker-compose.production.yml logs traefik

# Verify DNS
dig yourdomain.com

# Test Let's Encrypt staging first (edit traefik.yml)
# Then switch to production
```

### Database Connection Issues
```bash
# Check PostgreSQL logs
docker-compose -f docker-compose.production.yml logs postgres

# Verify credentials
docker-compose -f docker-compose.production.yml exec postgres \
  psql -U saas_prod_user -d saas_production -c "\l"
```

### Memory Issues
```bash
# Increase swap
sudo fallocate -l 4G /swapfile
sudo chmod 600 /swapfile
sudo mkswap /swapfile
sudo swapon /swapfile

# Make permanent
echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab
```

## Support

For issues:
1. Check logs: `docker-compose -f docker-compose.production.yml logs`
2. Verify environment files are correct
3. Check DNS configuration
4. Review DOCKER.md for detailed troubleshooting

## Security Contacts

Report security issues to: security@yourdomain.com
