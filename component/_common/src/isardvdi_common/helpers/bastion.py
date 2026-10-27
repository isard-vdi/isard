#
#   Copyright © 2025 Pau Abril Iranzo
#
#   This file is part of IsardVDI.
#
#   IsardVDI is free software: you can redistribute it and/or modify
#   it under the terms of the GNU Affero General Public License as published by
#   the Free Software Foundation, either version 3 of the License, or (at your
#   option) any later version.
#
#   IsardVDI is distributed in the hope that it will be useful, but WITHOUT ANY
#   WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS
#   FOR A PARTICULAR PURPOSE. See the GNU General Public License for more
#   details.
#
#   You should have received a copy of the GNU Affero General Public License
#   along with IsardVDI. If not, see <https://www.gnu.org/licenses/>.
#
# SPDX-License-Identifier: AGPL-3.0-or-later


import logging as log
import os
import re
import threading
import time
import traceback
from typing import Callable, Literal, Optional

import dns.resolver
import grpc
from isardvdi_common.connections.rethink_connection_factory import (
    RethinkSharedConnection,
)
from isardvdi_common.helpers.caches import Caches
from isardvdi_common.helpers.error_factory import Error
from isardvdi_protobuf.haproxy_sync.v1 import haproxy_sync_pb2
from rethinkdb import r

# Provider hook for the haproxy-sync (a.k.a. "haproxy_bastion") gRPC stub.
# apiv4's lifespan startup registers a callable that returns a long-lived
# stub (one channel per worker process). Other services that import this
# module via the shared user / target helpers don't register and don't
# call any of the methods below that exercise the stub, so the
# unconfigured state is invisible to them.
#
# This replaces a module-load-time ``create_haproxy_bastion_client(...)``
# call that opened a TCP channel for every importer of the ``_common``
# package — including services (engine, change-handler, …) that never
# need it. See ``apiv4.connections.grpc_client`` module docstring for
# the full incident analysis (the prior code path also called
# ``grpc.experimental.gevent.init_gevent()`` which SIGSEGV'd apiv4
# under load).
_haproxy_bastion_client_provider: Optional[Callable[[], object]] = None


def configure_haproxy_bastion_client(provider: Callable[[], object]) -> None:
    """Register a factory returning the haproxy-sync gRPC stub.

    Called once at service startup before any bastion / target
    operation runs. The provider is invoked each time, so callers
    typically memoize a single stub in the closure rather than
    rebuilding the channel per call.

    The same hook is consumed by ``isardvdi_common.models.targets``,
    which delegates to this module so there is one source of truth
    for the haproxy-sync channel.
    """
    global _haproxy_bastion_client_provider
    _haproxy_bastion_client_provider = provider


def _haproxy_bastion_client():
    """Return the registered haproxy-sync gRPC stub.

    Raises ``RuntimeError`` if no provider has been registered. This
    only triggers in misconfigured services; the only documented
    caller (apiv4) wires up the provider in its ``lifespan`` startup
    before any request is served.
    """
    if _haproxy_bastion_client_provider is None:
        raise RuntimeError(
            "haproxy-sync (haproxy_bastion) client not configured: call "
            "isardvdi_common.helpers.bastion.configure_haproxy_bastion_client(provider) "
            "during service startup before invoking bastion/target operations."
        )
    return _haproxy_bastion_client_provider()


# haproxy-sync wraps the raw acme.sh stdout/stderr in DomainSyncError.error.
# When ACME rejects a certificate the payload embeds a JSON object with a
# human-friendly "detail" field — see Bastion.readable_sync_error.
_ACME_DETAIL_RE = re.compile(r'"detail"\s*:\s*"((?:[^"\\]|\\.)*)"', re.DOTALL)


