# Authentication & Teams Implementation Summary

This document provides an overview of the authentication and teams implementation for the B2B SaaS template.

## Overview

The implementation provides a complete multi-tenant authentication and team management system with:

- Custom User model with email-based authentication
- Company and Team models for multi-tenancy
- Role-based access control (RBAC)
- API key authentication for server-to-server calls
- JWT token authentication for user sessions
- Team invitations system

## Architecture

### Apps Structure

```
backend/apps/
├── users/              # User management and authentication
├── teams/              # Multi-tenancy, companies, and teams
└── authentication/     # API key authentication
```

## Models

### Users App

#### User Model
- **Path**: `/Users/quinnosha/Documents/Github/dev-tools/b2b-saas-template/backend/apps/users/models.py`
- **Table**: `users`
- **Key Fields**:
  - `email` (unique, used as username)
  - `first_name`, `last_name`
  - `is_email_verified`
  - `company` (FK to Company)
  - Inherits from Django's AbstractBaseUser and PermissionsMixin

### Teams App

#### Company Model
- **Path**: `/Users/quinnosha/Documents/Github/dev-tools/b2b-saas-template/backend/apps/teams/models.py`
- **Table**: `companies`
- **Key Fields**:
  - `name`, `slug` (unique)
  - `settings` (JSONField)
  - `owner` (FK to User)
- **Features**:
  - Auto-generates slug from name
  - Creates default team on creation (via signal)

#### Team Model
- **Table**: `teams`
- **Key Fields**:
  - `name`, `slug`
  - `company` (FK)
  - `settings` (JSONField)
- **Constraints**:
  - Unique together: (company, slug)

#### TeamMember Model
- **Table**: `team_members`
- **Key Fields**:
  - `user` (FK)
  - `team` (FK)
  - `role` (owner/admin/member/viewer)
  - `invited_by` (FK to User)
  - `joined_at`
- **Constraints**:
  - Unique together: (user, team)

#### TeamInvitation Model
- **Table**: `team_invitations`
- **Key Fields**:
  - `email`, `team` (FK)
  - `role`, `token` (unique)
  - `invited_by` (FK)
  - `expires_at`, `accepted_at`
- **Features**:
  - Auto-generates secure token
  - Default expiration: 7 days

### Authentication App

#### APIKey Model
- **Path**: `/Users/quinnosha/Documents/Github/dev-tools/b2b-saas-template/backend/apps/authentication/models.py`
- **Table**: `api_keys`
- **Key Fields**:
  - `name`, `key` (hashed)
  - `prefix` (first 8 chars for lookup)
  - `company` (FK)
  - `created_by` (FK)
  - `scopes` (ArrayField)
  - `last_used_at`, `expires_at`
  - `is_active`
- **Security**:
  - Keys are hashed using Django's password hashers
  - Raw key shown only once on creation

## API Endpoints

### Authentication
- `POST /api/v1/auth/token/` - Obtain JWT token pair
- `POST /api/v1/auth/token/refresh/` - Refresh access token
- `POST /api/v1/auth/token/verify/` - Verify token validity

### Users
- `POST /api/v1/users/` - Register new user (public)
- `GET /api/v1/users/me/` - Get current user profile
- `PATCH /api/v1/users/me/` - Update current user profile
- `POST /api/v1/users/me/change-password/` - Change password

