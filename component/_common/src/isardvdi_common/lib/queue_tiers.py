"""Phase-1 queue-tier resolver (pure logic; one env read for the multitenancy switch).

Replaces the role-demoting ``Helpers.check_task_priority`` with an
**action-driven** tier model. The storage worker pool is partitioned so that a
*reserved* pool serves only ``interactive``/``standard`` and an *elastic* pool
serves ``bulk``/``background`` (+ interactive overflow) — see
``docker/storage/init.sh``. Latency isolation therefore comes from *which tier a
task lands on*, which is what this module decides.

Design: docs/design/queue-worker-dimensioning.md §3.

Tiers, most-urgent first:

* ``interactive`` — a single, user-is-waiting action (desktop create, a
  non-persistent start's volatile create). Sub-second target. Served
  by the always-on reserved pool. Prioritised *ahead* of ``resize``.
* ``standard``    — a single foreground op that is not click-and-wait (a disk
  ``resize``, a ``recreate``, an awaited media download). Seconds target.
* ``template``    — template-from-desktop whole-disk copies. Heavy, so never on
  the reserved/std pools, but kept on their OWN governed lane so a burst of
  quick ``bulk`` creates can never block a template and vice-versa.
* ``bulk``        — mass operations (deployment create, bulk create/recreate).
  Throughput, not latency. Marked by the *producer* (``priority="bulk"``). Bulk
  *deletes* are NOT bulk — they reclaim (see below).
* ``maintenance`` — long best-effort work (convert, sparsify, disconnect,
  ``virt_win_reg``, downloads, pool migration ``move``). Never on the reserved
  pool. (Formerly ``background``.)
* ``reclaim``     — physical space reclamation (``delete``, ``move_delete``,
  bulk delete, broom sweeps). The user already saw the item vanish (the DB row +
  view are removed synchronously); the bytes are freed whenever nothing more
  urgent is pending.
* ``background``  — the lowest tier: idle-only lifecycle metadata refreshes that
  NOBODY is blocked on — a post-stop ``qemu-img info`` size refresh, a batch
  status re-scan. Cheap reads that must never preempt real work; run in the
  troughs, hidden entirely under node pressure. The user still SEES the result
  (feedback is emitted regardless of tier) — only the *scheduling* is deferred.
  The tier a task lands on depends on the TRIGGER, not just the action: the same
  ``qemu_img_info_backing_chain`` is ``background`` as a standalone refresh,
  ``standard`` from an admin datatable click, and rides its parent's tier as an
  in-chain finalize the user is blocked on.

The ``template``/``bulk``/``maintenance``/``reclaim``/``background`` tiers are the
*governed* set — fair-scheduled on the elastic/template/bg-floor pools; the two
foreground tiers (``interactive``/``standard``) ride flat reserved/std lanes. Of
the governed set ``template``/``maintenance`` are *heavy* (PSI-deferred AND
max-heavy-capped); ``reclaim``/``background`` are PSI-deferred but not capped
(trivial deletes / metadata reads); ``bulk`` is neither.
"""

import os

# Most-urgent -> least-urgent. Order is relied upon by the worker subscription
# order in docker/storage/init.sh.
TIERS = (
    "interactive",
    "standard",
    "template",
    "bulk",
    "maintenance",
    "reclaim",
    "background",
)

# The governed tiers served only by the governed pools (elastic / template-lane /
# bg-floor) — never by the reserved(interactive) or std-lane pools. A governed
# action can be routed among these but can never be promoted onto a foreground
# lane. Which of these are PSI-deferred / max-heavy-capped is refined below
# (DEFERRABLE_TIERS / HEAVY_TIERS); ``bulk`` is governed but neither.
_GOVERNED_TIERS = frozenset(
    {"template", "bulk", "maintenance", "reclaim", "background"}
)

