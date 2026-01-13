# Comprehensive Testing Specification

## ADDED Requirements

### Requirement: Backend API Test Infrastructure
The project SHALL have pytest-based API tests for all Django apps.

#### Scenario: Test configuration
- **GIVEN** pytest is installed with django plugin
- **WHEN** `pytest backend/` is run
- **THEN** all API tests execute
- **AND** fixtures provide test data

### Requirement: Authentication Tests
The project SHALL test all authentication flows.

#### Scenario: User registration
- **WHEN** POST /api/v1/auth/register/ with valid data
- **THEN** user is created
- **AND** tokens are returned

#### Scenario: JWT login
- **WHEN** POST /api/v1/auth/token/ with valid credentials
- **THEN** access and refresh tokens returned
- **AND** tokens are valid JWT format

#### Scenario: Token refresh
- **GIVEN** valid refresh token
- **WHEN** POST /api/v1/auth/token/refresh/
- **THEN** new access token returned

#### Scenario: API key authentication
- **GIVEN** valid API key
- **WHEN** request includes X-API-Key header
- **THEN** request is authenticated

#### Scenario: Invalid credentials
- **WHEN** POST /api/v1/auth/token/ with wrong password
- **THEN** 401 Unauthorized returned

### Requirement: Team Management Tests
The project SHALL test team operations with proper permissions.

#### Scenario: Create team
- **GIVEN** authenticated company owner
- **WHEN** POST /api/v1/teams/
- **THEN** team is created
- **AND** user becomes team owner

#### Scenario: Invite member
- **GIVEN** team admin or owner
- **WHEN** POST /api/v1/teams/{id}/invitations/
- **THEN** invitation is created
- **AND** invitation email is queued

#### Scenario: Accept invitation
- **GIVEN** valid invitation token
- **WHEN** POST /api/v1/invitations/{token}/accept/
- **THEN** user becomes team member

#### Scenario: Change member role
- **GIVEN** team owner
- **WHEN** PATCH /api/v1/teams/{id}/members/{member_id}/
- **THEN** member role is updated

#### Scenario: Remove member
- **GIVEN** team admin or owner
- **WHEN** DELETE /api/v1/teams/{id}/members/{member_id}/
- **THEN** member is removed from team

### Requirement: Permission Tests
The project SHALL enforce role-based permissions.

#### Scenario: Owner-only actions
- **GIVEN** user with member role
- **WHEN** attempting owner-only action (delete team, change owner)
- **THEN** 403 Forbidden returned

#### Scenario: Admin actions
- **GIVEN** user with admin role
- **WHEN** attempting admin action (invite, remove member)
- **THEN** action succeeds

#### Scenario: Cross-company isolation
- **GIVEN** user from Company A
- **WHEN** attempting to access Company B resources
- **THEN** 404 Not Found returned (not 403, for security)

### Requirement: Billing Tests
The project SHALL test billing operations.

#### Scenario: List plans
- **WHEN** GET /api/v1/billing/plans/
- **THEN** available plans returned
- **AND** includes pricing information

#### Scenario: Create checkout session
- **GIVEN** authenticated user
- **WHEN** POST /api/v1/billing/checkout/
- **THEN** Stripe checkout URL returned

#### Scenario: Webhook processing
- **GIVEN** valid Stripe webhook signature
- **WHEN** POST /api/v1/billing/webhooks/stripe/
- **THEN** event is processed
- **AND** subscription status updated

#### Scenario: Usage tracking
- **GIVEN** active subscription with limits
- **WHEN** usage is recorded
- **THEN** usage count increases
- **AND** limit enforcement works

### Requirement: E2E Automation Tests
The project SHALL have Playwright-based E2E tests.

#### Scenario: Complete signup flow
- **WHEN** user visits /register
- **AND** fills registration form
- **AND** submits form
- **THEN** user is registered
- **AND** redirected to dashboard

#### Scenario: Login/logout cycle
- **WHEN** user visits /login
- **AND** enters valid credentials
- **THEN** user is logged in
- **AND** can access dashboard
- **WHEN** user clicks logout
- **THEN** user is logged out
- **AND** redirected to login

#### Scenario: Team management flow
- **GIVEN** logged in owner
- **WHEN** user creates team
- **AND** invites member via email
- **THEN** invitation is sent
- **WHEN** invitee accepts
- **THEN** appears in team members list

### Requirement: Frontend Unit Tests
The project SHALL have Jest/Vitest tests for React components.

#### Scenario: Component rendering
- **WHEN** component is rendered
- **THEN** expected elements are present
- **AND** no console errors

#### Scenario: Form validation
- **WHEN** invalid input is entered
- **THEN** validation errors displayed
- **WHEN** valid input is entered
- **THEN** form submits successfully

#### Scenario: Protected route behavior
- **GIVEN** unauthenticated state
- **WHEN** accessing /dashboard
- **THEN** redirected to /login
