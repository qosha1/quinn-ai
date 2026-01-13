"""
Core API views including health check endpoint.
"""

import logging
from django.conf import settings
from django.db import connection
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from redis import Redis
from celery import Celery

logger = logging.getLogger(__name__)


@api_view(["GET"])
@permission_classes([AllowAny])
def health_check(request):
    """
    Health check endpoint that verifies system dependencies.

    Returns 200 if all services are healthy, 503 if any service is down.

    Checks:
    - Database connectivity
    - Redis connectivity
    - Celery worker availability

    GET /api/v1/health/
    """
    health_status = {
        "status": "healthy",
        "database": "unknown",
        "redis": "unknown",
        "celery": "unknown",
    }
    http_status = status.HTTP_200_OK

    # Check database
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            cursor.fetchone()
        health_status["database"] = "healthy"
    except Exception as e:
        logger.error(f"Database health check failed: {e}")
        health_status["database"] = "unhealthy"
        health_status["status"] = "unhealthy"
        http_status = status.HTTP_503_SERVICE_UNAVAILABLE

    # Check Redis
    try:
        redis_client = Redis.from_url(settings.REDIS_URL)
        redis_client.ping()
        health_status["redis"] = "healthy"
    except Exception as e:
        logger.error(f"Redis health check failed: {e}")
        health_status["redis"] = "unhealthy"
        health_status["status"] = "unhealthy"
        http_status = status.HTTP_503_SERVICE_UNAVAILABLE

    # Check Celery
    try:
        from config.celery_app import app as celery_app
        inspector = celery_app.control.inspect()
        active_workers = inspector.active()

        if active_workers:
            health_status["celery"] = "healthy"
        else:
            health_status["celery"] = "no_workers"
            health_status["status"] = "degraded"
            # Don't set 503 for missing workers, just degraded
    except Exception as e:
        logger.error(f"Celery health check failed: {e}")
        health_status["celery"] = "unhealthy"
        health_status["status"] = "degraded"

    return Response(health_status, status=http_status)