# The governed tiers that are PSI-**deferrable**: hidden from the dequeue order
# under node CPU/IO/memory pressure so urgent work proceeds. ``bulk`` is
# governed/fair but never deferred (quick throughput up to the worker count). All
# long-tail tiers defer, INCLUDING ``reclaim`` -- a mass-delete / broom storm can
# add real IO on discard-heavy backends, so it too yields under pressure -- and
# ``background`` (idle-only metadata refreshes), which by definition run only in
# the troughs.
DEFERRABLE_TIERS = frozenset({"template", "maintenance", "reclaim", "background"})

# The deferrable tiers that ALSO count against the global max-heavy *concurrency
# cap* (the P1 resource governor): genuine node-loaders -- a whole-disk
# ``template`` copy, and ``maintenance`` (``convert``/``sparsify`` disk churn, the
# ``virt_win_reg``/``sparsify`` libguestfs appliance VMs, whole-disk ``move``).
# ``reclaim`` is deferrable but NOT capped: ``delete`` (a plain unlink) and
# ``move_delete`` (a rename into ``deleted/``) are trivial-resource and must never
# consume a slot the heavy converts need. ``bulk`` is neither deferred nor capped.
HEAVY_TIERS = frozenset({"template", "maintenance"})

# Legacy high/default/low priority strings still flow in from older call sites
# and admin API params during rollout. ``default`` is action-dependent and is
# resolved separately (see normalize_tier). ``low`` maps to the maintenance lane
# (the renamed ``background``).
_LEGACY_MAP = {"high": "interactive", "low": "maintenance"}

# C1 single foreground: not sub-second, but the user is still in the loop. A disk
# ``resize`` sits here (not interactive) so a create/start always overtakes a
# resize on its own lane. ``virt_win_reg`` is NOT here -- it drives a libguestfs
# appliance VM (minutes; CPU/memory + a KVM slot), so it is floored to the heavy
# ``maintenance`` lane instead of blocking the foreground std lane.
_STANDARD_ACTIONS = frozenset({"resize"})

# Physical space reclamation: the user has already seen the item disappear, so
# these are the LOWEST priority and are HARD-floored to ``reclaim`` regardless of
# any requested tier — a bulk-delete marked ``bulk`` by the producer still
# reclaims, exactly like a single delete.
_RECLAIM_ACTIONS = frozenset({"delete", "move_delete"})

# Long best-effort maintenance: never latency-sensitive. HARD-floored to
# ``maintenance`` so they can never monopolise a reserved/std worker.
# ``virt_win_reg`` is here (not ``standard``): virt-win-reg drives a libguestfs
# appliance VM that mounts the disk (minutes; CPU/memory + a KVM slot), so it is
# heavy node-loading work, not a quick foreground op.
_MAINTENANCE_ACTIONS = frozenset({"sparsify", "convert", "disconnect", "virt_win_reg"})

# The whole-disk ``move`` (rsync/qemu-img, job_timeout up to 12h): pool migration
# AND template-from-desktop share this action. It must never touch a foreground
# lane, so it is floored INTO the governed set — default ``maintenance`` (pool
# migration), but the producer may route it to a specific governed tier: a
# template-from-desktop passes ``priority="template"`` to land on the dedicated
# template lane, a bulk migration ``priority="bulk"``. An interactive/standard
# request is dropped back to ``maintenance``.
_MOVE_ACTIONS = frozenset({"move"})

# Downloads default to maintenance but MAY be explicitly raised to standard when
# the user is blocked on them (awaited media). They are not hard-floored.
_DOWNLOAD_ACTIONS = frozenset({"download_url", "download_url_for_domain"})

# Phase-2 per-category fairness applies to the governed throughput tiers only;
# interactive/standard ride the flat reserved/standard lanes (a per-category
# segment there would just fragment the reserved lane).
_FAIR_TIERS = _GOVERNED_TIERS

# Sentinel category for a task with no resolvable owner category (deleted owner,
# system maintenance). It gets its own fair-scheduler lane instead of stranding
# on a queue no per-category worker discovers.
NULL_CATEGORY = "_nocat"


