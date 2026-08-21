"""Scrubbing + cross-table consistency tests for anonymize-db.

Mirrors the cli `_scrub_dir` pipeline (defensive_sweep -> per-table scrubber ->
final cross_table_rewrite pass) on an in-memory set of tables shaped like a real
IsardVDI rethinkdb dump, and asserts that:
  * human/PII content is gone, and
  * every value that is denormalized across tables receives the SAME replacement.
"""

from __future__ import annotations

import json
import re

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


REAL_MAC = "52:54:00:aa:bb:cc"
OTHER_MAC = "52:54:00:dd:ee:ff"


def test_macs_replaced_consistently_in_every_place_they_appear():
    tables = {
        "domains": [
            {
                "id": "d1234567-aaaa",
                "user": "u1234567-bbbb",
                "hardware": {"interfaces": [{"id": "default", "mac": REAL_MAC}]},
                "create_dict": {
                    "hardware": {"interfaces": [{"id": "default", "mac": REAL_MAC}]}
                },
                "xml": (
                    "<domain><devices><interface type='bridge'>"
                    f"<mac address='{REAL_MAC}'/></interface></devices></domain>"
                ),
            },
            {
                "id": "d7654321-cccc",
                "user": "u1234567-bbbb",
                "hardware": {"interfaces": [{"mac": OTHER_MAC}]},
            },
        ]
    }
    out = _run(tables)

    blob = json.dumps(out)
    assert REAL_MAC not in blob, "real MAC survived"
    assert OTHER_MAC not in blob, "real MAC survived"

    d1 = out["domains"][0]
    hw_mac = d1["hardware"]["interfaces"][0]["mac"]
    cd_mac = d1["create_dict"]["hardware"]["interfaces"][0]["mac"]
    xml_mac = re.search(r"<mac address='([^']+)'", d1["xml"]).group(1)

    assert hw_mac.startswith("02:")
    # one interface described in three places must get ONE replacement, or a
    # restored dev database contradicts itself
    assert hw_mac == cd_mac == xml_mac

    assert out["domains"][1]["hardware"]["interfaces"][0]["mac"] != hw_mac


def test_macs_stay_unique_when_scrubbed_one_document_at_a_time():
    """The cli streams each table document by document (`fn([doc])`), so a
    scrubber must never derive a value from the row's index within its batch —
    that index is always 0 there."""
    s = Scrubber(seed=0)
    fn = get_scrubbers(s)["domains"]
    docs = [
        {
            "id": f"d{i}aaaaaa-0000",
            "user": "u1234567-bbbb",
            "create_dict": {
                "hardware": {"interfaces": [{"mac": f"52:54:00:00:00:{i:02x}"}]}
            },
        }
        for i in range(5)
    ]
    scrubbed = [fn([d])[0] for d in docs]
    macs = {d["create_dict"]["hardware"]["interfaces"][0]["mac"] for d in scrubbed}
    assert len(macs) == 5, f"domains collided onto the same MAC: {sorted(macs)}"


def test_targets_bastion_domains_scrubbed():
    tables = {
        "targets": [
            {
                "id": "t1234567-aaaa",
                "desktop_id": "d1234567-bbbb",
                "user_id": "u1234567-cccc",
                "domains": [
                    "maria-desktop.bastion.realcorp.example",
                    "finance-lab.bastion.realcorp.example",
                ],
                "http": {"enabled": True, "http_port": 80, "https_port": 443},
                "ssh": {"authorized_keys": ["ssh-ed25519 AAAA t@realcorp.example"]},
            }
        ]
    }
    out = _run(tables)
    t = out["targets"][0]

    assert "realcorp.example" not in json.dumps(out)
    assert len(t["domains"]) == 2
    for d in t["domains"]:
        assert d.endswith(".example.test")
    # FKs and non-identity config untouched
    assert t["desktop_id"] == "d1234567-bbbb"
    assert t["user_id"] == "u1234567-cccc"
    assert t["http"] == {"enabled": True, "http_port": 80, "https_port": 443}
    assert t["ssh"]["authorized_keys"] == []


