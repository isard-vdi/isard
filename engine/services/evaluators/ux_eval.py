"""
UX Evaluator.
Must be called from EvalController
"""
import time
from math import floor, ceil
from pprint import pformat
from statistics import mean, stdev
from threading import Thread
from time import sleep

import graphyte
import numpy as np

from engine.config import CARBON
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
        self.sender = graphyte.Sender(CARBON['server'], prefix='isard-eval.{}'.format(self.name), port=CARBON['port'])
        self.user_id = user_id
        self.id_pool = id_pool
        self.defined_domains = dd
        self.templates = templates
        self.hyps = hyps
        self.params = params
        self.steps = 3  # How many steps will start domains
        self.real_stop = True  # Wait for auto stop domain
        self.time_to_stop = 15  # Force to stop after X seconds
        self.initial_ux = {}  # one key for each template
        self.names = ["ram_hyp_usage", "cpu_hyp_usage", "cpu_hyp_iowait", "cpu_usage"]
        self.statistics = ["max", "min", "mean", "stdev"]
        self.inc_statistics = ["mean", "stdev"]
        self.calcule_ux = True
        self.data_ux_names = ["execution_time", "inc_execution_time", "performance"]
        self._init_data_ux_names()
        self.ux_scorers = {"execution_time": {"min": 0,
                                             "max": 30,
                                             "weight": 60,
                                             "unit": "percent"},
                          "cpu_hyp_iowait_stdev": {"min": 0,
                                                   "max": 30,
                                                   "weight": 20,
                                                   "unit": "percent"},
                          "cpu_usage_mean": {"min": 0,
                                             "max": 30,
                                             "weight": 20,
                                             "unit": "percent"}
                           }
        self.total_weights_ux_scorers = sum(v['weight'] for v in self.ux_scorers.values())

    def _init_data_ux_names(self):
        for name in self.names:
            for s in self.statistics:
                self.data_ux_names.append(name + "_" + s)
        for name in self.names:
            for s in self.inc_statistics:
                self.data_ux_names.append("inc" + "_" + name + "_" + s)
                self.data_ux_names.append("inc" + "_" + name + "_" + s + "_percent")
        eval_log.info("Data UX Names: {}".format(self.data_ux_names))

    def run(self):
        data = {}
        self._calcule_ux()
        data["initial_ux"] = self.initial_ux
        data.update(self._start_domains())
        # eval_log.debug("FINAL: {}".format(pformat(data)))
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
                self.initial_ux[t['id']] = INITIAL_UX

            eval_log.debug("INITIAL_UX: {}".format(pformat(self.initial_ux[t['id']])))

    def _initial_ux_parallel(self, template_id, domains):
        self.initial_ux[template_id] = {}
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
            if not results[i]:
                raise Exception("Need to reset")
            stats, et = results[i]
            self.initial_ux[template_id][hyp.id] = self._calcule_ux_domain(stats, et, hyp.cpu_power)
            domain_id = domains[i]['id']
            update_domain_force_hyp(domain_id, '')  # Clean force_hyp

    def _initial_ux_sequencial(self, template_id, domain_id):
        self.initial_ux[template_id] = {}
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
            self.initial_ux[template_id][hyp.id] = self._calcule_ux_domain(stats, et, hyp.cpu_power)
        update_domain_force_hyp(domain_id, '')  # Clean force_hyp

    def _get_stats_background(self, domain_id, results, i, hyp):
        update_domain_status('Starting', domain_id)
        self._wait_starting(domain_id)
        stats, et, stop_by_timeout = self._wait_stop(domain_id, hyp)
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

    ################# Main Function
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
            total_results.append([r[0] for r in results if r])
            data["step_{}".format(step)] = data_results
            if data_results["total"]["timeouts"] > ceil(data_results["total"]["n_domains"]/2):
                for hyp in self.hyps:
                    hyp.stop_eval_statistics()
                data["total"] = self._analyze_total_results(total_results)
                break
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
        # eval_log.info("_calcule_ux_background: domain:{}, thread_id: {}".format(domain_id, thread_id))
        # Start
        update_domain_status('Starting', domain_id)
        self._wait_starting(domain_id)

        # Get hyp_id where is running
        hyp_id, hyp, template_id = self._get_hyp_domain_running(domain_id)
        eval_log.info(
            "_calcule_ux_background: domain:{}, thread_id: {}, hyp_id: {}".format(domain_id, thread_id, hyp_id))
        # Wait until stop
        et = self.initial_ux[template_id][hyp_id]["execution_time"]
        et_inc_max = self.ux_scorers["execution_time"]["max"]
        timeout = et * (1 + et_inc_max/100)
        eval_log.info("TIMEOUT: {}, ET: {}".format(timeout, et))
        stats, et, stop_by_timeout = self._wait_stop(domain_id, hyp, timeout=timeout)

        # Calcule domain ux
        ux = self._calcule_ux_domain(stats, et, hyp.cpu_power)
        self.sender.send(template_id + '.execution_time', ux["execution_time"])
        self.sender.send(template_id + '.performance', ux["performance"])
        # eval_log.debug("UX: domain_id: {}, hyp_id:{} , pformat(ux): {}".format(domain_id, hyp_id, pformat(ux)))

        # Get increment data: actual/initial
        initial_ux = self.initial_ux[template_id][hyp_id]
        increment = self._get_inc(ux, initial_ux)
        self.sender.send(hyp_id + '.inc_hyp_cpu_usage', increment["cpu_hyp_usage"]["mean"])
        self.sender.send(hyp_id + '.inc_hyp_cpu_iowait', increment["cpu_hyp_iowait"]["mean"])
        # Calcule some data
        data = self._calcule_data_from_ux(domain_id, hyp_id, template_id, ux, increment)

        results[thread_id] = (data, stop_by_timeout)

    def _analyze_step_results(self, results_timeouts):
        results = [r[0] for r in results_timeouts if r]  # Remove None's, produced by errors
        timeouts = [r[1] for r in results_timeouts if r and r[1] is True]  # Get any True value
        a = np.array(results)
        eval_log.debug("results_analyze_results: {}".format(a))
        data_results = {}
        total = list(np.round(np.mean(a[:, 3:].astype(np.float), axis=0), 2))
        data_results["total"] = {"score": total[-1],
                                 "n_domains":len(results),
                                 "timeouts":len(timeouts)}
        # eval_log.debug(
        #     "total_analyze_results: {}".format(list(np.round(np.mean(a[:, 2:-1].astype(np.float), axis=0), 2))))
        for t in self.templates:
            data_results[t['id']] = {}
            for hyp in self.hyps:
                c = np.where((a[:, 1] == hyp.id) & (a[:, 2] == t['id']))  # Query rows by hyp_id and template_id
                tmp = a[c]
                if len(tmp) > 0:
                    hyp_stats = list(np.round(np.mean(tmp[:, 3:].astype(np.float), axis=0), 2))
                    statistics_names = ["inc_cpu_hyp_iowait_stdev_percent",
                                        "inc_cpu_usage_mean_percent",
                                        "inc_cpu_usage_stdev_percent"
                                        # "inc_execution_time", "execution_time",
                                        # "inc_hyp_cpu_iowait_stdev", "execution_time",
                                        # "ram_hyp_usage_mean", "inc_ram_hyp_usage_mean",
                                        # "cpu_hyp_usage_mean", "inc_cpu_hyp_usage_mean"
                                        ]
                    data_results[t['id']][hyp.id] = {sn: hyp_stats[self.data_ux_names.index(sn)] for sn in
                                                     statistics_names}
                    data_results[t['id']][hyp.id]["inc_execution_time_percent"] = round((hyp_stats[1] - 1) * 100, 2)
                    data_results[t['id']][hyp.id]["score"] = hyp_stats[-1]
        # eval_log.debug("TOTAL NP: {}".format(data_results["total"]))
        return data_results

    def _analyze_total_results(self, results):
        # eval_log.debug("_analyze_total_results: {}".format(pformat(results)))
        total = np.array(results[0])
        for i in range(1, len(results)):
            total = np.append(total, results[i], axis=0)
        eval_log.debug("TOTAL: {}".format(total))
        means = list(np.round(np.mean(total[:, 3:].astype(np.float), axis=0), 2))
        return {"score": means[-1]}

    def _wait_stop(self, domain_id, hyp, timeout=9999):
        stats = []
        i = 0
        start_time = time.time()
        while (get_domain_status(domain_id) == "Started"
               and (self.real_stop or i < self.time_to_stop)
               and i < timeout):
            tmp = []
            s = hyp.get_ux_eval_statistics(domain_id)
            # eval_log.debug("UX Stats: {}".format(pformat(s)))
            for name in self.names:
                value = s.get(name)
                tmp.append(value)
                if value:
                    self.sender.send(hyp.id + '.' + name, value)
            # eval_log.debug(tmp)
            stats.append(tmp)
            # eval_log.debug("Domain {} is started and i : {}".format(domain_id, i))
            sleep(1)
            i += 1

        if get_domain_status(domain_id) == "Started":
            update_domain_status('Stopping', domain_id, hyp.id)  # Force stop
            j = 0
            while ((get_domain_status(domain_id) == "Stopping") and j < 10):
                sleep(1)
                j += 1
        execution_time = time.time() - start_time
        stop_by_timeout = i >= timeout or execution_time > timeout
        eval_log.debug("Execution_time: {}, stop_by_time_out: {}, i_value: {}, timeout: {}".format(execution_time, stop_by_timeout, i, timeout))
        return stats, execution_time, stop_by_timeout

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
                d.append(increment[name][s + "_percent"])
            data.extend(d)
        score = self._ux_score(increment)
        data.append(score)
        # eval_log.debug("domain_id: {}, hyp_id: {}, score: {}".format(domain_id, hyp_id, score))
        names= ["domain_id", "hyp_id", "template_id", "execution_time", "inc_execution_time", "performance"]
        names.extend(self.data_ux_names)
        tmp = dict(zip(names, data))
        eval_log.debug("domain_ux_data: {}".format(tmp))
        return data

    def _ux_score(self, increment):
        total_score = 0
        for value in self.ux_scorers.keys():
            xv, vmax, vmin, wv = getattr(self, "_ux_score_" + value)(increment)  # Call scorer function
            score = (1 - min(xv / (vmax - vmin), 1)) * wv / self.total_weights_ux_scorers
            eval_log.debug("Partial_ Score ({}): {}".format(value, score))
            total_score += score
        return total_score * 10

    def _ux_score_execution_time(self, increment):
        xv = increment["execution_time_percent"]
        vmax = self.ux_scorers["execution_time"]["max"]
        vmin = self.ux_scorers["execution_time"]["min"]
        wv = self.ux_scorers["execution_time"]["weight"]
        return xv, vmax, vmin, wv

    def _ux_score_cpu_hyp_iowait_stdev(self, increment):
        xv = increment["cpu_hyp_iowait"]["stdev_percent"]
        vmax = self.ux_scorers["cpu_hyp_iowait_stdev"]["max"]
        vmin = self.ux_scorers["cpu_hyp_iowait_stdev"]["min"]
        wv = self.ux_scorers["cpu_hyp_iowait_stdev"]["weight"]
        return xv, vmax, vmin, wv

    def _ux_score_cpu_usage_mean(self, increment):
        xv = increment["cpu_usage"]["mean_percent"]
        vmax = self.ux_scorers["cpu_usage_mean"]["max"]
        vmin = self.ux_scorers["cpu_usage_mean"]["min"]
        wv = self.ux_scorers["cpu_usage_mean"]["weight"]
        return xv, vmax, vmin, wv
