# Copyright 2017 the Isard-vdi project authors:
#      Josep Maria Viñolas Auquer
#      Alberto Larraz Dalmases
# License: AGPLv3

#!/usr/bin/env python
# coding=utf-8

import logging as log
import configparser
import os
from webapp import app

try:
    LOG_LEVEL = app.config['LOG_LEVEL']
except Exception as e:
    LOG_LEVEL = 'INFO'
    
# LOG FORMATS
LOG_FORMAT='%(asctime)s %(msecs)d - %(levelname)s - %(threadName)s: %(message)s'
LOG_DATE_FORMAT='%Y/%m/%d %H:%M:%S'
LOG_LEVEL_NUM = log.getLevelName(LOG_LEVEL)
# ~ log.basicConfig(format=LOG_FORMAT,datefmt=LOG_DATE_FORMAT,level=LOG_LEVEL_NUM)

log.basicConfig(filename='logs/webapp.log',
                            filemode='a',
                            format=LOG_FORMAT,datefmt=LOG_DATE_FORMAT,level=LOG_LEVEL_NUM)
