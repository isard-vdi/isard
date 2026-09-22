# Copyright 2017 the Isard-vdi project authors:
#      Josep Maria Viñolas Auquer
#      Alberto Larraz Dalmases
# License: AGPLv3

import traceback

from cachetools import cached
from isardvdi_common.connections.rethink_custom_base_factory import RethinkCustomBase
from isardvdi_common.helpers.caches import Caches
from isardvdi_common.helpers.error_factory import Error
from isardvdi_common.helpers.synchronized_cache import SynchronizedTTLCache
from rethinkdb import r


class QuotasProcess(RethinkCustomBase):
    @classmethod
    @cached(
        SynchronizedTTLCache(maxsize=200, ttl=5),
        key=lambda cls, user_id: user_id,
    )
    def cached_user_domains(cls, user_id):
        with cls._rdb_context():
            return list(
                r.table("domains")
                .get_all(user_id, index="user")
                .pluck("status", "kind", "create_dict")
                .run(cls._rdb_connection)
            )

    @classmethod
    def cached_user_desktops(cls, user_id):
        return [d for d in cls.cached_user_domains(user_id) if d["kind"] == "desktop"]

    @classmethod
    def cached_user_desktops_started(cls, user_id):
        return [
            d
            for d in cls.cached_user_domains(user_id)
            if d["kind"] == "desktop" and d["status"] == "Started"
        ]

    @classmethod
    @cached(
        SynchronizedTTLCache(maxsize=200, ttl=5),
        key=lambda cls, user_id: user_id,
    )
    def cached_user_templates(cls, user_id):
        with cls._rdb_context():
            return [
                d for d in cls.cached_user_domains(user_id) if d["kind"] == "template"
            ]

    @classmethod
    @cached(
        SynchronizedTTLCache(maxsize=200, ttl=5),
        key=lambda cls, user_id: user_id,
    )
    def cached_user_isos_count(cls, user_id):
        with cls._rdb_context():
            return (
                r.table("media")
                .get_all(user_id, index="user")
                .count()
                .run(cls._rdb_connection)
            )

    @classmethod
    @cached(
        SynchronizedTTLCache(maxsize=200, ttl=5),
        key=lambda cls, user_id: user_id,
    )
    def cached_user_deployments_ids(cls, user_id):
        with cls._rdb_context():
            return list(
                r.table("deployments")
                .get_all(user_id, index="user")
                .pluck("id")["id"]
                .run(cls._rdb_connection)
            )

    # ──────────────────────────────────────────────────────────────────────

    @classmethod
    @cached(
        SynchronizedTTLCache(maxsize=50, ttl=10),
        key=lambda cls, user_id, category_id, role_id: user_id,
    )
    def get(cls, user_id, category_id, role_id):
        # Used only in webapp as information
        userquotas = {}
        userquotas["user"] = cls.process_user_quota(user_id)
        if role_id == "manager":
            userquotas["limits"] = (
                cls.process_category_limits(category_id)
                if cls.process_category_limits(category_id)
                else cls.get_manager_usage(category_id)
            )
        if role_id == "admin":
            userquotas["global"] = cls.get_admin_usage()

        return userquotas

    @classmethod
    def process_user_quota(cls, user_id):
        user = Caches.get_document("users", user_id)

        desktops = len(cls.cached_user_desktops(user_id))
        if user["role"] == "user":
            templates = 0
            isos = 0
        else:
            templates = len(cls.cached_user_templates(user_id))
            isos = cls.cached_user_isos_count(user_id)

        starteds = {
            "count": len(cls.cached_user_desktops_started(user_id)),
            "vcpus": sum(
                domain["create_dict"]["hardware"]["vcpus"]
                for domain in cls.cached_user_desktops_started(user_id)
            ),
            "memory": sum(
                domain["create_dict"]["hardware"]["memory"]
                for domain in cls.cached_user_desktops_started(user_id)
            ),
        }

        deployments_ids = cls.cached_user_deployments_ids(user_id)
        deployments = len(deployments_ids)
        deployment_desktops = 0

        ## Not used in webapp yet
        # with cls._rdb_context():
        #     started_deployment_desktops_starting_by = (
        #         r.table("domains")
        #         .get_all(r.args(deployments_ids), index="tag")
        #         .filter(
        #             lambda desktop: r.expr(
        #                 [
        #                     "Started",
        #                     "Starting",
        #                     "StartingPaused",
        #                     "CreatingAndStarting",
        #                     "Shutting-down",
        #                 ]
        #             ).contains(desktop["status"])
        #         )
        #         .eq_join("start_logs_id", r.table("logs_desktops"))
        #         .pluck({"right": ["starting_by"]}, "left")
        #         .zip()
        #         .group(lambda log: log["starting_by"])
        #         .count()
        #         .run(cls._rdb_connection)
        #     )

        # owner_count = started_deployment_desktops_starting_by.get("deployment-owner", 0)
        # co_owner_count = started_deployment_desktops_starting_by.get(
        #     "deployment-co-owner", 0
        # )
        # started_deployment_desktops = owner_count + co_owner_count
        started_deployment_desktops = 0

        vcpus = starteds["vcpus"]
        memory = round(starteds["memory"] / 1048576)

        user_quota = user.get("quota") or False
        if user_quota == False:
            qpdesktops = qpup = qptemplates = qpisos = qpvcpus = qpmemory = qpDeployments = qpDktpDeployment = qpStartDeploymentDktp = 0  # fmt: skip
            dq = rq = tq = iq = vq = mq = deploymentsq = dktpDeploymentq = startDeploymentDktpq = 9999  # fmt: skip
        else:
            qpdesktops = (
                desktops * 100 / user_quota["desktops"]
                if user_quota.get("desktops")
                else 100
            )
            dq = user_quota["desktops"]

            qpup = (
                starteds["count"] * 100 / user_quota["running"]
                if user_quota.get("running")
                else 100
            )
            rq = user_quota["running"]

            qptemplates = (
                templates * 100 / user_quota["templates"]
                if user_quota.get("templates")
                else 100
            )
            tq = user_quota["templates"]

            qpisos = isos * 100 / user_quota["isos"] if user_quota.get("isos") else 100
            iq = user_quota["isos"]

            qpvcpus = (
                vcpus * 100 / user_quota["vcpus"] if user_quota.get("vcpus") else 100
            )
            vq = user_quota["vcpus"]

            qpmemory = (
                memory * 100 / user_quota["memory"] if user_quota.get("memory") else 100
            )  # convert GB to KB (domains are in KB by default)
            mq = user_quota["memory"]

            qpDeployments = (
                deployments * 100 / user_quota["deployments_total"]
                if user_quota.get("deployments_total")
                else 100
            )
            deploymentsq = user_quota["deployments_total"]

            qpDktpDeployment = (
                deployment_desktops * 100 / user_quota["deployment_desktops"]
                if user_quota.get("deployment_desktops")
                else 100
            )
            dktpDeploymentq = user_quota["deployment_desktops"]

            qpStartDeploymentDktp = (
                started_deployment_desktops
                * 100
                / user_quota["started_deployment_desktops"]
                if user_quota.get("started_deployment_desktops")
                else 100
            )
            startDeploymentDktpq = user_quota["started_deployment_desktops"]

        return {
            "user": user,
            "d": desktops,
            "dq": dq,
            "dqp": int(round(qpdesktops, 0)),
            "r": starteds["count"],
            "rq": rq,
            "rqp": int(round(qpup, 0)),
            "t": templates,
            "tq": tq,
            "tqp": int(round(qptemplates, 0)),
            "i": isos,
            "iq": iq,
            "iqp": int(round(qpisos, 0)),
            "v": vcpus,
            "vq": vq,
            "vqp": int(round(qpvcpus, 0)),
            "m": int(round(memory)),
            "mq": mq,
            "mqp": int(round(qpmemory, 0)),
            "deployments": deployments,
            "deploymentsq": deploymentsq,
            "deploymentsqp": int(round(qpDeployments, 0)),
            "dktpDeployment": deployment_desktops,
            "dktpDeploymentq": dktpDeploymentq,
            "dktpDeploymentqp": int(round(qpDktpDeployment, 0)),
            "startDeploymentDktp": started_deployment_desktops,
            "startDeploymentDktpq": startDeploymentDktpq,
            "startDeploymentDktpqp": int(round(qpStartDeploymentDktp, 0)),
        }

    @classmethod
    @cached(
        SynchronizedTTLCache(maxsize=50, ttl=10),
        key=lambda cls, id, from_user_id=None, from_group_id=None: (
            id,
            from_user_id,
            from_group_id,
        ),
    )
    def process_category_limits(cls, id, from_user_id=None, from_group_id=None):
        if from_user_id:
            user = Caches.get_document("users", id, ["category", "role"])
            id = user["category"]
        if from_group_id:
            id = Caches.get_document("groups", id, ["parent_category"])
        category = Caches.get_document("categories", id)
        if category == None:
            return False

        category_limits = category.get("limits") or False
        if category_limits == False:
            return False

        with cls._rdb_context():
            desktops = (
                r.table("domains")
                .get_all(["desktop", category["id"]], index="kind_category")
                .count()
                .run(cls._rdb_connection)
            )
        with cls._rdb_context():
            templates = (
                r.table("domains")
                .get_all(["template", category["id"]], index="kind_category")
                .count()
                .run(cls._rdb_connection)
            )
        with cls._rdb_context():
            isos = (
                r.table("media")
                .get_all(category["id"], index="category")
                .count()
                .run(cls._rdb_connection)
            )
        with cls._rdb_context():
            starteds = (
                r.table("domains")
                .get_all(["Started", category["id"]], index="status_category")
                .map(lambda domain: domain["create_dict"]["hardware"].default({}))
                .map(
                    lambda hardware: {
                        "count": 1,
                        "memory": hardware["memory"].default(0),
                        "vcpus": hardware["vcpus"].default(0),
                    }
                )
                .reduce(
                    lambda left, right: {
                        "count": left["count"] + right["count"],
                        "vcpus": left["vcpus"].add(right["vcpus"]),
                        "memory": left["memory"].add(right["memory"]),
                    }
                )
                .default({"count": 0, "memory": 0, "vcpus": 0})
                .run(cls._rdb_connection)
            )

        with cls._rdb_context():
            users = (
                r.table("users")
                .get_all(category["id"], index="category")
                .count()
                .run(cls._rdb_connection)
            )

        with cls._rdb_context():
            deployments = (
                r.table("deployments")
                .eq_join("user", r.table("users"))
                .filter({"right": {"category": category["id"]}})
                .count()
                .run(cls._rdb_connection)
            )

        vcpus = starteds["vcpus"]
        memory = round(starteds["memory"] / 1048576)

        if category_limits == False:
            qpdesktops = qpup = qptemplates = qpisos = qpvcpus = qpmemory = qpusers = qpDeployments = 0  # fmt: skip
            dq = rq = tq = iq = vq = mq = uq = deploymentsq = 9999  # fmt: skip
        else:
            qpdesktops = (
                desktops * 100 / category_limits["desktops"]
                if category_limits.get("desktops")
                else 100
            )
            dq = category_limits["desktops"]

            qpup = (
                starteds["count"] * 100 / category_limits["running"]
                if category_limits.get("running")
                else 100
            )
            rq = category_limits["running"]

            qptemplates = (
                templates * 100 / category_limits["templates"]
                if category_limits.get("templates")
                else 100
            )
            tq = category_limits["templates"]

            qpisos = (
                isos * 100 / category_limits["isos"]
                if category_limits.get("isos")
                else 100
            )
            iq = category_limits["isos"]

            qpvcpus = (
                vcpus * 100 / category_limits["vcpus"]
                if category_limits.get("vcpus")
                else 100
            )
            vq = category_limits["vcpus"]

            qpmemory = (
                memory * 100 / category_limits["memory"]
                if category_limits.get("memory")
                else 100
            )
            mq = category_limits["memory"]

            qpusers = (
                users * 100 / category_limits["users"]
                if category_limits.get("users")
                else 100
            )
            uq = category_limits["users"]

            qpDeployments = (
                deployments * 100 / category_limits["deployments_total"]
                if category_limits.get("deployments_total")
                else 100
            )
            deploymentsq = category_limits["deployments_total"]

        return {
            "category": category,
            "d": desktops,
            "dq": dq,
            "dqp": int(round(qpdesktops, 0)),
            "r": starteds["count"],
            "rq": rq,
            "rqp": int(round(qpup, 0)),
            "t": templates,
            "tq": tq,
            "tqp": int(round(qptemplates, 0)),
            "i": isos,
            "iq": iq,
            "iqp": int(round(qpisos, 0)),
            "v": vcpus,
            "vq": vq,
            "vqp": int(round(qpvcpus, 0)),
            "m": int(round(memory)),
            "mq": mq,
            "mqp": int(round(qpmemory, 0)),
            "u": users,
            "uq": uq,
            "uqp": int(round(qpusers, 0)),
            "deployments": deployments,
            "deploymentsq": deploymentsq,
            "deploymentsqp": int(round(qpDeployments, 0)),
        }

    @classmethod
    @cached(
        SynchronizedTTLCache(maxsize=200, ttl=10),
        key=lambda cls, id, from_user_id=None: (id, from_user_id),
    )
    def process_group_limits(cls, id, from_user_id=None):
        if from_user_id:
            user = Caches.get_document("users", id, ["group", "role"])
            group_id = user["group"]
        else:
            group_id = id
        group = Caches.get_document("groups", group_id)
        if group == None:
            return False

        group_limits = group.get("limits") or False
        if group_limits == False:
            return False

        with cls._rdb_context():
            desktops = (
                r.table("domains")
                .get_all(["desktop", group["id"]], index="kind_group")
                .count()
                .run(cls._rdb_connection)
            )
        with cls._rdb_context():
            templates = (
                r.table("domains")
                .get_all(["template", group["id"]], index="kind_group")
                .count()
                .run(cls._rdb_connection)
            )
        with cls._rdb_context():
            isos = (
                r.table("media")
                .get_all(group["id"], index="group")
                .count()
                .run(cls._rdb_connection)
            )
        with cls._rdb_context():
            starteds = (
                r.table("domains")
                .get_all(["Started", group["id"]], index="status_group")
                .map(lambda domain: domain["create_dict"]["hardware"].default({}))
                .map(
                    lambda hardware: {
                        "count": 1,
                        "memory": hardware["memory"].default(0),
                        "vcpus": hardware["vcpus"].default(0),
                    }
                )
                .reduce(
                    lambda left, right: {
                        "count": left["count"] + right["count"],
                        "vcpus": left["vcpus"].add(right["vcpus"]),
                        "memory": left["memory"].add(right["memory"]),
                    }
                )
                .default({"count": 0, "memory": 0, "vcpus": 0})
                .run(cls._rdb_connection)
            )
        with cls._rdb_context():
            users = (
                r.table("users")
                .get_all(group["id"], index="group")
                .count()
                .run(cls._rdb_connection)
            )

        with cls._rdb_context():
            deployments = (
                r.table("deployments")
                .eq_join("user", r.table("users"))
                .filter({"right": {"group": group["id"]}})
                .count()
                .run(cls._rdb_connection)
            )

        vcpus = starteds["vcpus"]
        memory = round(starteds["memory"] / 1048576)

        if group_limits == False:
            qpdesktops = qpup = qptemplates = qpisos = qpvcpus = qpmemory = qpusers = qpdeployments = 0  # fmt: skip
            dq = rq = tq = iq = vq = mq = uq = deploymentsq = 9999  # fmt: skip
        else:
            qpdesktops = (
                desktops * 100 / group_limits["desktops"]
                if group_limits.get("desktops")
                else 100
            )
            dq = group_limits["desktops"]

            qpup = (
                starteds["count"] * 100 / group_limits["running"]
                if group_limits.get("running")
                else 100
            )
            rq = group_limits["running"]

            qptemplates = (
                templates * 100 / group_limits["templates"]
                if group_limits.get("templates")
                else 100
            )
            tq = group_limits["templates"]

            qpisos = (
                isos * 100 / group_limits["isos"] if group_limits.get("isos") else 100
            )
            iq = group_limits["isos"]

            qpvcpus = (
                vcpus * 100 / group_limits["vcpus"]
                if group_limits.get("vcpus")
                else 100
            )
            vq = group_limits["vcpus"]

            qpmemory = (
                memory * 100 / group_limits["memory"]
                if group_limits.get("memory")
                else 100
            )
            mq = group_limits["memory"]

            qpusers = (
                users * 100 / group_limits["users"]
                if group_limits.get("users")
                else 100
            )
            uq = group_limits["users"]

            qpdeployments = (
                deployments * 100 / group_limits["deployments_total"]
                if group_limits.get("deployments_total")
                else 100
            )
            deploymentsq = group_limits["deployments_total"]

        return {
            "group": group,
            "d": desktops,
            "dq": dq,
            "dqp": int(round(qpdesktops, 0)),
            "r": starteds["count"],
            "rq": rq,
            "rqp": int(round(qpup, 0)),
            "t": templates,
            "tq": tq,
            "tqp": int(round(qptemplates, 0)),
            "i": isos,
            "iq": iq,
            "iqp": int(round(qpisos, 0)),
            "v": vcpus,
            "vq": vq,
            "vqp": int(round(qpvcpus, 0)),
            "m": int(round(memory)),
            "mq": mq,
            "mqp": int(round(qpmemory, 0)),
            "u": users,
            "uq": uq,
            "uqp": int(round(qpusers, 0)),
            "deployments": deployments,
            "deploymentsq": deploymentsq,
            "deploymentsqp": int(round(qpdeployments, 0)),
        }

    @classmethod
    @cached(
        SynchronizedTTLCache(maxsize=10, ttl=30),
        key=lambda cls, category_id: category_id,
    )
    def get_manager_usage(cls, category_id):
        with cls._rdb_context():
            desktops = (
                r.table("domains")
                .get_all(["desktop", category_id], index="kind_category")
                .count()
                .run(cls._rdb_connection)
            )
        with cls._rdb_context():
            templates = (
                r.table("domains")
                .get_all(["template", category_id], index="kind_category")
                .count()
                .run(cls._rdb_connection)
            )
        with cls._rdb_context():
            isos = (
                r.table("media")
                .get_all(category_id, index="category")
                .count()
                .run(cls._rdb_connection)
            )
        with cls._rdb_context():
            starteds = (
                r.table("domains")
                .get_all(["Started", category_id], index="status_category")
                .map(lambda domain: domain["create_dict"]["hardware"].default({}))
                .map(
                    lambda hardware: {
                        "count": 1,
                        "memory": hardware["memory"].default(0),
                        "vcpus": hardware["vcpus"].default(0),
                    }
                )
                .reduce(
                    lambda left, right: {
                        "count": left["count"] + right["count"],
                        "vcpus": left["vcpus"].add(right["vcpus"]),
                        "memory": left["memory"].add(right["memory"]),
                    }
                )
                .default({"count": 0, "memory": 0, "vcpus": 0})
                .run(cls._rdb_connection)
            )
        with cls._rdb_context():
            users = (
                r.table("users")
                .get_all(category_id, index="category")
                .count()
                .run(cls._rdb_connection)
            )
        with cls._rdb_context():
            deployments = (
                r.table("deployments")
                .eq_join("user", r.table("users"))
                .filter({"right": {"category": category_id}})
                .count()
                .run(cls._rdb_connection)
            )

        return {
            "d": desktops,
            "r": starteds["count"],
            "t": templates,
            "i": isos,
            "v": starteds["vcpus"],
            "m": round(starteds["memory"] / 1048576),
            "u": users,
            "deployments": deployments,
        }

    @classmethod
    @cached(
        SynchronizedTTLCache(maxsize=10, ttl=30),
        key=lambda cls: None,
    )
    def get_admin_usage(cls):
        with cls._rdb_context():
            desktops = (
                r.table("domains")
                .get_all("desktop", index="kind")
                .count()
                .run(cls._rdb_connection)
            )
        with cls._rdb_context():
            templates = (
                r.table("domains")
                .get_all("template", index="kind")
                .count()
                .run(cls._rdb_connection)
            )
        with cls._rdb_context():
            isos = r.table("media").count().run(cls._rdb_connection)
        with cls._rdb_context():
            starteds = (
                r.table("domains")
                .get_all("Started", index="status")
                .map(lambda domain: domain["create_dict"]["hardware"].default({}))
                .map(
                    lambda hardware: {
                        "count": 1,
                        "memory": hardware["memory"].default(0),
                        "vcpus": hardware["vcpus"].default(0),
                    }
                )
                .reduce(
                    lambda left, right: {
                        "count": left["count"] + right["count"],
                        "vcpus": left["vcpus"].add(right["vcpus"]),
                        "memory": left["memory"].add(right["memory"]),
                    }
                )
                .default({"count": 0, "memory": 0, "vcpus": 0})
                .run(cls._rdb_connection)
            )
        with cls._rdb_context():
            users = r.table("users").count().run(cls._rdb_connection)
        with cls._rdb_context():
            deployments = r.table("deployments").count().run(cls._rdb_connection)

        return {
            "d": desktops,
            "r": starteds["count"],
            "t": templates,
            "i": isos,
            "v": starteds["vcpus"],
            "m": round(starteds["memory"] / 1048576),
            "u": users,
            "deployments": deployments,
        }

    # @classmethod
    # @cached(
    #     SynchronizedTTLCache(maxsize=100, ttl=10),
    #     key=lambda cls, payload: payload["user_id"],
    # )
    # def check_payload_quota_newdesktop(cls, payload):
    #     with cls._rdb_context():
    #         desktops = (
    #             r.table("domains")
    #             .get_all(["desktop", payload["user_id"]], index="kind_user")
    #             .count()
    #             .run(cls._rdb_connection)
    #         )
    #     if desktops >= payload.get("quota", {}).get("desktops"):
    #         raise Error(
    #             "precondition_required",
    #             "User "
    #             + payload["user_id"]
    #             + " quota exceeded for creating new desktop.",
    #             traceback.format_exc(),
    #             data=payload,
    #             description_code="desktop_new_user_quota_exceeded",
    #         )

    # @classmethod
    # def check(cls, item, user_id, amount=1):
    #     """All common events should call here and check if quota/limits have exceeded already."""
    #     user = cls.process_user_quota(user_id)
    #     group = cls.process_group_limits(user_id, from_user_id=True)
    #     category = cls.process_category_limits(user_id, from_user_id=True)
    #     if item == "NewDesktop":
    #         if user != False and float(user["dqp"]) >= 100:
    #             raise Error(
    #                 "precondition_required",
    #                 "User "
    #                 + user["user"]["name"]
    #                 + " quota exceeded for creating new desktop.",
    #                 traceback.format_exc(),
    #                 data=user,
    #                 description_code="desktop_new_user_quota_exceeded",
    #             )
    #         if group != False and float(group["dqp"]) >= 100:
    #             raise Error(
    #                 "precondition_required",
    #                 "Group "
    #                 + group["group"]["name"]
    #                 + " quota exceeded for creating new desktop.",
    #                 traceback.format_exc(),
    #                 data=group,
    #                 description_code="desktop_new_group_quota_exceeded",
    #             )
    #         if category != False and float(category["dqp"]) >= 100:
    #             raise Error(
    #                 "precondition_required",
    #                 "Category "
    #                 + category["category"]["name"]
    #                 + " quota exceeded for creating new desktop.",
    #                 traceback.format_exc(),
    #                 data=category,
    #                 description_code="desktop_new_category_quota_exceeded",
    #             )

    #     if item == "NewConcurrent":
    #         if user != False:
    #             if float(user["rqp"]) >= 100:
    #                 raise Error(
    #                     "precondition_required",
    #                     "User "
    #                     + user["user"]["name"]
    #                     + " quota exceeded for starting new desktop.",
    #                     traceback.format_exc(),
    #                     data=user,
    #                     description_code="desktop_start_user_quota_exceeded",
    #                 )
    #             if float(user["vqp"]) >= 100:
    #                 raise Error(
    #                     "precondition_required",
    #                     "User "
    #                     + user["user"]["name"]
    #                     + " quota exceeded for vCPU at starting a new desktop.",
    #                     traceback.format_exc(),
    #                     data=user,
    #                     description_code="desktop_start_vcpu_quota_exceeded",
    #                 )
    #             if float(user["mqp"]) >= 100:
    #                 raise Error(
    #                     "precondition_required",
    #                     "User "
    #                     + user["user"]["name"]
    #                     + " quota exceeded for RAM at starting a new desktop.",
    #                     traceback.format_exc(),
    #                     data=user,
    #                     description_code="desktop_start_memory_quota_exceeded",
    #                 )
    #         if group != False:
    #             if float(group["rqp"]) >= 100:
    #                 raise Error(
    #                     "precondition_required",
    #                     "Group "
    #                     + group["group"]["name"]
    #                     + " quota exceeded for starting new desktop.",
    #                     traceback.format_exc(),
    #                     data=group,
    #                     description_code="desktop_start_group_quota_exceeded",
    #                 )
    #             if float(group["vqp"]) >= 100:
    #                 raise Error(
    #                     "precondition_required",
    #                     "Group "
    #                     + group["group"]["name"]
    #                     + " quota exceeded for vCPU at starting new desktop.",
    #                     traceback.format_exc(),
    #                     data=group,
    #                     description_code="desktop_start_group_vcpu_quota_exceeded",
    #                 )
    #             if float(group["mqp"]) >= 100:
    #                 raise Error(
    #                     "precondition_required",
    #                     "Group "
    #                     + group["group"]["name"]
    #                     + " quota exceeded for RAM at starting new desktop.",
    #                     traceback.format_exc(),
    #                     data=group,
    #                     description_code="desktop_start_group_memory_quota_exceeded",
    #                 )
    #         if category != False:
    #             if float(category["rqp"]) >= 100:
    #                 raise Error(
    #                     "precondition_required",
    #                     "Category"
    #                     + category["category"]["name"]
    #                     + " quota exceeded for starting new desktop.",
    #                     traceback.format_exc(),
    #                     data=category,
    #                     description_code="desktop_start_category_quota_exceeded",
    #                 )
    #             if float(category["vqp"]) >= 100:
    #                 raise Error(
    #                     "precondition_required",
    #                     "Category"
    #                     + category["category"]["name"]
    #                     + " quota exceeded for vCPU at starting new desktop.",
    #                     traceback.format_exc(),
    #                     data=category,
    #                     description_code="desktop_start_category_vcpu_quota_exceeded",
    #                 )
    #             if float(category["mqp"]) >= 100:
    #                 raise Error(
    #                     "precondition_required",
    #                     "Category"
    #                     + category["category"]["name"]
    #                     + " quota exceeded for RAM at starting new desktop.",
    #                     traceback.format_exc(),
    #                     data=category,
    #                     description_code="desktop_start_category_memory_quota_exceeded",
    #                 )

    #     if item == "NewTemplate":
    #         if user != False and float(user["tqp"]) >= 100:
    #             raise Error(
    #                 "precondition_required",
    #                 "User "
    #                 + user["user"]["name"]
    #                 + " quota exceeded for creating new template.",
    #                 traceback.format_exc(),
    #                 data=user,
    #                 description_code="template_new_user_quota_exceeded",
    #             )
    #         if group != False and float(group["tqp"]) >= 100:
    #             raise Error(
    #                 "precondition_required",
    #                 "Group "
    #                 + group["group"]["name"]
    #                 + " quota exceeded for creating new template.",
    #                 traceback.format_exc(),
    #                 data=group,
    #                 description_code="template_new_group_quota_exceeded",
    #             )
    #         if category != False and float(category["tqp"]) >= 100:
    #             raise Error(
    #                 "precondition_required",
    #                 "Category "
    #                 + category["category"]["name"]
    #                 + " quota exceeded for creating new desktop.",
    #                 traceback.format_exc(),
    #                 data=category,
    #                 description_code="template_new_category_quota_exceeded",
    #             )

    #     if item == "NewIso":
    #         if user != False and float(user["iqp"]) >= 100:
    #             raise Error(
    #                 "precondition_required",
    #                 "User "
    #                 + user["user"]["name"]
    #                 + " quota exceeded for uploading new iso",
    #                 traceback.format_exc(),
    #                 data=user,
    #                 description_code="iso_creation_user_quota_exceeded",
    #             )
    #         if group != False and float(group["iqp"]) >= 100:
    #             raise Error(
    #                 "precondition_required",
    #                 "Group "
    #                 + group["group"]["name"]
    #                 + " quota exceeded for uploading new iso",
    #                 traceback.format_exc(),
    #                 data=group,
    #                 description_code="iso_creation_group_quota_exceeded",
    #             )
    #         if category != False and float(category["iqp"]) >= 100:
    #             raise Error(
    #                 "precondition_required",
    #                 "Category "
    #                 + category["category"]["name"]
    #                 + " quota exceeded for uploading new iso",
    #                 traceback.format_exc(),
    #                 data=category,
    #                 description_code="iso_creation_category_quota_exceeded",
    #             )

    #     if item == "NewUser":
    #         if group != False and float(group["uqp"]) >= 100:
    #             raise Error(
    #                 "precondition_required",
    #                 "Group "
    #                 + group["group"]["name"]
    #                 + " quota exceeded for creating user",
    #                 traceback.format_exc(),
    #                 data=group,
    #                 description_code="user_new_group_cuota_exceeded",
    #             )
    #         if category != False and float(category["uqp"]) >= 100:
    #             raise Error(
    #                 "precondition_required",
    #                 "Category "
    #                 + category["category"]["name"]
    #                 + " quota exceeded for creating user",
    #                 traceback.format_exc(),
    #                 data=category,
    #                 description_code="user_new_category_cuota_exceeded",
    #             )

    #     if item == "NewUsers":
    #         if group != False and group["u"] + amount > group["uq"]:
    #             raise Error(
    #                 "precondition_required",
    #                 "Group "
    #                 + group["group"]["name"]
    #                 + " quota exceeded for creating "
    #                 + str(amount)
    #                 + " users",
    #                 traceback.format_exc(),
    #                 data=group,
    #                 description_code="user_new_group_cuota_exceeded",
    #             )
    #         if category != False and category["u"] + amount > category["uq"]:
    #             raise Error(
    #                 "precondition_required",
    #                 "Category "
    #                 + category["category"]["name"]
    #                 + " quota exceeded for creating "
    #                 + str(amount)
    #                 + " users",
    #                 traceback.format_exc(),
    #                 data=category,
    #                 description_code="user_new_category_cuota_exceeded",
    #             )

    #     return False

    @classmethod
    def _live_users_count(cls, index, id):
        with cls._rdb_context():
            return (
                r.table("users")
                .get_all(id, index=index)
                .count()
                .run(cls._rdb_connection)
            )

    @classmethod
    def _with_live_users(cls, limits, index, id):
        """Refresh the users usage of a TTL-cached ``process_*_limits`` result.

        Returns a copy: the argument is the object held in the cache. The
        percentage is recomputed exactly as ``process_*_limits`` does,
        rounding included, so the gate keeps comparing the same number.
        """
        users = cls._live_users_count(index, id)
        percent = users * 100 / limits["uq"] if limits["uq"] else 100
        return {**limits, "u": users, "uqp": int(round(percent, 0))}

    # Not cached: cachetools memoizes the return value, never the raise, so a
    # cached "ok" would wave through every later create inside the TTL.
    @classmethod
    def check_new_autoregistered_user(cls, category_id, group_id):
        """All common events should call here and check if quota/limits have exceeded already."""
        group = cls.process_group_limits(group_id, from_user_id=False)
        category = cls.process_category_limits(category_id, from_user_id=False)

        if group != False:
            group = cls._with_live_users(group, "group", group_id)
        if category != False:
            category = cls._with_live_users(category, "category", category_id)

        if group != False and float(group["uqp"]) >= 100:
            raise Error(
                "precondition_required",
                "Group " + group["group"]["name"] + " quota exceeded for creating user",
                traceback.format_exc(),
                data=group,
                description_code="user_new_group_cuota_exceeded",
            )
        if category != False and float(category["uqp"]) >= 100:
            raise Error(
                "precondition_required",
                "Category "
                + category["category"]["name"]
                + " quota exceeded for creating user",
                traceback.format_exc(),
                data=category,
                description_code="user_new_category_cuota_exceeded",
            )

        return False

    @classmethod
    def get_user(cls, user_id):
        user = Caches.get_document("users", user_id)
        group = Caches.get_document("groups", user["group"])

        limits = group.get("limits") or False
        if limits == False:
            limits = (
                Caches.get_document("categories", group["parent_category"], ["limits"])
                or False
            )
        return {"quota": user.get("quota") or False, "limits": limits}

    @classmethod
    def get_shutdown_timeouts(cls, payload, desktop_id=None):
        rules = Caches.get_cached_desktops_priority()
        if not len(rules):
            return False

        if desktop_id:
            # check for desktop
            for rule in rules:
                if rule["allowed"]["desktops"] is not False:
                    if (
                        len(rule["allowed"]["desktops"]) == 0
                        or desktop_id in rule["allowed"]["desktops"]
                    ):
                        return rule["shutdown"]

        # if not, check for payload
        alloweds = [
            ("users", "user"),
            ("groups", "group"),
            ("categories", "category"),
            ("roles", "role"),
        ]

        for allowed_item in alloweds:
            for rule in rules:
                if rule["allowed"][allowed_item[0]] is not False:
                    if (
                        len(rule["allowed"][allowed_item[0]]) == 0
                        or payload[allowed_item[1] + "_id"]
                        in rule["allowed"][allowed_item[0]]
                    ):
                        return rule["shutdown"]
        return False
