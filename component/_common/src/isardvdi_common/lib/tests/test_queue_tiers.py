"""Unit tests for the queue-tier resolver (pure logic).

The resolver replaces the role-demoting ``check_task_priority`` with an
action-driven tier model:
interactive / standard / template / bulk / maintenance / reclaim.
"""

import pytest
from isardvdi_common.lib import queue_tiers as qt

# --- the six tiers exist and are ordered high->low urgency ------------------


def test_tiers_are_the_seven_tiers():
    # ``background`` is the lowest tier: idle-only lifecycle metadata refreshes
    # (e.g. a post-stop qemu-img-info size refresh) that nobody is blocked on.
    assert qt.TIERS == (
        "interactive",
        "standard",
        "template",
        "bulk",
        "maintenance",
        "reclaim",
        "background",
    )


def test_governed_tiers_are_the_governed_five():
    assert qt._GOVERNED_TIERS == frozenset(
        {"template", "bulk", "maintenance", "reclaim", "background"}
    )


def test_background_is_deferrable_but_not_heavy():
    # background hides under node pressure (run-when-idle) but never counts
    # against the max-heavy concurrency cap — it is a trivial metadata read.
    assert "background" in qt.DEFERRABLE_TIERS
    assert "background" not in qt.HEAVY_TIERS
    assert "background" in qt._GOVERNED_TIERS


# --- default_tier_for_action: the per-action default (kills "everything=default") ---


@pytest.mark.parametrize(
    "action,expected",
    [
        # single foreground, user waiting -> interactive (create/start ahead of resize)
        ("create", "interactive"),
        ("recreate", "interactive"),
        ("find", "interactive"),
        ("touch", "interactive"),
        ("qemu_img_info_backing_chain", "interactive"),
        # single foreground but seconds-not-subsecond -> standard (below create/start)
        ("resize", "standard"),
        # long / maintenance -> maintenance (never reserved/std)
        ("sparsify", "maintenance"),
        ("convert", "maintenance"),
        ("disconnect", "maintenance"),
        # virt_win_reg drives a libguestfs appliance VM -> heavy maintenance, not std
        ("virt_win_reg", "maintenance"),
        ("move", "maintenance"),
        # long network downloads -> maintenance by default
        ("download_url", "maintenance"),
        ("download_url_for_domain", "maintenance"),
        # physical space reclamation -> the lowest tier
        ("delete", "reclaim"),
        ("move_delete", "reclaim"),
    ],
)
def test_default_tier_for_action(action, expected):
    assert qt.default_tier_for_action(action) == expected


def test_default_tier_for_unknown_action_is_interactive_conservative():
    # An unmapped action must never silently land on a starved lane; default to
    # the safe foreground lane.
    assert qt.default_tier_for_action("some_new_action") == "interactive"


# --- normalize_tier: accepts tiers AND legacy high/default/low ---------------


def test_normalize_passes_through_valid_tiers():
    for t in qt.TIERS:
        assert qt.normalize_tier(t) == t


def test_normalize_legacy_high_maps_to_interactive():
    assert qt.normalize_tier("high") == "interactive"


def test_normalize_legacy_low_maps_to_maintenance():
    assert qt.normalize_tier("low") == "maintenance"


def test_normalize_legacy_default_uses_action_default():
    assert qt.normalize_tier("default", action="create") == "interactive"
    assert qt.normalize_tier("default", action="resize") == "standard"
    assert qt.normalize_tier("default", action="sparsify") == "maintenance"
    assert qt.normalize_tier("default", action="delete") == "reclaim"


def test_normalize_legacy_default_without_action_is_interactive():
    assert qt.normalize_tier("default") == "interactive"


def test_normalize_rejects_garbage():
    with pytest.raises(ValueError):
        qt.normalize_tier("turbo")


# --- trigger-driven qemu_img_info_backing_chain tiering ---------------------
# qibc is NOT hard-floored: its tier follows the TRIGGER, not the action.
#  * as a standalone lifecycle refresh nobody is blocked on (post-stop size
#    refresh, batch status) the producer passes ``background`` -> idle lane.
#  * as an admin datatable "check" click the producer passes ``standard``
#    -> quick, but not the sub-second reserved lane.
#  * as an in-chain finalize (create/sparsify/... dependent), the caller is
#    blocked on the parent op, so ``default`` keeps the safe-foreground
#    fallback (interactive) — a create's disk-info refresh stays fast.


def test_qibc_honours_explicit_background_trigger():
    assert (
        qt.normalize_tier("background", action="qemu_img_info_backing_chain")
        == "background"
    )
    assert (
        qt.retier_queue("storage.pool-a.background", "qemu_img_info_backing_chain")
        == "storage.pool-a.background"
    )


