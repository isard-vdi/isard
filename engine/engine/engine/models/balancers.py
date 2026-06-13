import copy
import random
import threading
import time

from engine.models.numa_balancer import (
    aggregate_pending_by_node,
    select_balanced_numa_node,
)
from engine.services.db import get_table_field
from engine.services.db.hypervisors import (
    get_diskopts_online,
    get_hypers_gpu_online,
    get_hypers_online,
)
from engine.services.lib.functions import (
    get_diskoperations_pools_threads_running,
    get_pools_threads_running,
)
from engine.services.log import logs
from isardvdi_common.gpu_pool_policy import profile_suffix_from_id

""" 
BALANCERS 

Balancers receive fields stats and mountpoints
"""


class Balancer_round_robin:
    # This balancer will return the next hypervisor in a round robin fashion
    def __init__(self):
        self.index_round_robin = 0

    def _balancer(self, hypers):
        self.index_round_robin += 1
        if self.index_round_robin >= len(hypers):
            self.index_round_robin = 0
        logs.main.debug(
            f"BALANCER ROUND ROBIN. INDEX: {self.index_round_robin+1}/{len(hypers)}"
        )
        return hypers[self.index_round_robin]


class Balancer_available_ram:
    # This balancer will return the hypervisor with more available ram
    def _balancer(self, hypers):
        logs.main.debug(
            f"BALANCER AVAILABLE RAM. MEMORY AVAILABLE: {[{h['id']: h['stats']['mem_stats']['available']} for h in hypers if h.get('stats',{}).get('mem_stats',{}).get('available')]}"
        )
        return weighted_select(sort_hypervisors_ram_absolute(hypers))


class Balancer_available_ram_percent:
    # This balancer will return the hypervisor with more available ram in percentage
    def _balancer(self, hypers):
        logs.main.debug(
            f"BALANCER AVAILABLE RAM%. MEMORY AVAILABLE: {[{h['id']: h['stats']['mem_stats']['available']*100/h['stats']['mem_stats']['total']} for h in hypers if h.get('stats',{}).get('mem_stats',{}).get('available')]}"
        )

        return weighted_select(sort_hypervisors_ram_percentage(hypers))


class Balancer_less_cpu:
    # This balancer will return the hypervisor with less cpu usage
    def _balancer(self, hypers):
        logs.main.debug(
            f"BALANCER LESS CPU. CPU IDLE: {[{h['id']: h['stats']['cpu_1min']['idle']} for h in hypers if h.get('stats',{}).get('cpu_1min',{}).get('idle')]}"
        )

        return weighted_select(sort_hypervisors_cpu_percentage(hypers))


class Balancer_less_cpu_till_low_ram:
    RAM_LIMIT = 0.75  # If ram is below 75%, return hypervisor with less cpu usage

    # This balancer will return the hypervisor with less cpu usage when ram is below 75%
    # After that, it will return the hypervisor with more available ram
    def _balancer(self, hypers):
        hypers_ordered_by_cpu = sort_hypervisors_cpu_percentage(hypers)
        logs.main.debug(
            f"BALANCER LESS CPU TILL LOW RAM. CPU IDLE: {[{h['id']: h['stats']['cpu_1min']['idle']} for h in hypers_ordered_by_cpu if h.get('stats',{}).get('cpu_1min',{}).get('idle')]}"
        )
        logs.main.debug(
            f"BALANCER LESS CPU TILL LOW RAM. RAM PERCENTAGE: {[{h['id']: _get_used_ram_percentage(h)} for h in hypers_ordered_by_cpu if h.get('stats',{}).get('cpu_1min',{}).get('idle')]}"
        )

        # Collect all hypervisors with enough free RAM (sorted by CPU)
        eligible = [
            h
            for h in hypers_ordered_by_cpu
            if _get_used_ram_percentage(h) <= self.RAM_LIMIT
        ]

        if eligible:
            selected = weighted_select(eligible)
            logs.main.info(
                "BALANCER LESS CPU TILL LOW RAM. SELECTED: %s (from %d eligible)"
                % (str(selected["id"]), len(eligible))
            )
            return selected

        # If none of the hypervisors has enough RAM, distribute weighted by available RAM
        hypers_ordered_by_ram = sort_hypervisors_ram_absolute(hypers)
        selected = weighted_select(hypers_ordered_by_ram)
        logs.main.info(
            "BALANCER LESS CPU TILL LOW RAM. NO ELIGIBLE, SELECTED BY RAM: %s"
            % str(selected["id"])
        )
        return selected


