#
#   Copyright © 2026 IsardVDI
#
# SPDX-License-Identifier: AGPL-3.0-or-later

"""N physically identical GPU cards must each keep their own ``gpus`` row.

Two (or more) physically identical cards resolve to the SAME model token (by
design, so they share one ``reservables_vgpus`` pool). ``ensure_gpu_cards`` must
still persist ONE ``gpus`` row per physical GPU (card_id ``auto-<hyper>-<pci>``).

Regression for the inventory collapse: on a re-registration, ``remove_hyper``
nulls ``physical_device`` on every ``auto-`` card of the hypervisor; the per-GPU
loop then fell into the "unassigned card with matching brand/model" branch and
stole another slot's just-nulled row instead of re-binding its own / creating a
fresh one. Processing the cards in discovery order (first card first) made the
first card's GPUs grab the second card's nulled rows, which the second card then
reclaimed via its own ``card_id`` -- leaving one whole card with no row, and
therefore no reservable and unbookable. Seen in the field with two identical
NVIDIA A16 cards (8 GPUs) that showed only 4 in the inventory.
"""

from unittest.mock import MagicMock

import pytest

HYPER = "hypX"
BDFS_2CARDS = ("45", "46", "47", "48", "c5", "c6", "c7", "c8")
BDFS_3CARDS = (
    "45",
    "46",
    "47",
    "48",
    "55",
    "56",
    "57",
    "58",
    "65",
    "66",
    "67",
    "68",
)


def _gpu(bdf, uuid):
    """A discovered-GPU dict as it reaches ``ensure_gpu_cards`` (resolve done)."""
    return {
        "pci_bus_id": f"0000:{bdf}:00.0",
        "gpu_uuid": uuid,
        "memory_total_mb": 14 * 1024,
        "name": "NVIDIA A16",
        "vgpu_profiles": [],
        "companion_pci_bdfs": [],
        "_resolved_model": "A16",  # identical cards collapse to one token
    }


def _card_id(bdf):
    return f"auto-{HYPER}-pci_0000_{bdf}_00_0"


def _vgpu_id(bdf):
    return f"{HYPER}-pci_0000_{bdf}_00_0"


# --- A deliberately small in-memory stand-in for the subset of the ReQL
# surface ``ensure_gpu_cards`` touches (dict-equality filter + get/insert/
# update/delete/pluck). Faithful to row state so we can assert row counts. ---


class _Res:
    def __init__(self, value):
        self._value = value

    def run(self, conn=None):
        return self._value


class _Query:
    def __init__(self, docs):
        self._docs = docs

    def pluck(self, *fields):
        return _Query([{k: d[k] for k in fields if k in d} for d in self._docs])

    def limit(self, n):
        return _Query(self._docs[:n])

    def run(self, conn=None):
        return [dict(d) for d in self._docs]


class _DocRef:
    def __init__(self, store, doc_id):
        self._store = store
        self._id = doc_id

    def run(self, conn=None):
        doc = self._store.get(self._id)
        return dict(doc) if doc is not None else None

    def pluck(self, *fields):
        doc = self._store.get(self._id) or {}
        return _Res({k: doc.get(k) for k in fields})

    def update(self, fields):
        if self._id in self._store:
            self._store[self._id].update(fields)
        return _Res({"replaced": 1})

    def delete(self):
        self._store.pop(self._id, None)
        return _Res({"deleted": 1})


class _Table:
    def __init__(self, store):
        self._store = store

    def get(self, doc_id):
        return _DocRef(self._store, doc_id)

    def insert(self, doc, conflict=None):
        self._store[doc["id"]] = dict(doc)
        return _Res({"inserted": 1})

    def filter(self, pred):
        if callable(pred):
            raise NotImplementedError(
                "ensure_gpu_cards only uses dict-equality filters"
            )
        docs = [
            d
            for d in self._store.values()
            if all(d.get(k) == v for k, v in pred.items())
        ]
        return _Query(docs)

    def get_all(self, *args, **kwargs):
        return _Query([])


class _R:
    def __init__(self, tables):
        self._tables = tables

    def table(self, name):
        return _Table(self._tables.setdefault(name, {}))


