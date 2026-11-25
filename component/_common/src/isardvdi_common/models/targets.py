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


import time
import uuid
from uuid import uuid4

import grpc
from isardvdi_common.connections.rethink_custom_base_factory import RethinkCustomBase
from isardvdi_common.helpers.bastion import Bastion, _haproxy_bastion_client
from isardvdi_common.helpers.error_factory import Error
from isardvdi_common.helpers.helpers import Helpers
from isardvdi_common.helpers.host_name import normalize_host_name
from isardvdi_protobuf.haproxy_sync.v1 import haproxy_sync_pb2
from pydantic import BaseModel, Field
from pydantic.experimental.missing_sentinel import MISSING
from rethinkdb import r

from ..schemas.targets import Http, Ssh

# The haproxy-sync gRPC stub is provided by the same hook that powers
# ``Bastion`` — see ``isardvdi_common.helpers.bastion._haproxy_bastion_client``.
# Deliberately importing the private getter rather than duplicating the
# provider state here so there's a single registration point and one
# source of truth for the haproxy-sync channel. apiv4's lifespan startup
# calls ``configure_haproxy_bastion_client(provider)`` once on the
# ``bastion`` module; this module picks up the same provider via the
# shared getter.


class TargetModel(BaseModel):
    desktop_id: str = MISSING
    domains: list[str] = []
    http: Http = Http()
    id: str = Field(default_factory=lambda: str(uuid4()))
    ssh: Ssh = Ssh()
    user_id: str = MISSING


class Targets(RethinkCustomBase):
    @classmethod
    def find_domain_target(cls, domain_id):
        """Return the target row for ``domain_id`` or ``None`` — never raises.

        Callers that must react to a missing target (the recycle-bin add
        paths) use this; only ``get_domain_target`` raises, for the HTTP
        endpoints where a 404 is the correct response.
        """
        with cls._rdb_context():
            target = list(
                r.table("targets")
                .get_all(domain_id, index="desktop_id")
                .run(cls._rdb_connection)
            )
        return target[0] if target else None

    @classmethod
    def get_domain_target(cls, domain_id, conn_type=None):
        target = cls.find_domain_target(domain_id)
        if not target:
            raise Error(
                "not_found",
                "Target not found",
                description_code="target_not_found",
            )
        if conn_type:
            return target[conn_type]
        return target

    @staticmethod
    def normalize_domains(domains: list[str] | None) -> list[str]:
        """Return the ASCII form of the non-blank ``domains``."""
        try:
            return [
                normalize_host_name(d.strip()) for d in domains or [] if d and d.strip()
            ]
        except ValueError as e:
            raise Error(
                "bad_request",
                str(e),
                description_code="bastion_domain_invalid",
            )

    @classmethod
    def verify_new_domains(
        cls, domain_id: str, target: dict, domains: list[str]
    ) -> None:
        """Check the DNS of the ``domains`` not stored on ``target`` yet, if required."""
        stored = target.get("domains") or []
        new_domains = [d for d in domains if d not in stored]
        if not new_domains or not Bastion.bastion_domain_verification_required():
            return
        with cls._rdb_context():
            dom_row = (
                r.table("domains").get(domain_id).default(None).run(cls._rdb_connection)
            )
        bastion_domain = Bastion.get_bastion_domain((dom_row or {}).get("category"))
        for d in new_domains:
            Bastion.check_bastion_domain_dns(
                d, f"{target['id']}.{bastion_domain}", kind="cname"
            )

    @classmethod
    def update_domain_target(cls, domain_id, data={}):
        try:
            target = cls.get_domain_target(domain_id)
        except Error as e:
            # Only the "target not yet created" case should fall through
            # to the new-target construction below; any other typed
            # error (forbidden, conflict, ...) must propagate.
            if e.status_code != 404:
                raise
            with cls._rdb_context():
                domain = (
                    r.table("domains")
                    .get(domain_id)
                    .default(None)
                    .run(cls._rdb_connection)
                )
            if domain is None:
                raise Error(
                    "not_found",
                    f"Domain {domain_id} not found",
                    description_code="domain_not_found",
                )
            user_id = domain.get("user")
            target = {
                "id": str(uuid.uuid4()),
                "desktop_id": domain_id,
                "user_id": user_id,
                "domains": [],
            }
            target["http"] = {"enabled": False, "http_port": 80, "https_port": 443}
            target["ssh"] = {"enabled": False, "port": 22, "authorized_keys": []}

            valid_target = TargetModel(**target).model_dump(exclude_unset=False)
            with cls._rdb_context():
                r.db("isard").table("targets").insert(valid_target).run(
                    cls._rdb_connection
                )

        if data.get("http"):
            target["http"] = {**(target.get("http") or {}), **data["http"]}
        if data.get("ssh"):
            target["ssh"] = {**(target.get("ssh") or {}), **data["ssh"]}
        if "domains" in data:
            new_domains = cls.normalize_domains(data["domains"])
            old_domains = [d for d in target.get("domains", []) if d]

            if len(new_domains) > 10:
                raise Error(
                    "bad_request",
                    "Maximum 10 domains allowed per target",
                )

            cls.verify_new_domains(domain_id, target, new_domains)

            domains_to_add = set(new_domains) - set(old_domains)
            domains_to_remove = set(old_domains) - set(new_domains)

            for d in domains_to_remove:
                _haproxy_bastion_client().BastionDeleteIndividualDomain(
                    haproxy_sync_pb2.BastionDeleteIndividualDomainRequest(domain=d)
                )
            for d in domains_to_add:
                _haproxy_bastion_client().BastionAddIndividualDomain(
                    haproxy_sync_pb2.BastionAddIndividualDomainRequest(domain=d)
                )

            target["domains"] = new_domains

        valid_target = TargetModel(**target).model_dump(exclude_unset=True)

        with cls._rdb_context():
            r.db("isard").table("targets").get(target["id"]).update(valid_target).run(
                cls._rdb_connection
            )

        return target

    @classmethod
    def delete_domain_target(cls, domain_id: str):
        with cls._rdb_context():
            r.table("targets").get_all(domain_id, index="desktop_id").delete().run(
                cls._rdb_connection
            )

    @classmethod
    def find_domains_targets(cls, domain_ids: list) -> list[dict]:
        """Return the target rows of ``domain_ids``; never raises, may be empty."""
        with cls._rdb_context():
            return list(
                r.table("targets")
                .get_all(r.args(domain_ids), index="desktop_id")
                .run(cls._rdb_connection)
            )

    @classmethod
    def bulk_delete_domain_targets(cls, domain_ids: list):
        with cls._rdb_context():
            r.table("targets").get_all(
                r.args(domain_ids), index="desktop_id"
            ).delete().run(cls._rdb_connection)

    @classmethod
    def get_user_targets(cls, user_id):
        with cls._rdb_context():
            return list(
                r.table("targets")
                .get_all(user_id, index="user_id")
                .run(cls._rdb_connection)
            )

    @classmethod
    def change_desktops_target_owner(cls, domain_ids, new_user_payload):
        if Helpers.can_use_bastion(new_user_payload) == True:
            with cls._rdb_context():
                r.table("targets").get_all(
                    r.args(domain_ids), index="desktop_id"
                ).update({"user_id": new_user_payload["user_id"]}).run(
                    cls._rdb_connection
                )
        else:
            cls.bulk_delete_domain_targets(domain_ids)
