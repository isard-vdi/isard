#!/usr/bin/env python
# coding=utf-8
# Copyright 2017 the Isard-vdi project authors:
#      Josep Maria Viñolas Auquer
#      Alberto Larraz Dalmases
# License: AGPLv3

"""Per-category (multi-tenant) visibility/capacity helpers for GPU reservables.

Phase 2 of GPU category-delegation. Ownership is anchored on the physical card
(``gpus.category``, set in Phase 1); capacity and visibility are then computed
**on read** by filtering the per-card ``resource_planner`` plans and the
reservable list through these helpers -- the global ``reservables_vgpus`` rows
are left untouched (one row per profile still spans every enabling card).

Every card -> category decision funnels through :func:`gpu_owner_category`, the
single hook a future per-``(card, profile)`` slice delegation would swap for a
join-table lookup, so the read-path callers never change.
"""

from rethinkdb import RethinkDB

from api import app

from ..flask_rethink import RDB

r = RethinkDB()
db = RDB(app)
db.init_app(app)


def gpu_owner_category(card, profile=None):
    """Category that owns a physical GPU card, or ``None`` (undelegated/global).

    ``card`` may be a card id (str) or an already-fetched ``gpus`` row (dict).
    The ``profile`` argument is accepted but ignored today (whole-card
    delegation); per-slice delegation later resolves a ``(card, profile)`` ->
    category map HERE only, leaving every caller unchanged.
    """
    if isinstance(card, dict):
        return card.get("category")
    with app.app_context():
        row = r.table("gpus").get(card).run(db.conn)
    return (row or {}).get("category")


def category_uses_global_pool(category_id):
    """Whether a category also draws from the shared global (``category=None``)
    GPU pool, in addition to its own delegated cards.

    Per-category flag ``categories.gpu_use_global_pool``; defaults to ``True``
    (own + global) when unset or the category is missing, so existing installs
    keep seeing the shared pool exactly as before.
    """
    if not category_id:
        return True
    with app.app_context():
        category = r.table("categories").get(category_id).run(db.conn)
    if not category:
        return True
    value = category.get("gpu_use_global_pool")
    return True if value is None else bool(value)


def _card_visible(owner_category, requester_category, use_global):
    """Pure visibility predicate (no DB) — is a card owned by ``owner_category``
    visible to a requester in ``requester_category``?

    A card delegated to the requester's own category is always visible; an
    undelegated (``None``) card is visible only when the requester's category
    draws from the shared global pool; another category's card is hidden.
    Kept dependency-free so the rule is unit-testable in isolation.
    """
    return owner_category == requester_category or (
        use_global and owner_category is None
    )


def visible_gpu_card_ids(payload):
    """Set of physical GPU card ids visible to the requester's category, or
    ``None`` when unrestricted (admin or no payload -> caller skips filtering).

    A card delegated to the requester's category is visible; an undelegated
    (``None``) card is visible only when the category uses the global pool;
    another category's card is hidden.
    """
    if not payload or payload.get("role_id") == "admin":
        return None
    category_id = payload.get("category_id")
    use_global = category_uses_global_pool(category_id)
    with app.app_context():
        cards = list(r.table("gpus").pluck("id", "category").run(db.conn))
    ids = set()
    for card in cards:
        if _card_visible(gpu_owner_category(card), category_id, use_global):
            ids.add(card["id"])
    return ids


def filter_gpu_plans_by_category(plans, payload):
    """Drop ``resource_planner`` plans whose backing GPU card is not visible to
    the requester's category (Phase 2 capacity scoping).

    Non-gpu plans pass through untouched; admin (or no payload) sees every plan.
    The visible-card set is resolved lazily and only once, so non-gpu callers
    pay nothing.
    """
    if not plans or not payload or payload.get("role_id") == "admin":
        return plans
    visible = "unset"
    filtered = []
    for plan in plans:
        if plan.get("item_type") != "gpus":
            filtered.append(plan)
            continue
        if visible == "unset":
            visible = visible_gpu_card_ids(payload)
            if visible is None:
                return plans
        if plan.get("item_id") in visible:
            filtered.append(plan)
    return filtered


def filter_reservables_by_category(reservables, payload, keep_ids=None):
    """Keep only reservables enabled on at least one GPU card visible to the
    requester's category (Phase 2 visibility).

    ``keep_ids`` (e.g. the reservables already attached to a desktop) are always
    kept so an existing desktop never loses its profile from the picker even if
    its card was later delegated elsewhere. Admin (or no payload) sees all.
    """
    if not reservables or not payload or payload.get("role_id") == "admin":
        return reservables
    visible_cards = visible_gpu_card_ids(payload)
    if visible_cards is None:
        return reservables
    keep_ids = set(keep_ids or [])
    with app.app_context():
        cards = list(r.table("gpus").pluck("id", "profiles_enabled").run(db.conn))
    visible_enabled = set()
    for card in cards:
        if card["id"] in visible_cards:
            for reservable_id in card.get("profiles_enabled", []):
                visible_enabled.add(reservable_id)
    return [
        res
        for res in reservables
        if res.get("id") in visible_enabled or res.get("id") in keep_ids
    ]
