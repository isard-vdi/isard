#
#   Copyright © 2026 IsardVDI
#
# SPDX-License-Identifier: AGPL-3.0-or-later

"""The bulk create loop skips a per-desktop ``Error`` but never swallows a real defect, and always closes the modal."""

import asyncio

import pytest
from isardvdi_common.helpers.error_factory import Error
from isardvdi_common.lib.domains.desktops import desktops as mod

DP = mod.DesktopsProcessed


def _desktop(n):
    return {
        "name": f"d{n}",
        "description": "",
        "template_id": "tmpl-1",
        "user_id": f"u-{n}",
        "domain_id": f"dom-{n}",
        "deployment_tag_dict": {"tag": "dep-1"},
        "new_data": None,
        "image": None,
    }


def _install_loop(monkeypatch, fail_on):
    calls = {"created": [], "events": []}

    def new_from_template(cls, name, *args, **kwargs):
        exc = fail_on.get(name)
        if exc is not None:
            raise exc
        calls["created"].append(name)
        return None

    monkeypatch.setattr(DP, "new_from_template", classmethod(new_from_template))
    monkeypatch.setattr(
        mod, "send_socket_user", lambda kind, data, users: calls["events"].append(kind)
    )
    monkeypatch.setattr(mod.asyncio, "sleep", _no_sleep)
    monkeypatch.setattr(mod.asyncio, "to_thread", _inline_to_thread)
    return calls


@pytest.fixture
def harness(monkeypatch):
    return _install_loop(
        monkeypatch,
        {
            "d1": Error(
                "precondition_required",
                "Template disk is not ready",
                description_code="template_storage_not_ready",
            )
        },
    )


@pytest.fixture
def harness_defect(monkeypatch):
    return _install_loop(
        monkeypatch, {"d1": RuntimeError("a real defect, not a per-desktop Error")}
    )


_real_sleep = asyncio.sleep


async def _no_sleep(_seconds):
    # keep the throttle's yield to the loop, drop its 0.25 s
    await _real_sleep(0)


async def _inline_to_thread(func, *args, **kwargs):
    # run the offload inline so the loop's error handling is deterministic
    return func(*args, **kwargs)


@pytest.mark.asyncio
async def test_one_unbuildable_desktop_does_not_stop_the_rest(harness):
    DP.new_from_templateTh(
        [_desktop(0), _desktop(1), _desktop(2)],
        {"id": "dep-1", "user": "owner", "co_owners": []},
    )
    # the coroutine runs as a task on this loop; give it the turns it needs
    for _ in range(20):
        await _real_sleep(0)
    assert harness["created"] == ["d0", "d2"]
    assert harness["events"] == ["creating_desktops", "end_creating_desktops"]


@pytest.mark.asyncio
async def test_a_non_error_defect_is_not_swallowed(harness_defect):
    before = asyncio.all_tasks()
    DP.new_from_templateTh(
        [_desktop(0), _desktop(1), _desktop(2)],
        {"id": "dep-1", "user": "owner", "co_owners": []},
    )
    # new_from_templateTh fires-and-forgets; grab its task to see the defect.
    (task,) = asyncio.all_tasks() - before
    with pytest.raises(RuntimeError):
        await task
    assert harness_defect["created"] == ["d0"]
    assert harness_defect["events"] == ["creating_desktops", "end_creating_desktops"]