class Bastion(RethinkSharedConnection):
    @staticmethod
    def _call_grpc_with_infinite_retry(
        func, *args, initial_delay=1, max_delay=30, max_retries=60, **kwargs
    ):
        """
        Call a gRPC function with retry and exponential backoff.
        Retries up to max_retries times with delays capped at max_delay.
        """
        delay = initial_delay
        attempt = 0
        while attempt < max_retries:
            try:
                return func(*args, wait_for_ready=True, timeout=30, **kwargs)
            except grpc.RpcError as e:
                if e.code() == grpc.StatusCode.UNAVAILABLE:
                    attempt += 1
                    if attempt >= max_retries:
                        log.error(
                            f"gRPC service unavailable after {max_retries} attempts, giving up"
                        )
                        raise
                    log.warning(
                        f"gRPC service unavailable, retrying in {delay}s... (attempt {attempt}/{max_retries}) ({e.details()})"
                    )
                    time.sleep(delay)
                    delay = min(
                        delay * 2, max_delay
                    )  # Exponential backoff, capped at 30s
                    continue
                # For other errors, re-raise
                raise

        # If we exhausted all retries
        raise grpc.RpcError(f"Failed after {max_retries} attempts")

    @classmethod
    def bastion_enabled_in_db(cls) -> bool:
        return Caches.get_document("config", 1, ["bastion"]).get("enabled")

    @classmethod
    def get_bastion_domain(cls, category_id: str = None) -> str:
        """
        Get bastion domain from category or config.
        If category does not have bastion domain, it will return the default
        bastion domain from config.
        """
        bastion_domain = (
            Caches.get_document("categories", category_id, ["bastion_domain"])
            if category_id
            else None
        )
        if bastion_domain is None:
            bastion_domain = Caches.get_document("config", 1, ["bastion"]).get("domain")
        return bastion_domain

    @classmethod
    def update_bastion_config(
        cls,
        enabled: bool,
        domain: str,
        domain_verification_required: bool,
    ):
        """
        Update the bastion config.
        """
        with cls._rdb_context():
            old_domain = (
                r.table("config")
                .get(1)
                .pluck("bastion")
                .run(cls._rdb_connection)
                .get("bastion")
            ).get("domain")
        if old_domain != domain:
            client = _haproxy_bastion_client()
            if old_domain:
                client.BastionDeleteSubdomain(
                    haproxy_sync_pb2.BastionDeleteSubdomainRequest(domain=old_domain)
                )
            client.BastionAddSubdomain(
                haproxy_sync_pb2.BastionAddSubdomainRequest(domain=domain)
            )

        with cls._rdb_context():
            r.table("config").get(1).update(
                {
                    "bastion": {
                        "enabled": enabled,
                        "domain": domain,
                        "domain_verification_required": domain_verification_required,
                    }
                }
            ).run(cls._rdb_connection)
        Caches.invalidate_cache("config", 1)

    @classmethod
    def get_category_bastion_domain(cls, category_id: str) -> str:
        """
        Get bastion domain from category.
        """
        return Caches.get_document("categories", category_id, ["bastion_domain"])

    @classmethod
    def update_category_bastion_domain(cls, category_id, domain):
        with cls._rdb_context():
            old_domain = (
                r.table("categories")
                .get(category_id)
                .pluck("bastion_domain")
                .run(cls._rdb_connection)
            ).get("bastion_domain")
        if old_domain == domain:
            return

        with cls._rdb_context():
            r.table("categories").get(category_id).update(
                {"bastion_domain": domain}
            ).run(cls._rdb_connection)
        Caches.invalidate_cache("categories", category_id)

        client = _haproxy_bastion_client()
        if old_domain:
            client.BastionDeleteSubdomain(
                haproxy_sync_pb2.BastionDeleteSubdomainRequest(domain=old_domain)
            )
        client.BastionAddSubdomain(
            haproxy_sync_pb2.BastionAddSubdomainRequest(domain=domain)
        )

    @classmethod
    def update_bastion_haproxy_map(cls):
        """
        Update the bastion domain map for haproxy.
        """
        subdomains = []
        with cls._rdb_context():
            subdomains.append(
                r.table("config")
                .get(1)
                .pluck("bastion")
                .run(cls._rdb_connection)["bastion"]["domain"]
            )

        with cls._rdb_context():
            category_domains = list(
                r.table("categories")
                .pluck("bastion_domain")["bastion_domain"]
                .run(cls._rdb_connection)
            )
        category_domains = [
            domain for domain in category_domains if isinstance(domain, str)
        ]
        subdomains.extend(category_domains)

        with cls._rdb_context():
            targets = list(r.table("targets").pluck("domains").run(cls._rdb_connection))

        individual_domains = list(
            dict.fromkeys(
                d
                for t in targets
                for d in (t.get("domains") or [])
                if isinstance(d, str) and d
            )
        )

        cls._call_grpc_with_infinite_retry(
            _haproxy_bastion_client().BastionSyncMaps,
            haproxy_sync_pb2.BastionSyncMapsRequest(
                subdomains=subdomains,
                individual_domains=individual_domains,
            ),
        )

    @classmethod
    def sync_category_branding_domains(cls):
        """Sync category branding domains to HAProxy via DomainSync.

        Collects all categories with branding.domain.enabled == True and pushes
        them to the haproxy-sync service. Custom certificates are forwarded when
        certificate_source is "custom".

        Returns the gRPC ``DomainSyncResponse`` so callers can inspect
        ``failed_domains`` (each entry has ``domain`` + raw ``error`` strings).
        Use :meth:`readable_sync_error` to extract ACME's human-readable
        ``"detail"`` field from the wrapped error string.
        """
        with cls._rdb_context():
            categories = list(
                r.table("categories")
                .filter(
                    lambda cat: r.branch(
                        cat.has_fields({"branding": {"domain": "enabled"}}),
                        cat["branding"]["domain"]["enabled"] == True,
                        False,
                    )
                )
                .pluck(
                    {
                        "branding": {
                            "domain": [
                                "name",
                                "certificate_source",
                                "certificate_data",
                            ]
                        }
                    }
                )
                .run(cls._rdb_connection)
            )

        domains = []
        for category in categories:
            domain_branding = category.get("branding", {}).get("domain", {})
            name = domain_branding.get("name")
            if not name:
                continue
            certificate = b""
            if domain_branding.get("certificate_source") == "custom":
                cert_data = domain_branding.get("certificate_data", "")
                if cert_data:
                    certificate = (
                        cert_data.encode("utf-8")
                        if isinstance(cert_data, str)
                        else cert_data
                    )
            domains.append(
                haproxy_sync_pb2.DomainSyncDomain(name=name, certificate=certificate)
            )

        return cls._call_grpc_with_infinite_retry(
            _haproxy_bastion_client().DomainSync,
            haproxy_sync_pb2.DomainSyncRequest(domains=domains),
        )

    @staticmethod
    def readable_sync_error(raw: str) -> str:
        """Extract ACME's human-readable ``detail`` from a wrapped sync error.

        haproxy-sync returns the raw acme.sh stdout/stderr in
        ``DomainSyncError.error``. When ACME rejects a certificate the
        payload embeds a JSON object with a ``"detail"`` field (e.g.
        ``"DNS-01 challenge failed for example.com"``) — surface that
        instead of the full shell log dump. Falls back to the raw string
        when the regex doesn't match.
        """
        if not raw:
            return ""
        match = _ACME_DETAIL_RE.search(raw)
        if match:
            return match.group(1).encode("utf-8").decode("unicode_escape")
        return raw

    @classmethod
    def bastion_domain_verification_required(cls) -> bool:
        """
        Get if bastion domain verification is required.
        """
        return Caches.get_document("config", 1, ["bastion"]).get(
            "domain_verification_required", True
        )

    @classmethod
    def check_bastion_domain_dns(
        cls,
        domain: str,
        expected: str,
        kind: Literal["category", "cname"] = "category",
    ):
        try:
            match kind:
                case "category":
                    domain = f"_isardvdi-bastion-{kind}.{domain}"

                    result = dns.resolver.resolve(domain, "TXT")
                    for val in result:
                        if val.to_text().strip('"') == expected:
                            return True

                case "cname":
                    result = dns.resolver.resolve(domain, "CNAME")
                    for val in result:
                        if val.to_text().strip(".") == expected:
                            return True

                case _:
                    raise Error(
                        "bad_request",
                        f"Invalid kind for DNS check: {kind}",
                        traceback.format_exc(),
                    )

        except dns.resolver.NXDOMAIN:
            raise Error(
                "precondition_required",
                f'DNS record for "{domain}" not found. Make sure the record exists and try again in a few minutes.',
                traceback.format_exc(),
                description_code="bastion_domain_dns_not_found",
            )
        except Error as e:
            raise e
        except Exception as e:
            raise Error(
                "precondition_required",
                f"Error checking DNS record for {domain}: {str(e)}",
                traceback.format_exc(),
                description_code="bastion_domain_dns_error",
            )

        raise Error(
            "precondition_required",
            f"DNS record for {domain} does not match expected value",
            traceback.format_exc(),
            description_code="bastion_domain_dns_mismatch",
        )

    @classmethod
    def check_duplicate_bastion_domains(
        cls,
        domains: list,
        category_id: str = None,
        target_id: str = None,
    ) -> None:
        """Validate bastion domains for uniqueness and correctness.

        Ports v3 ``api/views/decorators.py::checkDuplicateBastionDomains``:

        - rejects empty or whitespace-only entries,
        - rejects the system domain and the default bastion domain,
        - rejects any domain already used by another category
          (excluding ``category_id`` if given),
        - rejects any domain already used by another desktop's bastion
          target (excluding ``target_id`` if given).
        """
        if not domains:
            return
        if not isinstance(domains, list):
            raise Error(
                "bad_request",
                "Domains must be a list",
                traceback.format_exc(),
            )

        system_domain = os.getenv("DOMAIN")
        bastion_domain = Caches.get_document("config", 1, ["bastion"]).get("domain")

        for raw in domains:
            if not raw or not isinstance(raw, str):
                raise Error(
                    "bad_request",
                    "Empty or invalid domains are not allowed in the domains list",
                    traceback.format_exc(),
                )
            domain = raw.strip()
            if not domain:
                raise Error(
                    "bad_request",
                    "Whitespace-only domains are not allowed",
                    traceback.format_exc(),
                )
            if domain == system_domain:
                raise Error(
                    "conflict",
                    "Bastion domain is the same as the default domain",
                    traceback.format_exc(),
                )
            if domain == bastion_domain:
                raise Error(
                    "conflict",
                    "Bastion domain is the same as the default domain",
                    traceback.format_exc(),
                )

            with cls._rdb_context():
                category_query = r.table("categories").get_all(
                    domain, index="bastion_domain"
                )
                if category_id:
                    category_query = category_query.filter(
                        lambda c: c["id"] != category_id
                    )
                if category_query.count().run(cls._rdb_connection) > 0:
                    raise Error(
                        "conflict",
                        f"Bastion domain '{domain}' already used by another category",
                        traceback.format_exc(),
                    )

                target_query = r.table("targets").filter(
                    lambda t: t["domains"].default([]).contains(domain)
                )
                if target_id:
                    target_query = target_query.filter(lambda t: t["id"] != target_id)
                if target_query.count().run(cls._rdb_connection) > 0:
                    raise Error(
                        "conflict",
                        f"Bastion domain '{domain}' already used by another desktop",
                        traceback.format_exc(),
                    )
