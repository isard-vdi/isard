# Copyright 2017 the Isard-vdi project authors:
#      Josep Maria Viñolas Auquer
#      Alberto Larraz Dalmases
# License: AGPLv3

import traceback

from cachetools import TTLCache, cached
from isardvdi_common.api_exceptions import Error
from rethinkdb import RethinkDB

from api import app

from .api_allowed import ApiAllowed

allowed = ApiAllowed()
r = RethinkDB()
from .flask_rethink import RDB

db = RDB(app)
db.init_app(app)


class QuotasProcess:
    def __init__(self):
        None

    @cached(TTLCache(maxsize=10, ttl=10))
    def get(self, user_id, category_id, role_id):
        userquotas = {}
        userquotas["user"] = self.process_user_quota(user_id)
        if role_id == "manager":
            userquotas["limits"] = (
                self.process_category_limits(category_id)
                if self.process_category_limits(category_id)
                else self.get_manager_usage(category_id)
            )
        if role_id == "admin":
            userquotas["global"] = self.get_admin_usage()

        return userquotas

    def process_user_quota(self, user_id):
        with app.app_context():
            user = (
                r.table("users")
                .get(user_id)
                .without("password", "vpn", "user_storage")
                .run(db.conn)
            )

        with app.app_context():
            desktops = (
                r.table("domains")
                .get_all(["desktop", user_id], index="kind_user")
                .count()
                .run(db.conn)
            )
            templates = (
                r.table("domains")
                .get_all(["template", user_id], index="kind_user")
                .count()
                .run(db.conn)
            )
            isos = r.table("media").get_all(user_id, index="user").count().run(db.conn)
            try:
                starteds = (
                    r.table("domains")
                    .get_all(["Started", user_id], index="status_user")
                    .pluck("create_dict")
                    .map(
                        lambda domain: {
                            "count": 1,
                            "memory": domain["create_dict"]["hardware"]["memory"],
                            "vcpus": domain["create_dict"]["hardware"]["vcpus"],
                        }
                    )
                    .reduce(
                        lambda left, right: {
                            "count": left["count"] + right["count"],
                            "vcpus": left["vcpus"].add(right["vcpus"]),
                            "memory": left["memory"].add(right["memory"]),
                        }
                    )
                    .run(db.conn)
                )
            except r.ReqlNonExistenceError:
                starteds = {"count": 0, "memory": 0, "vcpus": 0}
            deployments = (
                r.table("deployments")
                .get_all(user["id"], index="user")
                .count()
                .run(db.conn)
            )
            deployment_desktops = 0

            started_deployment_desktops = (
                r.table("domains")
                .get_all(
                    r.args(
                        list(
                            r.table("deployments")
                            .get_all(user_id, index="user")
                            .pluck("id")["id"]
                            .run(db.conn)
                        )
                    ),
                    index="tag",
                )
                .filter(
                    lambda desktop: r.expr(
                        [
                            "Started",
                            "Starting",
                            "StartingPaused",
                            "CreatingAndStarting",
                            "Shutting-down",
                        ]
                    ).contains(desktop["status"])
                )
                .eq_join("start_logs_id", r.table("logs_desktops"))
                .pluck({"right": ["starting_by"]}, "left")
                .zip()
                .filter(lambda log: log.get_field("starting_by").eq("deployment-owner"))
                .count()
                .run(db.conn)
            ) + (
                r.table("domains")
                .get_all(
                    r.args(
                        list(
                            r.table("deployments")
                            .get_all(user_id, index="user")
                            .pluck("id")["id"]
                            .run(db.conn)
                        )
                    ),
                    index="tag",
                )
                .filter(
                    lambda desktop: r.expr(
                        [
                            "Started",
                            "Starting",
                            "StartingPaused",
                            "CreatingAndStarting",
                            "Shutting-down",
                        ]
                    ).contains(desktop["status"])
                )
                .eq_join("start_logs_id", r.table("logs_desktops"))
                .pluck({"right": ["starting_by"]}, "left")
                .zip()
                .filter(
                    lambda log: log.get_field("starting_by").eq("deployment-co-owner")
                )
                .count()
                .run(db.conn)
            )

        vcpus = starteds["vcpus"]
        memory = round(starteds["memory"] / 1048576)

        if user["quota"] == False:
            qpdesktops = qpup = qptemplates = qpisos = qpvcpus = qpmemory = qpDeployments = qpDktpDeployment = qpStartDeploymentDktp = 0  # fmt: skip
            dq = rq = tq = iq = vq = mq = deploymentsq = dktpDeploymentq = startDeploymentDktpq = 9999  # fmt: skip
        else:
            qpdesktops = (
                desktops * 100 / user["quota"]["desktops"]
                if user["quota"]["desktops"]
                else 100
            )
            dq = user["quota"]["desktops"]

            qpup = (
                starteds["count"] * 100 / user["quota"]["running"]
                if user["quota"]["running"]
                else 100
            )
            rq = user["quota"]["running"]

            qptemplates = (
                templates * 100 / user["quota"]["templates"]
                if user["quota"]["templates"]
                else 100
            )
            tq = user["quota"]["templates"]

            qpisos = (
                isos * 100 / user["quota"]["isos"] if user["quota"]["isos"] else 100
            )
            iq = user["quota"]["isos"]

            qpvcpus = (
                vcpus * 100 / user["quota"]["vcpus"] if user["quota"]["vcpus"] else 100
            )
            vq = user["quota"]["vcpus"]

            qpmemory = (
                memory * 100 / user["quota"]["memory"]
                if user["quota"]["memory"]
                else 100
            )  # convert GB to KB (domains are in KB by default)
            mq = user["quota"]["memory"]

            qpDeployments = (
                deployments * 100 / user["quota"]["deployments_total"]
                if user["quota"]["deployments_total"]
                else 100
            )
            deploymentsq = user["quota"]["deployments_total"]

            qpDktpDeployment = (
                deployment_desktops * 100 / user["quota"]["deployment_desktops"]
                if user["quota"]["deployment_desktops"]
                else 100
            )
            dktpDeploymentq = user["quota"]["deployment_desktops"]

            qpStartDeploymentDktp = (
                started_deployment_desktops
                * 100
                / user["quota"]["started_deployment_desktops"]
                if user["quota"]["started_deployment_desktops"]
                else 100
            )
            startDeploymentDktpq = user["quota"]["started_deployment_desktops"]

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

    def process_category_limits(self, id, from_user_id=None, from_group_id=None):
        if from_user_id:
            with app.app_context():
                user = r.table("users").get(id).pluck("category", "role").run(db.conn)
            id = user["category"]
        if from_group_id:
            with app.app_context():
                id = (
                    r.table("groups")
                    .get(id)
                    .pluck("parent_category")
                    .run(db.conn)["parent_category"]
                )

        with app.app_context():
            category = r.table("categories").get(id).run(db.conn)
        if (
            category == None
            or "limits" not in category.keys()
            or category["limits"] == False
        ):
            return False

        with app.app_context():
            desktops = (
                r.table("domains")
                .get_all(["desktop", category["id"]], index="kind_category")
                .count()
                .run(db.conn)
            )
            templates = (
                r.table("domains")
                .get_all(["template", category["id"]], index="kind_category")
                .count()
                .run(db.conn)
            )
            isos = (
                r.table("media")
                .get_all(category["id"], index="category")
                .count()
                .run(db.conn)
            )
            try:
                starteds = (
                    r.table("domains")
                    .get_all(["Started", category["id"]], index="status_category")
                    .pluck("create_dict")
                    .map(
                        lambda domain: {
                            "count": 1,
                            "memory": domain["create_dict"]["hardware"]["memory"],
                            "vcpus": domain["create_dict"]["hardware"]["vcpus"],
                        }
                    )
                    .reduce(
                        lambda left, right: {
                            "count": left["count"] + right["count"],
                            "vcpus": left["vcpus"].add(right["vcpus"]),
                            "memory": left["memory"].add(right["memory"]),
                        }
                    )
                    .run(db.conn)
                )
            except r.ReqlNonExistenceError:
                starteds = {"count": 0, "memory": 0, "vcpus": 0}

            users = (
                r.table("users")
                .get_all(category["id"], index="category")
                .count()
                .run(db.conn)
            )

            deployments = (
                r.table("deployments")
                .eq_join("user", r.table("users"))
                .filter({"right": {"category": category["id"]}})
                .count()
                .run(db.conn)
            )

        vcpus = starteds["vcpus"]
        memory = round(starteds["memory"] / 1048576)

        if category["limits"] == False:
            qpdesktops = qpup = qptemplates = qpisos = qpvcpus = qpmemory = qpusers = qpDeployments = 0  # fmt: skip
            dq = rq = tq = iq = vq = mq = uq = deploymentsq = 9999  # fmt: skip
        else:
            qpdesktops = (
                desktops * 100 / category["limits"]["desktops"]
                if category["limits"]["desktops"]
                else 100
            )
            dq = category["limits"]["desktops"]

            qpup = (
                starteds["count"] * 100 / category["limits"]["running"]
                if category["limits"]["running"]
                else 100
            )
            rq = category["limits"]["running"]

            qptemplates = (
                templates * 100 / category["limits"]["templates"]
                if category["limits"]["templates"]
                else 100
            )
            tq = category["limits"]["templates"]

            qpisos = (
                isos * 100 / category["limits"]["isos"]
                if category["limits"]["isos"]
                else 100
            )
            iq = category["limits"]["isos"]

            qpvcpus = (
                vcpus * 100 / category["limits"]["vcpus"]
                if category["limits"]["vcpus"]
                else 100
            )
            vq = category["limits"]["vcpus"]

            qpmemory = (
                memory / category["limits"]["memory"]
                if category["limits"]["memory"]
                else 100
            )  # convert GB to KB (domains are in KB by default)
            mq = category["limits"]["memory"]

            qpusers = (
                users * 100 / category["limits"]["users"]
                if category["limits"]["users"]
                else 100
            )
            uq = category["limits"]["users"]

            qpDeployments = (
                deployments * 100 / category["limits"]["deployments_total"]
                if category["limits"]["deployments_total"]
                else 100
            )
            deploymentsq = category["limits"]["deployments_total"]

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

    def process_group_limits(self, id, from_user_id=None):
        if from_user_id:
            with app.app_context():
                user = r.table("users").get(id).pluck("group", "role").run(db.conn)
                group_id = user["group"]
        else:
            group_id = id

        with app.app_context():
            group = r.table("groups").get(group_id).run(db.conn)
        if group == None or "limits" not in group.keys() or group["limits"] == False:
            return False

        with app.app_context():
            desktops = (
                r.table("domains")
                .get_all(["desktop", group["id"]], index="kind_group")
                .count()
                .run(db.conn)
            )
            templates = (
                r.table("domains")
                .get_all(["template", group["id"]], index="kind_group")
                .count()
                .run(db.conn)
            )
            isos = (
                r.table("media")
                .get_all(group["id"], index="group")
                .count()
                .run(db.conn)
            )
            try:
                starteds = (
                    r.table("domains")
                    .get_all(["Started", group["id"]], index="status_group")
                    .pluck("create_dict")
                    .map(
                        lambda domain: {
                            "count": 1,
                            "memory": domain["create_dict"]["hardware"]["memory"],
                            "vcpus": domain["create_dict"]["hardware"]["vcpus"],
                        }
                    )
                    .reduce(
                        lambda left, right: {
                            "count": left["count"] + right["count"],
                            "vcpus": left["vcpus"].add(right["vcpus"]),
                            "memory": left["memory"].add(right["memory"]),
                        }
                    )
                    .run(db.conn)
                )
            except r.ReqlNonExistenceError:
                starteds = {"count": 0, "memory": 0, "vcpus": 0}
            users = (
                r.table("users")
                .get_all(group["id"], index="group")
                .count()
                .run(db.conn)
            )

            deployments = (
                r.table("deployments")
                .eq_join("user", r.table("users"))
                .filter({"right": {"group": group["id"]}})
                .count()
                .run(db.conn)
            )

        vcpus = starteds["vcpus"]
        memory = round(starteds["memory"] / 1048576)

        if group["limits"] == False:
            qpdesktops = qpup = qptemplates = qpisos = qpvcpus = qpmemory = qpusers = qpdeployments = 0  # fmt: skip
            dq = rq = tq = iq = vq = mq = uq = deploymentsq = 9999  # fmt: skip
        else:
            qpdesktops = (
                desktops * 100 / group["limits"]["desktops"]
                if group["limits"]["desktops"]
                else 100
            )
            dq = group["limits"]["desktops"]

            qpup = (
                starteds["count"] * 100 / group["limits"]["running"]
                if group["limits"]["running"]
                else 100
            )
            rq = group["limits"]["running"]

            qptemplates = (
                templates * 100 / group["limits"]["templates"]
                if group["limits"]["templates"]
                else 100
            )
            tq = group["limits"]["templates"]

            qpisos = (
                isos * 100 / group["limits"]["isos"] if group["limits"]["isos"] else 100
            )
            iq = group["limits"]["isos"]

            qpvcpus = (
                vcpus * 100 / group["limits"]["vcpus"]
                if group["limits"]["vcpus"]
                else 100
            )
            vq = group["limits"]["vcpus"]

            qpmemory = (
                memory / group["limits"]["memory"] if group["limits"]["memory"] else 100
            )  # convert GB to KB (domains are in KB by default)
            mq = group["limits"]["memory"]

            qpusers = (
                users * 100 / group["limits"]["users"]
                if group["limits"]["users"]
                else 100
            )
            uq = group["limits"]["users"]

            qpdeployments = (
                deployments * 100 / group["limits"]["deployments_total"]
                if group["limits"]["deployments_total"]
                else 100
            )
            deploymentsq = group["limits"]["deployments_total"]

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

    def get_manager_usage(self, category_id):
        with app.app_context():
            desktops = (
                r.table("domains")
                .get_all(["desktop", category_id], index="kind_category")
                .count()
                .run(db.conn)
            )
            templates = (
                r.table("domains")
                .get_all(["template", category_id], index="kind_category")
                .count()
                .run(db.conn)
            )
            isos = (
                r.table("media")
                .get_all(category_id, index="category")
                .count()
                .run(db.conn)
            )
            try:
                starteds = (
                    r.table("domains")
                    .get_all(["Started", category_id], index="status_category")
                    .pluck("create_dict")
                    .map(
                        lambda domain: {
                            "count": 1,
                            "memory": domain["create_dict"]["hardware"]["memory"],
                            "vcpus": domain["create_dict"]["hardware"]["vcpus"],
                        }
                    )
                    .reduce(
                        lambda left, right: {
                            "count": left["count"] + right["count"],
                            "vcpus": left["vcpus"].add(right["vcpus"]),
                            "memory": left["memory"].add(right["memory"]),
                        }
                    )
                    .run(db.conn)
                )
            except r.ReqlNonExistenceError:
                starteds = {"count": 0, "memory": 0, "vcpus": 0}
            users = (
                r.table("users")
                .get_all(category_id, index="category")
                .count()
                .run(db.conn)
            )
            deployments = (
                r.table("deployments")
                .eq_join("user", r.table("users"))
                .filter({"right": {"category": category_id}})
                .count()
                .run(db.conn)
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

    def get_admin_usage(self):
        with app.app_context():
            desktops = (
                r.table("domains").get_all("desktop", index="kind").count().run(db.conn)
            )
            templates = (
                r.table("domains")
                .get_all("template", index="kind")
                .count()
                .run(db.conn)
            )
            isos = r.table("media").count().run(db.conn)
            try:
                starteds = (
                    r.table("domains")
                    .get_all("Started", index="status")
                    .pluck("create_dict")
                    .map(
                        lambda domain: {
                            "count": 1,
                            "memory": domain["create_dict"]["hardware"]["memory"],
                            "vcpus": domain["create_dict"]["hardware"]["vcpus"],
                        }
                    )
                    .reduce(
                        lambda left, right: {
                            "count": left["count"] + right["count"],
                            "vcpus": left["vcpus"].add(right["vcpus"]),
                            "memory": left["memory"].add(right["memory"]),
                        }
                    )
                    .run(db.conn)
                )
            except r.ReqlNonExistenceError:
                starteds = {"count": 0, "memory": 0, "vcpus": 0}
            users = r.table("users").count().run(db.conn)
            deployments = r.table("deployments").count().run(db.conn)

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

    def check_payload_quota_newdesktop(self, payload):
        with app.app_context():
            desktops = (
                r.table("domains")
                .get_all(["desktop", payload["user_id"]], index="kind_user")
                .count()
                .run(db.conn)
            )
        if desktops >= payload.get("quota", {}).get("desktops"):
            raise Error(
                "precondition_required",
                "User "
                + payload["user_id"]
                + " quota exceeded for creating new desktop.",
                traceback.format_exc(),
                data=payload,
                description_code="desktop_new_user_quota_exceeded",
            )

    def check(self, item, user_id, amount=1):
        """All common events should call here and check if quota/limits have exceeded already."""
        user = self.process_user_quota(user_id)
        group = self.process_group_limits(user_id, from_user_id=True)
        category = self.process_category_limits(user_id, from_user_id=True)
        if item == "NewDesktop":
            if user != False and float(user["dqp"]) >= 100:
                raise Error(
                    "precondition_required",
                    "User "
                    + user["user"]["name"]
                    + " quota exceeded for creating new desktop.",
                    traceback.format_exc(),
                    data=user,
                    description_code="desktop_new_user_quota_exceeded",
                )
            if group != False and float(group["dqp"]) >= 100:
                raise Error(
                    "precondition_required",
                    "Group "
                    + group["group"]["name"]
                    + " quota exceeded for creating new desktop.",
                    traceback.format_exc(),
                    data=group,
                    description_code="desktop_new_group_quota_exceeded",
                )
            if category != False and float(category["dqp"]) >= 100:
                raise Error(
                    "precondition_required",
                    "Category "
                    + category["category"]["name"]
                    + " quota exceeded for creating new desktop.",
                    traceback.format_exc(),
                    data=category,
                    description_code="desktop_new_category_quota_exceeded",
                )

        if item == "NewConcurrent":
            if user != False:
                if float(user["rqp"]) >= 100:
                    raise Error(
                        "precondition_required",
                        "User "
                        + user["user"]["name"]
                        + " quota exceeded for starting new desktop.",
                        traceback.format_exc(),
                        data=user,
                        description_code="desktop_start_user_quota_exceeded",
                    )
                if float(user["vqp"]) >= 100:
                    raise Error(
                        "precondition_required",
                        "User "
                        + user["user"]["name"]
                        + " quota exceeded for vCPU at starting a new desktop.",
                        traceback.format_exc(),
                        data=user,
                        description_code="desktop_start_vcpu_quota_exceeded",
                    )
                if float(user["mqp"]) >= 100:
                    raise Error(
                        "precondition_required",
                        "User "
                        + user["user"]["name"]
                        + " quota exceeded for RAM at starting a new desktop.",
                        traceback.format_exc(),
                        data=user,
                        description_code="desktop_start_memory_quota_exceeded",
                    )
            if group != False:
                if float(group["rqp"]) >= 100:
                    raise Error(
                        "precondition_required",
                        "Group "
                        + group["group"]["name"]
                        + " quota exceeded for starting new desktop.",
                        traceback.format_exc(),
                        data=group,
                        description_code="desktop_start_group_quota_exceeded",
                    )
                if float(group["vqp"]) >= 100:
                    raise Error(
                        "precondition_required",
                        "Group "
                        + group["group"]["name"]
                        + " quota exceeded for vCPU at starting new desktop.",
                        traceback.format_exc(),
                        data=group,
                        description_code="desktop_start_group_vcpu_quota_exceeded",
                    )
                if float(group["mqp"]) >= 100:
                    raise Error(
                        "precondition_required",
                        "Group "
                        + group["group"]["name"]
                        + " quota exceeded for RAM at starting new desktop.",
                        traceback.format_exc(),
                        data=group,
                        description_code="desktop_start_group_memory_quota_exceeded",
                    )
            if category != False:
                if float(category["rqp"]) >= 100:
                    raise Error(
                        "precondition_required",
                        "Category"
                        + category["category"]["name"]
                        + " quota exceeded for starting new desktop.",
                        traceback.format_exc(),
                        data=category,
                        description_code="desktop_start_category_quota_exceeded",
                    )
                if float(category["vqp"]) >= 100:
                    raise Error(
                        "precondition_required",
                        "Category"
                        + category["category"]["name"]
                        + " quota exceeded for vCPU at starting new desktop.",
                        traceback.format_exc(),
                        data=category,
                        description_code="desktop_start_category_vcpu_quota_exceeded",
                    )
                if float(category["mqp"]) >= 100:
                    raise Error(
                        "precondition_required",
                        "Category"
                        + category["category"]["name"]
                        + " quota exceeded for RAM at starting new desktop.",
                        traceback.format_exc(),
                        data=category,
                        description_code="desktop_start_category_memory_quota_exceeded",
                    )

        if item == "NewTemplate":
            if user != False and float(user["tqp"]) >= 100:
                raise Error(
                    "precondition_required",
                    "User "
                    + user["user"]["name"]
                    + " quota exceeded for creating new template.",
                    traceback.format_exc(),
                    data=user,
                    description_code="template_new_user_quota_exceeded",
                )
            if group != False and float(group["tqp"]) >= 100:
                raise Error(
                    "precondition_required",
                    "Group "
                    + group["group"]["name"]
                    + " quota exceeded for creating new template.",
                    traceback.format_exc(),
                    data=group,
                    description_code="template_new_group_quota_exceeded",
                )
            if category != False and float(category["tqp"]) >= 100:
                raise Error(
                    "precondition_required",
                    "Category "
                    + category["category"]["name"]
                    + " quota exceeded for creating new desktop.",
                    traceback.format_exc(),
                    data=category,
                    description_code="template_new_category_quota_exceeded",
                )

        if item == "NewIso":
            if user != False and float(user["iqp"]) >= 100:
                raise Error(
                    "precondition_required",
                    "User "
                    + user["user"]["name"]
                    + " quota exceeded for uploading new iso",
                    traceback.format_exc(),
                    data=user,
                    description_code="iso_creation_user_quota_exceeded",
                )
            if group != False and float(group["iqp"]) >= 100:
                raise Error(
                    "precondition_required",
                    "Group "
                    + group["group"]["name"]
                    + " quota exceeded for uploading new iso",
                    traceback.format_exc(),
                    data=group,
                    description_code="iso_creation_group_quota_exceeded",
                )
            if category != False and float(category["iqp"]) >= 100:
                raise Error(
                    "precondition_required",
                    "Category "
                    + category["category"]["name"]
                    + " quota exceeded for uploading new iso",
                    traceback.format_exc(),
                    data=category,
                    description_code="iso_creation_category_quota_exceeded",
                )

        if item == "NewUser":
            if group != False and float(group["uqp"]) >= 100:
                raise Error(
                    "precondition_required",
                    "Group "
                    + group["group"]["name"]
                    + " quota exceeded for creating user",
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

        if item == "NewUsers":
            if group != False and group["u"] + amount > group["uq"]:
                raise Error(
                    "precondition_required",
                    "Group "
                    + group["group"]["name"]
                    + " quota exceeded for creating "
                    + str(amount)
                    + " users",
                    traceback.format_exc(),
                    data=group,
                    description_code="user_new_group_cuota_exceeded",
                )
            if category != False and category["u"] + amount > category["uq"]:
                raise Error(
                    "precondition_required",
                    "Category "
                    + category["category"]["name"]
                    + " quota exceeded for creating "
                    + str(amount)
                    + " users",
                    traceback.format_exc(),
                    data=category,
                    description_code="user_new_category_cuota_exceeded",
                )

        return False

    def check_new_autoregistered_user(self, category_id, group_id):
        """All common events should call here and check if quota/limits have exceeded already."""
        group = self.process_group_limits(group_id, from_user_id=False)
        category = self.process_category_limits(category_id, from_user_id=False)

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

    def get_user(self, user_id):
        with app.app_context():
            user = (
                r.table("users")
                .get(user_id)
                .without("password", "vpn", "user_storage")
                .run(db.conn)
            )
            group = r.table("groups").get(user["group"]).run(db.conn)
        limits = group["limits"]
        if limits == False:
            with app.app_context():
                limits = (
                    r.table("categories")
                    .get(group["parent_category"])
                    .pluck("limits")
                    .run(db.conn)["limits"]
                )
        return {"quota": user["quota"], "limits": limits}

    def get_shutdown_timeouts(self, payload, desktop_id=None):
        with app.app_context():
            rules = list(
                r.table("desktops_priority").order_by(r.desc("priority")).run(db.conn)
            )
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
