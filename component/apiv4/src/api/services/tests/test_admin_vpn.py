# SPDX-License-Identifier: AGPL-3.0-or-later

"""Tests for AdminVpnService.

The previous suite pinned a service-side ``if kind not in (...): raise
Error`` guard on ``active_client`` and ``reset_connection_status``.
Both routes (``/admin/vpn_connection/{kind}/{client_ip}`` and
``/admin/vpn_connection/{kind}``) now constrain ``kind`` at the route
boundary via ``typing.Literal[...]``, so FastAPI returns 400 with a
structured ``validation_error`` envelope before the handler runs and
the service layer never sees garbage. Route-layer enforcement is pinned
by ``testing/integration/test_legacy_ui_contracts.py::test_literal_path_param_rejects_invalid``.

Service-level tests for the success paths use raw RethinkDB query
chains and would need a MockThink fixture; the routes/tests/ layer
covers those.
"""
