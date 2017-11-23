# from engine import app
from math import ceil
from time import sleep

from engine import app
from engine.services.db import get_user, update_domain_status, get_domains, get_domain, insert_domain, \
    get_domains_id, get_domains_count
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
                                            'memory': 5000000,
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


class EvalController(object):
    def __init__(self, id_pool="default", templates=[{'id': "_windows_7_x64_v3", 'weight': 100}]):
        self.user = get_user('eval')
        self.templates = templates  # Define on database for each pool?
        self.id_pool = id_pool
        self.params = {'MAX_DOMAINS': 10,
                       'CREATE_SLEEP_TIME': 1,
                       'STOP_SLEEP_TIME': 1,
                       'START_SLEEP_TIME': 0}  # load from database?
        self._init_pool()

    def _init_pool(self):
        pool = app.m.pools.get(self.id_pool)
        if pool:
            self.pool = pool
            self.pool.num_eval_domains = min(pool.num_eval_domains, self.params["MAX_DOMAINS"])
        else:
            self.pool = None

    def clear_domains(self):
        """
        Just for testing purposes.
        :return:
        """
        domains = get_domains(self.user["id"])
        for d in domains:
            update_domain_status('Stopped', d['id'])
        return "Ok"

    def create_domains(self):
        """
        Create domains if necessari
        :return:
        """
        if not self.pool:
            return {"error":"Pool not defined"}
        data = {}
        log.debug("CREATE DOMAINS for pool: {}".format(self.id_pool))
        dd = self._define_domains() # Define number of domains for each template.
        for t in self.templates:
            n_domains = get_domains_count(self.user["id"], origin=t['id'])
            data[t['id']] = pending = dd[t['id']] - n_domains  # number of pending domains to create
            i = n_domains  # index of new domain
            while (pending > 0):  # Must create more desktops from this template?
                self._create_eval_domain(t['id'], i)
                log.debug("DOMAIN template ({}) created number: {}".format(t['id'], i))
                pending -= 1
                i += 1
                sleep(self.params["CREATE_SLEEP_TIME"])
        return {"created_domains":data}

    def stop_domains(self):
        """
        Stop domains if necessari.
        Los dominios que voy a usar en Failed, Started o Stopped. Sino es asi, no puedo usar esto.
        :return:
        """
        stopped_domains = get_domains_count(self.user["id"], status="Stopped")
        while (stopped_domains < self.pool.num_eval_domains):
            domains = get_domains(self.user["id"])
            for d in domains:
                if d["status"] == "Stopping":
                    update_domain_status('Stopped', d['id'])
                if d["status"] in ("Failed", "Starting"):
                    update_domain_status('Stopped', d['id'])
                if d["status"] == "Started":
                    update_domain_status('Stopping', d['id'])
                # IF status == 'Stopping' what?? Bug?
            sleep(self.params["STOP_SLEEP_TIME"])
            stopped_domains = get_domains_count(self.user["id"], status="Stopped")

    def destroy_domains(self):
        """
        Remove all eval domains.
        Must be removed on each defined pool.
        :return:
        """
        ids = get_domains_id(self.user["id"], id)
        for a in ids:
            update_domain_status('Deleting', a['id'])

    def run(self):
        """
        Start all default domains for each configured pool, analyze statistics to evaluate hardware performance and stop them.
        For real and exat evaluate must be run without any other domains running.
        :return:
        """
        data = {}

        self.create_domains()  # Create domains if necessari
        #self.stop_domains()  # Stop domains if necessari

        # Start domains and evaluate
        domains = get_domains(self.user["id"])
        log.debug("DOMAINS: ")
        log.debug(domains)
        # TODO--> get domains from templates.
        i = 0
        while (i < 10 and self._evaluate(self.pool)):
            id = domains[i]['id']
            log.debug("ID_DOMAIN: ".format(id))
            update_domain_status('Starting', id)
            sleep(self.params["START_SLEEP_TIME"])
            i += 1
        data["started_domains"] = i
        return data

    def _define_domains(self):
        """
        Define how many domains of each template must use for evaluate.
        :param n:
        :return:
        """
        n = self.pool.num_eval_domains
        total_weight = sum([t['weight'] for t in self.templates])
        if total_weight == 100:
            return {t['id']: ceil(n * t['weight'] / 100) for t in self.templates}
        else:
            # Sum of weigths is different from 100, so we balance it.
            w = 100 / len(self.templates)
            return {t['id']: ceil(n * w / 100) for t in self.templates}

    def _create_eval_domain(self, id_t, i):
        d = DICT_CREATE.copy()
        t = get_domain(id_t)
        id_domain = "_eval_{}_{}".format(id_t, i)
        disk_path = "{}/{}/{}/{}.qcow2".format(self.user['category'], self.user['group'], self.user['id'], id_domain)
        d['create_dict']['hardware']['disks'][0]['file'] = disk_path
        d['create_dict']['hardware']['disks'][0]['parent'] = t['disks_info'][0]['filename']
        d['create_dict']['origin'] = t['id']
        d['id'] = id_domain
        d['name'] = id_domain[1:]  # remove first char
        d['icon'] = t['icon']
        d['os'] = t['os']
        insert_domain(d)

    def _evaluate(self, pool):
        """
        Evaluate pool resources.
        If pool arrive to Threshold, return False
        :param pool:
        :return:
        """
        return True
        # TODO
