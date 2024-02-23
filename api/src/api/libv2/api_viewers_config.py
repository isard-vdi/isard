from rethinkdb import RethinkDB

from api import app

r = RethinkDB()

from .flask_rethink import RDB

db = RDB(app)
db.init_app(app)

from isardvdi_common.api_exceptions import Error

from .helpers import _check


def get_viewers_config():
    custom = []
    with app.app_context():
        viewers = (
            r.table("config").get(1).pluck("viewers")["viewers"].keys().run(db.conn)
        )
        for viewer in viewers:
            custom.append(
                r.table("config")
                .get(1)
                .pluck("viewers")["viewers"][viewer]
                .run(db.conn)
            )
    return custom


def update_viewers_config(viewer, custom):
    with app.app_context():
        query = (
            r.table("config")
            .get(1)
            .update({"viewers": {viewer: {"custom": custom}}})
            .run(db.conn)
        )
    if not _check(query, "inserted"):
        raise Error(
            "internal_server",
            "update_viewers_config: unable to update viewer custom field in database",
        )


def reset_viewers_config(viewer):
    with app.app_context():
        query = (
            r.table("config")
            .get(1)
            .update(
                {"viewers": {viewer: {"custom": r.row["viewers"][viewer]["default"]}}}
            )
            .run(db.conn)
        )
    if not _check(query, "inserted"):
        raise Error(
            "internal_server",
            "update_viewers_config: unable to update viewer custom field in database",
        )
