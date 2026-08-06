# SPDX-License-Identifier: AGPL-3.0-or-later

"""``boot_order`` on the desktop-from-media input.

The endpoint validated its input against a schema looser than the one every
later stage uses, so it answered 201 for desktops that could never be finished.
``MediaHardware.boot_order`` was a bare ``list[str]`` while the same file and the
shared domain schemas constrain it to ``iso|floppy|disk|pxe``. A desktop created
with ``boot_order=["cdrom"]`` existed and started fine, and only refused to
become a template: ``Input should be 'iso', 'floppy', 'disk' or 'pxe'`` — usable
but permanently un-templatable, with nothing telling the user why.
"""

import pytest
from api.schemas.domains.hardware import MediaHardware
from pydantic import ValidationError


def _hardware(**overrides):
    base = {
        "boot_order": ["disk"],
        "disk_bus": "virtio",
        "disk_size": 5,
        "interfaces": ["default"],
        "memory": 1,
        "vcpus": 1,
        "videos": ["default"],
    }
    base.update(overrides)
    return base


@pytest.mark.parametrize("value", ["disk", "iso", "floppy", "pxe"])
def test_every_value_the_domain_schemas_accept_is_accepted(value):
    assert MediaHardware(**_hardware(boot_order=[value])).boot_order == [value]


@pytest.mark.parametrize("value", ["cdrom", "hd", ""])
def test_a_value_the_later_stages_reject_is_refused_here(value):
    with pytest.raises(ValidationError):
        MediaHardware(**_hardware(boot_order=[value]))
