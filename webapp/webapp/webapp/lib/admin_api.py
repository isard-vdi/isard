# Copyright 2017 the Isard-vdi project authors:
#      Josep Maria Viñolas Auquer
#      Alberto Larraz Dalmases
# License: AGPLv3

import os
import pickle
import tarfile

from rethinkdb import RethinkDB
from werkzeug.utils import secure_filename

from webapp import app

from ..lib.log import *

r = RethinkDB()
from .flask_rethink import RDB

db = RDB(app)
db.init_app(app)

from flask_login import current_user


def get_login_path():
    with app.app_context():
        category = (
            r.table("categories")
            .get(current_user.category)
            .pluck("id", "name", "frontend", "custom_url_name")
            .run(db.conn)
        )
    if category.get("frontend", False):
        return "/login/"
    else:
        return "/login/" + category.get("custom_url_name")
