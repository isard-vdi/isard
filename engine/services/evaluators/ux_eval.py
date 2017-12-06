"""
UX Evaluator.
Must be called from EvalController
"""
import time
from math import floor
from pprint import pformat
from statistics import mean, stdev
from threading import Thread
from time import sleep

import graphyte
import numpy as np

from engine.controllers.eval_controller import EvalController
from engine.services.db import update_domain_status, get_domains, get_domain_status, \
    update_domain_force_hyp, get_domain
from engine.services.evaluators.evaluator_interface import EvaluatorInterface
from engine.services.log import eval_log

INITIAL_UX = {'hdani1': {'cpu_hyp_iowait': {'max': 0.0,
                                            'mean': 0.0,
                                            'min': 0.0,
                                            'stdev': 0.0},
                         'cpu_hyp_usage': {'max': 84.16,
                                           'mean': 55.218,
                                           'min': 50.49,
                                           'stdev': 10.42257038034924},
                         'cpu_usage': {'max': 1.64,
                                       'mean': 1.0822222222222222,
                                       'min': 1.0,
                                       'stdev': 0.21075920963138106},
                         'execution_time': 11.059932470321655,
                         'performance': 4.61,
                         'ram_hyp_usage': {'max': 11.09,
                                           'mean': 8.125,
                                           'min': 6.98,
                                           'stdev': 1.6846578947140045}},
              'hdani2': {'cpu_hyp_iowait': {'max': 0.0,
                                            'mean': 0.0,
                                            'min': 0.0,
                                            'stdev': 0.0},
                         'cpu_hyp_usage': {'max': 79.4,
                                           'mean': 54.99,
                                           'min': 50.75,
                                           'stdev': 8.819305843180379},
                         'cpu_usage': {'max': 1.57,
                                       'mean': 1.0744444444444445,
                                       'min': 1.0,
                                       'stdev': 0.1863539046485954},
                         'execution_time': 11.058387041091919,
                         'performance': 4.61,
                         'ram_hyp_usage': {'max': 11.08,
                                           'mean': 8.029,
                                           'min': 7.07,
                                           'stdev': 1.4524114048329726}},
              'hdani3': {'cpu_hyp_iowait': {'max': 0.17,
                                            'mean': 0.017,
                                            'min': 0.0,
                                            'stdev': 0.053758720222862454},
                         'cpu_hyp_usage': {'max': 20.59,
                                           'mean': 17.911,
                                           'min': 16.86,
                                           'stdev': 1.3919247265726855},
                         'cpu_usage': {'max': 1.13,
                                       'mean': 1.0344444444444445,
                                       'min': 1.0,
                                       'stdev': 0.04530759073022727},
                         'execution_time': 11.057267427444458,
                         'performance': 4.61,
                         'ram_hyp_usage': {'max': 4.39,
                                           'mean': 3.341,
                                           'min': 3.06,
                                           'stdev': 0.45969675995280956}},
              'hdani4': {'cpu_hyp_iowait': {'max': 0.12,
                                            'mean': 0.012,
                                            'min': 0.0,
                                            'stdev': 0.03794733192202055},
                         'cpu_hyp_usage': {'max': 20.39,
                                           'mean': 14.315999999999999,
                                           'min': 12.61,
                                           'stdev': 2.4264661089283277},
                         'cpu_usage': {'max': 1.5,
                                       'mean': 1.0855555555555556,
                                       'min': 1.01,
                                       'stdev': 0.15828069300384612},
                         'execution_time': 11.053992748260498,
                         'performance': 4.61,
                         'ram_hyp_usage': {'max': 3.42,
                                           'mean': 2.645,
                                           'min': 2.4,
                                           'stdev': 0.365612119906086}}}


