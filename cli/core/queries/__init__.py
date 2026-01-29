"""Query helpers for common database operations.

This module provides high-level functions for interacting with quinn.db
without writing raw SQL. Functions are organized by entity type into
focused submodules.

For backward compatibility, all exports are re-exported at the package level.
"""

from .common import generate_id, parse_datetime, get_or_create_config
from .org import OrgState, get_org_state, update_org_status
from .team import Team, TeamMember, create_team, get_team, get_team_channel, get_team_children, get_all_teams, add_team_member, get_team_member, update_team_member_role, remove_team_member, get_team_members_list, get_worker_team_memberships, get_team_members_by_role
from .worker import Worker, WorkerState, create_worker, get_worker, get_worker_by_name, update_worker_status, get_workers_by_status, get_workers_by_manager, get_team_workers, get_all_workers_for_topology, get_root_worker, create_worker_state, get_worker_state, update_worker_runtime_status, record_worker_heartbeat, increment_worker_task_count, get_workers_by_runtime_status, is_worker_manager
from .channel import Channel, Message, ChannelAccessError, create_channel, create_direct_channel, get_or_create_direct_channel, get_channel, get_channel_by_name, create_default_org_channels, can_subscribe_to_channel, subscribe_to_channel, is_subscribed_to_channel, unsubscribe_from_channel, get_channel_subscribers, get_worker_channels, unsubscribe_from_all_channels, create_message, create_message_with_notifications, get_message, get_channel_messages, get_thread_messages, search_messages, add_message_ref, get_message_refs

# Backward compatibility alias
get_messages_in_channel = get_channel_messages
from .budget import BudgetPool, BudgetAllocation, BudgetTransaction, BudgetBalance, create_budget_pool, get_budget_pool, get_all_budget_pools, update_budget_pool, delete_budget_pool, create_budget_allocation, get_budget_allocation, get_worker_allocations, get_current_allocation, get_allocations_by_pool, update_allocation_spend, delete_budget_allocation, create_budget_transaction, get_budget_transaction, get_transactions_by_allocation, get_transactions_by_worker, create_budget_balance, get_budget_balance, get_worker_balance, get_all_worker_balances, delete_budget_balance, get_pool_allocated_total, get_worker_delegation_authority, get_worker_allocated_budget, is_worker_manager
from .okr import KeyResult, OKR, OKRTreeNode, WorkOKRLink, create_okr, get_okr, update_okr_status, get_okrs_by_owner, list_okrs, get_child_okrs, update_okr_key_result, add_okr_key_result, get_okr_hierarchy, get_okr_ancestors, link_work_to_okr, unlink_work_from_okr, get_work_okr_link, get_work_for_okr, get_okrs_for_work, get_work_for_okr_hierarchy
from .permission import Permission, EffectivePermission, PermissionAudit, grant_permission, get_permission, get_permission_for_grantee, revoke_permission, revoke_permission_for_grantee, get_permissions_for_bead, get_permissions_for_worker, get_permissions_for_team, set_effective_permission, get_effective_permission, delete_effective_permission, delete_effective_permissions_for_bead, log_permission_audit, get_permission_audit_for_bead, get_permission_audit_for_worker, get_permission_denials
from .delegation import DelegationGrant, DelegationAuditRecord, RevokeResult, create_delegation_grant, get_delegation_grant, get_delegation_grant_by_id, revoke_delegation_grant, get_delegation_chain, check_delegation_cycle, get_delegations_by_delegator, expire_delegations, get_delegation_audit, get_worker_delegation_version, update_worker_delegation
from .config import get_config, set_config, get_lifecycle_config, get_all_lifecycle_configs
from .event import create_event, get_events_since, get_events_for_entity, get_events_by_type, get_events_by_actor, count_events

