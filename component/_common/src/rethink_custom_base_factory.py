#
#   IsardVDI - Open Source KVM Virtual Desktops based on KVM Linux and dockers
#   Copyright (C) 2023 Simó Albert i Beltran
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

import importlib

if importlib.util.find_spec("api") is not None:
    from api.libv2.rethink_custom_base import RethinkCustomBase
elif importlib.util.find_spec("engine") is not None:
    from engine.models.rethink_custom_base import RethinkCustomBase
elif importlib.util.find_spec("isardvdi_core_worker") is not None:
    from isardvdi_core_worker.rethink_custom_base import RethinkCustomBase
