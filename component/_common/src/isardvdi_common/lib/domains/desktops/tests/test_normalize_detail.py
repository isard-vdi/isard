#
#   IsardVDI - Open Source KVM Virtual Desktops based on KVM Linux and dockers
#   Copyright (C) 2026 IsardVDI
#
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Unit coverage for DesktopsProcessed._normalize_detail.

The engine writes ``domains.detail`` inconsistently (``update_domain_status``
json-dumps it, other paths store it raw); ``_normalize_detail`` must return a
clean human string either way so the user sees the real Failed reason.
"""

import json

from isardvdi_common.lib.domains.desktops.desktops import DesktopsProcessed

f = DesktopsProcessed._normalize_detail


def test_empty_and_none_return_none():
    assert f(None) is None
    assert f("") is None


def test_plain_string_is_passed_through():
    assert f("Failed by engine as it was incomplete") == (
        "Failed by engine as it was incomplete"
    )


def test_json_dumped_string_is_decoded():
    # update_domain_status stores json.dumps(detail) — a quoted JSON string.
    raw = json.dumps("desktop not started: no hypervisors online in pool default")
    assert f(raw) == "desktop not started: no hypervisors online in pool default"


def test_json_dumped_dict_prefers_detail_then_msg():
    assert f(json.dumps({"detail": "no GPU capacity", "msg": "x"})) == "no GPU capacity"
    assert f(json.dumps({"msg": "queued"})) == "queued"


def test_json_dumped_dict_without_known_keys_falls_back_to_raw():
    raw = json.dumps({"other": 1})
    assert f(raw) == raw


def test_numeric_looking_plain_string_stays_raw():
    # json.loads("123") -> int, not str/dict -> keep the original string.
    assert f("123") == "123"
