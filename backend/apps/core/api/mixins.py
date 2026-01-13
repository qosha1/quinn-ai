"""
Common ViewSet mixins for API views.
"""

from rest_framework import status
from rest_framework.decorators import action
from rest_framework.response import Response


class TimestampFilterMixin:
    """
    Mixin to add timestamp filtering to ViewSets.

    Adds support for filtering by created_at and updated_at fields.
    """

    def get_queryset(self):
        """Filter queryset by timestamp parameters."""
        queryset = super().get_queryset()

        created_after = self.request.query_params.get("created_after")
        created_before = self.request.query_params.get("created_before")
        updated_after = self.request.query_params.get("updated_after")
        updated_before = self.request.query_params.get("updated_before")

        if created_after:
            queryset = queryset.filter(created_at__gte=created_after)
        if created_before:
            queryset = queryset.filter(created_at__lte=created_before)
        if updated_after:
            queryset = queryset.filter(updated_at__gte=updated_after)
        if updated_before:
            queryset = queryset.filter(updated_at__lte=updated_before)

        return queryset


class BulkActionMixin:
    """
    Mixin to add bulk operations to ViewSets.

    Provides bulk delete and bulk update actions.
    """

    @action(detail=False, methods=["post"])
    def bulk_delete(self, request):
        """
        Bulk delete objects by IDs.

        Expects: {"ids": ["uuid1", "uuid2", ...]}
        """
        ids = request.data.get("ids", [])
        if not ids:
            return Response(
                {"error": "No IDs provided"},
                status=status.HTTP_400_BAD_REQUEST
            )

        queryset = self.get_queryset().filter(id__in=ids)
        count = queryset.count()
        queryset.delete()

        return Response(
            {"deleted": count},
            status=status.HTTP_200_OK
        )


class SoftDeleteMixin:
    """
    Mixin to add soft delete functionality.

    Requires model to have 'is_deleted' and 'deleted_at' fields.
    """

    def perform_destroy(self, instance):
        """Soft delete instead of hard delete."""
        from django.utils import timezone
        instance.is_deleted = True
        instance.deleted_at = timezone.now()
        instance.save(update_fields=["is_deleted", "deleted_at"])

    def get_queryset(self):
        """Exclude soft-deleted items by default."""
        queryset = super().get_queryset()
        if not self.request.query_params.get("include_deleted"):
            queryset = queryset.filter(is_deleted=False)
        return queryset
