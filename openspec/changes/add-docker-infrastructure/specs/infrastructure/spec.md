# Infrastructure Specification

## ADDED Requirements

### Requirement: Docker Compose Local Development
The system SHALL provide a docker-compose.local.yml that orchestrates all services for local development.

#### Scenario: Start local environment
- **WHEN** developer runs `docker-compose -f docker-compose.local.yml up`
- **THEN** all services start (django, postgres, redis, celery, nginx)
- **AND** Django is accessible at http://localhost:8000
- **AND** Landing page is accessible at http://localhost:3000
- **AND** App is accessible at http://localhost:3001

#### Scenario: Hot reload development
- **WHEN** developer modifies Python or TypeScript code
- **THEN** changes are reflected without container restart

### Requirement: Docker Compose Production
The system SHALL provide a production docker-compose with Traefik for SSL termination.

#### Scenario: Production deployment
- **WHEN** deploying to production server
- **THEN** Traefik automatically obtains Let's Encrypt certificates
- **AND** all services are health-checked
- **AND** static files are served via Nginx

### Requirement: Environment Configuration
The system SHALL use environment files for all configuration.

#### Scenario: Configure database
- **WHEN** .envs/.local/.postgres contains credentials
- **THEN** Django connects using those credentials
- **AND** secrets are never committed to git

### Requirement: Makefile Commands
The system SHALL provide a Makefile for common developer tasks.

#### Scenario: Build and start
- **WHEN** developer runs `make up`
- **THEN** containers are built and started
- **AND** migrations run automatically
