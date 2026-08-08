"""Pin the v197 cross-lineage cutover reconciliation contract.

The main and apiv4-integration lineages share migration history up to
v183 and both minted 184-189 with DIFFERENT content. A main-lineage DB
(config.version 188, or 189 with the GPU stack) attached to this code
runs forward only, so every apiv4-only change from 184-189 must ALSO
exist at v197, idempotently. These tests AST-inspect upgrade.py (it cannot be
imported bare: humanfriendly, rethinkdb, config) and pin:

* release_version == 197 and the reconciliation blocks exist in exactly
  the table functions that carried apiv4-only 184-189 content;
* the v190 allow_insecure_tls write is the value-preserving form
  (``.default(False)``) so the cutover pass cannot clobber an
  operator-enabled flag a main-lineage DB already carries;
* the three id-less v193 inserts are existence-guarded so a main-lineage
  DB (which ran the same inserts as its v188) cannot duplicate them;
* the v197 domains block carries the apiv4-and-websockets v178 create_dict
  hardware backfill (disk_bus/isos/floppies/personal_vlans), each
  has_fields-guarded, and the recycle_bin block backfills its count fields
  guarded on desktops_count absence.
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
    # >= so later migrations (GPU port v198, bugfix/1179 v199, ...) can land
    # on top without touching this contract.
    src = open(_SRC).read()
    m = re.search(r"^release_version = (\d+)", src, re.M)
    assert m and int(m.group(1)) >= 197


def test_reconciliation_blocks_present():
    missing = {
        f for f in _RECONCILED_FUNCS if f not in _FUNCS or "197" not in _FUNCS[f][0]
    }
    assert not missing, f"functions missing the v197 reconciliation: {missing}"


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


def _v197_block(fn_name):
    """The text of the ``if version == 197:`` block in a table function,
    bounded by the next ``if version ==`` or the function end."""
    versions, seg = _FUNCS[fn_name]
    assert "197" in versions, fn_name
    block = seg[seg.index("if version == 197:") :]
    nxt = block.find("if version ==", len("if version == 197:"))
    return block if nxt == -1 else block[:nxt]


def test_v197_domains_backfills_create_dict_hardware_fields():
    # Port of apiv4-and-websockets v178: legacy domains migrated to this lineage
    # never ran AW's backfill, and _common reads these unguarded. Consolidated
    # form: ONE filter (literal has_fields per field, .default({})-guarded
    # parents) + ONE update with .default() per field. Match against a
    # whitespace-collapsed block so black's line-wrapping of the .default({})
    # chains does not break the assertions.
    flat = re.sub(r"\s+", "", _v197_block("domains"))
    for field, default in (
        ('"disk_bus"', '"default"'),
        ('"isos"', "[]"),
        ('"floppies"', "[]"),
        ('"personal_vlans"', "False"),
    ):
        assert field in flat, f"missing backfill for {field}"
        assert default in flat, f"missing default {default} for {field}"
        # each field selected via a literal has_fields(...).not_() term
        assert f"has_fields({field})" in flat, f"missing has_fields({field}) guard"
    # superset-repair: parents .default({})-guarded so malformed (missing
    # create_dict/hardware) rows are repaired, not skipped
    assert 'd["create_dict"].default({})["hardware"].default({})' in flat
    # reservables is intentionally excluded (v164 covers it) -- never add it
    assert '"reservables"' not in flat


def test_v197_recycle_bin_count_backfill_is_guarded():
    block = _v197_block("storage")
    assert "desktops_count" in block
    # guarded on absence so it is a no-op on apiv4-lineage DBs
    assert 'has_fields("desktops_count")' in block


def _blocks():
    """Every ``if version == N:`` body, keyed by (function, N), comment- and
    whitespace-normalised so the same migration is recognisable under any
    number.

    Bounded by DEDENT, not by the next ``if version ==``: the last block of a
    function would otherwise swallow everything after it (``return True`` and
    the rest), which makes two identical copies read as different bodies and
    silently defeats the duplicate check below.
    """
    out = {}
    for fn, (_versions, seg) in _FUNCS.items():
        lines = seg.split("\n")
        for i, line in enumerate(lines):
            m = re.match(r"(\s*)if version == (\d+):\s*$", line)
            if not m:
                continue
            indent = len(m.group(1))
            body = []
            for nxt in lines[i + 1 :]:
                if not nxt.strip():
                    continue
                if len(nxt) - len(nxt.lstrip()) <= indent:
                    break
                if not nxt.strip().startswith("#"):
                    body.append(nxt.strip())
            out[(fn, int(m.group(2)))] = "\n".join(body)
    return out


def test_no_block_is_numbered_above_the_release_version():
    """A block above ``release_version`` is never replayed: the loop stops at
    the release, so the migration is dead code that looks live."""
    src = open(_SRC).read()
    release = int(re.search(r"^release_version = (\d+)", src, re.M).group(1))
    over = sorted({v for _fn, v in _blocks() if v > release})
    assert not over, f"blocks above release_version {release}: {over}"


def test_no_migration_body_is_claimed_by_two_numbers():
    """The same migration under two numbers means two branches each brought
    their own copy. Both then run: once on the way to N, again on the way to
    M. The number is a position in a global sequence, so it can only be
    settled by the merge order -- never inside the branch that adds it.
    """
    per_body = {}
    for (fn, version), body in _blocks().items():
        # short bodies (a lone guarded index_drop) legitimately recur
        if len(body.split("\n")) < 5:
            continue
        per_body.setdefault((fn, body), set()).add(version)
    dupes = {fn: sorted(vs) for (fn, _body), vs in per_body.items() if len(vs) > 1}
    assert not dupes, f"the same migration appears under several numbers: {dupes}"
