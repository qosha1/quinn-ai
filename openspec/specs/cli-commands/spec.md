# CLI Commands Specification

## Overview

The `qn` CLI provides organization and worker management commands.

## Requirements

### Requirement: CLI Entry Point
The system SHALL provide a `qn` command as the main entry point.

#### Scenario: qn command exists
- **WHEN** `qn` is invoked
- **THEN** it SHALL display help text with available subcommands

#### Scenario: qn --help
- **WHEN** `qn --help` is invoked
- **THEN** it SHALL display usage information

### Requirement: Command Namespaces
The CLI SHALL provide two command namespaces.

#### Scenario: qn org namespace
- **WHEN** `qn org` is invoked
- **THEN** it SHALL display org subcommands

#### Scenario: qn wrkr namespace
- **WHEN** `qn wrkr` is invoked
- **THEN** it SHALL display wrkr subcommands

### Requirement: Global Options
The CLI SHALL support global configuration options.

#### Scenario: --org-path option
- **WHEN** `--org-path PATH` is provided
- **THEN** all commands SHALL use PATH as the org folder

#### Scenario: QUINN_ORG_PATH environment variable
- **WHEN** QUINN_ORG_PATH is set
- **AND** --org-path is not provided
- **THEN** commands SHALL use QUINN_ORG_PATH as the org folder

### Requirement: qn org init Command
The system SHALL support org initialization.

#### Scenario: qn org init
- **WHEN** `qn org init` is invoked in an empty directory
- **THEN** org folder structure SHALL be created
- **AND** database SHALL be initialized
- **AND** CEO worker SHALL be created

#### Scenario: qn org init --ceo-name
- **WHEN** `qn org init --ceo-name "Alice"` is invoked
- **THEN** CEO SHALL be created with name "Alice"

#### Scenario: qn org init in existing org
- **WHEN** `qn org init` is invoked in existing org
- **THEN** error SHALL be displayed
- **AND** no changes SHALL be made

### Requirement: qn org start Command
The system SHALL support starting an org.

#### Scenario: qn org start
- **WHEN** `qn org start` is invoked on initialized org
- **THEN** org SHALL transition to running state
- **AND** CEO session SHALL be spawned

#### Scenario: qn org start on uninitialized
- **WHEN** `qn org start` is invoked on uninitialized org
- **THEN** error SHALL be displayed

### Requirement: qn org stop Command
The system SHALL support stopping an org.

#### Scenario: qn org stop
- **WHEN** `qn org stop` is invoked on running org
- **THEN** all worker sessions SHALL be stopped gracefully
- **AND** org SHALL transition to stopped state

#### Scenario: qn org stop on stopped org
- **WHEN** `qn org stop` is invoked on stopped org
- **THEN** error SHALL be displayed

### Requirement: qn org status Command
The system SHALL display org status.

#### Scenario: qn org status
- **WHEN** `qn org status` is invoked
- **THEN** org status SHALL be displayed
- **AND** worker count SHALL be displayed
- **AND** active session count SHALL be displayed

### Requirement: qn wrkr get-work Command
The system SHALL allow workers to get work.

#### Scenario: qn wrkr get-work
- **WHEN** `qn wrkr get-work` is invoked by worker
- **THEN** next assigned bead SHALL be returned
- **AND** beads SHALL be sorted by priority

#### Scenario: qn wrkr get-work with no work
- **WHEN** `qn wrkr get-work` is invoked
- **AND** no beads are assigned to worker
- **THEN** empty response SHALL be returned

### Requirement: msgr inbox Command
The system SHALL allow workers to view messages and notifications.

#### Scenario: msgr inbox
- **WHEN** `msgr inbox` is invoked
- **THEN** unread notifications SHALL be listed first
- **AND** messages SHALL include sender and timestamp
- **AND** worker identity SHALL be obtained from QUINN_WORKER_ID

### Requirement: msgr send Command
The system SHALL allow workers to send messages.

#### Scenario: msgr send to channel
- **WHEN** `msgr send #CHANNEL "message"` is invoked
- **THEN** message SHALL be created in channel
- **AND** notifications SHALL be sent to subscribers
- **AND** channel reference SHALL be resolved from name

#### Scenario: msgr send direct message
- **WHEN** `msgr send @WORKER "message"` is invoked
- **THEN** DM channel SHALL be created or retrieved
- **AND** message SHALL be sent to worker
- **AND** notification SHALL be created for recipient

### Requirement: qn wrkr status Command
The system SHALL display worker status.

#### Scenario: qn wrkr status
- **WHEN** `qn wrkr status` is invoked
- **THEN** worker lifecycle status SHALL be displayed
- **AND** runtime status SHALL be displayed
- **AND** current task SHALL be displayed if any

### Requirement: Worker Context
Worker commands SHALL require worker context.

#### Scenario: QUINN_WORKER_ID required
- **WHEN** wrkr command is invoked
- **AND** QUINN_WORKER_ID is not set
- **THEN** error SHALL be displayed

### Requirement: Exit Codes
The CLI SHALL use standard exit codes.

#### Scenario: Success exit code
- **WHEN** command completes successfully
- **THEN** exit code SHALL be 0

#### Scenario: Error exit code
- **WHEN** command fails
- **THEN** exit code SHALL be non-zero
- **AND** error message SHALL be displayed to stderr
