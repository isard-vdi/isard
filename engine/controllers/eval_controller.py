# Copyright 2018 the Isard-vdi project authors:
#      Alberto Larraz Dalmases
#      Josep Maria Viñolas Auquer
#      Daniel Criado Casas
# License: AGPLv3

# from engine import app
from math import ceil, floor
from random import shuffle
from time import sleep
from traceback import format_exc, print_exc

from flask import current_app

from engine.services.db import get_user, update_domain_status, get_domains, get_domain, insert_domain, \
    get_domains_id, get_domains_count, get_hypers_info
from engine.services.log import *

# Example of data dict for create domain
DICT_CREATE_WIN7 = {'allowed': {'categories': False,
                                'groups': False,
                                'roles': False,
                                'users': False},
                    'category': 'testing',
                    'create_dict': {'hardware': {'boot_order': ['disk'],
                                                 'disks': [{'file': 'testing/test_users/test1/prova_win7.qcow2',
                                                            'parent': '/vimet/bases/windows_7v3.qcow2'}],
                                                 'graphics': ['default'],
                                                 'interfaces': ['default'],
                                                 'memory': 2500000,
                                                 'vcpus': 2,
                                                 'videos': ['default']},
                                    'origin': '_windows_7_x64_v3'},
                    'description': '',
                    'detail': None,
                    'group': 'test_users',
                    'hypervisors_pools': ['default'],
                    'icon': 'windows',
                    'id': '_test1_prova_win7',
                    'kind': 'desktop',
                    'name': 'prova win7',
                    'os': 'windows',
                    'server': False,
                    'status': 'Creating',
                    'user': 'test1',
                    'xml': None}

DICT_CREATE = {'allowed': {'categories': False,
                           'groups': False,
                           'roles': False,
                           'users': False},
               'category': 'admin',
               'create_dict': {'hardware': {'boot_order': ['disk'],
                                            'disks': [{'file': None,  # replace
                                                       'parent': None  # replace
                                                       }],
                                            'graphics': ['default'],
                                            'interfaces': ['default'],
                                            'memory': 2000000,
                                            'vcpus': 2,
                                            'videos': ['default']},
                               'origin': None  # replace
                               },
               'description': '',
               'detail': None,
               'group': 'eval',
               'hypervisors_pools': ['default'],
               'icon': None,  # replace
               'id': None,  # replace,
               'kind': 'desktop',
               'name': None,  # replace
               'os': None,  # replace
               'server': False,
               'status': 'Creating',
               'user': 'eval',
               'xml': None}


