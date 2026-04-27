"""EscalationConfig dataclass + YAML loader.

Lives in its own file because load_from_yaml is ~100 lines of YAML schema
parsing and would make types.py unbalanced.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import yaml

from shared.escalation.types import (
    AutoEscalationSettings,
    BoardInterventionSettings,
    EscalationPathLevel,
    NotificationSettings,
    RetryPolicy,
    TimeoutWarningSettings,
)


@dataclass
class EscalationConfig:
    """
    Configuration for escalation behavior.

    This class supports both simple programmatic configuration and loading
    from YAML files (like escalation.yaml). Use load_from_yaml() to load
    a full configuration including escalation paths, notification rules,
    and auto-escalation settings.

    Attributes:
        timeout_seconds: Default timeout before auto-escalation (default 300s).
        max_escalation_depth: Maximum levels to escalate before failing (default 10).
        auto_escalate_on_timeout: Whether to automatically escalate on timeout.
        retry_attempts: Number of retry attempts before escalating (default 1).
        enable_history: Whether to track escalation history (default True).
        max_history_size: Maximum history entries to retain (default 10000).
        max_queue_size: Maximum pending escalations (default 1000).
        escalation_paths: Named escalation paths (default, critical, blocked, etc.).
        retry_policy: Retry policy for failed operations.
        notification_settings: Settings for escalation notifications.
        timeout_warning: Settings for timeout warnings.
        auto_escalation: Settings for automatic escalation checks.
        board_intervention: Settings for board intervention thresholds.
    """

    timeout_seconds: int = 300
    max_escalation_depth: int = 10
    auto_escalate_on_timeout: bool = True
    retry_attempts: int = 1
    enable_history: bool = True
    max_history_size: int = 10000
    max_queue_size: int = 1000

    # Extended configuration from escalation.yaml
    escalation_paths: dict[str, list[EscalationPathLevel]] = field(default_factory=dict)
    retry_policy: RetryPolicy = field(default_factory=RetryPolicy)
    notification_settings: NotificationSettings = field(default_factory=NotificationSettings)
    timeout_warning: TimeoutWarningSettings = field(default_factory=TimeoutWarningSettings)
    auto_escalation: AutoEscalationSettings = field(default_factory=AutoEscalationSettings)
    board_intervention: BoardInterventionSettings = field(default_factory=BoardInterventionSettings)

    def get_path(self, path_name: str = "default") -> list[EscalationPathLevel]:
        """
        Get an escalation path by name.

        Args:
            path_name: Name of the path (default, critical, blocked, okr_linked).

        Returns:
            List of escalation levels for the path, or empty list if not found.
        """
        return self.escalation_paths.get(path_name, [])

    def get_timeout_for_level(
        self, path_name: str, level: int
    ) -> int | None:
        """
        Get the timeout in seconds for a specific level in a path.

        Args:
            path_name: Name of the escalation path.
            level: The level number (1-based).

        Returns:
            Timeout in seconds, or None if level not found.
        """
        for path_level in self.get_path(path_name):
            if path_level.level == level:
                return path_level.after_minutes * 60
        return None

    @classmethod
    def load_from_yaml(cls, path: str | Path) -> EscalationConfig:
        """
        Load escalation configuration from a YAML file.

        The YAML file should follow the structure defined in
        cli/config/escalation.yaml, including:
        - default_timeout_minutes
        - escalation_paths (default, critical, blocked, okr_linked)
        - retry_policy
        - notification_rules
        - auto_escalation
        - board_intervention

        Args:
            path: Path to the YAML configuration file.

        Returns:
            EscalationConfig populated from the YAML file.

        Raises:
            FileNotFoundError: If the YAML file doesn't exist.
            yaml.YAMLError: If the YAML is invalid.
        """
        path = Path(path)
        with path.open() as f:
            data = yaml.safe_load(f)

        # Parse escalation paths
        escalation_paths: dict[str, list[EscalationPathLevel]] = {}
        for path_name, levels in data.get("escalation_paths", {}).items():
            escalation_paths[path_name] = [
                EscalationPathLevel(
                    level=lvl["level"],
                    to=lvl["to"],
                    after_minutes=lvl["after_minutes"],
                    priority_bump=lvl.get("priority_bump", 0),
                )
                for lvl in levels
            ]

        # Parse retry policy
        retry_data = data.get("retry_policy", {})
        retry_policy = RetryPolicy(
            max_retries=retry_data.get("max_retries", 3),
            backoff=retry_data.get("backoff", "exponential"),
            base_delay_minutes=retry_data.get("base_delay_minutes", 15),
            max_delay_minutes=retry_data.get("max_delay_minutes", 120),
        )

        # Parse notification settings
        notif_data = data.get("notification_rules", {})
        esc_notif = notif_data.get("escalation", {})
        res_notif = notif_data.get("resolution", {})
        notification_settings = NotificationSettings(
            notify_original_assignee=esc_notif.get("notify_original_assignee", True),
            notify_escalation_target=esc_notif.get("notify_escalation_target", True),
            create_bead=esc_notif.get("create_bead", True),
            include_context=esc_notif.get("include_context", True),
            channel=esc_notif.get("channel"),
            notify_escalation_chain=res_notif.get("notify_escalation_chain", True),
        )

        # Parse timeout warning settings
        warn_data = notif_data.get("timeout_warning", {})
        timeout_warning = TimeoutWarningSettings(
            enabled=warn_data.get("enabled", True),
            warning_before_minutes=warn_data.get("warning_before_minutes", 15),
            notify_assignee=warn_data.get("notify_assignee", True),
        )

        # Parse auto-escalation settings
        auto_data = data.get("auto_escalation", {})
        auto_escalation = AutoEscalationSettings(
            enabled=auto_data.get("enabled", True),
            check_interval_minutes=auto_data.get("check_interval_minutes", 5),
            escalatable_states=auto_data.get(
                "escalatable_states", ["open", "in_progress", "blocked"]
            ),
            exempt_states=auto_data.get("exempt_states", ["draft", "review", "closed"]),
        )

        # Parse board intervention settings
        board_data = data.get("board_intervention", {})
        board_intervention = BoardInterventionSettings(
            consecutive_ceo_escalations=board_data.get("consecutive_ceo_escalations", 3),
            org_wide_escalation_threshold=board_data.get(
                "org_wide_escalation_threshold", 0.25
            ),
            threshold_window_minutes=board_data.get("threshold_window_minutes", 1440),
        )

        # Convert default_timeout_minutes to seconds
        default_timeout_minutes = data.get("default_timeout_minutes", 5)
        timeout_seconds = default_timeout_minutes * 60

        return cls(
            timeout_seconds=timeout_seconds,
            retry_attempts=retry_policy.max_retries,
            escalation_paths=escalation_paths,
            retry_policy=retry_policy,
            notification_settings=notification_settings,
            timeout_warning=timeout_warning,
            auto_escalation=auto_escalation,
            board_intervention=board_intervention,
        )
