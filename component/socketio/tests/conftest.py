import importlib
from unittest import mock

import pytest
import socketio

MODULE = "isardvdi_socketio"


def _reload_clean():
    return importlib.reload(importlib.import_module(MODULE))


@pytest.fixture
def wrapper_loader(monkeypatch):
    """Reload the socketio wrapper under a controlled environment while spying
    on the AsyncServer constructor, so a test can assert on the kwargs the
    wrapper builds without needing a real redis or ASGI stack.

    Returns loader(*, log_level=None, cors=None, socketio_debug=None) -> captured
    AsyncServer kwargs.
    """
    captured = {}

    def _spy_async_server(**kwargs):
        captured.clear()
        captured.update(kwargs)
        return mock.MagicMock(name="AsyncServer")

    def _loader(*, log_level=None, cors=None, socketio_debug=None):
        monkeypatch.setattr(socketio, "AsyncServer", _spy_async_server)
        monkeypatch.setattr(
            socketio, "AsyncRedisManager", lambda *args, **kwargs: mock.MagicMock()
        )
        monkeypatch.setattr(
            socketio, "ASGIApp", lambda *args, **kwargs: mock.MagicMock()
        )
        if log_level is None:
            monkeypatch.delenv("LOG_LEVEL", raising=False)
        else:
            monkeypatch.setenv("LOG_LEVEL", log_level)
        if cors is None:
            monkeypatch.delenv("CORS_ALLOWED_ORIGINS", raising=False)
        else:
            monkeypatch.setenv("CORS_ALLOWED_ORIGINS", cors)
        if socketio_debug is None:
            monkeypatch.delenv("SOCKETIO_DEBUG", raising=False)
        else:
            monkeypatch.setenv("SOCKETIO_DEBUG", socketio_debug)
        _reload_clean()
        return captured

    yield _loader
    monkeypatch.undo()
    _reload_clean()


@pytest.fixture
def pristine_module(monkeypatch):
    """The wrapper imported with real classes and a clean environment, for
    exercising the registered connect/disconnect/event handlers."""
    monkeypatch.delenv("LOG_LEVEL", raising=False)
    monkeypatch.delenv("CORS_ALLOWED_ORIGINS", raising=False)
    monkeypatch.delenv("SOCKETIO_DEBUG", raising=False)
    module = _reload_clean()
    yield module
    monkeypatch.undo()
    _reload_clean()