class Balancer_less_cpu_till_low_ram_percent:
    RAM_LIMIT = 0.75  # If ram is below 75%, return hypervisor with less cpu usage

    # This balancer will return the hypervisor with less cpu usage when ram is below 75%
    # After that, it will return the hypervisor with more available ram in percentage
    def _balancer(self, hypers):
        hypers_ordered_by_cpu = sort_hypervisors_cpu_percentage(hypers)
        logs.main.debug(
            f"BALANCER LESS CPU TILL LOW RAM PERCENTAGE. CPU IDLE: {[{h['id']: h['stats']['cpu_1min']['idle']} for h in hypers_ordered_by_cpu if h.get('stats',{}).get('cpu_1min',{}).get('idle')]}"
        )
        logs.main.debug(
            f"BALANCER LESS CPU TILL LOW RAM PERCENTAGE. RAM PERCENTAGE: {[{h['id']: _get_used_ram_percentage(h)} for h in hypers_ordered_by_cpu if h.get('stats',{}).get('cpu_1min',{}).get('idle')]}"
        )

        # Collect all hypervisors with enough free RAM (sorted by CPU)
        eligible = [
            h
            for h in hypers_ordered_by_cpu
            if _get_used_ram_percentage(h) <= self.RAM_LIMIT
        ]

        if eligible:
            selected = weighted_select(eligible)
            logs.main.info(
                "BALANCER LESS CPU TILL LOW RAM PERCENTAGE. SELECTED: %s (from %d eligible)"
                % (str(selected["id"]), len(eligible))
            )
            return selected

        # If none of the hypervisors has enough RAM, distribute weighted by RAM percentage
        hypers_ordered_by_ram = sort_hypervisors_ram_percentage(hypers)
        selected = weighted_select(hypers_ordered_by_ram)
        logs.main.info(
            "BALANCER LESS CPU TILL LOW RAM PERCENTAGE. NO ELIGIBLE, SELECTED BY RAM PERCENT: %s"
            % str(selected["id"])
        )
        return selected


"""
BALANCER INTERFACE

Balancer interface is the interface that the engine uses to get the next hypervisor
"""

BALANCERS = [
    "round_robin",
    "available_ram",
    "available_ram_percent",
    "less_cpu",
    "less_cpu_till_low_ram",
    "less_cpu_till_low_ram_percent",
]


