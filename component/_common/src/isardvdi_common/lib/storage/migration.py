#
#   IsardVDI - Open Source KVM Virtual Desktops based on KVM Linux and dockers
#   Copyright (C) 2026 IsardVDI
#
#   This program is free software: you can redistribute it and/or modify
#   it under the terms of the GNU Affero General Public License as published by
#   the Free Software Foundation, either version 3 of the License, or
#   (at your option) any later version.
#
#   This program is distributed in the hope that it will be useful,
#   but WITHOUT ANY WARRANTY; without even the implied warranty of
#   MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#   GNU Affero General Public License for more details.
#
#   You should have received a copy of the GNU Affero General Public License
#   along with this program.  If not, see <https://www.gnu.org/licenses/>.
#
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Plan builder for the admin storage-disk path->path migration.

Two layers:

* **Pure** (DB-free, unit tested): the true-recursion BFS topo walk
  (``Storage.derivatives`` is only 2-level, so it is NOT reused), per-disk
  ``storage_migration_item`` construction, classification, plan summary, and
  the live ``qemu-img info -U`` size probe.
* **DB-driven**: :func:`build_plan_for_roots` wires the real ``Storage`` /
  ``StoragePool`` models into the pure layer; it is exercised live against real
  storage rows (the plan endpoint runs it).
