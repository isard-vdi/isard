#
#   Copyright © 2026 IsardVDI
#
# SPDX-License-Identifier: AGPL-3.0-or-later

"""``end_creating_desktops`` must report what actually happened.

The bulk-spawn loop ``new_from_templateTh`` tolerates a single desktop failing
and carries on, but on origin/main it ended by emitting ``end_creating_desktops``
with only ``{"deployment_id": ...}`` — so a deployment that created zero desktops
looked identical to one that created them all, and the user got no message.

This pins the enriched payload: ``created`` / ``failed`` counts and a
``failures`` list carrying each failed desktop's name and ``description_code``.
"""
import time

import pytest
from isardvdi_common.helpers.error_factory import Error
from isardvdi_common.lib.domains.desktops import desktops as mod

DP = mod.DesktopsProcessed


@pytest.fixture
def captured(monkeypatch):
    calls = []
    monkeypatch.setattr(
        mod,
        "send_socket_user",
        lambda event, payload, recipients: calls.append((event, payload, recipients)),
    )

    def fake_new_from_template(cls, name, description, template_id, user_id, *a, **k):
        if "bad" in name:
            raise Error(
                "precondition_required",
                f"Template {template_id} is not ready",
                description_code="template_not_ready",
            )
        return {"id": "d-" + name, "tag": "tag", "create_dict": {}}

    monkeypatch.setattr(DP, "new_from_template", classmethod(fake_new_from_template))
    monkeypatch.setattr(
        mod.Helpers, "set_current_booking", staticmethod(lambda *a, **k: None)
    )
    return calls


def _desktop(name):
    return {
        "name": name,
        "description": "d",
        "template_id": "t-1",
        "user_id": "u-1",
        "domain_id": "dom-" + name,
        "deployment_tag_dict": {},
        "new_data": {},
        "image": None,
    }


def _wait_for_end(calls, secs=8):
    deadline = time.time() + secs
    while time.time() < deadline:
        for event, payload, _ in calls:
            if event == "end_creating_desktops":
                return payload
        time.sleep(0.1)
    return None


def test_end_payload_reports_created_and_failed(captured):
    deployment = {"id": "dep-1", "user": "u-1", "co_owners": []}
    desktops = [_desktop("ok one"), _desktop("bad two"), _desktop("ok three")]
    DP.new_from_templateTh(desktops, deployment)

    payload = _wait_for_end(captured)
    assert payload is not None, "end_creating_desktops was never emitted"
    assert payload["deployment_id"] == "dep-1"
    assert payload["created"] == 2
    assert payload["failed"] == 1
    codes = [f["description_code"] for f in payload["failures"]]
    assert codes == ["template_not_ready"]
    assert payload["failures"][0]["name"] == "bad two"


def test_end_payload_all_ok_has_no_failures(captured):
    deployment = {"id": "dep-2", "user": "u-1", "co_owners": []}
    DP.new_from_templateTh([_desktop("ok a"), _desktop("ok b")], deployment)

    payload = _wait_for_end(captured)
    assert payload is not None
    assert payload["created"] == 2
    assert payload["failed"] == 0
    assert payload["failures"] == []
