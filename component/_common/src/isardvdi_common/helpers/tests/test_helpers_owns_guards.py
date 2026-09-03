#
#   Copyright © 2026 IsardVDI
#
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Ownership / access-rights guards in ``Helpers``.

These are the authorization walls: they answer "may this payload touch this
item?" and reject with a typed 403 (or 404 for a missing item) otherwise. A
guard that stops firing lets a user reach an item that is not theirs, so the
allow paths *and* the reject codes are pinned.

Covered: ``owns_booking_id``, ``owns_domain_id``, ``owns_media_id``,
``owns_deployment_id``. Each runs unmocked; only the document lookups (and
``Alloweds.is_allowed`` for the shared-template path) are stubbed.
"""

import pytest
from isardvdi_common.helpers import helpers as mod
from isardvdi_common.helpers.error_factory import Error

H = mod.Helpers


def _docs(monkeypatch, mapping):
    """``Caches.get_document(table, id, ...)`` -> mapping[table]."""
    monkeypatch.setattr(
        mod.Caches,
        "get_document",
        classmethod(
            lambda cls, table, item_id, keys=None, invalidate=False: mapping.get(table)
        ),
    )


class TestOwnsBookingId:
    def test_admin_passes(self, monkeypatch):
        _docs(monkeypatch, {})
        assert H.owns_booking_id({"role_id": "admin"}, "b-1") == "b-1"

    def test_missing_booking_not_found(self, monkeypatch):
        _docs(monkeypatch, {"bookings": None})
        with pytest.raises(Error) as exc:
            H.owns_booking_id({"role_id": "user", "user_id": "u-1"}, "b-1")
        assert exc.value.error["description_code"] == "not_found"

    def test_owner_passes(self, monkeypatch):
        _docs(monkeypatch, {"bookings": "u-1"})
        assert H.owns_booking_id({"role_id": "user", "user_id": "u-1"}, "b-1") == "b-1"

    def test_manager_same_category_passes(self, monkeypatch):
        _docs(monkeypatch, {"bookings": "u-owner", "users": "cat-1"})
        assert (
            H.owns_booking_id(
                {"role_id": "manager", "user_id": "u-mgr", "category_id": "cat-1"},
                "b-1",
            )
            == "b-1"
        )

    def test_non_owner_forbidden(self, monkeypatch):
        _docs(monkeypatch, {"bookings": "u-owner"})
        with pytest.raises(Error) as exc:
            H.owns_booking_id({"role_id": "user", "user_id": "u-other"}, "b-1")
        assert exc.value.error["error"] == "forbidden"
        assert exc.value.error["description_code"] == "not_enough_rights_booking"


class TestOwnsDomainId:
    def test_admin_passes(self, monkeypatch):
        _docs(monkeypatch, {})
        assert H.owns_domain_id({"role_id": "admin"}, "d-1") is True

    def test_owner_passes(self, monkeypatch):
        _docs(monkeypatch, {"domains": {"user": "u-1", "tag": False, "category": "c"}})
        assert H.owns_domain_id({"role_id": "user", "user_id": "u-1"}, "d-1") is True

    def test_non_owner_forbidden(self, monkeypatch):
        _docs(
            monkeypatch,
            {"domains": {"user": "u-owner", "tag": False, "category": "c"}},
        )
        with pytest.raises(Error) as exc:
            H.owns_domain_id({"role_id": "user", "user_id": "u-other"}, "d-1")
        assert exc.value.error["error"] == "forbidden"
        assert exc.value.error["description_code"] == "not_enough_rights_desktop"

    def test_missing_domain_is_forbidden(self, monkeypatch):
        # The inner not_found is swallowed by the except; the observable result
        # of a missing domain is the generic forbidden wall.
        _docs(monkeypatch, {"domains": None})
        with pytest.raises(Error) as exc:
            H.owns_domain_id({"role_id": "user", "user_id": "u-1"}, "d-1")
        assert exc.value.error["description_code"] == "not_enough_rights_desktop"


class TestOwnsMediaId:
    def test_admin_passes(self, monkeypatch):
        _docs(monkeypatch, {})
        assert H.owns_media_id({"role_id": "admin"}, "m-1") == "m-1"

    def test_owner_passes(self, monkeypatch):
        _docs(monkeypatch, {"media": {"user": "u-1", "category": "c"}})
        assert H.owns_media_id({"role_id": "user", "user_id": "u-1"}, "m-1") == "m-1"

    def test_non_owner_forbidden(self, monkeypatch):
        _docs(monkeypatch, {"media": {"user": "u-owner", "category": "c"}})
        with pytest.raises(Error) as exc:
            H.owns_media_id({"role_id": "user", "user_id": "u-other"}, "m-1")
        assert exc.value.error["error"] == "forbidden"
        assert exc.value.error["description_code"].startswith("not_enough_rights_media")


class TestOwnsDeploymentId:
    def test_admin_passes(self, monkeypatch):
        _docs(monkeypatch, {})
        assert H.owns_deployment_id({"role_id": "admin"}, "dep-1") is True

    def test_owner_passes(self, monkeypatch):
        _docs(
            monkeypatch,
            {"deployments": {"user": "u-1", "co_owners": []}},
        )
        assert (
            H.owns_deployment_id({"role_id": "user", "user_id": "u-1"}, "dep-1") is True
        )

    def test_co_owner_passes(self, monkeypatch):
        _docs(
            monkeypatch,
            {"deployments": {"user": "u-owner", "co_owners": ["u-1"]}},
        )
        assert (
            H.owns_deployment_id({"role_id": "user", "user_id": "u-1"}, "dep-1") is True
        )

    def test_non_owner_forbidden(self, monkeypatch):
        _docs(
            monkeypatch,
            {"deployments": {"user": "u-owner", "co_owners": []}},
        )
        with pytest.raises(Error) as exc:
            H.owns_deployment_id({"role_id": "user", "user_id": "u-other"}, "dep-1")
        assert exc.value.error["error"] == "forbidden"
        assert exc.value.error["description_code"].startswith(
            "not_enough_rights_deployment"
        )