def test_user_storage_provider_table_scrubbed():
    tables = {
        "user_storage": [
            {
                "id": "prov1234-aaaa",
                "provider": "nextcloud",
                "urlprefix": "https://nextcloud.realcorp.example",
                "user": "isard-admin",
                "password": "real-provider-secret",
                "verify_cert": True,
            }
        ]
    }
    out = _run(tables)
    p = out["user_storage"][0]

    blob = json.dumps(out)
    assert "nextcloud.realcorp.example" not in blob
    assert "real-provider-secret" not in blob
    assert "isard-admin" not in blob

    assert p["urlprefix"] == "https://storage-prov1234.example.test"
    assert p["user"] == "storage-admin"
    assert p["provider"] == "nextcloud"  # product name, not identity
    assert p["verify_cert"] is True


def _integrity_fixture() -> dict[str, list[dict]]:
    """A dump shaped so every documented relation has at least one live edge."""
    user_id = "u1234567-aaaa-bbbb-cccc-000000000001"
    dep_id = "p1234567-aaaa-bbbb-cccc-000000000002"
    dom_a = "d1234567-aaaa-bbbb-cccc-000000000003"
    dom_b = "d7654321-aaaa-bbbb-cccc-000000000004"
    return {
        "users": [
            {
                "id": user_id,
                "name": "Real Person",
                "username": "real.person@realcorp.example",
                "email": "real.person@realcorp.example",
                "password": "$2b$realhash",
            }
        ],
        "deployments": [
            {"id": dep_id, "name": "Real Lab", "tag": dep_id, "tag_name": "Real Lab"}
        ],
        "domains": [
            {
                "id": dom_a,
                "user": user_id,
                "username": "real.person@realcorp.example",
                "name": "Real Desktop A",
                "tag": dep_id,
                "tag_name": "Real Lab",
            },
            {
                "id": dom_b,
                "user": user_id,
                "username": "real.person@realcorp.example",
                "name": "Real Desktop B",
                "tag": dep_id,
                "tag_name": "Real Lab",
            },
        ],
        "logs_desktops": [
            {
                "id": "ld1",
                "desktop_id": dom_a,
                "desktop_name": "Real Desktop A",
                "deployment_id": dep_id,
                "deployment_name": "Real Lab",
                "owner_user_id": user_id,
                "owner_user_name": "real.person@realcorp.example",
                "hyp_started": "isard-hypervisor-real-hyp01",
            },
            {
                "id": "ld2",
                "desktop_id": dom_b,
                "desktop_name": "Real Desktop B",
                "deployment_id": dep_id,
                "deployment_name": "Real Lab",
                "owner_user_id": user_id,
                "owner_user_name": "real.person@realcorp.example",
                "hyp_started": "isard-hypervisor-real-hyp02",
            },
        ],
    }


def test_referential_integrity_preserved():
    before = _integrity_fixture()
    hyp_cardinality_before = len(
        {r["hyp_started"] for r in before["logs_desktops"] if r["hyp_started"]}
    )
    out = _run(_integrity_fixture())

    user_ids = {u["id"] for u in out["users"]}
    deployment_ids = {d["id"] for d in out["deployments"]}
    domain_ids = {d["id"] for d in out["domains"]}

    assert len(out["domains"]) == 2
    for d in out["domains"]:
        assert d["user"] in user_ids, "domains.user no longer resolves"
        assert d["tag"] in deployment_ids, "domains.tag no longer resolves"

    for row in out["logs_desktops"]:
        assert row["desktop_id"] in domain_ids
        assert row["deployment_id"] in deployment_ids
        assert row["owner_user_id"] in user_ids

    hyp_cardinality_after = len(
        {r["hyp_started"] for r in out["logs_desktops"] if r["hyp_started"]}
    )
    assert hyp_cardinality_after == hyp_cardinality_before


def test_integrity_fixture_has_no_surviving_pii():
    out = _run(_integrity_fixture())
    blob = json.dumps(out)
    for needle in (
        "Real Person",
        "real.person@realcorp.example",
        "Real Lab",
        "Real Desktop A",
        "Real Desktop B",
        "isard-hypervisor-real-hyp01",
        "isard-hypervisor-real-hyp02",
    ):
        assert needle not in blob, f"PII leaked: {needle!r}"