def test_qibc_honours_explicit_standard_trigger():
    assert (
        qt.normalize_tier("standard", action="qemu_img_info_backing_chain")
        == "standard"
    )


def test_qibc_default_stays_interactive_for_in_chain_finalize():
    # An in-chain qibc dependent enqueued with ``.default`` still rides fast so a
    # create/resize the user is blocked on is not deferred to the idle lane.
    assert (
        qt.normalize_tier("default", action="qemu_img_info_backing_chain")
        == "interactive"
    )


def test_background_is_fair_scheduled_with_category():
    # background is a governed/fair tier, so per-category multitenancy segments it.
    assert (
        qt.retier_queue(
            "storage.pool-a.background", "qemu_img_info_backing_chain", category="cat1"
        )
        == "storage.pool-a.cat1.background"
    )


# --- create/start prioritised ahead of resize -------------------------------


def test_create_is_interactive_resize_is_standard():
    # A create/start (interactive, reserved pool) always overtakes a resize
    # (standard, std-lane) — they ride different lanes served by different pools.
    assert qt.default_tier_for_action("create") == "interactive"
    assert qt.default_tier_for_action("resize") == "standard"


# --- the headline behavioral fix: role NO LONGER demotes --------------------


def test_non_admin_interactive_is_not_demoted():
    assert qt.normalize_tier("interactive", role_id="user") == "interactive"
    assert (
        qt.normalize_tier(qt.default_tier_for_action("create"), role_id="user")
        == "interactive"
    )


def test_bulk_stays_bulk_regardless_of_role():
    assert qt.normalize_tier("bulk", role_id="admin") == "bulk"
    assert qt.normalize_tier("bulk", role_id="user") == "bulk"


# --- deletes are the LOWEST tier, always (single AND bulk) -------------------


def test_delete_hard_floors_to_reclaim():
    # A plain delete used to resolve to interactive (the catch-all default) —
    # now it is the lowest tier and can never crowd a create/start.
    assert qt.normalize_tier("default", action="delete") == "reclaim"
    assert qt.normalize_tier("interactive", action="delete") == "reclaim"
    assert qt.normalize_tier("high", action="move_delete") == "reclaim"


def test_bulk_delete_behaves_like_a_single_delete():
    # The producer may mark a mass delete ``bulk``, but a delete still reclaims —
    # it never rides the bulk throughput lane.
    assert qt.normalize_tier("bulk", action="delete") == "reclaim"
    assert qt.retier_queue("storage.POOL.bulk", "delete") == "storage.POOL.reclaim"


# --- maintenance churn is hard-floored to maintenance -----------------------


def test_maintenance_action_cannot_be_promoted_out_of_maintenance():
    assert qt.normalize_tier("interactive", action="convert") == "maintenance"
    assert qt.normalize_tier("interactive", action="sparsify") == "maintenance"
    assert qt.normalize_tier("standard", action="disconnect") == "maintenance"
    assert qt.normalize_tier("template", action="sparsify") == "maintenance"
    # virt_win_reg is a libguestfs appliance op -> floored to maintenance, not std
    assert qt.normalize_tier("interactive", action="virt_win_reg") == "maintenance"
    assert qt.normalize_tier("standard", action="virt_win_reg") == "maintenance"


def test_maintenance_action_never_raises_on_free_form_priority():
    assert qt.normalize_tier("urgent", action="convert") == "maintenance"
    assert qt.normalize_tier("whatever", action="sparsify") == "maintenance"


# --- move: floored into the governed set, promotable to template/bulk -------


def test_move_defaults_to_maintenance_and_never_reaches_a_foreground_lane():
    # a 12h whole-disk move must never resolve to a reserved/std lane
    assert qt.normalize_tier("default", action="move") == "maintenance"
    assert qt.normalize_tier("interactive", action="move") == "maintenance"
    assert qt.normalize_tier("standard", action="move") == "maintenance"
    assert qt.normalize_tier("low", action="move") == "maintenance"
    # free-form priority must not raise
    assert qt.normalize_tier("urgent", action="move") == "maintenance"


