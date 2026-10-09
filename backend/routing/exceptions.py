"""API error types and a handler that gives every failure the same JSON shape."""
from __future__ import annotations

import logging

from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import exception_handler as drf_exception_handler

logger = logging.getLogger(__name__)


class UpstreamError(Exception):
    """A third-party provider failed, timed out, or returned something unusable."""

    def __init__(self, provider: str, detail: str, *, status_code: int = status.HTTP_502_BAD_GATEWAY):
        self.provider = provider
        self.detail = detail
        self.status_code = status_code
        super().__init__(f"{provider}: {detail}")


class NoRouteFound(UpstreamError):
    def __init__(self, detail: str = "No drivable route connects those two places."):
        super().__init__("osrm", detail, status_code=status.HTTP_422_UNPROCESSABLE_ENTITY)


class RateLimited(UpstreamError):
    """The provider's free tier is exhausted for now."""

    def __init__(self, provider: str, retry_after: str | None = None):
        wait = f" Try again in about {retry_after} seconds." if retry_after else " Try again shortly."
        super().__init__(
            provider,
            f"The free {provider} tier is rate-limited right now.{wait}",
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
        )


class GeocodingError(UpstreamError):
    def __init__(self, detail: str):
        super().__init__("nominatim", detail, status_code=status.HTTP_422_UNPROCESSABLE_ENTITY)


def api_exception_handler(exc, context):
    if isinstance(exc, UpstreamError):
        logger.warning("Upstream failure from %s: %s", exc.provider, exc.detail)
        return Response(
            {"error": {"type": "upstream_error", "provider": exc.provider, "detail": exc.detail}},
            status=exc.status_code,
        )

    response = drf_exception_handler(exc, context)
    if response is not None and not isinstance(response.data, dict):
        response.data = {"error": {"type": "error", "detail": response.data}}
    elif response is not None and "error" not in response.data:
        response.data = {"error": {"type": "validation_error", "fields": response.data}}
    return response