def test_recycle_bin_matcher_is_anchored():
    tables = {
        "recycle_bin": [
            {
                "id": "rb1",
                "item": {
                    "name": "Real Desktop",
                    "owner_user_name": "mgonzalez@realcorp.example",
                    "guest_ip": "10.9.8.7",
                    "uid": "jdoe@school.example",
                    # non-identity keys that the substring matcher destroyed
                    "chipset": "q35",
                    "clipboard": "enabled",
                    "description": "a note",
                    "interface_names": ["default", "wireguard"],
                    "authorized_keys": ["ssh-ed25519 AAAA teacher@school.example"],
                },
            }
        ]
    }
    out = _run(tables)
    item = out["recycle_bin"][0]["item"]

    blob = json.dumps(out)
    for needle in (
        "Real Desktop",
        "mgonzalez@realcorp.example",
        "10.9.8.7",
        "jdoe@school.example",
        "teacher@school.example",
    ):
        assert needle not in blob, f"leaked: {needle!r}"

    assert item["name"] == ""
    assert item["owner_user_name"] == ""
    assert item["guest_ip"] == ""
    assert item["uid"] == ""
    assert item["description"] == ""
    assert item["authorized_keys"] == []
    # structure that carries no identity survives
    assert item["chipset"] == "q35"
    assert item["clipboard"] == "enabled"
    assert item["interface_names"] == ["default", "wireguard"]


def test_hypervisor_ids_aliased_not_blanked():
    tables = {
        "logs_desktops": [
            {"id": "l1", "hyp_started": "isard-hypervisor-gencat-hyp03"},
            {"id": "l2", "hyp_started": "isard-hypervisor-gencat-hyp03"},
            {"id": "l3", "hyp_started": "isard-hypervisor-gencat-hyp07"},
            {"id": "l4", "hyp_started": False, "hyp_forced": "bastion-hyp01"},
        ]
    }
    out = _run(tables)

    blob = json.dumps(out)
    assert "isard-hypervisor-gencat-hyp03" not in blob
    assert "isard-hypervisor-gencat-hyp07" not in blob
    assert "bastion-hyp01" not in blob

    rows = out["logs_desktops"]
    # same source hypervisor -> same alias; grouping survives
    assert rows[0]["hyp_started"] == rows[1]["hyp_started"]
    assert rows[0]["hyp_started"] != rows[2]["hyp_started"]
    assert rows[0]["hyp_started"].startswith("hyp-")
    # cardinality of the dimension is unchanged
    assert len({r["hyp_started"] for r in rows if r["hyp_started"]}) == 2
    # non-string values pass through untouched
    assert rows[3]["hyp_started"] is False
    assert rows[3]["hyp_forced"].startswith("hyp-")


def test_log_names_rebuilt_from_fks():
    tables = {
        "logs_users": [
            {
                "id": "lu1",
                "owner_user_id": "u1234567-aaaa-bbbb",
                "owner_user_name": "mgonzalez@realcorp.example",
                "owner_category_id": "acme",
                "owner_category_name": "Acme Corporation",
                "owner_group_id": "g1234567890abcdef",
                "owner_group_name": "Finance Department",
                "request_ip": "10.1.2.3",
                "request_agent_browser": "Firefox",
                "request_agent_platform": "Linux",
                "request_agent_version": "141.0.7390.55",
            }
        ],
        "logs_desktops": [
            {
                "id": "ld1",
                "desktop_id": "d1234567-cccc-dddd",
                "desktop_name": "Maria's Finance Desktop",
                "deployment_id": "p1234567-eeee-ffff",
                "deployment_name": "Finance Lab 2026",
                "owner_user_id": "u1234567-aaaa-bbbb",
                "owner_user_name": "mgonzalez@realcorp.example",
            }
        ],
    }
    out = _run(tables)

    blob = json.dumps(out)
    for needle in (
        "mgonzalez@realcorp.example",
        "Acme Corporation",
        "Finance Department",
        "Maria's Finance Desktop",
        "Finance Lab 2026",
        "10.1.2.3",
        "141.0.7390.55",
    ):
        assert needle not in blob, f"leaked: {needle!r}"

    lu = out["logs_users"][0]
    assert lu["owner_user_name"] == "user-u1234567"
    assert lu["owner_category_name"] == "category-acme"
    assert lu["owner_group_name"] == "group-g1234567890a"
    assert lu["owner_user_id"] == "u1234567-aaaa-bbbb"
    assert lu["request_ip"] == ""
    # The whole request fingerprint goes, not part of it: logs_desktops has
    # always dropped the agent version too, and logs_users started receiving
    # it once the request-capture path was restored.
    assert lu["request_agent_browser"] == ""
    assert lu["request_agent_platform"] == ""
    assert lu["request_agent_version"] == ""

    ld = out["logs_desktops"][0]
    assert ld["desktop_name"] == "desktop-d1234567"
    assert ld["deployment_name"] == "deployment-p1234567"
    assert ld["owner_user_name"] == "user-u1234567"


