import json
import re
import time
import traceback
import urllib.request
from urllib.parse import quote, urlparse

from flask import jsonify, request
from isardvdi_common.api_exceptions import Error
from isardvdi_common.media import Media
from rethinkdb import RethinkDB

from api import app

from ..libv2.api_admin import admin_table_list, admin_table_update
from ..libv2.flask_rethink import RDB
from ..libv2.quotas import Quotas

quotas = Quotas()

from ..libv2.api_media import ApiMedia, media_task_check, media_task_delete

api_media = ApiMedia()

from ..libv2.api_allowed import ApiAllowed

allowed = ApiAllowed()

r = RethinkDB()
db = RDB(app)
db.init_app(app)

from ..libv2.api_admin import admin_table_insert
from ..libv2.validators import _validate_item
from .decorators import (
    checkDuplicate,
    has_token,
    is_admin_or_manager,
    is_admin_or_manager_or_advanced,
    ownsDomainId,
    ownsMediaId,
)


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
        data["url"] = quote(data.get("url", ""), safe=":/?=&%")
    except:
        raise Error(
            "bad_request",
            "Unable to parse body data.",
            traceback.format_exc(),
        )
    url = urlparse(data["url"])
    if url.scheme != "https" or not re.compile(
        r"^(([a-zA-Z]{1})|([a-zA-Z]{1}[a-zA-Z]{1})|"
        r"([a-zA-Z]{1}[0-9]{1})|([0-9]{1}[a-zA-Z]{1})|"
        r"([a-zA-Z0-9][-_.a-zA-Z0-9]{0,61}[a-zA-Z0-9]))\."
        r"([a-zA-Z]{2,13}|[a-zA-Z0-9-]{2,30}.[a-zA-Z]{2,3})$"
    ).match(url.netloc):
        raise Error(
            "bad_request",
            "The url does not meet the requirements.",
            traceback.format_exc(),
            "media_url_bad_format",
        )
    try:
        response = urllib.request.urlopen(data["url"])
    except urllib.error.HTTPError as e:
        if e.code == 404:
            raise Error(
                "not_found",
                "The url could not be found.",
                traceback.format_exc(),
                "media_url_not_found",
            )
        # Set Mozilla as user agent to avoid getting forbidden from the download servers
        req = urllib.request.Request(
            data["url"],
            data=None,
            headers={
                "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_9_3) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/35.0.1916.47 Safari/537.36"
            },
        )
        response = urllib.request.urlopen(req)
    except:
        raise Error(
            "bad_request",
            "The url is not valid.",
            traceback.format_exc(),
            "media_url_not_valid",
        )
    if response.info()["content-Length"]:
        media_size = float(response.info()["content-Length"])
    else:
        media_size = 0
    quotas.media_create(payload["user_id"], media_size)
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
    checkDuplicate("media", data["name"], user=payload["user_id"])

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
        only_in_allowed=True,
    )
    return (
        json.dumps(media),
        200,
        {"Content-Type": "application/json"},
    )


@app.route("/api/v3/desktops/media_list", methods=["POST"])
@is_admin_or_manager
def api_v3_desktops_media_list(payload):
    data = request.get_json(force=True)
    ownsDomainId(payload, data["id"])
    return (
        json.dumps(api_media.List(data["id"])),
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
    """
    Endpoint to delete a media

    :param payload: Data from JWT
    :type payload: dict
    :param media_id: Media ID
    :type media_id: str
    :return: Task ID or None
    :rtype: Set with Flask response values and data in JSON
    """
    ownsMediaId(payload, media_id)
    api_media.DeleteDesktops(media_id)
    task_id = media_task_delete(media_id, payload.get("user_id"))
    return jsonify(task_id)


@app.route("/api/v3/media/check/<media_id>", methods=["PUT"])
@is_admin_or_manager
def api_v3_admin_media_check(payload, media_id):
    """
    Endpoint to check a media status

    :param payload: Data from JWT
    :type payload: dict
    :param media_id: Media ID
    :type media_id: str
    :return: Task ID or None
    :rtype: Set with Flask response values and data in JSON
    """
    ownsMediaId(payload, media_id)
    task_id = media_task_check(media_id, payload.get("user_id"))
    return jsonify(task_id)
