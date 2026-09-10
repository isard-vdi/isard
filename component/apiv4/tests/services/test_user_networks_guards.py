# SPDX-License-Identifier: AGPL-3.0-or-later

"""Authorization / precondition guards on ``UserNetworkService``.

The route layer (``routes/user_networks.py``) is pure plumbing — it forwards
to this service and maps exceptions to 500 — so the who-can-touch-this
decisions live here and are pinned to BOTH HTTP status and description_code:

* get_user_network: missing -> 404 not_found; a caller who is not admin, not
  the owner, and not a manager of the network's category -> 403 forbidden;
  admin / owner / manager-same-category pass.
* update_user_network / delete_user_network reuse that wall (they call
  get_user_network first). The pinned point for the destructive delete is
  that a forbidden caller's delete NEVER reaches the DB.

The service runs unmocked; only ``UserNetworksProcessed`` (the rethink lib)
is patched, so the allow/deny decision is the real code.
"""

from unittest.mock import patch

import pytest
from api.services.error import Error
from api.services.user_networks import UserNetworkService

MOD = "api.services.user_networks.UserNetworksProcessed"


def _payload(role_id="user", user_id="u1", category_id="cat1"):
    return {
        "user_id": user_id,
        "role_id": role_id,
        "category_id": category_id,
        "group_id": "g1",
    }


def _network(user="owner", category="cat1"):
    return {"id": "n1", "user": user, "category": category, "name": "net"}


class TestGetUserNetworkGuards:
    def test_missing_network_404(self):
        with patch(MOD + ".get", return_value=None):
            with pytest.raises(Error) as exc:
                UserNetworkService.get_user_network("n1", _payload())
        assert exc.value.status_code == 404
        assert exc.value.error["description_code"] == "not_found"

    def test_admin_passes(self):
        net = _network(user="someone-else")
        with patch(MOD + ".get", return_value=net):
            assert UserNetworkService.get_user_network("n1", _payload("admin")) == net

    def test_owner_passes(self):
        net = _network(user="u1")
        with patch(MOD + ".get", return_value=net):
            assert (
                UserNetworkService.get_user_network("n1", _payload(user_id="u1")) == net
            )

    def test_manager_same_category_passes(self):
        net = _network(user="someone-else", category="cat1")
        with patch(MOD + ".get", return_value=net):
            assert (
                UserNetworkService.get_user_network(
                    "n1", _payload("manager", category_id="cat1")
                )
                == net
            )

    def test_non_owner_forbidden(self):
        net = _network(user="someone-else", category="other-cat")
        with patch(MOD + ".get", return_value=net):
            with pytest.raises(Error) as exc:
                UserNetworkService.get_user_network("n1", _payload(user_id="u1"))
        assert exc.value.status_code == 403
        assert exc.value.error["description_code"] == "forbidden"

    def test_manager_other_category_forbidden(self):
        net = _network(user="someone-else", category="other-cat")
        with patch(MOD + ".get", return_value=net):
            with pytest.raises(Error) as exc:
                UserNetworkService.get_user_network(
                    "n1", _payload("manager", category_id="cat1")
                )
        assert exc.value.status_code == 403


SVC = "api.services.user_networks.UserNetworkService"


class TestUpdateAuthWall:
    def test_backstop_forbidden_update_does_not_write(self):
        # get_user_network already gates access, so update's own owner-check is
        # a backstop: verify it independently by letting a non-owned network
        # through the lookup and confirming a non-owner still cannot write.
        net = _network(user="someone-else", category="other-cat")
        with patch(SVC + ".get_user_network", return_value=net), patch(
            MOD + ".update"
        ) as upd:
            with pytest.raises(Error) as exc:
                UserNetworkService.update_user_network(
                    "n1", object(), _payload(user_id="u1")
                )
        assert exc.value.status_code == 403
        upd.assert_not_called()

    def test_owner_update_writes(self):
        from types import SimpleNamespace

        net = _network(user="u1")
        data = SimpleNamespace(name="new", description=None, qos_id=None, allowed=None)
        with patch(MOD + ".get", return_value=net), patch(MOD + ".update") as upd:
            result = UserNetworkService.update_user_network(
                "n1", data, _payload(user_id="u1")
            )
        upd.assert_called_once()
        assert result["name"] == "new"


class TestDeleteAuthWall:
    def test_backstop_forbidden_delete_does_not_touch_db(self):
        # Backstop check (get_user_network is the primary gate): even if the
        # lookup returns a network the caller does not own, the destructive
        # delete must NEVER reach the DB.
        net = _network(user="someone-else", category="other-cat")
        with patch(SVC + ".get_user_network", return_value=net), patch(
            MOD + ".delete"
        ) as dele:
            with pytest.raises(Error) as exc:
                UserNetworkService.delete_user_network("n1", _payload(user_id="u1"))
        assert exc.value.status_code == 403
        dele.assert_not_called()

    def test_owner_delete_removes(self):
        net = _network(user="u1")
        with patch(MOD + ".get", return_value=net), patch(MOD + ".delete") as dele:
            UserNetworkService.delete_user_network("n1", _payload(user_id="u1"))
        dele.assert_called_once_with("n1")
