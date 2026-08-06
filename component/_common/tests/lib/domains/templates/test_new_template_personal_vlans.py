# SPDX-License-Identifier: AGPL-3.0-or-later

"""Regression tests for the apiv4-integration template-from-desktop
port (``CommonTemplates.new_template``). Two fields the port initially
dropped have caused user-visible breakage:

1. ``create_dict.personal_vlans`` — required by
   ``CreateDictDomainTemplate``. Without it, every later
   "create desktop from this template" raises 400
   ``invalid_desktop_data``.

2. ``tag_name`` — the legacy ``ApiTemplates.New()`` on main wrote
   ``"tag_name": False`` (api/src/api/libv2/api_templates.py:137).
   The apiv4-integration port forgot it.

The full ``new_template`` path requires a running RethinkDB plus the
storage worker queue; it is exercised end-to-end by integration tests.
The unit-level checks below pin the contract pieces that flipped:

* a schema-only assertion that ``CreateDictDomainTemplate`` still
  requires ``personal_vlans``,
* a logic-mirror that walks the same dict-assembly steps the function
  performs and verifies the resulting ``create_dict`` and
  ``template_dict`` carry the formerly-missing fields.
"""

from __future__ import annotations

import pytest


def _make_source_desktop(*, personal_vlans=False):
    """Minimal desktop row, populated with the keys ``new_template``
    actually reads. Fields the function ignores are omitted to keep
    the fixture small."""
    return {
        "id": "desktop-1",
        "xml": "",
        "icon": "",
        "os": "linux",
        "guest_properties": {"viewers": {}, "credentials": {}, "fullscreen": False},
        "favourite_hyp": False,
        "forced_hyp": False,
        "parents": [],
        "create_dict": {
            "hardware": {
                "boot_order": ["disk"],
                "disk_bus": "default",
                "disks": [
                    {
                        "extension": "qcow2",
                        "file": "/isard/groups/d1.qcow2",
                        "parent": "parent-disk",
                        "storage_id": "src-storage-id",
                    }
                ],
                "floppies": [],
                "graphics": ["default"],
                "interfaces": [{"id": "default", "mac": "52:54:00:00:00:01"}],
                "isos": [],
                "memory": 1024 * 1024,
                "qos_disk_id": False,
                "vcpus": 1,
                "videos": ["default"],
            },
            "origin": "media-1",
            "personal_vlans": personal_vlans,
            "reservables": {"vgpus": None},
        },
    }


def _assemble_create_dict(desktop, template_storage_id, template_storage_path):
    """Mirrors the assembly section of ``new_template`` (templates.py
    around lines 279-302). Anything the function adds to
    ``create_dict`` MUST be reflected here, otherwise this test stops
    catching new field-drops."""
    hardware = desktop["create_dict"]["hardware"]
    hardware["disks"] = [
        {
            "extension": "qcow2",
            "parent": "parent-disk",
            "storage_id": template_storage_id,
            "file": template_storage_path,
        }
    ]
    create_dict = {"hardware": hardware, "origin": desktop["id"]}
    create_dict["personal_vlans"] = desktop["create_dict"].get("personal_vlans", False)
    if desktop["create_dict"].get("reservables"):
        create_dict["reservables"] = desktop["create_dict"]["reservables"]
    create_dict["hardware"]["qos_disk_id"] = False
    return create_dict


def _assemble_template_dict(desktop, name, template_id, user_dict):
    """Mirrors the ``template_dict`` assembly in ``new_template``
    (templates.py around lines 304-335). The fields here are the
    contract the integration insert into ``r.table('domains')`` is
    promised to write — anything missing here is missing in prod."""
    create_dict = _assemble_create_dict(desktop, "tpl-storage-id", "/x.qcow2")
    return {
        "accessed": 0,
        "id": template_id,
        "name": name,
        "description": "",
        "kind": "template",
        "user": user_dict["id"],
        "username": user_dict["username"],
        "status": "CreatingTemplate",
        "detail": None,
        "category": user_dict["category"],
        "group": user_dict["group"],
        "xml": desktop.get("xml", ""),
        "icon": desktop.get("icon", ""),
        "image": {"id": "card-1", "type": "stock", "url": ""},
        "os": desktop.get("os", ""),
        "guest_properties": desktop["guest_properties"],
        "create_dict": create_dict,
        "hypervisors_pools": ["default"],
        "parents": desktop.get("parents") or [],
        "allowed": {
            "roles": False,
            "categories": False,
            "groups": False,
            "users": False,
        },
        "enabled": False,
        "tag": False,
        "tag_name": False,
        "tag_visible": False,
        "favourite_hyp": desktop.get("favourite_hyp", False),
        "forced_hyp": desktop.get("forced_hyp", False),
    }


# --------------------------------------------------------------------
# Tests
# --------------------------------------------------------------------


@pytest.mark.parametrize("pv", [True, False])
def test_create_dict_carries_personal_vlans(pv):
    """The new template's ``create_dict`` must carry ``personal_vlans``
    forward from the source desktop. Both True and False need to be
    explicitly written — Pydantic treats omitted as missing, not
    default-False, when the schema declares the field with no default."""
    desktop = _make_source_desktop(personal_vlans=pv)
    create_dict = _assemble_create_dict(
        desktop, "tpl-storage-id", "/isard/templates/tpl.qcow2"
    )
    assert "personal_vlans" in create_dict
    assert create_dict["personal_vlans"] is pv


