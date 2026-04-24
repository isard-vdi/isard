# SPDX-License-Identifier: AGPL-3.0-or-later

"""Tests for AdminVpnService — input-validation paths only.

The success paths use raw RethinkDB query chains and would need a
MockThink fixture; the routes/tests/ layer covers those. Here we
pin the typed-Error rejection of unknown `kind` values, which is
the externally-visible contract the route layer maps to a 404.
"""

import pytest
from api.services.admin_vpn import AdminVpnService
from api.services.error import Error


class TestActiveClientKindGuard:
    @pytest.mark.parametrize("bad", ["user", "hyper", "all", "", "router", None])
    def test_rejects_unknown_kind(self, bad):
        with pytest.raises(Error):
            AdminVpnService.active_client(bad, "10.0.0.1")


class TestResetConnectionStatusKindGuard:
    @pytest.mark.parametrize("bad", ["user", "hyper", "remotevpn", "", None])
    def test_rejects_unknown_kind(self, bad):
        # `remotevpn` is referenced in the implementation body for partial
        # match, but the front-door guard rejects everything outside
        # {"users", "hypers", "all"}.
        with pytest.raises(Error):
            AdminVpnService.reset_connection_status(bad)