class UXEval(EvaluatorInterface):
    def __init__(self, user_id, id_pool, dd, templates, hyps, params):
        self.name = "ux"
        graphyte.init('grafana', prefix='isard-eval.{}'.format(self.name))
        self.user_id = user_id
        self.id_pool = id_pool
        self.defined_domains = dd
        self.templates = templates
        self.hyps = hyps
        self.params = params
        self.steps = 2  # How many steps will start domains
        self.real_stop = False  # Wait for auto stop domain
        self.time_to_stop = 15  # Force to stop after X seconds
        self.ux = {}  # one key for each template
        self.names = ["ram_hyp_usage", "cpu_hyp_usage", "cpu_hyp_iowait", "cpu_usage"]
        self.statistics = ["max", "min", "mean", "stdev"]
        self.inc_statistics = ["mean", "stdev"]
        self.calcule_ux = True
        self.data_ux_names = ["execution_time", "inc_execution_time", "performance"]
        self._init_data_ux_names()
        self.ux_values = {"execution_time": {"min": 0,
                                             "max": 30,
                                             "weigth": 50,
                                             "unit": "percent"},
                          "cpu_hyp_iowait_stdev": {"min": 0,
                                                   "max": 30,
                                                   "weigth": 50,
                                                   "unit": "percent"}
                          }

    def _init_data_ux_names(self):
        for name in self.names:
            for s in self.statistics:
                self.data_ux_names.append(name + "_" + s)
        for name in self.names:
            for s in self.inc_statistics:
                self.data_ux_names.append("inc" + "_" + name + "_" + s)
        eval_log.info("Data UX Names: {}".format(self.data_ux_names))

    def run(self):
        data = {}
        self._calcule_ux()
        data["initial_ux"] = self.ux
        data.update(self._start_domains())
        eval_log.debug("FINAL: {}".format(pformat(data)))
        return data

    def _calcule_ux(self):
        """
        Calcule initial ux for each template on each hyp.
        :return:
        """
        for t in self.templates:
            domains = get_domains(self.user_id, origin=t['id'])
            if self.calcule_ux:
                if len(domains) >= len(self.hyps):  # Enought domains for run in parallel?
                    self._initial_ux_parallel(t['id'], domains)
                else:
                    self._initial_ux_sequencial(t['id'], domains[0]['id'])
            else:
                self.ux[t['id']] = INITIAL_UX

            eval_log.debug("INITIAL_UX: {}".format(pformat(self.ux[t['id']])))

    def _initial_ux_parallel(self, template_id, domains):
        self.ux[template_id] = {}
        threads = [None] * len(self.hyps)
        results = [None] * len(self.hyps)
        for i in range(len(self.hyps)):
            domain_id = domains[i]['id']
            hyp = self.hyps[i]
            hyp.launch_eval_statistics()
            eval_log.info(
                "Calculing ux for template: {} in hypervisor {}. Domain: {}".format(template_id, hyp.id, domain_id))
            update_domain_force_hyp(domain_id, hyp.id)
            threads[i] = Thread(target=self._get_stats_background, args=(domain_id, results, i, hyp))
            threads[i].start()
        for i in range(len(self.hyps)):
            threads[i].join()
            hyp = self.hyps[i]
            hyp.stop_eval_statistics()
            stats, et = results[i]
            self.ux[template_id][hyp.id] = self._calcule_ux_domain(stats, et, hyp.cpu_power)
            domain_id = domains[i]['id']
            update_domain_force_hyp(domain_id, '')  # Clean force_hyp

    def _initial_ux_sequencial(self, template_id, domain_id):
        self.ux[template_id] = {}
        for hyp in self.hyps:
            eval_log.info("Calculing ux for template: {} in hypervisor {}".format(t['id'], hyp.id))
            update_domain_force_hyp(domain_id, hyp.id)
            update_domain_status('Starting', domain_id)
            hyp.launch_eval_statistics()
            sleep(2)
            self._wait_starting(domain_id)
            stats, et = self._wait_stop(domain_id, hyp)
            hyp.stop_eval_statistics()
            sleep(2)
            self.ux[template_id][hyp.id] = self._calcule_ux_domain(stats, et, hyp.cpu_power)
        update_domain_force_hyp(domain_id, '')  # Clean force_hyp

    def _get_stats_background(self, domain_id, results, i, hyp):
        update_domain_status('Starting', domain_id)
        self._wait_starting(domain_id)
        stats, et = self._wait_stop(domain_id, hyp)
        results[i] = (stats, et)

    def _calcule_ux_domain(self, stats, et, cpu_power):
        # eval_log.debug("STATS: {}".format(stats))
        # ["ram_hyp_usage", "cpu_hyp_usage", "cpu_hyp_iowait", "cpu_usage"]
        a = np.array(stats)
        ram_hyp_usage = list(filter(None.__ne__, list(a[:, 0])))
        cpu_hyp_usage = list(filter(None.__ne__, list(a[:, 1])))
        cpu_hyp_iowait = list(filter(None.__ne__, list(a[:, 2])))
        cpu_usage = list(filter(None.__ne__, list(a[:, 3])))
        performance = round(et / cpu_power, 2)
        ux = {
            "execution_time": et,
            "performance": performance,
            "ram_hyp_usage": self._statistics(ram_hyp_usage),
            "cpu_hyp_usage": self._statistics(cpu_hyp_usage),
            "cpu_hyp_iowait": self._statistics(cpu_hyp_iowait),
            "cpu_usage": self._statistics(cpu_usage),
        }
        # eval_log.debug("UX: {}".format(ux))
        return ux

    def _statistics(self, list):
        # sd = stdev(list) if len(list) >= 2 else 0
        return {"max": max(list), "min": min(list), "mean": mean(list), "stdev": stdev(list)}

    def _start_domains(self):
        for hyp in self.hyps:
            hyp.launch_eval_statistics()

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
                domain_id = domains_ids[i]
                threads[i] = Thread(target=self._calcule_ux_background, args=(domain_id, results, i))
                threads[i].start()
                i += 1

            for i in range(len(threads)):
                threads[i].join()
            data_results = self._analyze_step_results(results)
            total_results.append(data_results["total"])
            data["step_{}".format(step)] = data_results
            # eval_log.debug("RESULTS: {}".format(pformat(results)))

            if start_domains < total_domains and start_domains + step_domains > total_domains:
                start_domains = total_domains
            else:
                start_domains += step_domains
            sleep(10)  # Relaxing time
            step += 1

        for hyp in self.hyps:
            hyp.stop_eval_statistics()
        data["total"] = self._analyze_total_results(total_results)
        return data

    def _calcule_ux_background(self, domain_id, results, thread_id):
        eval_log.info("_calcule_ux_background: domain:{}, thread_id: {}".format(domain_id, thread_id))
        # Start
        update_domain_status('Starting', domain_id)
        self._wait_starting(domain_id)

        # Get hyp_id where is running
        hyp_id, hyp, template_id = self._get_hyp_domain_running(domain_id)
        eval_log.info(
            "_calcule_ux_background: domain:{}, thread_id: {}, hyp_id: {}".format(domain_id, thread_id, hyp_id))
        # Wait until stop
        stats, et = self._wait_stop(domain_id, hyp)

        # Calcule domain ux
        ux = self._calcule_ux_domain(stats, et, hyp.cpu_power)
        graphyte.send(template_id + '.execution_time', ux["execution_time"])
        graphyte.send(template_id + '.performance', ux["performance"])
        # eval_log.debug("UX: domain_id: {}, hyp_id:{} , pformat(ux): {}".format(domain_id, hyp_id, pformat(ux)))

        # Get increment data: actual/initial
        initial_ux = self.ux[template_id][hyp_id]
        increment = self._get_inc(ux, initial_ux)
        graphyte.send(hyp_id + '.inc_hyp_cpu_usage', increment["cpu_hyp_usage"]["mean"])
        graphyte.send(hyp_id + '.inc_hyp_cpu_iowait', increment["cpu_hyp_iowait"]["mean"])
        # Calcule some data
        data = self._calcule_data_from_ux(domain_id, hyp_id, template_id, ux, increment)

        results[thread_id] = data

    def _analyze_step_results(self, results):
        results = [r for r in results if r]  # Remove None's, produced by errors
        a = np.array(results)
        eval_log.debug("results_analyze_results: {}".format(a))
        data_results = {}
        data_results["total"] = list(np.round(np.mean(a[:, 3:-1].astype(np.float), axis=0), 2))
        # eval_log.debug(
        #     "total_analyze_results: {}".format(list(np.round(np.mean(a[:, 2:-1].astype(np.float), axis=0), 2))))
        for t in self.templates:
            data_results[t['id']] = {}
            for hyp in self.hyps:
                c = np.where((a[:, 1] == hyp.id) & (a[:, 2] == t['id']))  # Query rows by hyp_id and template_id
                tmp = a[c]
                if len(tmp) > 0:
                    hyp_stats = list(np.round(np.mean(tmp[:, 3:-1].astype(np.float), axis=0), 2))
                    statistics_names = ["inc_execution_time", "execution_time",
                                        "ram_hyp_usage_mean", "inc_ram_hyp_usage_mean",
                                        "cpu_hyp_usage_mean", "inc_cpu_hyp_usage_mean"]
                    data_results[t['id']][hyp.id] = {sn: hyp_stats[self.data_ux_names.index(sn)] for sn in
                                                     statistics_names}
                    data_results[t['id']][hyp.id]["inc_execution_time_percent"] = round((hyp_stats[1] - 1) * 100, 2)
        # eval_log.debug("TOTAL NP: {}".format(data_results["total"]))
        return data_results

    def _analyze_total_results(self, results):
        # eval_log.debug("_analyze_total_results: {}".format(pformat(results)))
        a = np.array(results)
        stats = list(np.round(np.mean(a, axis=0), 2))
        return stats

    def _wait_stop(self, domain_id, hyp):
        stats = []
        i = 0
        start_time = time.time()
        while (get_domain_status(domain_id) == "Started" and (self.real_stop or i < self.time_to_stop)):
            tmp = []
            s = hyp.get_ux_eval_statistics(domain_id)
            # eval_log.debug("UX Stats: {}".format(pformat(s)))
            for name in self.names:
                value = s.get(name)
                tmp.append(value)
                if value:
                    graphyte.send(hyp.id + '.' + name, value)
            # eval_log.debug(tmp)
            stats.append(tmp)
            # eval_log.debug("Domain {} is started and i : {}".format(domain_id, i))
            sleep(1)
            i += 1
        if get_domain_status(domain_id) == "Started":
            update_domain_status('Stopping', domain_id, hyp.id)  # Force stop
            i = 0
            while ((get_domain_status(domain_id) == "Stopping") and i < 10):
                sleep(1)
                i += 1
        execution_time = time.time() - start_time
        # eval_log.debug(stats)
        return stats, execution_time

    def _wait_starting(self, domain_id):
        i = 0
        while ((get_domain_status(domain_id) == "Starting") and i < 10):
            sleep(1)
            i += 1

    def _get_hyp_domain_running(self, domain_id):
        d = get_domain(domain_id)
        assert d['status'] == "Started"
        hyp_id = d['history_domain'][0]['hyp_id']
        hyp = list(filter(lambda h: h.id == hyp_id, self.hyps))[0]
        if not hyp_id:
            eval_log.debug("History domain: {}", d['history_domain'])
        template_id = d['create_dict']['origin']
        return hyp_id, hyp, template_id

    def _get_inc(self, ux, initial_ux):
        inc_et = max(round(ux["execution_time"] / initial_ux["execution_time"], 2), 1)
        increment = {
            "execution_time": inc_et,
            "execution_time_percent": round((inc_et - 1) * 100, 2)
        }
        for name in self.names:
            increment[name] = {}
            for stat in self.inc_statistics:
                initial = 0.01 if initial_ux[name][stat] == 0 else initial_ux[name][stat]
                inc = max(round(ux[name][stat] / initial, 2), 1)
                increment[name][stat] = inc
                increment[name][stat + "_percent"] = round((inc - 1) * 100, 2)
        return increment

    def _calcule_data_from_ux(self, domain_id, hyp_id, template_id, ux, increment):
        data = [domain_id, hyp_id, template_id,
                ux["execution_time"], increment["execution_time"], ux["performance"]]
        for name in self.names:
            d = []
            for s in self.statistics:
                d.append(ux[name][s])
            data.extend(d)
        for name in self.names:
            d = []
            for s in self.inc_statistics:
                d.append(increment[name][s])
            data.extend(d)
        score = self._ux_score(increment)
        data.append(score)
        eval_log.debug("domain_id: {}, hyp_id: {}, score: {}".format(domain_id, hyp_id, score))
        return data

    def _ux_score(self, increment):
        # eval_log.debug(increment)
        # eval_log.debug(self.ux_values)
        score_execution_time = (1 - ((increment["execution_time_percent"] / (self.ux_values["execution_time"]["max"] -
                                                                             self.ux_values["execution_time"][
                                                                                 "min"])))) * (
                                   self.ux_values["execution_time"]["weigth"] / 100)

        score_cpu_hyp_iowait_stdev = (1 - (
            (increment["cpu_hyp_iowait"]["stdev_percent"] / (
                self.ux_values["cpu_hyp_iowait_stdev"]["max"] -
                self.ux_values["cpu_hyp_iowait_stdev"][
                    "min"])))) * (
                                         self.ux_values["cpu_hyp_iowait_stdev"]["weigth"] / 100)
        score = score_execution_time + score_cpu_hyp_iowait_stdev
        return score * 10
