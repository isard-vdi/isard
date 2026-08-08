"""A LOG_LEVEL that is not UPPERCASE must not take the process down.

``logging.getLevelName`` only knows uppercase names. For anything else it does
not raise: it returns the string ``"Level <whatever>"``, and ``setLevel`` then
rejects that with ``ValueError`` -- at import time, so the whole process dies
rather than logging at the wrong level. Seen live on two pXXX hypervisors whose
cfg said ``LOG_LEVEL="info"``: every RQ job on those nodes failed at
``import isardvdi_task.task``, and because the crash was inside the error
helper, the rows were left ``Failed`` with no reason recorded anywhere.
"""

import importlib
import logging

import pytest

MODULE = "isardvdi_common.helpers.log"


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("INFO", logging.INFO),
        ("info", logging.INFO),
        ("  Debug  ", logging.DEBUG),
        ("warning", logging.WARNING),
    ],
)
def test_a_log_level_is_read_whatever_its_case(monkeypatch, value, expected):
    monkeypatch.setenv("LOG_LEVEL", value)
    mod = importlib.reload(importlib.import_module(MODULE))
    assert mod.LOG_LEVEL_NUM == expected


def test_an_unknown_log_level_falls_back_instead_of_raising(monkeypatch):
    monkeypatch.setenv("LOG_LEVEL", "chatty")
    mod = importlib.reload(importlib.import_module(MODULE))
    assert mod.LOG_LEVEL_NUM == logging.INFO
