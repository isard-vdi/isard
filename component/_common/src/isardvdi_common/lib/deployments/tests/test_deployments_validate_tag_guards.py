#
#   Copyright © 2026 IsardVDI
#
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Guards on ``DeploymentsProcessed.validate_tag_desktop_id_for_deployment``.

Confirms a ``tag_desktop_id`` really belongs to a deployment before it is
used to target desktops. Pinned:

* unknown deployment (L1410) not_found;
* a tag_desktop_id not in the deployment's recipes (L1420)
  invalid_tag_desktop_id_for_deployment.

This method is ``@cached``: it memoizes the "valid" (returns None) result,
so the cache is cleared before every test and each test uses distinct ids —
otherwise a value left by one test could satisfy another without the guard
ever running.
"""

import pytest
from isardvdi_common.helpers.error_factory import Error
from isardvdi_common.lib.deployments import deployments as mod

DP = mod.DeploymentsProcessed


@pytest.fixture(autouse=True)
def clear_caches():
    """Clear any @cached memo on the module/class before and after each test."""

    def _clear():
        cache = getattr(mod, "_validate_tag_desktop_id_for_deployment_cache", None)
        if cache is not None:
            cache.clear()
        for value in vars(DP).values():
            inner = getattr(value, "__func__", value)
            cache = getattr(inner, "cache", None)
            if cache is not None:
                cache.clear()

    _clear()
    yield
    _clear()


def _use(monkeypatch, deployment):
    monkeypatch.setattr(
        mod.Caches, "get_document", classmethod(lambda cls, *a, **k: deployment)
    )


class TestValidateTagGuards:
    def test_deployment_not_found(self, monkeypatch):
        _use(monkeypatch, None)
        with pytest.raises(Error) as exc:
            DP.validate_tag_desktop_id_for_deployment("dep-missing", "tag-1")
        assert exc.value.error["error"] == "not_found"

    def test_tag_not_in_deployment(self, monkeypatch):
        _use(monkeypatch, {"create_dict": [{"tag_desktop_id": "tag-good"}]})
        with pytest.raises(Error) as exc:
            DP.validate_tag_desktop_id_for_deployment("dep-a", "tag-bad")
        assert (
            exc.value.error["description_code"]
            == "invalid_tag_desktop_id_for_deployment"
        )

    def test_valid_tag_passes(self, monkeypatch):
        _use(monkeypatch, {"create_dict": [{"tag_desktop_id": "tag-ok"}]})
        assert DP.validate_tag_desktop_id_for_deployment("dep-b", "tag-ok") is None
