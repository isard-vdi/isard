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

import subprocess
from pathlib import Path

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


class TestHasBackingFile:
    """``compress`` rewrites the file through ``qemu-img convert -O qcow2``
    without ``-B``, which writes a FLAT image, and then replaces the original
    with it. On a disk that reads through another one that severs the chain
    while the stored parent still claims it is there.
    """

    @staticmethod
    def _run(stdout="{}", returncode=0):
        from unittest.mock import MagicMock

        return MagicMock(stdout=stdout, returncode=returncode)

    def test_a_chained_disk_is_reported_as_backed(self, monkeypatch):
        from storage_lib import qcow

        monkeypatch.setattr(
            qcow.subprocess,
            "run",
            lambda *a, **k: self._run(
                '{"full-backing-filename": "/isard/templates/p.qcow2"}'
            ),
        )

        assert qcow.has_backing_file("/isard/groups/c.qcow2") == (True, None)

    def test_a_root_disk_is_not(self, monkeypatch):
        from storage_lib import qcow

        monkeypatch.setattr(
            qcow.subprocess, "run", lambda *a, **k: self._run('{"virtual-size": 100}')
        )

        assert qcow.has_backing_file("/isard/templates/p.qcow2") == (False, None)

    def test_an_unanswerable_question_is_an_error_not_a_no(self, monkeypatch):
        """A caller must treat "I could not tell" as "do not touch it"."""
        from storage_lib import qcow

        monkeypatch.setattr(
            qcow.subprocess, "run", lambda *a, **k: self._run("not json at all")
        )

        has, err = qcow.has_backing_file("/x.qcow2")
        assert has is False and err


class TestTheGuardReachesTheWorkerShells:
    """``sparsify`` fans the work out with ``xargs … bash -c 'process_file …'``,
    so the guard runs in a *child shell*. A bash function is not inherited
    unless it is exported, and an undefined guard cannot refuse anything: the
    file gets rewritten and nothing says so.

    The script also exports a block of names just before the fan-out. That
    block is a list, and lists get rewritten by refactors -- one landed while
    this MR was open and dropped these two lines. Pinning the export next to
    the definition is what makes the guard survive that.
    """

    SCRIPT = Path(__file__).resolve().parent.parent / "sparsify"

    def _lines(self):
        return self.SCRIPT.read_text().splitlines()

    def test_the_function_is_exported_where_it_is_defined(self):
        lines = self._lines()
        end = next(i for i, l in enumerate(lines) if l.startswith("is_backing_file()"))
        # near the definition, not only in the block hundreds of lines below
        near = "\n".join(lines[end : end + 20])
        assert "export -f is_backing_file" in near
        assert "export BACKING_FILES_FILE" in near

    def test_an_exported_guard_refuses_inside_a_child_shell(self, tmp_path):
        """The mechanism itself, run for real: the same shape as the fan-out."""
        backing = tmp_path / "backing_files.txt"
        backing.write_text("/isard/a.qcow2\n")

        script = f"""
        BACKING_FILES_FILE={backing}
        is_backing_file() {{ [ -s "$BACKING_FILES_FILE" ] || return 1
                             grep -Fxq -- "$1" "$BACKING_FILES_FILE"; }}
        export -f is_backing_file
        export BACKING_FILES_FILE
        echo /isard/a.qcow2 | xargs -I {{}} bash -c \
            'is_backing_file "$1" && echo refused || echo rewritten' _ {{}}
        """
        out = subprocess.run(
            ["bash", "-c", script], capture_output=True, text=True
        ).stdout
        assert out.strip() == "refused"
