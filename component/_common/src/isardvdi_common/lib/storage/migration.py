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


def build_tree_items(migration_id, root_id, get_children, node_info):
    """Build the ``storage_migration_item`` dicts (state ``pending``) for ONE
    tree, in topo order.

    ``node_info(node_id) -> dict`` supplies per-disk data: ``kind``,
    ``src_path``, ``dst_path``, ``dst_dir``, ``size_bytes`` and (for non-root
    nodes) ``parent_storage_id`` / ``parent_dst_path`` / ``parent_dst_dir``.

    The root (topo_index 0) never rebases — its backing points at a parent
    OUTSIDE the migrated tree, which does not move — so its rebase target is
    cleared here regardless of what ``node_info`` returns.
    """
    order = walk_tree_topo(root_id, get_children)
    items = []
    for idx, nid in enumerate(order):
        info = node_info(nid)
        is_root = idx == 0
        items.append(
            {
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


def summarize_plan(item_dicts):
    """Aggregate per-job totals from the built item dicts.

    Computed from the data (never incremented), matching the at-least-once
    ledger invariant. ``derivative_templates`` are template items that are not
    a tree root (``storage_id != tree_id``).
    """
    kinds = Counter(it.get("kind") for it in item_dicts)
    derivative_templates = sum(
        1
        for it in item_dicts
        if it.get("kind") == "template" and it["storage_id"] != it["tree_id"]
    )
    bytes_total = sum(int(it.get("size_bytes") or 0) for it in item_dicts)
    return {
        "trees": len({it["tree_id"] for it in item_dicts}),
        "derivative_templates": derivative_templates,
        "desktops": kinds.get("desktop", 0),
        "media": kinds.get("media", 0),
        "items_total": len(item_dicts),
        "bytes_total": bytes_total,
        "bytes_done": 0,
        "state_counts": {"pending": len(item_dicts)} if item_dicts else {},
    }


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
# DB-driven layer (live)
# --------------------------------------------------------------------------- #
def build_plan_for_roots(migration_id, root_ids, dst_pool, *, size_fn=None):
    """Build pending ``storage_migration_item`` dicts for every tree rooted at
    ``root_ids``, migrating into ``dst_pool`` (a ``StoragePool``).

    ``size_fn(src_path) -> int|None`` optionally supplies a fresh size (e.g.
    :func:`probe_actual_size` run on the storage worker); when it returns
    ``None`` (or is not given) the DB's ``qemu-img-info.actual-size`` is used.

    Returns ``(items, totals)``.
    """
    from isardvdi_common.lib.storage.storage import StorageProcessed
    from isardvdi_common.models.storage import Storage

    cache = {}

    def st(sid):
        if sid not in cache:
            cache[sid] = Storage(sid)
        return cache[sid]

    def get_children(sid):
        return [c.id for c in st(sid).children]

    def node_info(sid):
        s = st(sid)
        has_children = len(s.children) > 0
        src_path = s.path
        size_bytes = None
        if size_fn is not None:
            size_bytes = size_fn(src_path)
        if size_bytes is None:
            size_bytes = StorageProcessed.get_storage_actual_size(sid)
        info = {
            "kind": classify_kind(has_children, getattr(s, "perms", None)),
            "src_path": src_path,
            "dst_path": s.path_in_pool(dst_pool),
            "dst_dir": s.get_storage_pool_path(dst_pool),
            "size_bytes": size_bytes or 0,
        }
        parent_id = s.parent
        if parent_id:
            p = st(parent_id)
            info["parent_storage_id"] = parent_id
            info["parent_dst_path"] = p.path_in_pool(dst_pool)
            info["parent_dst_dir"] = p.get_storage_pool_path(dst_pool)
        return info

    items = []
    for root_id in root_ids:
        items.extend(build_tree_items(migration_id, root_id, get_children, node_info))
    return items, summarize_plan(items)
