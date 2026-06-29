from unittest.mock import patch

import pytest

from engine.models.balancers import (
    Balancer_available_ram,
    Balancer_available_ram_percent,
    Balancer_less_cpu,
    Balancer_less_cpu_till_low_ram,
    Balancer_less_cpu_till_low_ram_percent,
    _build_hugepages_extra,
    _get_used_ram_percentage,
    _parse_extra_gpu_info,
    sort_hypervisors_cpu_percentage,
    sort_hypervisors_ram_absolute,
    sort_hypervisors_ram_percentage,
    weighted_select,
)


# Every balancer ends with `weighted_select(sorted_list)` which uses
# `random.choices` to distribute load across candidates while still
# favouring the best-ranked one (3:2:1 weights for 3 hypers = 50/33/17%).
# The selection tests want to assert the sort/filter logic, not the
# randomness — so mock weighted_select to just return the top element.
# A separate TestWeightedSelect class covers the probabilistic side.
@pytest.fixture
def deterministic_select():
    with patch(
        "engine.models.balancers.weighted_select",
        new=lambda sorted_hypers: sorted_hypers[0],
    ) as p:
        yield p


@pytest.mark.parametrize(
    "test_input, expected",
    [
        (
            {
                "stats": {
                    "mem_stats": {
                        "total": 2000 * 1024 * 1024,
                        "available": 1500 * 1024 * 1024,
                    }
                }
            },
            0.25,
        ),
        # With explicit 'used' field (hugepages-aware)
        (
            {
                "stats": {
                    "mem_stats": {
                        "total": 1008 * 1024 * 1024,
                        "available": 206 * 1024 * 1024,
                        "used": 130 * 1024 * 1024,
                        "hugepages_total_kb": 336 * 1024 * 1024,
                        "hugepages_free_kb": 336 * 1024 * 1024,
                        "hugepages_used_kb": 0,
                    }
                }
            },
            130 / 1008,
        ),
    ],
)
def test_get_used_ram_percentage(test_input, expected):
    assert _get_used_ram_percentage(test_input) == pytest.approx(expected)


@pytest.mark.parametrize(
    "test_input, expected",
    [
        (
            [
                {
                    "id": "hyper1",
                    "stats": {
                        "mem_stats": {
                            "total": 2000 * 1024 * 1024,
                            "available": 100 * 1024 * 1024,
                        }
                    },
                },
                {
                    "id": "hyper2",
                    "stats": {
                        "mem_stats": {
                            "total": 500 * 1024,
                            "available": 120 * 1024 * 1024,
                        }
                    },
                },
                {
                    "id": "hyper3",
                    "stats": {
                        "mem_stats": {
                            "total": 100 * 1024,
                            "available": 80 * 1024 * 1024,
                        }
                    },
                },
            ],
            "hyper2",
        )
    ],
)
def test_sort_hypervisors_ram_absolute(test_input, expected):
    assert sort_hypervisors_ram_absolute(test_input)[0]["id"] == expected


@pytest.mark.parametrize(
    "test_input,expected",
    [
        (
            [
                {
                    "id": "hyper1",
                    "stats": {
                        "mem_stats": {
                            "total": 2000 * 1024 * 1024,
                            "available": 100 * 1024 * 1024,
                        }
                    },
                },
                {
                    "id": "hyper2",
                    "stats": {
                        "mem_stats": {
                            "total": 20000 * 1024 * 1024,
                            "available": 500 * 1024 * 1024,
                        }
                    },
                },
                {
                    "id": "hyper3",
                    "stats": {
                        "mem_stats": {
                            "total": 2000 * 1024 * 1024,
                            "available": 200 * 1024 * 1024,
                        }
                    },
                },
            ],
            "hyper2",
        ),
    ],
)
def test_available_ram(test_input, expected, deterministic_select):
    balancer = Balancer_available_ram()
    assert balancer._balancer(test_input)["id"] == expected


