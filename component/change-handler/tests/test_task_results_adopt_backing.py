# SPDX-License-Identifier: AGPL-3.0-or-later

"""D6: a backing file with no row is adopted only when it validates."""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

UUID = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
IN_POOL = f"/isard/storage_pools/default/templates/{UUID}.qcow2"
OUT_POOL = f"/isard/outside/{UUID}.qcow2"


def _task(**attrs):
    base = dict(id="t1", user_id="child-owner", depending_status="finished")
    base.update(attrs)
    return SimpleNamespace(**base)


def _child(realpath, full_backing=None):
    child = MagicMock(status="ready", id="child1")
    child.parent = "UNSET"
    setattr(
        child,
        "qemu-img-info",
        {
            "full-backing-filename": full_backing or realpath,
            "backing-realpath": realpath,
        },
    )
    return child


def _run(
    realpath, enabled=True, mountpoint="/isard/storage_pools/default", full_backing=None
):
    from isardvdi_change_handler.task_results import storage

    child = _child(realpath, full_backing=full_backing)
    adopted = MagicMock(id=UUID)
    with (
        patch.object(storage, "Storage") as S,
        patch.object(storage, "StoragePool") as SP,
        patch.object(storage, "_flag_review_damage") as flag,
    ):
        S.exists.return_value = True
        S.return_value = child
        S.get_by_path.return_value = None
        S.create_from_path.return_value = adopted
        SP.mountpoint_for_path.return_value = mountpoint
        SP.get_by_path.return_value = [MagicMock(enabled=enabled)]
        storage.handle_storage_update_parent(_task(), "child1")
    return storage, S, SP, flag, child, adopted


# --- adopt ---------------------------------------------------------------


def test_a_valid_backing_is_adopted_as_an_admin_reviewed_read_only_row():
    storage, S, SP, flag, child, adopted = _run(IN_POOL)
    (path,), kwargs = S.create_from_path.call_args
    assert path == IN_POOL
    assert kwargs["user_id"] == storage.ADOPTED_BACKING_OWNER  # system, not child owner
    flag.assert_called_once()
    assert flag.call_args.args[0] is adopted  # the review mark is on the adopted row
    assert child.parent == adopted.id
    assert adopted.check_backing_chain.call_args.kwargs["update_parent"] is True


# --- reject --------------------------------------------------------------


def test_a_backing_outside_every_pool_is_not_adopted():
    storage, S, SP, flag, child, adopted = _run(OUT_POOL, mountpoint=None)
    S.create_from_path.assert_not_called()
    assert flag.call_args.args[0] is child  # the child is flagged, not a new row
    assert child.parent == "UNSET"  # no bogus parent pointer


def test_a_symlink_or_dotdot_escaping_the_pool_uses_the_realpath():
    # header path looks in-pool, realpath escapes it -> judged on the realpath
    storage, S, SP, flag, child, adopted = _run(
        OUT_POOL, mountpoint=None, full_backing=IN_POOL
    )
    SP.mountpoint_for_path.assert_called_with(OUT_POOL)
    S.create_from_path.assert_not_called()
    assert child.parent == "UNSET"


def test_a_backing_in_a_disabled_pool_is_not_adopted():
    storage, S, SP, flag, child, adopted = _run(IN_POOL, enabled=False)
    S.create_from_path.assert_not_called()
    assert flag.call_args.args[0] is child


def test_a_backing_not_named_like_a_uuid_is_not_adopted():
    storage, S, SP, flag, child, adopted = _run(
        "/isard/storage_pools/default/templates/not-a-uuid.qcow2"
    )
    S.create_from_path.assert_not_called()
    assert flag.call_args.args[0] is child


# --- the refusal predicate ----------------------------------------------


def test_refusal_predicate_matrix():
    from isardvdi_change_handler.task_results import storage

    with patch.object(storage, "StoragePool") as SP:
        SP.mountpoint_for_path.return_value = "/isard/storage_pools/default"
        SP.get_by_path.return_value = [MagicMock(enabled=True)]
        assert storage._backing_adoption_refusal(IN_POOL) is None

        assert "uuid" in storage._backing_adoption_refusal(
            "/isard/storage_pools/default/templates/x.qcow2"
        )

        SP.mountpoint_for_path.return_value = None
        assert "outside" in storage._backing_adoption_refusal(OUT_POOL)

        SP.mountpoint_for_path.return_value = "/isard/storage_pools/default"
        SP.get_by_path.return_value = [MagicMock(enabled=False)]
        assert "disabled" in storage._backing_adoption_refusal(IN_POOL)
