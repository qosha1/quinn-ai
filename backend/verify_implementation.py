#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Verification script for authentication and teams implementation.

Run this script to verify all components are properly installed.
Usage: python verify_implementation.py
"""

import os
import sys
from pathlib import Path

# Color codes for output
GREEN = '\033[92m'
RED = '\033[91m'
YELLOW = '\033[93m'
RESET = '\033[0m'


def check_file_exists(filepath, description):
    """Check if a file exists."""
    if Path(filepath).exists():
        print(f"{GREEN}[OK]{RESET} {description}")
        return True
    else:
        print(f"{RED}[FAIL]{RESET} {description} - MISSING: {filepath}")
        return False


def main():
    """Run verification checks."""
    print("\n" + "="*60)
    print("B2B SaaS Template - Implementation Verification")
    print("="*60 + "\n")

    all_checks_passed = True

    # Check Users App
    print(f"{YELLOW}Checking Users App...{RESET}")
    users_checks = [
        ("apps/users/__init__.py", "Users app init"),
        ("apps/users/models.py", "User model"),
        ("apps/users/managers.py", "User manager"),
        ("apps/users/admin.py", "User admin"),
        ("apps/users/api/serializers.py", "User serializers"),
        ("apps/users/api/views.py", "User ViewSets"),
        ("apps/users/migrations/0001_initial.py", "User migrations"),
    ]
    for filepath, desc in users_checks:
        if not check_file_exists(filepath, desc):
            all_checks_passed = False
    print()

    # Check Teams App
    print(f"{YELLOW}Checking Teams App...{RESET}")
    teams_checks = [
        ("apps/teams/__init__.py", "Teams app init"),
        ("apps/teams/models.py", "Team models"),
        ("apps/teams/signals.py", "Team signals"),
        ("apps/teams/permissions.py", "Team permissions"),
        ("apps/teams/mixins.py", "Team mixins"),
        ("apps/teams/admin.py", "Team admin"),
        ("apps/teams/api/serializers.py", "Team serializers"),
        ("apps/teams/api/views.py", "Team ViewSets"),
        ("apps/teams/migrations/0001_initial.py", "Team migrations"),
    ]
    for filepath, desc in teams_checks:
        if not check_file_exists(filepath, desc):
            all_checks_passed = False
    print()

    # Check Authentication App
    print(f"{YELLOW}Checking Authentication App...{RESET}")
    auth_checks = [
        ("apps/authentication/__init__.py", "Authentication app init"),
        ("apps/authentication/models.py", "APIKey model"),
        ("apps/authentication/backends.py", "API Key authentication backend"),
        ("apps/authentication/admin.py", "Authentication admin"),
        ("apps/authentication/api/serializers.py", "Authentication serializers"),
        ("apps/authentication/api/views.py", "Authentication ViewSets"),
        ("apps/authentication/migrations/0001_initial.py", "Authentication migrations"),
    ]
    for filepath, desc in auth_checks:
        if not check_file_exists(filepath, desc):
            all_checks_passed = False
    print()

    # Check Configuration
    print(f"{YELLOW}Checking Configuration...{RESET}")
    config_checks = [
        ("config/settings/base.py", "Settings configuration"),
        ("config/api_router.py", "API router configuration"),
    ]
    for filepath, desc in config_checks:
        if not check_file_exists(filepath, desc):
            all_checks_passed = False
    print()

    # Check for specific settings
    print(f"{YELLOW}Checking Settings Content...{RESET}")
    settings_file = Path("config/settings/base.py")
    if settings_file.exists():
        content = settings_file.read_text()
        settings_checks = [
            ("AUTH_USER_MODEL", "Custom user model configured"),
            ("apps.users", "Users app in INSTALLED_APPS"),
            ("apps.teams", "Teams app in INSTALLED_APPS"),
            ("apps.authentication", "Authentication app in INSTALLED_APPS"),
            ("APIKeyAuthentication", "API Key auth in authentication classes"),
        ]
        for check, desc in settings_checks:
            if check in content:
                print(f"{GREEN}[OK]{RESET} {desc}")
            else:
                print(f"{RED}[FAIL]{RESET} {desc}")
                all_checks_passed = False
    print()

    # Summary
    print("="*60)
    if all_checks_passed:
        print(f"{GREEN}All checks passed!{RESET}")
        print("\nNext steps:")
        print("1. Run migrations: python manage.py migrate")
        print("2. Create superuser: python manage.py createsuperuser")
        print("3. Run tests: python manage.py test")
        print("4. Start server: python manage.py runserver")
    else:
        print(f"{RED}Some checks failed. Please review the errors above.{RESET}")
    print("="*60 + "\n")

    return 0 if all_checks_passed else 1


if __name__ == "__main__":
    sys.exit(main())
