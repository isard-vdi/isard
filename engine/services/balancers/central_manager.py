from random import random
from threading import Thread
from time import sleep

from engine.services.balancers.balancer_interface import BalancerInterface
from engine.services.db import get_domain
from engine.services.log import hypman_log as hmlog


class CentralManager(BalancerInterface):
    def __init__(self, hyps=None):
        self.hyps = hyps
        self._init_hyps()
        self._get_actual_stats()
        self.thread_refresh_stats = self._start_refresh_stats()

    def __del__(self):
        """Necessary?"""
        if self.thread_refresh_stats.is_alive():
            self._stop_refresh_stats()

    def get_next(self, args):
        to_create_disk = args.get("to_create_disk")
        path_selected = args.get("path_selected")
        domain_id = args.get("domain_id")
        hmlog.info("---------------------------------------------")
        for hyp_id, hyp in self.hyps.items():
            hmlog.info("Calculing PS for hyp: {}".format(hyp_id))
            cpu_free, cpu_power, cpu_ratio, ram_free = self._get_stats(hyp)
            ps = self.calcule_ps(cpu_free, cpu_power, cpu_ratio, ram_free)
            hyp.ps = ps
        hyp_id_best_ps, hyp = max(self.hyps.items(), key=lambda v: v[1].ps)
        hmlog.info("Max PS of hyp: {}".format(hyp_id_best_ps))
        hmlog.info("---------------------------------------------")
        if domain_id:
            d = get_domain(domain_id)
            self._recalcule_stats(hyp, d)
        return hyp_id_best_ps

    def calcule_ps(self, cpu_free, cpu_power, cpu_ratio, ram_free):
        """
        Calcule priority service value from params
        :return:
        """
        rv = 1 if ram_free > 15 else ram_free / 100
        cv = 1 if cpu_ratio < 1 else 1 / cpu_ratio  # 1/cpu_ratio = inverse
        cpu_free /= 100
        ps = cpu_free * cpu_power * rv * cv
        hmlog.debug(
            "cpu_free: {}, cpu_power: {}, cpu_ratio: {}, ram_free: {}, rv: {}, ps: {}".format(cpu_free, cpu_power,
                                                                                              cpu_ratio, ram_free, rv,
                                                                                              ps))
        return round(ps, 2)

    def _init_hyps(self):
        for id, hyp in self.hyps.items():
            hyp.get_hyp_info()
            hyp.info["cpu_power"] = round(hyp.info["cpu_cores"] * hyp.info["cpu_threads"] * hyp.info["cpu_mhz"] / 1000,
                                          2)
            while(not getattr(hyp, "stats_hyp_now", None)):
                hmlog.info("Waiting for stats_hyp_now: {}".format(id))
                sleep(2)

    def _get_stats(self, hyp):
        """TODO: change this when Alberto implements new statistics feature """
        cpu_free = round(random() * 100, 2)
        cpu_power = hyp.info["cpu_power"]
        cpu_ratio = hyp.balancer_load.get("vcpu_cpu_rate", 0)
        ram_free = hyp.balancer_load.get("mem_free", 100)
        return cpu_free, cpu_power, cpu_ratio, ram_free

    def _recalcule_stats(self, hyp, domain):
        vcpus = domain["hardware"]["vcpus"]
        # cpu_free -= (2% * vcpus)
        hyp_vcpus = hyp.balancer_load.get("vcpus", 0)
        sum_vcpus = hyp_vcpus + vcpus
        hyp.balancer_load["vcpus"] = sum_vcpus
        hyp.balancer_load['vcpu_cpu_rate'] = round((sum_vcpus / hyp.info['cpu_threads']) * 100, 2)
        ram = domain["hardware"]["currentMemory"] / 1024  # Memory in MB
        hyp_ram = hyp.info["memory_in_MB"]
        ram_free = hyp.balancer_load.get("mem_free", 100)
        hyp.balancer_load["mem_free"] = ram_free - (ram / hyp_ram * 100)

    def _start_refresh_stats(self, interval=30):
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
