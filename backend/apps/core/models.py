"""
Core models providing base functionality for all apps.
"""

import uuid
from django.db import models


class BaseModel(models.Model):
    """
    Abstract base model with common fields for all models.

    Provides:
    - UUID primary key
    - Created timestamp (auto_now_add)
    - Updated timestamp (auto_now)
    """

    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
        help_text="Unique identifier for this record"
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        help_text="Timestamp when this record was created"
    )
    updated_at = models.DateTimeField(
        auto_now=True,
        help_text="Timestamp when this record was last updated"
    )

    class Meta:
        abstract = True
        ordering = ["-created_at"]

    def __str__(self):
        """Return string representation of the model."""
        return f"{self.__class__.__name__}({self.id})"
