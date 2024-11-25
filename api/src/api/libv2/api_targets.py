import traceback
import uuid

from isardvdi_common.api_exceptions import Error
from rethinkdb import RethinkDB

from api import app

from ..views.decorators import can_use_bastion
from .flask_rethink import RDB

r = RethinkDB()

db = RDB(app)
db.init_app(app)


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
            }
            target["http"] = {"enabled": False, "http_port": 80, "https_port": 443}
            target["ssh"] = {"enabled": False, "port": 22, "authorized_keys": []}

            with app.app_context():
                r.db("isard").table("targets").insert(target).run(db.conn)

        if data.get("http"):
            target["http"] = data["http"]
        if data.get("ssh"):
            target["ssh"] = data["ssh"]

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
                ).update({"user_id": new_user_payload["user_id"]})
        else:
            self.bulk_delete_domain_targets(domain_ids)
