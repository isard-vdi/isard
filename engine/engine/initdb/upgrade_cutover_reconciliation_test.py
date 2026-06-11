"""Pin the v196 cross-lineage cutover reconciliation contract.

The main and apiv4-integration lineages share migration history up to
v183 and both minted 184-189 with DIFFERENT content. A main-lineage DB
(config.version 188, or 189 with the GPU stack) attached to this code
runs forward only, so every apiv4-only change from 184-189 must ALSO
exist at v196, idempotently. These tests AST-inspect upgrade.py (it cannot be
imported bare: humanfriendly, rethinkdb, config) and pin:

* release_version == 196 and the reconciliation blocks exist in exactly
  the table functions that carried apiv4-only 184-189 content;
* the v190 allow_insecure_tls write is the value-preserving form
  (``.default(False)``) so the cutover pass cannot clobber an
  operator-enabled flag a main-lineage DB already carries;
* the three id-less v193 inserts are existence-guarded so a main-lineage
  DB (which ran the same inserts as its v188) cannot duplicate them.
"""

import ast
import os
import re

_SRC = os.path.join(os.path.dirname(__file__), "upgrade.py")

# Table functions that carried apiv4-only content under a version number
# (184-189) the main lineage reused for different content.
_RECONCILED_FUNCS = {
    "categories",
    "groups",
    "users",
    "deployments",
    "domains",
    "storage",
    "media",
    "hypervisors",
}

# Functions whose v193 inserts carry no explicit document id.
_GUARDED_193_FUNCS = {"notification_tmpls", "unused_item_timeout", "notifications"}


def _func_versions():
    src = open(_SRC).read()
    tree = ast.parse(src)
    out = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef):
            for fn in node.body:
                if isinstance(fn, ast.FunctionDef):
                    seg = ast.get_source_segment(src, fn) or ""
                    out[fn.name] = (
                        set(re.findall(r"if version == (\d+):", seg)),
                        seg,
                    )
    return out


_FUNCS = _func_versions()


def test_release_version_covers_reconciliation():
    # >= so later migrations (GPU port v197, bugfix/1179 v198, ...) can land
    # on top without touching this contract.
    src = open(_SRC).read()
    m = re.search(r"^release_version = (\d+)", src, re.M)
    assert m and int(m.group(1)) >= 196


def test_reconciliation_blocks_present():
    missing = {
        f for f in _RECONCILED_FUNCS if f not in _FUNCS or "196" not in _FUNCS[f][0]
    }
    assert not missing, f"functions missing the v196 reconciliation: {missing}"


def test_v190_is_value_preserving():
    versions, seg = _FUNCS["config"]
    assert "190" in versions
    block = seg[seg.index("if version == 190:") :]
    block = block[: block.index("if version == 19", 20)]
    # the write must read back the stored value with a False default,
    # not assign a literal False unconditionally
    assert ".default(False)" in block
    assert '"allow_insecure_tls": False' not in block


def test_v193_inserts_are_existence_guarded():
    for fn in _GUARDED_193_FUNCS:
        versions, seg = _FUNCS[fn]
        assert "193" in versions, fn
        block = seg[seg.index("if version == 193:") :]
        insert_pos = block.index(".insert(")
        guard_pos = block.index(".count()")
        assert guard_pos < insert_pos, (
            f"{fn}: v193 insert must be preceded by an existence guard "
            f"(id-less documents duplicate on the cutover re-run)"
        )
