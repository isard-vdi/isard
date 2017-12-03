from math import floor
from statistics import mean, stdev
import datetime
import numpy as np
from time import sleep
from pprint import pformat
from threading import Thread

from engine.controllers.eval_controller import EvalController
from engine.services.db import update_domain_status, get_domains, get_domain_status, \
    get_history_domain, get_all_hypervisor_status, update_domain_force_hyp, get_domain, get_all_domain_status
from engine.services.evaluators.evaluator_interface import EvaluatorInterface
from engine.services.log import eval_log

INITIAL_UX = {'hdani1': {'cpu_idle': {'max': 100,
                                      'mean': 99.75641961852861,
                                      'min': 47.568,
                                      'stdev': 2.0159202785773984},
                         'cpu_iowait': {'max': 0.495,
                                        'mean': 0.0012068119891008174,
                                        'min': 0,
                                        'stdev': 0.014845970586484016},
                         'cpu_usage': {'max': 0.048348400062018175,
                                       'mean': 0.007547425720455162,
                                       'min': 0,
                                       'stdev': 0.016614037929014606},
                         'execution_time': 10.81,
                         'performance': 4.5},
              'hdani2': {'cpu_idle': {'max': 100,
                                      'mean': 99.7663840283456,
                                      'min': 45.73,
                                      'stdev': 1.827776326242979},
                         'cpu_iowait': {'max': 2.37,
                                        'mean': 0.002293540474243663,
                                        'min': 0,
                                        'stdev': 0.05007970979203264},
                         'cpu_usage': {'max': 0.048348400062018175,
                                       'mean': 0.008490853935512056,
                                       'min': 0,
                                       'stdev': 0.017501534467715258},
                         'execution_time': 10.92,
                         'performance': 4.55},
              'hdani3': {'cpu_idle': {'max': 100,
                                      'mean': 99.91376927267774,
                                      'min': 63.258,
                                      'stdev': 0.9335489863770705},
                         'cpu_iowait': {'max': 0.896,
                                        'mean': 0.001030781803323345,
                                        'min': 0,
                                        'stdev': 0.022803374204505084},
                         'cpu_usage': {'max': 0.048348400062018175,
                                       'mean': 0.0067926831484096456,
                                       'min': 0,
                                       'stdev': 0.015844653223508334},
                         'execution_time': 10.86,
                         'performance': 4.53},
              'hdani4': {'cpu_idle': {'max': 100,
                                      'mean': 99.92492502726282,
                                      'min': 86.559,
                                      'stdev': 0.594055439659702},
                         'cpu_iowait': {'max': 0.147,
                                        'mean': 0.0003214285714285714,
                                        'min': 0,
                                        'stdev': 0.004392460621570733},
                         'cpu_usage': {'max': 0.048348400062018175,
                                       'mean': 0.009703833069156636,
                                       'min': 0,
                                       'stdev': 0.018537044585853736},
                         'execution_time': 10.82,
                         'performance': 4.51}}


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
        self.names = ["cpu_idle", "cpu_iowait", "cpu_usage"]
        self.statistics = ["mean", "stdev"]
        self.calcule_ux = True

    def run(self):
        data = {}
        self._calcule_ux()
        data["ux"] = self.ux
        data.update(self._start_domains())
        eval_log.debug("FINAL: {}".format(pformat(data)))
        return data

    def _calcule_ux(self):
        """
        Calcule average ux for each template on each hyp.
        :return:
        """
        for t in self.templates:
            domain = get_domains(self.user_id, origin=t['id'])[0]
            if self.calcule_ux:
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
                    self.ux[t['id']][hyp.id] = self._calcule_ux_domain(domain['id'], hyp.id, hyp.cpu_power)
            else:
                self.ux[t['id']] = INITIAL_UX

            eval_log.debug("INITIAL_UX: {}".format(pformat(self.ux[t['id']])))

    def _is_started(self, domain_id):
        status = get_domain_status(domain_id)
        return status == "Started"

    def _calcule_ux_domain(self, domain_id, hyp_id, hyp_cpu_power):
        hd = get_history_domain(domain_id)
        #eval_log.debug("HISTORY_DOMAIN: {}".format(pformat(hd[:3])))
        start = hd[2]['when']
        stop = hd[0]['when']
        format_time = "%Y-%b-%d %H:%M:%S.%f"
        start_time = datetime.datetime.strptime(start, format_time)
        stop_time = datetime.datetime.strptime(stop, format_time)
        execution_time = round((stop_time - start_time).total_seconds(), 2)
        performance = round(execution_time / hyp_cpu_power, 2)
        #eval_log.debug("EXECUTION TIME of domain {} in hypervisor {}: {}".format(domain_id, hyp_id, execution_time))
        hyp_status = get_all_hypervisor_status(hyp_id, start=start_time.timestamp(), end=stop_time.timestamp())
        domain_status = get_all_domain_status(domain_id, start=start_time.timestamp(), end=stop_time.timestamp())
        cpu_idle = []
        cpu_iowait = []
        cpu_usage = []
        for s in hyp_status:
            if s["cpu_percent"]:
                cpu_idle.append(s["cpu_percent"]["idle"])
                cpu_iowait.append(s["cpu_percent"]["iowait"])
        if len(domain_status) == 0:
            eval_log.warn("len(domain_status) == 0  {}, {}".format(domain_id, hyp_id))
        for s in domain_status:
            cu = s["status"].get("cpu_usage")
            if cu:
                if cu < 0:
                    cu = 0
                cpu_usage.append(cu)
            else:
                eval_log.warn("NOT CU: {}, {}".format(domain_id, hyp_id))
        ux = {"execution_time": execution_time,
              "cpu_idle": self._statistics(cpu_idle),
              "cpu_iowait": self._statistics(cpu_iowait),
              "cpu_usage": self._statistics(cpu_usage),
              "performance": performance
              }
        #eval_log.debug(ux)
        return ux

    def _statistics(self, list):
        return {"max": max(list), "min": min(list), "mean": mean(list), "stdev": stdev(list)}

    def _start_domains(self):
        data = {}
        domains_id_list = EvalController.get_domains_id_randomized(self.user_id, self.id_pool, self.defined_domains,
                                                                   self.templates)
        total_domains = len(domains_id_list)
        start_domains = step_domains = floor(total_domains / self.steps)
        step = 0
        total_results = []
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
            data_results = self._analyze_results(results)
            total_results.append(data_results["total"])
            data["step_{}".format(step)] = data_results
            eval_log.debug("RESULTS: {}".format(pformat(results)))

            if start_domains < total_domains and start_domains + step_domains > total_domains:
                start_domains = total_domains
            else:
                start_domains += step_domains
            sleep(10)  # Realxing time
            step += 1

        data["total"] = self._analyze_total_results(total_results)
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
        hyp = list(filter(lambda h: h.id == hyp_id, self.hyps))[0]
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
        ux = self._calcule_ux_domain(domain_id, hyp_id, hyp.cpu_power)
        #eval_log.debug("UX: domain_id: {}, hyp_id:{} , pformat(ux): {}".format(domain_id, hyp_id, pformat(ux)))
        # Compare ux with initial ux
        initial_ux = self.ux[template_id][hyp_id]
        inefficiency = {"execution_time": round(ux["execution_time"] / initial_ux["execution_time"], 2)}
        for name in self.names:
            inefficiency[name] = {}
            for stat in self.statistics:
                inefficiency[name][stat] = round(ux[name][stat] / initial_ux[name][stat], 2)
        # ["domain_id","hyp_id","execution_time","inc_execution_time","performance",
        # "cpu_idle_max", "cpu_idle_min", "cpu_idle_mean", "cpu_idle_stdev",
        # "cpu_iowait_max", "cpu_iowait_min", "cpu_iowait_mean", "cpu_iowait_stdev",
        # "cpu_usage_max", "cpu_usage_min", "cpu_usage_mean", "cpu_usage_stdev",
        # "inc_cpu_idle_mean", "inc_cpu_idle_stdev",
        # "inc_cpu_iowait_mean", "inc_cpu_iowait_stdev",
        # "inc_cpu_usage_mean", "inc_cpu_usage_stdev",
        # ]

        data = [domain_id, hyp_id, ux["execution_time"], inefficiency["execution_time"], ux["performance"]]
        statistics = ["max", "min", "mean", "stdev"]
        for name in self.names:
            d = []
            for s in statistics:
                d.append(ux[name][s])
            data.extend(d)
        statistics = ["mean", "stdev"]
        for name in self.names:
            d = []
            for s in statistics:
                d.append(inefficiency[name][s])
            data.extend(d)
        results[thread_id] = data

    def _analyze_results(self, results):
        results = [r for r in results if r] # Remove None's, produced by errors
        a = np.array(results)
        #eval_log.debug("results_analyze_results: {}".format(a))
        data_results = {}
        data_results["total"] = list(np.round(np.mean(a[:, 2:-1].astype(np.float), axis=0), 2))
        for hyp in self.hyps:
            c = np.where((a[:, 1] == hyp.id))  # Query rows by hyp_id
            tmp = a[c]
            eval_log.debug("TMP: {}".format(tmp))
            hyp_stats = list(np.round(np.mean(tmp[:, 2:-1].astype(np.float), axis=0), 2))
            data_results[hyp.id] = hyp_stats
        #eval_log.debug("TOTAL NP: {}".format(data_results["total"]))
        return data_results

    def _analyze_total_results(self, results):
        #eval_log.debug("_analyze_total_results: {}".format(pformat(results)))
        a = np.array(results)
        stats = list(np.round(np.mean(a, axis=0), 2))
        return stats
