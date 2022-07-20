import json

from flask import request
from rethinkdb import RethinkDB

from api import app

from ..libv2.api_media import ApiMedia
from ..libv2.flask_rethink import RDB
from .decorators import has_token, ownsCategoryId

r = RethinkDB()
db = RDB(app)
db.init_app(app)

api_media = ApiMedia()


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
