# SPDX-License-Identifier: AGPL-3.0-or-later

import json
from pathlib import Path

import isardvdi_changefeed
import pytest
from isardvdi_changefeed import __main__ as changefeed_main
from isardvdi_changefeed.table_changefeed import REDACT_FIELDS
from pydantic import ValidationError

_TABLES_JSON = Path(isardvdi_changefeed.__file__).parent / "tables.json"

_PRIVATE_KEY_PATH = ["vpn", "wireguard", "keys", "private"]


def _config():
    return {t["table"]: t for t in json.loads(_TABLES_JSON.read_text())}


def _pluck_exposes_wireguard_keys(pluck):
    """True when an explicit pluck streams ``vpn.wireguard.keys`` (which
    includes the private key). A ``None`` pluck (full row) is handled
    per-table below since it can carry the keypair without naming it."""
    if pluck is None:
        return False
    for entry in pluck:
        if isinstance(entry, dict) and "vpn" in entry:
            wireguard = (entry.get("vpn") or {}).get("wireguard") or {}
            if wireguard.get("keys"):
                return True
    return False


def test_tables_json_validates():
    entries = changefeed_main._load_tables()
    assert entries
    assert all(isinstance(e["table"], str) for e in entries)


def test_malformed_entry_raises(tmp_path):
    bad = tmp_path / "tables.json"
    bad.write_text(json.dumps([{"strem": True}]))
    with pytest.raises(ValidationError):
        [
            changefeed_main._TableEntry.model_validate(e)
            for e in json.loads(bad.read_text())
        ]


def test_user_storage_pluck_matches_contract():
    """Lock the user_storage pluck contract.

    The pluck emits metadata fields only. password is intentionally
    omitted — it is an external-provider credential and must not leak
    to admin sockets. If this changes, the frontend contract and
    security review must be updated in lockstep.
    """
    cfg = _config()["user_storage"]
    assert cfg["pluck"] == [
        "id",
        "name",
        "description",
        "provider",
        "status",
        "enabled",
    ]
    assert "password" not in cfg["pluck"]


def test_hypervisors_pluck_includes_thread_status():
    """Lock the hypervisors pluck — includes thread_status."""
    cfg = _config()["hypervisors"]
    flat = [p for p in cfg["pluck"] if isinstance(p, str)]
    assert "thread_status" in flat


def test_hypervisors_vpn_pluck_includes_tunnel_status():
    """Lock the hypervisors vpn pluck — tunnel_status is published so the
    webapp datatable can render the live VPN indicator written by the VPN
    container's tunnel_monitor."""
    cfg = _config()["hypervisors"]
    vpn_pluck = next(
        p["vpn"] for p in cfg["pluck"] if isinstance(p, dict) and "vpn" in p
    )
    assert vpn_pluck.get("tunnel_status") is True


def test_streamed_tables_plucking_wireguard_keys_redact_private():
    """Any streamed table that plucks ``vpn.wireguard.keys`` must strip the
    private key before publishing — otherwise it leaks to redis pub/sub, the
    ``stream:<table>`` streams, and the admin socket via the change handler.
    Currently users + hypervisors; this guards new tables added later."""
    offenders = [
        name
        for name, cfg in _config().items()
        if cfg.get("stream")
        and _pluck_exposes_wireguard_keys(cfg.get("pluck"))
        and _PRIVATE_KEY_PATH not in REDACT_FIELDS.get(name, [])
    ]
    assert not offenders, (
        "streamed tables expose vpn.wireguard.keys without redacting the "
        f"private key: {offenders}"
    )


def test_remotevpn_full_row_redacts_private_key():
    """remotevpn streams the full row (no pluck), so it carries the wireguard
    private key; the full-row case is invisible to the pluck scan above, so
    assert its redaction explicitly."""
    cfg = _config()["remotevpn"]
    assert cfg.get("stream") is True
    assert cfg.get("pluck") is None
    assert _PRIVATE_KEY_PATH in REDACT_FIELDS["remotevpn"]
