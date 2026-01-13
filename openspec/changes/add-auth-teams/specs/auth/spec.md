# Authentication Specification

## ADDED Requirements

### Requirement: Custom User Model
The system SHALL use a custom User model with email as the username field.

#### Scenario: User registration
- **WHEN** user registers with email and password
- **THEN** User is created with email as username
- **AND** password is securely hashed
- **AND** user is assigned to a company

### Requirement: JWT Authentication
The system SHALL authenticate API requests using JWT tokens.

#### Scenario: Token obtain
- **WHEN** POST /api/v1/token/ with valid credentials
- **THEN** response contains access and refresh tokens
- **AND** access token expires in 30 minutes
- **AND** refresh token expires in 1 day

#### Scenario: Token refresh
- **WHEN** POST /api/v1/token/refresh/ with valid refresh token
- **THEN** new access token is returned

### Requirement: API Key Authentication
The system SHALL support API key authentication for server-to-server calls.

#### Scenario: API key auth
- **WHEN** request includes X-API-Key header
- **THEN** request is authenticated as the key owner
- **AND** key scopes are enforced