def test_move_routes_to_a_heavy_tier_only_never_bulk():
    # a template-from-desktop move lands on the dedicated template lane. A 12h
    # whole-disk copy MUST be max-heavy-capped, so a move can ride only a HEAVY
    # (capped) tier — template or maintenance. It must NEVER land on the non-heavy
    # ``bulk`` lane (un-PSI-paced, unaccounted); and since ``reclaim`` is now
    # deferrable-but-not-capped (trivial deletes), a move tagged reclaim floors to
    # maintenance too — a whole-disk copy must be capped.
    assert qt.normalize_tier("template", action="move") == "template"
    assert qt.normalize_tier("maintenance", action="move") == "maintenance"
    assert qt.normalize_tier("reclaim", action="move") == "maintenance"  # not capped
    assert qt.normalize_tier("bulk", action="move") == "maintenance"  # NOT bulk


def test_download_default_maintenance_but_awaited_standard_is_honored():
    assert qt.normalize_tier("default", action="download_url") == "maintenance"
    assert qt.normalize_tier("standard", action="download_url") == "standard"


# --- retier_queue: rewrite the tier segment of a storage.<pool>.<tier> name --


def test_retier_queue_rewrites_last_segment_by_action():
    assert (
        qt.retier_queue("storage.POOL.default", "create") == "storage.POOL.interactive"
    )
    assert qt.retier_queue("storage.POOL.default", "resize") == "storage.POOL.standard"
    assert (
        qt.retier_queue("storage.POOL.default", "sparsify")
        == "storage.POOL.maintenance"
    )
    assert qt.retier_queue("storage.POOL.default", "delete") == "storage.POOL.reclaim"


def test_retier_queue_maps_legacy_low_and_high():
    assert (
        qt.retier_queue("storage.POOL.low", "download_url")
        == "storage.POOL.maintenance"
    )
    # a delete floors to reclaim regardless of the legacy high hint
    assert qt.retier_queue("storage.POOL.high", "delete") == "storage.POOL.reclaim"


def test_retier_queue_template_move():
    # template-from-desktop passes priority="template" -> its own governed lane
    assert qt.retier_queue("storage.POOL.template", "move") == "storage.POOL.template"


def test_retier_queue_preserves_cross_pool_colon_segment():
    # Cross-pool move queues keep the src:dst infra key intact; only the trailing
    # tier segment is rewritten. A move floors to maintenance.
    assert (
        qt.retier_queue("storage.SRC:DST.default", "move")
        == "storage.SRC:DST.maintenance"
    )


def test_retier_queue_dotted_priority_degrades_to_a_served_queue():
    # A free-form priority containing a dot must NOT leave a bogus
    # middle segment / an unparseable 5-segment name. Everything after
    # storage.<pool>. is the priority; a dotted one is unrecognised -> default
    # tier for the action -> a real queue a worker serves.
    q = qt.retier_queue("storage.POOL.a.b", "resize")
    assert q == "storage.POOL.standard"  # dotted priority -> resize default
    assert qt.parse_storage_queue(q) == ("POOL", None, "standard")
    q2 = qt.retier_queue("storage.POOL.x.y.z", "create")
    assert q2 == "storage.POOL.interactive"
    assert qt.parse_storage_queue(q2) == ("POOL", None, "interactive")
    # a delete with a dotted priority still hard-floors to reclaim (served)
    assert qt.retier_queue("storage.POOL.a.b", "delete") == "storage.POOL.reclaim"


def test_retier_queue_honors_explicit_bulk():
    assert qt.retier_queue("storage.POOL.bulk", "create") == "storage.POOL.bulk"


def test_retier_queue_leaves_non_storage_queues_untouched():
    assert qt.retier_queue("core", "update_status") == "core"
    assert qt.retier_queue("notifier.default", "notify") == "notifier.default"


def test_retier_queue_tolerates_none_and_malformed():
    assert qt.retier_queue(None, "create") is None
    assert qt.retier_queue("storage", "create") == "storage"


def test_retier_queue_degrades_free_form_priority_to_default_tier():
    # An rsync route passing a free-form priority string must not raise/500; the
    # tier segment degrades to the action's default (a real, served queue).
    assert (
        qt.retier_queue("storage.POOL.urgent", "create") == "storage.POOL.interactive"
    )
    assert (
        qt.retier_queue("storage.POOL.turbo", "download_url")
        == "storage.POOL.maintenance"
    )


# --- retier_dependents: recursive over the whole dependents tree -------------


def test_retier_dependents_recurses_into_nested_levels():
    tree = [
        {
            "task": "create",
            "queue": "storage.POOL.default",
            "dependents": [
                {
                    "task": "sparsify",
                    "queue": "storage.POOL.default",
                    "dependents": [
                        {"task": "move", "queue": "storage.POOL.default"},
                    ],
                }
            ],
        }
    ]
    qt.retier_dependents(tree)
    lvl1 = tree[0]
    lvl2 = lvl1["dependents"][0]
    lvl3 = lvl2["dependents"][0]
    assert lvl1["queue"] == "storage.POOL.interactive"
    assert lvl2["queue"] == "storage.POOL.maintenance"  # sparsify floored
    assert lvl3["queue"] == "storage.POOL.maintenance"  # nested move floored