### Companies
- `GET /api/v1/companies/` - List companies (user's company)
- `POST /api/v1/companies/` - Create new company
- `GET /api/v1/companies/{id}/` - Get company details
- `PATCH /api/v1/companies/{id}/` - Update company (owner only)
- `DELETE /api/v1/companies/{id}/` - Delete company (owner only)

### Teams
- `GET /api/v1/teams/` - List teams
- `POST /api/v1/teams/` - Create team (admin+)
- `GET /api/v1/teams/{id}/` - Get team details
- `PATCH /api/v1/teams/{id}/` - Update team (admin+)
- `DELETE /api/v1/teams/{id}/` - Delete team (admin+)

### Team Members
- `GET /api/v1/team-members/` - List team members
- `POST /api/v1/team-members/` - Add member (admin+)
- `GET /api/v1/team-members/my-teams/` - Get user's teams
- `PATCH /api/v1/team-members/{id}/` - Update member role (admin+)
- `DELETE /api/v1/team-members/{id}/` - Remove member (admin+)

### Team Invitations
- `GET /api/v1/team-invitations/` - List invitations
- `POST /api/v1/team-invitations/` - Send invitation (admin+)
- `POST /api/v1/team-invitations/accept/` - Accept invitation
- `POST /api/v1/team-invitations/{id}/resend/` - Resend invitation
- `DELETE /api/v1/team-invitations/{id}/` - Cancel invitation (admin+)

### API Keys
- `GET /api/v1/api-keys/` - List API keys
- `POST /api/v1/api-keys/` - Create API key (admin+)
- `GET /api/v1/api-keys/{id}/` - Get API key details
- `POST /api/v1/api-keys/{id}/revoke/` - Revoke key (admin+)
- `POST /api/v1/api-keys/{id}/activate/` - Activate key (admin+)
- `DELETE /api/v1/api-keys/{id}/` - Delete key (admin+)

## Permissions & Access Control

### Role Hierarchy
```
owner > admin > member > viewer
```

### Permission Classes

#### IsCompanyMember
- **Path**: `/Users/quinnosha/Documents/Github/dev-tools/b2b-saas-template/backend/apps/teams/permissions.py`
- Checks if user belongs to the company

#### IsTeamMember
- Checks if user is a member of the team

#### HasTeamRole
- Checks if user has required role level
- Variants: IsOwner, IsAdmin, IsMember

### ViewSet Mixins

#### TeamOwnedMixin
- **Path**: `/Users/quinnosha/Documents/Github/dev-tools/b2b-saas-template/backend/apps/teams/mixins.py`
- Auto-filters queryset by user's company/team
- Auto-assigns company on creation

#### CompanyOwnedMixin
- Simpler version for company-scoped resources

## Authentication Methods

### 1. JWT Authentication
- **Access Token**: 30 minutes lifetime
- **Refresh Token**: 1 day lifetime
- Token rotation enabled
- Used for user sessions

### 2. API Key Authentication
- **Path**: `/Users/quinnosha/Documents/Github/dev-tools/b2b-saas-template/backend/apps/authentication/backends.py`
- Header: `X-API-Key: {key}`
- Used for server-to-server authentication
- Scoped to company
- Tracks last usage

### 3. Session Authentication
- Django session authentication
- Primarily for admin interface

## Database Migrations

### Migration Files
1. **Teams**: `/Users/quinnosha/Documents/Github/dev-tools/b2b-saas-template/backend/apps/teams/migrations/0001_initial.py`
   - Creates Company, Team, TeamMember, TeamInvitation tables

2. **Users**: `/Users/quinnosha/Documents/Github/dev-tools/b2b-saas-template/backend/apps/users/migrations/0001_initial.py`
   - Creates User table with FK to Company

3. **Authentication**: `/Users/quinnosha/Documents/Github/dev-tools/b2b-saas-template/backend/apps/authentication/migrations/0001_initial.py`
   - Creates APIKey table

### Running Migrations
```bash
cd backend
python manage.py migrate
```

## Signals

### Auto-create Default Team
- **Path**: `/Users/quinnosha/Documents/Github/dev-tools/b2b-saas-template/backend/apps/teams/signals.py`
- Triggered: When Company is created
- Action: Creates "Default Team" and adds owner as team owner

## Configuration

### Settings Updated
- **Path**: `/Users/quinnosha/Documents/Github/dev-tools/b2b-saas-template/backend/config/settings/base.py`
- Added `AUTH_USER_MODEL = "users.User"`
- Added apps to `INSTALLED_APPS`
- Added `APIKeyAuthentication` to `DEFAULT_AUTHENTICATION_CLASSES`
- Updated JWT token lifetimes

### Router Updated
- **Path**: `/Users/quinnosha/Documents/Github/dev-tools/b2b-saas-template/backend/config/api_router.py`
- Registered all ViewSets with appropriate basenames

## Usage Examples

### 1. Register User
```bash
POST /api/v1/users/
{
  "email": "user@example.com",
  "password": "SecurePassword123!",
  "password_confirm": "SecurePassword123!",
  "first_name": "John",
  "last_name": "Doe"
}
```

### 2. Login (Get JWT Token)
```bash
POST /api/v1/auth/token/
{
  "email": "user@example.com",
  "password": "SecurePassword123!"
}

Response:
{
  "access": "eyJ0eXAiOiJKV1QiLCJhbGc...",
  "refresh": "eyJ0eXAiOiJKV1QiLCJhbGc..."
}
```

### 3. Create Company
```bash
POST /api/v1/companies/
Authorization: Bearer {access_token}
{
  "name": "Acme Corp",
  "settings": {}
}
```

### 4. Invite User to Team
```bash
POST /api/v1/team-invitations/
Authorization: Bearer {access_token}
{
  "email": "newuser@example.com",
  "team": "{team_id}",
  "role": "member"
}
```

### 5. Create API Key
```bash
POST /api/v1/api-keys/
Authorization: Bearer {access_token}
{
  "name": "Production API Key",
  "scopes": ["read", "write"],
  "expires_at": "2025-12-31T23:59:59Z"
}

Response:
{
  "id": "uuid",
  "name": "Production API Key",
  "key": "xlPQN8Sh...", # Only shown once!
  "prefix": "xlPQN8Sh",
  "message": "Store this key securely. It will not be shown again."
}
```

### 6. Use API Key
```bash
GET /api/v1/teams/
X-API-Key: xlPQN8Sh...
```

## Security Considerations

### Password Security
- Minimum 8 characters
- Django password validators enabled
- Passwords hashed using PBKDF2

### API Key Security
- Keys hashed before storage
- Only prefix stored in plaintext for lookup
- Raw key shown only once on creation
- Support for expiration and revocation

### Multi-tenancy Isolation
- All queries filtered by company/team
- ViewSet mixins enforce isolation
- Permission classes validate access

### Role-Based Access
- Hierarchical role system
- Permission checks at ViewSet level
- Object-level permissions supported

## Next Steps

1. **Run Migrations**:
   ```bash
   cd /Users/quinnosha/Documents/Github/dev-tools/b2b-saas-template/backend
   python manage.py migrate
   ```

2. **Create Superuser**:
   ```bash
   python manage.py createsuperuser
   ```

3. **Test Endpoints**:
   - Use Django REST Framework browsable API
   - Access admin at `/admin/`
   - Test API endpoints with Postman or curl

4. **Optional Enhancements**:
   - Add email verification flow
   - Implement password reset
   - Add team invitation emails
   - Configure API key scopes
   - Add audit logging
   - Implement rate limiting

## File Locations Reference

### Models
- Users: `/Users/quinnosha/Documents/Github/dev-tools/b2b-saas-template/backend/apps/users/models.py`
- Teams: `/Users/quinnosha/Documents/Github/dev-tools/b2b-saas-template/backend/apps/teams/models.py`
- Auth: `/Users/quinnosha/Documents/Github/dev-tools/b2b-saas-template/backend/apps/authentication/models.py`

### Serializers
- Users: `/Users/quinnosha/Documents/Github/dev-tools/b2b-saas-template/backend/apps/users/api/serializers.py`
- Teams: `/Users/quinnosha/Documents/Github/dev-tools/b2b-saas-template/backend/apps/teams/api/serializers.py`
- Auth: `/Users/quinnosha/Documents/Github/dev-tools/b2b-saas-template/backend/apps/authentication/api/serializers.py`

### ViewSets
- Users: `/Users/quinnosha/Documents/Github/dev-tools/b2b-saas-template/backend/apps/users/api/views.py`
- Teams: `/Users/quinnosha/Documents/Github/dev-tools/b2b-saas-template/backend/apps/teams/api/views.py`
- Auth: `/Users/quinnosha/Documents/Github/dev-tools/b2b-saas-template/backend/apps/authentication/api/views.py`

### Permissions
- `/Users/quinnosha/Documents/Github/dev-tools/b2b-saas-template/backend/apps/teams/permissions.py`
- `/Users/quinnosha/Documents/Github/dev-tools/b2b-saas-template/backend/apps/teams/mixins.py`

### Admin
- Users: `/Users/quinnosha/Documents/Github/dev-tools/b2b-saas-template/backend/apps/users/admin.py`
- Teams: `/Users/quinnosha/Documents/Github/dev-tools/b2b-saas-template/backend/apps/teams/admin.py`
- Auth: `/Users/quinnosha/Documents/Github/dev-tools/b2b-saas-template/backend/apps/authentication/admin.py`

### Configuration
- Settings: `/Users/quinnosha/Documents/Github/dev-tools/b2b-saas-template/backend/config/settings/base.py`
- Router: `/Users/quinnosha/Documents/Github/dev-tools/b2b-saas-template/backend/config/api_router.py`
