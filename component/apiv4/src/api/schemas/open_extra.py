#
#   Copyright © 2025 IsardVDI
#
#   SPDX-License-Identifier: AGPL-3.0-or-later

from typing import Any, Dict, List, Optional

from pydantic import BaseModel


class CategoryResponse(BaseModel):
    """Public category response"""

    id: str
    name: Optional[str] = None
    frontend: Optional[bool] = None
    custom_url_name: Optional[str] = None
    photo: Optional[str] = None


class LoginConfigResponse(BaseModel):
    """Login configuration response"""

    notification_cover: Optional[Dict[str, Any]] = None
    notification_form: Optional[Dict[str, Any]] = None
