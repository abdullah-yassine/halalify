import logging

from rest_framework.response import Response
from rest_framework.views import exception_handler

logger = logging.getLogger(__name__)


def handle_exception(exc, context):
    """
    DRF exception handler that ensures internal details never reach the client.

    DRF's default handler already converts known DRF exceptions (ValidationError,
    NotAuthenticated, etc.) to Response objects. This wrapper intercepts anything
    that falls through — unhandled Python exceptions, Django ORM errors, etc. —
    and returns a generic 500 instead of leaking stack traces or DB error messages.

    Logs the exception TYPE (not the full traceback with local variables) so that
    auth tokens and SQL queries in local variables are never written to logs.
    """
    response = exception_handler(exc, context)

    if response is None:
        view = context.get("view", None)
        logger.error(
            "Unhandled exception in %s.%s: %s",
            type(view).__module__ if view else "unknown",
            type(view).__name__ if view else "view",
            type(exc).__name__,
        )
        return Response({"error": "An unexpected error occurred."}, status=500)

    return response
