#
#   Copyright © 2023 Miriam Melina Gamboa Valdez
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
from flask import Blueprint, Flask
from spectree import SpecTree

print("Starting notifier...")

app = Flask(__name__, template_folder="templates")
app_bp = Blueprint("notifier", __name__)
app.register_blueprint(app_bp, url_prefix="/notifier/api/v1")
api = SpecTree("flask", annotations=True, title="Notifier API", version="v1.0")
api.register(app)

from .views import views
