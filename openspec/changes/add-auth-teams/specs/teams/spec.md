# Teams Specification

## ADDED Requirements

### Requirement: Company Model
The system SHALL provide a Company model as the root tenant.

#### Scenario: Company creation
- **WHEN** new company is created
- **THEN** a default team is auto-created
- **AND** creating user becomes owner

### Requirement: Team Model
The system SHALL provide Teams within Companies for workspace organization.

#### Scenario: Team membership
- **WHEN** user is added to team
- **THEN** TeamMember record is created with role
- **AND** user can access team resources

### Requirement: Role-Based Access Control
The system SHALL enforce role hierarchy: owner > admin > member > viewer.

#### Scenario: Admin permissions
- **WHEN** admin user attempts to delete team
- **THEN** action is allowed
- **WHEN** member user attempts to delete team
- **THEN** action is denied with 403

### Requirement: Team Invitations
The system SHALL support inviting users to teams via email.

#### Scenario: Invite user
- **WHEN** admin invites email to team
- **THEN** TeamInvitation is created with unique token
- **AND** invited user can accept and join team

### Requirement: Resource Isolation
The system SHALL isolate resources by company/team ownership.

#### Scenario: Query filtering
- **WHEN** user queries resources
- **THEN** only resources from their company are returned
- **AND** cross-tenant access is prevented
