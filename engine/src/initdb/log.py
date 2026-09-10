# Copyright 2017 the Isard-vdi project authors:
#      Josep Maria Viñolas Auquer
#      Alberto Larraz Dalmases
# License: AGPLv3

#!/usr/bin/env python
# coding=utf-8

import configparser
import logging as log
import os

from .lib import loadConfig

try:
    LOG_LEVEL = loadConfig().cfg["LOG_LEVEL"]
except Exception as e:
    LOG_LEVEL = "INFO"

# LOG FORMATS
LOG_FORMAT = "%(asctime)s %(msecs)d - %(levelname)s - %(threadName)s: %(message)s"
LOG_DATE_FORMAT = "%Y/%m/%d %H:%M:%S"
# getLevelName returns the string "Level <x>" for an unknown name, and
# basicConfig then raises ValueError at import. Normalise and fall back.
LOG_LEVEL_NUM = log.getLevelName(str(LOG_LEVEL).strip().upper())
if not isinstance(LOG_LEVEL_NUM, int):
    print(f"LOG_LEVEL={LOG_LEVEL!r} is not a log level; falling back to INFO")
    LOG_LEVEL_NUM = log.INFO
log.basicConfig(format=LOG_FORMAT, datefmt=LOG_DATE_FORMAT, level=LOG_LEVEL_NUM)