@pytest.fixture
def fake_db(monkeypatch):
    from isardvdi_common.lib.hypervisors import hypervisors as mod

    tables = {
        "gpus": {},
        "gpu_profiles": {},
        "hypervisors": {
            HYPER: {"id": HYPER, "hostname": HYPER, "pci_devices": {}},
        },
        "resource_planner": {},
    }
    monkeypatch.setattr(mod, "r", _R(tables))

    class _Ctx:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    monkeypatch.setattr(
        mod.HypervisorsProcessed, "_rdb_context", classmethod(lambda cls: _Ctx())
    )
    monkeypatch.setattr(
        type(mod.HypervisorsProcessed),
        "_rdb_connection",
        property(lambda self: MagicMock(name="conn")),
    )
    # Capacity bookkeeping + metadata heal are not under test.
    monkeypatch.setattr(
        mod.HypervisorsProcessed,
        "_recompute_total_units",
        classmethod(lambda cls, *a, **k: None),
    )
    monkeypatch.setattr(mod, "gpu_card_metadata_resync", lambda existing, gpu: {})

    return mod, tables["gpus"]


def _register(mod, bdfs):
    mod.HypervisorsProcessed.ensure_gpu_cards(HYPER, [_gpu(b, "U" + b) for b in bdfs])


def test_two_identical_cards_fresh_registration(fake_db):
    mod, gpus = fake_db
    _register(mod, BDFS_2CARDS)
    assert len(gpus) == 8
    for bdf in BDFS_2CARDS:
        assert gpus[_card_id(bdf)]["physical_device"] == _vgpu_id(bdf)


def _seed_detached(gpus, bdfs):
    """Rows for the given cards exist but are detached (physical_device=None),
    as ``remove_hyper`` leaves them when the hypervisor re-registers."""
    for bdf in bdfs:
        gpus[_card_id(bdf)] = {
            "id": _card_id(bdf),
            "brand": "NVIDIA",
            "model": "A16",
            "physical_device": None,
            "profiles_enabled": [],
        }


def test_identical_card_not_stolen_when_sibling_rows_detached(fake_db):
    """The field state: the second card (c5-c8) has rows but detached; the
    first card (45-48) has none. Re-discovery (first card first) must create
    the first card's own rows, not steal the second card's detached ones."""
    mod, gpus = fake_db
    _seed_detached(gpus, ("c5", "c6", "c7", "c8"))
    _register(mod, BDFS_2CARDS)  # gpu_apply order: card 1 before card 2
    assert len(gpus) == 8, f"card 1 stole card 2's rows; got {sorted(gpus)}"
    for bdf in BDFS_2CARDS:
        assert gpus[_card_id(bdf)]["physical_device"] == _vgpu_id(bdf)


def test_three_identical_cards_no_collapse(fake_db):
    """Two of three identical cards already have (detached) rows; discovery of
    all twelve GPUs must end with twelve distinct rows."""
    mod, gpus = fake_db
    _seed_detached(gpus, BDFS_3CARDS[4:])  # cards 2+3 present/detached, card 1 absent
    _register(mod, BDFS_3CARDS)
    assert len(gpus) == 12, f"collapsed to {sorted(gpus)}"
    for bdf in BDFS_3CARDS:
        assert gpus[_card_id(bdf)]["physical_device"] == _vgpu_id(bdf)


def test_manual_unassigned_card_is_still_adopted(fake_db):
    """A hand-created (non ``auto-``) card with model+no physical_device is
    still adopted by discovery — the behaviour the model match was there for."""
    mod, gpus = fake_db
    gpus["manual-a16"] = {
        "id": "manual-a16",
        "brand": "NVIDIA",
        "model": "A16",
        "physical_device": None,
        "profiles_enabled": ["NVIDIA-A16-2Q"],
    }
    _register(mod, ("45",))
    # The physical GPU binds to the manual card; no stray auto- row created.
    assert gpus["manual-a16"]["physical_device"] == _vgpu_id("45")
    assert _card_id("45") not in gpus
    assert len(gpus) == 1