class BalancerInterface:

    # Virtualization uses "default" id_pool always when instantiated
    # from historic "hyper_pools" field (group by type of hyper)
    # So, calls to get_next_hypervisor will decide pool based on storage path category storage pool
    # NOTE: Now domain and it's storage belong to the same category. If we decide could not,
    # we should change the way to get the pool_id from the storage user owner category

    # Disk operations uses the domain category to decide the pool:
    # pool_id = get_category_storage_pool_id(dict_domain.get("category"))
    # To call the balancer for get_next_diskoperations

    def __init__(self, id_pool="default", balancer_type="round_robin"):
        if balancer_type not in BALANCERS:
            logs.hmlog.error(f"Balancer type {balancer_type} not found in {BALANCERS}")
            exit(1)
        self.id_pool = id_pool
        if balancer_type == "round_robin":
            self._balancer = Balancer_round_robin()
        if balancer_type == "available_ram":
            self._balancer = Balancer_available_ram()
        if balancer_type == "available_ram_percent":
            self._balancer = Balancer_available_ram_percent()
        if balancer_type == "less_cpu":
            self._balancer = Balancer_less_cpu()
        if balancer_type == "less_cpu_till_low_ram":
            self._balancer = Balancer_less_cpu_till_low_ram()
        if balancer_type == "less_cpu_till_low_ram_percent":
            self._balancer = Balancer_less_cpu_till_low_ram_percent()

        self._lock = threading.Lock()
        self._pending_ram = {}  # {hyp_id: [(ram_gb, timestamp), ...]}
        # Per-NUMA-node in-flight starts, so consecutive non-GPU desktops spread
        # across nodes instead of all landing on the one with most free pages.
        self._pending_node = {}  # {hyp_id: [(node, ram_gb, vcpus, timestamp), ...]}

    _PENDING_EXPIRY_SECONDS = 30

    def _record_pending(self, hyp_id, ram_gb):
        """Record a pending domain start's RAM usage for a hypervisor."""
        self._pending_ram.setdefault(hyp_id, []).append((ram_gb, time.time()))

    def _record_pending_node(self, hyp_id, node, ram_gb, vcpus):
        """Record a pending domain start's RAM+vCPUs on a specific NUMA node."""
        self._pending_node.setdefault(hyp_id, []).append(
            (str(node), ram_gb, vcpus, time.time())
        )

    def _get_pending_by_node(self, hyp_id):
        """Return live per-node pending load: {node: {ram_kb, vcpus}}."""
        return aggregate_pending_by_node(
            self._pending_node.get(hyp_id, []),
            time.time(),
            self._PENDING_EXPIRY_SECONDS,
        )

    def _cleanup_expired(self):
        """Remove pending entries older than expiry threshold."""
        cutoff = time.time() - self._PENDING_EXPIRY_SECONDS
        for hyp_id in list(self._pending_ram):
            self._pending_ram[hyp_id] = [
                (ram, ts) for ram, ts in self._pending_ram[hyp_id] if ts > cutoff
            ]
            if not self._pending_ram[hyp_id]:
                del self._pending_ram[hyp_id]
        for hyp_id in list(self._pending_node):
            self._pending_node[hyp_id] = [
                e for e in self._pending_node[hyp_id] if e[3] > cutoff
            ]
            if not self._pending_node[hyp_id]:
                del self._pending_node[hyp_id]

    def _get_pending_ram_kb(self, hyp_id):
        """Return total pending RAM in KB for a hypervisor."""
        entries = self._pending_ram.get(hyp_id, [])
        return sum(ram_gb for ram_gb, _ in entries) * 1048576  # GB to KB

    def _adjust_for_pending(self, hypers):
        """Return deep-copied hyper dicts with available RAM reduced by pending starts."""
        adjusted = copy.deepcopy(hypers)
        for h in adjusted:
            pending_kb = self._get_pending_ram_kb(h["id"])
            if pending_kb > 0:
                mem_stats = h.get("stats", {}).get("mem_stats")
                if mem_stats and "available" in mem_stats:
                    mem_stats["available"] = max(0, mem_stats["available"] - pending_kb)
        return adjusted

    def get_next_hypervisor(
        self,
        forced_hyp=None,
        favourite_hyp=None,
        reservables=None,
        force_gpus=None,
        storage_pool_id=None,
        domain_memory_gb=1.0,
        domain_vcpus=1,
        prefer_cpuset=None,
        prefer_numa_node=None,
        coplacement_profiles=None,
    ):
        if storage_pool_id is None:
            logs.hmlog.error("Storage pool id is None so can't get next hypervisor")
            return False, {}

        # Desktop does not have vgpu
        if (
            not reservables
            or not reservables.get("vgpus")
            or not len(reservables.get("vgpus", []))
        ):
            hyp_id, hyp_extra = self._get_next_capabilities_virt(
                forced_hyp,
                favourite_hyp,
                storage_pool_id,
                domain_memory_gb,
                domain_vcpus,
            )
            return hyp_id, hyp_extra

        # Desktop has vgpu
        gpu_profile = reservables.get("vgpus")[0]

        # Force gpus is a list of existing vgpus ids
        if force_gpus and len(force_gpus):
            forced_gpus_hypervisors = [
                get_table_field("vgpus", fgh, "hyp_id") for fgh in force_gpus
            ]
        else:
            forced_gpus_hypervisors = None

        hypervisor, extra = self._get_next_capabilities_virt_gpus(
            forced_hyp,
            favourite_hyp,
            gpu_profile,
            forced_gpus_hypervisors,
            storage_pool_id,
            domain_memory_gb,
            domain_vcpus=domain_vcpus,
            prefer_cpuset=prefer_cpuset,
            prefer_numa_node=prefer_numa_node,
            coplacement_profiles=coplacement_profiles,
        )

        # If no hypervisor with gpu available and online, return False
        if hypervisor == False:
            logs.hmlog.warning(
                f"No GPU capacity for profile {gpu_profile} in pool {self.id_pool}: "
                f"all matching cards in use or no GPU hypervisor online"
            )
            return False, {}

        return hypervisor, extra

    def get_next_diskoperations(self, forced_hyp=None, favourite_hyp=None):
        hypers = get_diskopts_online(self.id_pool, forced_hyp, favourite_hyp)
        hypers_w_threads = get_diskoperations_pools_threads_running(hypers)
        if len(hypers) != len(hypers_w_threads):
            logs.main.error("####################### BALANCER #######################")
            logs.main.error(
                "Some disk operations hypervisors are not online in pool %s."
                % self.id_pool
            )
            logs.main.error(
                "Hypervisors online: %s. Hypervisors with disks threads running: %s."
                % (
                    [h["id"] for h in hypers],
                    [h["id"] for h in hypers_w_threads],
                )
            )

        if len(hypers_w_threads) == 0:
            logs.main.error("####################### BALANCER #######################")
            logs.main.error(
                "No disk operations online to execute next diskopts action in pool %s."
                % self.id_pool
            )
            return False
        if len(hypers_w_threads) == 1:
            logs.main.debug("####################### BALANCER #######################")
            logs.main.debug(
                "Executing next disk operations action in the only diskopts available: %s in pool %s."
                % (hypers_w_threads[0]["id"], self.id_pool)
            )
            return hypers[0]["id"]
        hyper_selected = self._balancer._balancer(hypers_w_threads)["id"]
        logs.main.debug("####################### BALANCER #######################")
        logs.main.debug(
            "Executing next disk operations action in hypervisor: %s (current hypers avail: %s) in pool %s"
            % (hyper_selected, [h["id"] for h in hypers_w_threads], self.id_pool)
        ),
        return hyper_selected

    def _record_gpu_node_pending(
        self, hyp_id, gpu_extra, domain_memory_gb, domain_vcpus
    ):
        """Record a GPU desktop's load on its GPU's NUMA node.

        A GPU desktop is pinned to the node of its card(s) (in ui_actions), so it
        does not use the non-GPU balancer — but recording it here lets the
        non-GPU balancer steer later desktops away from the GPU-loaded node.
        Caller MUST hold ``self._lock``.
        """
        try:
            nn = gpu_extra.get("gpu_numa_node")
            if nn is not None and int(nn) >= 0:
                self._record_pending_node(
                    hyp_id, int(nn), domain_memory_gb, int(domain_vcpus or 1)
                )
        except Exception as e:
            logs.main.warning(f"GPU NUMA pending record skipped for {hyp_id}: {e}")

    def _attach_balanced_node(
        self, hyp_id, hyper_dict, extra, domain_memory_gb, domain_vcpus
    ):
        """Pick a NUMA node for a non-GPU desktop and record it as in-flight.

        Mutates and returns ``extra`` (adds ``selected_numa_node`` when a node is
        chosen). Best-effort: any failure leaves ``extra`` untouched so the start
        proceeds with the caller's existing single-node behaviour. Caller MUST
        hold ``self._lock`` (this reads and updates the per-node pending state).
        """
        try:
            vcpus = int(domain_vcpus or 1)
            numa_hp_free = (
                hyper_dict.get("stats", {})
                .get("mem_stats", {})
                .get("numa_hugepages_free_kb", {})
            )
            node = select_balanced_numa_node(
                hyper_dict.get("numa_topology", {}),
                numa_hp_free,
                int(domain_memory_gb * 1048576),
                vcpus,
                self._get_pending_by_node(hyp_id),
            )
            if node is not None:
                extra["selected_numa_node"] = node
                self._record_pending_node(hyp_id, node, domain_memory_gb, vcpus)
        except Exception as e:
            logs.main.warning(f"NUMA node balancing skipped for {hyp_id}: {e}")
        return extra

    def _get_next_capabilities_virt(
        self,
        forced_hyp=None,
        favourite_hyp=None,
        storage_pool_id=None,
        domain_memory_gb=1.0,
        domain_vcpus=1,
    ):
        hypers = get_hypers_online(
            self.id_pool, forced_hyp, favourite_hyp, storage_pool_id=storage_pool_id
        )
        hypers_w_threads = get_pools_threads_running(hypers)
        if len(hypers) != len(hypers_w_threads):
            logs.main.error("####################### BALANCER #######################")
            logs.main.error(
                "Some virt hypervisors are not online in pool %s." % self.id_pool
            )
            logs.main.error(
                "Virt hypervisors online: %s. Virt hypervisors with threads running: %s."
                % (
                    [h["id"] for h in hypers],
                    [h["id"] for h in hypers_w_threads],
                )
            )
        if len(hypers_w_threads) == 0:
            logs.main.debug("####################### BALANCER #######################")
            logs.main.error("No hypervisors online to execute next virt action.")
            return False, {}
        if len(hypers_w_threads) == 1:
            hyper_selected = hypers_w_threads[0]["id"]
            extra = _build_hugepages_extra(hypers_w_threads[0])
            with self._lock:
                self._record_pending(hyper_selected, domain_memory_gb)
                self._attach_balanced_node(
                    hyper_selected,
                    hypers_w_threads[0],
                    extra,
                    domain_memory_gb,
                    domain_vcpus,
                )
            logs.main.debug("####################### BALANCER #######################")
            logs.main.debug(
                "Executing next virt action in the only hypervisor available: %s"
                % hyper_selected
            )
            return hyper_selected, extra

        with self._lock:
            self._cleanup_expired()
            adjusted_hypers = self._adjust_for_pending(hypers_w_threads)
            hyper_selected = self._balancer._balancer(adjusted_hypers)["id"]
            self._record_pending(hyper_selected, domain_memory_gb)
            selected_hyper = next(
                (h for h in hypers_w_threads if h["id"] == hyper_selected), {}
            )
            extra = _build_hugepages_extra(selected_hyper)
            self._attach_balanced_node(
                hyper_selected, selected_hyper, extra, domain_memory_gb, domain_vcpus
            )

        logs.main.debug("####################### BALANCER #######################")
        logs.main.debug(
            "Executing next virt action in hypervisor: %s (current hypers avail: %s)"
            % (hyper_selected, [h["id"] for h in hypers_w_threads]),
        )
        return hyper_selected, extra

    def _get_next_capabilities_virt_gpus(
        self,
        forced_hyp=None,
        favourite_hyp=None,
        gpu_profile=None,
        forced_gpus_hypervisors=None,
        storage_pool_id=None,
        domain_memory_gb=1.0,
        domain_vcpus=1,
        prefer_cpuset=None,
        prefer_numa_node=None,
        coplacement_profiles=None,
    ):
        gpu_hypervisors_online = get_hypers_gpu_online(
            self.id_pool,
            forced_hyp,
            favourite_hyp,
            gpu_profile,
            forced_gpus_hypervisors,
            storage_pool_id=storage_pool_id,
            prefer_cpuset=prefer_cpuset,
            prefer_numa_node=prefer_numa_node,
            coplacement_profiles=coplacement_profiles,
        )
        hypers_w_threads = get_pools_threads_running(gpu_hypervisors_online)
        if len(gpu_hypervisors_online) != len(hypers_w_threads):
            logs.main.error("####################### BALANCER #######################")
            logs.main.error(
                "Some GPU hypervisors are not online in pool %s." % self.id_pool
            )
            logs.main.error(
                "Virt hypervisors online: %s. Virt hypervisors with threads running: %s."
                % (
                    [h["id"] for h in gpu_hypervisors_online],
                    [h["id"] for h in hypers_w_threads],
                )
            )

        if len(hypers_w_threads) == 0:
            logs.main.debug("####################### BALANCER #######################")
            logs.main.warning(
                "No GPU capacity for profile %s: all matching cards in use or no "
                "GPU hypervisor online." % gpu_profile
            )
            return False, {}
        if len(hypers_w_threads) == 1:
            hyp_id = hypers_w_threads[0]["id"]
            gpu_extra = _parse_extra_gpu_info(hypers_w_threads[0]["gpu_selected"])
            with self._lock:
                self._record_pending(hyp_id, domain_memory_gb)
                self._record_gpu_node_pending(
                    hyp_id, gpu_extra, domain_memory_gb, domain_vcpus
                )
            logs.main.debug("####################### BALANCER #######################")
            logs.main.debug(
                "Executing next GPU virt action in the only hypervisor %s with profile %s available"
                % (hyp_id, gpu_profile)
            )
            return hyp_id, gpu_extra

        with self._lock:
            self._cleanup_expired()
            adjusted_hypers = self._adjust_for_pending(hypers_w_threads)
            hyper_selected = self._balancer._balancer(adjusted_hypers)
            self._record_pending(hyper_selected["id"], domain_memory_gb)
            # Find the original (non-deep-copied) entry to get gpu_selected
            original = next(
                h for h in hypers_w_threads if h["id"] == hyper_selected["id"]
            )
            gpu_extra = _parse_extra_gpu_info(original["gpu_selected"])
            self._record_gpu_node_pending(
                original["id"], gpu_extra, domain_memory_gb, domain_vcpus
            )
        logs.main.debug("####################### BALANCER #######################")
        logs.main.debug(
            "Executing next GPU virt action in hypervisor %s with profile %s (current similar hypers avail: %s)"
            % (original["id"], gpu_profile, [h["id"] for h in hypers_w_threads]),
        )
        return original["id"], gpu_extra


