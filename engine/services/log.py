# Copyright 2017 the Isard-vdi project authors:
#      Alberto Larraz Dalmases
#      Josep Maria Viñolas Auquer
# License: AGPLv3
# coding=utf-8

# import coloredlogs
import logging as log

from engine.config import CONFIG_DICT

LOG_LEVEL = CONFIG_DICT["LOG"]["log_level"]
LOG_FILE = CONFIG_DICT["LOG"]["log_file"]
# LOG FORMATS

# log_format='%(levelname)s:%(message)s'
LOG_FORMAT = '%(asctime)s %(msecs)d - %(levelname)s - %(threadName)s: %(message)s'
LOG_DATE_FORMAT = '%Y/%m/%d %H:%M:%S'

LOG_LEVEL_NUM = log.getLevelName(LOG_LEVEL)
# logger = log.getLogger(CONFIG_DICT["LOG"]["log_name"])
# logger = log.getLogger()
# logger.setLevel(LOG_LEVEL_NUM)
# log.Formatter(fmt=LOG_FORMAT,datefmt=LOG_DATE_FORMAT)

# log.basicConfig(format=LOG_FORMAT, datefmt=LOG_DATE_FORMAT,level=LOG_LEVEL_NUM)
log.basicConfig(filename=LOG_FILE,
                format=LOG_FORMAT,
                datefmt=LOG_DATE_FORMAT,
                level=LOG_LEVEL_NUM)

logFormatter = log.Formatter(fmt=LOG_FORMAT, datefmt=LOG_DATE_FORMAT)
rootLogger = log.getLogger()

# fileHandler = logging.FileHandler("{0}/{1}.log".format(logPath, fileName))
# fileHandler.setFormatter(logFormatter)
# rootLogger.addHandler(fileHandler)

consoleHandler = log.StreamHandler()
consoleHandler.setLevel(log.ERROR)
consoleHandler.setFormatter(logFormatter)
rootLogger.addHandler(consoleHandler)

# coloredlogs.install(format=LOG_FORMAT,datefmt=LOG_DATE_FORMAT,level=LOG_LEVEL_NUM)


# LOGS TO FILE
# log.basicConfig(filename=LOG_FILE, level=level_num, format=log_format, datefmt=log_datefmt)

# LOGS TO SCREEN (useful for development)
# log.basicConfig(level=LOG_LEVEL_NUM, format=LOG_FORMAT, datefmt=LOG_DATE_FORMAT)

# Eval Logger
# create file handler which logs even debug messages
eval_log = log.getLogger('eval')
eval_handler = log.FileHandler('eval.log')
eval_handler.setLevel(log.DEBUG)
eval_formatter = log.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
eval_handler.setFormatter(eval_formatter)
eval_log.addHandler(eval_handler)