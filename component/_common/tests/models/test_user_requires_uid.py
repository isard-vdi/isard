#
#   Copyright © 2026 IsardVDI
#
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Users are looked up by uid, category and provider: a user stored without a
uid is the one every later login with an empty uid lands on."""

import pytest
from isardvdi_common.connections.rethink_base import RethinkBase
from isardvdi_common.helpers.error_factory import Error
from isardvdi_common.models.user import User


class TestUserInitDocument:
    @pytest.mark.parametrize(
        "user",
        [
            pytest.param({"username": "bob"}, id="missing"),
            pytest.param({"username": "bob", "uid": None}, id="null"),
            pytest.param({"username": "bob", "uid": ""}, id="empty"),
        ],
    )
    def test_init_document_rejects_a_user_without_uid(self, monkeypatch, user):
        inserted = []
        monkeypatch.setattr(
            RethinkBase,
            "init_document",
            classmethod(lambda cls, *args, **kwargs: inserted.append(kwargs)),
        )

        with pytest.raises(Error) as exc:
            User.init_document(**user)

        assert exc.value.status_code == 500
        assert exc.value.error["description_code"] == "user_uid_empty"
        assert inserted == []

    def test_init_document_inserts_a_user_with_uid(self, monkeypatch):
        inserted = []
        monkeypatch.setattr(
            RethinkBase,
            "init_document",
            classmethod(lambda cls, *args, **kwargs: inserted.append(kwargs)),
        )

        User.init_document(username="bob", uid="bob")

        assert inserted == [{"username": "bob", "uid": "bob"}]