def _build_hugepages_extra(hyper_dict):
    """Extract hugepages fallback info for non-GPU desktops."""
    hugepages_info = hyper_dict.get("hugepages_info", {})
    mem_stats = hyper_dict.get("stats", {}).get("mem_stats", {})
    if not hugepages_info or not hugepages_info.get("mounted"):
        return {
            "numa_topology": hyper_dict.get("numa_topology", {}),
            "numa_hugepages_free_kb": mem_stats.get("numa_hugepages_free_kb", {}),
        }
    return {
        "hugepages": hugepages_info,
        "min_free_mem_gb": hyper_dict.get("min_free_mem_gb", 0) or 0,
        "mem_available_kb": mem_stats.get("available", 0),
        "hugepages_free_kb": mem_stats.get("hugepages_free_kb", 0),
        "numa_hugepages_free_kb": mem_stats.get("numa_hugepages_free_kb", {}),
        "numa_topology": hyper_dict.get("numa_topology", {}),
    }


def _parse_extra_gpu_info(gpu_selected):
    return {
        "nvidia": True,
        "uid": gpu_selected["next_available_uid"],
        "gpu_id": gpu_selected["next_gpu_id"],
        "model": gpu_selected["gpu_profile"].split("-", 2)[1],
        # Bare canonical suffix (e.g. "8Q", "passthrough") with any "~<variant>"
        # qualifier stripped, so downstream mdev/info.types matching keys on it.
        "profile": (
            profile_suffix_from_id(gpu_selected["gpu_profile"])
            if len(gpu_selected["gpu_profile"].split("-", 2)) > 2
            else ""
        ),
        "pci_bus_id": gpu_selected.get("pci_bus_id"),
        "mig": gpu_selected.get("mig", False),
        "companion_pci_bdfs": gpu_selected.get("companion_pci_bdfs") or [],
        "hugepages": gpu_selected.get("hugepages_info", {}),
        "hugepages_free_kb": gpu_selected.get("hugepages_free_kb", 0),
        "numa_hugepages_free_kb": gpu_selected.get("numa_hugepages_free_kb", {}),
        "gpu_numa_node": gpu_selected.get("gpu_numa_node"),
        "numa_topology": gpu_selected.get("numa_topology", {}),
    }