def test_log_names_blank_when_fk_missing():
    tables = {
        "logs_desktops": [
            {"id": "ld1", "desktop_name": "Orphan Desktop", "desktop_id": None}
        ]
    }
    out = _run(tables)
    assert out["logs_desktops"][0]["desktop_name"] == ""


DEPLOYMENT_ID = "eeeeeeee-1111-2222-3333-555555555555"


def test_deployment_tag_fk_preserved():
    tables = {
        "deployments": [
            {
                "id": DEPLOYMENT_ID,
                "name": "Finance Lab 2026",
                "description": "for the finance dept",
                "tag": DEPLOYMENT_ID,
                "tag_name": "Finance Lab 2026",
                "create_dict": {
                    "name": "Finance Lab 2026",
                    "description": "for the finance dept",
                    "tag": DEPLOYMENT_ID,
                },
            }
        ],
        "domains": [
            {
                "id": "d1aaaaaa-0000",
                "user": "u1aaaaaa-0000",
                "tag": DEPLOYMENT_ID,
                "tag_name": "Finance Lab 2026",
            },
            {
                "id": "d2bbbbbb-0000",
                "user": "u1aaaaaa-0000",
                "tag": DEPLOYMENT_ID,
                "tag_name": "Finance Lab 2026",
            },
            {"id": "d3cccccc-0000", "user": "u1aaaaaa-0000", "tag": False},
        ],
    }
    out = _run(tables)

    assert "Finance Lab 2026" not in json.dumps(out)

    dep = out["deployments"][0]
    assert dep["tag"] == DEPLOYMENT_ID
    assert dep["create_dict"]["tag"] == DEPLOYMENT_ID
    assert dep["name"] == f"deployment-{DEPLOYMENT_ID[:8]}"
    assert dep["tag_name"] == dep["name"]

    grouped = [d for d in out["domains"] if d["tag"]]
    assert len(grouped) == 2
    for d in grouped:
        assert d["tag"] == DEPLOYMENT_ID
        assert d["tag_name"] == f"deployment-{DEPLOYMENT_ID[:8]}"
    assert out["domains"][2]["tag"] is False


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


# --- authentication provider configs -------------------------------------
# The same three blocks live twice: globally under config.auth.<provider> and
# per category under categories[].authentication.<provider>. Field names are
# those of authentication/model/config.go, which is the authoritative shape.

REAL_LDAP_CONFIG = {
    "name": "AD Corporatiu",
    "protocol": "ldaps",
    "host": "dc01.realorg.example",
    "port": 636,
    "bind_dn": "cn=svc-isard,ou=Services,dc=realorg,dc=example",
    "password": "TheRealBindPassword",
    "base_search": "ou=Students,dc=realorg,dc=example",
    "filter": "(&(objectClass=person)(sAMAccountName=%s))",
    "field_uid": "sAMAccountName",
    "regex_category": "^(REALORG-.*)$",
    "role_list_search_base": "ou=Groups,dc=realorg,dc=example",
    "role_list_filter": "(&(objectClass=group)(member=%s))",
    "role_admin_ids": "CN=IsardAdmins,OU=Groups,DC=realorg,DC=example",
    "role_manager_ids": "CN=Teachers,OU=Groups,DC=realorg,DC=example",
    "role_advanced_ids": "",
    "role_user_ids": "CN=Students,OU=Groups,DC=realorg,DC=example",
    "role_default": "user",
    "auto_register": True,
    "save_email": True,
}
REAL_SAML_CONFIG = {
    "name": "RealOrg IdP",
    "metadata_url": "https://idp.realorg.example/idp/shibboleth",
    "metadata_file": "/keys/realorg-idp-metadata.xml",
    "entity_id": "https://isard.realorg.example/saml",
    "key_file": "/keys/realorg.key",
    "cert_file": "/keys/realorg.cert",
    "regex_category": "^realorg\\.example$",
    "role_admin_ids": "isard-admins@realorg.example",
    "logout_redirect_url": "https://realorg.example/logout",
    "field_uid": "uid",
    "role_default": "user",
}
REAL_GOOGLE_CONFIG = {
    "name": "RealOrg Workspace",
    "client_id": "1234567890-realorg.apps.googleusercontent.com",
    "client_secret": "GOCSPX-TheRealClientSecret",
}
AUTH_NEEDLES = [
    "realorg",
    "RealOrg",
    "REALORG",
    "AD Corporatiu",
    "TheRealBindPassword",
    "GOCSPX-TheRealClientSecret",
    "svc-isard",
    "IsardAdmins",
    "Teachers",
    "Students",
]


