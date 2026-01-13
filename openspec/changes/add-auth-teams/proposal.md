# Change: Authentication and Team Management

## Why
B2B SaaS requires multi-tenant architecture with companies, teams, and role-based access control. Users need JWT authentication, API keys, and team invitations.

## What Changes
- Create users app with custom User model
- Create teams app with Company, Team, TeamMember models
- Create authentication app with API key support
- Implement role-based permissions (owner, admin, member, viewer)
- Add JWT token endpoints

## Impact
- New capabilities: auth, teams
- Enables multi-tenancy and access control
