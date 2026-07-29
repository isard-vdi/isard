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

from typing import Any, Optional

from isardvdi_common.models.domain import DomainModel
from isardvdi_common.models.media import MediaModel
from isardvdi_common.schemas.domains import DomainKindEnum
from isardvdi_common.schemas.media import MediaKindEnum
from pydantic import BaseModel, ConfigDict, Field, create_model, model_validator


class DownloadsOverviewResponse(BaseModel):
    """Response shape for ``GET /admin/items/downloads``.

    The service returns ``{}`` after the registration check passes;
    keeping a typed empty model documents the contract explicitly so
    callers don't expect a payload.
    """

    pass


class DownloadItem(BaseModel):
    """One row of ``GET /admin/items/downloads/{kind}``.

    The shape varies per kind (domains/media merge in registry rows,
    virt_install/videos/viewers come straight from the upstream
    updates server). Permissive (``ConfigDict(extra="allow")``) so all
    five kinds round-trip without schema fragmentation; the webapp
    admin renders fields per-kind.
    """

    model_config = ConfigDict(extra="allow")

    id: Optional[str] = None
    name: Optional[str] = None
    description: Optional[str] = None


# The entries the updates registry serves are inserted almost verbatim
# into ``domains`` / ``media``, so a malformed one does not fail here: it
# creates a row the installation cannot show. A domain whose kind is
# outside the taxonomy falls out of every kind-scoped query, leaving a
# desktop its owner never sees and cannot delete while it holds a disk.
#
# The accepted keys are therefore DERIVED from the row models rather than
# restated: a field added to ``DomainModel`` / ``MediaModel`` is accepted
# from the registry on the next release without touching this file, and
# one removed stops being accepted. Only the values that decide whether
# the row is reachable at all are typed; everything else the registry
# ships is passed through untouched, because these models VALIDATE and
# are never dumped back onto the payload.

# Keys the registry ships that are not fields of the row model: the
# download source, and the virtio defaults some media entries carry.
# ``new`` is added by our own listing before validation runs, not published by
# the registry (verified against a live one: it serves neither ``new`` nor
# ``status``). The bulk download path then selects on it, so forbidding it would
# refuse every entry while the code still depended on it.
_LISTING_ADDED_KEYS = ("new",)
_REGISTRY_ONLY_DOMAIN_KEYS = _LISTING_ADDED_KEYS + ("url-isard", "url-web")
_REGISTRY_ONLY_MEDIA_KEYS = _LISTING_ADDED_KEYS + (
    "default-virtio-iso",
    "default-virtio-fd",
)


def _derive_registry_model(
    name: str,
    row_model: type[BaseModel],
    registry_only_keys: tuple[str, ...],
    kind_annotation: type,
) -> type[BaseModel]:
    """Build the gate for one registry kind out of its row model."""
    fields: dict = {}
    for field_name, info in row_model.model_fields.items():
        if field_name == "kind":
            fields[field_name] = (kind_annotation, ...)
            continue
        fields[field_name] = (
            Any,
            Field(default=None, alias=info.alias) if info.alias else None,
        )
    for key in registry_only_keys:
        fields[key.replace("-", "_")] = (Any, Field(default=None, alias=key))
    return create_model(
        name,
        __config__=ConfigDict(extra="forbid", populate_by_name=True),
        **fields,
    )


class RegistryDomainEntry(  # type: ignore[misc]
    _derive_registry_model(
        "_RegistryDomainEntryBase",
        DomainModel,
        _REGISTRY_ONLY_DOMAIN_KEYS,
        DomainKindEnum,
    )
):
    """One ``domains`` entry as the updates registry serves it."""

    @model_validator(mode="after")
    def _has_a_download_source(self):
        if not self.url_isard and not self.url_web:
            raise ValueError("needs a url-isard or a url-web to download from")
        return self

    @model_validator(mode="after")
    def _carries_what_the_download_indexes(self):
        # The download path subscripts these without guarding, so a
        # missing one is a 500 raised after rows have been written.
        create_dict = self.create_dict
        if not isinstance(create_dict, dict):
            raise ValueError("needs a create_dict")
        if not isinstance(create_dict.get("hypervisors_pools"), list):
            raise ValueError("needs a create_dict.hypervisors_pools list")
        hardware = create_dict.get("hardware")
        if not isinstance(hardware, dict):
            raise ValueError("needs a create_dict.hardware")
        if not isinstance(hardware.get("interfaces"), list):
            raise ValueError("needs a create_dict.hardware.interfaces list")
        return self


class RegistryMediaEntry(  # type: ignore[misc]
    _derive_registry_model(
        "_RegistryMediaEntryBase",
        MediaModel,
        _REGISTRY_ONLY_MEDIA_KEYS,
        MediaKindEnum,
    )
):
    """One ``media`` entry as the updates registry serves it."""

    @model_validator(mode="after")
    def _has_a_download_source(self):
        if not self.url_isard and not self.url_web:
            raise ValueError("needs a url-isard or a url-web to download from")
        return self


REGISTRY_ENTRY_MODELS = {
    "domains": RegistryDomainEntry,
    "private_domains": RegistryDomainEntry,
    "media": RegistryMediaEntry,
    "private_media": RegistryMediaEntry,
}
