#
#   Copyright © 2026 IsardVDI
#
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Retention window must key on the OWNER, not the deleting agent.

``max_time`` is consulted ONLY for the ``== 0`` decision (permanent-now vs
send-to-bin). The scheduler then drains the bin by the OWNER's category
cutoff. So there is exactly ONE harmful case: the DELETING agent's category
is 0 (bin disabled) while the OWNER's category is non-zero — today that
destroys the content immediately, ignoring the owner's retention policy.
Every other value discrepancy is harmless: the item enters the bin and the
drain applies the owner's window (already the correct one).

These tests therefore pin the value 0, not two arbitrary different values.
"""

import pytest


@pytest.fixture
def de_mod():
    from isardvdi_common.helpers import desktop_events as mod

    return mod


def _install(mod, monkeypatch, rcb_attr, owner, cutoffs):
    created = {}

    class _FakeRcb:
        def __init__(self, user_id=None):
            self.agent_id = user_id
            self.owner_id = None
            self.deleted = []
            created["rcb"] = self

        def add(self, *args, **kwargs):
            # _add_owner stamps the entry's owner during add(); mirror that so
            # rcb.owner_id is populated exactly as production sees it.
            self.owner_id = owner

        def delete_storage(self, agent_id):
            self.deleted.append(agent_id)
            return ["task"]

    monkeypatch.setattr(mod, rcb_attr, _FakeRcb)
    monkeypatch.setattr(
        mod.RecycleBinHelpers,
        "get_user_recycle_bin_cutoff_time",
        staticmethod(lambda uid: cutoffs[uid]),
    )
    return created


AGENT = "agent-user"
OWNER = "owner-user"


class TestTemplatesDeleteOwnerCutoff:
    def test_agent_zero_owner_nonzero_is_the_bug_fixed(self, de_mod, monkeypatch):
        """The one harmful case: deleter's category disabled (0), owner's not.
        Must go to the bin under the OWNER's window, not be destroyed now."""
        created = _install(
            de_mod,
            monkeypatch,
            "RecycleBinTemplate",
            owner=OWNER,
            cutoffs={OWNER: 30, AGENT: 0},
        )
        de_mod.DesktopEvents.templates_delete("tpl-1", AGENT)
        assert created["rcb"].deleted == []

    def test_owner_zero_governs_permanent(self, de_mod, monkeypatch):
        """Owner's category disabled (0) → permanent-now is correct, whatever
        the deleter's window is."""
        created = _install(
            de_mod,
            monkeypatch,
            "RecycleBinTemplate",
            owner=OWNER,
            cutoffs={OWNER: 0, AGENT: 30},
        )
        de_mod.DesktopEvents.templates_delete("tpl-1", AGENT)
        assert created["rcb"].deleted == [AGENT]

    def test_both_nonzero_is_harmless_goes_to_bin(self, de_mod, monkeypatch):
        """No zero involved → never permanent-now regardless of the mismatch;
        the drain will apply the owner's window. Guards that only 0 matters."""
        created = _install(
            de_mod,
            monkeypatch,
            "RecycleBinTemplate",
            owner=OWNER,
            cutoffs={OWNER: 30, AGENT: 10},
        )
        de_mod.DesktopEvents.templates_delete("tpl-1", AGENT)
        assert created["rcb"].deleted == []


class TestUserDeleteResolvesViaAgent:
    """The "always the owner" rule is NOT universal. user_delete recycles the
    user itself: RecycleBinUser.add stamps that user as the entry owner AND
    deletes its ``users`` row, so resolving the cutoff via the owner queries a
    gone row (``users.get(...).pluck("category")`` raises ReqlNonExistenceError).
    The only surviving reference is the deleting agent, so user_delete must
    resolve max_time via the agent. This is the e2e regression (A7 bulk user
    delete) that the owner-only change introduced.
    """

    def test_does_not_query_the_deleted_owner(self, de_mod, monkeypatch):
        created = {}

        class _FakeRcb:
            def __init__(self, user_id=None):
                self.agent_id = user_id
                self.owner_id = None
                self.deleted = []
                created["rcb"] = self

            def add(self, user_id, delete_user=True):
                # Owner is the user being deleted; its ``users`` row is now gone.
                self.owner_id = user_id

            def delete_storage(self, agent_id):
                self.deleted.append(agent_id)
                return ["task"]

        monkeypatch.setattr(de_mod, "RecycleBinUser", _FakeRcb)

        queried = []

        def _cutoff(uid):
            queried.append(uid)
            if uid == "victim-user":
                raise Exception("ReqlNonExistenceError: users.get on a deleted row")
            return 24

        monkeypatch.setattr(
            de_mod.RecycleBinHelpers,
            "get_user_recycle_bin_cutoff_time",
            staticmethod(_cutoff),
        )

        # Must NOT raise, and must NOT query the deleted owner.
        de_mod.DesktopEvents.user_delete(AGENT, "victim-user")

        assert "victim-user" not in queried
        assert queried == [AGENT]
        assert created["rcb"].deleted == []  # 24 != 0 -> not permanent
