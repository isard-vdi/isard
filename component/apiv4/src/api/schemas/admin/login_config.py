#
#   Copyright © 2025 IsardVDI
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

from typing import Any, Dict, Optional

from pydantic import BaseModel, ConfigDict


class AdminLoginConfigResponse(BaseModel):
    """Raw response for the admin login-config read endpoints.

    Returned by ``GET /admin/login-config`` (global) and
    ``GET /admin/login-config/{category_id}`` (per-category — the
    service falls back to the global config when the category has no
    overrides). Permissive shape because the underlying
    ``Configuration.login`` blob is admin-edited freeform; the public
    ``LoginConfigResponse`` (in ``api.schemas.login``) typed each field
    individually for the consumer side, but the admin edit modal needs
    the unmerged raw payload.
    """

    model_config = ConfigDict(extra="allow")


class LoginNotificationUpdateRequest(BaseModel):
    """Request to update login notification configuration"""

    cover: Optional[Dict[str, Any]] = None
    form: Optional[Dict[str, Any]] = None


class LoginNotificationEnableRequest(BaseModel):
    """Request to enable or disable a login notification"""

    enabled: bool
