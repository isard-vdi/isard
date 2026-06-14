"""Scrubbing + cross-table consistency tests for anonymize-db.

Mirrors the cli `_scrub_dir` pipeline (defensive_sweep -> per-table scrubber ->
final cross_table_rewrite pass) on an in-memory set of tables shaped like a real
IsardVDI rethinkdb dump, and asserts that:
  * human/PII content is gone, and
  * every value that is denormalized across tables receives the SAME replacement.
"""

from __future__ import annotations

import json

from anonymize_db.scrub import Scrubber, get_scrubbers
from anonymize_db.xml_scrub import scrub_libvirt_xml

# --- real PII values planted in the fixture; none may survive scrubbing ---
REAL_EMAIL = "maria.gonzalez@realcorp.example"
REAL_NAME = "Maria Gonzalez Hidalgo"
REAL_USERNAME = "mgonzalez@realcorp.example"
USER_ID = "aaaaaaaa-1111-2222-3333-444444444444"
DOMAIN_ID = "bbbbbbbb-5555-6666-7777-888888888888"

PII_NEEDLES = [
    REAL_EMAIL,
    REAL_NAME,
    REAL_USERNAME,
    "VIP finance customer",  # users.description
    "Legal Team VPN",  # user_networks.name
    "HQ Amsterdam link",  # user_networks.description
    "Finance Premium Bandwidth",  # qos_net.name
    "My Finance Desktop",  # domains.name
    "secret internal note",  # domains.xml <metadata> free text
]


def _fixture() -> dict[str, list[dict]]:
    return {
        "users": [
            {
                "id": USER_ID,
                "name": REAL_NAME,
                "username": REAL_USERNAME,
                "email": REAL_EMAIL,
                "password": "$2b$realhash",
                "photo": "data:image/png;base64,xxx",
                "description": "VIP finance customer",
                "uid": "sso-mgonzalez-uid-1234567",
                "user_storage": {
                    "email": REAL_EMAIL,
                    "displayname": REAL_NAME,
                    "password": "nextcloud-secret",
                    "quota": 1024,
                },
            }
        ],
        "domains": [
            {
                "id": DOMAIN_ID,
                "user": USER_ID,
                "username": REAL_USERNAME,
                "name": "My Finance Desktop",
                "description": "contains a secret internal note",
                "user": USER_ID,
                "create_dict": {
                    "hardware": {
                        "interfaces": [{"id": "default", "mac": "52:54:00:aa:bb:cc"}]
                    }
                },
                "xml": (
                    "<domain><name>_aaaa</name>"
                    "<metadata><isard:who user_id='%s'/>secret internal note</metadata>"
                    "</domain>" % USER_ID
                ),
                "guest_properties": {
                    "credentials": {"username": "real", "password": "real"}
                },
            }
        ],
        "user_networks": [
            {
                "id": "cccccccc-9999",
                "name": "Legal Team VPN",
                "description": "HQ Amsterdam link",
                "user": USER_ID,
            }
        ],
        "qos_net": [
            {
                "id": "dddddddd-0000",
                "name": "Finance Premium Bandwidth",
                "description": "for finance dept",
            }
        ],
        "videos": [
            # built-in default: id must be preserved (referenced by id elsewhere)
            {"id": "default", "name": "Default", "description": "Default video card"}
        ],
        "disk_bus": [
            # id IS the canonical value and must not change
            {"id": "virtio", "name": "Virtio", "description": "virtio bus"}
        ],
        # an UNSCRUBBED table that denormalizes user identity by value -> must be
        # rewritten consistently by the cross-table pass
        "some_other_table": [
            {
                "id": "x1",
                "owner_email": REAL_EMAIL,
                "owner_fullname": REAL_NAME,
                "owner_username": REAL_USERNAME,
            }
        ],
    }


def _run(tables: dict[str, list[dict]]) -> dict[str, list[dict]]:
    s = Scrubber(seed=0)
    scrubbers = get_scrubbers(s)
    # per-table pass (defensive sweep first, then specific scrubber)
    for name, rows in tables.items():
        s.defensive_sweep(name, rows)
        fn = scrubbers.get(name)
        if fn is not None:
            fn(rows)
    # final cross-table consistency pass
    for rows in tables.values():
        s.cross_table_rewrite(rows)
    return tables


def test_no_pii_survives():
    out = _run(_fixture())
    blob = json.dumps(out, ensure_ascii=False)
    for needle in PII_NEEDLES:
        assert needle not in blob, f"PII leaked: {needle!r}"


def test_user_storage_subdoc_scrubbed_and_consistent():
    out = _run(_fixture())
    u = out["users"][0]
    us = u["user_storage"]
    assert us["email"] == u["email"]  # same replacement as top-level
    assert us["displayname"] == u["name"]
    assert REAL_EMAIL not in (us["email"], us["displayname"])
    assert us["quota"] == 1024  # non-PII preserved
    assert u["description"] == ""


def test_domain_username_matches_user_username():
    out = _run(_fixture())
    user = out["users"][0]
    domain = out["domains"][0]
    assert domain["username"] == user["username"]  # derived from the `user` FK
    assert domain["username"] == f"user-{USER_ID[:8]}"


def test_cross_table_denormalized_values_consistent():
    out = _run(_fixture())
    user = out["users"][0]
    other = out["some_other_table"][0]
    # every denormalized copy got the SAME replacement as the users row
    assert other["owner_email"] == user["email"]
    assert other["owner_fullname"] == user["name"]
    assert other["owner_username"] == user["username"]


