# coding=utf-8
# Copyright 2017 the Isard-vdi project authors:
#      Josep Maria Viñolas Auquer
#      Alberto Larraz Dalmases
# License: AGPLv3

import datetime
import logging
import os
from importlib.util import find_spec

from pythonjsonlogger.json import JsonFormatter


class RequestFormatter(JsonFormatter):
    def __init__(self, *args, **kwargs):
        service = None
        api_spec = find_spec("api")
        if api_spec:
            if api_spec.origin == "/api/api/__init__.py":
                service = "api"
            elif api_spec.origin == "/app/api/__init__.py":
                service = "apiv4"
        else:
            for module in ["webapp", "scheduler", "notifier"]:
                if find_spec(module):
                    service = module
                    break
        if service:
            kwargs.setdefault("static_fields", {}).setdefault("service", service)
        return super().__init__(*args, **kwargs)

    def format(self, record):
        record.levelname = record.levelname.lower()

        return super().format(record)

    @staticmethod
    def formatTime(record, datefmt=None):
        # Format record.created as RFC3339
        return (
            datetime.datetime.fromtimestamp(record.created)
            .replace(microsecond=0)
            .astimezone()
            .isoformat()
        )


# Get log level
LOG_LEVEL = os.environ.get("LOG_LEVEL", "INFO")
# getLevelName only knows UPPERCASE names, and for anything else it does not
# fail: it returns the string "Level <whatever>", which setLevel then rejects
# with ValueError. That happens at import, so a LOG_LEVEL of "info" does not
# mis-set the level -- it takes down every process that imports this module.
LOG_LEVEL_NUM = logging.getLevelName(LOG_LEVEL.strip().upper())
if not isinstance(LOG_LEVEL_NUM, int):
    print(f"LOG_LEVEL={LOG_LEVEL!r} is not a log level; falling back to INFO")
    LOG_LEVEL_NUM = logging.INFO

# Configure log formatter
formatter = RequestFormatter(
    "%(levelname)s %(service)s %(message)s %(asctime)s",
    rename_fields={
        "message": "msg",
        "levelname": "level",
        "asctime": "time",
    },
)

# Configure global logger
logger = logging.getLogger()
handler = logging.StreamHandler()
handler.setFormatter(formatter)
logger.addHandler(handler)
logger.setLevel(LOG_LEVEL_NUM)
