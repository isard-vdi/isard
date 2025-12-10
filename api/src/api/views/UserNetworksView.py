# Copyright 2017 the Isard-vdi project authors:
#      Josep Maria Viñolas Auquer
#      Alberto Larraz Dalmases
# License: AGPLv3

import json

from flask import request

#!flask/bin/python
# coding=utf-8
from api import app

from ..libv2.api_user_networks import (
    create_user_network,
    delete_user_network,
    get_user_network,
    get_user_networks,
    update_user_network,
)
from .decorators import has_token


@app.route("/api/v3/user/networks", methods=["GET"])
@has_token
def api_v3_user_networks_list(payload):
    """List all user networks accessible to the current user."""
    networks = get_user_networks(payload)
    return json.dumps(networks), 200, {"Content-Type": "application/json"}


@app.route("/api/v3/user/networks/<network_id>", methods=["GET"])
@has_token
def api_v3_user_network_get(payload, network_id):
    """Get a specific user network."""
    network = get_user_network(network_id, payload)
    return json.dumps(network), 200, {"Content-Type": "application/json"}


@app.route("/api/v3/user/networks", methods=["POST"])
@has_token
def api_v3_user_network_create(payload):
    """Create a new user network."""
    data = request.get_json(force=True)
    network = create_user_network(data, payload)
    return json.dumps(network), 201, {"Content-Type": "application/json"}


@app.route("/api/v3/user/networks/<network_id>", methods=["PUT"])
@has_token
def api_v3_user_network_update(payload, network_id):
    """Update a user network."""
    data = request.get_json(force=True)
    network = update_user_network(network_id, data, payload)
    return json.dumps(network), 200, {"Content-Type": "application/json"}


@app.route("/api/v3/user/networks/<network_id>", methods=["DELETE"])
@has_token
def api_v3_user_network_delete(payload, network_id):
    """Delete a user network."""
    delete_user_network(network_id, payload)
    return json.dumps({}), 200, {"Content-Type": "application/json"}
