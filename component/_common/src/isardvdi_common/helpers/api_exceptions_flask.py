#
#   Copyright © 2022 Josep Maria Viñolas Auquer
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

from flask import has_request_context, jsonify, request
from isardvdi_common.helpers.error_base import ErrorBase

# This module is the Flask-flavoured ``Error``. It only runs in Flask
# services (webapp, scheduler, notifier). The historical ``from api
# import app`` first-fallback dated from apiv3 and silently bound to
# apiv4's FastAPI ``app`` after the migration — FastAPI has no
# ``.logger`` attribute, so the class body crashed at import time when
# any Flask service was loaded inside the same uv workspace as apiv4.
try:
    from webapp import app
except Exception:
    try:
        from scheduler import app
    except Exception:
        from notifier import app


class Error(ErrorBase):
    logger = app.logger

    has_request_context = has_request_context

    request = request


@app.errorhandler(Error)
def handle_user_error(ex):
    response = jsonify(ex.error)
    response.status_code = ex.status_code
    response.headers = {"content-type": ex.content_type}
    return response