# templates = [{'id': "_windows_7_x64_v3", 'weight': 100}],
# templates=[{'id': "centos_7", 'weight': 100}]
# evaluators=["load","ux"]
class EvalController(object):
    def __init__(self, id_pool="default",
                 templates=[{'id': "_admin_ubuntu_17_eval_wget", 'weight': 100}],
                 # templates=[{'id': "_admin_ubuntu_17_eval", 'weight': 100}],
                 # templates=[{'id': "centos_7", 'weight': 100}],
                 # templates=[{'id': "_windows_7_x64_v3", 'weight': 100}],
                 # templates=[{'id': "centos_7", 'weight': 50}, {'id': "_windows_7_x64_v3", 'weight': 50}],
                 evaluators=["ux"],
                 max_domains=None,
                 # max_domains=14,
                 # evaluators=["load","ux"]
                 ):
        self.user = get_user('eval')
        self.templates = templates  # Define on database for each pool?
        self.id_pool = id_pool
        self.max_domains = max_domains
        self.params = {'MAX_DOMAINS': 50,
                       'POOLING_INTERVAL': 1,
                       'CREATE_SLEEP_TIME': 1,
                       'STOP_SLEEP_TIME': 2,
                       'START_SLEEP_TIME': 3,
                       'TEMPLATE_MEMORY': 1000}  # in MB, info duplicated on DICT_CREATE but in bytes
        self._init_domains()
        self._init_hyps()
        self._init_evaluators(evaluators)
        self.hyp_polling_interval = {}

    def _init_evaluators(self, evaluators):
        self.evaluators = []
        if "load" in evaluators:
            evaluator = LoadEval(self.user['id'], self.id_pool, self.defined_domains, self.templates, self.hyps,
                                 self.params)
            self.evaluators.append(evaluator)
        if "ux" in evaluators:
            evaluator = UXEval(self.user['id'], self.id_pool, self.defined_domains, self.templates, self.hyps,
                               self.params)
            self.evaluators.append(evaluator)

    def _init_hyps(self):
        self.hyps = []
        hyps = get_hypers_info(self.id_pool, pluck=['id', 'hostname', 'info'])
        manager = current_app.m
        for h in hyps:
            # TODO: calcule percent as hyp method
            percent = round(self.params.get('TEMPLATE_MEMORY', 2000) * 100 / h['info']['memory_in_MB'], 2)
            hyp_obj = manager.t_status[h['id']].status_obj.hyp_obj
            hyp_obj.id = h['id']
            hyp_obj.percent_ram_template = percent
            hyp_obj.cpu_power = round(h['info']['cpu_cores'] * h['info']['cpu_mhz'] / 1e3, 1)
            self.hyps.append(hyp_obj)

    def _init_domains(self):
        self.num_domains = self.max_domains if self.max_domains else self._calcule_num_domains()
        eval_log.debug("Num of max domains for eval: {}".format(self.num_domains))
        self.defined_domains = self._define_domains()

    def _calcule_num_domains(self):
        hyps = get_hypers_info(self.id_pool, pluck=['id', 'info'])
        n = sum(floor(x['info']['memory_in_MB'] / self.params.get('TEMPLATE_MEMORY', 2000)) for x in hyps)
        # m = min(hyps, key=lambda x: x['info']['memory_in_MB'])
        # min_mem = m['info']['memory_in_MB']
        # # TODO: adjust num_domains value.
        # num_domains = ceil(min_mem / self.params.get('TEMPLATE_MEMORY', 2000)) * (len(hyps)+2)
        # n = min(self.params.get('MAX_DOMAINS'), num_domains)
        # n = 20
        # eval_log.debug("Num of max domains for eval: {}".format(n))
        return n

    def _define_domains(self):
        """
        Define how many domains of each template must use for evaluate.
        :param n:
        :return:
        """
        n = self.num_domains
        total_weight = sum([t['weight'] for t in self.templates])
        if total_weight == 100:
            return {t['id']: ceil(n * t['weight'] / 100) for t in self.templates}
        else:
            # Sum of weigths is different from 100, so we balance it.
            w = 100 / len(self.templates)
            return {t['id']: ceil(n * w / 100) for t in self.templates}

    def clear_domains(self):
        """
        Just for testing purposes.
        :return:
        """
        domains = get_domains(self.user["id"])
        for d in domains:
            update_domain_status('Stopped', d['id'])
        return "Okey"

    def create_domains(self):
        """
        Create domains if necessari
        :return:
        """
        data = {}
        total_created_domains = 0
        eval_log.info("CREATE DOMAINS for pool: {}".format(self.id_pool))
        dd = self.defined_domains  # Define number of domains for each template.
        for t in self.templates:
            n_domains = get_domains_count(self.user["id"], origin=t['id'])
            p = dd[t['id']] - n_domains  # number of pending domains to create
            data[t['id']] = pending = p if p >= 0 else 0  # number of pending domains to create
            i = n_domains  # index of new domain
            eval_log.debug("Creating {} pending domains from template: {}".format(pending, t['id']))
            total_created_domains += pending
            while (pending > 0):  # Must create more desktops from this template?
                self._create_eval_domain(t['id'], i)
                pending -= 1
                i += 1
                sleep(self.params["CREATE_SLEEP_TIME"])
        return {"total_created_domains": total_created_domains,
                "data": data}

    @classmethod
    def stop_domains(cls, user_id, stop_sleep_time):
        """
        Stop domains if they are started.
        :return:
        """
        domains = get_domains(user_id, status="Started")
        while(len(domains) > 0):
            eval_log.info("Stoping {} domains".format(len(domains)))
            for d in domains:
                update_domain_status('Stopping', d['id'], hyp_id=d['hyp_started'])
                sleep(stop_sleep_time)
            domains = get_domains(user_id, status="Started")
        return {"total_stopped_domains": len(domains),
                "data": None}

    @classmethod
    def get_domains_id_randomized(cls, user_id, id_pool, dd, templates):
        domains_id_list = []
        for t in templates:
            n_dd = dd[t['id']]  # defined domains number
            ids = get_domains_id(user_id, id_pool, origin=t['id'])
            shuffle(ids)
            if len(ids) < n_dd:
                error_msg = "Error starting domains for eval template {}," \
                            " needs {} domains and have {}".format(t['id'], n_dd, len(ids))
                eval_log.error(error_msg)
                return {"error": error_msg}
            [domains_id_list.append(ids.pop()) for i in range(n_dd)]
        shuffle(domains_id_list)
        return domains_id_list

    def destroy_domains(self):
        """
        Remove all eval domains.
        Must be removed on each defined pool.
        :return:
        """
        ids = get_domains_id(self.user["id"], self.id_pool)
        for a in ids:
            update_domain_status('Deleting', a['id'])

    def run(self):
        """
        Run all default evaluators on specified pool.
        Analyze statistics to evaluate hardware performance.
        For real and exact evaluate must be run without any other domains running.
        :return:
        """
        data = {}

        data_create = self.create_domains()  # Create domains if necessari
        sleep(data_create.get("total_created_domains"))  # Wait 1 sec more for each created domain.
        data_stop = EvalController.stop_domains(self.user['id'],
                                                self.params["STOP_SLEEP_TIME"])  # Stop domains if necessari
        sleep(data_stop.get("total_stopped_domains"))  # Wait 1 sec more for each stopped domain.
        # Run evaluators
        try:
            self._set_polling_interval()
            for e in self.evaluators:
                d = e.run()
                data[e.name] = d
                sleep(10)
                data_stop = EvalController.stop_domains(self.user['id'], self.params["STOP_SLEEP_TIME"])
                sleep(data_stop.get("total_stopped_domains"))  # Wait 1 sec more for each stopped domain.
        except:
            eval_log.debug("Exception on RUN evaluator: {}".format(format_exc()))
            self._restablish_pooling_interval()

        return data

    def _set_polling_interval(self):
        ts = current_app.m.t_status
        for hyp_id, thread in ts.items():
            self.hyp_polling_interval[hyp_id] = thread.status_obj.polling_interval
            thread.status_obj.polling_interval = self.params['POOLING_INTERVAL']
        sleep(10)  # Relaxing time

    def _restablish_pooling_interval(self):
        ts = current_app.m.t_status
        for hyp_id, pi in self.hyp_polling_interval.items():
            ts[hyp_id].status_obj.polling_interval = pi

    def _create_eval_domain(self, id_t, i):
        d = DICT_CREATE.copy()
        t = get_domain(id_t)
        id_domain = "_eval_{}_{}".format(id_t, i)
        disk_path = "{}/{}/{}/{}.qcow2".format(self.user['category'], self.user['group'], self.user['id'], id_domain)
        d['create_dict']['hardware']['disks'][0]['file'] = disk_path
        d['create_dict']['hardware']['disks'][0]['parent'] = t['disks_info'][0]['filename']
        d['create_dict']['hardware']['memory'] = t['create_dict']['hardware']['memory']
        d['create_dict']['hardware']['currentMemory'] = t['create_dict']['hardware']['memory']  # / 0,7?  =>  +30 %
        d['create_dict']['origin'] = t['id']
        d['id'] = id_domain
        d['name'] = id_domain[1:]  # remove first char
        d['icon'] = t['icon']
        d['os'] = t['os']
        insert_domain(d)


from engine.services.evaluators.load_eval import LoadEval
from engine.services.evaluators.ux_eval import UXEval
