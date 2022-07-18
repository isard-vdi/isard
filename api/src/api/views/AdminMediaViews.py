import json
import time
import traceback

from flask import request
from rethinkdb import RethinkDB

from api import app

from ..libv2.api_admin import admin_table_insert, admin_table_list
from ..libv2.api_exceptions import Error
from ..libv2.api_media import ApiMedia
from ..libv2.flask_rethink import RDB
from ..libv2.validators import _validate_item
from .decorators import has_token, is_admin_or_manager, ownsCategoryId

r = RethinkDB()
db = RDB(app)
db.init_app(app)

api_media = ApiMedia()

# Add media
@app.route("/api/v3/admin/media", methods=["POST"])
@is_admin_or_manager
def api_v3_admin_media_insert(payload):
    try:
        data = request.get_json()
    except:
        raise Error(
            "bad_request",
            "Unable to parse body data.",
            traceback.format_exc(),
        )

    with app.app_context():
        username = r.table("users").get(payload["user_id"])["username"].run(db.conn)
        uid = r.table("users").get(payload["user_id"])["uid"]
        if username == None:
            raise Error("not_found", "User not found", traceback.format_exc())
        group = r.table("groups").get(payload["group_id"])["uid"].run(db.conn)
        if group == None:
            raise Error("not_found", "Group not found", traceback.format_exc())

    data["user"] = payload["user_id"]
    data["username"] = username
    data["category"] = payload["category_id"]
    data["group"] = payload["group_id"]
    data["url-web"] = data["url"]
    data["accessed"] = time.time()

    data = _validate_item("media", data)

    urlpath = (
        data["category"]
        + "/"
        + group
        + "/"
        + payload["provider"]
        + "/"
        + uid
        + "-"
        + username
        + "/"
        + data["name"].replace(" ", "_")
    )
    data["path"] = urlpath

    admin_table_insert("media", data)

    return json.dumps({}), 200, {"Content-Type": "application/json"}


@app.route("/api/v3/admin/media/desktops/<media_id>", methods=["GET"])
@has_token
def api_v3_admin_media_desktops(payload, media_id):
    return (
        json.dumps(api_media.DesktopList(media_id)),
        200,
        {"Content-Type": "application/json"},
    )


@app.route("/api/v3/admin/media/<media_id>", methods=["DELETE"])
@has_token
def api_v3_admin_media_delete(payload, media_id):
    media = api_media.Get(media_id)
    ownsCategoryId(payload, media["category"])
    api_media.DeleteDesktops(media_id)
    return json.dumps(media_id), 200, {"Content-Type": "application/json"}


@app.route("/api/v3/admin/media/installs")
@has_token
def api_v3_media_installs(payload):
    return (
        json.dumps(
            admin_table_list(
                "virt_install",
                order_by="name",
                pluck=["id", "name", "description", "vers"],
            )
        ),
        200,
        {"Content-Type": "application/json"},
    )