"""

import json
import subprocess
from collections import Counter, deque

from rethinkdb import r


# --------------------------------------------------------------------------- #
# Pure layer
# --------------------------------------------------------------------------- #
def walk_tree_topo(root_id, get_children):
    """Return all node ids in the subtree rooted at ``root_id`` in BFS topo
    order — **parents strictly before children** — via a genuine recursion
    (not ``Storage.derivatives``'s 2-level expansion).

    :param get_children: ``node_id -> iterable[node_id]``.
    Cycle-safe: every node is emitted at most once.
    """
    order = []
    seen = set()
    queue = deque([root_id])
    while queue:
        nid = queue.popleft()
        if nid in seen:
            continue
        seen.add(nid)
        order.append(nid)
        for cid in get_children(nid):
            if cid not in seen:
                queue.append(cid)
    return order


def classify_kind(has_children, perms):
    """Classify a storage row for plan counts.

    A node with children is a (derivative) template; a leaf with write perms is
    a desktop; a read-only leaf is a (base) template. Media rows are classified
    by the caller (they live in a separate table, no chain).
    """
    if has_children:
        return "template"
    return "desktop" if "w" in (perms or []) else "template"


class _Unplaceable(Exception):
    """A disk whose destination directory cannot be resolved."""

    def __init__(self, storage_id, reason):
        super().__init__(reason)
        self.storage_id = storage_id
        self.reason = reason


def split_moving_subtrees(order, parent_of, moves):
    """Split ONE tree's topo ``order`` into the sub-trees that actually move.

    ``item_kinds`` lets a selection move only some disk types, so a tree can
    come out as several independent sub-trees of moving disks hanging off
    disks that stay (typically desktops under a base template left behind).
    Each survivor is grouped under its topmost MOVING ancestor, which becomes
    that sub-tree's root — so every ``tree_id`` in the ledger is a disk the
    ledger actually holds, and the topo order inside a group is preserved.

    ``parent_of(node_id)`` returns the parent id when it is inside this tree,
    else ``None``; ``moves(node_id)`` says whether the disk is being migrated.
    Returns ``[(sub_root_id, [ids in topo order]), ...]``.
    """
    sub_root = {}
    groups = {}
    for nid in order:
        if not moves(nid):
            continue
        parent = parent_of(nid)
        # sub_root only ever holds MOVING nodes, so a hit means the parent moves
        root = sub_root[parent] if parent in sub_root else nid
        sub_root[nid] = root
        groups.setdefault(root, []).append(nid)
    return list(groups.items())


def stranded_by_selection(order, parent_of, moves):
    """Disks that would be left backing onto a moved parent: ``(parent, child)``
    pairs where the parent moves and the child does not.

    Moving a disk while leaving a derivative behind breaks that derivative's
    backing chain unless the derivative is rebased in place, which this planner
    does not do. The caller refuses such a selection rather than building a plan
    that silently strands disks.
    """
    return [
        (parent_of(nid), nid)
        for nid in order
        if not moves(nid) and parent_of(nid) is not None and moves(parent_of(nid))
    ]


#: the tree-start orders an admin can ask for. ``none`` is the historical
#: behaviour: whatever order the ledger rows come back in.
MIGRATION_ORDERS = ("none", "oldest_first", "newest_first")


def tree_order_key(moving_ids, descendants_of, accessed_of):
    """The usage key of ONE tree: how recently anything it moves was used.

    ``max``, not ``min``: a tree is as hot as its hottest disk. With ``min`` a
    tree holding one actively-used desktop would sort as cold because it also
    holds a forgotten one.

    Two rules compose here, and they are easy to read as contradicting each
    other. The key is taken over the disks that MOVE — a base template left
    behind as chain context has an irrelevant (and usually stale) usage date, so
    it must not decide anything. But a moving disk that HAS derivatives is as
    hot as they are: deriving a desktop stamps the new desktop, never the
    template it came from, so a template's own date understates it by up to
    years. So each mover contributes ``max(its own, all of its descendants')``,
    whether or not those descendants move.

    Returns ``None`` when nothing that moves has any usage data at all — the
    caller keeps those trees in a group of their own.
    """
    best = None
    for sid in moving_ids:
        for candidate in (sid, *descendants_of(sid)):
            value = accessed_of(candidate)
            if value and (best is None or value > best):
                best = value
    return best


def sort_tree_ids(tree_keys, order):
    """Order tree ids by their usage key (pure).

    ``tree_keys`` maps ``tree_id -> key|None``. ``none`` (or anything
    unrecognised) preserves the caller's order, which keeps the historical
    behaviour byte for byte.

    Trees with NO usage data go last in BOTH directions, never first: a disk we
    know nothing about is not evidence that it is cold, and with a byte budget
    "unknown" would otherwise consume the window ahead of disks we can actually
    reason about. Ties break on the tree id, and the two directions are exact
    inverses of one another over the trees that do have a key.
    """
    if order not in ("oldest_first", "newest_first"):
        return list(tree_keys)
    known = [t for t, k in tree_keys.items() if k is not None]
    unknown = sorted(t for t, k in tree_keys.items() if k is None)
    known.sort(key=lambda t: (tree_keys[t], t), reverse=order == "newest_first")
    return known + unknown


def budget_prefix(ordered_trees, bytes_of, budget):
    """The prefix of ``ordered_trees`` that fits in ``budget`` bytes (0 == no
    budget, everything fits).

    Mirrors what the runner actually does: a tree is admitted while the budget
    still allows a new one, and a tree already in flight always finishes, so the
    last admitted tree may overshoot. Answering this at plan time is the only
    way an admin can see, BEFORE approving a job, which trees will not move in
    this occurrence.
    """
    if not budget:
        return list(ordered_trees)
    fitting = []
    spent = 0
    for tree_id in ordered_trees:
        if spent >= budget:
            break
        fitting.append(tree_id)
        spent += bytes_of(tree_id)
    return fitting


def build_tree_items(migration_id, root_id, get_children, node_info, order=None):
    """Build the ``storage_migration_item`` dicts (state ``pending``) for ONE
    tree, in topo order.

    ``node_info(node_id) -> dict`` supplies per-disk data: ``kind``,
    ``src_path``, ``dst_path``, ``dst_dir``, ``size_bytes`` and (for non-root
    nodes) ``parent_storage_id`` / ``parent_dst_path`` / ``parent_dst_dir``.

    ``order`` is the pre-walked topo order for this tree; the caller passes the
    walk it already had to do to know which disks move, so the subtree is not
    traversed twice (every step is a DB read of the node's children).

    The root (topo_index 0) never rebases — its backing points at a parent
    OUTSIDE the migrated tree, which does not move — so its rebase target is
    cleared here regardless of what ``node_info`` returns.
    """
    order = walk_tree_topo(root_id, get_children) if order is None else order
    items = []
    for idx, nid in enumerate(order):
        info = node_info(nid)
        is_root = idx == 0
        items.append(
            {
                # Deterministic id == natural key, so re-planning a job upserts
                # the same rows (idempotent) instead of duplicating them.
                "id": f"{migration_id}--{nid}",
                "migration_id": migration_id,
                "storage_id": nid,
                "tree_id": root_id,
                "topo_index": idx,
                "state": "pending",
                "kind": info.get("kind", "desktop"),
                "src_path": info.get("src_path"),
                "dst_path": info.get("dst_path"),
                "dst_dir": info.get("dst_dir"),
                "parent_storage_id": info.get("parent_storage_id"),
                # Root has no in-tree parent to rebase onto.
                "parent_dst_path": None if is_root else info.get("parent_dst_path"),
                "parent_dst_dir": None if is_root else info.get("parent_dst_dir"),
                "size_bytes": int(info.get("size_bytes") or 0),
                "bytes_done": 0,
                "attempts": 0,
                "checkpoints": [],
            }
        )
    return items


def _bytes_by_kind(item_dicts):
    """Sum ``size_bytes`` grouped by item ``kind`` (template/desktop/media)."""
    out = {}
    for it in item_dicts:
        k = it.get("kind") or "other"
        out[k] = out.get(k, 0) + int(it.get("size_bytes") or 0)
    return out


def _count_by_kind(item_dicts):
    """Count items grouped by ``kind`` (template/desktop/media), mirroring
    :func:`_bytes_by_kind`. Every item has exactly one kind, so these counts sum
    to ``items_total`` — which ``trees`` does NOT (a standalone desktop is its own
    tree root yet is a desktop, not a template)."""
    out = {}
    for it in item_dicts:
        k = it.get("kind") or "other"
        out[k] = out.get(k, 0) + 1
    return out


def summarize_plan(item_dicts, not_moving=None, order=None, excluded=None):
    """Aggregate per-job totals from the built item dicts.

    Computed from the data (never incremented), matching the at-least-once
    ledger invariant. ``derivative_templates`` are template items that are not
    a tree root (``storage_id != tree_id``).

    ``not_moving`` counts, per kind, the disks the selection walked but does not
    move (``item_kinds`` filtered them out). They carry no ledger row — they are
    chain context, not work — so the plan preview is the only place an admin can
    see them, and "1.301 move, 7 stay" is the whole point of choosing kinds.
    """
    kinds = Counter(it.get("kind") for it in item_dicts)
    derivative_templates = sum(
        1
        for it in item_dicts
        if it.get("kind") == "template" and it["storage_id"] != it["tree_id"]
    )
    bytes_total = sum(int(it.get("size_bytes") or 0) for it in item_dicts)
    #: per-kind byte totals (template / desktop / media) so the UI can show a
    #: size next to each item-type count. Template covers root + derivative.
    bytes_by_kind = _bytes_by_kind(item_dicts)
    return {
        "trees": len({it["tree_id"] for it in item_dicts}),
        "derivative_templates": derivative_templates,
        "desktops": kinds.get("desktop", 0),
        "media": kinds.get("media", 0),
        "items_total": len(item_dicts),
        "items_by_kind": _count_by_kind(item_dicts),
        "bytes_total": bytes_total,
        "bytes_by_kind": bytes_by_kind,
        "bytes_done": 0,
        "state_counts": {"pending": len(item_dicts)} if item_dicts else {},
        "not_moving_by_kind": dict(not_moving or {}),
        "not_moving_total": sum((not_moving or {}).values()),
        #: trees left out because a disk in them has no resolvable destination.
        #: The plan is still built: one malformed row must not cost the estate
        #: its migration, but the admin has to see what stayed and why.
        "excluded_trees": list(excluded or ()),
        "excluded_disks_total": sum(e["disks"] for e in (excluded or ())),
        "order": order or "none",
        #: trees whose moving disks have no usage date. They sort last in BOTH
        #: directions, so a budget reaches them last either way.
        "order_trees_without_usage": len(
            {
                it["tree_id"]
                for it in item_dicts
                if it.get("tree_order_key") is None and "tree_order_key" in it
            }
        ),
    }


def aggregate_status(migration, items, *, include_items=False):
    """Build the admin-view aggregate for a migration from its loaded ledger
    (pure given ``migration`` + its ``items``).

    The single source of truth shared by the apiv4 status endpoint and the
    change-handler ``storage:migration`` socket emit, so both render identically.
    Everything is COUNT/SUM over the items (never an incremental counter); the
    aggregate ETA is bytes-remaining over the best observed EWMA throughput
    (``None`` until the first move completes). ``include_items`` adds the per-disk
    rows for the UI's expand.
    """
    from isardvdi_common.models.storage_migration import (
        compute_bytes_done,
        compute_state_counts,
        item_is_done,
    )

    by_tree = {}
    for it in items:
        by_tree.setdefault(it["tree_id"], []).append(it)
    trees = []
    for tree_id, tit in by_tree.items():
        s = summarize_plan(tit)
        trees.append(
            {
                "tree_id": tree_id,
                "root_storage_id": tree_id,
                "items_total": s["items_total"],
                "derivative_templates": s["derivative_templates"],
                "desktops": s["desktops"],
                "media": s["media"],
                "done": sum(1 for it in tit if item_is_done(it["state"])),
                "bytes_total": s["bytes_total"],
                "bytes_done": compute_bytes_done(tit),
                "state_counts": compute_state_counts(tit),
            }
        )
    bytes_total = sum(int(it.get("size_bytes") or 0) for it in items)
    bytes_done = compute_bytes_done(items)
    ewma = getattr(migration, "throughput_ewma", None) or {}
    mbps = max(ewma.values()) if ewma else None
    eta = tree_eta_seconds(max(0, bytes_total - bytes_done), mbps)
    cfg = getattr(migration, "config", None) or {}
    cfg_window = cfg.get("window") or {}
    payload = {
        "id": migration.id,
        "status": str(migration.status),
        # what this job moves and where to (src/dst pool ids, kind, path/category)
        # — static, but carried on every aggregate so the admin table + detail can
        # always show the origin → destination route (resolved to pool names in the
        # UI). Shared by the status endpoint and the socket emit.
        "selection": getattr(migration, "selection", None) or {},
        "config": cfg,
        "current_window": getattr(migration, "current_window", None),
        "eta_seconds": None if eta is None else int(eta),
        # schedule surface for the admin table (recurring badge + days + next-run)
        "recurring": bool(cfg.get("recurring")),
        "days": cfg_window.get("days") or [],
        # next-run is filled live by the status endpoint (needs now-in-tz); the
        # runner also stamps current_window each tick.
        "next_run_seconds": (getattr(migration, "current_window", None) or {}).get(
            "next_run_seconds"
        ),
        "totals": {
            "trees": len(by_tree),
            "derivative_templates": sum(t["derivative_templates"] for t in trees),
            "desktops": sum(t["desktops"] for t in trees),
            "media": sum(t["media"] for t in trees),
            "items_total": len(items),
            "items_by_kind": _count_by_kind(items),
            "bytes_total": bytes_total,
            "bytes_by_kind": _bytes_by_kind(items),
            "bytes_done": bytes_done,
            "done": sum(1 for it in items if item_is_done(it["state"])),
            "state_counts": compute_state_counts(items),
        },
        "trees": trees,
    }
    if include_items:
        payload["items"] = [
            {
                "id": it.get("id"),
                "storage_id": it["storage_id"],
                "tree_id": it["tree_id"],
                "topo_index": it.get("topo_index", 0),
                "kind": it.get("kind"),
                "state": str(it["state"]),
                "size_bytes": int(it.get("size_bytes") or 0),
                "error": it.get("error"),
                "dst_path": it.get("dst_path"),
            }
            for it in sorted(
                items, key=lambda x: (x["tree_id"], x.get("topo_index", 0))
            )
        ]
    return payload


def probe_actual_size(path, timeout=30):
    """Live ``qemu-img info -U --output=json`` probe -> ``actual-size`` bytes,
    or ``None`` on any error. Runs where the disks are mounted (storage worker);
    the plan seeds from the DB and refreshes with this when available.
    """
    try:
        result = subprocess.run(
            ["qemu-img", "info", "-U", "--output=json", str(path)],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=True,
            timeout=timeout,
        )
        size = json.loads(result.stdout).get("actual-size")
        return int(size) if size is not None else None
    except (
        subprocess.CalledProcessError,
        subprocess.TimeoutExpired,
        json.JSONDecodeError,
        FileNotFoundError,
        OSError,
        ValueError,
        TypeError,
    ):
        return None


# --------------------------------------------------------------------------- #
# Per-disk saga decision layer (pure) — the correctness-critical ordering
# --------------------------------------------------------------------------- #
#: states past which a disk needs no phase-A (move/rebase) work. Phase A ends at
#: ``rebased`` (moved + backing repointed); the DB commit (db_update) is DEFERRED
#: to Phase B, past the verify gate, so a disk whose destination fails
#: verification is never left committed to a bad/unverified destination (F1).
#: ``quarantined`` is terminal off-path, so a re-armed tree with one quarantined
#: disk still settles (that disk is skipped in the walk like ``skipped``).
_PHASE_A_DONE = {"rebased", "db_updated", "released", "skipped", "quarantined"}
#: terminal states
_DONE = {"released", "skipped", "quarantined"}


def _job_finished(status):
    return status == "finished"


def _job_failed(status):
    return status in ("failed", "stopped", "canceled")


def item_in_place(item):
    """True when a disk's destination equals its current location — a same-pool
    selection, or a subtree member that already lives in the destination pool.
    Moving it is a no-op and deleting the "source" would destroy the live disk
    in place, so the move and the release are both skipped (saga-1)."""
    dst = item.get("dst_path")
    return bool(dst) and dst == item.get("src_path")


def all_in_place(items):
    """True when a NON-EMPTY plan resolves ENTIRELY in-place — every disk's
    destination equals its source (``item_in_place``). This is the path/category
    equivalent of a same-pool migration: the destination pool is the one the
    disks already live in, so nothing would move. An empty plan is not
    "all in place" (a recurring job may legitimately start with an empty scope)."""
    items = list(items)
    return bool(items) and all(item_in_place(it) for it in items)


def decide_item_action(item, job_status_fn):
    """Decide the next action for ONE disk given its state and the status of
    its in-flight RQ task (``job_status_fn(task_id) -> status|None``).

    Actions: ``start_move``, ``skip_move`` (dst == src), ``mark_moved``,
    ``start_rebase``, ``mark_rebased``, ``skip_rebase`` (root), ``wait`` (task
    still running), ``fail``, ``noop`` (Phase A done / already terminal).

    Phase A ends at ``rebased``: the DB commit (db_update) and the pre-release
    verify gate are Phase B, driven by :func:`tree_next` once the WHOLE tree is
    moved+rebased. A ``rebased`` disk therefore has no further Phase-A action.
    """
    state = str(item["state"])
    is_root = item.get("topo_index", 0) == 0 or not item.get("parent_dst_path")

    if state == "pending":
        # dst == src: nothing to move (the file is already there); never rsync a
        # disk onto itself. Advance straight to moved.
        return "skip_move" if item_in_place(item) else "start_move"
    if state == "moving":
        st = job_status_fn(item.get("move_task_id"))
        if _job_finished(st):
            return "mark_moved"
        if _job_failed(st):
            return "fail"
        if st is None:
            # The in-flight job is gone (redis expired / cleared on a restart).
            # Re-enqueue: move with remove_source_file=False is idempotent.
            return "start_move"
        return "wait"
    if state == "moved":
        if is_root:
            return "skip_rebase"
        if not item.get("rebase_task_id"):
            return "start_rebase"
        st = job_status_fn(item.get("rebase_task_id"))
        if _job_finished(st):
            return "mark_rebased"
        if _job_failed(st):
            return "fail"
        if st is None:
            # Lost rebase job — re-enqueue: rebase -u is idempotent.
            return "start_rebase"
        return "wait"
    # ``rebased`` ends Phase A; db_update is deferred to Phase B (tree_next),
    # after the whole tree's pre-release verify gate passes.
    return "noop"


def verify_gate_state(item, job_status_fn):
    """State of ONE moved+rebased (``rebased``) disk's pre-release destination
    gate, the invariant the whole saga rests on: a disk's row is never repointed
    (db_update) and its source never ``move_delete``d unless its destination
    exists, passes ``qemu-img check`` and (for a non-root) backs onto the
    parent's NEW path. The check runs as a worker
    task (the disks live on the storage worker), so the gate is async like the
    move/rebase steps:

    * ``"start"``  — no verify task yet, or the job vanished on a restart;
      enqueue/re-enqueue it (read-only, idempotent);
    * ``"wait"``   — verify still running;
    * ``"fail"``   — verify failed (destination bad) -> terminalize, retain source;
    * ``"passed"`` — verify finished clean -> the source may now be deleted.

    UNCONDITIONAL — not relaxed by ``config.verify`` (that knob only governs the
    post-rebase check). It catches the data-loss path where a move "succeeds"
    (rsync returns a non-zero rc WITHOUT raising) yet leaves the destination
    absent/partial, which for a ROOT disk skips rebase and would otherwise reach
    release with zero destination verification.

    A passed gate is PERSISTED on the item (``verify_passed``) and short-circuits
    here: unlike move/rebase — whose finished job is immediately recorded as a
    state transition (``moved``/``rebased``) — a passed verify does NOT advance
    the disk's state (db_update is deferred to Phase B2, past the whole-tree
    gate), so without a durable flag the "passed" observation lived ONLY in the
    ephemeral rq job result. On a many-disk tree the gate is driven one disk per
    tick, so an early disk's verify job expires from redis (``job_status`` -> None
    -> ``"start"``) long before the last disk is verified — the tree could never
    see every disk passed at once and re-verified forever. The flag makes each
    pass monotonic, exactly as the ``moved``/``rebased`` transitions do for A.
    """
    if item.get("verify_passed"):
        return "passed"
    if not item.get("verify_task_id"):
        return "start"
    st = job_status_fn(item.get("verify_task_id"))
    if _job_finished(st):
        return "passed"
    if _job_failed(st):
        return "fail"
    if st is None:
        return "start"
    return "wait"


def plan_autostart_deactivation(items, domains_of):
    """Plan the up-front autostart suppression for a migration (qcow-2).

    ``domains_of(storage_id) -> iterable`` yields a disk's domains (each with
    ``id`` and ``server_autostart``). Returns ``(writes, to_deactivate)``:

    * ``writes`` — ``[(item, records)]`` for items whose autostart has not yet
      been recorded; each record is ``{"id", "was_on"}`` capturing the CURRENT
      live ``server_autostart``. The caller persists these FIRST and only THEN
      deactivates, so a crash between the two never loses the pre-suppression
      value (the record already holds ``was_on=True`` for ``reactivate`` to
      restore) — closing the loss window the deactivate-before-persist ordering
      would otherwise open.
    * ``to_deactivate`` — domain ids recorded ``was_on=True`` that are STILL
      live-on. Re-derived from the full ledger every prepare (so a crash between
      persist and deactivate re-suppresses on resume — crash-safe), but filtered
      to the not-yet-suppressed set so ``deactivate_autostart`` does not re-fire
      (and re-notify) once a domain is already off.
    """
    writes = []
    to_deactivate = []
    for item in items:
        recorded = item.get("autostart_domains")
        if recorded is None:
            doms = list(domains_of(item["storage_id"]))
            records = [
                {"id": d.id, "was_on": bool(getattr(d, "server_autostart", False))}
                for d in doms
            ]
            writes.append((item, records))
            to_deactivate += [
                d.id for d in doms if bool(getattr(d, "server_autostart", False))
            ]
        else:
            # already recorded: only re-suppress domains recorded was_on=True that
            # are still live-on (a crash between persist and deactivate). Skip the
            # live read when nothing in this item could need suppressing.
            candidates = [r["id"] for r in recorded if r.get("was_on")]
            if not candidates:
                continue
            live = {
                d.id: bool(getattr(d, "server_autostart", False))
                for d in domains_of(item["storage_id"])
            }
            to_deactivate += [cid for cid in candidates if live.get(cid, False)]
    return writes, to_deactivate


def quiesce_decision(domain_status, force_stop):
    """Decide how to quiesce a disk's domain before moving it.

    ``ok`` — already safe to move (stopped, failed, or no domain/template);
    ``force_stop`` — running and the admin opted to force-stop it;
    ``skip`` — running and the admin did NOT opt to force-stop, so the disk
    (and its subtree) is skipped rather than moving a live disk.
    """
    if domain_status in (None, "Stopped", "Failed"):
        return "ok"
    return "force_stop" if force_stop else "skip"


def descendant_item_ids(items, storage_id, include_self=False):
    """Item ids of every disk descending from ``storage_id`` (via
    ``parent_storage_id``), for cascading a skip down a subtree."""
    by_parent = {}
    for it in items:
        by_parent.setdefault(it.get("parent_storage_id"), []).append(it)
    result = set()
    if include_self:
        result.update(it["id"] for it in items if it["storage_id"] == storage_id)
    stack = [storage_id]
    while stack:
        sid = stack.pop()
        for child in by_parent.get(sid, []):
            if child["id"] not in result:
                result.add(child["id"])
                stack.append(child["storage_id"])
    return result


#: actions that represent real forward progress in a tick (vs waiting on an
#: in-flight RQ task / gated / already-done). A drain loop stops once a whole
#: tick yields none of these — every tree is then waiting and re-ticking now
#: would just spin.
PROGRESS_ACTIONS = {
    "start_move",
    "skip_move",
    "mark_moved",
    "start_rebase",
    "mark_rebased",
    "skip_rebase",
    "db_update",
    "start_verify",
    "mark_verified",
    "release",
    "skip_release",
}


def tick_made_progress(results):
    """True if any tree advanced this tick. ``results`` is the
    ``[(tree_id, item_id, action), ...]`` list returned by ``tick``."""
    return any(action in PROGRESS_ACTIONS for (_tree, _item, action) in results)


# --------------------------------------------------------------------------- #
# Window + EWMA-ETA admission (pure) — P2.2
#
# Admission decides, at TREE granularity, whether a not-yet-started tree may
# begin NOW: only inside the maintenance window and only if its estimated
# transfer time fits the time left in the window (and each single disk fits the
# 12h move-task timeout). Throughput is an EWMA of observed MB/s per src:dst
# pool pair, so the estimate self-corrects as the run proceeds.
# --------------------------------------------------------------------------- #
def parse_hhmm(value):
    """``"HH:MM"`` -> minutes since midnight, or ``None`` if unset/invalid."""
    if not value:
        return None
    try:
        h, m = str(value).split(":")
        h, m = int(h), int(m)
    except (ValueError, AttributeError):
        return None
    if not (0 <= h < 24 and 0 <= m < 60):
        return None
    return h * 60 + m


def window_is_open(start_min, end_min, now_min):
    """Is ``now_min`` inside the daily ``[start, end)`` window? An unset window
    (either bound ``None``) or a zero-width one (``start == end``) is always
    open. Handles overnight windows (``start > end``)."""
    if start_min is None or end_min is None or start_min == end_min:
        return True
    if start_min < end_min:
        return start_min <= now_min < end_min
    return now_min >= start_min or now_min < end_min  # overnight


def window_remaining_seconds(start_min, end_min, now_min):
    """Seconds from ``now_min`` until the window closes. ``inf`` when there is
    no window (unbounded), ``0`` when the window is currently closed."""
    if start_min is None or end_min is None or start_min == end_min:
        return float("inf")
    if not window_is_open(start_min, end_min, now_min):
        return 0
    rem_min = end_min - now_min if end_min > now_min else (24 * 60 - now_min) + end_min
    return rem_min * 60


# --------------------------------------------------------------------------- #
# Day-of-week schedule (pure) — layered on the daily HH:MM window
#
# A recurring migration's window is open only on selected weekdays within the
# daily range. An overnight window's post-midnight tail belongs to the day the
# window STARTED on, so a "Friday 22:00-06:00" occurrence is one continuous
# instance keyed to Friday even though part of it runs on Saturday.
# Weekdays are Mon=0 … Sun=6 (datetime.weekday()).
# --------------------------------------------------------------------------- #
def normalize_days(days):
    """``days`` -> a set of in-range weekdays (0..6), or ``None`` when the
    restriction is empty/absent (== active every day). An all-invalid list also
    collapses to ``None`` (every day) rather than a never-open window."""
    if not days:
        return None
    out = set()
    for d in days:
        try:
            di = int(d)
        except (ValueError, TypeError):
            continue
        if 0 <= di <= 6:
            out.add(di)
    return out or None


def _occurrence_weekday(start_min, end_min, weekday, now_min):
    """Weekday the currently-open window instance STARTED on. For an overnight
    window (``start > end``) the post-midnight tail (``now < end``) belongs to
    the previous day; every other case is ``weekday`` itself."""
    if (
        start_min is not None
        and end_min is not None
        and start_min > end_min
        and now_min < end_min
    ):
        return (weekday - 1) % 7
    return weekday


def window_is_open_days(start_min, end_min, days, weekday, now_min):
    """Is the window open now, given the daily range AND the selected weekdays?

    First the time check (:func:`window_is_open`, which already handles unset /
    zero-width / overnight windows), then the day check: the occurrence's START
    weekday must be selected. ``days`` empty/None (or ``weekday`` None) imposes no
    day restriction — every day, preserving pre-schedule behaviour.
    """
    if not window_is_open(start_min, end_min, now_min):
        return False
    dset = normalize_days(days)
    if dset is None or weekday is None:
        return True
    return _occurrence_weekday(start_min, end_min, weekday, now_min) in dset


def window_remaining_seconds_days(start_min, end_min, days, weekday, now_min):
    """Seconds until the window closes, honouring the day filter. ``0`` when the
    window is closed today (wrong weekday or outside the range); otherwise the
    same time-to-close as :func:`window_remaining_seconds` (the close boundary is
    a time-of-day, unaffected by which weekday opened it)."""
    if not window_is_open_days(start_min, end_min, days, weekday, now_min):
        return 0
    return window_remaining_seconds(start_min, end_min, now_min)


def occurrence_key(now_dt, start_min, end_min):
    """Stable per-occurrence key: the ISO date (``YYYY-MM-DD``) the current
    window instance STARTED on. For an overnight window's post-midnight tail this
    is the previous calendar date, so one occurrence yields one key for its whole
    duration — the reconciler re-scans a recurring job exactly once per
    occurrence (when this key changes)."""
    from datetime import timedelta

    now_min = now_dt.hour * 60 + now_dt.minute
    day = now_dt.date()
    if (
        start_min is not None
        and end_min is not None
        and start_min > end_min
        and now_min < end_min
    ):
        day = day - timedelta(days=1)
    return day.isoformat()


def next_occurrence_seconds(start_min, end_min, days, weekday, now_min):
    """Seconds until the window NEXT opens on a selected weekday (admin-table
    lookahead). ``0`` when open now; ``None`` when there is no schedule at all
    (unbounded time and no day filter — always open, no meaningful next-run).
    Scans forward up to 7 days; an unset start opens at midnight."""
    dset = normalize_days(days)
    no_time = start_min is None or end_min is None
    if no_time and dset is None:
        return None
    if window_is_open_days(start_min, end_min, days, weekday, now_min):
        return 0
    open_at = 0 if start_min is None else start_min
    wd0 = 0 if weekday is None else weekday
    for k in range(0, 8):
        wd = (wd0 + k) % 7
        if dset is not None and wd not in dset:
            continue
        delta = k * 1440 + open_at - now_min
        if delta > 0:
            return delta * 60
    return None


def next_run_for_window(window, now_dt):
    """Seconds until ``window`` (a ``{start,end,days,tz}`` dict) next opens on a
    selected weekday, given an aware ``now_dt``. ``None`` when there is no
    schedule. Pure given ``now_dt`` — the caller supplies now-in-tz."""
    if not window:
        return None
    return next_occurrence_seconds(
        parse_hhmm(window.get("start")),
        parse_hhmm(window.get("end")),
        window.get("days") or [],
        now_dt.weekday(),
        now_dt.hour * 60 + now_dt.minute,
    )


def ewma_update(prev, sample, alpha=0.3):
    """Exponentially-weighted moving average. A non-positive/None sample is
    ignored (returns ``prev``); the first valid sample seeds the average."""
    if sample is None or sample <= 0:
        return prev
    if prev is None or prev <= 0:
        return sample
    return alpha * sample + (1 - alpha) * prev


def tree_eta_seconds(bytes_remaining, mbps):
    """Seconds to transfer ``bytes_remaining`` at ``mbps`` (MB/s, 1e6 bytes).
    ``None`` when throughput is unknown (no sample yet — can't estimate)."""
    if not mbps or mbps <= 0:
        return None
    if bytes_remaining <= 0:
        return 0.0
    return bytes_remaining / (mbps * 1_000_000)


def tree_admitted(tree_eta_s, max_disk_eta_s, remaining_window_s, task_timeout=43200):
    """Admit a not-yet-started tree only if it fits.

    * A single disk whose ETA exceeds the move-task timeout can never finish a
      move, so the tree is never admitted (respect the 12h timeout).
    * Unknown tree ETA (``None``, no throughput sample yet) is admitted
      optimistically — there is nothing to estimate against on a cold start.
    * Otherwise admit only if the whole-tree ETA fits the time left in the
      window (``inf`` when there is no window).
    """
    if max_disk_eta_s is not None and max_disk_eta_s > task_timeout:
        return False
    if tree_eta_s is None:
        return True
    return tree_eta_s <= remaining_window_s


# --------------------------------------------------------------------------- #
# Per-job parallelism (pure) — P2.3
#
# A migration may run several independent trees concurrently, bounded by
# ``config.parallelism`` so the storage worker is not oversubscribed. In-flight
# trees always keep advancing; only the START of a new tree is gated by a free
# slot (and by the window/ETA admission above).
# --------------------------------------------------------------------------- #
#: states past which a disk needs no further saga work of any kind
_TERMINAL_STATES = {"released", "skipped", "failed", "quarantined"}


def tree_phase(item_states):
    """Phase of a tree from its item states: ``"done"`` (every disk terminal),
    ``"not_started"`` (every disk still pending), else ``"in_flight"``."""
    states = [str(s) for s in item_states]
    if not states or all(s in _TERMINAL_STATES for s in states):
        return "done"
    if all(s == "pending" for s in states):
        return "not_started"
    return "in_flight"


def admission_slots(tree_phases, parallelism):
    """How many not-started trees may start this tick: the parallelism cap minus
    the trees already in flight (each consumes a slot). ``parallelism`` is
    clamped to a minimum of 1."""
    p = max(1, int(parallelism or 1))
    in_flight = sum(1 for ph in tree_phases if ph == "in_flight")
    return max(0, p - in_flight)


# --------------------------------------------------------------------------- #
# Cancel = finish-current-tree (pure) — P2.4
# --------------------------------------------------------------------------- #
def cancel_target(status):
    """Target status for an admin cancel request.

    A job that may have in-flight trees or suppressed autostart to unwind
    (running / window_closed / paused / already finishing) goes to
    ``finishing_tree``: the reconciler stops starting new trees, lets the
    current tree(s) finish cleanly, restores autostart, then flips it to
    ``canceled``. A job that never started (draft / planned) cancels outright.
    """
    return (
        "finishing_tree"
        if str(status) in {"running", "window_closed", "paused", "finishing_tree"}
        else "canceled"
    )


def recurring_status_target(
    is_complete,
    any_in_flight,
    win_open,
    finishing,
    any_failed,
    recurring,
):
    """End-of-tick next job status (pure). Returns the target status string, or
    ``None`` to mean "leave the caller's existing window branch in charge"
    (one-shot running<->window_closed, or a still-draining finishing job).

    * finishing (cancel): -> ``canceled`` once complete, else ``None``.
    * recurring: NEVER self-terminates — complete -> ``scheduled`` (idle);
      otherwise ``running`` while in-window or with an in-flight tree, else
      ``scheduled`` (between occurrences).
    * one-shot: complete -> ``failed`` if any disk failed else ``completed``;
      still draining -> ``None`` (existing window branch decides).

    HELD — recurring FAILURE policy: ``any_failed`` is accepted but does NOT
    terminalize a recurring job here (it stays alive and retries next
    occurrence). The quarantine-after-N vs pause-for-attention decision plugs in
    at this exact point once confirmed.
    """
    if finishing:
        return "canceled" if is_complete else None
    if recurring:
        if is_complete:
            return "scheduled"
        return "running" if (win_open or any_in_flight) else "scheduled"
    if is_complete:
        return "failed" if any_failed else "completed"
    return None


# --------------------------------------------------------------------------- #
# Recurring re-scan cadence + failure policy + audit (pure)
# --------------------------------------------------------------------------- #
#: Audit results that mean bytes were actually copied to the destination.
#: ``in_place`` is a release with no copy (dst == src), so it spends no budget.
_BUDGET_SPENDING_RESULTS = {"moved_ok"}


def occurrence_bytes_moved(items, occurrence):
    """Bytes committed to the destination DURING ``occurrence``.

    Read from each item's append-only ``audit`` records, which carry the
    occurrence they belong to -- NOT from the item's current state. A released
    item keeps that state for the job's whole life (``_rearm_for_occurrence``
    re-arms only failed/skipped disks, never released ones), so a state-based
    sum is cumulative: it would spend a recurring job's budget on its first
    occurrence and block every later one for ever.

    Counted at commit, not mid-flight, so an in-flight tree does not spend
    budget until it releases -- the same basis as ``compute_bytes_done``.
    """
    total = 0
    for it in items:
        for rec in it.get("audit") or []:
            if rec.get("occurrence") != occurrence:
                continue
            if rec.get("result") in _BUDGET_SPENDING_RESULTS:
                total += int(rec.get("size_bytes") or 0)
    return total


def budget_allows_new_tree(bytes_moved, max_bytes):
    """Whether another tree may START under the per-occurrence byte budget.

    ``max_bytes`` of 0 means unlimited. The budget gates only the START of a
    tree: one already in flight always finishes, since stopping mid-tree would
    leave a half-migrated backing chain. So the budget is a floor on what a run
    moves, not a hard ceiling -- the last tree may overshoot it.

    This is deliberately operator-set rather than probe-derived: on a
    thin-provisioned pool (VDO) the filesystem reports LOGICAL free space while
    the real limit is physical fill, so no statvfs reading can size this safely.
    """
    if not max_bytes:
        return True
    return bytes_moved < max_bytes


def should_rescan(cadence, occurrence_key, last_occurrence, is_drained, window_open):
    """Whether a recurring job re-scans this tick, per its cadence. Never outside
    the window. ``edge`` only at the occurrence edge (new key); ``edge_on_drain``
    also once the current batch has drained; ``continuous`` every tick in-window.
    (An occurrence-edge re-scan additionally re-arms failed/skipped disks — see
    ``plan_tree_rearm``; between edges only new disks are inserted.)"""
    if not window_open:
        return False
    is_edge = occurrence_key != last_occurrence
    if cadence == "continuous":
        return True
    if cadence == "edge_on_drain":
        return is_edge or is_drained
    return is_edge  # "edge" (default fallback)


def plan_tree_rearm(tree_ledger, policy, quarantine_after):
    """Decide a tree's re-arm actions at an occurrence edge. Returns
    ``(to_quarantine, to_rearm)`` where each entry is ``(item, occurrence_failures)``.

    A tree that already holds a ``quarantined`` disk is DEAD — it cannot migrate
    around a stuck disk, so nothing is touched. Under ``retry_quarantine`` a disk
    whose consecutive-occurrence failures would reach ``quarantine_after`` is
    quarantined (and its tree left dead: nothing re-armed). Otherwise every
    ``failed`` disk (occurrence_failures +1) and ``skipped`` disk (streak reset to
    0) is re-armed to pending; ``released`` / in-flight disks are left untouched.
    ``retry_forever`` / ``pause`` never quarantine (they keep counting / re-arming).
    """
    if any(str(it["state"]) == "quarantined" for it in tree_ledger):
        return [], []
    hits = []
    for it in tree_ledger:
        if str(it["state"]) == "failed":
            occ = int(it.get("occurrence_failures") or 0) + 1
            if policy == "retry_quarantine" and occ >= quarantine_after:
                hits.append((it, occ))
    if hits:
        return hits, []
    rearm = []
    for it in tree_ledger:
        s = str(it["state"])
        if s == "failed":
            rearm.append((it, int(it.get("occurrence_failures") or 0) + 1))
        elif s == "skipped":
            rearm.append((it, 0))
    return [], rearm


def build_audit_record(item, result, occurrence, now):
    """One append-only AUDIT record for the downloadable log: what happened to a
    disk on a given occurrence. ``result`` is one of moved_ok | failed | skipped |
    quarantined | in_place. ``now`` is the finish timestamp; ``started_at`` is the
    disk's move start (``None`` if it never moved)."""
    return {
        "occurrence": occurrence,
        "occurrence_time": now,
        "storage_id": item.get("storage_id"),
        "kind": item.get("kind"),
        "tree_id": item.get("tree_id"),
        "src_path": item.get("src_path"),
        "dst_path": item.get("dst_path"),
        "result": result,
        "size_bytes": int(item.get("size_bytes") or 0),
        "error": item.get("error"),
        "started_at": item.get("move_started_at"),
        "finished_at": now,
        # Still moved_ok: a new result string would drop the disk out of
        # summarize_audit's bytes_moved total.
        "source_retained": bool(item.get("source_retained")),
        "source_retained_path": item.get("source_retained_path"),
    }


def summarize_audit(records):
    """Summary header for the log: record count, counts by result, bytes actually
    moved (``moved_ok`` only), wall-clock duration (max finish − min start) and the
    number of distinct occurrences."""
    counts = {}
    bytes_moved = 0
    starts = []
    finishes = []
    occurrences = set()
    for rec in records:
        res = rec.get("result")
        counts[res] = counts.get(res, 0) + 1
        if res == "moved_ok":
            bytes_moved += int(rec.get("size_bytes") or 0)
        if rec.get("started_at") is not None:
            starts.append(float(rec["started_at"]))
        if rec.get("finished_at") is not None:
            finishes.append(float(rec["finished_at"]))
        if rec.get("occurrence") is not None:
            occurrences.add(rec["occurrence"])
    duration = (max(finishes) - min(starts)) if (starts and finishes) else None
    return {
        "records": len(records),
        "counts": counts,
        "bytes_moved": bytes_moved,
        "duration_seconds": duration,
        "occurrences": len(occurrences),
    }


#: A disk is COMMITTED once its storage row has been re-pointed at the new
#: location (``db_updated``) or it is already ``released``. Before that the source
#: is still the authoritative copy, so a cancel can discard the in-progress work.
_COMMITTED_STATES = {"db_updated", "released"}


def tree_has_committed_disk(tree_items):
    """True when any disk in the tree has reached the commit point — its storage
    row re-pointed at the new location (``db_updated``) or already ``released``.
    Before that the source is still byte-identical and authoritative, so a cancel
    can discard the in-progress work and skip the tree with no data loss."""
    return any(str(it["state"]) in _COMMITTED_STATES for it in tree_items)


def cancel_skips_tree(tree_items, action, finishing):
    """Under an admin cancel (``finishing_tree``), True when an in-flight tree
    must be SKIPPED rather than start/resume more work.

    The cancel-analysis case: an abandoned move on a tree with NO committed disk
    (the move was enqueued but the worker died at 0 bytes) would otherwise be
    RESUMED up to ``MAX_ABANDON_RESTARTS`` times before the bound terminalizes
    it — a cancelled admin should not have an un-started, possibly large move
    resumed. So when the next action would start/resume a move/rebase/verify and
    nothing in the tree has committed yet, discard the in-progress work and skip
    (sources retained). A tree that ALREADY committed a disk still finishes
    normally (finish-current-tree + verify-all-then-release-all)."""
    return (
        finishing
        and action in ("start_move", "start_rebase", "start_verify")
        and not tree_has_committed_disk(tree_items)
    )


def task_error_line(exc_info, fallback):
    """The last line of a worker traceback — the sentence that says WHY (pure).

    A storage task that refuses its work raises with everything an admin needs
    on that final line: which file, which destination, how much space was left
    and what the floor was. Reporting the disk as "move/rebase task failed"
    keeps all of it in the worker's log, which is not where the person reading
    the migration panel is looking.
    """
    lines = [line.strip() for line in (exc_info or "").splitlines() if line.strip()]
    return lines[-1] if lines else fallback


def plan_tree_failure(tree_items, failed_storage_id, reason=None):
    """Terminalize a whole tree after one of its disks fails, so the job reaches
    a terminal state (and autostart is restored) instead of wedging on a
    permanently-``blocked`` tree.

    The failed disk becomes ``failed``; its descendants and every other
    not-yet-terminal disk in the tree become ``skipped`` — the tree is abandoned
    with all sources retained (move_delete never ran), so there is no data loss.
    A committed (``db_updated``) ancestor is abandoned too: its source is never
    deleted, so it stays bootable via its new location and any abandoned child
    stays bootable via the retained source.

    ``reason`` is what the failing task actually said; without it the disk is
    marked with a generic sentence that tells the admin nothing they can act on.

    Returns ``[(item, new_state, reason)]`` for the items that must change
    (already-terminal disks are left untouched).
    """
    descendants = descendant_item_ids(tree_items, failed_storage_id)
    out = []
    for it in tree_items:
        if str(it["state"]) in _TERMINAL_STATES:
            continue
        if it["storage_id"] == failed_storage_id:
            out.append((it, "failed", reason or "move/rebase task failed"))
        elif it["id"] in descendants:
            out.append((it, "skipped", "ancestor disk failed"))
        else:
            out.append((it, "skipped", "tree abandoned after a disk in it failed"))
    return out


def tree_next(tree_items, job_status_fn):
    """Decide the next ``(item, action)`` for ONE tree.

    Phase A (move/rebase) is strictly serial, top-to-bottom: advance the
    lowest-topo disk not yet moved+rebased; a child is only reached once its
    parent is ``rebased`` (so the child's rebase target — the parent's file at
    its new path — exists). A ``failed`` disk blocks the tree.

    Phase B runs once EVERY disk in the tree is moved+rebased, in three strictly
    ordered sub-steps (each one-action-per-tick): **verify-all**, then
    **db_update-all**, then **release-all**. The DB repoint (db_update) is
    DEFERRED to here, AFTER the whole tree's verify gate passes — so a gate
    failure terminalizes the tree with every row still pointing at its retained
    source, never at a bad/unverified destination (F1). Deleting the source
    (move_delete) fires last, after every row has repointed, so a late gate
    failure can never strand an earlier disk's child on a recycled parent source.

    Returns ``(None, "done")`` when the whole tree is terminal, ``(item,
    "blocked")`` when a disk failed.
    """
    items = sorted(tree_items, key=lambda it: it.get("topo_index", 0))
    # Phase A — one disk in flight, parents before children (ends at ``rebased``).
    for it in items:
        s = str(it["state"])
        if s in _PHASE_A_DONE:
            continue
        if s == "failed":
            return (it, "blocked")
        return (it, decide_item_action(it, job_status_fn))
    # Phase B — every disk is moved+rebased. verify-all -> db_update-all ->
    # release-all, each one-action-per-tick.
    rebased = [it for it in items if str(it["state"]) == "rebased"]
    committed = [it for it in items if str(it["state"]) == "db_updated"]
    # B1 — drive the destination gate on every rebased disk that still needs it.
    # An in-place disk (dst == src) never moved: no destination to verify and no
    # separate source to delete, so it is excluded from the gate entirely.
    # The whole tree is scanned before any non-fail action so a failed gate
    # ALWAYS terminalizes promptly (fail takes priority over starting/recording a
    # sibling's gate — no pointless work on a doomed tree). A "wait" does NOT
    # short-circuit either: every disk's (idempotent, read-only) verify is
    # enqueued and a freshly-passed one is recorded within the SAME drain cycle,
    # so all disks verify concurrently on the worker instead of one-per-tick
    # (which, at ~1 disk/min, let early verify results expire before the last disk
    # was reached). "wait" is reported only once the whole tree is passed or
    # in-flight, so db_update (B2) still waits for the entire tree's gate to pass.
    to_start = to_mark = waiting = None
    for it in rebased:
        if item_in_place(it):
            continue
        gate = verify_gate_state(it, job_status_fn)
        if gate == "fail":
            return (it, "fail")
        if gate == "start":
            to_start = to_start or it
        elif gate == "passed" and not it.get("verify_passed"):
            # Passed but not yet persisted -> record it durably so the pass
            # survives the rq job result expiring (see verify_gate_state).
            to_mark = to_mark or it
        elif gate == "wait":
            waiting = waiting or it
    if to_start is not None:
        return (to_start, "start_verify")
    if to_mark is not None:
        return (to_mark, "mark_verified")
    if waiting is not None:
        return (waiting, "wait")
    # B2 — every destination verified; NOW repoint the rows (db_update). Deferred
    # to here (past the gate) so a verify failure never leaves a row committed to
    # a destination that did not pass. An in-place disk is repointed too: its
    # directory is unchanged, but a child rebased onto a moved parent still needs
    # its backing fields synced (saga-3).
    for it in rebased:
        return (it, "db_update")
    # B3 — every row committed; delete the sources last (move_delete fires last).
    # An in-place disk has no separate source to delete, so it is released
    # directly.
    for it in committed:
        return (it, "skip_release" if item_in_place(it) else "release")
    return (None, "done")


# --------------------------------------------------------------------------- #
# Selection -> roots (pure core + DB-driven wrapper)
# --------------------------------------------------------------------------- #
def _selection_members(storages, kind, src_pool_id, category_id, path_prefix):
    """Ids of the storages the selection covers (the migration SET)."""
    if kind == "pool":
        return {s["id"] for s in storages if s.get("pool_id") == src_pool_id}
    if kind == "category":
        return {s["id"] for s in storages if s.get("category") == category_id}
    if kind == "path":
        prefix = path_prefix or ""
        return {
            s["id"]
            for s in storages
            if (s.get("directory_path") or "").startswith(prefix)
        }
    return set()


def compute_roots(
    storages,
    *,
    kind="pool",
    src_pool_id=None,
    category_id=None,
    path_prefix=None,
    tree_ids=None,
):
    """Resolve a selection to its migration tree-roots (pure).

    ``storages`` is a list of light dicts ``{id, parent, pool_id, category,
    directory_path}``. Explicit ``tree_ids`` win (filtered to existing ids,
    order-preserving, de-duplicated). Otherwise a disk is a ROOT when it is in
    the selected set and its backing ``parent`` is NOT in that set (parent is
    None, or the parent lives outside the selection so it will not move). Each
    root's full subtree is walked later, so the whole backing chain migrates
    consistently.
    """
    ids = {s["id"] for s in storages}
    if tree_ids:
        seen = set()
        out = []
        for t in tree_ids:
            if t in ids and t not in seen:
                seen.add(t)
                out.append(t)
        return out
    members = _selection_members(storages, kind, src_pool_id, category_id, path_prefix)
    return [
        s["id"]
        for s in storages
        if s["id"] in members
        and (s.get("parent") is None or s.get("parent") not in members)
    ]


# --------------------------------------------------------------------------- #
# Cross-mode anti-overlap (pure) — two composed reservation forms
#
# disk-level: the resolved storage-id closure (roots + subtrees). Precise, and
#   the concrete cross-mode signal (a pool job and a path/category job touching
#   the same disk resolve to intersecting id sets).
# descriptor-level: a content-INDEPENDENT (pool[, path]) claim, so a recurring
#   "drain pool X" job keeps reserving X for its whole non-terminal life even
#   between occurrences when X is empty and its closure/ledger is momentarily
#   empty (which disk-level would miss).
# --------------------------------------------------------------------------- #
def resolved_ids_from_rows(rows, children_of, selection):
    """The set of storage ids a selection would TOUCH: every root (via
    :func:`compute_roots`) plus its full subtree closure (via ``children_of``,
    mirroring the planner, which walks children even outside the selected set).
    Pure — ``rows`` are light dicts and ``children_of(id) -> iterable[id]``."""
    roots = compute_roots(
        rows,
        kind=selection.get("kind", "pool"),
        src_pool_id=selection.get("src_pool_id"),
        category_id=selection.get("category_id"),
        path_prefix=selection.get("path_prefix"),
        tree_ids=selection.get("tree_ids") or [],
    )
    ids = set()
    for root in roots:
        for nid in walk_tree_topo(root, children_of):
            ids.add(nid)
    return ids


def scopes_overlap(a, b):
    """True when two resolved disk-id sets intersect."""
    return bool(set(a) & set(b))


def descriptor_claims(kind, src_pool_id=None, path_prefix=None, category_pools=None):
    """Reduce a selection to a content-independent reservation descriptor: a set
    of ``(pool_id, path_prefix|None)`` claims. ``prefix None`` == the whole pool.

    * pool     -> ``{(src_pool_id, None)}`` (whole source pool)
    * path     -> ``{(src_pool_id, path_prefix)}`` (a path subtree within a pool;
                  ``src_pool_id`` may be ``None`` if the pool could not be resolved)
    * category -> ``{(p, None) for p in category_pools}`` (every pool statically
                  ASSIGNED to the category — resolves without touching disks, which
                  is what lets an empty category still reserve its pools)
    """
    if kind == "pool":
        return {(src_pool_id, None)} if src_pool_id else set()
    if kind == "path":
        return {(src_pool_id, path_prefix or "")}
    if kind == "category":
        return {(p, None) for p in (category_pools or [])}
    return set()


def _claim_overlap(a, b):
    """Two ``(pool, prefix)`` claims overlap when they name the same pool (an
    unresolved ``None`` pool is a wildcard — over-reject) AND their path scopes
    intersect: a whole-pool claim (``prefix None``) covers any prefix, and two
    prefixes intersect when one contains the other."""
    pa, prefa = a
    pb, prefb = b
    if pa is not None and pb is not None and pa != pb:
        return False
    if prefa is None or prefb is None:
        return True
    return prefa.startswith(prefb) or prefb.startswith(prefa)


def descriptors_overlap(claims_a, claims_b):
    """True when any claim of A overlaps any claim of B (cross-mode)."""
    return any(_claim_overlap(a, b) for a in claims_a for b in claims_b)


def scope_conflict(new_ids, new_claims, new_recurring, existing_jobs):
    """The composed overlap decision. Returns the id of the first active job the
    new selection conflicts with, or ``None``.

    ``existing_jobs`` is a list of ``{id, recurring, reserved_ids, claims}``. The
    descriptor-level check runs whenever a RECURRING reservation is in play on
    either side (that is the case where a scope may be empty yet still reserved);
    the disk-level check always runs. Prefers over-rejecting.
    """
    for j in existing_jobs:
        if (new_recurring or j.get("recurring")) and descriptors_overlap(
            new_claims, j.get("claims") or set()
        ):
            return j["id"]
        if scopes_overlap(new_ids, j.get("reserved_ids") or set()):
            return j["id"]
    return None


def _enumerate_storages(statuses=("ready",)):
    """Light storage rows (id/parent/directory_path/user_id) for selection.

    Read via the ``status`` index so a pool/category/path plan never full-scans
    a ``deleted`` graveyard. The pool id + category are resolved lazily (cached)
    by the caller because they need extra lookups.
    """
    from isardvdi_common.models.storage import Storage

    with Storage._rdb_context():
        return list(
            r.table("storage")
            .get_all(*statuses, index="status")
            .pluck("id", "parent", "directory_path", "user_id")
            .run(Storage._rdb_connection)
        )


def _attach_pool_and_category(rows):
    """Resolve ``pool_id`` (by directory_path) and ``category`` (by user) for
    each light row, caching both lookups."""
    from isardvdi_common.models.storage_pool import StoragePool
    from isardvdi_common.models.user import User

    pool_cache = {}
    cat_cache = {}
    for s in rows:
        d = s.get("directory_path") or ""
        if d not in pool_cache:
            pools = StoragePool.get_by_path(d)
            pool_cache[d] = pools[0].id if pools else None
        s["pool_id"] = pool_cache[d]
        uid = s.get("user_id")
        if uid not in cat_cache:
            cat_cache[uid] = User(uid).category if uid and User.exists(uid) else None
        s["category"] = cat_cache[uid]
    return rows


def roots_for_selection(selection):
    """Live: resolve a ``MigrationSelection``-shaped dict to root storage ids."""
    tree_ids = selection.get("tree_ids") or []
    rows = _attach_pool_and_category(_enumerate_storages())
    return compute_roots(
        rows,
        kind=selection.get("kind", "pool"),
        src_pool_id=selection.get("src_pool_id"),
        category_id=selection.get("category_id"),
        path_prefix=selection.get("path_prefix"),
        tree_ids=tree_ids,
    )


def resolved_disk_ids(selection):
    """Live: the set of storage ids a selection would TOUCH (roots + subtree
    closure) — the disk-level reservation for the anti-overlap guard. Lighter
    than :func:`build_plan_for_roots` (no size probes) but mirrors its traversal:
    roots from the selection, subtrees via ``Storage.children`` (non-deleted, so a
    disk already in ``maintenance`` under a moving job is still seen)."""
    from isardvdi_common.models.storage import Storage

    roots = roots_for_selection(selection)
    cache = {}

    def st(sid):
        if sid not in cache:
            cache[sid] = Storage(sid)
        return cache[sid]

    def get_children(sid):
        return [c.id for c in st(sid).children]

    ids = set()
    for root in roots:
        for nid in walk_tree_topo(root, get_children):
            ids.add(nid)
    return ids


def pools_for_category(category_id):
    """Live: the ids of the storage pools statically ASSIGNED to a category
    (``StoragePool.categories`` config), for the category descriptor claim. Falls
    back to the default pool when no pool is explicitly assigned, since that is
    where the category's disks actually land."""
    from isardvdi_common.helpers.default_storage_pool import DEFAULT_STORAGE_POOL_ID
    from isardvdi_common.models.storage_pool import StoragePool

    assigned = [p.id for p in StoragePool.get_all() if p.has_category(category_id)]
    # No pool explicitly assigned -> the category's disks land in the default
    # pool, so reserve that (prefer over-reserving to missing a real overlap).
    return assigned or [DEFAULT_STORAGE_POOL_ID]


def pool_plan_summary(pool_id, *, size_fn=None):
    """Pool-scoped aggregation for the admin overview: one entry per root tree
    with its derivative-template / desktop / byte counts, plus job totals.

    The live ``%-moved`` overlay is joined from a running migration's ledger
    (``StorageMigrationItem.state_counts``) by the status endpoint; this returns
    the static plan shape (what WOULD move).
    """
    from isardvdi_common.models.storage_pool import StoragePool

    pool = StoragePool(pool_id)
    root_ids = roots_for_selection({"kind": "pool", "src_pool_id": pool_id})
    # dst pool is irrelevant to the COUNTS; reuse the same pool so path_in_pool
    # resolves without forcing the admin to pick a destination just to preview.
    items, totals = build_plan_for_roots("__preview__", root_ids, pool, size_fn=size_fn)
    by_tree = {}
    for it in items:
        by_tree.setdefault(it["tree_id"], []).append(it)
    trees = []
    for root_id in root_ids:
        s = summarize_plan(by_tree.get(root_id, []))
        trees.append(
            {
                "tree_id": root_id,
                "root_storage_id": root_id,
                "derivative_templates": s["derivative_templates"],
                "desktops": s["desktops"],
                "media": s["media"],
                "items_total": s["items_total"],
                "bytes_total": s["bytes_total"],
            }
        )
    return {"pool_id": pool_id, "trees": trees, "totals": totals}


# --------------------------------------------------------------------------- #
# DB-driven layer (live)
# --------------------------------------------------------------------------- #
def build_plan_for_roots(
    migration_id, root_ids, dst_pool, *, size_fn=None, item_kinds=None, order=None
):
    """Build pending ``storage_migration_item`` dicts for every tree rooted at
    ``root_ids``, migrating into ``dst_pool`` (a ``StoragePool``).

    ``size_fn(src_path) -> int|None`` optionally supplies a fresh size (e.g.
    :func:`probe_actual_size` run on the storage worker); when it returns
    ``None`` (or is not given) the DB's ``qemu-img-info.actual-size`` is used.

    ``item_kinds`` restricts WHICH disk kinds move (``desktop`` / ``template`` /
    ``media``); empty or ``None`` moves everything, which is the historical
    behaviour. The subtree is still walked in full — the backing chain has to be
    understood whether or not every link of it travels — but a disk of an
    unselected kind stays put and gets no ledger row.

    ``order`` (``oldest_first`` / ``newest_first``) stamps each item with its
    tree's usage key so the runner can start trees least-used-first or the other
    way round. The key is computed HERE and frozen into the ledger on purpose:
    recomputing it at run time would let a desktop somebody starts between
    planning and execution silently reorder the job, and under a byte budget
    that means moving something other than what the admin approved.

    Returns ``(items, totals)``.
    """
    from isardvdi_common.lib.storage.storage import StorageProcessed
    from isardvdi_common.models.storage import Storage

    cache = {}
    #: usage directory resolved ONCE per storage id. ``get_usage_path`` draws a
    #: weighted-random path on every call, so a multi-path destination pool would
    #: otherwise land dst_path, dst_dir and the child's parent_dst_path in three
    #: different directories (saga-0). Resolve once, derive everything from it.
    dst_dir_cache = {}

    def st(sid):
        if sid not in cache:
            cache[sid] = Storage(sid)
        return cache[sid]

    def get_children(sid):
        return [c.id for c in st(sid).children]

    #: The disks this plan MOVES. A disk outside this set stays put, and its
    #: destination must never be resolved: its pool may serve no such path.
    tree_orders = {rid: walk_tree_topo(rid, get_children) for rid in root_ids}
    walked = {nid for topo in tree_orders.values() for nid in topo}
    selected_kinds = set(item_kinds or ())

    kind_cache = {}

    def kind_of(sid):
        if sid not in kind_cache:
            s = st(sid)
            kind_cache[sid] = classify_kind(
                len(s.children) > 0, getattr(s, "perms", None)
            )
        return kind_cache[sid]

    def moves(sid):
        return not selected_kinds or kind_of(sid) in selected_kinds

    moving = {nid for nid in walked if moves(nid)}

    def parent_within(sid):
        """The disk's parent when it is part of THIS plan's walk, else None."""
        parent_id = st(sid).parent
        return parent_id if parent_id in walked else None

    # Refuse rather than strand: moving a disk while leaving a derivative behind
    # breaks that derivative's backing chain.
    for topo in tree_orders.values():
        stranded = stranded_by_selection(topo, parent_within, moves)
        if stranded:
            parent_id, child_id = stranded[0]
            from isardvdi_common.helpers import error_factory

            raise error_factory.Error(
                "bad_request",
                f"Storage {parent_id} would move while its derivative "
                f"{child_id} ({kind_of(child_id)}) stays behind, which would "
                f"break the derivative's backing chain. Add '{kind_of(child_id)}'"
                " to the selected item kinds, or leave the parent out of the "
                "selection.",
                description_code="storage_migration_would_strand_derivative",
            )

    def dst_dir_of(s):
        if s.id not in dst_dir_cache:
            try:
                dst_dir_cache[s.id] = s.get_storage_pool_path(dst_pool)
            except Exception as exc:
                # A category-nested (non-default) pool needs the owner's
                # category, and get_storage_pool_path deliberately raises rather
                # than write a "<mountpoint>/None/..." path.
                raise _Unplaceable(
                    s.id,
                    f"{exc}. Give the disk a resolvable owner category or "
                    "migrate into the default pool.",
                ) from exc
            if dst_dir_cache[s.id] is None:
                # Left to travel, this None reaches the item as dst_path and
                # task.move dies inside os.path.isfile(None) with a TypeError.
                raise _Unplaceable(
                    s.id,
                    f"its directory {getattr(s, 'directory_path', '?')} does not "
                    "match any usage path of its current pool, so the "
                    "destination directory is unknown",
                )
        return dst_dir_cache[s.id]

    def dst_path_of(s):
        return f"{dst_dir_of(s)}/{s.id}.{s.type}"

    def node_info(sid):
        s = st(sid)
        src_path = s.path
        size_bytes = None
        if size_fn is not None:
            size_bytes = size_fn(src_path)
        if size_bytes is None:
            size_bytes = StorageProcessed.get_storage_actual_size(sid)
        info = {
            "kind": kind_of(sid),
            "src_path": src_path,
            "dst_path": dst_path_of(s),
            "dst_dir": dst_dir_of(s),
            "size_bytes": size_bytes or 0,
        }
        parent_id = s.parent
        # Storage.delete leaves the parent uuid on its children, so a live estate
        # holds rows whose parent row is gone. Such a disk has no reachable
        # backing parent: plan it as a root rather than raising not_found and
        # taking every other tree in the migration down with it.
        if parent_id and Storage.exists(parent_id):
            info["parent_storage_id"] = parent_id
            if parent_id in moving:
                p = st(parent_id)
                # Reuse the parent's single resolved directory (cached by id) so
                # the child rebases onto exactly where the parent's file landed.
                info["parent_dst_path"] = dst_path_of(p)
                info["parent_dst_dir"] = dst_dir_of(p)
            # else: the parent stays put, so an unset rebase target is correct --
            # that is what the runner reads as "no rebase".
        return info

    items = []
    not_moving = Counter()
    excluded = []
    excluded_nodes = set()
    for root_id in root_ids:
        topo = tree_orders[root_id]
        tree_items = []
        try:
            for sub_root, sub_order in split_moving_subtrees(
                topo, parent_within, moves
            ):
                tree_items.extend(
                    build_tree_items(
                        migration_id,
                        sub_root,
                        get_children,
                        node_info,
                        order=sub_order,
                    )
                )
        except _Unplaceable as unplaceable:
            # The whole tree, not the disk: dropping one disk would leave its
            # derivatives rebasing onto a path nothing resolved. One malformed
            # row used to abort the entire migration.
            excluded.append(
                {
                    "root_id": root_id,
                    "storage_id": unplaceable.storage_id,
                    "reason": unplaceable.reason,
                    "disks": len(topo),
                }
            )
            excluded_nodes.update(topo)
            continue
        items.extend(tree_items)

    walked -= excluded_nodes
    # counted over the walked SET, not per tree: two explicit tree_ids can
    # overlap, and a disk that stays is one disk however many walks reach it
    for nid in walked:
        if not moves(nid):
            not_moving[kind_of(nid)] += 1

    if order in ("oldest_first", "newest_first"):
        _stamp_tree_order_keys(items, walked, st)
    return items, summarize_plan(
        items, not_moving=not_moving, order=order, excluded=excluded
    )


def _stamp_tree_order_keys(items, walked, st):
    """Write each item's ``tree_order_key`` — its tree's usage key.

    Only called when an order was asked for, so the default path pays nothing:
    the usage dates need a second query, and a plan over a whole pool is already
    thousands of disks.
    """
    from isardvdi_common.models.domain import Domain

    # children WITHIN the walk, from the Storage objects the plan already built
    # (they are cached by id, so this costs no extra query)
    children = {}
    for nid in walked:
        parent_id = st(nid).parent
        if parent_id in walked:
            children.setdefault(parent_id, []).append(nid)

    def descendants_of(sid):
        out = []
        stack = list(children.get(sid, ()))
        while stack:
            nid = stack.pop()
            out.append(nid)
            stack.extend(children.get(nid, ()))
        return out

    accessed = Domain.accessed_by_storage(list(walked))
    by_tree = {}
    for it in items:
        by_tree.setdefault(it["tree_id"], []).append(it["storage_id"])
    keys = {
        tree_id: tree_order_key(movers, descendants_of, accessed.get)
        for tree_id, movers in by_tree.items()
    }
    for it in items:
        it["tree_order_key"] = keys[it["tree_id"]]
