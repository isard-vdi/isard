# SPDX-License-Identifier: AGPL-3.0-or-later

"""Pins the acme-dns field numbers on the haproxy-sync messages.

Field numbers are the wire format. Renaming a protobuf field is free and
renumbering one is not: the two ends of this call are separate containers that
are not upgraded atomically, so an apiv4 sending acme_dns_password as field 6
to an haproxy-sync that reads field 6 as something else does not fail -- it
succeeds with the wrong value, and the operator sees a DNS-01 issuance that
authenticates with the subdomain as its password.

``buf breaking`` guards this too, but it compares against main on the remote,
so it only starts protecting these numbers once they are already there. Until
then a renumbering inside this branch passes every gate. This is what covers
that window, and it costs one file to keep afterwards.

The numbers themselves are not arbitrary. 4 to 7 on IssueMainDomainRequest are
the ones the previous change deliberately left free with a comment saying they
were for exactly this; 3 to 6 on DomainSyncDomain were simply never used.
"""

import pytest
from isardvdi_protobuf.haproxy_sync.v1 import haproxy_sync_pb2

_ACME_DNS_FIELDS = (
    "acme_dns_base_url",
    "acme_dns_username",
    "acme_dns_password",
    "acme_dns_subdomain",
)


def _numbers(message) -> dict:
    return {field.name: field.number for field in message.DESCRIPTOR.fields}


class TestIssueMainDomainRequest:
    def test_the_acme_dns_credentials_keep_their_numbers(self):
        assert _numbers(haproxy_sync_pb2.IssueMainDomainRequest) == {
            "names": 1,
            "acme_email": 2,
            "acme_server": 3,
            "acme_dns_base_url": 4,
            "acme_dns_username": 5,
            "acme_dns_password": 6,
            "acme_dns_subdomain": 7,
        }

    def test_all_four_credentials_are_carried(self):
        """Three of four cannot issue anything, so a message that can only
        express part of a registration is not worth having."""
        fields = _numbers(haproxy_sync_pb2.IssueMainDomainRequest)
        assert all(name in fields for name in _ACME_DNS_FIELDS)


class TestDomainSyncDomain:
    def test_the_acme_dns_credentials_keep_their_numbers(self):
        assert _numbers(haproxy_sync_pb2.DomainSyncDomain) == {
            "name": 1,
            "certificate": 2,
            "acme_dns_base_url": 3,
            "acme_dns_username": 4,
            "acme_dns_password": 5,
            "acme_dns_subdomain": 6,
        }

    def test_the_existing_fields_did_not_move(self):
        """Adding to a message is compatible; shifting what is already there is
        not, and the branding-domain path has been on the wire for releases."""
        fields = _numbers(haproxy_sync_pb2.DomainSyncDomain)
        assert fields["name"] == 1
        assert fields["certificate"] == 2


class TestBothScopes:
    @pytest.mark.parametrize(
        "message",
        [haproxy_sync_pb2.IssueMainDomainRequest, haproxy_sync_pb2.DomainSyncDomain],
    )
    def test_the_credentials_are_named_identically_on_both(self, message):
        """The main domain and a per-category branding domain need the same
        four values, and one name per value is what lets the caller build them
        the same way for either scope."""
        fields = _numbers(message)
        assert all(name in fields for name in _ACME_DNS_FIELDS)

    @pytest.mark.parametrize(
        "message",
        [haproxy_sync_pb2.IssueMainDomainRequest, haproxy_sync_pb2.DomainSyncDomain],
    )
    def test_the_credentials_default_to_empty_rather_than_absent(self, message):
        """proto3 has no presence for a bare string, so "not using acme-dns" is
        four empty strings rather than four unset fields. Every reader has to
        decide on emptiness, and this is what says so."""
        instance = message()
        assert all(getattr(instance, name) == "" for name in _ACME_DNS_FIELDS)
