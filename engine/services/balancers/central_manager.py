# Copyright 2018 the Isard-vdi project authors:
#      Alberto Larraz Dalmases
#      Josep Maria Viñolas Auquer
#      Daniel Criado Casas
# License: AGPLv3

import math
from threading import Thread
from time import sleep

from engine.services.balancers.balancer_interface import BalancerInterface
from engine.services.db import get_domain
from engine.services.log import logs


class CentralManager(BalancerInterface):
    def __init__(self, hyps=None):
        logs.hmlog.info("INIT CENTRAL MANAGER")
        self.hyps = hyps
        self._init_hyps()
        self._get_actual_stats()
        self.thread_refresh_stats = self._start_refresh_stats()

    def __del__(self):
        """Necessary?"""
        if self.thread_refresh_stats.is_alive():
            self._stop_refresh_stats()

    def get_next(self, args):
        domain_id = args.get("domain_id")
        for hyp_id, hyp in self.hyps.items():
            cpu_free, cpu_power, cpu_ratio, ram_free = self._get_stats(hyp)
            ps = self._calcule_ps(cpu_free, cpu_power, cpu_ratio, ram_free)
            hyp.ps = ps
        hyp_id_best_ps, hyp = max(self.hyps.items(), key=lambda v: v[1].ps)
        if domain_id:
            d = get_domain(domain_id)
            self._recalcule_stats(hyp, d)
        return hyp_id_best_ps

    def _calcule_ps(self, cpu_free, cpu_power, cpu_ratio, ram_free):
        """
        Calcule priority service value from params
        :return:
        """
        cpu_free = 0 if cpu_free < 25 else cpu_free
        ram_free = ram_free / 100
        cpu_free /= 100
        cpu_free *= cpu_free
        weight_cpu_power = 0.1 if cpu_ratio > 1 else 0.2
        ps = (0.4 * cpu_free) + (0.4 * ram_free) + (weight_cpu_power * cpu_power)
        if cpu_ratio > 1:
            i_cpu_ratio = 1/cpu_ratio
            ps += 0.1 * i_cpu_ratio
        return round(ps, 5)

    def _init_hyps(self):
        for id, hyp in self.hyps.items():
            logs.hmlog.info("INIT HYP: {}".format(id))
            hyp.get_hyp_info()
            hyp.get_load()  # Trick for no wait for stats_hyp_now
            logs.hmlog.info("cpu_cores: {}, "
                       "cpu_threads: {}, "
                       "log(cpu_threads): {}, "
                       "cpu_ghz: {}".format(hyp.info["cpu_cores"],
                                            hyp.info["cpu_threads"],
                                            math.log(hyp.info["cpu_threads"]),
                                            (hyp.info["cpu_mhz"] / 1000)))
            c = hyp.info["cpu_cores"]
            t = max(math.log(hyp.info["cpu_threads"]), 1)
            g = (hyp.info["cpu_mhz"] / 1000)  # GHz
            hyp.info["cpu_power"] = round(c * t * g, 2)
            logs.hmlog.info("cpu_power: {}".format(round(c * t * g, 2)))
            # TODO: Wait for stats_hyp_now attr
            # while (not getattr(hyp, "stats_hyp_now", None)):
            #     logs.hmlog.info("Waiting for stats_hyp_now: {}".format(id))
            #     sleep(2)
        total_cpu_power = sum(hyp.info["cpu_power"] for hyp in self.hyps.values())
        for id, hyp in self.hyps.items():
            hyp.info["cpu_power_normalized"] = round(hyp.info["cpu_power"] / total_cpu_power, 2)

    def _get_stats(self, hyp):
        cpu_free = hyp.balancer_load.get("cpu_free", 100)
        # cpu_power = hyp.info["cpu_power"]
        cpu_power = hyp.info["cpu_power_normalized"]
        cpu_ratio = hyp.balancer_load.get("vcpu_cpu_rate", 0)
        ram_free = hyp.balancer_load.get("mem_free", 100)
        return cpu_free, cpu_power, cpu_ratio, ram_free

    def _recalcule_stats(self, hyp, domain):
        vcpus = domain["hardware"]["vcpus"]
        hyp.balancer_load["cpu_free"] -= 2 * vcpus  # (2% * vcpus)
        hyp_vcpus = hyp.balancer_load.get("vcpus", 0)
        sum_vcpus = hyp_vcpus + vcpus
        hyp.balancer_load["vcpus"] = sum_vcpus
        hyp.balancer_load['vcpu_cpu_rate'] = round((sum_vcpus / hyp.info['cpu_threads']), 2)
        ram = domain["hardware"]["currentMemory"] / 1024  # Memory in MB
        hyp_ram = hyp.info["memory_in_MB"]
        ram_free = hyp.balancer_load.get("mem_free", 100)
        hyp.balancer_load["mem_free"] = ram_free - (ram / hyp_ram * 100)

    def _start_refresh_stats(self, interval=10):
        self.running_refresh_stats = True
        t = Thread(target=self._refresh_stats, args=(interval,))
        t.start()
        return t

    def _stop_refresh_stats(self):
        self.running_refresh_stats = False

    def _refresh_stats(self, interval):
        while (self.running_refresh_stats):
            self._get_actual_stats()
            sleep(interval)

    def _get_actual_stats(self):
        for id, hyp in self.hyps.items():
            hyp.balancer_load = hyp.stats_hyp_now.copy()
            hyp.balancer_load["cpu_free"] = 100 - hyp.balancer_load.get('cpu_load', 0)
            hyp.balancer_load["mem_free"] = 100 - hyp.balancer_load.get('mem_load_rate', 0)
