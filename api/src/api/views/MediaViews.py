from api import app
import logging as log
import traceback

from uuid import uuid4
import time,json
import sys,os
from flask import request
from ..libv2.apiv2_exc import *
from ..libv2.quotas_exc import *


from ..libv2.quotas import Quotas
quotas = Quotas()

from ..libv2.api_media import ApiMedia
api_media = ApiMedia()

from .decorators import has_token

@app.route('/api/v3/media', methods=['GET'])
@has_token
def api_v3_admin_media(payload):
    try:
        medias = api_media.Get(payload)
        return json.dumps(medias), 200, {'Content-Type': 'application/json'}
    # except MediaNotFound:
    #     log.error("User "+id+" not in database.")
    #     return json.dumps({"code":1,"msg":"UserDesktops: User not exists in database"}), 404, {'Content-Type': 'application/json'}
    except UserMediaError:
        log.error("Media listing failed.")
        return json.dumps({"code":2,"msg":"MediaGet: list error"}), 404, {'Content-Type': 'application/json'}
    except Exception as e:
        error = traceback.format_exc()
        return json.dumps({"code":9,"msg":"MediaGet general exception: " + error }), 401, {'Content-Type': 'application/json'}