def test_catalog_names_scrubbed_ids_preserved():
    out = _run(_fixture())
    assert out["user_networks"][0]["name"].startswith("usernet-")
    assert out["user_networks"][0]["description"] == ""
    assert out["qos_net"][0]["name"].startswith("qosnet-")
    # ids referenced elsewhere must be untouched
    assert out["videos"][0]["id"] == "default"
    assert out["disk_bus"][0]["id"] == "virtio"
    # but their display names are anonymized
    assert out["videos"][0]["name"].startswith("video-")


def test_tables_not_dropped():
    out = _run(_fixture())
    for t in ("user_networks", "qos_net", "videos", "disk_bus", "some_other_table"):
        assert len(out[t]) == 1, f"{t} lost rows"


def test_metadata_notes_stripped():
    xml = "<domain><metadata><isard:who user_id='u'/>secret internal note</metadata></domain>"
    out = scrub_libvirt_xml(xml)
    assert "secret internal note" not in out
    assert "isard:who" not in out
    assert "<metadata></metadata>" in out


# --- regression tests for the production leak found in production (deleted-user
#     identity denormalized in unscrubbed tables) ---


def test_storage_last_domain_attached_scrubbed():
    tables = {
        "storage": [
            {
                "id": "st1",
                "user_id": "abcdef12-3456-7890",
                "directory_path": "/isard/bases/x",
                "qemu-img-info": {"backing-filename": "/isard/y.qcow2"},
                "last_domain_attached": {
                    "id": "dom1",
                    "user": "abcdef12-3456-7890",
                    "username": "jdoe@school.example",
                    "name": "Real Desktop Name",
                    "description": "secret note",
                },
            }
        ],
    }
    out = _run(tables)
    lda = out["storage"][0]["last_domain_attached"]
    assert "jdoe@school.example" not in json.dumps(out)
    assert lda["username"] == "user-abcdef12"  # derived from the user FK
    assert lda["name"].startswith("desktop-")
    assert lda["description"] == ""
    # paths / qemu-img-info are NOT PII -> untouched
    assert out["storage"][0]["directory_path"] == "/isard/bases/x"
    assert out["storage"][0]["qemu-img-info"]["backing-filename"] == "/isard/y.qcow2"


def test_usage_consumption_item_name_scrubbed():
    tables = {
        "usage_consumption": [
            {
                "pk": "p1",
                "item_id": "25e58056-aaaa-bbbb",
                "item_type": "desktop",
                "item_name": "jdoe@school.example",
            }
        ]
    }
    out = _run(tables)
    assert out["usage_consumption"][0]["item_name"] == "desktop-25e58056"
    assert "jdoe@school.example" not in json.dumps(out)


def test_recycle_bin_uid_blanked_but_uuid_kept():
    tables = {
        "recycle_bin": [
            {
                "id": "rb1",
                "item": {
                    "uid": "jdoe@school.example",  # SSO uid == email
                    "uuid": "keep-this-uuid-value",  # must NOT match
                    "name": "Real Name",
                },
            }
        ]
    }
    out = _run(tables)
    item = out["recycle_bin"][0]["item"]
    assert item["uid"] == ""  # blanked
    assert item["uuid"] == "keep-this-uuid-value"  # not a false match
    assert "jdoe@school.example" not in json.dumps(out)


def test_ssh_authorized_keys_blanked():
    SSH = "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIEKZ teacher@school.example"
    tables = {
        # live domain carrying a bastion ssh config
        "domains": [
            {
                "id": "d1",
                "user": "u1abc234",
                "ssh": {"authorized_keys": [SSH], "enabled": True},
            }
        ],
        # deleted-desktop snapshot retained in recycle_bin
        "recycle_bin": [{"id": "rb1", "item": {"ssh": {"authorized_keys": [SSH]}}}],
    }
    out = _run(tables)
    assert "teacher@school.example" not in json.dumps(out)
    assert out["domains"][0]["ssh"]["authorized_keys"] == []
    assert out["domains"][0]["ssh"]["enabled"] is True  # non-PII flag kept
    assert out["recycle_bin"][0]["item"]["ssh"]["authorized_keys"] == []


def test_category_email_domain_restriction_scrubbed():
    # real shape: nested under authentication.{ldap,saml}.email_domain_restriction
    tables = {
        "categories": [
            {
                "id": "acme",
                "name": "Acme",
                "authentication": {
                    "ldap": {
                        "email_domain_restriction": {
                            "allowed": ["school.example"],
                            "enabled": True,
                        }
                    },
                    "saml": {
                        "email_domain_restriction": {"allowed": ["school.example"]}
                    },
                },
            },
            # default category is special-cased (early continue) but must still scrub this
            {
                "id": "default",
                "authentication": {
                    "ldap": {
                        "email_domain_restriction": {
                            "allowed": ["realorg.example"],
                            "enabled": False,
                        }
                    }
                },
            },
        ]
    }
    out = _run(tables)
    assert "school.example" not in json.dumps(out)
    assert "realorg.example" not in json.dumps(out)
    a = out["categories"][0]["authentication"]
    assert a["ldap"]["email_domain_restriction"]["allowed"] == ["example.test"]
    assert a["saml"]["email_domain_restriction"]["allowed"] == ["example.test"]
    assert a["ldap"]["email_domain_restriction"]["enabled"] is True  # flag kept
    d = out["categories"][1]["authentication"]["ldap"]["email_domain_restriction"]
    assert d["allowed"] == ["example.test"]
