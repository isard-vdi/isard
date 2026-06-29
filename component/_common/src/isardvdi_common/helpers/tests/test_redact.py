#
#   Copyright © 2026 IsardVDI
#
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Pin that ``redact_secrets`` masks only secret-bearing fields.

The change-handler logged the full ``DomainsRow`` at INFO and the engine
dumped whole domain/hypervisor rows at DEBUG, leaking guest credentials,
viewer passwords and TLS material to the central Loki. ``redact_secrets``
must hide exactly those fields and keep everything else (status, ids,
timestamps, non-secret prefs) visible for debugging.
"""

from isardvdi_common.helpers.redact import REDACTED, redact_secrets

_SECRET = "pirineus"


class TestRedactSecrets:
    def test_nested_credentials_masked_siblings_kept(self):
        row = {
            "id": "d1",
            "status": "Started",
            "guest_properties": {
                "credentials": {"username": "isard", "password": _SECRET},
                "fullscreen": True,
            },
        }
        out = redact_secrets(row)
        assert out["id"] == "d1"
        assert out["status"] == "Started"
        assert out["guest_properties"]["fullscreen"] is True
        assert out["guest_properties"]["credentials"] == REDACTED

    def test_viewer_passwd_and_tls_masked_guest_ip_kept(self):
        row = {
            "viewer": {
                "guest_ip": "10.0.0.5",
                "passwd": _SECRET,
                "tls-cert": "-----BEGIN CERTIFICATE-----",
                "client-tls": {"key": "-----BEGIN PRIVATE KEY-----"},
            }
        }
        out = redact_secrets(row)
        assert out["viewer"]["guest_ip"] == "10.0.0.5"
        assert out["viewer"]["passwd"] == REDACTED
        assert out["viewer"]["tls-cert"] == REDACTED
        assert out["viewer"]["client-tls"] == REDACTED

    def test_xml_blob_masked_whole(self):
        out = redact_secrets({"xml": f"<graphics passwd='{_SECRET}'/>"})
        assert out["xml"] == REDACTED

    def test_lists_are_recursed(self):
        out = redact_secrets({"viewers": [{"passwd": _SECRET}, {"port": 5900}]})
        assert out["viewers"][0]["passwd"] == REDACTED
        assert out["viewers"][1]["port"] == 5900

    def test_scalars_pass_through(self):
        assert redact_secrets("Started") == "Started"
        assert redact_secrets(42) == 42
        assert redact_secrets(None) is None

    def test_pydantic_model_is_dumped_and_redacted(self):
        class _Row:
            def model_dump(self):
                return {"id": "d1", "credentials": {"password": _SECRET}}

        out = redact_secrets(_Row())
        assert out["id"] == "d1"
        assert out["credentials"] == REDACTED

    def test_full_domain_change_leaks_no_secret(self):
        change = {
            "new_val": {
                "id": "d1",
                "status": "Started",
                "guest_properties": {"credentials": {"password": _SECRET}},
                "viewer": {"passwd": _SECRET},
                "xml": f"<graphics passwd='{_SECRET}'/>",
            },
            "old_val": {"id": "d1", "status": "Starting"},
        }
        assert _SECRET not in repr(redact_secrets(change))
