import contextvars
import logging
import os
import time

import isardvdi_common.helpers.log  # noqa: F401
from isardvdi_common.helpers.redact import BODY_LIMIT, loggable_body

UVICORN_LOGGERS = ("uvicorn", "uvicorn.error", "uvicorn.access", "uvicorn.asgi")
IDENTITY_FIELDS = ("user_id", "role_id", "category_id", "group_id")

_request_identity: contextvars.ContextVar = contextvars.ContextVar(
    "apiv4_request_identity", default=None
)
_request_start: contextvars.ContextVar = contextvars.ContextVar(
    "apiv4_request_start", default=None
)
_request_body: contextvars.ContextVar = contextvars.ContextVar(
    "apiv4_request_body", default=None
)

BODY_CONTENT_TYPES = ("application/json",)
DEBUG_STATS_PATHS = ("/api/v4", "/api/v4/")


def _content_type(scope):
    for name, value in scope.get("headers") or ():
        if name == b"content-type":
            return value.decode("latin-1", "replace").lower()
    return ""


class RequestContextMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        _request_start.set(time.perf_counter())

        if not (
            logging.getLogger().isEnabledFor(logging.DEBUG)
            and _content_type(scope).startswith(BODY_CONTENT_TYPES)
        ):
            return await self.app(scope, receive, send)

        captured = {"data": bytearray(), "size": 0}
        _request_body.set(captured)

        async def capturing_receive():
            message = await receive()
            if message["type"] == "http.request":
                chunk = message.get("body", b"")
                captured["size"] += len(chunk)
                room = BODY_LIMIT - len(captured["data"])
                if room > 0:
                    captured["data"].extend(chunk[:room])
            return message

        await self.app(scope, capturing_receive, send)


def set_request_identity(payload):
    _request_identity.set(payload)


def _identity():
    payload = _request_identity.get()
    if not isinstance(payload, dict):
        return None
    return {field: payload[field] for field in IDENTITY_FIELDS if payload.get(field)}


def _body():
    captured = _request_body.get()
    if not captured or not captured["size"]:
        return None
    if captured["size"] > BODY_LIMIT:
        return {"truncated": True, "size": captured["size"]}
    return loggable_body(bytes(captured["data"]))


class UvicornRecordFilter(logging.Filter):
    def filter(self, record):
        record.logger = record.name
        record.__dict__.pop("color_message", None)

        if record.name != "uvicorn.access":
            return True

        try:
            client_addr, method, full_path, http_version, status_code = record.args
        except TypeError, ValueError:
            return True

        path = str(full_path).split("?", 1)[0]
        if (
            path in DEBUG_STATS_PATHS
            and os.environ.get("DEBUG_STATS", "").lower() != "true"
        ):
            return False

        record.status = int(status_code)
        record.request = {
            "method": method,
            "url": path,
            "http_version": http_version,
            "client_addr": client_addr,
        }
        record.msg = "%s %s %s"
        record.args = (method, path, status_code)

        start = _request_start.get()
        if start is not None:
            record.duration_ms = round((time.perf_counter() - start) * 1000, 1)

        user = _identity()
        if user:
            record.user = user

        if logging.getLogger().isEnabledFor(logging.DEBUG):
            body = _body()
            if body is not None:
                record.request["body"] = body
        return True


def configure_uvicorn_logging(loggers=UVICORN_LOGGERS):
    for name in loggers:
        uvicorn_logger = logging.getLogger(name)
        uvicorn_logger.handlers.clear()
        uvicorn_logger.propagate = True
        uvicorn_logger.setLevel(logging.NOTSET)
        if not any(
            isinstance(existing, UvicornRecordFilter)
            for existing in uvicorn_logger.filters
        ):
            uvicorn_logger.addFilter(UvicornRecordFilter())


configure_uvicorn_logging()
