# Backend Core Specification

## ADDED Requirements

### Requirement: Django Project Structure
The backend SHALL follow cookiecutter-django patterns with modular configuration.

#### Scenario: Settings inheritance
- **WHEN** running in local environment
- **THEN** local.py imports from base.py
- **AND** DEBUG is True
- **AND** email backend is console

#### Scenario: Production settings
- **WHEN** running in production
- **THEN** production.py enables security headers
- **AND** DEBUG is False
- **AND** ALLOWED_HOSTS is configured from env

### Requirement: BaseModel
The core app SHALL provide a BaseModel with UUID primary key and timestamps.

#### Scenario: Model inheritance
- **WHEN** a new model inherits from BaseModel
- **THEN** it has id (UUID), created_at, updated_at fields
- **AND** timestamps auto-update on save

### Requirement: DRF Configuration
The system SHALL configure Django REST Framework with sensible defaults.

#### Scenario: API request
- **WHEN** client makes authenticated API request
- **THEN** JWT or session authentication is accepted
- **AND** responses use standard pagination
- **AND** OpenAPI schema is available at /api/schema/

### Requirement: Celery Integration
The system SHALL configure Celery with Redis broker.

#### Scenario: Async task
- **WHEN** a task is queued via .delay()
- **THEN** Celery worker processes it
- **AND** results are stored in Redis
- **AND** tasks are auto-discovered from apps

### Requirement: Health Check Endpoint
The system SHALL provide a health check endpoint.

#### Scenario: Health check
- **WHEN** GET /api/v1/health/
- **THEN** response includes database, redis, celery status
- **AND** returns 200 if all healthy, 503 if degraded
