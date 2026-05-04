#
#   Copyright © 2026 IsardVDI
#
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Unit tests for ``Helpers.owns_domain_id`` — template-allowed branch.

The new-desktop form in old-frontend calls
``GET /item/desktop/{id}/get-info`` for *templates* too (the URL says
"desktop" but the same handler serves both kinds). Without the
template-allowed branch, an advanced user with a template shared via
the alloweds mechanism gets ``forbidden / not_enough_rights_desktop``
when previewing the template in the new-desktop form.
"""

import pytest


@pytest.fixture
def patched_caches(monkeypatch):
    from isardvdi_common.helpers import alloweds as alloweds_mod
    from isardvdi_common.helpers import helpers as mod

    captured = {}

    def fake_get_document(table, item_id, fields=None):
        captured.setdefault("calls", []).append((table, item_id, fields))
        return captured.get("return")

    monkeypatch.setattr(mod.Caches, "get_document", staticmethod(fake_get_document))

    # ``Alloweds.is_allowed`` walks ``allowed.groups`` via
    # ``check_secondary_groups``, which hits rdb (``get_user`` +
    # ``get_all_linked_groups``). For the unit-test path we want plain
    # set-membership: True iff the user's primary group is in the
    # template's allowed groups.
    monkeypatch.setattr(
        alloweds_mod.Alloweds,
        "check_secondary_groups",
        classmethod(
            lambda cls, user_id, user_group_id, item_allowed_groups: (
                user_group_id in item_allowed_groups
            )
        ),
    )

    return {"mod": mod, "captured": captured}


def _payload(
    role_id="advanced", user_id="alice", category_id="cat-a", group_id="grp-a"
):
    return {
        "role_id": role_id,
        "user_id": user_id,
        "category_id": category_id,
        "group_id": group_id,
    }


def _template(
    *,
    owner="bob",
    category="cat-other",
    allowed_users=None,
    allowed_groups=None,
    allowed_categories=None,
    allowed_roles=None,
):
    return {
        "id": "tmpl-1",
        "kind": "template",
        "user": owner,
        "category": category,
        "tag": None,
        "allowed": {
            "users": allowed_users if allowed_users is not None else False,
            "groups": allowed_groups if allowed_groups is not None else False,
            "categories": (
                allowed_categories if allowed_categories is not None else False
            ),
            "roles": allowed_roles if allowed_roles is not None else False,
        },
    }


class TestOwnsDomainIdTemplateAlloweds:
    def test_template_shared_with_user_via_users_list_grants_access(
        self, patched_caches
    ):
        # An advanced user not owning the template but explicitly listed
        # in ``allowed.users`` must pass — this is the new-desktop form
        # case: pick a shared template, see its info before creating.
        patched_caches["captured"]["return"] = _template(allowed_users=["alice"])

        result = patched_caches["mod"].Helpers.owns_domain_id(
            _payload(), domain_id="tmpl-1"
        )

        assert result is True

    def test_template_shared_via_role_grants_access(self, patched_caches):
        patched_caches["captured"]["return"] = _template(allowed_roles=["advanced"])

        result = patched_caches["mod"].Helpers.owns_domain_id(
            _payload(), domain_id="tmpl-1"
        )

        assert result is True

    def test_template_shared_via_group_grants_access(self, patched_caches):
        patched_caches["captured"]["return"] = _template(allowed_groups=["grp-a"])

        result = patched_caches["mod"].Helpers.owns_domain_id(
            _payload(), domain_id="tmpl-1"
        )

        assert result is True

    def test_template_not_shared_with_user_still_denied(self, patched_caches):
        # ``ErrorBase`` (not the dynamic ``Error`` shim) — see the
        # documented ``error_factory snapshot-bind race``: when other
        # tests in the parallel suite have imported apiv4, ``Error``
        # from ``error_factory`` resolves to ``api.services.error.Error``
        # which isn't ``isinstance`` of ``ErrorBase``, but ``helpers.py``
        # bound ``Error`` to ``ErrorBase`` at module load. Catching the
        # parent here makes the assertion order-independent.
        from isardvdi_common.helpers.error_base import ErrorBase as Error

        # Template's allowed lists do not include this user / role / etc —
        # the existing forbidden-raise path must still trip. Regression
        # guard for the template-allowed branch silently allowing
        # everything.
        patched_caches["captured"]["return"] = _template(
            allowed_users=["someone-else"],
            allowed_roles=["manager"],
            allowed_groups=["grp-other"],
            allowed_categories=["cat-other"],
        )

        with pytest.raises(Error):
            patched_caches["mod"].Helpers.owns_domain_id(_payload(), domain_id="tmpl-1")

    def test_desktop_kind_unaffected_by_new_branch(self, patched_caches):
        """A non-owner advanced user accessing a desktop (not template)
        with no shared deployment must still be denied — the new branch
        is gated on ``kind == 'template'`` so desktops keep the existing
        owner / deployment / manager-category semantics."""
        # See sister test for the ``ErrorBase`` rationale.
        from isardvdi_common.helpers.error_base import ErrorBase as Error

        # Allowed lists granting access — but kind is desktop so the
        # template-allowed branch must NOT fire.
        desktop_row = _template(allowed_users=["alice"])
        desktop_row["kind"] = "desktop"
        patched_caches["captured"]["return"] = desktop_row

        with pytest.raises(Error):
            patched_caches["mod"].Helpers.owns_domain_id(_payload(), domain_id="dsk-1")

    def test_admin_short_circuits_before_cache_read(self, patched_caches):
        # Admins skip the row read entirely — no Caches.get_document call.
        result = patched_caches["mod"].Helpers.owns_domain_id(
            _payload(role_id="admin"), domain_id="any-id"
        )
        assert result is True
        assert patched_caches["captured"].get("calls") is None