@pytest.mark.parametrize(
    "test_input,expected",
    [
        (
            [
                {
                    "id": "hyper1",
                    "stats": {
                        "mem_stats": {
                            "total": 2000 * 1024 * 1024,
                            "available": 100 * 1024 * 1024,
                        }
                    },
                },
                {
                    "id": "hyper2",
                    "stats": {
                        "mem_stats": {
                            "total": 2000 * 1024 * 1024,
                            "available": 500 * 1024 * 1024,
                        }
                    },
                },
                {
                    "id": "hyper3",
                    "stats": {
                        "mem_stats": {
                            "total": 2000 * 1024 * 1024,
                            "available": 200 * 1024 * 1024,
                        }
                    },
                },
            ],
            "hyper2",
        ),
    ],
)
def test_available_ram_percent(test_input, expected, deterministic_select):
    balancer = Balancer_available_ram_percent()

    assert balancer._balancer(test_input)["id"] == expected


@pytest.mark.parametrize(
    "test_input,expected",
    [
        (
            [
                {
                    "id": "hyper1",
                    "stats": {
                        "cpu_1min": {
                            "idle": 73,
                        },
                    },
                },
                {
                    "id": "hyper2",
                    "stats": {
                        "cpu_1min": {
                            "idle": 80,
                        },
                    },
                },
                {
                    "id": "hyper3",
                    "stats": {
                        "cpu_1min": {
                            "idle": 44,
                        },
                    },
                },
            ],
            "hyper2",
        ),
        (
            [
                {
                    "id": "hyper1",
                    "stats": {
                        "cpu_1min": {
                            "idle": 73,
                        },
                    },
                },
                {
                    "id": "hyper2",
                    "stats": {
                        "cpu_1min": {
                            "idle": 30,
                        },
                    },
                },
                {
                    "id": "hyper3",
                    "stats": {
                        "cpu_1min": {
                            "idle": 44,
                        },
                    },
                },
            ],
            "hyper1",
        ),
    ],
)
def test_less_cpu(test_input, expected, deterministic_select):
    balancer = Balancer_less_cpu()

    assert balancer._balancer(test_input)["id"] == expected


@pytest.mark.parametrize(
    "test_input,expected",
    [
        # When the RAM level is low, it should choose the hypervisor with less CPU percentage
        (
            [
                {
                    "id": "hyper1",
                    "stats": {
                        "cpu_1min": {
                            "idle": 73,
                        },
                        "mem_stats": {
                            "total": 2000 * 1024 * 1024,  # 2000 GB
                            "available": 1500 * 1024 * 1024,
                        },
                    },
                },
                {
                    "id": "hyper2",
                    "stats": {
                        "cpu_1min": {
                            "idle": 80,
                        },
                        "mem_stats": {
                            "total": 2000 * 1024 * 1024,  # 2000 GB
                            "available": 1500 * 1024 * 1024,
                        },
                    },
                },
                {
                    "id": "hyper3",
                    "stats": {
                        "cpu_1min": {
                            "idle": 44,
                        },
                        "mem_stats": {
                            "total": 2000 * 1024 * 1024,  # 2000 GB
                            "available": 1500 * 1024 * 1024,
                        },
                    },
                },
            ],
            "hyper2",
            # When the RAM level is high, it should choose the hypervisor with more free RAM
        ),
        (
            [
                {
                    "id": "hyper1",
                    "stats": {
                        "cpu_1min": {
                            "idle": 73,
                        },
                        "mem_stats": {
                            "total": 2000 * 1024 * 1024,  # 2000 GB
                            "available": 100 * 1024 * 1024,
                        },
                    },
                },
                {
                    "id": "hyper2",
                    "stats": {
                        "cpu_1min": {
                            "idle": 30,
                        },
                        "mem_stats": {
                            "total": 2000 * 1024 * 1024,  # 2000 GB
                            "available": 20 * 1024 * 1024,
                        },
                    },
                },
                {
                    "id": "hyper3",
                    "stats": {
                        "cpu_1min": {
                            "idle": 44,
                        },
                        "mem_stats": {
                            "total": 4000 * 1024 * 1024,  # 2000 GB
                            "available": 150 * 1024 * 1024,
                        },
                    },
                },
            ],
            "hyper3",
        ),
    ],
)
def test_less_cpu_till_low_ram(test_input, expected, deterministic_select):
    balancer = Balancer_less_cpu_till_low_ram()

    assert balancer._balancer(test_input)["id"] == expected


