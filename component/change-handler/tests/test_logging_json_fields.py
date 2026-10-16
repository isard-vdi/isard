# SPDX-License-Identifier: AGPL-3.0-or-later

"""The change-handler logs JSON lines that keep a record's ``extra`` fields."""

import json
import logging

from isardvdi_change_handler import __main__ as change_handler_main


def test_extra_fields_reach_the_log_line(monkeypatch):
    monkeypatch.delenv("DEBUG_WEBSOCKETS", raising=False)
    root = logging.getLogger()
    saved_level, saved_handlers = root.level, list(root.handlers)
    try:
        change_handler_main._configure_logging()
        record = root.makeRecord(
            "rdb",
            logging.WARNING,
            __file__,
            1,
            "rdb_query_slow",
            (),
            None,
            extra={"query": "get_all", "duration_ms": 1234},
        )
        lines = [handler.format(record) for handler in root.handlers]
    finally:
        root.setLevel(saved_level)
        root.handlers[:] = saved_handlers

    parsed = []
    for line in lines:
        try:
            parsed.append(json.loads(line))
        except ValueError:
            pass
    assert any(
        doc.get("msg") == "rdb_query_slow"
        and doc.get("query") == "get_all"
        and doc.get("duration_ms") == 1234
        for doc in parsed
    ), lines