__all__ = [
    # Common utilities
    "generate_id",
    "parse_datetime",
    "get_or_create_config",
    # Org
    "OrgState",
    "get_org_state",
    "update_org_status",
    # Team
    "Team",
    "TeamMember",
    "create_team",
    "get_team",
    "get_team_channel",
    "get_team_children",
    "get_all_teams",
    "add_team_member",
    "get_team_member",
    "update_team_member_role",
    "remove_team_member",
    "get_team_members_list",
    "get_worker_team_memberships",
    "get_team_members_by_role",
    # Worker
    "Worker",
    "WorkerState",
    "create_worker",
    "get_worker",
    "get_worker_by_name",
    "update_worker_status",
    "get_workers_by_status",
    "get_workers_by_manager",
    "get_team_workers",
    "get_all_workers_for_topology",
    "get_root_worker",
    "create_worker_state",
    "get_worker_state",
    "update_worker_runtime_status",
    "record_worker_heartbeat",
    "increment_worker_task_count",
    "get_workers_by_runtime_status",
    "is_worker_manager",
    # Channel
    "Channel",
    "Message",
    "ChannelAccessError",
    "create_channel",
    "create_direct_channel",
    "get_or_create_direct_channel",
    "get_channel",
    "get_channel_by_name",
    "create_default_org_channels",
    "can_subscribe_to_channel",
    "subscribe_to_channel",
    "is_subscribed_to_channel",
    "unsubscribe_from_channel",
    "get_channel_subscribers",
    "get_worker_channels",
    "unsubscribe_from_all_channels",
    "create_message",
    "create_message_with_notifications",
    "get_message",
    "get_channel_messages",
    "get_messages_in_channel",  # Backward compatibility alias
    "get_thread_messages",
    "search_messages",
    "add_message_ref",
    "get_message_refs",
    # Budget
    "BudgetPool",
    "BudgetAllocation",
    "BudgetTransaction",
    "BudgetBalance",
    "create_budget_pool",
    "get_budget_pool",
    "get_all_budget_pools",
    "update_budget_pool",
    "delete_budget_pool",
    "create_budget_allocation",
    "get_budget_allocation",
    "get_worker_allocations",
    "get_current_allocation",
    "get_allocations_by_pool",
    "update_allocation_spend",
    "delete_budget_allocation",
    "create_budget_transaction",
    "get_budget_transaction",
    "get_transactions_by_allocation",
    "get_transactions_by_worker",
    "create_budget_balance",
    "get_budget_balance",
    "get_worker_balance",
    "get_worker_allocated_budget",
    "get_worker_delegation_authority",
    "get_all_worker_balances",
    "delete_budget_balance",
    "get_pool_allocated_total",
    "is_worker_manager",
    # OKR
    "KeyResult",
    "OKR",
    "OKRTreeNode",
    "WorkOKRLink",
    "create_okr",
    "get_okr",
    "update_okr_status",
    "get_okrs_by_owner",
    "list_okrs",
    "get_child_okrs",
    "update_okr_key_result",
    "add_okr_key_result",
    "get_okr_hierarchy",
    "get_okr_ancestors",
    "link_work_to_okr",
    "unlink_work_from_okr",
    "get_work_okr_link",
    "get_work_for_okr",
    "get_okrs_for_work",
    "get_work_for_okr_hierarchy",
    # Permission
    "Permission",
    "EffectivePermission",
    "PermissionAudit",
    "grant_permission",
    "get_permission",
    "get_permission_for_grantee",
    "revoke_permission",
    "revoke_permission_for_grantee",
    "get_permissions_for_bead",
    "get_permissions_for_worker",
    "get_permissions_for_team",
    "set_effective_permission",
    "get_effective_permission",
    "delete_effective_permission",
    "delete_effective_permissions_for_bead",
    "log_permission_audit",
    "get_permission_audit_for_bead",
    "get_permission_audit_for_worker",
    "get_permission_denials",
    # Delegation
    "DelegationGrant",
    "DelegationAuditRecord",
    "RevokeResult",
    "create_delegation_grant",
    "get_delegation_grant",
    "get_delegation_grant_by_id",
    "revoke_delegation_grant",
    "get_delegation_chain",
    "check_delegation_cycle",
    "get_delegations_by_delegator",
    "expire_delegations",
    "get_delegation_audit",
    "get_worker_delegation_version",
    "update_worker_delegation",
    # Config
    "get_config",
    "set_config",
    "get_lifecycle_config",
    "get_all_lifecycle_configs",
    # Event
    "create_event",
    "get_events_since",
    "get_events_for_entity",
    "get_events_by_type",
    "get_events_by_actor",
    "count_events",
]
