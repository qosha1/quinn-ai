# CLI Worker State Machine Specification

## Overview

Workers have dual state machines: lifecycle (HR state) and runtime (process state).

## Requirements

### Requirement: Worker Lifecycle States
Workers SHALL have lifecycle states tracking their organizational status.

#### Scenario: Valid lifecycle states
- **WHEN** a worker is created
- **THEN** its lifecycle status MUST be one of: 'pending', 'onboarding', 'active', 'offboarding', 'terminated'

#### Scenario: Initial state
- **WHEN** a worker is hired
- **THEN** its initial lifecycle status SHALL be 'pending'

### Requirement: Lifecycle State Transitions
The system SHALL enforce valid lifecycle state transitions.

#### Scenario: From pending
- **WHEN** worker is in 'pending' state
- **THEN** it MAY only transition to 'onboarding'

#### Scenario: From onboarding
- **WHEN** worker is in 'onboarding' state
- **THEN** it MAY transition to 'active' (success) or 'terminated' (failure)

#### Scenario: From active
- **WHEN** worker is in 'active' state
- **THEN** it MAY only transition to 'offboarding'

#### Scenario: From offboarding
- **WHEN** worker is in 'offboarding' state
- **THEN** it MAY only transition to 'terminated'

#### Scenario: Terminal state
- **WHEN** worker is in 'terminated' state
- **THEN** it SHALL NOT transition to any other state

#### Scenario: Invalid transition rejection
- **WHEN** an invalid state transition is attempted
- **THEN** InvalidStateTransition exception SHALL be raised

### Requirement: Worker Runtime States
Workers SHALL have runtime states tracking their session/process status.

#### Scenario: Valid runtime states
- **WHEN** a worker has a runtime state
- **THEN** it MUST be one of: 'starting', 'running', 'idle', 'stopped', 'crashed'

#### Scenario: No runtime state for pending
- **WHEN** worker lifecycle is 'pending'
- **THEN** worker SHALL NOT have a runtime state

### Requirement: Runtime State Transitions
The system SHALL enforce valid runtime state transitions.

#### Scenario: From starting
- **WHEN** worker runtime is 'starting'
- **THEN** it MAY transition to 'running' or 'crashed'

#### Scenario: From running
- **WHEN** worker runtime is 'running'
- **THEN** it MAY transition to 'idle', 'stopped', or 'crashed'

#### Scenario: From idle
- **WHEN** worker runtime is 'idle'
- **THEN** it MAY transition to 'running' or 'stopped'

#### Scenario: From stopped
- **WHEN** worker runtime is 'stopped'
- **THEN** it MAY only transition to 'starting'

#### Scenario: From crashed
- **WHEN** worker runtime is 'crashed'
- **THEN** it MAY only transition to 'starting'

### Requirement: Lifecycle Methods
The Worker class SHALL provide lifecycle transition methods.

#### Scenario: start_onboarding method
- **WHEN** start_onboarding() is called on 'pending' worker
- **THEN** worker SHALL transition to 'onboarding'

#### Scenario: complete_onboarding method
- **WHEN** complete_onboarding() is called on 'onboarding' worker
- **THEN** worker SHALL transition to 'active'

#### Scenario: start_offboarding method
- **WHEN** start_offboarding() is called on 'active' worker
- **THEN** worker SHALL transition to 'offboarding'

#### Scenario: terminate method
- **WHEN** terminate() is called on 'offboarding' worker
- **THEN** worker SHALL transition to 'terminated'

### Requirement: Runtime Methods
The Worker class SHALL provide runtime transition methods.

#### Scenario: start_session method
- **WHEN** start_session(pid) is called
- **THEN** worker_state SHALL be created/updated with 'starting' status and PID

#### Scenario: session_ready method
- **WHEN** session_ready() is called on 'starting' worker
- **THEN** runtime SHALL transition to 'running'

#### Scenario: begin_work method
- **WHEN** begin_work(task_id) is called on 'idle' worker
- **THEN** runtime SHALL transition to 'running' with current_task_id set

#### Scenario: finish_work method
- **WHEN** finish_work() is called on 'running' worker
- **THEN** runtime SHALL transition to 'idle' with current_task_id cleared

#### Scenario: stop_session method
- **WHEN** stop_session() is called on running/idle worker
- **THEN** runtime SHALL transition to 'stopped'

#### Scenario: mark_crashed method
- **WHEN** mark_crashed() is called
- **THEN** runtime SHALL transition to 'crashed'

### Requirement: Work Capability
The system SHALL determine if a worker can accept work.

#### Scenario: Can work query
- **WHEN** can_work property is checked
- **THEN** it SHALL return True only if lifecycle is 'active' and runtime is 'running' or 'idle'

#### Scenario: Pending cannot work
- **WHEN** worker lifecycle is 'pending'
- **THEN** can_work SHALL return False

#### Scenario: Onboarding limited work
- **WHEN** worker lifecycle is 'onboarding'
- **THEN** can_work SHALL return False (onboarding tasks handled separately)

### Requirement: Session Activity
The system SHALL track session activity status.

#### Scenario: Session active query
- **WHEN** is_session_active property is checked
- **THEN** it SHALL return True if runtime is 'starting', 'running', or 'idle'

#### Scenario: Session inactive
- **WHEN** runtime is 'stopped' or 'crashed'
- **THEN** is_session_active SHALL return False

### Requirement: Heartbeat Tracking
The system SHALL support heartbeat-based liveness detection.

#### Scenario: Record heartbeat
- **WHEN** record_heartbeat() is called
- **THEN** worker_state.last_activity SHALL be updated to current time

#### Scenario: Heartbeat staleness check
- **WHEN** is_heartbeat_stale(threshold_seconds) is called
- **THEN** it SHALL return True if last_activity is older than threshold

### Requirement: Lifecycle-Runtime Constraints
The system SHALL enforce constraints between lifecycle and runtime states.

#### Scenario: Cannot start session when pending
- **WHEN** start_session() is called on 'pending' worker
- **THEN** exception SHALL be raised

#### Scenario: Cannot start session when terminated
- **WHEN** start_session() is called on 'terminated' worker
- **THEN** exception SHALL be raised
