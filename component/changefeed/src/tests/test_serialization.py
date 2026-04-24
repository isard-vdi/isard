# SPDX-License-Identifier: AGPL-3.0-or-later
"""Tests for the isard-changefeed publisher serialization layer.

These tests cover two concerns:

1. The ``sanitize()`` helper in ``table_changefeed`` — verifying that
   datetimes become ISO strings (since the downstream AsyncAPI / Pydantic
   models expect JSON primitives on the wire).
2. The contract between ``sanitize()`` output and the per-table subscriber
   ``serialize()`` / ``parse()`` methods — verifying that a sanitised
   RethinkDB change dict can be fed straight into the subscriber for every
   real changefeed table.
"""

from __future__ import annotations

import json
from datetime import datetime

import pytest
from changefeed_subscribers import TABLE_TO_SUBSCRIBER
from table_changefeed import sanitize


class TestSanitize:
    def test_datetime_becomes_iso_string(self):
        dt = datetime(2026, 4, 9, 12, 34, 56)
        out = sanitize({"created": dt})
        assert out == {"created": "2026-04-09T12:34:56"}

    def test_nested_dict(self):
        dt = datetime(2026, 4, 9, 12, 0, 0)
        out = sanitize({"outer": {"inner": {"ts": dt}}})
        assert out["outer"]["inner"]["ts"] == "2026-04-09T12:00:00"

    def test_list_of_datetimes(self):
        out = sanitize([datetime(2026, 1, 1), datetime(2026, 2, 1)])
        assert out == ["2026-01-01T00:00:00", "2026-02-01T00:00:00"]

    def test_primitives_pass_through(self):
        assert sanitize(42) == 42
        assert sanitize("hello") == "hello"
        assert sanitize(True) is True
        assert sanitize(None) is None

    def test_mixed_structure_with_datetime_field(self):
        inner_ts = datetime(2026, 4, 9, 12, 0, 0)
        change = {
            "new_val": {
                "id": "domain-1",
                "table": "domains",
                "some_ts": inner_ts,
            },
            "old_val": None,
        }
        sanitised = sanitize(change)
        assert sanitised["new_val"]["some_ts"] == "2026-04-09T12:00:00"
        assert sanitised["new_val"]["id"] == "domain-1"
        assert sanitised["old_val"] is None


class TestSerializeIntegration:
    def test_sanitized_domain_change_roundtrips(self):
        change = {
            "new_val": {
                "id": "dsk-1",
                "table": "domains",
                "name": "test-desktop",
                "accessed": 1775995200.0,
                "status": "Started",
            },
            "old_val": {
                "id": "dsk-1",
                "table": "domains",
                "name": "test-desktop",
                "accessed": 1775995199.0,
                "status": "Stopped",
            },
        }

        subscriber = TABLE_TO_SUBSCRIBER["domains"]
        payload = subscriber.serialize(sanitize(change))
        env = subscriber.parse(payload)

        assert env.table == "domains"
        assert env.change.new_val is not None
        assert env.change.new_val.name == "test-desktop"
        assert env.change.new_val.status == "Started"
        assert env.change.new_val.accessed == 1775995200.0

    def test_sanitized_engine_change_preserves_fields(self):
        change = {
            "new_val": {
                "table": "engine",
                "status_all_threads": "Running",
                "threads": 5,
            },
            "old_val": None,
        }

        subscriber = TABLE_TO_SUBSCRIBER["engine"]
        payload = subscriber.serialize(sanitize(change))
        parsed = json.loads(payload)

        assert parsed["table"] == "engine"
        new_val = parsed["change"]["new_val"]
        assert new_val["status_all_threads"] == "Running"
        assert new_val["threads"] == 5

    @pytest.mark.parametrize("table", sorted(TABLE_TO_SUBSCRIBER))
    def test_every_table_accepts_empty_change(self, table):
        subscriber = TABLE_TO_SUBSCRIBER[table]
        payload = subscriber.serialize({"new_val": None, "old_val": None})
        env = subscriber.parse(payload)
        assert env.table == table


