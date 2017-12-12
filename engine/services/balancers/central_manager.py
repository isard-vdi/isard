from random import random
from threading import Thread
from time import sleep

from engine.services.balancers.balancer_interface import BalancerInterface
from engine.services.log import hypman_log as hmlog


class CentralManager(BalancerInterface):
    def __init__(self, hyps):
        self.hyps = hyps
        self._init_hyps()
        self._init_eval_statistics()  # TODO remove this when Alberto implements new statistics feature
        self._get_actual_stats()
        self.thread_refresh_stats = self._start_refresh_stats()

    def __del__(self):
        """Necessary?"""
        if self.thread_refresh_stats.is_alive():
            self._stop_refresh_stats()

    def get_next(self, args):
        to_create_disk = args.get("to_create_disk")
        path_selected = args.get("path_selected")

        for hyp_id, hyp in self.hyps.items():
            hmlog.info("Calculing PS for hyp: {}".format(hyp_id))
            cpu_free, cpu_power, cpu_ratio, ram_free = self._get_stats(hyp)
            ps = self.calcule_ps(cpu_free, cpu_power, cpu_ratio, ram_free)
            hyp.ps = ps
        hyp_id_best_ps, hyp = max(self.hyps.items(), key=lambda v: v[1].ps)
        hmlog.info("Max PS of hyp: {}".format(hyp_id_best_ps))
        # TODO re-calcule hyp.balancer_load
        return hyp_id_best_ps

    def calcule_ps(self, cpu_free, cpu_power, cpu_ratio, ram_free):
        """
        Calcule priority service value from params
        :return:
        """
        rv = 1 if ram_free > 15 else ram_free / 100
        # # rv = ram_free / 100
        # rv = random()
        cpu_free /= 100
        ps = cpu_free * cpu_power * rv * cpu_ratio
        hmlog.debug(
            "cpu_free: {}, cpu_power: {}, cpu_ratio: {}, ram_free: {}, rv: {}, ps: {}".format(cpu_free, cpu_power,
                                                                                              cpu_ratio, ram_free, rv,
                                                                                              ps))
        return round(ps,2)

    def _init_hyps(self):
        for id, hyp in self.hyps.items():
            hyp.get_hyp_info()
            hyp.info["cpu_power"] = round(hyp.info["cpu_cores"] * hyp.info["cpu_threads"] * hyp.info["cpu_mhz"] / 1000,
                                          2)

    def _init_eval_statistics(self):
        """ REMOVE WHEN ALBERT FINISH STATISTICS FEATURE """
        for id, hyp in self.hyps.items():
            hyp.launch_eval_statistics()

    def _get_stats(self, hyp):
        """TODO: change this when Alberto implements new statistics feature """
        cpu_free = round(random() * 100, 2)
        cpu_power = hyp.info["cpu_power"]
        vcpus = hyp.balancer_load.get("vm_vcpus_total", 0)
        cpu_ratio = hyp.info["cpu_cores"] if vcpus == 0 else round(hyp.info["cpu_cores"] / vcpus, 2)
        ram_free = hyp.balancer_load.get("percent_free", 100)
        return cpu_free, cpu_power, cpu_ratio, ram_free

    def _start_refresh_stats(self, interval=30):
        self.running_refresh_stats = True
        t = Thread(target=self._refresh_stats, args=(interval,))
        t.start()
        return t

    def _stop_refresh_stats(self):
        self.running_refresh_stats = False

    def _refresh_stats(self, interval):
        while (self.running_refresh_stats):
            # self.get_load()  # En teoria esto no hara falta cuando lo haga el Alberto.
            self._get_actual_stats()
            sleep(interval)

    def _get_actual_stats(self):
        for id, hyp in self.hyps.items():
            hyp.balancer_load = hyp.load.copy()
