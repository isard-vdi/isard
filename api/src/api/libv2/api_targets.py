import threading
import time
import traceback
import uuid
from typing import Literal

import dns.resolver
import grpc
from haproxy.v1 import haproxy_pb2
from isardvdi_common.api_exceptions import Error
from rethinkdb import RethinkDB

from api import app

from ..views.decorators import can_use_bastion
from .caches import get_document, invalidate_cache
from .flask_rethink import RDB

r = RethinkDB()

db = RDB(app)
db.init_app(app)


subdomains_lock = threading.Lock()
individual_lock = threading.Lock()


def bastion_enabled_in_db():
    return get_document("config", 1, ["bastion"]).get("enabled")


def get_bastion_domain(category_id: str = None) -> str:
    """
    Get bastion domain from category or config.
    If category does not have bastion domain, it will return the default
    bastion domain from config.
    """
    bastion_domain = (
        get_document("categories", category_id, ["bastion_domain"])
        if category_id
        else None
    )
    if bastion_domain is None:
        bastion_domain = get_document("config", 1, ["bastion"]).get("domain")
    return bastion_domain


def update_bastion_config(
    enabled: bool,
    domain: str,
    domain_verification_required: bool,
):
    """
    Update the bastion config.
    """
    with app.app_context():
        old_domain = (
            r.table("config").get(1).pluck("bastion").run(db.conn).get("bastion")
        ).get("domain")
    if old_domain != domain:
        if old_domain:
            app.haproxy_bastion_client.DeleteSubdomain(
                haproxy_pb2.DeleteSubdomainRequest(domain=old_domain)
            )
        app.haproxy_bastion_client.AddSubdomain(
            haproxy_pb2.AddSubdomainRequest(domain=domain)
        )

    with app.app_context():
        r.table("config").get(1).update(
            {
                "bastion": {
                    "enabled": enabled,
                    "domain": domain,
                    "domain_verification_required": domain_verification_required,
                }
            }
        ).run(db.conn)
    invalidate_cache("config", 1)


def get_category_bastion_domain(category_id: str) -> str:
    """
    Get bastion domain from category.
    """
    return get_document("categories", category_id, ["bastion_domain"])


def update_category_bastion_domain(category_id, domain):
    with app.app_context():
        old_domain = (
            r.table("categories").get(category_id).pluck("bastion_domain").run(db.conn)
        ).get("bastion_domain")
    if old_domain == domain:
        return

    with app.app_context():
        r.table("categories").get(category_id).update({"bastion_domain": domain}).run(
            db.conn
        )
    invalidate_cache("categories", category_id)

    if old_domain:
        app.haproxy_bastion_client.DeleteSubdomain(
            haproxy_pb2.DeleteSubdomainRequest(domain=old_domain)
        )
    app.haproxy_bastion_client.AddSubdomain(
        haproxy_pb2.AddSubdomainRequest(domain=domain)
    )


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
                    app.logger.error(
                        f"gRPC service unavailable after {max_retries} attempts, giving up"
                    )
                    raise
                app.logger.warning(
                    f"gRPC service unavailable, retrying in {delay}s... (attempt {attempt}/{max_retries}) ({e.details()})"
                )
                time.sleep(delay)
                delay = min(delay * 2, max_delay)  # Exponential backoff, capped at 30s
                continue
            # For other errors, re-raise
            raise

    # If we exhausted all retries
    raise grpc.RpcError(f"Failed after {max_retries} attempts")


def update_bastion_haproxy_map():
    """
    Update the bastion domain map for haproxy.
    """
    with subdomains_lock:
        subdomains = []
        with app.app_context():
            subdomains.append(
                r.table("config")
                .get(1)
                .pluck("bastion")
                .run(db.conn)["bastion"]["domain"]
            )

        with app.app_context():
            category_domains = list(
                r.table("categories")
                .pluck("bastion_domain")["bastion_domain"]
                .run(db.conn)
            )
        category_domains = [
            domain for domain in category_domains if isinstance(domain, str)
        ]
        subdomains.extend(category_domains)

        with app.app_context():
            # Use indexed distinct for O(log n) performance instead of full table scan
            individual_domains = list(
                r.table("targets").distinct(index="domains").run(db.conn)
            )
            # Filter out any None/empty values that might be in the index
            individual_domains = [d for d in individual_domains if d]

        _call_grpc_with_infinite_retry(
            app.haproxy_bastion_client.SyncMaps,
            haproxy_pb2.SyncMapsRequest(
                subdomains=subdomains,
                individual_domains=individual_domains,
            ),
        )


