# coding=utf-8
# Copyright 2017 the Isard-vdi project authors:
#      Josep Maria Viñolas Auquer
#      Alberto Larraz Dalmases
# License: AGPLv3

import logging as log
import os

from scheduler import app


class StructuredMessage(object):
    def __init__(self, message):
        self.message = message

    def __str__(self):
        if isinstance(self.message, str):
            return "%s" % (self.message)

        message = "%s - %s" % (
            self.message["msg"],
            self.message["description"],
        )
        if LOG_LEVEL in ["INFO", "WARNING"]:
            return message
        if LOG_LEVEL == "ERROR":
            return "%s - %s - %s" % (
                message,
                self.message["function_call"],
                self.message["function"],
            )
        if LOG_LEVEL == "DEBUG":
            return "%s - %s - %s\r\n%s\r\n%s" % (
                message,
                self.message["function"],
                self.message["function_call"],
                self.message["debug"],
                self.message["request"],
                self.message["data"],
            )


app.sm = StructuredMessage

LOG_LEVEL = os.environ.get("LOG_LEVEL", "INFO")
LOG_LEVEL_NUM = log.getLevelName(LOG_LEVEL)
log.basicConfig(
    level=LOG_LEVEL_NUM, format="%(asctime)s - %(levelname)-8s - %(message)s"
)
