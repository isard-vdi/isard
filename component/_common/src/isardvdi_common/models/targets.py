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
import traceback
import uuid
from uuid import uuid4

import grpc
from isardvdi_common.connections.rethink_custom_base_factory import RethinkCustomBase
from isardvdi_common.helpers.bastion import Bastion
from isardvdi_common.helpers.error_factory import Error
from isardvdi_common.helpers.helpers import Helpers
from isardvdi_protobuf.haproxy_sync.v1 import haproxy_sync_pb2
from pydantic import BaseModel, Field
from pydantic.experimental.missing_sentinel import MISSING
from rethinkdb import r

from ..schemas.targets import Http, Ssh

try:
    from api import app as _flask_api

    haproxy_bastion_client = _flask_api.haproxy_bastion_client
except (ImportError, AttributeError):
    # Non-Flask context or Flask app not initialized yet — create a
    # fresh gRPC client.
    from isardvdi_common.connections.grpc_client import create_haproxy_bastion_client

    # See helpers/bastion.py for rationale: 1312 is the gRPC default that
    # haproxy-sync listens on; 1313 is the HTTP port used by other services.
    haproxy_bastion_client = create_haproxy_bastion_client("isard-portal", 1312)


class TargetModel(BaseModel):
    desktop_id: str = MISSING
    domain: str | None = None
    domains: list[str] = []
    http: Http = Http()
    id: str = Field(default_factory=lambda: str(uuid4()))
    ssh: Ssh = Ssh()
    user_id: str = MISSING


class Targets(RethinkCustomBase):

    @classmethod
    def get_domain_target(cls, domain_id, conn_type=None):
        with cls._rdb_context():
            target = list(
                r.table("targets")
                .get_all(domain_id, index="desktop_id")
                .run(cls._rdb_connection)
            )

        if not target:
            raise Error(
                "not_found",
                "Target not found",
                traceback.format_exc(),
            )

        if conn_type:
            return target[0][conn_type]

        return target[0]

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
                "domain": None,
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
            target["http"] = data["http"]
        if data.get("ssh"):
            target["ssh"] = data["ssh"]
        if "domain" in data:
            if data["domain"] == target.get("domain"):
                pass
            elif not data["domain"]:
                if target.get("domain"):
                    haproxy_bastion_client.BastionDeleteIndividualDomain(
                        haproxy_sync_pb2.BastionDeleteIndividualDomainRequest(
                            domain=target["domain"]
                        )
                    )
                target["domain"] = None
            else:
                if Bastion.bastion_domain_verification_required():
                    with cls._rdb_context():
                        dom_row = (
                            r.table("domains")
                            .get(domain_id)
                            .default(None)
                            .run(cls._rdb_connection)
                        )
                    category_id = (dom_row or {}).get("category")
                    Bastion.check_bastion_domain_dns(
                        data["domain"],
                        f"{target['id']}.{Bastion.get_bastion_domain(category_id)}",
                        kind="cname",
                    )

                if target.get("domain"):
                    haproxy_bastion_client.BastionDeleteIndividualDomain(
                        haproxy_sync_pb2.BastionDeleteIndividualDomainRequest(
                            domain=target["domain"]
                        )
                    )

                target["domain"] = data["domain"]

                haproxy_bastion_client.BastionAddIndividualDomain(
                    haproxy_sync_pb2.BastionAddIndividualDomainRequest(
                        domain=data["domain"]
                    )
                )

        if "domains" in data:
            new_domains = [
                d.strip() for d in (data["domains"] or []) if d and d.strip()
            ]
            old_domains = [d for d in target.get("domains", []) if d]

            if len(new_domains) > 10:
                raise Error(
                    "bad_request",
                    "Maximum 10 domains allowed per target",
                )

            if Bastion.bastion_domain_verification_required():
                with cls._rdb_context():
                    dom_row = (
                        r.table("domains")
                        .get(domain_id)
                        .default(None)
                        .run(cls._rdb_connection)
                    )
                category_id = (dom_row or {}).get("category")
                for d in new_domains:
                    if d and d not in old_domains:
                        Bastion.check_bastion_domain_dns(
                            d,
                            f"{target['id']}.{Bastion.get_bastion_domain(category_id)}",
                            kind="cname",
                        )

            domains_to_add = set(new_domains) - set(old_domains)
            domains_to_remove = set(old_domains) - set(new_domains)

            for d in domains_to_remove:
                haproxy_bastion_client.BastionDeleteIndividualDomain(
                    haproxy_sync_pb2.BastionDeleteIndividualDomainRequest(domain=d)
                )
            for d in domains_to_add:
                haproxy_bastion_client.BastionAddIndividualDomain(
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
