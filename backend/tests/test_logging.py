import json
import logging

from app.core.logging import JsonFormatter
from app.core.request_context import reset_request_id, set_request_id


def test_json_log_formatter_includes_request_context_and_request_fields() -> None:
    record = logging.LogRecord(
        name="app.test",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="request.completed",
        args=(),
        exc_info=None,
    )
    record.method = "GET"
    record.path = "/health/live"
    record.status_code = 200
    token = set_request_id("log-request-1")
    try:
        payload = json.loads(JsonFormatter().format(record))
    finally:
        reset_request_id(token)

    assert payload["message"] == "request.completed"
    assert payload["request_id"] == "log-request-1"
    assert payload["method"] == "GET"
    assert payload["path"] == "/health/live"
    assert payload["status_code"] == 200
