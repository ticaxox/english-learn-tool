import logging
import re
from time import perf_counter
from uuid import uuid4

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

from app.core.errors import error_response
from app.core.request_context import reset_request_id, set_request_id

logger = logging.getLogger(__name__)
_REQUEST_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")


class RequestIDMiddleware(BaseHTTPMiddleware):
    """Attach a validated or generated request ID and emit one structured access log."""

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        incoming = request.headers.get("X-Request-ID")
        request_id = (
            incoming if incoming and _REQUEST_ID_PATTERN.fullmatch(incoming) else uuid4().hex
        )
        request.state.request_id = request_id
        token = set_request_id(request_id)
        started = perf_counter()
        try:
            try:
                response = await call_next(request)
            except Exception:
                logger.exception(
                    "request.failed",
                    extra={
                        "method": request.method,
                        "path": request.url.path,
                        "duration_ms": round((perf_counter() - started) * 1000, 2),
                    },
                )
                response = error_response(
                    status_code=500,
                    code="INTERNAL_SERVER_ERROR",
                    message="An unexpected internal error occurred.",
                    details=None,
                    request_id=request_id,
                )
            response.headers["X-Request-ID"] = request_id
            logger.info(
                "request.completed",
                extra={
                    "method": request.method,
                    "path": request.url.path,
                    "status_code": response.status_code,
                    "duration_ms": round((perf_counter() - started) * 1000, 2),
                },
            )
            return response
        finally:
            reset_request_id(token)
