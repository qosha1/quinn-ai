#!/bin/bash

# Docker Infrastructure Verification Script
# This script checks if all required components are in place

set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo "========================================="
echo "Docker Infrastructure Verification"
echo "========================================="
echo ""

# Check Docker
echo -n "Checking Docker installation... "
if command -v docker &> /dev/null; then
    echo -e "${GREEN}✓${NC}"
    docker --version
else
    echo -e "${RED}✗${NC}"
    echo "Docker is not installed. Please install Docker Desktop."
    exit 1
fi

echo ""

# Check Docker Compose
echo -n "Checking Docker Compose... "
if docker compose version &> /dev/null; then
    echo -e "${GREEN}✓${NC}"
    docker compose version
else
    echo -e "${RED}✗${NC}"
    echo "Docker Compose is not available."
    exit 1
fi

echo ""

# Check required files
echo "Checking required Docker files:"

FILES=(
    "docker-compose.local.yml"
    "docker-compose.production.yml"
    "Makefile"
    ".dockerignore"
    "compose/local/django/Dockerfile"
    "compose/local/django/start"
    "compose/local/django/entrypoint"
    "compose/local/nginx/Dockerfile"
    "compose/local/nginx/nginx.conf"
    "compose/local/node/Dockerfile"
    "compose/production/django/Dockerfile"
    "compose/production/traefik/traefik.yml"
    "compose/production/traefik/dynamic.yml"
)

for file in "${FILES[@]}"; do
    echo -n "  $file... "
    if [ -f "$file" ]; then
        echo -e "${GREEN}✓${NC}"
    else
        echo -e "${RED}✗${NC}"
        echo "    Missing required file: $file"
        exit 1
    fi
done

echo ""

# Check environment templates
echo "Checking environment templates:"

ENV_TEMPLATES=(
    ".envs/.local/.django.example"
    ".envs/.local/.postgres.example"
    ".envs/.production/.django.example"
    ".envs/.production/.postgres.example"
    ".envs/.production/.traefik.example"
)

for template in "${ENV_TEMPLATES[@]}"; do
    echo -n "  $template... "
    if [ -f "$template" ]; then
        echo -e "${GREEN}✓${NC}"
    else
        echo -e "${RED}✗${NC}"
        echo "    Missing template: $template"
        exit 1
    fi
done

echo ""

# Check if environment files exist
echo "Checking environment files:"

echo -n "  .envs/.local/.django... "
if [ -f ".envs/.local/.django" ]; then
    echo -e "${GREEN}✓${NC}"
else
    echo -e "${YELLOW}⚠${NC} Not found (run 'make setup' to create)"
fi

echo -n "  .envs/.local/.postgres... "
if [ -f ".envs/.local/.postgres" ]; then
    echo -e "${GREEN}✓${NC}"
else
    echo -e "${YELLOW}⚠${NC} Not found (run 'make setup' to create)"
fi

echo ""

# Check if Docker daemon is running
echo -n "Checking Docker daemon... "
if docker info &> /dev/null; then
    echo -e "${GREEN}✓${NC}"
else
    echo -e "${RED}✗${NC}"
    echo "Docker daemon is not running. Please start Docker Desktop."
    exit 1
fi

echo ""

# Check for port conflicts
echo "Checking for port conflicts:"

PORTS=(8000 3000 3001 5432 6379 80)

for port in "${PORTS[@]}"; do
    echo -n "  Port $port... "
    if lsof -Pi :$port -sTCP:LISTEN -t >/dev/null 2>&1; then
        echo -e "${YELLOW}⚠${NC} In use"
    else
        echo -e "${GREEN}✓${NC} Available"
    fi
done

echo ""

# Summary
echo "========================================="
echo "Verification Summary"
echo "========================================="
echo ""

if [ ! -f ".envs/.local/.django" ] || [ ! -f ".envs/.local/.postgres" ]; then
    echo -e "${YELLOW}Next steps:${NC}"
    echo "1. Run 'make setup' to create environment files"
    echo "2. Edit .envs/.local/.django and update SECRET_KEY"
    echo "3. Run 'make up' to start services"
else
    echo -e "${GREEN}All checks passed!${NC}"
    echo ""
    echo "You can now run:"
    echo "  make up    # Start all services"
    echo "  make logs  # View logs"
fi

echo ""
