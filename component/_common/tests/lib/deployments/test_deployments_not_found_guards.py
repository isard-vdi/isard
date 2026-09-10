#
#   Copyright © 2026 IsardVDI
#
# SPDX-License-Identifier: AGPL-3.0-or-later

"""not-found guards across ``DeploymentsProcessed`` entry points.

Every public operation that takes a ``deployment_id`` first resolves the
row and rejects a missing one before doing anything else. A guard that
stops firing here lets an operation run against a non-existent (or
just-deleted) deployment. Pinned on ``get_deployment``,
``get_deployment_info``, ``edit_deployment_data``,
``remove_desktops_from_deployment`` and ``add_desktops_to_deployment``.

Each function runs unmocked; only ``Caches.get_document`` is stubbed.
"""

import pytest
from isardvdi_common.helpers.error_factory import Error
from isardvdi_common.lib.deployments import deployments as mod

DP = mod.DeploymentsProcessed


def _missing(monkeypatch):
    monkeypatch.setattr(
        mod.Caches, "get_document", classmethod(lambda cls, *a, **k: None)
    )


class TestDeploymentNotFoundGuards:
    def test_get_deployment_missing(self, monkeypatch):
        _missing(monkeypatch)
        with pytest.raises(Error) as exc:
            DP.get_deployment("nope")
        assert exc.value.error["error"] == "not_found"
        assert exc.value.error["description_code"] == "not_found"

    def test_edit_deployment_data_missing(self, monkeypatch):
        _missing(monkeypatch)
        with pytest.raises(Error) as exc:
            DP.edit_deployment_data({"user_id": "u-1"}, "nope", {"name": "x"})
        assert exc.value.error["error"] == "not_found"

    def test_remove_desktops_missing(self, monkeypatch):
        # Empty delete list so the deployment guard is the sole not-found
        # source (a non-empty list would also trip validate_tag downstream).
        _missing(monkeypatch)
        with pytest.raises(Error) as exc:
            DP.remove_desktops_from_deployment({"user_id": "u-1"}, "nope", [])
        assert exc.value.error["error"] == "not_found"

    def test_add_desktops_missing(self, monkeypatch):
        _missing(monkeypatch)
        with pytest.raises(Error) as exc:
            DP.add_desktops_to_deployment({"user_id": "u-1"}, "nope", [{}])
        assert exc.value.error["error"] == "not_found"

    def test_get_deployment_info_wrong_kind(self, monkeypatch):
        # get_deployment_info rejects a row that is not a desktops-deployment.
        # First lookup ([create_dict]) must stay subscriptable, second returns
        # the row whose ``kind`` is checked.
        monkeypatch.setattr(
            mod.Caches,
            "get_document",
            classmethod(
                lambda cls, table, did, keys=None: (
                    [{"name": "r"}] if keys else {"kind": "desktop"}
                )
            ),
        )
        with pytest.raises(Error) as exc:
            DP.get_deployment_info("dep-1")
        assert exc.value.error["error"] == "not_found"
        assert exc.value.error["description_code"] == "not_found"