class TestSanitizeEdgeCases:
    def test_decimal_passes_through(self):
        from decimal import Decimal

        # Pinning current behavior: Decimal is not a known branch in sanitize,
        # so it passes through unchanged. If serialize-to-JSON later forces a
        # conversion, change sanitize and this assert together.
        d = Decimal("1.5")
        assert sanitize(d) is d

    def test_bytes_pass_through(self):
        # bytes is not JSON-serializable; sanitize does not coerce.
        # Downstream Pydantic will surface the TypeError at publish time.
        b = b"raw"
        assert sanitize(b) is b

    def test_nested_none_values(self):
        assert sanitize({"a": None, "b": [None, {"c": None}]}) == {
            "a": None,
            "b": [None, {"c": None}],
        }

    def test_tuple_passes_through_unchanged(self):
        # sanitize walks dict and list; tuple is not walked — pinning current
        # behavior. If this ever needs to change, audit call sites first.
        t = (1, datetime(2026, 1, 1))
        assert sanitize(t) == t


# The row models declare ``accessed`` as ``float`` across domains/media/users,
# so a Python ``datetime`` cannot live on that field — sanitize would turn it
# into an ISO string and Pydantic would reject the str. The realistic samples
# below put the datetime on a non-plucked key (``last_seen_dt``) so it flows
# through ``additional_properties`` untouched by the typed schema.
_REAL_SAMPLES = {
    "domains": {
        "id": "_local-admin-admin_desktop1",
        "table": "domains",
        "user": "local-admin-admin",
        "category": "default",
        "status": "Started",
        "kind": "desktop",
        "name": "Ütf-8 desktop — edge case",
        "accessed": 1775995200.0,
        "last_seen_dt": datetime(2026, 4, 21, 10, 0, 0),
        "create_dict": {
            "hardware": {
                "interfaces": [{"mac": "00:11:22:33:44:55"}],
                "memory": 2048,
            }
        },
    },
    "media": {
        "id": "m1",
        "table": "media",
        "kind": "iso",
        "user": "admin",
        "category": "default",
        "name": "Ubuntu — Noble",
        "status": "Downloaded",
        "accessed": 1775995200.0,
        "last_seen_dt": datetime(2026, 4, 1, 9, 0, 0),
    },
    "users": {
        "id": "local-admin-admin",
        "table": "users",
        "username": "admin",
        "category": "default",
        "group": "default-admins",
        "role": "admin",
        "name": "Administrador — ñandú",
        "email": "admin@example.org",
        "active": True,
        "accessed": 1775995200.0,
        "last_seen_dt": datetime(2026, 4, 10, 8, 30, 0),
        "vpn": {
            "wireguard": {
                "Address": "10.0.0.2/32",
                "connected": True,
            }
        },
    },
    "hypervisors": {
        "id": "isard-hypervisor",
        "table": "hypervisors",
        "hostname": "hyper-01",
        "enabled": True,
        "only_forced": False,
        "status": "Online",
        "status_time": 1775995200,
        "last_seen_dt": datetime(2026, 4, 15, 7, 0, 0),
        "description": "Ñode principal — producció",
        "vpn": {
            "tunneling_mode": "wireguard",
            "wireguard": {
                "Address": "10.1.0.1/24",
                "AllowedIPs": ["10.0.0.0/8"],
                "connected": True,
            },
        },
        "stats": {
            "mem_stats": {"total": 65536, "available": 32000, "used": 33536},
            "cpu_1min": {"used": 42.5},
        },
    },
    "engine": {
        "id": "engine",
        "table": "engine",
        "status_all_threads": "Running",
        "threads": 5,
        "last_seen_dt": datetime(2026, 4, 22, 12, 0, 0),
        "note": "Operació — sense errors",
    },
}


class TestRealisticRowsRoundTrip:
    @pytest.mark.parametrize(
        "table,sample", list(_REAL_SAMPLES.items()), ids=list(_REAL_SAMPLES)
    )
    def test_subscriber_accepts_realistic_row(self, table, sample):
        subscriber = TABLE_TO_SUBSCRIBER[table]
        change = {"new_val": sample, "old_val": None}
        payload = subscriber.serialize(sanitize(change))
        env = subscriber.parse(payload)

        assert env.table == table
        assert env.change.new_val is not None

        # EngineRow has no declared ``id`` field, so the id falls into
        # additional_properties rather than onto the model.
        if table == "engine":
            extras = env.change.new_val.additional_properties or {}
            assert extras.get("id") == sample["id"]
        else:
            assert env.change.new_val.id == sample["id"]

        # The datetime landed in additional_properties as an ISO string.
        extras = env.change.new_val.additional_properties or {}
        assert extras.get("last_seen_dt") == sample["last_seen_dt"].isoformat()

        # Round-trip survives JSON boundary: reparsing the serialized envelope
        # yields a dict equivalent to what Pydantic stored.
        reparsed = json.loads(payload)
        assert reparsed["table"] == table
