# B2B SaaS Backend

Django 5.1+ REST API backend for B2B SaaS template.

## Stack

- **Framework**: Django 5.1+
- **API**: Django REST Framework 3.14+
- **Database**: PostgreSQL with psycopg3
- **Cache/Queue**: Redis
- **Task Queue**: Celery 5.3+
- **Auth**: JWT (Simple JWT)
- **Documentation**: OpenAPI 3.0 (drf-spectacular)

## Quick Start

### 1. Install Dependencies

```bash
# Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements/local.txt
```

### 2. Environment Setup

```bash
# Copy example environment file
cp .env.example .env

# Edit .env with your settings
```

### 3. Database Setup

```bash
# Run migrations
python manage.py migrate

# Create superuser
python manage.py createsuperuser
```

### 4. Run Development Server

```bash
# Start Django server
python manage.py runserver

# In another terminal, start Celery worker
celery -A config.celery_app worker --loglevel=info
```

## API Documentation

Once the server is running, visit:

- **Swagger UI**: http://localhost:8000/api/schema/swagger-ui/
- **ReDoc**: http://localhost:8000/api/schema/redoc/
- **OpenAPI Schema**: http://localhost:8000/api/schema/

## Project Structure

```
backend/
├── apps/
│   └── core/              # Core app with base models
│       ├── api/           # API views and mixins
│       ├── models.py      # BaseModel with UUID, timestamps
│       └── utils.py       # Utility functions
├── config/
│   ├── settings/          # Settings modules
│   │   ├── base.py        # Base settings
│   │   ├── local.py       # Development settings
│   │   ├── production.py  # Production settings
│   │   └── test.py        # Test settings
│   ├── api_router.py      # API URL routing
│   ├── celery_app.py      # Celery configuration
│   ├── urls.py            # Main URL configuration
│   ├── asgi.py            # ASGI application
│   └── wsgi.py            # WSGI application
├── requirements/
│   ├── base.txt           # Base requirements
│   ├── local.txt          # Development requirements
│   └── production.txt     # Production requirements
├── manage.py              # Django management script
├── conftest.py            # Pytest configuration
└── pyproject.toml         # Python project config
```

## Available Endpoints

### Health Check
- `GET /api/v1/health/` - System health check (database, redis, celery)

### Authentication
- `POST /api/v1/auth/token/` - Obtain JWT token pair
- `POST /api/v1/auth/token/refresh/` - Refresh access token
- `POST /api/v1/auth/token/verify/` - Verify token validity

## Development

### Running Tests

```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=apps

# Run specific test file
pytest apps/core/tests/test_models.py
```

### Code Quality

```bash
# Format code with black
black .

# Sort imports with isort
isort .

# Lint with ruff
ruff check .

# Type checking with mypy
mypy apps/
```

### Database Migrations

```bash
# Create migrations
python manage.py makemigrations

# Apply migrations
python manage.py migrate

# Show migrations
python manage.py showmigrations
```

### Django Shell

```bash
# Django shell
python manage.py shell

# Django shell with IPython
python manage.py shell_plus  # Requires django-extensions
```

## Settings

Settings are split into multiple files:

- `base.py` - Common settings for all environments
- `local.py` - Development settings (DEBUG=True, console email)
- `production.py` - Production settings (security headers, DEBUG=False)
- `test.py` - Test settings (in-memory database, eager Celery)

Set via `DJANGO_SETTINGS_MODULE` environment variable:

```bash
# Development
export DJANGO_SETTINGS_MODULE=config.settings.local

# Production
export DJANGO_SETTINGS_MODULE=config.settings.production

# Testing
export DJANGO_SETTINGS_MODULE=config.settings.test
```

## Core Features

### BaseModel

All models inherit from `BaseModel` which provides:

- UUID primary key
- `created_at` timestamp (auto_now_add)
- `updated_at` timestamp (auto_now)

```python
from apps.core.models import BaseModel

class MyModel(BaseModel):
    name = models.CharField(max_length=100)
    # id, created_at, updated_at are inherited
```

### API Mixins

Common ViewSet mixins in `apps/core/api/mixins.py`:

- `TimestampFilterMixin` - Filter by created_at/updated_at
- `BulkActionMixin` - Bulk delete operations
- `SoftDeleteMixin` - Soft delete functionality

## Environment Variables

Required:
- `SECRET_KEY` - Django secret key
- `POSTGRES_DB` - Database name
- `POSTGRES_USER` - Database user
- `POSTGRES_PASSWORD` - Database password
- `POSTGRES_HOST` - Database host
- `REDIS_URL` - Redis connection URL

Optional:
- `ALLOWED_HOSTS` - Comma-separated allowed hosts (production)
- `CORS_ALLOWED_ORIGINS` - Comma-separated CORS origins
- `SENTRY_DSN` - Sentry error tracking DSN
- `EMAIL_HOST` - SMTP server
- `EMAIL_HOST_USER` - SMTP username
- `EMAIL_HOST_PASSWORD` - SMTP password

## Deployment

### Production Checklist

1. Set `DJANGO_SETTINGS_MODULE=config.settings.production`
2. Set strong `SECRET_KEY`
3. Configure `ALLOWED_HOSTS`
4. Set up PostgreSQL database
5. Set up Redis instance
6. Configure email settings
7. Set up Sentry (optional)
8. Collect static files: `python manage.py collectstatic`
9. Run migrations: `python manage.py migrate`
10. Start Gunicorn: `gunicorn config.wsgi:application`
11. Start Celery worker: `celery -A config.celery_app worker`

### Docker

See main project README for Docker setup.

## License

See main project LICENSE file.