def resolve_category(owner_category):
    """The category segment a producer threads into a fair lane: the owner's
    category, or the NULL_CATEGORY sentinel for an ownerless/system task. Mirrors
    the inline resolution create_task does, for callers that need the retiered
    lane up front (e.g. a pre-flight shed check)."""
    return owner_category or NULL_CATEGORY


def _category_segment(category):
    """A category id sanitised for use as a single dotted queue segment: the
    null sentinel for a missing value, and never containing a ``.`` OR a ``:``
    (either would break the ``storage.<pool>.<category>.<tier>`` parse, and ``:``
    additionally collides with the cross-pool ``src:dst`` key syntax). Both are
    mapped to ``_`` — category ids are opaque uuids in practice, so the mapping
    is not expected to collide; a ``.`` and a ``:`` in the same position would,
    but neither occurs in a real category id. Review #18."""
    if not category or not isinstance(category, str):
        return NULL_CATEGORY
    return category.replace(".", "_").replace(":", "_")


def parse_storage_queue(name):
    """Split a storage queue name into ``(pool, category, tier)``.

    Handles both the flat ``storage.<pool>.<tier>`` shape (``category`` None) and
    the per-category ``storage.<pool>.<category>.<tier>`` shape. ``pool`` may be a
    cross-pool ``src:dst`` key (colon-joined, never dotted). Returns ``None`` for
    a non-storage or malformed name. The worker uses this for discovery and
    per-category counter keys.
    """
    if not isinstance(name, str) or not name.startswith("storage."):
        return None
    parts = name.split(".")
    if len(parts) == 3:  # storage.<pool>.<tier>
        return (parts[1], None, parts[2])
    if len(parts) == 4:  # storage.<pool>.<category>.<tier>
        return (parts[1], parts[2], parts[3])
    return None


def default_tier_for_action(action):
    """Return the default tier for a task *action* with no extra context.

    Unknown actions are treated as ``interactive`` (the safe foreground lane) so
    a newly-added action can never silently stall on a starved maintenance lane.
    """
    if action in _RECLAIM_ACTIONS:
        return "reclaim"
    if (
        action in _MAINTENANCE_ACTIONS
        or action in _MOVE_ACTIONS
        or action in _DOWNLOAD_ACTIONS
    ):
        return "maintenance"
    if action in _STANDARD_ACTIONS:
        return "standard"
    return "interactive"


def normalize_tier(value, action=None, role_id=None):
    """Normalise a requested tier/priority into one of :data:`TIERS`.

    * Accepts the six tier names verbatim.
    * Maps legacy ``high`` -> interactive, ``low`` -> maintenance, and
      ``default`` -> the action's default tier (interactive if no action).
    * **Never demotes by role** — a non-admin's interactive action stays
      interactive (the Phase-1 behavioural fix). ``role_id`` is accepted for
      call-site compatibility and future weighting but does not lower the tier.
    * **Hard-floors** reclaim actions (delete/move_delete) to ``reclaim`` and
      maintenance actions (convert/sparsify/disconnect) to ``maintenance``, and
      floors the whole-disk ``move`` into the governed set, so isolation holds
      regardless of what the caller requested.

    :raises ValueError: if ``value`` is neither a tier nor a legacy priority
        (only for non-floored actions — a floored action returns its lane for
        any ``value`` and never raises).
    """
    # Isolation guarantees first — floored actions ignore the requested value
    # and never raise on a free-form priority.
    #
    # Deletes are the lowest tier, ALWAYS: a bulk-delete the producer marked
    # ``bulk`` still reclaims, just like a single delete.
    if action in _RECLAIM_ACTIONS:
        return "reclaim"
    # Maintenance churn can never leave the maintenance lane.
    if action in _MAINTENANCE_ACTIONS:
        return "maintenance"
    # Whole-disk move: floored into the governed set. Honour an explicit governed
    # tier (template-from-desktop -> ``template``, bulk migration -> ``bulk``),
    # else default to ``maintenance``; a foreground request is floored away.
    if action in _MOVE_ACTIONS:
        # A move is a whole-disk copy that can run for hours; it must land on a
        # PSI-paced HEAVY tier, never on ``bulk`` (governed but non-heavy -> no
        # PSI defer, no max_heavy accounting). So honour an explicit heavy tier
        # but floor everything else (incl. ``bulk``) to maintenance.
        return value if value in HEAVY_TIERS else "maintenance"

    if value == "default":
        return default_tier_for_action(action)
    if value in _LEGACY_MAP:
        return _LEGACY_MAP[value]
    if value in TIERS:
        return value
    raise ValueError(
        f"Unknown queue tier/priority {value!r}; expected one of "
        f"{TIERS} or legacy high/default/low"
    )


