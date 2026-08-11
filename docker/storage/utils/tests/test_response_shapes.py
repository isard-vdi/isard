"""The generated client hands back typed models; these scripts read dicts.

The mismatch is silent until it runs: iterating a list-response wrapper falls
back to the sequence protocol, asks for key 0 and raises ``KeyError(0)``, which
an operator sees as the bare ``0``. These tests pin the boundary against the
REAL generated models, so a future change of shape fails here instead of in
production. They skip where the client has not been generated -- it is built
during codegen, not carried in a source checkout.
"""

import importlib.machinery
import importlib.util
import os
from pathlib import Path

import pytest


def _load_move_disks():
    """The tool ships without a .py suffix, so it has to be loaded by path.

    Loading it also runs its start-up, which creates the runtime directories it
    logs into -- absolute paths that only exist inside the container and that
    only root may create. These tests want its pure helpers, so those creations
    are dropped for the duration of the load rather than requiring root.
    """
    path = Path(__file__).resolve().parents[1] / "move_disks"
    spec = importlib.util.spec_from_loader(
        "move_disks", importlib.machinery.SourceFileLoader("move_disks", str(path))
    )
    module = importlib.util.module_from_spec(spec)

    real_makedirs = os.makedirs

    def makedirs_unless_absolute(name, *args, **kwargs):
        if str(name).startswith("/"):
            return None
        return real_makedirs(name, *args, **kwargs)

    os.makedirs = makedirs_unless_absolute
    try:
        spec.loader.exec_module(module)
    finally:
        os.makedirs = real_makedirs
    return module


# Both the tool and these assertions need the generated client, and it is built
# during codegen rather than carried in a source checkout, so skip before the
# import that would fail.
pytest.importorskip(
    "isardvdi_apiv4_client.client",
    reason="the generated apiv4 client is produced by codegen",
)

move_disks = _load_move_disks()


def _model(name):
    module = pytest.importorskip(f"isardvdi_apiv4_client.models.{name}")
    for attribute in dir(module):
        if attribute.lower() == name.replace("_", ""):
            return getattr(module, attribute)
    pytest.skip(f"{name} is not in the generated client")


def test_the_pool_list_wrapper_is_not_iterable_as_a_list():
    """The defect itself: reading the wrapper as a list raises, and the message
    is a bare key, which is why it read as 'Error retrieving storage pools: 0'."""
    wrapper = _model("storage_pool_list_response").from_dict(
        {"storage_pools": [{"id": "p1", "name": "P1", "enabled": True}]}
    )

    with pytest.raises(KeyError) as raised:
        list(wrapper)
    # the key it asks for, whatever its type: the operator saw a bare "0"
    assert str(raised.value.args[0]) == "0"


def test_normalising_the_pool_list_wrapper_yields_usable_dicts():
    wrapper = _model("storage_pool_list_response").from_dict(
        {"storage_pools": [{"id": "p1", "name": "P1", "enabled": True}]}
    )

    pools = move_disks._as_dict(wrapper)["storage_pools"]

    assert [p["id"] for p in pools] == ["p1"]
    assert pools[0].get("enabled") is True, "callers use .get() on these"


def test_normalising_a_single_model_yields_a_plain_dict():
    task = _model("task_id_response").from_dict({"task_id": "t-1"})

    assert move_disks._as_dict(task)["task_id"] == "t-1"
