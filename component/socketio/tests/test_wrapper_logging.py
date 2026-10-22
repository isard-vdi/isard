import asyncio
import importlib
import json
import logging

import pytest
from pythonjsonlogger.json import JsonFormatter

APP = "isardvdi_socketio"
SOCKETIO = "socketio.server"
ENGINEIO = "engineio.server"


def _library_enabled(kwargs, kwarg, name):
    value = kwargs.get(kwarg)
    if value is True:
        return True
    if isinstance(value, logging.Logger):
        assert value is logging.getLogger(name)
        return value.isEnabledFor(logging.INFO)
    return False


def _enabled(kwargs):
    return {
        "app": logging.getLogger(APP).level == logging.DEBUG,
        "socketio": _library_enabled(kwargs, "logger", SOCKETIO),
        "engineio": _library_enabled(kwargs, "engineio_logger", ENGINEIO),
    }


def test_socketio_debug_unset_enables_nothing(wrapper_loader):
    kwargs = wrapper_loader(log_level="INFO")
    assert _enabled(kwargs) == {"app": False, "socketio": False, "engineio": False}


def test_socketio_debug_app_enables_only_the_service(wrapper_loader):
    kwargs = wrapper_loader(log_level="INFO", socketio_debug="app")
    assert _enabled(kwargs) == {"app": True, "socketio": False, "engineio": False}


def test_socketio_debug_socketio_leaves_engineio_off(wrapper_loader):
    kwargs = wrapper_loader(log_level="INFO", socketio_debug="socketio")
    assert _enabled(kwargs) == {"app": True, "socketio": True, "engineio": False}
    assert logging.getLogger(SOCKETIO).level == logging.DEBUG


def test_socketio_debug_all_enables_engineio(wrapper_loader):
    kwargs = wrapper_loader(log_level="INFO", socketio_debug=" ALL ")
    assert _enabled(kwargs) == {"app": True, "socketio": True, "engineio": True}
    assert logging.getLogger(ENGINEIO).level == logging.DEBUG


def test_log_level_debug_alone_enables_no_library_logger(wrapper_loader):
    kwargs = wrapper_loader(log_level="DEBUG")
    assert _enabled(kwargs)["socketio"] is False
    assert _enabled(kwargs)["engineio"] is False


def test_unknown_socketio_debug_value_is_off(wrapper_loader):
    kwargs = wrapper_loader(log_level="INFO", socketio_debug="packets")
    assert _enabled(kwargs) == {"app": False, "socketio": False, "engineio": False}


@pytest.fixture
def module_with_debug(monkeypatch, pristine_module):
    def _load(mode):
        monkeypatch.setenv("SOCKETIO_DEBUG", mode)
        return importlib.reload(pristine_module)

    return _load


def test_library_loggers_have_no_plain_text_handler(module_with_debug):
    module = module_with_debug("all")
    server = module.socketio_server
    assert server.logger is logging.getLogger(SOCKETIO)
    assert server.eio.logger is logging.getLogger(ENGINEIO)
    assert server.logger.handlers == []
    assert server.eio.logger.handlers == []


def test_unhandled_event_is_logged_as_json(module_with_debug, caplog):
    module = module_with_debug("app")
    json_handlers = [
        h
        for h in logging.getLogger().handlers
        if isinstance(h.formatter, JsonFormatter)
    ]
    assert json_handlers

    asyncio.run(
        module.socketio_server._trigger_event("no-such-event", "/userspace", "sid-9")
    )

    records = [r for r in caplog.records if r.name == APP]
    assert [r.levelno for r in records] == [logging.DEBUG]
    line = json.loads(json_handlers[0].format(records[0]))
    assert line["level"] == "debug"
    assert "no-such-event" in line["msg"]
