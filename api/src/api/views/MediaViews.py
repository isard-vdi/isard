import json

from flask import request

from api import app

from ..libv2.api_admin import admin_table_list, admin_table_update
from ..libv2.api_exceptions import Error
from ..libv2.quotas import Quotas

quotas = Quotas()

from ..libv2.api_media import ApiMedia

api_media = ApiMedia()

from ..libv2.api_allowed import ApiAllowed

allowed = ApiAllowed()

from .decorators import has_token, is_admin_or_manager_or_advanced


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
        query_merge=True,
    )
    return json.dumps(media), 200, {"Content-Type": "application/json"}


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
