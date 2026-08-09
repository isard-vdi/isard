#
#   Copyright © 2026 IsardVDI
#
# SPDX-License-Identifier: AGPL-3.0-or-later

"""A disk something reads through must never be handed to sparsify or compress.

Both rewrite the file, and an overlay reads from its backing file every cluster
it has not written itself, so the children silently start seeing something else.
The operator tools had no such check: the only protection was a literal
``/isard/templates`` path match, which a per-category storage pool defeats.
"""

from storage_lib.deps import split_backing_files


class TestSplitBackingFiles:
    def test_a_file_another_disk_backs_onto_is_protected(self):
        files = ["/isard/templates/a.qcow2", "/isard/groups/b.qcow2"]
        reverse_map = {"/isard/templates/a.qcow2": ["/isard/groups/b.qcow2"]}

        safe, protected = split_backing_files(files, reverse_map)

        assert safe == ["/isard/groups/b.qcow2"]
        assert protected == ["/isard/templates/a.qcow2"]

    def test_a_template_in_a_category_pool_is_protected_too(self):
        """The path filter this replaces matched one literal directory, so a
        template held in a per-category pool went straight through it."""
        pooled = "/isard/storage_pools/fast/cat-1/templates/t.qcow2"
        safe, protected = split_backing_files(
            [pooled], {pooled: ["/isard/storage_pools/fast/cat-1/desktops/d.qcow2"]}
        )

        assert safe == []
        assert protected == [pooled]

    def test_a_childless_template_stays_optimizable(self):
        """The rule is about being read through, not about living in a
        templates directory: a template nothing derives from is safe."""
        lone = "/isard/templates/lone.qcow2"

        safe, protected = split_backing_files([lone], {})

        assert safe == [lone]
        assert protected == []

    def test_order_is_preserved_in_both_halves(self):
        files = ["/a", "/b", "/c", "/d"]

        safe, protected = split_backing_files(files, {"/b": [], "/c": []})

        assert safe == ["/a", "/d"]
        assert protected == ["/b", "/c"]

    def test_a_set_is_accepted_as_well_as_a_map(self):
        safe, protected = split_backing_files(["/a", "/b"], {"/a"})

        assert (safe, protected) == (["/b"], ["/a"])

    def test_no_dependencies_at_all_protects_nothing(self):
        safe, protected = split_backing_files(["/a", "/b"], None)

        assert (safe, protected) == (["/a", "/b"], [])
