from math import floor
from statistics import mean, stdev
import datetime
from time import sleep
from pprint import pformat
from threading import Thread

from engine.controllers.eval_controller import EvalController
from engine.services.db import update_domain_status, get_domains, get_domain_status, \
    get_history_domain, get_all_hypervisor_status, update_domain_force_hyp, get_domain
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
        self.steps = 2  # How many steps will start domains
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
            for hyp in self.hyps:
                eval_log.info("Calculing ux for template: {} in hypervisor {}".format(t['id'], hyp.id))
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
                self.ux[t['id']][hyp.id] = self._calcule_ux_domain(domain['id'], hyp.id)

            eval_log.debug("INITIAL_UX: {}".format(pformat(self.ux[t['id']])))

    def _is_started(self, domain_id):
        status = get_domain_status(domain_id)
        return status == "Started"

    def _calcule_ux_domain(self, domain_id, hyp_id):
        hd = get_history_domain(domain_id)
        eval_log.debug("HISTORY_DOMAIN: {}".format(pformat(hd[:3])))
        start = hd[2]['when']
        stop = hd[0]['when']
        format_time = "%Y-%b-%d %H:%M:%S.%f"
        start_time = datetime.datetime.strptime(start, format_time)
        stop_time = datetime.datetime.strptime(stop, format_time)
        execution_time = round((stop_time - start_time).total_seconds(), 2)
        eval_log.debug("EXECUTION TIME of domain {} in hypervisor {}: {}".format(domain_id, hyp_id, execution_time))
        status = get_all_hypervisor_status(hyp_id, start=start_time.timestamp(), end=stop_time.timestamp())
        cpu_idle = []
        cpu_iowait = []
        for s in status:
            if s["cpu_percent"]:
                cpu_idle.append(s["cpu_percent"]["idle"])
                cpu_iowait.append(s["cpu_percent"]["iowait"])
        ux = {"execution_time": execution_time,
              "cpu_idle": {"max": max(cpu_idle), "min": min(cpu_idle), "mean": mean(cpu_idle),
                           "stdev": stdev(cpu_idle)},
              "cpu_iowait": {"max": max(cpu_iowait), "min": min(cpu_iowait), "mean": mean(cpu_iowait),
                             "stdev": stdev(cpu_iowait)}}
        eval_log.debug(ux)
        return ux

    def _start_domains(self):
        data = {}
        domains_id_list = EvalController.get_domains_id_randomized(self.user_id, self.id_pool, self.defined_domains,
                                                                   self.templates)
        total_domains = len(domains_id_list)
        start_domains = step_domains = floor(total_domains / self.steps)
        while (start_domains <= total_domains):
            eval_log.info("Starting {} domains for ux eval".format(start_domains))
            domains_ids = domains_id_list[:start_domains]
            threads = [None] * start_domains
            results = [None] * start_domains
            i = 0
            while (i < start_domains):
                domains_id = domains_ids[i]
                threads[i] = Thread(target=self._calcule_ux_background, args=(domains_id, results, i))
                threads[i].start()
                i += 1

            for i in range(len(threads)):
                threads[i].join()
            eval_log.debug("RESULTS: {}".format(pformat(results)))

            if start_domains < total_domains and start_domains + step_domains > total_domains:
                start_domains = total_domains
            else:
                start_domains += step_domains
            sleep(10)  # Realxing time

        return data

    def _calcule_ux_background(self, domain_id, results, thread_id):
        eval_log.info("_calcule_ux_background: domain:{}, thread_id: {}".format(domain_id, thread_id))
        # Start
        update_domain_status('Starting', domain_id)
        # Get hyp_id where is running
        i = 0
        while ((get_domain_status(domain_id) == "Starting") and i < 10):
            sleep(1)
            i += 1
        d = get_domain(domain_id)
        assert d['status'] == "Started"
        hyp_id = d['history_domain'][0]['hyp_id']
        if not hyp_id:
            eval_log.debug("History domain: {}", d['history_domain'])
        template_id = d['create_dict']['origin']
        # Wait until stop
        i = 0
        while (self._is_started(domain_id) and i < 10):
            # eval_log.debug("Domain {} is started and i : {}".format(domain_id, i))
            sleep(1)
            i += 1
        if get_domain_status(domain_id) == "Started":
            update_domain_status('Stopping', domain_id, hyp_id)  # Force stop
            i = 0
            while ((get_domain_status(domain_id) == "Stopping") and i < 10):
                sleep(1)
                i += 1
        # Calcule domain ux
        ux = self._calcule_ux_domain(domain_id, hyp_id)
        eval_log.debug("UX: domain_id: {}, hyp_id:{} , pformat(ux): {}".format(domain_id, hyp_id, pformat(ux)))
        # Compare ux with initial ux
        initial_ux = self.ux[template_id][hyp_id]
        data = {'domain_id': domain_id,
                'hyp_id': hyp_id,
                'initial_ux': initial_ux,
                'real_ux': ux}
        results[thread_id] = data
