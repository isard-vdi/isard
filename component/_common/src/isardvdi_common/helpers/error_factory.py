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

import os
import sys
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from isardvdi_common.helpers.error_base import ErrorBase as Error  # noqa: F401


def _has_apiv4() -> bool:
    for entry in sys.path:
        if entry and os.path.isfile(os.path.join(entry, "api", "services", "error.py")):
            return True
    return False


_has_api = _has_apiv4()
_Error = None
_resolving = False


def __getattr__(name):
    global _Error, _resolving
    if name != "Error":
        raise AttributeError(name)
    if _Error is not None:
        return _Error
    if _resolving:
        # Re-entrant access during apiv4 import. If api.services.error is
        # already in sys.modules (because jwt_token imported it before any
        # common helper), return the real class — callers that snapshot-bind
        # at module scope get the rich Error, not the base. Only fall back
        # to ErrorBase if api.services.error is genuinely not yet loaded.
        mod = sys.modules.get("api.services.error")
        if mod is not None:
            real = getattr(mod, "Error", None)
            if real is not None:
                return real
        from isardvdi_common.helpers.error_base import ErrorBase
        return ErrorBase
    _resolving = True
    try:
        if _has_api:
            # Only resolve the rich api.services.error.Error when it is
            # already present in sys.modules (i.e. apiv4 has fully imported
            # it).  If it is not there yet, we are most likely being called
            # during a transitive import chain that originates from a common
            # module — attempting importlib.import_module("api.services.error")
            # at that point would trigger api/__init__.py which re-imports
            # common modules that are still partially initialised, causing a
            # circular-import crash.
            #
            # Returning ErrorBase here is safe: _Error is left as None, so
            # the next call (after apiv4 has finished loading) will find
            # api.services.error in sys.modules and cache the real class.
            api_error_mod = sys.modules.get("api.services.error")
            if api_error_mod is None:
                from isardvdi_common.helpers.error_base import ErrorBase

                return ErrorBase

            _E = api_error_mod.Error
        else:
            from isardvdi_common.helpers.error_base import ErrorBase as _E
        _Error = _E
        return _Error
    finally:
        _resolving = False
