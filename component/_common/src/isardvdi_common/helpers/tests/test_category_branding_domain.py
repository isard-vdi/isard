#
#   Copyright © 2026 IsardVDI
#
#   This file is part of IsardVDI.
#
#   IsardVDI is free software: you can redistribute it and/or modify
#   it under the terms of the GNU Affero General Public License as published by
#   the Free Software Foundation, either version 3 of the License, or (at your
#   option) any later version.
#
#   IsardVDI is distributed in the hope that it will be useful, but WITHOUT ANY
#   WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS
#   FOR A PARTICULAR PURPOSE. See the GNU General Public License for more
#   details.
#
#   You should have received a copy of the GNU Affero General Public License
#   along with IsardVDI. If not, see <https://www.gnu.org/licenses/>.
#
# SPDX-License-Identifier: AGPL-3.0-or-later

"""A category branding domain must not be the installation's own domain.

Accepting it made haproxy-sync register a second certificate for a name the
base certificate already served, leaving two crt-list entries with the same SAN
and no deterministic answer to which one HAProxy would serve.
"""

import pytest
from isardvdi_common.helpers.category import Category


def _stub():
    """A Category instance with a known id but no DB (bypass __init__)."""
    cat = Category.__new__(Category)
    object.__setattr__(cat, "id", "cat-1")
    return cat


class _Reached(RuntimeError):
    """Raised in place of the uniqueness query, which needs a database."""


def _trip_on_the_db_query(cat):
    def _raise():
        raise _Reached()

    object.__setattr__(cat, "_rdb_context", _raise)


def test_rejects_the_installations_own_domain(monkeypatch):
    monkeypatch.setenv("DOMAIN", "portal.example.com")
    cat = _stub()

    with pytest.raises(ValueError, match="own"):
        cat.branding = {"domain": {"enabled": True, "name": "portal.example.com"}}


def test_rejects_the_installations_own_domain_whatever_its_case(monkeypatch):
    monkeypatch.setenv("DOMAIN", "portal.example.com")
    cat = _stub()

    with pytest.raises(ValueError, match="own"):
        cat.branding = {"domain": {"enabled": True, "name": "Portal.Example.COM"}}


def test_accepts_a_different_domain(monkeypatch):
    monkeypatch.setenv("DOMAIN", "portal.example.com")
    cat = _stub()
    _trip_on_the_db_query(cat)

    # Getting as far as the uniqueness query is the proof it was not refused.
    with pytest.raises(_Reached):
        cat.branding = {"domain": {"enabled": True, "name": "aula.example.com"}}


def test_does_not_refuse_anything_when_domain_is_unset(monkeypatch):
    monkeypatch.delenv("DOMAIN", raising=False)
    cat = _stub()
    _trip_on_the_db_query(cat)

    with pytest.raises(_Reached):
        cat.branding = {"domain": {"enabled": True, "name": "portal.example.com"}}
