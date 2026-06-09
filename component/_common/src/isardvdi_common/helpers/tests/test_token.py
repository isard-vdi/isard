# SPDX-License-Identifier: AGPL-3.0-or-later

"""Tests for ``Token.get_expired_user_data`` signature verification.

The cookie may be expired (logout reads stale cookies) but its HS256
signature against ``API_ISARDVDI_SECRET`` must still verify; a token
signed with any other secret must be rejected (AUTH-VULN-09).
"""

import time

import jwt
import pytest
from isardvdi_common.helpers.token import Token

SECRET = "testsecret"


@pytest.fixture(autouse=True)
def _secret(monkeypatch):
    monkeypatch.setenv("API_ISARDVDI_SECRET", SECRET)


def _tok(payload, secret=SECRET, exp_offset=-10):
    return jwt.encode(
        {**payload, "exp": int(time.time()) + exp_offset}, secret, algorithm="HS256"
    )


def test_valid_isardvdi_token_returns_data():
    data = {"user_id": "u1", "role_id": "admin", "provider": "form"}
    assert Token.get_expired_user_data(_tok({"kid": "isardvdi", "data": data})) == data


def test_valid_viewer_token_with_desktop_id_returns_data():
    data = {"desktop_id": "d1"}
    assert (
        Token.get_expired_user_data(_tok({"kid": "isardvdi-viewer", "data": data}))
        == data
    )


def test_viewer_token_without_desktop_id_is_rejected():
    tok = _tok({"kid": "isardvdi-viewer", "data": {"foo": "bar"}})
    assert Token.get_expired_user_data(tok) is None


def test_wrong_signature_is_rejected():
    tok = _tok({"kid": "isardvdi", "data": {"user_id": "x"}}, secret="attacker")
    assert Token.get_expired_user_data(tok) is None


def test_unknown_kid_is_rejected():
    tok = _tok({"kid": "isardvdi-hypervisor", "data": {"user_id": "x"}})
    assert Token.get_expired_user_data(tok) is None


def test_missing_kid_is_rejected():
    assert Token.get_expired_user_data(_tok({"data": {"user_id": "x"}})) is None


def test_garbage_token_is_rejected():
    assert Token.get_expired_user_data("not-a-jwt") is None


def test_non_expired_token_still_returns_data():
    data = {"user_id": "u2", "role_id": "user"}
    tok = _tok({"kid": "isardvdi", "data": data}, exp_offset=3600)
    assert Token.get_expired_user_data(tok) == data
