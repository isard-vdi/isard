#
#   Copyright © 2025 IsardVDI
#
#   SPDX-License-Identifier: AGPL-3.0-or-later

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class UserNetworkAllowed(BaseModel):
    roles: Any = Field(
        default=False,
        description="Roles allowed access. False = owner only, [] = everyone.",
    )
    categories: Any = Field(
        default=False,
        description="Categories allowed access. False = none, [] = all.",
    )
    groups: Any = Field(
        default=False,
        description="Groups allowed access. False = none, [] = all.",
    )
    users: List[str] = Field(
        default_factory=list,
        description="Specific user IDs allowed access.",
    )


class CreateUserNetworkRequest(BaseModel):
    name: str = Field(
        description="Name of the network.",
        min_length=1,
        max_length=100,
    )
    description: str = Field(
        default="",
        description="Description of the network.",
    )
    model: str = Field(
        default="virtio",
        description="Network model (e.g., virtio).",
    )
    qos_id: str = Field(
        default="unlimited",
        description="QoS rule ID.",
    )
    allowed: Optional[UserNetworkAllowed] = Field(
        default=None,
        description="Access control schema. If omitted, defaults to owner-only.",
    )


class UpdateUserNetworkRequest(BaseModel):
    name: Optional[str] = Field(
        default=None,
        description="Name of the network.",
        min_length=1,
        max_length=100,
    )
    description: Optional[str] = Field(
        default=None,
        description="Description of the network.",
    )
    qos_id: Optional[str] = Field(
        default=None,
        description="QoS rule ID.",
    )
    allowed: Optional[UserNetworkAllowed] = Field(
        default=None,
        description="Access control schema.",
    )


class UserNetworkResponse(BaseModel):
    id: str
    name: str
    description: str = ""
    kind: str = "user_network"
    model: str = "virtio"
    qos_id: str = "unlimited"
    metadata_id: int = 0
    allowed: Optional[Dict[str, Any]] = None
    user: str = ""
    group: str = ""
    category: str = ""
    created: Optional[str] = None
    modified: Optional[str] = None


class UserNetworkListResponse(BaseModel):
    networks: List[UserNetworkResponse] = Field(
        description="List of user networks.",
    )
