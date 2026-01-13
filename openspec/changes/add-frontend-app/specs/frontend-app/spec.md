# Frontend App Specification

## ADDED Requirements

### Requirement: JWT Authentication Flow
The app SHALL authenticate users via JWT with the Django backend.

#### Scenario: Login
- **WHEN** user submits login form with valid credentials
- **THEN** tokens are stored securely
- **AND** user is redirected to dashboard
- **AND** auth state is updated

#### Scenario: Token refresh
- **WHEN** access token is near expiry
- **THEN** refresh token is used to obtain new access token
- **AND** refresh happens transparently

#### Scenario: Logout
- **WHEN** user clicks logout
- **THEN** tokens are cleared
- **AND** user is redirected to login

### Requirement: Route Protection
The app SHALL protect dashboard routes from unauthenticated access.

#### Scenario: Unauthenticated access
- **WHEN** unauthenticated user visits /dashboard
- **THEN** user is redirected to /login
- **AND** return URL is preserved

### Requirement: API Client
The app SHALL provide a typed API client with automatic token handling.

#### Scenario: API request
- **WHEN** component calls api.get('/users/me/')
- **THEN** request includes Authorization header
- **AND** response is typed
- **AND** 401 triggers token refresh or logout

### Requirement: Team Management UI
The app SHALL provide UI for managing team members.

#### Scenario: Invite member
- **WHEN** admin enters email and clicks invite
- **THEN** invitation is sent via API
- **AND** pending invitation is shown in list

#### Scenario: Change role
- **WHEN** owner changes member's role
- **THEN** role is updated via API
- **AND** UI reflects new role

### Requirement: Billing Management UI
The app SHALL provide UI for subscription and billing management.

#### Scenario: Subscribe to plan
- **WHEN** user clicks subscribe on a plan
- **THEN** Stripe checkout is initiated
- **AND** on success, subscription is active

#### Scenario: View invoices
- **WHEN** user visits billing/invoices
- **THEN** invoice history is displayed
- **AND** PDF links are available

### Requirement: Dashboard Layout
The app SHALL have a consistent dashboard layout with sidebar navigation.

#### Scenario: Navigation
- **WHEN** user clicks sidebar item
- **THEN** corresponding page loads
- **AND** sidebar shows active state

#### Scenario: Responsive sidebar
- **WHEN** viewing on mobile
- **THEN** sidebar collapses to hamburger menu
- **AND** can be toggled open/closed
