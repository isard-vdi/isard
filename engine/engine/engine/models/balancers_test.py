import pytest
from engine.models.balancers import (
    Balancer_available_ram,
    Balancer_available_ram_percent,
    Balancer_less_cpu,
    Balancer_less_cpu_till_low_ram,
    Balancer_less_cpu_till_low_ram_percent,
    _get_used_ram_percentage,
    sort_hypervisors_cpu_percentage,
    sort_hypervisors_ram_absolute,
    sort_hypervisors_ram_percentage,
)


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
        )
    ],
)
def test_get_used_ram_percentage(test_input, expected):
    assert _get_used_ram_percentage(test_input) == expected


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
def test_available_ram(test_input, expected):
    balancer = Balancer_available_ram()


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
def test_available_ram_percent(test_input, expected):
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
def test_less_cpu(test_input, expected):
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
def test_less_cpu_till_low_ram(test_input, expected):
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
def test_less_cpu_till_low_ram_percent(test_input, expected):
    balancer = Balancer_less_cpu_till_low_ram_percent()

    assert balancer._balancer(test_input)["id"] == expected
