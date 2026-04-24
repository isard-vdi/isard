#
#   IsardVDI - Open Source KVM Virtual Desktops based on KVM Linux and dockers
#   Copyright (C) 2026 IsardVDI
#
#   This program is free software: you can redistribute it and/or modify
#   it under the terms of the GNU Affero General Public License as published by
#   the Free Software Foundation, either version 3 of the License, or
#   (at your option) any later version.
#
#   This program is distributed in the hope that it will be useful,
#   but WITHOUT ANY WARRANTY; without even the implied warranty of
#   MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#   GNU Affero General Public License for more details.
#
#   You should have received a copy of the GNU Affero General Public License
#   along with this program.  If not, see <https://www.gnu.org/licenses/>.
#
# SPDX-License-Identifier: AGPL-3.0-or-later

import os
from urllib.parse import urlparse, urlunparse

RQ_DB = 0
SESSIONS_DB = 1
CHANGEFEED_DB = 2
SOCKETIO_DB = 3


def _base_url() -> str:
    url = os.environ.get("REDIS_URL")
    if url:
        return url
    host = os.environ.get("REDIS_HOST", "isard-redis")
    port = os.environ.get("REDIS_PORT", "6379")
    password = os.environ.get("REDIS_PASSWORD", "")
    return f"redis://:{password}@{host}:{port}"


def _with_db(db: int) -> str:
    parsed = urlparse(_base_url())
    return urlunparse(parsed._replace(path=f"/{db}"))


def rq_url() -> str:
    return _with_db(RQ_DB)


def changefeed_url() -> str:
    return _with_db(CHANGEFEED_DB)


def socketio_url() -> str:
    return _with_db(SOCKETIO_DB)
