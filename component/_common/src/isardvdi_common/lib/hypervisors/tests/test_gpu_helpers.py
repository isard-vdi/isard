#
#   Copyright © 2026 IsardVDI
#
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Pin the three GPU-catalog helpers added to ``HypervisorsProcessed``.

``resolve_gpu_models`` / ``ensure_gpu_profiles`` / ``ensure_gpu_cards``
are the api-half of the cross-branch fix-set tracked by main
``6f7f8ea24`` (lock GPU card model to prevent catalog drift) and the
identity hardening from main ``7e88b182b`` (anchor GPU card identity to
``gpu_uuid``). The engine half landed in 2026-05-03; this skill-set is
the apiv4 / ``_common`` counterpart that auto-populates the catalog
from hypervisor discovery.

The tests use a tiny in-memory rdb store so the chained ``r.table(X)
.get(id).run(conn)`` / ``.filter(...).limit(1).run(conn)`` /
``.insert(row).run(conn)`` flows in the helpers exercise without
hitting a real database.
"""

from unittest.mock import MagicMock

import pytest

# ── Tiny in-memory rdb store ────────────────────────────────────────────


class _Table:
    """Pretend RethinkDB table. Backs a dict keyed by row id."""

    def __init__(self, name: str, rows: dict[str, dict]):
        self.name = name
        self.rows = rows
        self.insert_log: list[dict] = []
        self.update_log: list[tuple[str, dict]] = []
        self.delete_log: list[str] = []
        self._pending_filter = None

    def get(self, row_id: str):
        return _Row(self, row_id)

    def filter(self, criteria):
        # Result of `.filter(...)` is itself terminal-able with .limit().run()
        # OR with .pluck("id").run(). The two helpers cover both shapes.
        return _Filter(self, criteria)

    def get_all(self, key, index):
        # `.get_all(key, index=...).update(fields).run(conn)` — used by the
        # slot-move path to repoint resource_planner rows to the new card id.
        return _GetAll(self, key, index)

    def insert(self, row, conflict=None):
        return _Insert(self, row, conflict=conflict)


class _Row:
    def __init__(self, table: _Table, row_id: str):
        self.table = table
        self.row_id = row_id

    def run(self, conn):
        return self.table.rows.get(self.row_id)

    def update(self, fields):
        return _Update(self.table, self.row_id, fields)

    def pluck(self, *fields):
        # `.get(id).pluck(...).run(conn)` — ensure_gpu_cards reads the
        # hypervisor row's hostname/pci_devices for the passthrough label.
        outer = self

        class _RowPluck:
            def run(self, conn):
                row = outer.table.rows.get(outer.row_id)
                if row is None:
                    return None
                return {f: row.get(f) for f in fields}

        return _RowPluck()

    def delete(self):
        return _Delete(self.table, self.row_id)


class _GetAll:
    def __init__(self, table: _Table, key, index):
        self.table = table
        self.key = key
        self.index = index

    def update(self, fields):
        outer = self

        class _RunSet:
            def run(self, conn):
                replaced = 0
                for row in outer.table.rows.values():
                    if row.get(outer.index) == outer.key:
                        row.update(fields)
                        replaced += 1
                outer.table.update_log.append((f"{outer.index}={outer.key}", fields))
                return {"replaced": replaced}

        return _RunSet()


class _Filter:
    def __init__(self, table: _Table, criteria):
        self.table = table
        self.criteria = criteria

    def _matches(self, row):
        return all(row.get(k) == v for k, v in self.criteria.items())

    def limit(self, n):
        return _Limit(self.table, self.criteria, n)

    def pluck(self, *fields):
        return _Pluck(self.table, self.criteria, fields)


class _Limit:
    def __init__(self, table: _Table, criteria, n):
        self.table = table
        self.criteria = criteria
        self.n = n

    def run(self, conn):
        matched = [
            row
            for row in self.table.rows.values()
            if all(row.get(k) == v for k, v in self.criteria.items())
        ]
        return matched[: self.n]


class _Pluck:
    def __init__(self, table: _Table, criteria, fields):
        self.table = table
        self.criteria = criteria
        self.fields = fields

    def run(self, conn):
        out = []
        for row in self.table.rows.values():
            if all(row.get(k) == v for k, v in self.criteria.items()):
                out.append({f: row.get(f) for f in self.fields})
        return out


class _Insert:
    def __init__(self, table: _Table, row, conflict=None):
        self.table = table
        self.row = row
        self.conflict = conflict

    def run(self, conn):
        self.table.insert_log.append(self.row)
        # Mirror RethinkDB's conflict="update": shallow merge by id.
        row_id = self.row["id"]
        if self.conflict == "update" and row_id in self.table.rows:
            merged = dict(self.table.rows[row_id])
            merged.update(self.row)
            self.table.rows[row_id] = merged
        else:
            self.table.rows[row_id] = dict(self.row)
        return {"inserted": 1, "replaced": 0}


class _Update:
    def __init__(self, table: _Table, row_id: str, fields: dict):
        self.table = table
        self.row_id = row_id
        self.fields = fields

    def run(self, conn):
        self.table.update_log.append((self.row_id, self.fields))
        if self.row_id in self.table.rows:
            self.table.rows[self.row_id].update(self.fields)
        return {"replaced": 1}


class _Delete:
    def __init__(self, table: _Table, row_id: str):
        self.table = table
        self.row_id = row_id

    def run(self, conn):
        self.table.delete_log.append(self.row_id)
        self.table.rows.pop(self.row_id, None)
        return {"deleted": 1}


@pytest.fixture
def stub_rdb(monkeypatch):
    """Wires a tiny in-memory rdb store onto ``HypervisorsProcessed``."""
    from isardvdi_common.lib.hypervisors import hypervisors as mod

    class _Ctx:
        def __enter__(self):
            return self

        def __exit__(self, *_a):
            return False

    monkeypatch.setattr(
        mod.HypervisorsProcessed, "_rdb_context", classmethod(lambda cls: _Ctx())
    )
    monkeypatch.setattr(
        type(mod.HypervisorsProcessed),
        "_rdb_connection",
        property(lambda self: MagicMock(name="conn")),
    )

    tables = {
        "gpus": _Table("gpus", {}),
        "gpu_profiles": _Table("gpu_profiles", {}),
        "resource_planner": _Table("resource_planner", {}),
        # ensure_gpu_cards reads hostname+pci_devices for the auto
        # passthrough_variant label (upstream !4544); an absent row is fine.
        "hypervisors": _Table("hypervisors", {}),
    }
    monkeypatch.setattr(mod.r, "table", lambda name: tables[name])
    return {"tables": tables, "Processed": mod.HypervisorsProcessed}


# ── Fixture data ────────────────────────────────────────────────────────


def _gpu(
    pci="00000000:3b:00.0",
    name="NVIDIA A100",
    uuid="GPU-aaa",
    memory_mb=40960,
    vgpu_profiles=None,
    mig_profiles=None,
):
    """Match the shape ``discover_gpus()`` emits: nvidia-smi 8-char
    domain prefix (e.g. ``00000000:3b:00.0``). The helper
    ``_gpu_pci_name`` normalises this to ``pci_0000_3b_00_0``."""
    return {
        "pci_bus_id": pci,
        "name": name,
        "gpu_uuid": uuid,
        "memory_total_mb": memory_mb,
        "vgpu_profiles": vgpu_profiles or [],
        "mig_profiles": mig_profiles or [],
    }


# ── resolve_gpu_models ──────────────────────────────────────────────────


class TestResolveGpuModels:
    def test_first_sight_no_existing_card_derives_model(self, stub_rdb):
        gpus = [_gpu()]
        stub_rdb["Processed"].resolve_gpu_models("isard-hypervisor", gpus)
        assert gpus[0]["_resolved_model"] == "A100"
        # No existing row → no insert/update path here (ensure_gpu_cards
        # owns row creation).
        assert stub_rdb["tables"]["gpus"].update_log == []

    def test_uuid_match_keeps_persisted_model_across_slot_move(self, stub_rdb):
        # Card was previously seen at 3b:00.0; same uuid now at 5e:00.0.
        old_card_id = "auto-isard-hypervisor-pci_0000_3b_00_0"
        stub_rdb["tables"]["gpus"].rows[old_card_id] = {
            "id": old_card_id,
            "model": "OperatorCuratedModel",
            "gpu_uuid": "GPU-aaa",
        }
        gpus = [_gpu(pci="00000000:5e:00.0", name="NVIDIA A100", uuid="GPU-aaa")]
        stub_rdb["Processed"].resolve_gpu_models("isard-hypervisor", gpus)
        assert gpus[0]["_resolved_model"] == "OperatorCuratedModel"
        # Row migrated to new slot id.
        new_card_id = "auto-isard-hypervisor-pci_0000_5e_00_0"
        assert new_card_id in stub_rdb["tables"]["gpus"].rows
        assert old_card_id not in stub_rdb["tables"]["gpus"].rows

    def test_pci_anchored_card_with_persisted_model_is_trusted(self, stub_rdb):
        card_id = "auto-isard-hypervisor-pci_0000_3b_00_0"
        stub_rdb["tables"]["gpus"].rows[card_id] = {
            "id": card_id,
            "model": "LegacyName",
            "gpu_uuid": "GPU-aaa",
        }
        gpus = [_gpu()]
        stub_rdb["Processed"].resolve_gpu_models("isard-hypervisor", gpus)
        # Persisted model wins over freshly-derived "A100".
        assert gpus[0]["_resolved_model"] == "LegacyName"

    def test_card_swap_resets_model_and_logs(self, stub_rdb):
        card_id = "auto-isard-hypervisor-pci_0000_3b_00_0"
        # Same slot, but the persisted uuid differs from the discovered one
        # — physical card was swapped.
        stub_rdb["tables"]["gpus"].rows[card_id] = {
            "id": card_id,
            "model": "OldModel",
            "gpu_uuid": "GPU-old",
        }
        gpus = [_gpu(pci="00000000:3b:00.0", name="NVIDIA A100", uuid="GPU-new")]
        stub_rdb["Processed"].resolve_gpu_models("isard-hypervisor", gpus)
        assert gpus[0]["_resolved_model"] == "A100"
        # Row was updated with the fresh model + new uuid.
        assert stub_rdb["tables"]["gpus"].rows[card_id]["model"] == "A100"
        assert stub_rdb["tables"]["gpus"].rows[card_id]["gpu_uuid"] == "GPU-new"

    def test_legacy_row_without_uuid_backfills(self, stub_rdb):
        card_id = "auto-isard-hypervisor-pci_0000_3b_00_0"
        stub_rdb["tables"]["gpus"].rows[card_id] = {
            "id": card_id,
            "model": "LegacyName",
            # No gpu_uuid — legacy row pre-uuid-tracking.
        }
        gpus = [_gpu()]
        stub_rdb["Processed"].resolve_gpu_models("isard-hypervisor", gpus)
        assert gpus[0]["_resolved_model"] == "LegacyName"
        assert stub_rdb["tables"]["gpus"].rows[card_id]["gpu_uuid"] == "GPU-aaa"


# ── ensure_gpu_profiles ─────────────────────────────────────────────────


class TestEnsureGpuProfiles:
    def test_empty_input_is_noop(self, stub_rdb):
        stub_rdb["Processed"].ensure_gpu_profiles([])
        assert stub_rdb["tables"]["gpu_profiles"].insert_log == []

    def test_missing_resolved_model_raises(self, stub_rdb):
        gpus = [_gpu()]  # no _resolved_model
        with pytest.raises(RuntimeError, match="missing _resolved_model"):
            stub_rdb["Processed"].ensure_gpu_profiles(gpus)

    def test_creates_passthrough_profile_for_each_model(self, stub_rdb):
        gpus = [_gpu()]
        gpus[0]["_resolved_model"] = "A100"
        stub_rdb["Processed"].ensure_gpu_profiles(gpus)
        rows = stub_rdb["tables"]["gpu_profiles"].rows
        assert "NVIDIA-A100" in rows
        profiles = rows["NVIDIA-A100"]["profiles"]
        # passthrough entry is unconditional.
        assert any(p["profile"] == "passthrough" for p in profiles)

    def test_includes_vgpu_profiles_dedup(self, stub_rdb):
        gpus = [
            _gpu(
                vgpu_profiles=[
                    {
                        "name": "NVIDIA A100-4Q",
                        "framebuffer_mb": 4096,
                        "max_instances": 8,
                    }
                ]
            ),
            _gpu(
                pci="00000000:5e:00.0",
                uuid="GPU-bbb",
                vgpu_profiles=[
                    # Same suffix on the second card — must not dup.
                    {
                        "name": "NVIDIA A100-4Q",
                        "framebuffer_mb": 4096,
                        "max_instances": 8,
                    }
                ],
            ),
        ]
        for g in gpus:
            g["_resolved_model"] = "A100"
        stub_rdb["Processed"].ensure_gpu_profiles(gpus)
        profiles = stub_rdb["tables"]["gpu_profiles"].rows["NVIDIA-A100"]["profiles"]
        suffixes = [p["profile"] for p in profiles]
        # passthrough + 4Q, no duplicate 4Q from the second card.
        assert suffixes.count("4Q") == 1
        assert "passthrough" in suffixes

    def test_plain_gi_mig_profiles_are_not_bookable(self, stub_rdb):
        # Since upstream !4496/!4519 plain GI-name MIG profiles ("1g.10gb",
        # "+gfx"/"+me" variants) are deliberately NOT exposed as bookable
        # reservables: a plain GI carve strands the rest of the card. Only
        # passthrough, time-sliced vGPU ("<mem>Q") and MIG-backed vGPU
        # ("<slices>_<mem>Q", discovered as Q-series mdev types) enter the
        # catalog.
        gpus = [
            _gpu(
                mig_profiles=[
                    {
                        "name": "1g.10gb",
                        "profile_id": "1",
                        "memory_gib": 10,
                        "max_instances": 7,
                    }
                ]
            )
        ]
        gpus[0]["_resolved_model"] = "A100"
        stub_rdb["Processed"].ensure_gpu_profiles(gpus)
        profiles = stub_rdb["tables"]["gpu_profiles"].rows["NVIDIA-A100"]["profiles"]
        assert [p for p in profiles if p.get("mode") == "mig"] == []
        # The passthrough entry is still seeded.
        assert any(p.get("profile") == "passthrough" for p in profiles)

    @staticmethod
    def _suffix_units(stub_rdb, model):
        return {
            p["profile"]: p["units"]
            for p in stub_rdb["tables"]["gpu_profiles"].rows[f"NVIDIA-{model}"][
                "profiles"
            ]
        }

    def test_timesliced_units_are_framebuffer_limited_not_vf_ceiling(self, stub_rdb):
        # vfio_variant (SR-IOV) time-sliced "<fb>Q" profiles report
        # max_instances=0 and available_instances=<SR-IOV VF ceiling> (e.g.
        # 48). units MUST be the framebuffer count (card_total // profile_fb),
        # NOT 48 — else the booking planner over-allocates (books far more
        # desktops than can ever start). RTX PRO 6000 Blackwell = 96 GB
        # (reports 97887 MB): 48Q -> 2, 8Q -> 12, 6Q -> 16.
        gpus = [
            _gpu(
                name="NVIDIA RTX PRO 6000 Blackwell",
                memory_mb=97887,
                vgpu_profiles=[
                    {
                        "name": "NVIDIA RTXPro6000-48Q",
                        "framebuffer_mb": 49152,
                        "max_instances": 0,
                        "available_instances": 48,
                    },
                    {
                        "name": "NVIDIA RTXPro6000-8Q",
                        "framebuffer_mb": 8192,
                        "max_instances": 0,
                        "available_instances": 48,
                    },
                    {
                        "name": "NVIDIA RTXPro6000-6Q",
                        "framebuffer_mb": 6144,
                        "max_instances": 0,
                        "available_instances": 48,
                    },
                ],
            )
        ]
        gpus[0]["_resolved_model"] = "RTXPro6000"
        stub_rdb["Processed"].ensure_gpu_profiles(gpus)
        units = self._suffix_units(stub_rdb, "RTXPro6000")
        assert units["48Q"] == 2
        assert units["8Q"] == 12
        assert units["6Q"] == 16

    def test_vf_ceiling_caps_small_timesliced_profile(self, stub_rdb):
        # A 1Q profile fits 96 by framebuffer, but the card exposes only 48
        # SR-IOV VFs; units must cap at the VF ceiling (available_instances).
        gpus = [
            _gpu(
                memory_mb=97887,
                vgpu_profiles=[
                    {
                        "name": "NVIDIA RTXPro6000-1Q",
                        "framebuffer_mb": 1024,
                        "max_instances": 0,
                        "available_instances": 48,
                    }
                ],
            )
        ]
        gpus[0]["_resolved_model"] = "RTXPro6000"
        stub_rdb["Processed"].ensure_gpu_profiles(gpus)
        assert self._suffix_units(stub_rdb, "RTXPro6000")["1Q"] == 48

    def test_positive_max_instances_is_authoritative(self, stub_rdb):
        # MIG-backed and legacy-mdev profiles report a correct max_instances;
        # keep it verbatim (do not recompute from framebuffer).
        gpus = [
            _gpu(
                vgpu_profiles=[
                    {
                        "name": "NVIDIA A100-4Q",
                        "framebuffer_mb": 4096,
                        "max_instances": 8,
                        "available_instances": 8,
                    }
                ]
            )
        ]
        gpus[0]["_resolved_model"] = "A100"
        stub_rdb["Processed"].ensure_gpu_profiles(gpus)
        assert self._suffix_units(stub_rdb, "A100")["4Q"] == 8


# ── ensure_gpu_cards ────────────────────────────────────────────────────


class TestEnsureGpuCards:
    def test_empty_input_is_noop(self, stub_rdb):
        stub_rdb["Processed"].ensure_gpu_cards("isard-hypervisor", [])
        assert stub_rdb["tables"]["gpus"].insert_log == []

    def test_missing_resolved_model_raises(self, stub_rdb):
        gpus = [_gpu()]
        with pytest.raises(RuntimeError, match="missing _resolved_model"):
            stub_rdb["Processed"].ensure_gpu_cards("isard-hypervisor", gpus)

    def test_creates_card_when_no_existing_row(self, stub_rdb):
        gpus = [_gpu()]
        gpus[0]["_resolved_model"] = "A100"
        stub_rdb["Processed"].ensure_gpu_cards("isard-hypervisor", gpus)
        card_id = "auto-isard-hypervisor-pci_0000_3b_00_0"
        assert card_id in stub_rdb["tables"]["gpus"].rows
        new_card = stub_rdb["tables"]["gpus"].rows[card_id]
        assert new_card["physical_device"] == "isard-hypervisor-pci_0000_3b_00_0"
        assert new_card["model"] == "A100"
        assert new_card["gpu_uuid"] == "GPU-aaa"

    def test_updates_physical_device_when_card_exists(self, stub_rdb):
        card_id = "auto-isard-hypervisor-pci_0000_3b_00_0"
        stub_rdb["tables"]["gpus"].rows[card_id] = {
            "id": card_id,
            "model": "A100",
            "physical_device": None,
            "gpu_uuid": "GPU-aaa",
        }
        gpus = [_gpu()]
        gpus[0]["_resolved_model"] = "A100"
        stub_rdb["Processed"].ensure_gpu_cards("isard-hypervisor", gpus)
        # Existing card got physical_device set; not a fresh insert.
        assert stub_rdb["tables"]["gpus"].insert_log == []
        assert (
            stub_rdb["tables"]["gpus"].rows[card_id]["physical_device"]
            == "isard-hypervisor-pci_0000_3b_00_0"
        )

    def test_skips_when_physical_device_already_assigned(self, stub_rdb):
        # Different card_id already owns this physical_device.
        existing_id = "operator-curated-card"
        stub_rdb["tables"]["gpus"].rows[existing_id] = {
            "id": existing_id,
            "model": "A100",
            "physical_device": "isard-hypervisor-pci_0000_3b_00_0",
            "gpu_uuid": "GPU-aaa",
        }
        gpus = [_gpu()]
        gpus[0]["_resolved_model"] = "A100"
        stub_rdb["Processed"].ensure_gpu_cards("isard-hypervisor", gpus)
        # No auto-card created and the existing card untouched.
        assert (
            "auto-isard-hypervisor-pci_0000_3b_00_0"
            not in stub_rdb["tables"]["gpus"].rows
        )
        assert stub_rdb["tables"]["gpus"].rows[existing_id]["physical_device"] == (
            "isard-hypervisor-pci_0000_3b_00_0"
        )

    def test_assigns_to_unassigned_card_with_matching_model(self, stub_rdb):
        # An existing unassigned card with the same brand/model gets the
        # discovered physical device — this is how operators pre-declare
        # cards before they're physically wired up.
        unassigned_id = "operator-pre-declared"
        stub_rdb["tables"]["gpus"].rows[unassigned_id] = {
            "id": unassigned_id,
            "brand": "NVIDIA",
            "model": "A100",
            "physical_device": None,
        }
        gpus = [_gpu()]
        gpus[0]["_resolved_model"] = "A100"
        stub_rdb["Processed"].ensure_gpu_cards("isard-hypervisor", gpus)
        # No auto-card created; the pre-declared one was bound instead.
        assert (
            "auto-isard-hypervisor-pci_0000_3b_00_0"
            not in stub_rdb["tables"]["gpus"].rows
        )
        assert stub_rdb["tables"]["gpus"].rows[unassigned_id]["physical_device"] == (
            "isard-hypervisor-pci_0000_3b_00_0"
        )


class TestNormalizeGpuModel:
    """Lock the ``_common`` mirror of ``normalize_gpu_model`` against drift.

    Stays in lockstep with
    ``docker/hypervisor/src/lib/gpu_discovery.py::normalize_gpu_model``
    and ``component.apiv4.api.services.admin.hypervisors.
    AdminHypervisorsService._normalize_gpu_model``. The model is
    embedded verbatim in a URL path segment, so the output must be
    space-, dash- AND slash-free.
    """

    @staticmethod
    def _normalize(gpu_name, vgpu_profiles=None):
        from isardvdi_common.lib.hypervisors.hypervisors import HypervisorsProcessed

        return HypervisorsProcessed._normalize_gpu_model(gpu_name, vgpu_profiles)

    @pytest.mark.parametrize(
        "gpu_name, expected",
        [
            ("NVIDIA A16", "A16"),
            ("NVIDIA RTX A6000", "RTXA6000"),
            ("NVIDIA GA107GL [A2 / A16]", "GA107GL[A2A16]"),
            ("GA107GL[A2/A16]", "GA107GL[A2A16]"),
        ],
    )
    def test_name_path_is_clean(self, gpu_name, expected):
        result = self._normalize(gpu_name)
        assert result == expected
        assert "/" not in result
        assert "-" not in result
        assert " " not in result

    @pytest.mark.parametrize(
        "profile_name, expected",
        [
            # Classic time-sliced profile suffix
            ("A16-2Q", "A16"),
            # MIG slot-notation suffix (handled by the ``_common`` mirror's
            # MIG-aware regex)
            ("A100-1-5C", "A100"),
            # Slash inside model name
            ("GA107GL[A2/A16]-2Q", "GA107GL[A2A16]"),
        ],
    )
    def test_profile_path_is_clean(self, profile_name, expected):
        result = self._normalize("irrelevant", vgpu_profiles=[{"name": profile_name}])
        assert result == expected
        assert "/" not in result
        assert "-" not in result
        assert " " not in result
