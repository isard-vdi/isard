# Copyright 2017 the Isard-vdi project authors:
#      Alberto Larraz Dalmases
#      Josep Maria Viñolas Auquer
# License: AGPLv3
# coding=utf-8

# import coloredlogs
import logging as log

from engine.config import CONFIG_DICT
LOG_DIR = 'logs'
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

class Logs (object):
    def __init__(self):
        self.names_for_loggers = ['threads',
                             'workers',
                             'status',
                             'changes',
                             'downloads',
                             'main']
        for n in self.names_for_loggers:
            self.create_logger(n)

    def create_logger(self, name):
        logger_obj = log.getLogger(name)
        logger_handler = log.FileHandler(LOG_DIR + '/' + name + '.log')
        logger_handler.setLevel(log.DEBUG)
        logger_formatter = log.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(threadName)s - %(message)s')
        logger_handler.setFormatter(logger_formatter)
        logger_obj.addHandler(logger_handler)
        setattr(self, name, logger_obj)

eval_log = log.getLogger('eval')
eval_handler = log.FileHandler(LOG_DIR + '/' + 'eval.log')
eval_handler.setLevel(log.DEBUG)
eval_formatter = log.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(threadName)s - %(message)s')
eval_handler.setFormatter(eval_formatter)
eval_log.addHandler(eval_handler)

logs = Logs()

# threads_log = log.getLogger('threads')
# threads_handler = log.FileHandler(LOG_DIR + '/' + 'threads.log')
# threads_handler.setLevel(log.DEBUG)
# threads_formatter = log.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(threadName)s - %(message)s')
# threads_handler.setFormatter(threads_formatter)
# threads_log.addHandler(threads_handler)
#
# workers_log = log.getLogger('workers')
# workers_handler = log.FileHandler(LOG_DIR + '/' + 'workers.log')
# workers_handler.setLevel(log.DEBUG)
# workers_formatter = log.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(threadName)s - %(message)s')
# workers_handler.setFormatter(workers_formatter)
# workers_log.addHandler(workers_handler)
#
# status_log = log.getLogger('status')
# status_handler = log.FileHandler(LOG_DIR + '/' + 'status.log')
# status_handler.setLevel(log.DEBUG)
# status_formatter = log.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(threadName)s - %(message)s')
# status_handler.setFormatter(status_formatter)
# status_log.addHandler(status_handler)