@pytest.mark.parametrize(
    "test_input,expected",
    [
        # When the RAM level is low, it should choose the hypervisor with less CPU percentage
        (
            [
                {
                    "id": "hyper1",
                    "stats": {
                        "cpu_1min": {
                            "idle": 73,
                        },
                        "mem_stats": {
                            "total": 2000 * 1024 * 1024,  # 2000 GB
                            "available": 1500 * 1024 * 1024,
                        },
                    },
                },
                {
                    "id": "hyper2",
                    "stats": {
                        "cpu_1min": {
                            "idle": 80,
                        },
                        "mem_stats": {
                            "total": 2000 * 1024 * 1024,  # 2000 GB
                            "available": 1500 * 1024 * 1024,
                        },
                    },
                },
                {
                    "id": "hyper3",
                    "stats": {
                        "cpu_1min": {
                            "idle": 44,
                        },
                        "mem_stats": {
                            "total": 2000 * 1024 * 1024,  # 2000 GB
                            "available": 1500 * 1024 * 1024,
                        },
                    },
                },
            ],
            "hyper2",
            # When the RAM level is high, it should choose the hypervisor with more RAM percentage
        ),
        (
            [
                {
                    "id": "hyper1",
                    "stats": {
                        "cpu_1min": {
                            "idle": 73,
                        },
                        "mem_stats": {
                            "total": 2000 * 1024 * 1024,  # 2000 GB
                            "available": 100 * 1024 * 1024,
                        },
                    },
                },
                {
                    "id": "hyper2",
                    "stats": {
                        "cpu_1min": {
                            "idle": 30,
                        },
                        "mem_stats": {
                            "total": 2000 * 1024 * 1024,  # 2000 GB
                            "available": 20 * 1024 * 1024,
                        },
                    },
                },
                {
                    "id": "hyper3",
                    "stats": {
                        "cpu_1min": {
                            "idle": 44,
                        },
                        "mem_stats": {
                            "total": 2000 * 1024 * 1024,  # 2000 GB
                            "available": 50 * 1024 * 1024,
                        },
                    },
                },
            ],
            "hyper1",
        ),
    ],
)
def test_less_cpu_till_low_ram_percent(test_input, expected, deterministic_select):
    balancer = Balancer_less_cpu_till_low_ram_percent()

    assert balancer._balancer(test_input)["id"] == expected


# --------------------------------------------------------------------------
# weighted_select covers the probabilistic side left out of the balancer
# selection tests above — pin the design contract (best candidate favoured
# ~50%, no candidate can be starved) with a statistical sample.
# --------------------------------------------------------------------------


class TestWeightedSelect:
    def test_single_hyper_always_returned(self):
        h = {"id": "only"}
        assert weighted_select([h]) is h

    def test_best_ranked_has_higher_probability_but_others_still_picked(self):
        # 3 candidates: weights 3:2:1 → best ~50%, middle ~33%, last ~17%.
        candidates = [{"id": "best"}, {"id": "mid"}, {"id": "worst"}]
        # Seed so the assertion is deterministic.
        import random

        random.seed(0)
        picks = [weighted_select(candidates)["id"] for _ in range(1000)]
        count_best = picks.count("best")
        count_mid = picks.count("mid")
        count_worst = picks.count("worst")
        # Every candidate must appear at least once — confirms no starvation.
        assert count_best > 0 and count_mid > 0 and count_worst > 0
        # Probability ordering holds: best > mid > worst.
        assert count_best > count_mid > count_worst
        # And best is roughly half the picks (50% ± 5% for 1000 trials).
        assert 450 <= count_best <= 550


