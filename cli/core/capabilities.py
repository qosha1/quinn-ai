"""
Capability mapping from worker skills to model capabilities.

Per CLAUDE.md: "Workers have skills (0-100) and cost (0-100). System maps to providers."
Skills gate what capabilities/tools a worker can use.

This module maps worker skill levels to the model capabilities defined in
shared/provider_types.py (ModelCapabilities).
"""

from typing import Optional

# Skill thresholds for unlocking capabilities
# Each capability requires a minimum skill level to be unlocked
SKILL_THRESHOLDS: dict[str, tuple[str, int]] = {
    # (skill_name, min_level) -> capability_name
    "coding": ("coding", 60),      # coding skill >= 60 unlocks coding capability
    "reasoning": ("reasoning", 50), # reasoning skill >= 50 unlocks reasoning capability
    "research": ("research", 40),   # research skill >= 40 unlocks research capability
    "tool_use": ("tool_use", 30),   # tool_use skill >= 30 unlocks tool_use capability
}

# All capabilities that can be unlocked
ALL_CAPABILITIES = ["coding", "reasoning", "research", "tool_use", "long_context"]


def get_worker_capabilities(skills: dict[str, int]) -> list[str]:
    """Get list of capabilities unlocked by worker's skills.

    Maps skill levels to model capabilities based on thresholds:
    - "coding" skill (60+) -> coding capability
    - "reasoning" skill (50+) -> reasoning capability
    - "research" skill (40+) -> research capability
    - "tool_use" skill (30+) -> tool_use capability

    Args:
        skills: Worker's skills dictionary mapping skill names to levels (0-100)

    Returns:
        List of capability names the worker has unlocked

    Example:
        >>> get_worker_capabilities({"coding": 75, "reasoning": 60})
        ['coding', 'reasoning']
        >>> get_worker_capabilities({"research": 45, "tool_use": 35})
        ['research', 'tool_use']
        >>> get_worker_capabilities({})
        []
    """
    capabilities: list[str] = []

    for capability, (skill_name, min_level) in SKILL_THRESHOLDS.items():
        skill_level = skills.get(skill_name, 0)
        if skill_level >= min_level:
            capabilities.append(capability)

    return capabilities


def worker_can_use_capability(skills: dict[str, int], capability: str) -> bool:
    """Check if a worker's skills unlock a specific capability.

    Args:
        skills: Worker's skills dictionary mapping skill names to levels (0-100)
        capability: The capability name to check

    Returns:
        True if the worker's skills unlock the capability, False otherwise

    Example:
        >>> worker_can_use_capability({"coding": 75}, "coding")
        True
        >>> worker_can_use_capability({"coding": 50}, "coding")
        False
        >>> worker_can_use_capability({"reasoning": 60}, "reasoning")
        True
    """
    if capability not in SKILL_THRESHOLDS:
        # Unknown capabilities are not unlocked
        return False

    skill_name, min_level = SKILL_THRESHOLDS[capability]
    skill_level = skills.get(skill_name, 0)
    return skill_level >= min_level


def get_capability_threshold(capability: str) -> Optional[tuple[str, int]]:
    """Get the skill and minimum level required for a capability.

    Args:
        capability: The capability name

    Returns:
        Tuple of (skill_name, min_level) or None if capability not found

    Example:
        >>> get_capability_threshold("coding")
        ('coding', 60)
        >>> get_capability_threshold("unknown")
        None
    """
    return SKILL_THRESHOLDS.get(capability)


def get_missing_skills_for_capability(
    skills: dict[str, int], capability: str
) -> Optional[tuple[str, int]]:
    """Get the skill gap needed to unlock a capability.

    Args:
        skills: Worker's current skills dictionary
        capability: The capability to check

    Returns:
        Tuple of (skill_name, points_needed) or None if already unlocked
        or capability doesn't exist

    Example:
        >>> get_missing_skills_for_capability({"coding": 45}, "coding")
        ('coding', 15)
        >>> get_missing_skills_for_capability({"coding": 75}, "coding")
        None
    """
    if capability not in SKILL_THRESHOLDS:
        return None

    skill_name, min_level = SKILL_THRESHOLDS[capability]
    current_level = skills.get(skill_name, 0)

    if current_level >= min_level:
        return None

    return (skill_name, min_level - current_level)


def filter_capabilities_by_skills(
    skills: dict[str, int], required_capabilities: list[str]
) -> tuple[list[str], list[str]]:
    """Filter capabilities into available and missing based on worker skills.

    Useful for determining what a worker can and cannot do.

    Args:
        skills: Worker's skills dictionary
        required_capabilities: List of capabilities to check

    Returns:
        Tuple of (available_capabilities, missing_capabilities)

    Example:
        >>> filter_capabilities_by_skills(
        ...     {"coding": 75, "reasoning": 40},
        ...     ["coding", "reasoning", "research"]
        ... )
        (['coding'], ['reasoning', 'research'])
    """
    available: list[str] = []
    missing: list[str] = []

    for capability in required_capabilities:
        if worker_can_use_capability(skills, capability):
            available.append(capability)
        else:
            missing.append(capability)

    return available, missing