def _get_used_ram_percentage(hyper) -> float:
    mem_stats = hyper.get("stats", {}).get("mem_stats", {})
    total_ram = mem_stats.get("total", 1)
    used_ram = mem_stats.get("used", total_ram - mem_stats.get("available", 0))

    return used_ram / total_ram if total_ram > 0 else 0


# Sort the hypervisors by used RAM (absolute) (low to high)
def sort_hypervisors_ram_absolute(hypers):
    return sorted(
        hypers,
        key=lambda h: h.get("stats", {}).get("mem_stats", {}).get("available", 0),
        reverse=True,
    )


# Sort the hypervisors by used RAM percentage (low to high)
def sort_hypervisors_ram_percentage(hypers):
    return sorted(hypers, key=lambda h: _get_used_ram_percentage(h))


# Sort the hypervisors by used CPU percentage (low to high)
def sort_hypervisors_cpu_percentage(hypers):
    return sorted(
        hypers,
        key=lambda h: h.get("stats", {}).get("cpu_1min", {}).get("idle", 0),
        reverse=True,
    )


def weighted_select(sorted_hypers):
    """Select from sorted hypers with probability weighted by rank.

    Best-ranked hypervisor gets highest weight, distributing load
    while still favoring better candidates.
    With 3 hypers: weights are 3:2:1 (50%, 33%, 17%).
    """
    n = len(sorted_hypers)
    weights = list(range(n, 0, -1))
    return random.choices(sorted_hypers, weights=weights, k=1)[0]