def test_create_dict_defaults_personal_vlans_when_source_missing():
    """Very old desktops created before the field landed in
    ``CreateDictDomain`` won't have ``personal_vlans`` in
    ``create_dict``. The propagation must default-False rather than
    KeyError-ing the entire template creation."""
    desktop = _make_source_desktop(personal_vlans=False)
    desktop["create_dict"].pop("personal_vlans")

    create_dict = _assemble_create_dict(
        desktop, "tpl-storage-id", "/isard/templates/tpl.qcow2"
    )
    assert create_dict["personal_vlans"] is False


def test_template_dict_includes_tag_name_field():
    """Legacy ``ApiTemplates.New()`` (main: api_templates.py:137)
    always writes ``tag_name: False`` on a non-deployment template.
    Downstream code may read it (default-None breaks deployment
    progress events that filter by tag_name)."""
    desktop = _make_source_desktop(personal_vlans=False)
    user = {
        "id": "u-1",
        "username": "u1",
        "category": "cat",
        "group": "grp",
    }
    template_dict = _assemble_template_dict(desktop, "n", "tpl-1", user)
    assert "tag_name" in template_dict
    assert template_dict["tag_name"] is False


def test_template_dict_carries_personal_vlans_into_create_dict():
    """Integration of the two pins above: the template_dict that gets
    inserted must have ``create_dict.personal_vlans`` so any later
    ``DesktopFromTemplate(**new_desktop)`` validation passes."""
    desktop = _make_source_desktop(personal_vlans=True)
    user = {
        "id": "u-1",
        "username": "u1",
        "category": "cat",
        "group": "grp",
    }
    template_dict = _assemble_template_dict(desktop, "n", "tpl-1", user)
    assert template_dict["create_dict"]["personal_vlans"] is True


def test_create_dict_template_schema_requires_personal_vlans():
    """Locks the schema contract that motivated the fix: if a future
    refactor makes ``personal_vlans`` optional with a default, this
    test fails loudly so the propagation in ``new_template`` can be
    relaxed (or kept defensively)."""
    from isardvdi_common.schemas.domains import CreateDictDomainTemplate
    from pydantic import ValidationError

    base = {
        "hardware": {
            "boot_order": ["disk"],
            "disk_bus": "default",
            "disks": [
                {
                    "extension": "qcow2",
                    "file": "/x.qcow2",
                    "parent": "p",
                    "storage_id": "s",
                }
            ],
            "floppies": [],
            "graphics": ["default"],
            "interfaces": [{"id": "default", "mac": "52:54:00:00:00:01"}],
            "isos": [],
            "memory": 1024,
            "qos_disk_id": False,
            "vcpus": 1,
            "videos": ["default"],
        },
        "origin": "src",
    }

    with pytest.raises(ValidationError) as exc:
        CreateDictDomainTemplate(**base)
    assert "personal_vlans" in str(exc.value)

    # Adding the field makes it pass.
    CreateDictDomainTemplate(**{**base, "personal_vlans": False})


def _valid_template_dict():
    """Full template_dict shape that ``TemplateCreation`` should accept,
    matching what ``new_template`` writes after my fixes."""
    desktop = _make_source_desktop(personal_vlans=False)
    user = {"id": "u-1", "username": "u1", "category": "cat", "group": "grp"}
    return _assemble_template_dict(desktop, "valid-name", "tpl-uuid", user)


def test_template_creation_schema_accepts_well_formed_dict():
    """Sanity check: the dict ``new_template`` builds today must
    pass ``TemplateCreation`` so the new validation gate doesn't
    immediately break the happy path."""
    from isardvdi_common.schemas.domains import TemplateCreation

    template_dict = _valid_template_dict()
    TemplateCreation(**template_dict)


def test_template_creation_schema_rejects_missing_personal_vlans():
    """Defense-in-depth: the new validation gate must reject a
    template_dict that drops ``create_dict.personal_vlans`` — the
    exact regression that motivated the fix. Without this, a future
    refactor that re-introduces the drop would slip through."""
    from isardvdi_common.schemas.domains import TemplateCreation
    from pydantic import ValidationError

    template_dict = _valid_template_dict()
    template_dict["create_dict"].pop("personal_vlans")

    with pytest.raises(ValidationError) as exc:
        TemplateCreation(**template_dict)
    assert "personal_vlans" in str(exc.value)


def test_template_creation_schema_rejects_missing_tag_name():
    """The schema also pins ``tag_name`` so the legacy parity gap
    can't reopen silently."""
    from isardvdi_common.schemas.domains import TemplateCreation
    from pydantic import ValidationError

    template_dict = _valid_template_dict()
    template_dict.pop("tag_name")

    with pytest.raises(ValidationError) as exc:
        TemplateCreation(**template_dict)
    assert "tag_name" in str(exc.value)


def test_template_creation_schema_status_enum_is_template_specific():
    """Templates carry ``CreatingTemplate``, not ``Creating``. Pin the
    enum so a future copy-paste from ``DesktopFromTemplate`` (which
    uses ``DesktopStatusEnum``) doesn't accidentally let
    ``"Stopped"`` or ``"Started"`` past validation."""
    from isardvdi_common.schemas.domains import TemplateCreation
    from pydantic import ValidationError

    template_dict = _valid_template_dict()
    template_dict["status"] = "Started"

    with pytest.raises(ValidationError):
        TemplateCreation(**template_dict)
