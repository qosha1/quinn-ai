# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- Code quality commandments verification tests
- Template sync process for forked repos
- Versioning and changelog system

### Changed
- Updated CLAUDE.md with agentic tools integration rules

### Fixed
- Empty except block in billing services

---

## [0.1.0] - 2024-12-31

### Added
- Initial B2B SaaS template release
- Django 5.1+ backend with DRF
- NextJS 15 landing page with Tailwind and shadcn/ui
- NextJS 15 dashboard app with JWT auth and Stripe
- Multi-tenancy model (Company > Teams > Users)
- Role-based access control (owner, admin, member, viewer)
- Stripe billing integration with usage tracking
- Docker Compose infrastructure (local and production)
- Comprehensive test suites (pytest, vitest, playwright)
- OpenSpec integration for spec-driven development

### Infrastructure
- PostgreSQL 16 database
- Redis 7 for caching and Celery
- Nginx reverse proxy (local)
- Traefik reverse proxy (production)
- Celery worker and beat scheduler

### Security
- JWT authentication with refresh tokens
- API key authentication for programmatic access
- CORS configuration
- Environment-based secrets management

---

[Unreleased]: https://github.com/YOUR_ORG/b2b-saas-template/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/YOUR_ORG/b2b-saas-template/releases/tag/v0.1.0
