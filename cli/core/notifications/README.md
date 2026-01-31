# Notification System

Multi-channel notification system for board communication with escalation integration.

## Overview

The notification system provides multiple channels for sending alerts to board members:
- **File Queue**: Always available, writes to `storage/shared/board/inbox/`
- **Desktop Notifications**: Platform-specific (macOS/Linux/Windows)
- **Slack**: Webhook integration
- **Email**: SMTP integration

## Configuration

Configure channels in `org/config/notifications.yaml`:

```yaml
version: 1

channels:
  file_queue:
    enabled: true
    retention_days: 7

  desktop:
    enabled: true
    min_priority: high  # Only urgent/high priority

  slack:
    enabled: false
    webhook_url: ${SLACK_WEBHOOK_URL}
    min_priority: high

  email:
    enabled: false
    smtp_host: ${SMTP_HOST}
    smtp_port: 587
    from_address: ${FROM_EMAIL}
    to_address: ${BOARD_EMAIL}

rate_limiting:
  max_per_minute: 5
  max_per_hour: 20

quiet_hours:
  enabled: false
  start: "22:00"
  end: "07:00"
```

## Escalation Integration

The notification system automatically sends board notifications for escalation events:

- **Created** (NORMAL priority): New escalation submitted
- **Timeout** (HIGH priority): Escalation timed out, auto-escalating
- **Resolved** (INFO priority): Escalation successfully resolved
- **Failed** (URGENT priority): Escalation failed, board intervention needed

### How It Works

1. Worker submits escalation via `EscalationManager`
2. `EscalationNotificationHandler` receives event
3. Converts escalation to `BoardNotification`
4. `NotificationDispatcher` routes to all enabled channels
5. Board sees notification in UI and/or external channels

### Example Flow

```python
# In OrgContext, escalation manager is automatically wired with notifications
with OrgContext.create(org_path) as ctx:
    # Submit an escalation
    escalation = ctx.escalation_manager.submit(
        worker_id="worker-123",
        issue="Need help with task ABC",
        context={"task_id": "abc", "urgency": "high"}
    )
    # Notification is automatically sent to board
```

## Manual Notifications

You can also send notifications directly:

```python
from cli.core.notifications import create_board_notifier, BoardNotification, NotificationPriority

# Create notifier
notifier = create_board_notifier(org_path)

# Send notification
notification = BoardNotification(
    title="System Alert",
    message="Important update for board review",
    priority=NotificationPriority.HIGH,
    worker_id="system",
)

results = notifier.dispatcher.dispatch(notification)
```

## Architecture

- `channels.py`: Channel implementations (file, desktop, slack, email)
- `dispatcher.py`: Routing with rate limiting and quiet hours
- `escalation_handler.py`: Bridges escalation system to notifications
- `config.py`: Configuration loading
- `board_notifier.py`: High-level board notification facade

All escalation notifications are automatically wired in `OrgContext.escalation_manager`.
