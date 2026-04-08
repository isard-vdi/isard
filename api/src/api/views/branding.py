#
#   Copyright © 2026 Simó Albert i Beltran
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

from api.libv2.validators import _validate_item
from api.views.decorators import check_permissions
from flask import jsonify, request
from isardvdi_common.api_exceptions import Error
from isardvdi_common.category import Category

from api import app


@app.route("/api/v3/admin/category/<category_id>/branding", methods=["GET"])
@check_permissions("branding")
def _api_category_branding_get(payload, category_id):
    """
    Endpoint to retrieve branding configuration for a category.

    :param payload: Data from JWT
    :type payload: dict
    :param category_id: Category id
    :type category_id: str
    :return: Branding configuration as JSON
    :rtype: flask.Response
    """
    return jsonify(Category(category_id).branding)


@app.route("/api/v3/admin/category/<category_id>/branding", methods=["PUT"])
@check_permissions("branding")
def _api_category_branding_put(payload, category_id):
    """
    Endpoint to update branding configuration for a category.

    :param payload: Data from JWT
    :type payload: dict
    :param category_id: Category id
    :type category_id: str
    :return: True as JSON
    :rtype: flask.Response
    """
    try:
        Category(category_id).branding = _validate_item(
            "category_branding_update", request.get_json()
        )
    except ValueError as exception:
        raise Error(error="conflict", description=exception)

    return jsonify({"success": True})
