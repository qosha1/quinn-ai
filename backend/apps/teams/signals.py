"""
Signal handlers for Teams app.
"""

from django.db.models.signals import post_save
from django.dispatch import receiver

from apps.teams.models import Company, Team, TeamMember


@receiver(post_save, sender=Company)
def create_default_team(sender, instance, created, **kwargs):
    """
    Auto-create a default team when a new company is created.

    Args:
        sender: The model class (Company)
        instance: The Company instance being saved
        created: Boolean indicating if this is a new instance
        **kwargs: Additional keyword arguments
    """
    if created:
        # Create default team
        team = Team.objects.create(
            name="Default Team",
            slug="default",
            company=instance,
            settings={}
        )

        # Add company owner as team owner
        TeamMember.objects.create(
            user=instance.owner,
            team=team,
            role=TeamMember.Role.OWNER,
            invited_by=instance.owner
        )
