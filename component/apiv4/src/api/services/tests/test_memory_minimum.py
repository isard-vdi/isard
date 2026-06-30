#
#   Copyright © 2026 IsardVDI
#
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Memory round-to-minimum casuistics across the create/edit flows.

Two complementary layers enforce the 25 MiB engine floor:

* Request schemas (``DomainHardware`` / ``MediaHardware``, ``ge=0.025`` GiB)
  reject an explicitly-too-small value with a 422 before the lib runs.
* ``Helpers.memory_gib_to_kib`` rounds a value *inherited* from a template up
  to the floor (those never pass through the request schema), so installs
  holding sub-minimum RAM keep working instead of being rejected.

Per flow the contract is therefore: specify <min -> 422; specify >=min ->
stored as sent; inherit a sub-min template -> rounded up to the floor.
"""

from typing import get_args

import pytest
from api.schemas.deployments import (
    CreateDeploymentRequest,
    DeploymentDesktopEditRequest,
    DeploymentEditRequest,
)
from api.schemas.domains.desktops import (
    BulkCreatePersistentDesktopsRequest,
    CreateDesktopFromMedia,
    CreateDesktopRequest,
    DesktopEditRequest,
)
from api.schemas.domains.hardware import DomainHardware, MediaHardware
from api.schemas.domains.templates import NewTemplateRequest, TemplateEditRequest
from isardvdi_common.helpers.helpers import Helpers
from pydantic import ValidationError

MIN_GIB = 0.025
MIN_KIB = 25600  # engine set_memory floor: 25 MiB

# Required fields for a valid MediaHardware (all but memory).
_MEDIA_BASE = {
    "boot_order": ["disk"],
    "disk_bus": "virtio",
    "disk_size": 10,
    "interfaces": ["default"],
    "vcpus": 2,
    "videos": ["default"],
}


def _resolve_model(annotation):
    """Unwrap Optional[X] / X -> X (the underlying schema class)."""
    args = [a for a in get_args(annotation) if a is not type(None)]
    return args[0] if args else annotation


class TestHardwareSchemaMemoryMinimum:
    """The schemas every request body delegates to enforce ge=0.025 GiB."""

    def test_domain_hardware_rejects_sub_minimum(self):
        with pytest.raises(ValidationError):
            DomainHardware(memory=0.01)

    def test_domain_hardware_accepts_boundary(self):
        assert DomainHardware(memory=MIN_GIB).memory == MIN_GIB

    def test_domain_hardware_keeps_value_above_minimum(self):
        assert DomainHardware(memory=2.0).memory == 2.0

    def test_domain_hardware_default_is_one_gib(self):
        assert DomainHardware().memory == 1

    def test_media_hardware_rejects_sub_minimum(self):
        with pytest.raises(ValidationError):
            MediaHardware(memory=0.01, **_MEDIA_BASE)

    def test_media_hardware_accepts_boundary(self):
        assert MediaHardware(memory=MIN_GIB, **_MEDIA_BASE).memory == MIN_GIB

    def test_media_hardware_keeps_value_above_minimum(self):
        assert MediaHardware(memory=2.0, **_MEDIA_BASE).memory == 2.0


# Create/edit request bodies that DO take a hardware override, and the
# hardware schema each delegates to (which enforces the minimum).
REQUEST_BODIES = [
    (CreateDesktopRequest, DomainHardware),
    (DesktopEditRequest, DomainHardware),
    (CreateDesktopFromMedia, MediaHardware),
    (TemplateEditRequest, DomainHardware),
    (DeploymentDesktopEditRequest, DomainHardware),
]


class TestRequestBodiesInheritTheMinimum:
    """Each flow's request body routes ``hardware`` through a min-enforcing
    schema, so an explicit sub-min memory is a 422 at the API boundary."""

    @pytest.mark.parametrize(
        "request_cls,hardware_cls",
        REQUEST_BODIES,
        ids=[c.__name__ for c, _ in REQUEST_BODIES],
    )
    def test_hardware_field_enforces_minimum(self, request_cls, hardware_cls):
        assert _resolve_model(request_cls.model_fields["hardware"].annotation) is (
            hardware_cls
        )

    def test_deployment_create_desktops_use_desktop_request(self):
        """Deployment create validates each desktop via CreateDesktopRequest,
        so it inherits the DomainHardware minimum transitively."""
        element = _resolve_model(
            get_args(CreateDeploymentRequest.model_fields["desktops"].annotation)[0]
        )
        assert element is CreateDesktopRequest


class TestFlowsWithoutExplicitRamInheritOnly:
    """Bulk-create and template-create take no hardware override — RAM is
    inherited from the source template/desktop — so they can only round (via
    the helper), never 422 on a sub-min RAM."""

    @pytest.mark.parametrize(
        "request_cls",
        [BulkCreatePersistentDesktopsRequest, NewTemplateRequest],
        ids=["BulkCreatePersistentDesktopsRequest", "NewTemplateRequest"],
    )
    def test_no_hardware_field(self, request_cls):
        assert "hardware" not in request_cls.model_fields


class TestLegacyDeploymentFlatEditHasNoMinimum:
    """The apiv3 flat deployment edit takes ``hardware`` as a raw dict (no
    schema), so a sub-min value is not rejected — it is rounded later by the
    lib instead. This documents the one path that rounds rather than 422s."""

    def test_flat_hardware_is_an_unvalidated_dict(self):
        assert _resolve_model(
            DeploymentEditRequest.model_fields["hardware"].annotation
        ) is (dict)


class TestMemoryRoundsToMinimum:
    """``Helpers.memory_gib_to_kib`` — the conversion every create/edit service
    applies (e.g. the media service in api/services/desktops.py)."""

    def test_inherited_sub_minimum_is_rounded_up(self):
        assert Helpers.memory_gib_to_kib(8 / 1048576) == MIN_KIB  # 8 KiB template

    def test_value_above_minimum_is_passed_through(self):
        assert Helpers.memory_gib_to_kib(2.0) == 2097152
        assert Helpers.memory_gib_to_kib(8.0) == 8388608

    def test_explicit_sub_minimum_rounds_at_helper_level(self):
        assert Helpers.memory_gib_to_kib(0.01) == MIN_KIB

    def test_boundary_is_above_the_floor(self):
        assert Helpers.memory_gib_to_kib(MIN_GIB) == int(MIN_GIB * 1048576)
