# Copyright 2018 the Isard-vdi project authors:
#      Alberto Larraz Dalmases
#      Josep Maria Viñolas Auquer
#      Daniel Criado Casas
# License: AGPLv3

"""
UX Evaluator.
Must be called from EvalController
"""
import time
from math import floor, ceil
from pprint import pformat
from random import randint
from statistics import mean, stdev
from threading import Thread
from time import sleep
from timeit import default_timer as timer
from traceback import format_exc

import graphyte
import numpy as np

from engine.config import GRAFANA
from engine.controllers.eval_controller import EvalController
from engine.services.db import update_domain_status, get_domains, get_domain_status, \
    update_domain_forced_hyp, get_domain
from engine.services.db.eval import get_eval_initial_ux, insert_eval_initial_ux
from engine.services.evaluators.evaluator_interface import EvaluatorInterface
from engine.services.log import logs


class UXEval(EvaluatorInterface):
    def __init__(self, user_id, id_pool, dd, templates, hyps, params):
        self.name = "ux"
        self.code = "RR_stress_launch_apps"
        self.sender = graphyte.Sender(GRAFANA['server'], prefix='isard-eval.{}'.format(self.name), port=GRAFANA['port'])
        self.user_id = user_id
        self.id_pool = id_pool
        self.defined_domains = dd
        self.templates = templates
        self.hyps = hyps
        self.params = params
        self.steps = 3  # How many steps will start domains
        self.initial_ux_iterations = 1
        self.real_stop = True  # Wait for auto stop domain
        self.time_to_stop = 15  # Force to stop after X seconds
        self.initial_ux = {}  # one key for each template
        self.names = ["ram_hyp_usage", "cpu_hyp_usage", "cpu_hyp_iowait", "cpu_usage"]
        self.statistics = ["max", "min", "mean", "stdev"]
        self.inc_statistics = ["mean", "stdev"]
        self.calcule_ux = True
        self.save_ux = True
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

    def run(self):
        data = {}
        self._calcule_ux()
        data["initial_ux"] = self.initial_ux
        data.update(self._start_domains())
        return data

    def _init_data_ux_names(self):
        for name in self.names:
            for s in self.statistics:
                self.data_ux_names.append(name + "_" + s)
        for name in self.names:
            for s in self.inc_statistics:
                self.data_ux_names.append("inc" + "_" + name + "_" + s)
                self.data_ux_names.append("inc" + "_" + name + "_" + s + "_percent")
                # logs.eval.info("Data UX Names: {}".format(self.data_ux_names))
    def _calcule_ux(self):
        """
        Calcule initial ux for each template on each hyp.
        :return:
        """
        if self.calcule_ux:
            for t in self.templates:
                domains = get_domains(self.user_id, origin=t['id'])
                if len(domains) >= len(self.hyps):  # Enought domains for run in parallel?
                    self._initial_ux_parallel(t['id'], domains)
                else:
                    self._initial_ux_sequencial(t['id'], domains[0]['id'])

                if self.save_ux:
                    initial_ux = {"id": self.code,
                                  "initial_ux": self.initial_ux}
                    insert_eval_initial_ux(initial_ux)
                logs.eval.debug("INITIAL_UX: {}".format(pformat(self.initial_ux[t['id']])))
            sleep(35)
        else:
            self.initial_ux = get_eval_initial_ux(self.code)["initial_ux"]

    def _initial_ux_parallel(self, template_id, domains):
        self.initial_ux[template_id] = {}
        threads = [None] * len(self.hyps)
        results = [None] * len(self.hyps)
        for i in range(len(self.hyps)):
            domain_id = domains[i]['id']
            hyp = self.hyps[i]
            logs.eval.info(
                "Calculing ux for template: {} in hypervisor {}. Domain: {}".format(template_id, hyp.id, domain_id))
            update_domain_forced_hyp(domain_id, hyp.id)
            threads[i] = Thread(target=self._get_stats_background, args=(domain_id, results, i, hyp))
            threads[i].start()
        for i in range(len(self.hyps)):
            threads[i].join()
            hyp = self.hyps[i]
            if not results[i]:
                raise Exception("Need to reset")
            stats, et = results[i]
            self.initial_ux[template_id][hyp.id] = self._calcule_ux_domain(stats, et, hyp.cpu_power)
            domain_id = domains[i]['id']
            update_domain_forced_hyp(domain_id, '')  # Clean forced_hyp

    def _initial_ux_sequencial(self, template_id, domain_id):
        self.initial_ux[template_id] = {}
        for hyp in self.hyps:
            logs.eval.info("Calculing ux for template: {} in hypervisor {}".format(template_id, hyp.id))
            update_domain_forced_hyp(domain_id, hyp.id)
            update_domain_status('Starting', domain_id)
            stats = []
            et_mean = []
            for i in range(self.initial_ux_iterations):
                sleep(2)
                self._wait_starting(domain_id)
                tmp_stats, et = self._wait_stop(domain_id, hyp)
                sleep(2)
                stats.extend(tmp_stats)
                et_mean.append(et)
            et = round(mean(et_mean), 2)
            self.initial_ux[template_id][hyp.id] = self._calcule_ux_domain(stats, et, hyp.cpu_power)
        update_domain_forced_hyp(domain_id, '')  # Clean forced_hyp

    def _get_stats_background(self, domain_id, results, i, hyp):
        # hyp.launch_eval_statistics()
        try:
            stats = []
            et_mean = []
            for j in range(self.initial_ux_iterations):
                sleep(2)
                update_domain_status('Starting', domain_id)
                self._wait_starting(domain_id)
                tmp_stats, et, stop_by_timeout = self._wait_stop(domain_id, hyp)
                stats.extend(tmp_stats)
                et_mean.append(et)
                sleep(5)
            et = round(mean(et_mean), 2)
            results[i] = (stats, et)
        except:
            logs.eval.error(format_exc())
            # hyp.stop_eval_statistics()

    def _calcule_ux_domain(self, stats, et, cpu_power):
        # logs.eval.debug("STATS: {}".format(stats))
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
        # logs.eval.debug("UX: {}".format(ux))
        return ux

    def _statistics(self, list):
        # sd = stdev(list) if len(list) >= 2 else 0
        return {"max": max(list), "min": min(list), "mean": mean(list), "stdev": stdev(list)}

    ################# Main Function
    def _start_domains(self):
        data = {}
        domains_id_list = EvalController.get_domains_id_randomized(self.user_id, self.id_pool, self.defined_domains,
                                                                   self.templates)
        total_domains = len(domains_id_list)
        start_domains = step_domains = ceil(total_domains / self.steps)
        step = 0
        total_results = []
        while (start_domains <= total_domains):
            logs.eval.info("Starting {} domains for ux eval".format(start_domains))
            domains_ids = domains_id_list[:start_domains]
            threads = [None] * start_domains
            results = [None] * start_domains
            i = 0
            while (i < start_domains):
                domain_id = domains_ids[i]
                threads[i] = Thread(target=self._calcule_ux_background, args=(domain_id, results, i, step))
                threads[i].start()
                i += 1

            for i in range(len(threads)):
                threads[i].join()
            data_results = self._analyze_step_results(results)
            total_results.append([r[0] for r in results if r])
            data["step_{}".format(step)] = data_results
            # if data_results["total"]["timeouts"] > ceil(data_results["total"]["n_domains"] / 2):
            #     # for hyp in self.hyps:
            #     #     hyp.stop_eval_statistics()
            #     data["total"] = self._analyze_total_results(total_results)
            #     break
            # logs.eval.debug("RESULTS: {}".format(pformat(results)))
            hmlog.debug("################## STEP: {}".format(step))
            diff = total_domains - start_domains
            inc = 1 if diff == 0 else step_domains if step_domains < diff else diff
            start_domains += inc
            sleep(35)  # Relaxing time
            step += 1

        data["total"] = {"score": self._analyze_total_results(total_results)}
        return data

    def _calcule_ux_background(self, domain_id, results, thread_id, step):
        # logs.eval.info("_calcule_ux_background: domain:{}, thread_id: {}".format(domain_id, thread_id))
        try:
            # Start
            update_domain_status('Starting', domain_id)
            self._wait_starting(domain_id)

            # Get hyp_id where is running
            hyp_id, hyp, template_id = self._get_hyp_domain_running(domain_id)
            logs.eval.info(
                "_calcule_ux_background: domain:{}, thread_id: {}, hyp_id: {}".format(domain_id, thread_id, hyp_id))
            # Wait until stop
            et_initial = self.initial_ux[template_id][hyp_id]["execution_time"]
            et_inc_max = self.ux_scorers["execution_time"]["max"]
            timeout = et_initial * (1 + et_inc_max / 100)
            logs.eval.info("TIMEOUT: {}, ET: {}".format(timeout, et_initial))
            stats, et, stop_by_timeout = self._wait_stop(domain_id, hyp, timeout=timeout)
            # et = self._calcule_random_et(et_initial, et_inc_max, step)
            # Calcule domain ux
            ux = self._calcule_ux_domain(stats, et, hyp.cpu_power)
            self.sender.send(template_id + '.execution_time', ux["execution_time"])
            self.sender.send(template_id + '.performance', ux["performance"])
            # logs.eval.debug("UX: domain_id: {}, hyp_id:{} , pformat(ux): {}".format(domain_id, hyp_id, pformat(ux)))

            # Get increment data: actual/initial
            initial_ux = self.initial_ux[template_id][hyp_id]
            increment = self._get_inc(ux, initial_ux)
            self.sender.send(hyp_id + '.inc_hyp_cpu_usage', increment["cpu_hyp_usage"]["mean"])
            self.sender.send(hyp_id + '.inc_hyp_cpu_iowait', increment["cpu_hyp_iowait"]["mean"])
            # Calcule some data
            data = self._calcule_data_from_ux(domain_id, hyp_id, template_id, ux, increment)

            results[thread_id] = (data, stop_by_timeout)
        except:
            logs.eval.error(format_exc())

    def _calcule_random_et(self, et_initial, et_inc_max, step):
        next_step = step + 1
        lower = step / self.steps * et_inc_max
        upper = (next_step * next_step) / (self.steps * self.steps) * et_inc_max
        r = randint(int(lower), int(upper) + (next_step*next_step))
        if r > et_inc_max:
            r = et_inc_max
        return round(et_initial * (r / 100 + 1), 2)

    def _analyze_step_results(self, results_timeouts):
        results = [r[0] for r in results_timeouts if r]  # Remove None's, produced by errors
        timeouts = [r[1] for r in results_timeouts if r and r[1] is True]  # Get any True value
        a = np.array(results)
        # logs.eval.debug("results_analyze_results: {}".format(a))
        data_results = {}
        total = list(np.round(np.mean(a[:, 3:].astype(np.float), axis=0), 2))
        data_results["total"] = {"score": total[-1],
                                 "n_domains": len(results),
                                 "timeouts": len(timeouts)}
        # logs.eval.debug(
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
                                        # "inc_cpu_usage_stdev_percent"
                                        # "inc_execution_time", "execution_time",
                                        # "inc_hyp_cpu_iowait_stdev", "execution_time",
                                        # "ram_hyp_usage_mean", "inc_ram_hyp_usage_mean",
                                        # "cpu_hyp_usage_mean", "inc_cpu_hyp_usage_mean"
                                        ]
                    data_results[t['id']][hyp.id] = {sn: hyp_stats[self.data_ux_names.index(sn)] for sn in
                                                     statistics_names}
                    data_results[t['id']][hyp.id]["inc_execution_time_percent"] = round((hyp_stats[1] - 1) * 100, 2)
                    data_results[t['id']][hyp.id]["score"] = hyp_stats[-1]
                    data_results[t['id']][hyp.id]["n_domains"] = len(tmp)
                    data_results[t['id']][hyp.id]["vcpu_cpu_rate"] = round(2 * len(tmp) / hyp.info['cpu_threads'], 2)
        # logs.eval.debug("TOTAL NP: {}".format(data_results["total"]))
        return data_results

    def _analyze_total_results(self, results):
        # logs.eval.debug("_analyze_total_results: {}".format(pformat(results)))
        total = np.array(results[0])
        for i in range(1, len(results)):
            total = np.append(total, results[i], axis=0)
        # logs.eval.debug("TOTAL: {}".format(total))
        means = list(np.round(np.mean(total[:, 3:].astype(np.float), axis=0), 2))
        return means[-1]

    def _wait_stop(self, domain_id, hyp, timeout=150):
        stats = []
        i = 0
        start_time = time.time()
        execution_time = time.time() - start_time
        while (get_domain_status(domain_id) == "Started"
               and (self.real_stop or i < self.time_to_stop)
               and execution_time < timeout):
            tmp = []
            s = self._process_stats(hyp, domain_id)
            # logs.eval.debug("UX Stats: {}".format(pformat(s)))
            for name in self.names:
                value = s.get(name)
                tmp.append(value)
                if value:
                    self.sender.send(hyp.id + '.' + name, value)
            # logs.eval.debug(tmp)
            stats.append(tmp)
            # logs.eval.debug("Domain {} is started and i : {}".format(domain_id, i))
            sleep(1)
            i += 1
            execution_time = time.time() - start_time

        if get_domain_status(domain_id) == "Started":
            update_domain_status('Stopping', domain_id, hyp.id)  # Force stop
            j = 0
            while ((get_domain_status(domain_id) == "Stopping") and j < 10):
                sleep(1)
                j += 1
        stop_by_timeout = execution_time > timeout
        logs.eval.debug(
            "Execution_time: {}, stop_by_time_out: {}, i_value: {}, timeout: {}".format(execution_time, stop_by_timeout,
                                                                                        i, timeout))
        return stats, execution_time, stop_by_timeout

    def _process_stats(self, hyp, domain_id):
        stats = hyp.stats_hyp[-3:]  # Get 3 last rows of stats data
        cpu_load = stats['cpu_load'].mean()
        data = {}
        data["ram_hyp_usage"] = round(hyp.stats_hyp_now.get('mem_load_rate', 0), 2)
        data["cpu_hyp_usage"] = cpu_load
        data["cpu_hyp_iowait"] = hyp.stats_hyp_now.get('cpu_iowait')
        domain_stats = hyp.stats_domains_now.get(domain_id)
        if domain_stats:
            data["cpu_usage"] = round(max(domain_stats.get('cpu_load', 0), 0), 2)
        else:
            data["cpu_usage"] = 0
        return data

    def _wait_starting(self, domain_id):
        i = 0
        while ((get_domain_status(domain_id) == "Starting") and i < 10):
            sleep(1)
            i += 1

    def _get_hyp_domain_running(self, domain_id):
        d = get_domain(domain_id)
        assert d['status'] == "Started"
        hyp_id = d["hyp_started"]
        try:
            hyp = list(filter(lambda h: h.id == hyp_id, self.hyps))[0]
        except:
            hmlog.debug("Hyp_id: {}".format(hyp_id))
            hmlog.debug(format_exc())
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
        # logs.eval.debug("domain_id: {}, hyp_id: {}, score: {}".format(domain_id, hyp_id, score))
        names = ["domain_id", "hyp_id", "template_id", "execution_time", "inc_execution_time", "performance"]
        names.extend(self.data_ux_names)
        tmp = dict(zip(names, data))
        logs.eval.debug("domain_ux_data: {}".format(tmp))
        return data

    def _ux_score(self, increment):
        total_score = 0
        for value in self.ux_scorers.keys():
            xv, vmax, vmin, wv = getattr(self, "_ux_score_" + value)(increment)
            weight = wv / self.total_weights_ux_scorers
            score = (1 - min(xv / (vmax - vmin), 1)) * weight
            total_score += score
        return total_score * 10

    def _ux_score_execution_time(self, increment):
        xv = increment["execution_time_percent"]
        vmax = self.ux_scorers["execution_time"]["max"]
        vmin = self.ux_scorers["execution_time"]["min"]
        wv = self.ux_scorers["execution_time"]["weight"]
        return xv * xv, vmax * vmax, vmin * vmin, wv

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
