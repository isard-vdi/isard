import json
import time
import traceback

from flask import request
from rethinkdb import RethinkDB

from api import app

from .._common.api_exceptions import Error
from ..libv2.api_admin import admin_table_list, admin_table_update
from ..libv2.flask_rethink import RDB
from ..libv2.quotas import Quotas

quotas = Quotas()

from ..libv2.api_media import ApiMedia

api_media = ApiMedia()

from ..libv2.api_allowed import ApiAllowed

allowed = ApiAllowed()

r = RethinkDB()
db = RDB(app)
db.init_app(app)

from ..libv2.api_admin import admin_table_insert
from ..libv2.validators import _validate_item
from .decorators import has_token, is_admin_or_manager_or_advanced, ownsMediaId


@app.route("/api/v3/media/new/check_quota", methods=["GET"])
@has_token
def api_v3_media_check_quota(payload):
    quotas.media_create(payload["user_id"])
    return (
        json.dumps({}),
        200,
        {"Content-Type": "application/json"},
    )


# Add media
@app.route("/api/v3/media", methods=["POST"])
@is_admin_or_manager_or_advanced
def api_v3_admin_media_insert(payload):
    try:
        data = request.get_json()
    except:
        raise Error(
            "bad_request",
            "Unable to parse body data.",
            traceback.format_exc(),
        )
    quotas.media_create(payload["user_id"])
    with app.app_context():
        user = r.table("users").get(payload["user_id"]).run(db.conn)
        username = user["username"]
        uid = user["uid"]

    data["user"] = payload["user_id"]
    data["username"] = username
    data["category"] = payload["category_id"]
    data["group"] = payload["group_id"]
    data["url-web"] = data["url"]
    data["accessed"] = int(time.time())

    data = _validate_item("media", data)

    urlpath = (
        data["category"]
        + "/"
        + payload["group_id"]
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


@app.route("/api/v3/media", methods=["GET"])
@has_token
def api_v3_admin_media(payload):
    media = api_media.Media(payload)
    return json.dumps(media), 200, {"Content-Type": "application/json"}


@app.route("/api/v3/media_allowed", methods=["GET"])
@has_token
def api_v3_user_media_allowed(payload):
    media = allowed.get_items_allowed(
        payload=payload,
        table="media",
        query_pluck=[
            "id",
            "name",
            "status",
            "category",
            "category_name",
            "group",
            "group_name",
            "owner",
            "progress",
            "user",
            "description",
            "kind",
            "icon",
        ],
        order="name",
        query_filter=lambda media: media["user"] != payload["user_id"],
        query_merge=True,
    )
    return (
        json.dumps(media),
        200,
        {"Content-Type": "application/json"},
    )


@app.route("/api/v3/desktops/media_list", methods=["POST"])
@has_token
def api_v3_desktops_media_list(payload):
    data = request.get_json(force=True)
    return (
        json.dumps(api_media.List(data["pk"])),
        200,
        {"Content-Type": "application/json"},
    )


# Media actions
@app.route("/api/v3/media/<action>/<id>", methods=["POST"])
@is_admin_or_manager_or_advanced
def api_v3_media_actions(payload, action, id):
    if action == "abort":
        data = {"id": id, "status": "DownloadAborting"}
    if action == "download":
        data = {"id": id, "status": "DownloadStarting"}
    admin_table_update("media", data)
    return json.dumps({}), 200, {"Content-Type": "application/json"}


@app.route("/api/v3/media/installs")
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


# Gets related desktops list at deleting media
@app.route("/api/v3/media/desktops/<media_id>", methods=["GET"])
@is_admin_or_manager_or_advanced
def api_v3_admin_media_desktops(payload, media_id):
    ownsMediaId(payload, media_id)
    return (
        json.dumps(api_media.DesktopList(media_id)),
        200,
        {"Content-Type": "application/json"},
    )


@app.route("/api/v3/media/<media_id>", methods=["DELETE"])
@is_admin_or_manager_or_advanced
def api_v3_admin_media_delete(payload, media_id):
    media = api_media.Get(media_id)
    ownsMediaId(payload, media_id)
    api_media.DeleteDesktops(media_id)
    return json.dumps(media_id), 200, {"Content-Type": "application/json"}
