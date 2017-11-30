from math import floor
from random import randint, shuffle
from statistics import mean
import time
from time import sleep

from engine.controllers.eval_controller import EvalController
from engine.services.db import update_domain_status, get_domains_id, get_domains, get_domain, get_domain_status, \
    get_history_domain, get_all_hypervisor_status
from engine.services.evaluators.evaluator_interface import EvaluatorInterface
from engine.services.log import eval_log

class UXEval(EvaluatorInterface):
    def __init__(self, user_id, id_pool, dd, templates, hyps, params):
        self.user_id = user_id
        self.id_pool = id_pool
        self.defined_domains = dd
        self.templates = templates
        self.hyps = hyps
        self.params = params
        self.domains_percent_increment = 25

    def run(self):
        data = {}
        self._calcule_ux()
        self._start_domains()

        return data

    def _calcule_ux(self):
        """
        Calcule average ux for each template on each hyp.
        :return:
        """
        for t in self.templates:
            domain = get_domains(self.user["id"], origin=t['id'])[0]
            self.templates[t['id']]['ux'] = {}
            for hyp in self.hyps:
                update_domain_force_hyp(domain['id'], hyp.id)
                update_domain_status('Starting', id)
                i = 0
                while ((get_domain_status(domain['id'])=="Starting") or i < 10):
                    sleep(1)
                    i += 1
                i = 0
                while(self._is_started(domain['id']) or i < 10):
                    sleep(1)
                    i+=1
                EvalController.stop_domains(self.user["id"], self.params["STOP_SLEEP_TIME"])
                self._calcule_ux_domain(domain['id'], hyp.id, t['id'])
            eval_log.debug(self.templates[t['id']]['ux'])

    def _is_started(self, domain_id):
        status = get_domain_status(domain_id)
        return status == "Started"


    def _calcule_ux_domain(self, domain_id, hyp_id, template_id):
        hd = get_history_domain(domain_id)
        start = hd[2]['when']
        stop = hd[0]['when']
        format_time = "%Y-%b-%d %H:%M:%S.%f"
        start_time = time.mktime(time.strptime(start, format_time))
        stop_time = time.mktime(time.strptime(stop, format_time))
        execution_time = (start_time-stop_time)/1e3 #1000
        status = get_all_hypervisor_status(hyp_id, start=start_time, end=stop_time)
        cpu_idle = []
        cpu_iowait = []
        for s in status:
            cpu_idle.append(s["cpu_percent"]["idle"])
            cpu_iowait.append(s["cpu_percent"]["iowait"])
        ux = {"cpu_idle":{"max":max(cpu_idle), "min":min(cpu_idle), "mean":mean(cpu_idle)},
              "cpu_iowait": {"max": max(cpu_iowait), "min": min(cpu_iowait), "mean": mean(cpu_iowait)}}
        self.templates[template_id]['ux'][hyp_id] = ux


    def _start_domains(self):
        data = {}
        return data