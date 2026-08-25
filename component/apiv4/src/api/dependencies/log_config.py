import contextvars
import logging

import isardvdi_common.helpers.log  # noqa: F401

UVICORN_LOGGERS = ("uvicorn", "uvicorn.error", "uvicorn.access", "uvicorn.asgi")
IDENTITY_FIELDS = ("user_id", "role_id", "category_id", "group_id")

_request_identity: contextvars.ContextVar = contextvars.ContextVar(
    "apiv4_request_identity", default=None
)


def set_request_identity(payload):
    _request_identity.set(payload)


def _identity():
    payload = _request_identity.get()
    if not isinstance(payload, dict):
        return None
    return {field: payload[field] for field in IDENTITY_FIELDS if payload.get(field)}


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
        record.status = int(status_code)
        record.request = {
            "method": method,
            "url": path,
            "http_version": http_version,
            "client_addr": client_addr,
        }
        record.msg = "%s %s %s"
        record.args = (method, path, status_code)

        if logging.getLogger().isEnabledFor(logging.DEBUG):
            user = _identity()
            if user:
                record.user = user
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