def test_retier_dependents_tolerates_none_and_non_dicts():
    qt.retier_dependents(None)  # must not raise
    tree = [None, "junk", {"task": "create", "queue": "storage.P.default"}]
    qt.retier_dependents(tree)
    assert tree[2]["queue"] == "storage.P.interactive"


# --- Phase-2 per-category queue shape ---------------------------------------


def test_retier_queue_no_category_stays_flat():
    assert (
        qt.retier_queue("storage.POOL.low", "download_url")
        == "storage.POOL.maintenance"
    )
    assert qt.retier_queue("storage.POOL.bulk", "create") == "storage.POOL.bulk"


def test_retier_queue_category_shapes_all_governed_tiers():
    assert (
        qt.retier_queue("storage.POOL.bulk", "create", category="catA")
        == "storage.POOL.catA.bulk"
    )
    assert (
        qt.retier_queue("storage.POOL.template", "move", category="catA")
        == "storage.POOL.catA.template"
    )
    assert (
        qt.retier_queue("storage.POOL.low", "download_url", category="catA")
        == "storage.POOL.catA.maintenance"
    )
    # a delete with a category still lands on the category reclaim lane
    assert (
        qt.retier_queue("storage.POOL.bulk", "delete", category="catA")
        == "storage.POOL.catA.reclaim"
    )
    # a floored move with a category lands on the category maintenance lane
    assert (
        qt.retier_queue("storage.SRC:DST.default", "move", category="catA")
        == "storage.SRC:DST.catA.maintenance"
    )


def test_retier_queue_category_ignored_for_interactive_and_standard():
    # interactive/standard ride the reserved/standard lanes -> never per-category.
    assert (
        qt.retier_queue("storage.POOL.high", "create", category="catA")
        == "storage.POOL.interactive"
    )
    assert (
        qt.retier_queue("storage.POOL.standard", "resize", category="catA")
        == "storage.POOL.standard"
    )


def test_retier_queue_null_category_routes_to_sentinel():
    assert (
        qt.retier_queue("storage.POOL.bulk", "create", category="")
        == f"storage.POOL.{qt.NULL_CATEGORY}.bulk"
    )
    assert (
        qt.retier_queue("storage.POOL.bulk", "create", category="a.b")
        == "storage.POOL.a_b.bulk"
    )


def test_retier_dependents_threads_category():
    tree = [
        {
            "task": "create",
            "queue": "storage.POOL.default",
            "dependents": [{"task": "sparsify", "queue": "storage.POOL.default"}],
        }
    ]
    qt.retier_dependents(tree, category="catA")
    assert tree[0]["queue"] == "storage.POOL.interactive"  # flat (interactive)
    assert (
        tree[0]["dependents"][0]["queue"] == "storage.POOL.catA.maintenance"
    )  # sparsify -> per-category maintenance


# --- parse_storage_queue -----------------------------------------------------


@pytest.mark.parametrize(
    "name,expected",
    [
        ("storage.POOL.bulk", ("POOL", None, "bulk")),
        ("storage.POOL.catA.maintenance", ("POOL", "catA", "maintenance")),
        ("storage.POOL.reclaim", ("POOL", None, "reclaim")),
        ("storage.SRC:DST.maintenance", ("SRC:DST", None, "maintenance")),
        ("storage.SRC:DST.catA.reclaim", ("SRC:DST", "catA", "reclaim")),
        ("core", None),
        ("notifier.default", None),
        ("storage", None),
        (None, None),
    ],
)
def test_parse_storage_queue(name, expected):
    assert qt.parse_storage_queue(name) == expected


@pytest.mark.parametrize(
    "value,expected",
    [
        ("true", True),
        ("True", True),
        ("1", True),
        ("yes", True),
        ("on", True),
        (" TRUE ", True),
        ("false", False),
        ("0", False),
        ("no", False),
        ("", False),
        (None, False),  # unset env -> default OFF (global queues)
    ],
)
def test_multitenancy_enabled(monkeypatch, value, expected):
    if value is None:
        monkeypatch.delenv("STORAGE_QUEUE_MULTITENANCY", raising=False)
    else:
        monkeypatch.setenv("STORAGE_QUEUE_MULTITENANCY", value)
    assert qt.multitenancy_enabled() is expected
