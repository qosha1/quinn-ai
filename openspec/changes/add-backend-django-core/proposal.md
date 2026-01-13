# Change: Django Backend Core Setup

## Why
The backend needs a well-structured Django project following cookiecutter patterns with modular settings, DRF configuration, and Celery integration.

## What Changes
- Create Django project structure in /backend
- Configure split settings (base, local, production, test)
- Set up DRF with JWT authentication
- Configure Celery with Redis broker
- Add core app with BaseModel

## Impact
- New capability: backend-core
- Foundation for all Django apps
