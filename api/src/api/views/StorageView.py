# Copyright 2017 the Isard-vdi project authors:
#      Josep Maria Viñolas Auquer
#      Alberto Larraz Dalmases
# License: AGPLv3

import json
import logging as log

from api import app

from ..libv2.api_storage import get_disks, parse_disks
from .decorators import has_token


@app.route("/api/v3/storage/<status>", methods=["GET"])
@has_token
def api_v3_storage(payload, status):

    disks = get_disks(
        payload["user_id"],
        pluck=[
            "id",
            "user_id",
            "user_name",
            {"qemu-img-info": {"virtual-size": True, "actual-size": True}},
            "status_logs",
        ],
        status=status,
    )

    disks = parse_disks(disks)

    return (
        json.dumps(disks),
        200,
        {"Content-Type": "application/json"},
    )