def bastion_domain_verification_required() -> bool:
    """
    Get if bastion domain verification is required.
    """
    return get_document("config", 1, ["bastion"]).get(
        "domain_verification_required", True
    )


def check_bastion_domain_dns(
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


class ApiTargets:
    def __init__(self) -> None:
        pass

    def get_domain_target(self, domain_id, conn_type=None):
        with app.app_context():
            target = list(
                r.table("targets").get_all(domain_id, index="desktop_id").run(db.conn)
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

    def update_domain_target(self, domain_id, data={}):
        try:
            target = self.get_domain_target(domain_id)
        except:
            with app.app_context():
                user_id = (
                    r.table("domains").get(domain_id).pluck("user").run(db.conn)["user"]
                )
            target = {
                "id": str(uuid.uuid4()),
                "desktop_id": domain_id,
                "user_id": user_id,
                "domains": [],
            }
            target["http"] = {
                "enabled": False,
                "http_port": 80,
                "https_port": 443,
                "proxy_protocol": False,
            }
            target["ssh"] = {"enabled": False, "port": 22, "authorized_keys": []}

            with app.app_context():
                r.db("isard").table("targets").insert(target).run(db.conn)

        if data.get("http"):
            target["http"] = data["http"]
        if data.get("ssh"):
            target["ssh"] = data["ssh"]
        if "domains" in data:
            # Filter out empty/whitespace-only strings
            new_domains = [
                d.strip() for d in (data["domains"] or []) if d and d.strip()
            ]
            old_domains = [d for d in target.get("domains", []) if d]

            # Validate max 10 domains
            if len(new_domains) > 10:
                raise Error(
                    "bad_request",
                    "Maximum 10 domains allowed per target",
                    traceback.format_exc(),
                )

            # DNS verification for all new domains
            if bastion_domain_verification_required():
                with app.app_context():
                    category_id = (
                        r.table("domains")
                        .get(domain_id)
                        .pluck("category")
                        .run(db.conn)["category"]
                    )
                for domain in new_domains:
                    if domain and domain not in old_domains:
                        check_bastion_domain_dns(
                            domain,
                            f"{target['id']}.{get_bastion_domain(category_id)}",
                            kind="cname",
                        )

            # Calculate domains to add/remove
            domains_to_add = set(new_domains) - set(old_domains)
            domains_to_remove = set(old_domains) - set(new_domains)

            # Update HAProxy
            for domain in domains_to_remove:
                app.haproxy_bastion_client.DeleteIndividualDomain(
                    haproxy_pb2.DeleteIndividualDomainRequest(domain=domain)
                )

            for domain in domains_to_add:
                app.haproxy_bastion_client.AddIndividualDomain(
                    haproxy_pb2.AddIndividualDomainRequest(domain=domain)
                )

            target["domains"] = new_domains

        with app.app_context():
            r.db("isard").table("targets").get(target["id"]).update(target).run(db.conn)

        return target

    def delete_domain_target(self, domain_id: str):
        with app.app_context():
            r.table("targets").get_all(domain_id, index="desktop_id").delete().run(
                db.conn
            )

    def bulk_delete_domain_targets(self, domain_ids: list):
        with app.app_context():
            r.table("targets").get_all(
                r.args(domain_ids), index="desktop_id"
            ).delete().run(db.conn)

    def get_user_targets(self, user_id):
        with app.app_context():
            return list(
                r.table("targets").get_all(user_id, index="user_id").run(db.conn)
            )

    def change_desktops_target_owner(self, domain_ids, new_user_payload):
        if can_use_bastion(new_user_payload) == True:
            with app.app_context():
                r.table("targets").get_all(
                    r.args(domain_ids), index="desktop_id"
                ).update({"user_id": new_user_payload["user_id"]}).run(db.conn)
        else:
            self.bulk_delete_domain_targets(domain_ids)
