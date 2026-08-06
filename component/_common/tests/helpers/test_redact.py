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

``loggable_body`` layers the request-body rules on top: JSON only, redacted,
size-capped, dropped rather than logged raw when it cannot be parsed.
"""

import json

from isardvdi_common.helpers.redact import (
    BODY_LIMIT,
    REDACTED,
    loggable_body,
    redact_secrets,
)

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


class TestRequestBodyVocabulary:
    """Keys that reach the redactor from apiv4 request bodies, not changefeed rows."""

    def test_ssh_key_masked(self):
        assert redact_secrets({"ssh_key": _SECRET})["ssh_key"] == REDACTED

    def test_authorized_keys_masked(self):
        assert redact_secrets({"authorized_keys": [_SECRET]})["authorized_keys"] == (
            REDACTED
        )

    def test_jwt_masked(self):
        assert redact_secrets({"jwt": _SECRET})["jwt"] == REDACTED

    def test_registration_code_masked(self):
        assert redact_secrets({"code": _SECRET})["code"] == REDACTED

    def test_diagnostic_code_fields_stay_readable(self):
        """`code` is exact-match: these carry no secret and are needed in logs."""
        row = {"description_code": "not_found", "msg_code": "a", "message_code": "b"}
        assert redact_secrets(row) == row

    def test_non_secret_key_fields_stay_readable(self):
        """Why bare `key` is not a token: these would all have been swallowed."""
        row = {"evicted_keys": 3, "key": "es", "keyboard": "es"}
        assert redact_secrets(row) == row

    def test_every_row_of_a_bulk_edit_is_masked(self):
        """apiv3 checked only a top-level `password`, so every CSV row leaked."""
        out = redact_secrets(
            {"users": [{"username": "a", "password": _SECRET}, {"password": _SECRET}]}
        )
        assert _SECRET not in repr(out)
        assert out["users"][0]["username"] == "a"


class TestLoggableBody:
    def test_json_bytes_are_parsed_and_redacted(self):
        raw = json.dumps({"username": "isard", "password": _SECRET}).encode()
        assert loggable_body(raw) == {"username": "isard", "password": REDACTED}

    def test_form_encoded_is_dropped_entirely(self):
        """Logging this raw is precisely how apiv3 leaked GET/DELETE params."""
        assert loggable_body(b"username=isard&password=" + _SECRET.encode()) is None

    def test_binary_is_dropped(self):
        assert loggable_body(b"\xff\xfe\x00") is None

    def test_nothing_to_log_is_none(self):
        assert loggable_body(b"") is None
        assert loggable_body(None) is None

    def test_oversized_is_summarised_not_logged(self):
        raw = json.dumps({"password": _SECRET, "pad": "x" * BODY_LIMIT}).encode()
        out = loggable_body(raw)
        assert out == {"truncated": True, "size": len(raw)}
        assert _SECRET not in repr(out)

    def test_a_json_scalar_body_survives(self):
        assert loggable_body(b'"hello"') == "hello"
