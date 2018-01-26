# Copyright 2018 the Isard-vdi project authors:
#      Alberto Larraz Dalmases
#      Josep Maria Viñolas Auquer
#      Daniel Criado Casas
# License: AGPLv3

"""
Load Evaluator.
Must be called from EvalController
"""
from math import floor
from pprint import pformat
from random import randint
from statistics import mean
from threading import Thread
from time import sleep

import graphyte

from engine.config import GRAFANA
from engine.controllers.eval_controller import EvalController
from engine.services.db import update_domain_status
from engine.services.evaluators.evaluator_interface import EvaluatorInterface
from engine.services.log import logs


class LoadEval(EvaluatorInterface):
    def __init__(self, user_id, id_pool, dd, templates, hyps, params):
        self.name = "load"
        self.sender = graphyte.Sender(GRAFANA['url'], prefix='isard-eval.{}'.format(self.name), port=GRAFANA['carbon_port'])
        self.user_id = user_id
        self.id_pool = id_pool
        self.defined_domains = dd
        self.templates = templates
        self.hyps = hyps
        self.params = params
        self.running_grafana_stats = False

    def run(self):
        self.t_grafana_stats = self._launch_thread_grafana_stats()
        data = {}
        data_start = self._start_domains()
        data.update(data_start)
        data_final_statistics = self._get_final_statistics()
        data.update(data_final_statistics)
        self._stop_grafana_stats()
        return data

    def _start_domains(self):
        domains_id_list = EvalController.get_domains_id_randomized(self.user_id, self.id_pool, self.defined_domains,
                                                                   self.templates)
        total_domains = len(domains_id_list)
        threshold = floor(total_domains / 2)
        keep_starting = True
        started_domains = 0
        while (len(domains_id_list) and keep_starting):
            n = max(int(len(domains_id_list) / 4), 1)
            # upper_limit_random = len(domains_id_list) if len(domains_id_list) < threshold else threshold
            # n = randint(1, upper_limit_random)
            logs.eval.debug("Starting {} random domains".format(n))
            started_domains += n
            sleep_time = 20
            while (n):
                id = domains_id_list.pop()
                update_domain_status('Starting', id)
                n -= 1
            logs.eval.debug("Waiting for next start {} seconds".format(sleep_time))
            while (sleep_time > 0 and keep_starting):
                sleep(5)
                keep_starting = self._evaluate()
                sleep_time -= 5
            keep_starting = self._evaluate()
        sleep(20)
        return {"started_domains": started_domains}

    def _evaluate(self):
        """
        Evaluate pool resources.
        If pool arrive to Threshold, return False
        :param id_pool:
        :return:
        """
        overload = 0
        for h in self.hyps:
            statistics = self._process_stats(h)
            cond_1 = statistics["cpu_percent_free"] < 10
            cond_2 = statistics.get("ram_percent_free", 100) < h.percent_ram_template
            logs.eval.debug("EVALUATE - Hyp: {}, cpu: {}, "
                           "ram: {}, ram_template: {}".format(h.id,
                                                              statistics["cpu_percent_free"],
                                                              statistics["ram_percent_free"],
                                                              h.percent_ram_template))
            condition_list = [cond_1, cond_2]
            if any(condition_list):  # Enter if there is any True value on condition_list
                overload += 1
                logs.eval.debug("EVALUATE - Overload: {}".format(overload))
                # return False
        return overload < 1

    def _get_final_statistics(self):
        data = {h.id: self._process_stats(h) for h in self.hyps}
        d = {
            "hyps": data,
            "total_started_domains": sum(h["domains_count"] for h in data.values())
        }
        return d

    def _process_stats(self, hyp):
        stats = hyp.stats_hyp[-3:]  # Get 3 last rows of stats data
        cpu_load = stats['cpu_load'].mean()
        cpu_free = round(100 - cpu_load, 2)
        # cpu_percent_free = 100 - hyp.stats_hyp_now.get('cpu_load', 0)
        # logs.eval.debug("Hyp: {}, CPU now free: {}".format(hyp.id, cpu_percent_free))
        # logs.eval.debug("Hyp: {}, CPU mean free: {}".format(hyp.id, cpu_free))
        ram_percent_free = round(100 - hyp.stats_hyp_now.get('mem_load_rate', 0), 2)

        data = {"cpu_percent_free": cpu_free,
                "ram_percent_free": ram_percent_free,
                "domains_count": len(hyp.stats_domains_now)}
        return data

    def _launch_thread_grafana_stats(self, interval=1):
        self.running_grafana_stats = True
        t = Thread(target=self._grafana_stats, args=(interval,))
        t.start()
        return t

    def _grafana_stats(self, interval):
        while (self.running_grafana_stats):
            total_domains = 0
            for h in self.hyps:
                statistics = self._process_stats(h)
                self.sender.send(h.id + '.cpu_percent_free', statistics["cpu_percent_free"])
                self.sender.send(h.id + '.ram_percent_free', statistics["ram_percent_free"])
                self.sender.send(h.id + '.percent_ram_template', h.percent_ram_template)
                self.sender.send(h.id + '.n_domains', statistics["domains_count"])
                total_domains += statistics["domains_count"]
            self.sender.send('n_domains', total_domains)
            sleep(interval)

    def _stop_grafana_stats(self):
        self.running_grafana_stats = False