def retier_queue(queue, action, category=None):
    """Rewrite the trailing tier segment of a ``storage.<pool>.<tier>`` queue.

    The last dotted segment of a storage queue name is its tier/priority; it is
    re-resolved through :func:`normalize_tier` using ``action``. The infra part
    of the key (pool id, or a cross-pool ``src:dst`` key) is preserved verbatim.

    When ``category`` is given AND the resolved tier is fair-scheduled
    (``bulk``/``background``), a per-category segment is inserted to produce
    ``storage.<pool>.<category>.<tier>`` so the elastic worker can schedule that
    category's throughput work fairly. ``category`` is None (the default) for
    every caller until per-category fairness is switched on, and for the
    interactive/standard tiers, which stay flat. A null/empty category routes to
    the :data:`NULL_CATEGORY` sentinel lane rather than a flat queue, so a
    deleted-owner task is still fair-scheduled and never stranded.

    Non-storage queues (``core``, ``notifier.*``), ``None`` and names without a
    dotted tier segment are returned untouched. A storage queue whose trailing
    segment is a free-form / unrecognised priority (e.g. an rsync route passing
    an arbitrary string) does NOT raise — it degrades to the action's default
    tier, a real queue a worker serves, so a bad priority can never 500 the
    caller or strand the task on a non-existent queue.
    """
    if not isinstance(queue, str) or not queue.startswith("storage."):
        return queue
    # Structure is ``storage.<pool>.<priority>`` where <pool> is a pool id or a
    # cross-pool ``src:dst`` key — NEVER dotted. So the priority is everything
    # after the second dot: split on the first two dots and take the remainder,
    # rather than rpartition(".") which (for a free-form priority containing a
    # dot, e.g. an rsync route passing "a.b") would leave a bogus middle segment
    # and produce an unserved / unparseable queue. A dotted priority is
    # unrecognised by normalize_tier and so degrades to the action's default tier
    # — a real queue a worker serves.
    parts = queue.split(".", 2)
    if len(parts) < 3:
        return queue  # no tier segment (e.g. "storage.pool") -> untouched
    head = f"{parts[0]}.{parts[1]}"
    prio = parts[2]
    try:
        tier = normalize_tier(prio, action=action)
    except ValueError:
        tier = default_tier_for_action(action)
    if category is not None and tier in _FAIR_TIERS:
        return f"{head}.{_category_segment(category)}.{tier}"
    return f"{head}.{tier}"


def retier_dependents(dependents, category=None):
    """Retier every dependent task's queue in a (possibly nested) dependents tree.

    ``create_task`` builds a chain of ``{"task", "queue", "dependents": [...]}``
    dicts; each level is rewritten through :func:`retier_queue` using that task's
    own ``action`` (and, when per-category fairness is on, the owning
    ``category`` — the same one flows to every level of the chain). The walk is
    **recursive** so a finalize step nested two or more levels deep (e.g.
    recreate / template-from-desktop chains) is tiered too rather than lingering
    on its raw ``.default`` queue. Mutates in place.
    """
    for dep in dependents or []:
        if not isinstance(dep, dict):
            continue
        if "queue" in dep:
            dep["queue"] = retier_queue(dep["queue"], dep.get("task"), category)
        nested = dep.get("dependents")
        if nested:
            retier_dependents(nested, category)
