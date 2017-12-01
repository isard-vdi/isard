from statistics import mean, stdev
import datetime
from time import sleep
from pprint import pformat

from engine.controllers.eval_controller import EvalController
from engine.services.db import update_domain_status, get_domains, get_domain_status, \
    get_history_domain, get_all_hypervisor_status, update_domain_force_hyp
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
        self.ux = {}  # one key for each template

    def run(self):
        data = {}
        self._calcule_ux()
        data["ux"] = self.ux
        self._start_domains()

        return data

    def _calcule_ux(self):
        """
        Calcule average ux for each template on each hyp.
        :return:
        """
        for t in self.templates:
            domain = get_domains(self.user_id, origin=t['id'])[0]
            self.ux[t['id']] = {}
            eval_log.info("Calculing ux for template: {} in hypervisors".format(t['id']))
            for hyp in self.hyps:
                update_domain_force_hyp(domain['id'], hyp.id)
                update_domain_status('Starting', domain['id'])
                i = 0
                while ((get_domain_status(domain['id']) == "Starting") and i < 10):
                    sleep(1)
                    i += 1
                i = 0
                while (self._is_started(domain['id']) and i < 10):
                    eval_log.debug("Domain {} is started and i : {}".format(domain['id'], i))
                    sleep(1)
                    i += 1
                EvalController.stop_domains(self.user_id, self.params["STOP_SLEEP_TIME"])
                self.ux[t['id']][hyp.id] = self._calcule_ux_domain(domain['id'], hyp.id, t['id'])

            eval_log.debug(pformat(self.ux[t['id']]))

    def _is_started(self, domain_id):
        status = get_domain_status(domain_id)
        return status == "Started"

    def _calcule_ux_domain(self, domain_id, hyp_id, template_id):
        hd = get_history_domain(domain_id)
        eval_log.debug("History domain of {}: {}".format(domain_id, hd))
        start = hd[2]['when']
        stop = hd[0]['when']
        format_time = "%Y-%b-%d %H:%M:%S.%f"
        start_time = datetime.datetime.strptime(start, format_time)
        stop_time = datetime.datetime.strptime(stop, format_time)
        execution_time = round((stop_time - start_time).total_seconds(), 2)
        status = get_all_hypervisor_status(hyp_id, start=start_time.timestamp(), end=stop_time.timestamp())
        cpu_idle = []
        cpu_iowait = []
        for s in status:
            if s["cpu_percent"]:
                cpu_idle.append(s["cpu_percent"]["idle"])
                cpu_iowait.append(s["cpu_percent"]["iowait"])
        ux = {"execution_time": execution_time,
              "cpu_idle": {"max": max(cpu_idle), "min": min(cpu_idle), "mean": mean(cpu_idle), "stdev":stdev(cpu_idle)},
              "cpu_iowait": {"max": max(cpu_iowait), "min": min(cpu_iowait), "mean": mean(cpu_iowait), "stdev":stdev(cpu_iowait)}}
        return ux

    def _start_domains(self):
        data = {}
        return data
