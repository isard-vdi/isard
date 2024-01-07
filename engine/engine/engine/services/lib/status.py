import os

from cachetools import TTLCache, cached
from engine.models.balancers import BalancerInterface

engine_threads = [
    "background",
    "events",
    "broom",
    # "downloads_changes", # We will avoid this one as it starts and stops when needed
    "orchestrator",
    "changes_domains",
]

virt_balancer_type = os.environ.get("ENGINE_HYPER_BALANCER", "available_ram_percent")
virt_balancer = BalancerInterface(
    "default",
    balancer_type=virt_balancer_type,
)

disk_balancer_type = os.environ.get("ENGINE_DISK_BALANCER", "less_cpu")
disk_balancer = BalancerInterface(
    "00000000-0000-0000-0000-000000000000",
    balancer_type=disk_balancer_type,
)


@cached(cache=TTLCache(maxsize=1, ttl=5))
def get_next_hypervisor():
    virt, _ = virt_balancer.get_next_hypervisor()
    return virt


@cached(cache=TTLCache(maxsize=1, ttl=5))
def get_next_disk():
    return disk_balancer.get_next_diskoperations()
