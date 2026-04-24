#
#   Copyright © 2025 IsardVDI
#
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Pydantic schemas for the ``/admin/quota`` admin endpoints. The
underlying ``Quotas`` helper returns slightly different shapes for
user / category / group lookups (group adds ``grouplimits``,
category may have ``limits=False``), so the response is intentionally
loose — it accepts whatever dict the common helper produces and
documents the common keys for OpenAPI consumers.
"""

from typing import Any, Dict, Optional, Union

from pydantic import BaseModel, Field


class AdminQuotaResponse(BaseModel):
    """Configured quota / limits for a user, category or group.

    The shape varies by ``kind``: user lookups return ``quota`` +
    ``limits``; category lookups return ``quota`` + ``limits``; group
    lookups additionally include ``grouplimits``. ``Quotas.Get*Quota``
    in the common helper is the source of truth.
    """

    quota: Union[bool, Dict[str, Any]] = Field(
        description=(
            "Quota dict (desktops, templates, vcpus, memory, ...) or "
            "``False`` if no quota is configured."
        ),
    )
    limits: Union[bool, Dict[str, Any]] = Field(
        default=False,
        description=(
            "Limits dict (the maximum the entity may set its own quota "
            "to) or ``False`` if no limits apply."
        ),
    )
    grouplimits: Optional[Union[bool, Dict[str, Any]]] = Field(
        default=None,
        description=("Group-level limits, only present on group quota lookups."),
    )

    class Config:
        # Allow extra keys so that any future field added by the common
        # ``Quotas`` helper passes through without a schema migration.
        extra = "allow"
