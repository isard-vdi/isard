import os
import logging
from logging.handlers import RotatingFileHandler


class BaseConfig(object):
    DEBUG = False
    TESTING = False

    LOGGING_FORMAT = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    LOG_DATE_FORMAT = '%Y/%m/%d %H:%M:%S'
    LOGGING_LOCATION = 'base.log'
    LOGGING_LEVEL = logging.WARN


class DevelopmentConfig(BaseConfig):
    DEBUG = True
    TESTING = False
    LOGGING_LEVEL = logging.DEBUG
    LOGGING_LOCATION = 'development.log'


class TestingConfig(BaseConfig):
    DEBUG = False
    TESTING = True
    LOGGING_LEVEL = logging.INFO
    LOGGING_LOCATION = 'test.log'

config = {
    "development": "app.config.DevelopmentConfig",
    "testing": "app.config.TestingConfig",
    "default": "app.config.BaseConfig"
}


def configure_app(app):
    config_name = os.getenv('ISARD_CONFIGURATION', 'development')
    app.config.from_object(config[config_name])
    #app.config.from_pyfile('config.cfg', silent=True)
    
    # Configure logging
    handler = RotatingFileHandler(app.config['LOGGING_LOCATION'], maxBytes=10000, backupCount=1)
    handler.setLevel(app.config['LOGGING_LEVEL'])
    formatter = logging.Formatter(app.config['LOGGING_FORMAT'])
    handler.setFormatter(formatter)
    app.logger.addHandler(handler)
    app.template_folder=app.config["TEMPLATE_FOLDER"]


