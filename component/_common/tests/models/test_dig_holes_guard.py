# SPDX-License-Identifier: AGPL-3.0-or-later

"""dig_holes parks a disk only when the registry admits it, and says why not."""

from types import SimpleNamespace
from unittest.mock import PropertyMock, patch

import pytest
from isardvdi_common.models.storage import Storage


def _domain(kind="desktop", status="Stopped", domain_id="d1"):
    return SimpleNamespace(id=domain_id, kind=kind, status=status)


def _park(
    domains, perms=("r", "w"), children=(), deleted_children=(), action="dig_holes"
):
    storage = Storage.__new__(Storage)
    object.__setattr__(storage, "id", "s1")
    object.__setattr__(storage, "status", "ready")
    object.__setattr__(storage, "perms", list(perms))
    asked = []
    claims = []

    def _get_children(cls, storage_ids, include_deleted=False):
        asked.append(include_deleted)
        return list(children) + (list(deleted_children) if include_deleted else [])

    def _claim(doc_id, update_data, *, field, values, validate=True):
        claims.append((doc_id, field, tuple(values)))
        return True

    with (
        patch.object(
            Storage, "domains", new_callable=PropertyMock, return_value=domains
        ),
        patch.object(Storage, "get_children", classmethod(_get_children)),
        patch.object(
            Storage, "children", new_callable=PropertyMock, return_value=list(children)
        ),
        patch.object(Storage, "update_document_if", staticmethod(_claim)),
        patch.object(Storage, "_update_cache"),
        patch.object(
            Storage, "__setattr__", lambda self, k, v: object.__setattr__(self, k, v)
        ),
        patch(
            "isardvdi_common.models.domain.Domain.update_document_if",
            return_value=True,
        ),
    ):
        try:
            storage.set_maintenance(action)
        except Exception as exc:
            return exc.error["description_code"], claims, asked
    return None, claims, asked


def test_a_stopped_desktops_leaf_disk_is_parked_with_a_guarded_claim():
    code, claims, asked = _park([_domain()])
    assert code is None
    assert claims == [("s1", "status", ("ready",))]
    assert asked == [True]


@pytest.mark.parametrize(
    "kwargs, code",
    [
        ({"domains": [_domain("template")]}, "storage_used_by_template"),
        (
            {"domains": [_domain(), _domain("template", domain_id="t1")]},
            "storage_used_by_template",
        ),
        ({"domains": []}, "storage_not_used_by_any_domain"),
        ({"domains": [_domain()], "perms": ("r",)}, "storage_read_only"),
        ({"domains": [_domain(status="Started")]}, "storage_open_by_running_desktop"),
        ({"domains": [_domain()], "children": ["c"]}, "storage_has_children"),
        (
            {"domains": [_domain()], "deleted_children": ["gone"]},
            "storage_has_children",
        ),
    ],
    ids=[
        "template",
        "desktop-and-template",
        "no-domain",
        "read-only",
        "running",
        "child",
        "deleted-child",
    ],
)
def test_a_refused_dig_parks_nothing_and_says_why(kwargs, code):
    refused, claims, _ = _park(**kwargs)
    assert refused == code
    assert claims == []


@pytest.mark.parametrize(
    "action",
    [
        "migrate",
        "purge",
        "find",
        "check_backing_chain",
        "check_integrity",
        "derive",
        "template_from_desktop",
    ],
)
def test_a_label_that_does_not_park_a_disk_is_refused_before_any_claim(action):
    code, claims, _ = _park([_domain(status="Started")], children=["c"], action=action)
    assert code == "storage_invalid_maintenance_action"
    assert claims == []