class TestParseExtraGpuInfo:
    """`_parse_extra_gpu_info` must forward the per-host hugepage figures so
    `ui_actions` can back GPU desktops with hugepages.

    Regression: the numa-aware GPU placement port dropped `hugepages_free_kb`
    and `numa_hugepages_free_kb` from this dict. With them absent the GPU gate
    reads `extra_info.get("hugepages_free_kb", 0)` == 0, so `0 >= guest_RAM` is
    always False and every GPU desktop silently starts on 4K pages (anonymous
    RAM) instead of the reserved 1 GiB hugepage pool — exhausting normal RAM.
    """

    def test_forwards_hugepages_free_figures(self):
        gpu_selected = {
            "next_available_uid": "uid-1",
            "next_gpu_id": "gpu-1",
            "gpu_profile": "nvidia-rtxpro6000-8Q",
            "hugepages_info": {"1G": {"free": 900, "total": 900}, "mounted": True},
            "hugepages_free_kb": 900 * 1048576,
            "numa_hugepages_free_kb": {"0": 450 * 1048576, "1": 450 * 1048576},
            "gpu_numa_node": 1,
            "numa_topology": {"libvirt_numa_ok": False, "nodes": {}},
        }

        extra = _parse_extra_gpu_info(gpu_selected)

        assert extra["hugepages_free_kb"] == 900 * 1048576
        assert extra["numa_hugepages_free_kb"] == {
            "0": 450 * 1048576,
            "1": 450 * 1048576,
        }
        # The descriptive dict is still passed through unchanged.
        assert extra["hugepages"] == {
            "1G": {"free": 900, "total": 900},
            "mounted": True,
        }

    def test_forwards_vfio_variant_framework_and_vf_bdf(self):
        # On the vendor-specific VFIO framework the start path must emit a
        # vfio-pci VF hostdev keyed by vf_bdf instead of an mdev, so the picked
        # entry's framework + vf_bdf must reach ei (and thence recreate_xml_if_gpu).
        extra = _parse_extra_gpu_info(
            {
                "next_available_uid": "0000:05:00.4",  # VF BDF is the entry key
                "next_gpu_id": "hyp1-pci_0000_05_00_0",
                "gpu_profile": "NVIDIA-A16-2Q",
                "framework": "vfio_variant",
                "vf_bdf": "0000:05:00.4",
            }
        )
        assert extra["framework"] == "vfio_variant"
        assert extra["vf_bdf"] == "0000:05:00.4"
        assert extra["uid"] == "0000:05:00.4"
        assert extra["profile"] == "2Q"

    def test_legacy_mdev_has_no_framework(self):
        extra = _parse_extra_gpu_info(
            {
                "next_available_uid": "uid-1",
                "next_gpu_id": "gpu-1",
                "gpu_profile": "nvidia-a16-1Q",
            }
        )
        assert extra["framework"] is None
        assert extra["vf_bdf"] is None

    def test_hugepages_free_figures_default_safely(self):
        # A host that has not reported hugepage stats yet must not blow up.
        extra = _parse_extra_gpu_info(
            {
                "next_available_uid": "uid-1",
                "next_gpu_id": "gpu-1",
                "gpu_profile": "nvidia-a16-1Q",
            }
        )

        assert extra["hugepages_free_kb"] == 0
        assert extra["numa_hugepages_free_kb"] == {}


class TestBuildHugepagesExtra:
    """`_build_hugepages_extra` (non-GPU path) must still surface the NUMA
    topology + per-node free figures even when the host has no mounted
    hugepage pool, so `ui_actions` can NUMA-balance non-GPU desktops.

    Regression: the numa-aware placement port short-circuited the unmounted
    branch with `return {}`, dropping numa_topology/numa_hugepages_free_kb —
    which makes `ui_actions` see no NUMA nodes and skip cputune/numatune for
    non-GPU desktops on hosts without hugepages.
    """

    def test_unmounted_still_surfaces_numa(self):
        hyper = {
            "hugepages_info": {"mounted": False},
            "numa_topology": {"nodes": {"0": {}, "1": {}}},
            "stats": {"mem_stats": {"numa_hugepages_free_kb": {"0": 0, "1": 0}}},
        }

        extra = _build_hugepages_extra(hyper)

        assert extra["numa_topology"] == {"nodes": {"0": {}, "1": {}}}
        assert extra["numa_hugepages_free_kb"] == {"0": 0, "1": 0}
        # No hugepage pool → no hugepage-backing fields.
        assert "hugepages" not in extra

    def test_mounted_surfaces_full_hugepage_extra(self):
        hyper = {
            "hugepages_info": {"1G": {"free": 4, "total": 8}, "mounted": True},
            "min_free_mem_gb": 16,
            "numa_topology": {"nodes": {"0": {}}},
            "stats": {
                "mem_stats": {
                    "available": 100 * 1048576,
                    "hugepages_free_kb": 4 * 1048576,
                    "numa_hugepages_free_kb": {"0": 4 * 1048576},
                }
            },
        }

        extra = _build_hugepages_extra(hyper)

        assert extra["hugepages"] == {"1G": {"free": 4, "total": 8}, "mounted": True}
        assert extra["hugepages_free_kb"] == 4 * 1048576
        assert extra["numa_hugepages_free_kb"] == {"0": 4 * 1048576}
