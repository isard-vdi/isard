#
#   IsardVDI - Open Source KVM Virtual Desktops based on KVM Linux and dockers
#   Copyright (C) 2025 Simó Albert i Beltran
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

from importlib.util import find_spec

# Route Error to the right concrete class depending on which service imports
# this. apiv4 (FastAPI) exposes api.services.error; services that don't
# expose that module fall back to the framework-neutral ErrorBase.
api_spec = find_spec("api")
if api_spec and find_spec("api.services.error"):
    from api.services.error import Error  # apiv4 (FastAPI)
else:
    from isardvdi_common.helpers.error_base import ErrorBase as Error
