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
        return sort_hypervisors_ram_absolute(hypers)[0]


class Balancer_available_ram_percent:
    # This balancer will return the hypervisor with more available ram in percentage
    def _balancer(self, hypers):
        logs.main.debug(
            f"BALANCER AVAILABLE RAM%. MEMORY AVAILABLE: {[{h['id']: h['stats']['mem_stats']['available']*100/h['stats']['mem_stats']['total']} for h in hypers if h.get('stats',{}).get('mem_stats',{}).get('available')]}"
        )

        return sort_hypervisors_ram_percentage(hypers)[0]


class Balancer_less_cpu:
    # This balancer will return the hypervisor with less cpu usage
    def _balancer(self, hypers):
        logs.main.debug(
            f"BALANCER LESS CPU. CPU IDLE: {[{h['id']: h['stats']['cpu_1min']['idle']} for h in hypers if h.get('stats',{}).get('cpu_1min',{}).get('idle')]}"
        )

        return sort_hypervisors_cpu_percentage(hypers)[0]


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
            f"BALANCER LESS CPU TILL LOW RAM. RAM PERCENTAGE: {[{h['id']: (h['stats']['mem_stats']['total']-h['stats']['mem_stats']['available'])/h['stats']['mem_stats']['total']} for h in hypers_ordered_by_cpu if h.get('stats',{}).get('cpu_1min',{}).get('idle')]}"
        )

        # If the hypervisor has enough free RAM, choose it!
        for hyper in hypers_ordered_by_cpu:
            if _get_used_ram_percentage(hyper) <= self.RAM_LIMIT:
                logs.main.info(
                    "BALANCER LESS CPU TILL LOW RAM. BEST CPU HYPER SELECTED: %s"
                    % str(hyper["id"])
                )
                return hyper

        # If none of the hypervisors has enough RAM, choose the one with more available
        hypers_ordered_by_ram = sort_hypervisors_ram_absolute(hypers)
        logs.main.info(
            "BALANCER LESS CPU TILL LOW RAM. NO BEST CPU HYPER, SELECTED BY RAM: %s"
            % str(hypers_ordered_by_ram[0]["id"])
        )
        return hypers_ordered_by_ram[0]


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
            f"BALANCER LESS CPU TILL LOW RAM. RAM PERCENTAGE: {[{h['id']: (h['stats']['mem_stats']['total']-h['stats']['mem_stats']['available'])/h['stats']['mem_stats']['total']} for h in hypers_ordered_by_cpu if h.get('stats',{}).get('cpu_1min',{}).get('idle')]}"
        )

        # If the hypervisor has enough free RAM, choose it!
        for hyper in hypers_ordered_by_cpu:
            if _get_used_ram_percentage(hyper) <= self.RAM_LIMIT:
                logs.main.info(
                    "BALANCER LESS CPU TILL LOW RAM. BEST CPU HYPER SELECTED: %s"
                    % str(hyper["id"])
                )
                return hyper

        # If none of the hypervisors has enough RAM, choose the one with more available
        hypers_ordered_by_ram = sort_hypervisors_ram_percentage(hypers)

        logs.main.info(
            "BALANCER LESS CPU TILL LOW RAM PERCENTAGE. NO BEST CPU HYPER, SELECTED BY RAM PERCENT: %s"
            % str(hypers_ordered_by_ram[0]["id"])
        )
        return hypers_ordered_by_ram[0]


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

    def get_next_hypervisor(
        self,
        forced_hyp=None,
        favourite_hyp=None,
        reservables=None,
        force_gpus=None,
        storage_pool_id=None,
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
            return (
                self._get_next_capabilities_virt(
                    forced_hyp, favourite_hyp, storage_pool_id
                ),
                {},
            )

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
        )

        # If no hypervisor with gpu available and online, return False
        if hypervisor == False:
            logs.hmlog.error(
                f"No hypervisor with gpu {gpu_profile} available in pool {self.id_pool}"
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

    def _get_next_capabilities_virt(
        self, forced_hyp=None, favourite_hyp=None, storage_pool_id=None
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
            return False
        if len(hypers_w_threads) == 1:
            logs.main.debug("####################### BALANCER #######################")
            logs.main.debug(
                "Executing next virt action in the only hypervisor available: %s"
                % hypers_w_threads[0]["id"]
            )
            return hypers_w_threads[0]["id"]
        hyper_selected = self._balancer._balancer(hypers_w_threads)["id"]
        logs.main.debug("####################### BALANCER #######################")
        logs.main.debug(
            "Executing next virt action in hypervisor: %s (current hypers avail: %s)"
            % (hyper_selected, [h["id"] for h in hypers_w_threads]),
        )
        return hyper_selected

    def _get_next_capabilities_virt_gpus(
        self,
        forced_hyp=None,
        favourite_hyp=None,
        gpu_profile=None,
        forced_gpus_hypervisors=None,
        storage_pool_id=None,
    ):
        gpu_hypervisors_online = get_hypers_gpu_online(
            self.id_pool,
            forced_hyp,
            favourite_hyp,
            gpu_profile,
            forced_gpus_hypervisors,
            storage_pool_id=storage_pool_id,
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
            logs.main.error(
                "No GPU hypervisors online with profile %s to execute next virt action."
                % gpu_profile
            )
            return False, {}
        if len(hypers_w_threads) == 1:
            logs.main.debug("####################### BALANCER #######################")
            logs.main.debug(
                "Executing next GPU virt action in the only hypervisor %s with profile %s available"
                % (hypers_w_threads[0]["id"], gpu_profile)
            )
            return hypers_w_threads[0]["id"], _parse_extra_gpu_info(
                hypers_w_threads[0]["gpu_selected"]
            )
        hyper_selected = self._balancer._balancer(hypers_w_threads)
        logs.main.debug("####################### BALANCER #######################")
        logs.main.debug(
            "Executing next GPU virt action in hypervisor %s with profile %s (current similar hypers avail: %s)"
            % (hyper_selected, gpu_profile, [h["id"] for h in hypers_w_threads]),
        )
        return hyper_selected["id"], _parse_extra_gpu_info(
            hyper_selected["gpu_selected"]
        )


def _parse_extra_gpu_info(gpu_selected):
    return {
        "nvidia": True,
        "uid": gpu_selected["next_available_uid"],
        "gpu_id": gpu_selected["next_gpu_id"],
        "model": gpu_selected["gpu_profile"].split("-")[-2],
        "profile": gpu_selected["gpu_profile"].split("-")[-1],
    }


def _get_used_ram_percentage(hyper) -> float:
    mem_stats = hyper.get("stats", {}).get("mem_stats", {})
    total_ram = mem_stats.get("total", 1)
    used_ram = total_ram - mem_stats.get("available", 0)

    return 1 / (total_ram / used_ram)


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
