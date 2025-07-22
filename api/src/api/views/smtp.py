#
#   Copyright © 2025 Simó Albert i Beltran
#
#   This file is part of IsardVDI.
#
#   IsardVDI is free software: you can redistribute it and/or modify
#   it under the terms of the GNU Affero General Public License as published by
#   the Free Software Foundation, either version 3 of the License, or (at your
#   option) any later version.
#
#   IsardVDI is distributed in the hope that it will be useful, but WITHOUT ANY
#   WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS
#   FOR A PARTICULAR PURPOSE. See the GNU General Public License for more
#   details.
#
#   You should have received a copy of the GNU Affero General Public License
#   along with IsardVDI. If not, see <https://www.gnu.org/licenses/>.
#
# SPDX-License-Identifier: AGPL-3.0-or-later

from smtplib import SMTP

from cachetools import TTLCache, cached
from flask import jsonify, request
from isardvdi_common.configuration import Configuration

from api import app

from ..libv2.validators import _validate_item
from .decorators import is_admin


@cached(cache=TTLCache(maxsize=1, ttl=5))
@app.route("/api/v3/smtp", methods=["GET"])
@is_admin
def _api_smtp_get(payload):
    """
    Endpoint to retrieve SMTP configuration.

    :param payload: Data from JWT
    :type payload: dict
    :return: SMTP configuration as JSON
    :rtype: flask.Response
    """
    return jsonify(_validate_item("smtp", Configuration.smtp))


@app.route("/api/v3/smtp", methods=["PUT"])
@is_admin
def _api_smtp_put(payload):
    """
    Endpoint save STMP configuration. Body should content JSON with the configuration
    as key/value.

    :param payload: Data from JWT
    :type payload: dict
    :return: Saved configuration as JSON
    :rtype: flask.Response
    """
    Configuration.smtp = _validate_item("smtp", request.get_json())
    return jsonify(_validate_item("smtp", Configuration.smtp))


@cached(cache=TTLCache(maxsize=1, ttl=5))
@app.route("/api/v3/smtp/enabled", methods=["GET"])
@is_admin
def _api_smtp_enabled_get(payload):
    """
    Endpoint to retrieve if STMP configuration is enabled.

    :param payload: Data from JWT
    :type payload: dict
    :return: Boolean about if SMTP configuration is enabled as JSON
    :rtype: flask.Response
    """
    return jsonify(Configuration.smtp.get("enabled", False))
