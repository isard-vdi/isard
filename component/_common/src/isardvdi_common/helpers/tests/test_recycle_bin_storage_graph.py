#
#   Copyright © 2026 IsardVDI
#
# SPDX-License-Identifier: AGPL-3.0-or-later

"""The recycle bin decides what to drag along over the DOMAIN graph, and then
destroys STORAGE files.

The two graphs are written independently. A disk can have a child in the
storage graph with no domain of its own -- the disks page creates exactly that,
posting a parent to the storage-create route with no domain attached -- and a
domain walk cannot see it. Recycling the parent then unlinks the file that
child reads through, and nothing reports it.
"""

from isardvdi_common.helpers.recycle_bin import uncovered_storage_children


class TestUncoveredStorageChildren:
    def test_a_child_outside_the_deletion_is_reported(self):
        """The defect, stated: a derived disk with no domain of its own."""
        uncovered = uncovered_storage_children(
            {"tpl-disk"}, [{"id": "orphan-derived", "status": "ready"}]
        )

        assert uncovered == ["orphan-derived"]

    def test_a_child_that_is_part_of_the_deletion_is_not(self):
        uncovered = uncovered_storage_children(
            {"tpl-disk", "desktop-disk"}, [{"id": "desktop-disk", "status": "ready"}]
        )

        assert uncovered == []

    def test_a_failed_child_does_not_block(self):
        """Caught on a real install, not by reasoning: ``Failed`` is written by
        the engine and is not in ``StorageStatusEnum`` at all. Blocking on
        everything that is not obviously gone made 32 failed disks refuse every
        legitimate template deletion on that install."""
        uncovered = uncovered_storage_children(
            {"tpl-disk"}, [{"id": "broken", "status": "Failed"}]
        )

        assert uncovered == []

    def test_an_orphan_child_does_not_block(self):
        uncovered = uncovered_storage_children(
            {"tpl-disk"}, [{"id": "lost", "status": "orphan"}]
        )

        assert uncovered == []

    def test_a_child_in_maintenance_still_blocks(self):
        """It is a live disk in the middle of an operation, not a dead one."""
        uncovered = uncovered_storage_children(
            {"tpl-disk"}, [{"id": "busy", "status": "maintenance"}]
        )

        assert uncovered == ["busy"]

    def test_an_already_recycled_child_does_not_block(self):
        """It is going away too; blocking on it would deadlock the bin."""
        uncovered = uncovered_storage_children(
            {"tpl-disk"}, [{"id": "old", "status": "recycled"}]
        )

        assert uncovered == []

    def test_a_deleted_child_does_not_block(self):
        uncovered = uncovered_storage_children(
            {"tpl-disk"}, [{"id": "gone", "status": "deleted"}]
        )

        assert uncovered == []

    def test_the_answer_is_sorted_and_deduplicated(self):
        uncovered = uncovered_storage_children(
            set(),
            [
                {"id": "b", "status": "ready"},
                {"id": "a", "status": "ready"},
                {"id": "b", "status": "ready"},
            ],
        )

        assert uncovered == ["a", "b"]

    def test_no_children_at_all_is_no_objection(self):
        assert uncovered_storage_children({"tpl-disk"}, []) == []
        assert uncovered_storage_children({"tpl-disk"}, None) == []
