#
#   Copyright © 2025 IsardVDI
#
#   SPDX-License-Identifier: AGPL-3.0-or-later

from typing import Any, Dict, List, Optional

from pydantic import BaseModel


class CardResponse(BaseModel):
    """Single card response"""

    id: str
    url: str
    type: str


class GenerateCardRequest(BaseModel):
    """Request to generate a default card"""

    desktop_id: str
    desktop_name: str
