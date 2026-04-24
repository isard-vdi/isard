#
#   Copyright © 2025 IsardVDI
#
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Unit tests for :func:`api.services.admin_tables._sanitize_table_data`.

Covers the interaction between the blanket HTML sanitizer and fields that
hold machine-generated structured data (notably ``domains.xml``).
"""

from api.services.admin_tables import _sanitize_table_data

SAMPLE_LIBVIRT_XML = (
    '<domain type="kvm">'
    "<name>test-vm</name>"
    "<uuid>00000000-0000-0000-0000-000000000000</uuid>"
    '<memory unit="KiB">1048576</memory>'
    "</domain>"
)


def test_domains_xml_field_passes_through_unchanged():
    data = {"id": "dom-1", "xml": SAMPLE_LIBVIRT_XML}
    _sanitize_table_data("domains", data)
    assert data["xml"] == SAMPLE_LIBVIRT_XML


def test_domains_xml_field_preserved_even_with_script_substring():
    xml = (
        '<domain type="kvm"><name>not&lt;script&gt;</name>'
        "<description>keep &lt;b&gt;tags&lt;/b&gt;</description></domain>"
    )
    data = {"id": "dom-1", "xml": xml}
    _sanitize_table_data("domains", data)
    assert data["xml"] == xml


def test_domains_user_input_fields_still_sanitized():
    data = {
        "id": "dom-1",
        "name": "<script>alert(1)</script>clean",
        "description": "<img src=x onerror=alert(1)>hello",
    }
    _sanitize_table_data("domains", data)
    assert "<script>" not in data["name"]
    assert "alert" not in data["name"]
    assert "clean" in data["name"]
    assert "onerror" not in data["description"]
    assert "hello" in data["description"]


def test_domains_non_string_fields_untouched():
    hardware = {"memory": 1048576, "vcpus": 2}
    create_dict = {"hardware": hardware}
    data = {
        "id": "dom-1",
        "hardware": hardware,
        "create_dict": create_dict,
        "persistent": True,
    }
    _sanitize_table_data("domains", data)
    assert data["hardware"] is hardware
    assert data["create_dict"] is create_dict
    assert data["persistent"] is True


def test_notification_tmpls_body_field_sanitized():
    data = {"id": "n-1", "body": "<script>alert(1)</script>safe"}
    _sanitize_table_data("notification_tmpls", data)
    assert "<script>" not in data["body"]
    assert "safe" in data["body"]


def test_non_sensitive_table_not_sanitized():
    data = {"id": "if-1", "name": "<b>bold</b>keep"}
    _sanitize_table_data("interfaces", data)
    assert data["name"] == "<b>bold</b>keep"
