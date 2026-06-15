"""Unit tests for the pure GPU multi-tenancy helpers.

``gpu_multitenancy`` can't be imported bare (``from api import app`` boots Flask
+ RethinkDB at import time), so — mirroring ``api_reservables_test.py`` — we
extract the self-contained functions via ``ast`` and exec them in isolation:

- ``_card_visible``: the single rule deciding whether a requester's category can
  see a given GPU card (own card always; undelegated/global card only when the
  category draws from the global pool; another category's card never).
- ``filter_gpu_plans_by_category``: the availability filter wired into
  ``booking_provisioning`` — its only DB dependency is ``visible_gpu_card_ids``,
  which we stub, so the per-plan logic (admin unfiltered, non-gpu plans pass
  through, gpu plans dropped by card) is testable in isolation.
"""

import ast
import os

_SRC = os.path.join(os.path.dirname(__file__), "../gpu_multitenancy.py")
_WANTED = {"_card_visible", "filter_gpu_plans_by_category"}


def _load():
    tree = ast.parse(open(_SRC).read())
    funcs = [
        n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name in _WANTED
    ]
    assert {f.name for f in funcs} == _WANTED
    ns = {}
    exec(compile(ast.Module(body=funcs, type_ignores=[]), _SRC, "exec"), ns)
    return ns


_H = _load()
_visible = _H["_card_visible"]


def _filter(plans, payload, visible):
    # Inject the only DB dependency (visible_gpu_card_ids) as a stub.
    _H["visible_gpu_card_ids"] = lambda _payload: visible
    return _H["filter_gpu_plans_by_category"](plans, payload)


_MGR = {"role_id": "manager", "category_id": "catA"}
_GPU = lambda card: {"item_type": "gpus", "item_id": card}
_USB = lambda usb: {"item_type": "usbs", "item_id": usb}


def test_own_category_card_is_visible_regardless_of_pool():
    assert _visible("catA", "catA", True) is True
    assert _visible("catA", "catA", False) is True


def test_other_category_card_is_hidden():
    assert _visible("catB", "catA", True) is False
    assert _visible("catB", "catA", False) is False


def test_global_card_visible_only_when_pool_enabled():
    assert _visible(None, "catA", True) is True
    assert _visible(None, "catA", False) is False


def test_global_requester_sees_global_card_when_pooled():
    # A requester whose own category is itself global/None still only matches
    # global cards through the pool flag.
    assert _visible(None, None, True) is True
    assert _visible(None, None, False) is True  # None == None (own match)


# --- filter_gpu_plans_by_category (the availability filter) ------------------


def test_admin_plans_unfiltered():
    plans = [_GPU("cardA"), _GPU("cardB")]
    out = _filter(plans, {"role_id": "admin", "category_id": "x"}, {"cardA"})
    assert out is plans  # identity: admin path returns the input untouched


def test_no_payload_unfiltered():
    plans = [_GPU("cardA")]
    assert _filter(plans, None, {"cardA"}) is plans


def test_gpu_plans_dropped_by_card():
    plans = [_GPU("cardA"), _GPU("cardB"), _GPU("cardC")]
    out = _filter(plans, _MGR, {"cardA", "cardC"})  # cardB not visible
    assert [p["item_id"] for p in out] == ["cardA", "cardC"]


def test_non_gpu_plans_pass_through_untouched():
    # A usbs plan is never category-filtered, even for a manager whose visible
    # GPU set excludes everything.
    plans = [_USB("usb1"), _GPU("cardA"), _USB("usb2"), _GPU("cardB")]
    out = _filter(plans, _MGR, {"cardA"})
    assert [p["item_id"] for p in out] == ["usb1", "cardA", "usb2"]


def test_visible_none_returns_all():
    # Defensive: if the visible set resolves to None (unrestricted), pass all.
    plans = [_GPU("cardA"), _GPU("cardB")]
    assert _filter(plans, _MGR, None) is plans