def _auth_block(source: str = "custom") -> dict:
    return {
        "ldap": {
            "disabled": False,
            "config_source": source,
            "ldap_config": json.loads(json.dumps(REAL_LDAP_CONFIG)),
        },
        "saml": {
            "disabled": False,
            "config_source": source,
            "saml_config": json.loads(json.dumps(REAL_SAML_CONFIG)),
        },
        "google": {
            "disabled": False,
            "config_source": source,
            "google_config": json.loads(json.dumps(REAL_GOOGLE_CONFIG)),
        },
    }


def _assert_provider_config_scrubbed(auth: dict) -> None:
    ldap = auth["ldap"]["ldap_config"]
    assert ldap["host"] == "ldap.example.test"
    assert ldap["bind_dn"] == "cn=anon,dc=example,dc=test"
    assert ldap["base_search"] == "dc=example,dc=test"
    assert ldap["role_list_search_base"] == "dc=example,dc=test"
    assert ldap["password"].startswith("anon-")
    assert ldap["role_admin_ids"] == ""
    assert ldap["role_manager_ids"] == ""
    assert ldap["role_user_ids"] == ""
    assert ldap["regex_category"] == ".*"
    # schema shape, not identity: kept so a dev restore exercises the same paths
    assert ldap["field_uid"] == "sAMAccountName"
    assert ldap["role_default"] == "user"
    assert ldap["auto_register"] is True
    assert ldap["port"] == 636

    saml = auth["saml"]["saml_config"]
    assert saml["metadata_url"] == "https://idp.example.test/metadata"
    assert saml["metadata_file"] == ""
    assert saml["entity_id"] == "https://isard.example.test/saml"
    assert saml["key_file"] == ""
    assert saml["cert_file"] == ""
    assert saml["logout_redirect_url"] == ""
    assert saml["role_admin_ids"] == ""
    assert saml["regex_category"] == ".*"
    assert saml["field_uid"] == "uid"

    google = auth["google"]["google_config"]
    assert "realorg" not in google["client_id"]
    assert google["client_secret"].startswith("anon-")


def test_global_auth_provider_configs_scrubbed():
    tables = {"config": [{"id": 1, "auth": _auth_block()}]}
    out = _run(tables)
    dumped = json.dumps(out)
    for needle in AUTH_NEEDLES:
        assert needle not in dumped, needle
    _assert_provider_config_scrubbed(out["config"][0]["auth"])


def test_per_category_auth_provider_configs_scrubbed():
    # A category with config_source "custom" carries its own copy of the same
    # three blocks. It must be scrubbed exactly like the global one.
    tables = {
        "categories": [
            {"id": "realorg-fp", "name": "RealOrg FP", "authentication": _auth_block()},
            # the default category early-continues; it must still be scrubbed
            {"id": "default", "authentication": _auth_block()},
        ]
    }
    out = _run(tables)
    dumped = json.dumps(out)
    for needle in AUTH_NEEDLES:
        if needle == "realorg":
            continue  # categories.id is the primary key and is preserved
        assert needle not in dumped, needle
    _assert_provider_config_scrubbed(out["categories"][0]["authentication"])
    _assert_provider_config_scrubbed(out["categories"][1]["authentication"])


