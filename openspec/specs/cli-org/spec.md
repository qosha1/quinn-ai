# CLI Org Lifecycle Specification

## Overview

Organizations have a single lifecycle state machine tracking operational status.

## Requirements

### Requirement: Org Lifecycle States
Organizations SHALL have lifecycle states tracking operational status.

#### Scenario: Valid lifecycle states
- **WHEN** an org exists
- **THEN** its status MUST be one of: 'uninitialized', 'initialized', 'running', 'stopped'

#### Scenario: Initial state
- **WHEN** a database is created
- **THEN** org status SHALL be 'uninitialized'

### Requirement: Lifecycle State Transitions
The system SHALL enforce valid org state transitions.

#### Scenario: From uninitialized
- **WHEN** org is in 'uninitialized' state
- **THEN** it MAY only transition to 'initialized'

#### Scenario: From initialized
- **WHEN** org is in 'initialized' state
- **THEN** it MAY only transition to 'running'

#### Scenario: From running
- **WHEN** org is in 'running' state
- **THEN** it MAY only transition to 'stopped'

#### Scenario: From stopped
- **WHEN** org is in 'stopped' state
- **THEN** it MAY only transition to 'running'

#### Scenario: Invalid transition rejection
- **WHEN** an invalid state transition is attempted
- **THEN** InvalidOrgTransition exception SHALL be raised

### Requirement: Org Initialization
The system SHALL support org initialization with a CEO.

#### Scenario: init method creates CEO
- **WHEN** init(ceo_name, ceo_role) is called on 'uninitialized' org
- **THEN** a worker SHALL be created with the given name and role
- **AND** the worker SHALL have no manager (root of hierarchy)
- **AND** org status SHALL transition to 'initialized'
- **AND** ceo_worker_id SHALL be set to the new worker's ID

#### Scenario: init requires uninitialized state
- **WHEN** init() is called on org not in 'uninitialized' state
- **THEN** InvalidOrgTransition exception SHALL be raised

### Requirement: Org Start
The system SHALL support starting an org.

#### Scenario: start from initialized
- **WHEN** start() is called on 'initialized' org
- **THEN** CEO worker lifecycle SHALL transition to 'active'
- **AND** org status SHALL transition to 'running'
- **AND** started_at SHALL be set to current time

#### Scenario: start from stopped (resume)
- **WHEN** start() is called on 'stopped' org
- **THEN** org status SHALL transition to 'running'
- **AND** started_at SHALL be updated to current time

#### Scenario: start requires initialized or stopped state
- **WHEN** start() is called on org in 'uninitialized' or 'running' state
- **THEN** InvalidOrgTransition exception SHALL be raised

### Requirement: Org Stop
The system SHALL support stopping an org.

#### Scenario: stop method
- **WHEN** stop() is called on 'running' org
- **THEN** org status SHALL transition to 'stopped'
- **AND** stopped_at SHALL be set to current time

#### Scenario: stop requires running state
- **WHEN** stop() is called on org not in 'running' state
- **THEN** InvalidOrgTransition exception SHALL be raised

### Requirement: Org Properties
The Org class SHALL provide status properties.

#### Scenario: status property
- **WHEN** status property is accessed
- **THEN** it SHALL return the current org lifecycle state

#### Scenario: ceo property
- **WHEN** ceo property is accessed on initialized org
- **THEN** it SHALL return the CEO Worker instance

#### Scenario: ceo property on uninitialized
- **WHEN** ceo property is accessed on 'uninitialized' org
- **THEN** it SHALL return None

#### Scenario: is_operational property
- **WHEN** is_operational property is checked
- **THEN** it SHALL return True only if status is 'running'

### Requirement: Org Query Helpers
The Org class SHALL provide query helpers.

#### Scenario: worker_count property
- **WHEN** worker_count property is accessed
- **THEN** it SHALL return the total number of workers in the org

#### Scenario: active_session_count property
- **WHEN** active_session_count property is accessed
- **THEN** it SHALL return the count of workers with active sessions

### Requirement: State Constraints
The system SHALL enforce constraints based on org state.

#### Scenario: No workers when uninitialized
- **WHEN** org is 'uninitialized'
- **THEN** no workers SHALL exist

#### Scenario: Only CEO when initialized
- **WHEN** org is 'initialized'
- **THEN** exactly one worker (CEO) SHALL exist

#### Scenario: CEO is root
- **WHEN** org has a CEO
- **THEN** CEO worker SHALL have manager_id = NULL

### Requirement: Class Method
The Org class SHALL provide a class method for loading.

#### Scenario: load class method
- **WHEN** Org.load(db) is called
- **THEN** it SHALL return an Org instance with state loaded from database
