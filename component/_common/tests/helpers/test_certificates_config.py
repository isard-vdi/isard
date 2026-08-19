# SPDX-License-Identifier: AGPL-3.0-or-later

"""Tests for ``isardvdi_common.helpers.certificates_config.CertificatesConfig``.

The accessor for ``config[1].certificates``, modelled on ``ViewersConfig``.

The pair of writers is the point of these tests. RethinkDB's ``update`` is a
deep merge and can never remove a key, so it is the right call to persist a
subset; ``r.literal`` forces a wholesale replace of the subtree and is the only
way a nested block can actually shrink. Mixing them up is silent either way:
the merge quietly keeps a key the caller meant to drop, and the replace quietly
drops every key the caller did not resend.

Both writers must invalidate the shared ``config``/1 document cache, or every
reader keeps serving the pre-write document for the rest of the TTL.
"""

from unittest.mock import MagicMock, patch

import pytest


@pytest.fixture
def certificates_config():
    from isardvdi_common.helpers.certificates_config import CertificatesConfig

    return CertificatesConfig


@pytest.fixture
def rdb(certificates_config, monkeypatch):
    """Capture the ReQL term each writer builds, without a database.

    ``_rdb_connection`` is a descriptor with a metaclass property, so it is
    replaced on the type the way the rest of the helper suites do it; patching
    it as a plain attribute fails to restore on teardown.
    """

    class _Ctx:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    monkeypatch.setattr(
        certificates_config, "_rdb_context", classmethod(lambda cls: _Ctx())
    )
    monkeypatch.setattr(
        type(certificates_config),
        "_rdb_connection",
        property(lambda self: MagicMock(name="conn")),
    )
    with patch("isardvdi_common.helpers.certificates_config.r") as mock_r:
        yield mock_r


class TestGetCertificatesConfig:
    def test_returns_the_certificates_block(self, certificates_config, rdb):
        rdb.table.return_value.get.return_value.default.return_value.run.return_value = {
            "certificates": {"main_domain": {"names": ["vdi.example.com"]}}
        }
        assert certificates_config.get_certificates_config() == {
            "main_domain": {"names": ["vdi.example.com"]}
        }

    def test_missing_block_is_an_empty_dict(self, certificates_config, rdb):
        rdb.table.return_value.get.return_value.default.return_value.run.return_value = {
            "id": 1
        }
        assert certificates_config.get_certificates_config() == {}

    def test_missing_row_is_an_empty_dict(self, certificates_config, rdb):
        rdb.table.return_value.get.return_value.default.return_value.run.return_value = (
            None
        )
        assert certificates_config.get_certificates_config() == {}

    def test_null_block_is_an_empty_dict(self, certificates_config, rdb):
        rdb.table.return_value.get.return_value.default.return_value.run.return_value = {
            "certificates": None
        }
        assert certificates_config.get_certificates_config() == {}


class TestUpdateCertificatesConfig:
    def test_merges_without_r_literal(self, certificates_config, rdb):
        certificates_config.update_certificates_config(
            {"main_domain": {"email": "a@b"}}
        )
        payload = rdb.table.return_value.get.return_value.update.call_args.args[0]
        assert payload == {"certificates": {"main_domain": {"email": "a@b"}}}
        rdb.literal.assert_not_called()

    @patch("isardvdi_common.helpers.certificates_config.Caches")
    def test_invalidates_the_config_cache(self, mock_caches, certificates_config, rdb):
        certificates_config.update_certificates_config({"main_domain": {}})
        mock_caches.invalidate_cache.assert_called_once_with("config", 1)


class TestReplaceCertificatesConfig:
    def test_wraps_the_subtree_in_r_literal(self, certificates_config, rdb):
        rdb.literal.return_value = "<literal>"
        certificates_config.replace_certificates_config(
            {"main_domain": {"email": "a@b"}}
        )
        rdb.literal.assert_called_once_with({"main_domain": {"email": "a@b"}})
        payload = rdb.table.return_value.get.return_value.update.call_args.args[0]
        assert payload == {"certificates": "<literal>"}

    @patch("isardvdi_common.helpers.certificates_config.Caches")
    def test_invalidates_the_config_cache(self, mock_caches, certificates_config, rdb):
        certificates_config.replace_certificates_config({"main_domain": {}})
        mock_caches.invalidate_cache.assert_called_once_with("config", 1)