def test_config_smtp_and_shared_tokens_scrubbed():
    tables = {
        "config": [
            {
                "id": 1,
                "smtp": {
                    "enabled": True,
                    "host": "smtp.realorg.example",
                    "port": 587,
                    "username": "isard@realorg.example",
                    "password": "TheRealMailPassword",
                    "from": "no-reply@realorg.example",
                    # pre-v175 names that survive the migration's deep merge
                    "server": "smtp.realorg.example",
                    "sender_address": "no-reply@realorg.example",
                    "sender_name": "RealOrg VDI",
                },
                "resources": {
                    "url": "https://repository.isardvdi.com",
                    "code": "REALCODE1234567890",
                    "private_code": "REALPRIVATECODE",
                },
                "engine": {
                    "api": {"token": "TheRealEngineToken", "web_port": 5555},
                    "grafana": {
                        "hostname": "grafana.realorg.example",
                        "url": "https://grafana.realorg.example",
                    },
                },
            }
        ]
    }
    out = _run(tables)
    dumped = json.dumps(out)
    for needle in ("realorg", "RealOrg", "TheReal", "REALCODE", "REALPRIVATECODE"):
        assert needle not in dumped, needle
    c = out["config"][0]
    assert c["smtp"]["enabled"] is False
    assert c["smtp"]["port"] == 587  # not identity
    assert c["smtp"]["server"] == "smtp.example.test"
    assert c["smtp"]["sender_address"] == "noreply@example.test"
    assert c["resources"]["code"].startswith("anon-")
    assert c["resources"]["private_code"].startswith("anon-")
    assert c["engine"]["api"]["token"].startswith("anon-")
    assert c["engine"]["api"]["web_port"] == 5555  # not identity
    assert c["engine"]["grafana"]["hostname"] == "isard-grafana"


def test_defensive_sweep_matches_composite_secret_names():
    # The sweep is the only net a newly-added field gets. A fully anchored
    # alternation misses every composite name, which is how config.engine.api.
    # token used to ship verbatim.
    tables = {
        "some_new_table": [
            {
                "id": "x",
                "smtp_password": "real",
                "bind_password": "real",
                "refresh_token": "real",
                "api_token": "real",
                "token": "real",
                "passphrase": "real",
                "ssh-private_key": "real",
                # not secrets: must survive untouched
                "password_last_updated": "2026-08-20",
                "status_code": 404,
                "description_code": "smtp_host_internal",
                "tokens_used": 12,
            }
        ]
    }
    out = _run(tables)
    row = out["some_new_table"][0]
    for k in (
        "smtp_password",
        "bind_password",
        "refresh_token",
        "api_token",
        "token",
        "passphrase",
        "ssh-private_key",
    ):
        assert row[k].startswith("anon-"), k
    assert row["password_last_updated"] == "2026-08-20"
    assert row["status_code"] == 404
    assert row["description_code"] == "smtp_host_internal"
    assert row["tokens_used"] == 12


def test_config_login_free_text_blanked():
    # The login screen is operator-authored copy: in the field the service
    # title, the notification banners and the provider descriptions name the
    # organisation and link to its own portal.
    tables = {
        "config": [
            {
                "id": 1,
                "login": {
                    "info": {"title": "RealOrg virtual desktops"},
                    "locale": {"default": "ca-ES", "hide": True},
                    "notification_form": {
                        "enabled": True,
                        "icon": "info-circle",
                        "extra_styles": "background-color: #ffffff;",
                        "title": "Sign in with your realorg.example account",
                        "description": "",
                        "button": {
                            "text": "Sign in with another account",
                            "url": "https://desktops.realorg.example/login/all",
                            "extra_styles": "color: #bf0000;",
                        },
                    },
                    "providers": {
                        "saml": {
                            "description": "Sign in with your realorg.example account",
                            "submit_text": "Identify",
                            "hide_categories_dropdown": False,
                        }
                    },
                },
                "notification_form": {
                    "title": "From 13 January only realorg.example accounts work",
                    "description": "Click Enter to migrate them.",
                },
            }
        ]
    }
    out = _run(tables)
    dumped = json.dumps(out)
    for needle in ("realorg", "RealOrg", "Identify", "another account", "migrate"):
        assert needle not in dumped, needle
    login = out["config"][0]["login"]
    assert login["info"]["title"] == ""
    assert login["notification_form"]["button"]["url"] == ""
    assert login["providers"]["saml"]["description"] == ""
    assert login["providers"]["saml"]["submit_text"] == ""
    assert out["config"][0]["notification_form"]["title"] == ""
    # presentation and flags are not identity and stay
    assert login["locale"] == {"default": "ca-ES", "hide": True}
    assert login["notification_form"]["enabled"] is True
    assert login["notification_form"]["icon"] == "info-circle"
    assert login["notification_form"]["button"]["extra_styles"] == "color: #bf0000;"
    assert login["providers"]["saml"]["hide_categories_dropdown"] is False
