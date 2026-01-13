.PHONY: help up down build restart logs shell migrate makemigrations test createsuperuser collectstatic clean

# Default environment is local
ENV ?= local
COMPOSE_FILE = docker-compose.$(ENV).yml

help:
	@echo "B2B SaaS Template - Docker Management"
	@echo ""
	@echo "Available commands:"
	@echo "  make up              - Start all services (development)"
	@echo "  make down            - Stop all services"
	@echo "  make build           - Build all Docker images"
	@echo "  make restart         - Restart all services"
	@echo "  make logs            - View logs from all services"
	@echo "  make logs-django     - View Django logs"
	@echo "  make logs-celery     - View Celery worker logs"
	@echo "  make shell           - Open Django shell"
	@echo "  make bash            - Open bash in Django container"
	@echo "  make migrate         - Run database migrations"
	@echo "  make makemigrations  - Create new migrations"
	@echo "  make test            - Run Django tests"
	@echo "  make test-coverage   - Run tests with coverage report"
	@echo "  make createsuperuser - Create Django superuser"
	@echo "  make collectstatic   - Collect static files"
	@echo "  make clean           - Remove all containers, volumes, and images"
	@echo "  make clean-volumes   - Remove only volumes (WARNING: deletes data)"
	@echo "  make ps              - List running containers"
	@echo "  make setup           - Initial setup (copy env files)"
	@echo ""
	@echo "Production commands:"
	@echo "  make up-prod         - Start production services"
	@echo "  make down-prod       - Stop production services"
	@echo "  make logs-prod       - View production logs"
	@echo ""

# Development commands
up:
	docker-compose -f $(COMPOSE_FILE) up -d

down:
	docker-compose -f $(COMPOSE_FILE) down

build:
	docker-compose -f $(COMPOSE_FILE) build

restart:
	docker-compose -f $(COMPOSE_FILE) restart

logs:
	docker-compose -f $(COMPOSE_FILE) logs -f

logs-django:
	docker-compose -f $(COMPOSE_FILE) logs -f django

logs-celery:
	docker-compose -f $(COMPOSE_FILE) logs -f celery-worker

logs-landing:
	docker-compose -f $(COMPOSE_FILE) logs -f landing

logs-app:
	docker-compose -f $(COMPOSE_FILE) logs -f app

shell:
	docker-compose -f $(COMPOSE_FILE) exec django python manage.py shell

bash:
	docker-compose -f $(COMPOSE_FILE) exec django bash

migrate:
	docker-compose -f $(COMPOSE_FILE) exec django python manage.py migrate

makemigrations:
	docker-compose -f $(COMPOSE_FILE) exec django python manage.py makemigrations

test:
	docker-compose -f $(COMPOSE_FILE) exec django python manage.py test

test-coverage:
	docker-compose -f $(COMPOSE_FILE) exec django coverage run --source='.' manage.py test
	docker-compose -f $(COMPOSE_FILE) exec django coverage report
	docker-compose -f $(COMPOSE_FILE) exec django coverage html

createsuperuser:
	docker-compose -f $(COMPOSE_FILE) exec django python manage.py createsuperuser

collectstatic:
	docker-compose -f $(COMPOSE_FILE) exec django python manage.py collectstatic --noinput

ps:
	docker-compose -f $(COMPOSE_FILE) ps

# Clean commands
clean:
	docker-compose -f $(COMPOSE_FILE) down -v --rmi all --remove-orphans

clean-volumes:
	@echo "WARNING: This will delete all database data!"
	@echo "Press Ctrl+C to cancel, or wait 5 seconds to continue..."
	@sleep 5
	docker-compose -f $(COMPOSE_FILE) down -v

# Production commands
up-prod:
	docker-compose -f docker-compose.production.yml up -d

down-prod:
	docker-compose -f docker-compose.production.yml down

build-prod:
	docker-compose -f docker-compose.production.yml build

logs-prod:
	docker-compose -f docker-compose.production.yml logs -f

restart-prod:
	docker-compose -f docker-compose.production.yml restart

# Setup command - copy environment files
setup:
	@echo "Setting up environment files..."
	@if [ ! -f .envs/.local/.django ]; then \
		cp .envs/.local/.django.example .envs/.local/.django; \
		echo "Created .envs/.local/.django - Please update values"; \
	else \
		echo ".envs/.local/.django already exists"; \
	fi
	@if [ ! -f .envs/.local/.postgres ]; then \
		cp .envs/.local/.postgres.example .envs/.local/.postgres; \
		echo "Created .envs/.local/.postgres - Please update values"; \
	else \
		echo ".envs/.local/.postgres already exists"; \
	fi
	@echo ""
	@echo "Setup complete! Next steps:"
	@echo "1. Edit .envs/.local/.django and update SECRET_KEY and other settings"
	@echo "2. Edit .envs/.local/.postgres if you want to change database credentials"
	@echo "3. Run 'make up' to start the services"

# Database backup (local development)
backup-db:
	@echo "Creating database backup..."
	docker-compose -f $(COMPOSE_FILE) exec -T postgres pg_dump -U saas_user saas_db > backup_$(shell date +%Y%m%d_%H%M%S).sql
	@echo "Backup created: backup_$(shell date +%Y%m%d_%H%M%S).sql"

# Database restore (local development)
restore-db:
	@echo "Restoring database from $(file)..."
	@if [ -z "$(file)" ]; then \
		echo "Usage: make restore-db file=backup_file.sql"; \
		exit 1; \
	fi
	docker-compose -f $(COMPOSE_FILE) exec -T postgres psql -U saas_user saas_db < $(file)
	@echo "Database restored from $(file)"

# Install dependencies in running containers
install-backend:
	docker-compose -f $(COMPOSE_FILE) exec django pip install -r /requirements/local.txt

install-landing:
	docker-compose -f $(COMPOSE_FILE) exec landing npm install

install-app:
	docker-compose -f $(COMPOSE_FILE) exec app npm install

# Linting and formatting
lint-backend:
	docker-compose -f $(COMPOSE_FILE) exec django flake8 .
	docker-compose -f $(COMPOSE_FILE) exec django black --check .

format-backend:
	docker-compose -f $(COMPOSE_FILE) exec django black .
	docker-compose -f $(COMPOSE_FILE) exec django isort .

lint-frontend:
	docker-compose -f $(COMPOSE_FILE) exec landing npm run lint
	docker-compose -f $(COMPOSE_FILE) exec app npm run lint

# Security scanning (requires trivy installed)
security-scan:
	@echo "Scanning Django image..."
	trivy image saas-django-local
	@echo "Scanning Node images..."
	trivy image saas-landing-local
	trivy image saas-app-local
