"""
Load Evaluator.
Must be called from EvalController
"""
from math import floor
from random import randint, shuffle
from time import sleep

from engine.controllers.eval_controller import EvalController
from engine.services.db import update_domain_status, get_domains_id
from engine.services.evaluators.evaluator_interface import EvaluatorInterface
from engine.services.log import eval_log


class LoadEval(EvaluatorInterface):
    def __init__(self, user_id, id_pool, dd, templates, hyps, params):
        self.name = "load_eval"
        self.user_id = user_id
        self.id_pool = id_pool
        self.defined_domains = dd
        self.templates = templates
        self.hyps = hyps
        self.params = params

    def start_domains(self):
        domains_id_list = EvalController.get_domains_id_randomized(self.user_id, self.id_pool, self.defined_domains,
                                                                   self.templates)
        total_domains = len(domains_id_list)
        threshold = floor(total_domains / 2)
        keep_starting = True
        started_domains = 0
        while (len(domains_id_list) and keep_starting):
            upper_limit_random = len(domains_id_list) if len(domains_id_list) < threshold else threshold
            n = randint(1, upper_limit_random)
            eval_log.debug("Starting {} random domains".format(n))
            started_domains += n
            sleep_time = self.params["START_SLEEP_TIME"] * n
            while (n):
                id = domains_id_list.pop()
                update_domain_status('Starting', id)
                n -= 1
            eval_log.debug("Waiting for next start {} seconds".format(sleep_time))
            sleep(sleep_time)
            keep_starting = self._evaluate()
        return {"started_domains": started_domains}

    def run(self):
        data = {}
        data_start = self.start_domains()
        data.update(data_start)
        data_final_statistics = self._get_final_statistics()
        data.update(data_final_statistics)
        return data

    def _evaluate(self):
        """
        Evaluate pool resources.
        If pool arrive to Threshold, return False
        :param id_pool:
        :return:
        """
        for h in self.hyps:
            statistics = h.get_eval_statistics()
            cond_1 = statistics["cpu_percent_free"] < 10
            cond_2 = statistics["ram_percent_free"] < h.percent_ram_template
            eval_log.debug("EVALUATE - Hyp: {}, cpu: {}, "
                           "ram: {}, ram_template: {}".format(h.id,
                                                              statistics["cpu_percent_free"],
                                                              statistics["ram_percent_free"],
                                                              h.percent_ram_template))
            condition_list = [cond_1, cond_2]
            if any(condition_list):  # Enter if there is any True value on condition_list
                eval_log.debug("EVALUATE - Return False")
                return False
        return True

    def _get_statistics(self):
        data = {}
        for h in self.hyps:
            statistics = h.get_eval_statistics()
            data[h.id] = statistics
        return data

    def _get_final_statistics(self):
        s = self._get_statistics()
        domains = []
        for id, h in s.items():
            domains.extend(h["domains"])
        d = {"hyps": s,
             "total_started_domains": {"ids": domains,
                                       "count": len(domains)}}
        return d
