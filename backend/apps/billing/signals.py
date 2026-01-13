"""
Signal handlers for billing events.
"""

import logging

from django.db.models.signals import post_save
from django.dispatch import receiver

from apps.billing.models import Subscription

logger = logging.getLogger(__name__)


@receiver(post_save, sender=Subscription)
def subscription_status_changed(sender, instance, created, **kwargs):
    """
    Handle subscription status changes.

    Logs subscription updates and can trigger additional actions.
    """
    if created:
        logger.info(
            f"New subscription created: {instance.id} for company {instance.company.id}"
        )
    else:
        logger.info(
            f"Subscription updated: {instance.id}, status: {instance.status}"
        )

    # You can add additional logic here, such as:
    # - Sending notifications
    # - Updating company permissions
    # - Triggering analytics events
    # - Updating cache
