# Copyright 2017 the Isard-vdi project authors:
#      Alberto Larraz Dalmases
#      Josep Maria Viñolas Auquer
# License: AGPLv3

# coding=utf-8
"""
a module to control hypervisor functions and state. Overrides libvirt events and

"""

import traceback
import socket
import time
import threading
from datetime import datetime
from io import StringIO
from collections import deque
from statistics import mean
import time
import uuid

import libvirt
import paramiko
from lxml import etree
import xmltodict
from flatten_dict import flatten
from libpci import LibPCI

# ~ import pandas as pd

from engine.services.lib.functions import state_and_cause_to_str, hostname_to_uri, try_socket
from engine.services.lib.functions import test_hypervisor_conn, timelimit, new_dict_from_raw_dict_stats
from engine.services.lib.functions import calcule_cpu_hyp_stats, get_tid
from engine.services.db import get_id_hyp_from_uri, update_actual_stats_hyp, update_actual_stats_domain, update_info_nvidia_hyp_domain, \
                               get_hyp, update_db_default_gpu_models, update_uids_for_nvidia_id
from engine.services.log import *
from engine.config import *
from engine.services.lib.functions import exec_remote_cmd
from engine.services.lib.libvirt_dicts import virDomainState
from engine.services.db.domains import update_domain_status, get_domains_with_status_in_list, get_domains_started_in_hyp
from engine.models.nvidia_models import NVIDIA_MODELS
from engine.services.lib.functions import execute_commands

TIMEOUT_QUEUE = 20
TIMEOUT_CONN_HYPERVISOR = 4 #int(CONFIG_DICT['HYPERVISORS']['timeout_conn_hypervisor'])


# > 1 is connected
HYP_STATUS_CONNECTED = 10

# 1 is ready
HYP_STATUS_READY = 1

# < 0 not connected and error
HYP_STATUS_ERROR_WHEN_CONNECT = -5
HYP_STATUS_ERROR_WHEN_CONNECT_TIMELIMIT = -6
HYP_STATUS_ERROR_NOT_RESOLVES_HOSTNAME = -7
HYP_STATUS_ERROR_WHEN_CLOSE_CONNEXION = -1
HYP_STATUS_NOT_ALIVE = -10

MAX_GET_KVM_RETRIES = 3

class hyp(object):
    """
    operates with hypervisor
    """
    def __init__(self, address, user='root', port=22, capture_events=False, try_ssh_autologin=False, hyp_id =None):

        # dictionary of domains
        # self.id = 0
        self.domains = {}
        self.domains_states = {}
        port=int(port)
        if (type(port) == int) and port > 1 and port < pow(2, 16):
            self.port = port
        else:
            self.port = 22
        #log.info('El port es: '+str(self.port))
        self.try_ssh_autologin = try_ssh_autologin
        self.user = user
        self.hostname = address
        self.connected = False
        self.ssh_autologin_fail = False
        self.fail_connected_reason = ''
        self.eventLoopThread = None
        self.info = {}
        self.info_stats = {}
        self.capture_events = capture_events
        self.id_hyp_rethink = hyp_id
        self.hyp_id = hyp_id
        self.has_nvidia = False
        self.gpus = {}

        self.create_stats_vars()

        # isard_preferred_keys = tuple(paramiko.ecdsakey.ECDSAKey.supported_key_format_identifiers()) + (
        #    'ssh-rsa',
        #    'ssh-dss',
        # )
        #
        # paramiko.Transport._preferred_keys = isard_preferred_keys

        if self.connect_to_hyp():
            if self.capture_events:
                self.launch_events()


    def try_ssh(self):

        # try socket
        timeout = float(CONFIG_DICT['TIMEOUTS']['ssh_paramiko_hyp_test_connection'])
        if try_socket(self.hostname, self.port, timeout):

            # ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            ssh = paramiko.SSHClient()
            # ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            # INFO TO DEVELOPER: OJO, load_system_host_keys debería ir pero el problema está en que hay ciertos algoritmos de firma
            # que la librería actual de paramiko da error. Seguramente haciendo un update de la librearía en un futuro
            # esto se arreglará espero: si solo existe el hash ecdsa-sha2-nistp256
            # ssh -o "HostKeyAlgorithms ssh-rsa" root@ajenti.escoladeltreball.org

            ssh.load_system_host_keys()
            # ssh.load_host_keys(os.path.expanduser('~/.ssh/known_hosts'))
            # time.sleep(1)
            try:
                # timelimit(3,test_hypervisor_conn,self.hostname,
                #             username=self.user,
                #             port= self.port,
                #             timeout=CONFIG_DICT['TIMEOUTS']['ssh_paramiko_hyp_test_connection'])
                ssh.connect(self.hostname,
                            username=self.user,
                            port=self.port,
                            timeout=timeout, banner_timeout=timeout)

                log.debug("host {} with ip {} TEST CONNECTION OK, ssh connect without password".format(self.hostname,
                                                                                                       self.ip))
                ssh.close()
            except paramiko.SSHException as e:
                log.error("host {} with ip {} can't connect with ssh without password. Paramiko except Reason: {}".format(self.hostname,
                                                                                                                          self.ip, e))
                log.error("")
                # message when host not found or key format not supported: not found in known_hosts
                self.fail_connected_reason = 'ssh authentication fail when connect: {}'.format(e)
                self.ssh_autologin_fail = True
            except Exception as e:
                log.error(
                    "host {} with ip {} can't connect with ssh without password. Reasons? timeout, ssh authentication with keys is needed, port is correct?".format(
                        self.hostname, self.ip))
                log.error('reason: {}'.format(e))
                self.fail_connected_reason = 'ssh authentication fail when connect: {}'.format(e)
                self.ssh_autologin_fail = True

        else:
            self.ssh_autologin_fail = True
            self.fail_connected_reason = 'socket error in ssh port, sshd disabled or firewall'
            log.error('socket error, try if ssh is listen in hostname {} with ip address {} and port {}'.format(self.hostname,self.ip,self.port))

    def connect_to_hyp(self):
        try:
            self.ip = socket.gethostbyname(self.hostname)

            if self.try_ssh_autologin == True:
                self.try_ssh()

            if self.ssh_autologin_fail is False:
                try:
                    self.uri = hostname_to_uri(self.hostname, user=self.user, port=self.port)
                    if self.id_hyp_rethink is None:
                        try:
                            self.id_hyp_rethink = get_id_hyp_from_uri(self.uri)
                        except Exception as e:
                            log.error('error when hypervisor have not rethink id. {}'.format(e))
                    #timeout_libvirt = float(CONFIG_DICT['TIMEOUTS']['libvirt_hypervisor_timeout_connection'])
                    #self.conn = timelimit(timeout_libvirt, test_hypervisor_conn, self.uri)
                    self.conn = test_hypervisor_conn(self.uri)

                    # timeout = float(CONFIG_DICT['TIMEOUTS']['ssh_paramiko_hyp_test_connection'])

                    if (self.conn != False):
                        self.connected = True
                        # prueba de alberto para que indique cuando ha caído y para que mantenga alive la conexión


                        # OJO INFO TO DEVELOPER
                        # self.startEvent()


                        # este setKeepAlive no tengo claro que haga algo, pero bueno...
                        # y al ponerlo da error lo dejo comentado, pero en futuro hay que quitar
                        # esta línea si no sabemos bien que hace...
                        # self.conn.setKeepAlive(5, 3)
                        log.info("connected to hypervisor: %s" % self.hostname)
                        self.set_status(HYP_STATUS_CONNECTED)
                        self.fail_connected_reason = ''
                        # para que le de tiempo a los eventos a quedarse registrados hay que esperar un poquillo, ya
                        # que se arranca otro thread
                        # self.get_hyp_info()
                        return True
                    else:
                        log.error('libvirt can\'t connect to hypervisor {}'.format(self.hostname))
                        log.info("""connection to hypervisor fail, try policykit or permissions,
                              or try in the hypervisor if libvirtd service is started
                              (in Fedora/Centos: systemctl status libvirtd )
                              or if the port 22 is open""")
                        self.set_status(HYP_STATUS_ERROR_WHEN_CONNECT)
                        self.fail_connected_reason = 'Hypervisor policykit or permissions or libvirtd has not started'

                        return False

                # except TimeLimitExpired:
                #     log.error("""Time Limit Expired connecting to hypervisor""")
                #     self.set_status(HYP_STATUS_ERROR_WHEN_CONNECT_TIMELIMIT)
                #     self.fail_connected_reason = 'Time Limit Expired connecting to hypervisor'
                #     return False

                except Exception as e:
                    log.error('connection to hypervisor {} fail with unexpected error: {}'.format(self.hostname, e))
                    log.error('libvirt uri: {}'.format(self.uri))
                    self.set_status(HYP_STATUS_ERROR_WHEN_CONNECT)
                    self.fail_connected_reason = 'connection to hypervisor {} fail with unexpected error'.format(
                        self.hostname)
                    return False

        except socket.error as e:
            log.error(e)
            log.error('not resolves ip from hostname: {}'.format(self.hostname))
            self.fail_connected_reason = 'not resolves ip from hostname: {}'.format(self.hostname)
            return False

        except Exception as e:
            log.error(e)

    def launch_events(self):
        self.launch_event_handlers()
        self.conn.registerCloseCallback(self.myConnectionCloseCallback, None)

    def set_status(self, status_code):
        if status_code > 1:
            self.connected = True
        else:
            self.connected = False

            # set_hyp_status(self.hostname,status_code)

    def init_nvidia(self):
        d_hyp = get_hyp(self.id_hyp_rethink)
        default_gpu_models = d_hyp.get('default_gpu_models',{})
        uuids_gpu = d_hyp.get('nvidia_uids',{})

        if len(self.info['nvidia']) > 0:
            if len(default_gpu_models) < len(self.info['nvidia']):

                default_gpu_models = {k:a['type_max_gpus'] for k,a in self.info['nvidia'].items()}
                update_db_default_gpu_models(self.id_hyp_rethink,default_gpu_models)

            for gpu_id,d_info_gpu in self.info['nvidia'].items():
                if gpu_id not in uuids_gpu.keys():
                    d_uids = self.create_uuids(d_info_gpu)
                    update_uids_for_nvidia_id(self.id_hyp_rethink,gpu_id,d_uids)

            d_hyp = get_hyp(self.id_hyp_rethink)
            for gpu_id,d_uids in d_hyp['nvidia_uids'].items():
                selected_gpu_type = default_gpu_models[gpu_id]
                info_nvidia = d_hyp['info']['nvidia'][gpu_id]
                self.delete_and_create_devices_if_not_exist(gpu_id,d_uids,info_nvidia,selected_gpu_type,self.id_hyp_rethink)
            if len(d_hyp['nvidia_uids']) > 0:
                self.update_started_uids()

    def get_kvm_mod(self):
        for i in range(MAX_GET_KVM_RETRIES):
            try:
                d = exec_remote_cmd('lsmod |grep kvm',self.hostname,username=self.user,port=self.port)
                if len(d['err']) > 0:
                    log.error('error {} returned from command: lsmod |grep kvm'.format(d['err'].decode('utf-8')))
                else:
                    s = d['out'].decode('utf-8')
                    if s.find('kvm_intel') >= 0:
                        self.info['kvm_module'] = 'intel'
                    elif s.find('kvm_amd') >= 0:
                        self.info['kvm_module'] = 'amd'
                    elif s.find('kvm') >= 0:
                        self.info['kvm_module'] = 'bios_disabled'
                        log.error('No kvm module kvm_amd or kvm_intel activated. You must review your BIOS')
                        log.error('Hardware acceleration is supported, but disabled in the BIOS settings')
                    else:
                        self.info['kvm_module'] = False
                        log.error('No kvm module installed. You must review if qemu-kvm is installed and CPU capabilities')
                return True

            except Exception as e:
                log.error('Exception while executing remote command in hypervisor to list kvm modules: {}'.format(e))
                log.error(f'Ssh launch command attempt fail: {i+1}/{MAX_GET_KVM_RETRIES}. Retry in one second.')
            time.sleep(1)

        self.info['kvm_module'] = False
        log.error(f'remote ssh command in hypervisor {hostname} fail with {MAX_GET_KVM_RETRIES} retries')
        return False

    def get_hyp_info(self):

        libvirt_version = str(self.conn.getLibVersion())
        self.info['libvirt_version'] = '{}.{}.{}'.format(int(libvirt_version[-9:-6]),
                                                         int(libvirt_version[-6:-3]),
                                                         int(libvirt_version[-3:]))

        try:
            qemu_version = str(self.conn.getVersion())
            self.info['qemu_version'] = '{}.{}.{}'.format(int(qemu_version[-9:-6]),
                                                          int(qemu_version[-6:-3]),
                                                          int(qemu_version[-3:]))
        except libvirt.libvirtError as e:
            logs.workers.error(f'Exception when get qemu_version in hyp {self.id_hyp_rethink}: {e}')
            self.info['qemu_version'] = '0.0.0'



        inf = self.conn.getInfo()
        self.info['arch'] = inf[0]
        self.info['memory_in_MB'] = inf[1]
        self.info['cpu_threads'] = inf[2]
        self.info['cpu_mhz'] = inf[3]
        self.info['numa_nodes'] = inf[4]
        self.info['cpu_cores'] = inf[6]
        self.info['threads_x_core'] = inf[7]
        xml = self.conn.getSysinfo()
        parser = etree.XMLParser(remove_blank_text=True)
        tree = etree.parse(StringIO(xml), parser)

        try:
            if tree.xpath('/sysinfo/processor/entry[@name="socket_destination"]'):
                self.info['cpu_model'] = tree.xpath('/sysinfo/processor/entry[@name="socket_destination"]')[0].text

            if tree.xpath('/sysinfo/system/entry[@name="manufacturer"]'):
                self.info['motherboard_manufacturer'] = tree.xpath('/sysinfo/system/entry[@name="manufacturer"]')[0].text

            if tree.xpath('/sysinfo/system/entry[@name="product"]'):
                self.info['motherboard_model'] = tree.xpath('/sysinfo/system/entry[@name="product"]')[0].text

            if tree.xpath('/sysinfo/memory_device'):
                self.info['memory_banks'] = len(tree.xpath('/sysinfo/memory_device'))
                self.info['memory_type'] = tree.xpath('/sysinfo/memory_device/entry[@name="type"]')[0].text
                try:
                    self.info['memory_speed'] = tree.xpath('/sysinfo/memory_device/entry[@name="speed"]')[0].text
                except:
                    self.info['memory_speed'] = "0"

        except Exception as e:
            log.error('Exception when extract information with libvirt from hypervisor {}: {}'.format(self.hostname, e))
            log.error('Traceback: {}'.format(traceback.format_exc()))

        xml = self.conn.getCapabilities()
        parser = etree.XMLParser(remove_blank_text=True)
        tree = etree.parse(StringIO(xml), parser)

        if tree.xpath('/capabilities/host/cpu/model'):
            self.info['cpu_model_type'] = tree.xpath('/capabilities/host/cpu/model')[0].text

        if tree.xpath('/capabilities/guest/arch/domain[@type="kvm"]/machine[@canonical]'):
            self.info['kvm_type_machine_canonical'] = \
                tree.xpath('/capabilities/guest/arch/domain[@type="kvm"]/machine[@canonical]')[0].get('canonical')

        # intel virtualization => cpu feature vmx
        #   amd virtualization => cpu feature svm
        if tree.xpath('/capabilities/host/cpu/feature[@name="vmx"]'):
            self.info['virtualization_capabilities'] = 'vmx'
        elif tree.xpath('/capabilities/host/cpu/feature[@name="svm"]'):
            self.info['virtualization_capabilities'] = 'svm'
        else:
            self.info['virtualization_capabilities'] = False

        # read_gpu
        self.get_nvidia_capabilities()

    def get_nvidia_available_instances_of_type(self,vgpu_id):
        self.get_nvidia_capabilities(only_get_availables=True)
        d_available = {}
        for pci_id,info_nvidia in self.info['nvidia'].items():
            d_available[pci_id] = info_nvidia['types'][vgpu_id]['available']
        return d_available


    def get_nvidia_capabilities(self,only_get_availables=False):
        d_info_nvidia = {}
        mdev_names = self.conn.listDevices('mdev_types')
        mdev_devices = [a for a in self.conn.listAllDevices() if a.name() in mdev_names]
        if len(mdev_devices) > 0:
            l_dict_mdev = [xmltodict.parse(a.XMLDesc()) for a in mdev_devices]
            l_nvidia_devices = [a for a in l_dict_mdev if a['device']['driver']['name'] == 'nvidia']
            if len(l_nvidia_devices) > 0:
                self.has_nvidia = True
                for d in l_nvidia_devices:
                    info_nvidia = {}
                    try:
                        try:
                            max_count = d['device']['capability']['capability'][0]['@maxCount']
                        except:
                            max_count = 0
                        name = d['device']['name']
                        path = d['device']['path']
                        parent = d['device']['parent']
                        vendor_pci_id = int(d['device']['capability']['vendor']['@id'],base=0)
                        device_pci_id = int(d['device']['capability']['product']['@id'],base=0)
                        if only_get_availables is False:
                            pci = LibPCI()
                            device_name = pci.lookup_device_name(vendor_pci_id,device_pci_id)
                        else:
                            device_name = self.info['nvidia'].get(name,'')
                    except:
                        max_count = 0
                    try:
                        #only Q-Series Virtual GPU Types (Required license edition: vWS)
                        if type(d['device']['capability']['capability']) is list:  ## T4
                            types = d['device']['capability']['capability'][1]['type']
                        else:
                            types = d['device']['capability']['capability']['type']
                        l_types = [dict(a) for a in types if a['name'][-1] == 'Q']
                        for a in l_types:
                            a['name'] =a['name'].replace('GRID ','')
                        l_types.sort(key=lambda r: int(r['name'].split('Q')[0].split('-')[-1]))
                        type_max_gpus = l_types[0]['name']
                        d_types = {a['name']:{'id':a['@id'],
                                              'available':int(a['availableInstances']),
                                              'memory':NVIDIA_MODELS.get(a['name'],{}).get('mb'),
                                              'max':NVIDIA_MODELS.get(a['name'],{}).get('max'),
                                              } for a in l_types}
                    except:
                        d_types = {}
                    info_nvidia['types'] = d_types
                    info_nvidia['type_max_gpus'] = type_max_gpus
                    info_nvidia['device_name'] = device_name
                    info_nvidia['pci_id'] = name
                    info_nvidia['path'] = path
                    info_nvidia['parent'] = parent
                    info_nvidia['max_count'] = max_count
                    info_nvidia['max_gpus'] = d_types[type_max_gpus]['max']
                    info_nvidia['model'] = type_max_gpus.split('-')[0]
                    d_info_nvidia[name] = info_nvidia
        self.info['nvidia'] = d_info_nvidia

    def create_uuids(self,d_info_gpu):
        d_uids = {}
        for name,d_type in d_info_gpu['types'].items():
            d = {}
            #in some nvidia cards as A40 d['max'] is None
            if d_type.get('max') is None:
                d_type['max'] = d_type.get('available',1)
            total_available = max(d_type.get('max',1),d_type.get('available',1))
            for i in range(total_available):
                uid = str(uuid.uuid4())
                d[uid] = {'created':False,
                          'reserved':False,
                          'started':False}
            d_uids[name] = d
        return d_uids

    def delete_and_create_devices_if_not_exist(self,gpu_id,d_uids,info_nvidia,selected_gpu_type,hyp_id):
        cmds1 = list()
        path = info_nvidia['path']
        for type in d_uids.keys():
            id_type = info_nvidia['types'][type]['id']
            dir = f'{path}/mdev_supported_types/{id_type}'
            cmds1.append({'title': f'{type}', 'cmd': f'ls "{dir}/devices"'})

        array_out_err = execute_commands(self.hostname, cmds1, port=self.port, dict_mode=True)
        uids_in_hyp_now = {d['title']:d['out'].splitlines() for d in array_out_err}

        # DELETE  UUIDS
        cmds1 = list()
        for type,l_uids_now in uids_in_hyp_now.items():
            id_type = info_nvidia['types'][type]['id']
            dir = f'{path}/mdev_supported_types/{id_type}'

            for uid_now in l_uids_now:
                if (type != selected_gpu_type) or ((type == selected_gpu_type) and (uid_now not in d_uids[type])):
                        cmds1.append({'title': f'remove uuid to {type}: {uid_now}', 'cmd': f'echo "1" > "{dir}/devices/{uid_now}/remove"'})
        # CREATE  UUIDS
        created = []
        for type,l_uids_now in uids_in_hyp_now.items():
            id_type = info_nvidia['types'][type]['id']
            dir = f'{path}/mdev_supported_types/{id_type}'
            if type == selected_gpu_type:
                for uid in d_uids[type]:
                    if uid not in l_uids_now:
                        cmds1.append({'title': f'create uuid to {type}: {uid}', 'cmd': f'echo "{uid}" > "{dir}/create"'})
                    else:
                        created.append(uid)

        if len(cmds1) > 0:
            array_out_err = execute_commands(self.hostname, cmds1, port=self.port, dict_mode=True)
            output_ok = [d['title'] for d in array_out_err if len(d['err']) == 0]
            append_uids = [a.split(':')[1].strip() for a in output_ok if a.find('create uuid')==0]
            remove_uids = [a.split(':')[1].strip() for a in output_ok if a.find('remove uuid')==0]
            if len(remove_uids) > 0:
                ok = update_info_nvidia_hyp_domain('removed',remove_uids,hyp_id)
            created += append_uids
            if len(created) > 0:
                ok = update_info_nvidia_hyp_domain('created',created,hyp_id)
            if len([d['err'] for d in array_out_err if len(d['err'])>0]) > 0:
                print('errors creating uids')
                return False
            return True
        else:
            return True

    def update_started_uids(self):
        pass

    def define_and_start_paused_xml(self, xml_text):
        # todo alberto: faltan todas las excepciones, y mensajes de log,
        # aquí hay curro y es importante, porque hay que mirar si los discos no están
        # si es un error de conexión con el hypervisor...
        # está el tema de los timeouts...
        # TODO INFO TO DEVELOPER: igual se podría verificar si arrancando el dominio sin definirlo
        # con la opción XML_INACTIVE sería suficiente
        # o quizás lo mejor sería arrancar con createXML(libvirt.VIR_DOMAIN_START_PAUSED)
        xml_stopped = ''
        xml_started = ''
        try:
            d = self.conn.defineXML(xml_text)
            d.undefine()
            try:
                d = self.conn.createXML(xml_text, flags=libvirt.VIR_DOMAIN_START_PAUSED)
                xml_started = d.XMLDesc()
                xml_stopped = d.XMLDesc(libvirt.VIR_DOMAIN_XML_INACTIVE)
                d.destroy()
            except Exception as e:
                log.error('error starting paused vm: {}'.format(e))

        except Exception as e:
            log.error('error defining vm: {}'.format(e))

        return xml_stopped, xml_started


    def get_domains(self):
        """
        return dictionary with domain objects of libvirt
        keys of dictionary are names
        domains can be started or paused
        """
        self.domains = {}
        self.domains_states = {}
        if self.connected:
            try:
                for d in self.conn.listAllDomains(libvirt.VIR_CONNECT_LIST_DOMAINS_ACTIVE):
                    try:
                        domain_name = d.name()
                        l_libvirt_state = d.state()
                        state_id = l_libvirt_state[0]
                        reason_id = -1 if len(l_libvirt_state) < 2 else l_libvirt_state[1]
                        self.domains_states[domain_name] = {
                             'status': virDomainState[state_id]['status'],
                             'detail': virDomainState[state_id].get('reason',  {}).\
                                                                get(reason_id, {}).\
                                                                get('detail',  '')
                             }
                    except:
                        log.info('unkown domain fail when trying to get his name, power off??')
                        continue
                    if domain_name[0] == '_':
                        self.domains[domain_name] = d
            except:
                log.error('error when try to list domain in hypervisor {}'.format(self.hostname))
                self.domains = {}

        return self.domains_states

    def update_domain_coherence_in_db(self):
        d_domains_with_states = self.get_domains()
        set_domains_running_in_hyps = set()
        if self.id_hyp_rethink is None:
            try:
                self.id_hyp_rethink = get_id_hyp_from_uri(self.uri)
                if self.id_hyp_rethink is None:
                    log.error('error when hypervisor have not rethink id. {}'.format(e))
                    raise TypeError
            except Exception as e:
                log.error('error when hypervisor have not rethink id. {}'.format(e))
                raise e
        for domain_id, d in d_domains_with_states.items():
            update_domain_status(d['status'],
                                 domain_id,
                                 hyp_id=self.id_hyp_rethink,
                                 detail=d['detail'])
            set_domains_running_in_hyps.add(domain_id)
        domains_with_hyp_started_in_db = get_domains_started_in_hyp(self.id_hyp_rethink)
        set_domains_with_hyp_started_in_db = set(list(domains_with_hyp_started_in_db.keys()))
        domains_to_be_stopped = set_domains_with_hyp_started_in_db.difference(set_domains_running_in_hyps)
        for domain_id in domains_to_be_stopped:
            update_domain_status('Stopped',
                                 domain_id,
                                 detail=f'domain not running in hyp {self.id_hyp_rethink}')

    #
    # def hyp_worker_thread(self,queue_worker):
    #     log.debug('Hyp {} worker thread started ...'.format(self.hostname))
    #     #h = hyp('vdesktop1')
    #     while(1):
    #         try:
    #             d=queue_worker.get(timeout=TIMEOUT_QUEUE)
    #             log.debug('received ACTION:{}; '.format(d['action']))
    #             if d['action'] == 'start_domain':
    #                 xml = d['xml']
    #                 h.conn.createXML(xml)
    #                 log.debug('domain started {} ??'.format(d['name']))
    #             if d['action'] == 'hyp_info':
    #                 h.conn.get_hyp_info()
    #
    #             log.debug('hypervisor motherboard: {}'.format(h.info['motherboard_manufacturer']))
    #             #time.sleep(0.1)
    #         except Queue.Empty:
    #             try:
    #                 if h.conn.isAlive():
    #                     log.debug('hypervisor {} is alive'.format(host))
    #                 else:
    #                     log.debug('trying to reconnect hypervisor {}'.format(host))
    #                     h.connect_to_hyp()
    #                     if h.conn.isAlive():
    #                         log.debug('hypervisor {} is alive'.format(host))
    #
    #             except libvirtError:
    #                 log.debug('trying to reconnect hypervisor {}'.format(host))
    #                 h.connect_to_hyp()
    #                 if h.conn.isAlive():
    #                     log.debug('hypervisor {} is alive'.format(host))

    def disconnect(self):
        try:
            self.conn.close()
            self.set_status(HYP_STATUS_READY)
        except:
            log.error('error closing connexion for hypervisor {}'.format(self.hostname))
            self.set_status(HYP_STATUS_ERROR_WHEN_CLOSE_CONNEXION)

    def get_stats_from_libvirt(self, exclude_domains_not_isard=True):
        raw_stats = {}
        if self.connected:
            # get CPU Stats
            try:
                raw_stats['cpu'] = self.conn.getCPUStats(libvirt.VIR_NODE_CPU_STATS_ALL_CPUS)
            except:
                log.error('getCPUStats fail in hypervisor {}'.format(self.hostname))
                return False

            # get Memory Stats
            try:
                raw_stats['memory'] = self.conn.getMemoryStats(-1, 0)
            except:
                log.error('getMemoryStats fail in hypervisor {}'.format(self.hostname))
                return False

            # get All Domain Stats
            try:
                # l_stats = self.conn.getAllDomainStats(flags=libvirt.VIR_CONNECT_GET_ALL_DOMAINS_STATS_ACTIVE)
                raw_stats['domains'] = {l[0].name(): {'stats': l[1],
                                                      'state': l[0].state(),
                                                      'd'    : l[0]}
                                        for l in
                                        self.conn.getAllDomainStats(flags=libvirt.VIR_CONNECT_LIST_DOMAINS_ACTIVE)}

                raw_stats['time_utc'] = time.time()

                # remove stats from domains not started with _ (all domains in isard start with _)
                if exclude_domains_not_isard is True:
                    for domain_name in list(raw_stats['domains'].keys()):
                        if domain_name[0] != '_':
                            del raw_stats['domains'][domain_name]

            except:
                log.error('getAllDomainStats fail in hypervisor {}'.format(self.hostname))
                return False

            return raw_stats

        else:
            log.error('can not get stats from libvirt if hypervisor {} is not connected'.format(self.hostname))
            return False

    def     process_hypervisor_stats(self, raw_stats):
        return True
        # ~ if len(self.info) == 0:
        # ~ self.get_hyp_info()

        # ~ now_raw_stats_hyp = {}
        # ~ now_raw_stats_hyp['cpu_stats'] = raw_stats['cpu']
        # ~ now_raw_stats_hyp['mem_stats'] = raw_stats['memory']
        # ~ now_raw_stats_hyp['time_utc'] = raw_stats['time_utc']
        # ~ now_raw_stats_hyp['datetime'] = timestamp = datetime.utcfromtimestamp(raw_stats['time_utc'])

        # ~ self.stats_raw_hyp.append(now_raw_stats_hyp)

        # ~ sum_vcpus, sum_memory, sum_domains, sum_memory_max, sum_disk_wr, \
        # ~ sum_disk_rd, sum_disk_wr_reqs, sum_disk_rd_reqs, sum_net_tx, sum_net_rx, \
        # ~ mean_vcpu_load, mean_vcpu_iowait= self.process_domains_stats(raw_stats)

        # ~ if len(self.stats_raw_hyp) > 1:
        # ~ hyp_stats = {}

        # ~ if self.stats_hyp['started'] == False:
        # ~ self.stats_hyp['started'] = timestamp

        # ~ hyp_stats['num_domains'] = sum_domains

        # ~ cpu_percents = calcule_cpu_hyp_stats(self.stats_raw_hyp[-2]['cpu_stats'],self.stats_raw_hyp[-1]['cpu_stats'])[0]

        # ~ hyp_stats['cpu_load'] = round(cpu_percents['used'],2)
        # ~ hyp_stats['cpu_iowait'] = round(cpu_percents['iowait'],2)
        # ~ hyp_stats['vcpus'] = sum_vcpus
        # ~ hyp_stats['vcpu_cpu_rate'] = round((sum_vcpus / self.info['cpu_threads']) * 100, 2)

        # ~ hyp_stats['mem_load_rate']    = round(((raw_stats['memory']['total'] -
        # ~ raw_stats['memory']['free'] -
        # ~ raw_stats['memory']['cached']) / raw_stats['memory']['total'] ) * 100, 2)
        # ~ hyp_stats['mem_cached_rate']  = round(raw_stats['memory']['cached'] / raw_stats['memory']['total'] * 100, 2)
        # ~ hyp_stats['mem_free_gb'] = round((raw_stats['memory']['cached'] + raw_stats['memory']['free']) / 1024 / 1024 , 2)

        # ~ hyp_stats['mem_domains_gb'] = round(sum_memory, 3)
        # ~ hyp_stats['mem_domains_max_gb'] = round(sum_memory_max, 3)
        # ~ if sum_memory_max > 0:
        # ~ hyp_stats['mem_balloon_rate'] = round(sum_memory / sum_memory_max * 100, 2)
        # ~ else:
        # ~ hyp_stats['mem_balloon_rate'] = 0

        # ~ hyp_stats['disk_wr'] = sum_disk_wr
        # ~ hyp_stats['disk_rd'] = sum_disk_rd
        # ~ hyp_stats['disk_wr_reqs'] = sum_disk_wr_reqs
        # ~ hyp_stats['disk_rd_reqs'] = sum_disk_rd_reqs
        # ~ hyp_stats['net_tx'] = sum_net_tx
        # ~ hyp_stats['net_rx'] = sum_net_rx
        # ~ hyp_stats['vcpus_load'] = mean_vcpu_load
        # ~ hyp_stats['vcpus_iowait'] = mean_vcpu_iowait
        # ~ hyp_stats['timestamp_utc'] = now_raw_stats_hyp['time_utc']

        # ~ self.stats_hyp_now = hyp_stats.copy()

        # ~ fields = ['num_domains', 'vcpus', 'vcpu_cpu_rate', 'cpu_load', 'cpu_iowait',
        # ~ 'mem_load_rate', 'mem_free_gb', 'mem_cached_rate',
        # ~ 'mem_balloon_rate', 'mem_domains_gb', 'mem_domains_max_gb',
        # ~ 'disk_wr', 'disk_rd', 'disk_wr_reqs', 'disk_rd_reqs',
        # ~ 'net_tx', 'net_rx', 'vcpus_load', 'vcpus_iowait']

        # ~ # (id_hyp,hyp_stats,timestamp)

        # ~ #time_delta = timestamp - self.stats_hyp['started']
        # ~ self.stats_hyp['near_df'] = self.stats_hyp['near_df'].append(pd.DataFrame(hyp_stats,
        # ~ columns=fields,
        # ~ index=[timestamp]))

    def process_domains_stats(self, raw_stats):
        return True
        # ~ if len(self.info) == 0:
        # ~ self.get_hyp_info()
        # ~ d_all_domain_stats = raw_stats['domains']

        # ~ previous_domains = set(self.stats_domains.keys())
        # ~ current_domains  = set(d_all_domain_stats.keys())
        # ~ add_domains      = current_domains.difference(previous_domains)
        # ~ remove_domains   = previous_domains.difference(current_domains)

        # ~ for d in remove_domains:
        # ~ del self.stats_domains[d]
        # ~ del self.stats_raw_domains[d]
        # ~ del self.stats_domains_now[d]
        # ~ # TODO: buen momento para asegurarse que la máquina se quedó en Stopped,
        # ~ # podríamos ahorrarnos esa  comprobación en el thread broom ??

        # ~ #TODO: también es el momento de guardar en histórico las estadísticas de ese dominio,
        # ~ # esto nos permite hacer análisis posterior

        # ~ for d in add_domains:
        # ~ self.stats_domains[d] = {
        # ~ 'started'              : datetime.utcfromtimestamp(raw_stats['time_utc']),
        # ~ 'near_df'              : pd.DataFrame(),
        # ~ 'medium_df'            : pd.DataFrame(),
        # ~ 'long_df'              : pd.DataFrame(),
        # ~ 'boot_df'              : pd.DataFrame(),
        # ~ 'last_timestamp_near'  : False,
        # ~ 'last_timestamp_medium': False,
        # ~ 'last_timestamp_long'  : False,
        # ~ 'means_near'           : False,
        # ~ 'means_medium'         : False,
        # ~ 'means_long'           : False,
        # ~ 'means_all'            : False,
        # ~ 'means_boot'           : False
        # ~ }
        # ~ self.stats_raw_domains[d] = deque(maxlen=self.stats_queue_lenght_domains_raw_stats)
        # ~ self.stats_domains_now[d] = dict()

        # ~ sum_vcpus = 0
        # ~ sum_memory = 0
        # ~ sum_domains = 0
        # ~ sum_memory_max = 0
        # ~ sum_disk_wr = 0
        # ~ sum_disk_rd = 0
        # ~ sum_net_tx = 0
        # ~ sum_net_rx = 0
        # ~ sum_disk_wr_reqs = 0
        # ~ sum_disk_rd_reqs = 0
        # ~ mean_vcpu_load = 0
        # ~ mean_vcpu_iowait = 0

        # ~ for d, raw in d_all_domain_stats.items():

        # ~ raw['stats']['now_utc_time'] = raw_stats['time_utc']
        # ~ raw['stats']['now_datetime'] = datetime.utcfromtimestamp(raw_stats['time_utc'])

        # ~ self.stats_raw_domains[d].append(raw['stats'])


        # ~ if len(self.stats_raw_domains[d]) > 1:

        # ~ sum_domains += 1

        # ~ d_stats = {}

        # ~ current = self.stats_raw_domains[d][-1]
        # ~ previous = self.stats_raw_domains[d][-2]

        # ~ delta = current['now_utc_time'] - previous['now_utc_time']
        # ~ if delta == 0:
        # ~ log.error('same value in now_utc_time, must call get_stats_from_libvirt')
        # ~ break

        # ~ timestamp = datetime.utcfromtimestamp(current['now_utc_time'])
        # ~ d_stats['time_utc'] = current['now_utc_time']

        # ~ sum_vcpus += current['vcpu.current']

        # ~ #d_stats['cpu_load'] = round(((current['cpu.time'] - previous['cpu.time']) / 1000000000 / self.info['cpu_threads'])*100,3)
        # ~ if current.get('cpu.time') and previous.get('cpu.time'):
        # ~ d_stats['cpu_load'] = round((current['cpu.time'] - previous['cpu.time']) / 1000000000 / self.info['cpu_threads'],3)

        # ~ d_balloon={k:v/1024 for k,v in current.items() if k[:5] == 'ballo' }

        # ~ # balloon is running and monitorized if balloon.unused key is disposable
        # ~ if 'balloon.unused' in d_balloon.keys():
        # ~ mem_used    = round((d_balloon['balloon.current']-d_balloon['balloon.unused'])/1024.0, 3)
        # ~ mem_balloon = round(d_balloon['balloon.current'] / 1024.0, 3)
        # ~ mem_max = round(d_balloon['balloon.maximum'] / 1024.0, 3)

        # ~ elif 'balloon.maximum' in d_balloon.keys():
        # ~ mem_used =    round(d_balloon['balloon.maximum'] / 1024.0 ,3)
        # ~ mem_balloon = round(d_balloon['balloon.maximum'] / 1024.0, 3)
        # ~ mem_max = round(d_balloon['balloon.maximum'] / 1024.0, 3)

        # ~ else:
        # ~ mem_used = 0
        # ~ mem_balloon = 0
        # ~ mem_max = 0

        # ~ d_stats['mem_load']    = round(mem_used / (self.info['memory_in_MB']/1024), 2)
        # ~ d_stats['mem_used']    = mem_used
        # ~ d_stats['mem_balloon'] = mem_balloon
        # ~ d_stats['mem_max']     = mem_max

        # ~ sum_memory += mem_used
        # ~ sum_memory_max += mem_max

        # ~ vcpu_total_time = 0
        # ~ vcpu_total_wait = 0

        # ~ for n in range(current['vcpu.current']):
        # ~ try:
        # ~ vcpu_total_time += current['vcpu.' +str(n)+ '.time'] - previous['vcpu.' +str(n)+ '.time']
        # ~ vcpu_total_wait += current['vcpu.' +str(n)+ '.wait'] - previous['vcpu.' +str(n)+ '.wait']
        # ~ except KeyError:
        # ~ vcpu_total_time = 0
        # ~ vcpu_total_wait = 0

        # ~ d_stats['vcpu_load'] = round((vcpu_total_time / (delta * 1e9) / current['vcpu.current'])*100,2)
        # ~ d_stats['vcpu_iowait'] = round((vcpu_total_wait / (delta * 1e9) / current['vcpu.current'])*100,2)

        # ~ total_block_wr = 0
        # ~ total_block_wr_reqs = 0
        # ~ total_block_rd = 0
        # ~ total_block_rd_reqs = 0

        # ~ if 'block.count' in current.keys():
        # ~ for n in range(current['block.count']):
        # ~ try:
        # ~ total_block_wr += current['block.'+str(n)+'.wr.bytes'] - previous['block.'+str(n)+'.wr.bytes']
        # ~ total_block_rd += current['block.'+str(n)+'.rd.bytes'] - previous['block.'+str(n)+'.rd.bytes']
        # ~ total_block_wr_reqs += current['block.'+str(n)+'.wr.reqs'] - previous['block.'+str(n)+'.wr.reqs']
        # ~ total_block_rd_reqs += current['block.'+str(n)+'.rd.reqs'] - previous['block.'+str(n)+'.rd.reqs']
        # ~ except KeyError:
        # ~ total_block_wr = 0
        # ~ total_block_wr_reqs = 0
        # ~ total_block_rd = 0
        # ~ total_block_rd_reqs = 0

        # ~ #KB/s
        # ~ d_stats['disk_wr'] = round(total_block_wr / delta / 1024,3)
        # ~ d_stats['disk_rd'] = round(total_block_rd / delta / 1024,3)
        # ~ d_stats['disk_wr_reqs'] = round(total_block_wr_reqs / delta,3)
        # ~ d_stats['disk_rd_reqs'] = round(total_block_rd_reqs / delta,3)
        # ~ sum_disk_wr      += d_stats['disk_wr']
        # ~ sum_disk_rd      += d_stats['disk_rd']
        # ~ sum_disk_wr_reqs += d_stats['disk_wr_reqs']
        # ~ sum_disk_rd_reqs += d_stats['disk_rd_reqs']

        # ~ total_net_tx = 0
        # ~ total_net_rx = 0

        # ~ if 'net.count' in current.keys():
        # ~ for n in range(current['net.count']):
        # ~ try:
        # ~ total_net_tx += current['net.' +str(n)+ '.tx.bytes'] - previous['net.' +str(n)+ '.tx.bytes']
        # ~ total_net_rx += current['net.' +str(n)+ '.rx.bytes'] - previous['net.' +str(n)+ '.rx.bytes']
        # ~ except KeyError:
        # ~ total_net_tx = 0
        # ~ total_net_rx = 0

        # ~ d_stats['net_tx'] = round(total_net_tx / delta / 1000, 3)
        # ~ d_stats['net_rx'] = round(total_net_rx / delta / 1000, 3)
        # ~ sum_net_tx += d_stats['net_tx']
        # ~ sum_net_rx += d_stats['net_rx']

        # ~ self.stats_domains_now[d] = d_stats.copy()
        # ~ self.update_domain_means_and_data_frames(d, d_stats, timestamp)


        # ~ if len(self.stats_domains_now) > 0:
        # ~ try:
        # ~ mean_vcpu_load = sum([j['vcpu_load'] for j in self.stats_domains_now.values()]) / len(self.stats_domains_now)
        # ~ mean_vcpu_iowait   = sum([j['vcpu_iowait'] for j in self.stats_domains_now.values()]) / len(self.stats_domains_now)
        # ~ except KeyError:
        # ~ mean_vcpu_iowait = 0.0
        # ~ mean_vcpu_load = 0.0

        # ~ return sum_vcpus, sum_memory, sum_domains, sum_memory_max, sum_disk_wr, sum_disk_rd, \
        # ~ sum_disk_wr_reqs, sum_disk_rd_reqs, sum_net_tx, sum_net_rx, mean_vcpu_load, mean_vcpu_iowait

    def update_domain_means_and_data_frames(self, d, d_stats, timestamp):
        return True
        # ~ started = self.stats_domains[d]['started']
        # ~ time_delta_now = timestamp - started

        # ~ fields = "vcpu_load / vcpu_iowait / mem_load / mem_used / mem_balloon / mem_max / " + \
        # ~ "disk_wr / disk_rd / disk_wr_reqs / disk_rd_reqs / net_tx / net_rx"
        # ~ fields = [s.strip() for s in fields.split('/')]

        # ~ self.stats_domains[d]['near_df'] = self.stats_domains[d]['near_df'].append(pd.DataFrame(d_stats,
        # ~ columns=fields,
        # ~ index=[time_delta_now]))
        # ~ if self.stats_domains[d]['means_boot'] is False:
        # ~ if time_delta_now.seconds > self.stats_booting_time:
        # ~ self.stats_domains[d]['boot_df'] = self.stats_domains[d]['near_df'].copy()
        # ~ self.stats_domains[d]['means_boot'] = self.stats_domains[d]['boot_df'].mean().to_dict()

        # ~ # delete samples from near > stats_near_size_window
        # ~ last_time_delta = self.stats_domains[d]['near_df'].tail(1).index[0]
        # ~ index_near_to_delete = self.stats_domains[d]['near_df'][:last_time_delta - pd.offsets.Second(self.stats_near_size_window)].index
        # ~ self.stats_domains[d]['near_df'].drop(index=index_near_to_delete, inplace=True)
        # ~ self.stats_domains[d]['means_near'] = d_stats.copy()
        # ~ self.stats_domains[d]['means_medium'] = self.stats_domains[d]['near_df'].mean().to_dict()

        # ~ # insert new values in medium_df
        # ~ if len(self.stats_domains[d]['medium_df']) == 0:
        # ~ self.stats_domains[d]['means_long'] = self.stats_domains[d]['means_medium'].copy()
        # ~ self.stats_domains[d]['means_total'] = self.stats_domains[d]['means_medium'].copy()
        # ~ if int(time_delta_now.seconds / self.stats_medium_sample_period) >= 1:
        # ~ self.stats_domains[d]['medium_df'] = self.stats_domains[d]['medium_df'].append(
        # ~ pd.DataFrame(self.stats_domains[d]['means_medium'],
        # ~ columns=fields,
        # ~ index=[
        # ~ time_delta_now]))
        # ~ else:
        # ~ last_time_delta_medium = self.stats_domains[d]['medium_df'].tail(1).index[0]

        # ~ if int(time_delta_now.seconds / self.stats_medium_sample_period) > int(
        # ~ last_time_delta_medium.seconds / self.stats_medium_sample_period):

        # ~ self.stats_domains[d]['medium_df'] = self.stats_domains[d]['medium_df'].append(
        # ~ pd.DataFrame(self.stats_domains[d]['means_medium'],
        # ~ columns=fields,
        # ~ index=[
        # ~ time_delta_now]))

        # ~ index_medium_to_delete = self.stats_domains[d]['medium_df'][:last_time_delta_medium - pd.offsets.Second(self.stats_medium_size_window)].index
        # ~ self.stats_domains[d]['medium_df'].drop(index=index_medium_to_delete, inplace=True)

        # ~ self.stats_domains[d]['means_long'] = self.stats_domains[d]['medium_df'].mean().to_dict()

        # ~ if len(self.stats_domains[d]['long_df']) == 0:
        # ~ self.stats_domains[d]['means_total'] = self.stats_domains[d]['means_long'].copy()

        # ~ if int(time_delta_now.seconds / self.stats_long_sample_period) >= 1:
        # ~ self.stats_domains[d]['long_df'] = self.stats_domains[d]['long_df'].append(
        # ~ pd.DataFrame(self.stats_domains[d]['means_long'],
        # ~ columns=fields,
        # ~ index=[
        # ~ time_delta_now]))
        # ~ else:
        # ~ last_time_delta_long = self.stats_domains[d]['long_df'].tail(1).index[0]

        # ~ if int(time_delta_now.seconds / self.stats_long_sample_period) > int(
        # ~ last_time_delta_long.seconds / self.stats_long_sample_period):
        # ~ self.stats_domains[d]['long_df'] = self.stats_domains[d]['long_df'].append(
        # ~ pd.DataFrame(self.stats_domains[d]['means_long'],
        # ~ columns=fields,
        # ~ index=[
        # ~ time_delta_now]))

        # ~ index_long_to_delete = self.stats_domains[d][
        # ~ 'long_df'][: last_time_delta_long - pd.offsets.Second(
        # ~ self.stats_long_size_window)].index
        # ~ self.stats_domains[d]['long_df'].drop(index=index_long_to_delete, inplace=True)

        # ~ self.stats_domains[d]['means_total'] = self.stats_domains[d]['long_df'].mean().to_dict()


    def create_stats_vars(self,testing=True):
        return True
        # ~ self.stats_queue_lenght_hyp_raw_stats = 3
        # ~ self.stats_queue_lenght_domains_raw_stats = 3

        # ~ self.stats_polling_interval = 5

        # ~ self.stats_booting_time = 120
        # ~ self.stats_near_size_window = 300
        # ~ self.stats_medium_size_window = 2 * 3600
        # ~ self.stats_long_size_window = 24 * 3600

        # ~ self.stats_near_sample_period = self.stats_polling_interval
        # ~ self.stats_medium_sample_period = 60
        # ~ self.stats_long_sample_period = 1800

        # ~ if testing is True:
        # ~ self.stats_polling_interval = 1

        # ~ self.stats_booting_time = 20
        # ~ self.stats_near_size_window = 30
        # ~ self.stats_medium_size_window = 120
        # ~ self.stats_long_size_window = 240

        # ~ self.stats_near_sample_period = self.stats_polling_interval
        # ~ self.stats_medium_sample_period = 10
        # ~ self.stats_long_sample_period = 60


        # ~ self.stats_hyp_now = dict()
        # ~ self.stats_domains_now = dict()
        # ~ self.stats_raw_hyp = deque(maxlen=self.stats_queue_lenght_hyp_raw_stats)
        # ~ self.stats_raw_domains = dict()

        # ~ #Pandas dataframe
        # ~ self.stats_hyp = {
        # ~ 'started'     : False,
        # ~ 'near_df'     : pd.DataFrame(),
        # ~ 'medium_df'   : pd.DataFrame(),
        # ~ 'long_df'     : pd.DataFrame(),
        # ~ 'means_near'  : False,
        # ~ 'means_medium': False,
        # ~ 'means_long'  : False,
        # ~ }

        # ~ #Dictionary of pandas dataframes
        # ~ self.stats_domains = dict()

        # ~ #Thread to polling stats
        # ~ self.polling_thread = False


    def launch_thread_status_polling(self,polling_interval=0):
        self.polling_thread = self.PollingStats(self, polling_interval)
        self.polling_thread.daemon = True
        self.polling_thread.start()

    class PollingStats(threading.Thread):
        def __init__(self, hyp_obj, polling_interval=0, stop=False):
            threading.Thread.__init__(self)
            self.name = 'PollingStats_{}'.format(hyp_obj.hostname)
            self.hyp_obj = hyp_obj
            if polling_interval == 0:
                self.polling_interval = self.stats_polling_interval
            else:
                self.polling_interval = polling_interval
            self.stop = stop
            self.tid = False

        def run(self):
            self.tid = get_tid()
            log.info('starting thread: {} (TID {})'.format(self.name, self.tid))
            while self.stop is not True:
                self.hyp_obj.get_load()
                interval = 0.0
                while interval < self.polling_interval:
                    time.sleep(0.1)
                    interval += 0.1
                    if self.stop is True:
                        break

    def get_load(self):

        if len(self.info) == 0:
            self.get_hyp_info()

        raw_stats = self.get_stats_from_libvirt()

        if raw_stats is False:
            return False

        domains_with_stats = list(raw_stats['domains'].keys())
        #broom action: domains that are started or stopped in stats that have errors in database
        self.update_domains_started_and_stopped(domains_with_stats)

        self.process_hypervisor_stats(raw_stats)

        if len(self.stats_hyp_now) > 0:
            self.send_stats()

        return True

    def update_domains_started_and_stopped(self,domains_with_stats):
        if self.id_hyp_rethink is None:
            try:
                self.id_hyp_rethink = get_id_hyp_from_uri(hostname_to_uri(self.hostname, user=self.user, port=self.port))
            except Exception as e:
                log.error('error when hypervisor have not rethink id. {}'.format(e))
                return False
        l_all_domains = get_domains_with_status_in_list(list_status=['Started', 'Shutting-down', 'Stopped', 'Failed'])
        for d in l_all_domains:
            if d['id'] in domains_with_stats:
                if d['status'] == 'Started' or d['status'] == 'Shutting-down':
                    #if status started check if has the same hypervisor
                    if d['hyp_started'] != self.id_hyp_rethink:
                        log.error(f"Domain {d['id']} started in hypervisor ({self.id_hyp_rethink}) but database says that is started in {d['hyp_started']} !! ")
                        update_domain_status(status=d['status'],
                                             id_domain='_admin_downloaded_tetros',
                                             detail=f'Started in other hypervisor!! {self.id_hyp_rethink}. Updated by status thread',
                                             hyp_id=self.id_hyp_rethink)
                else:
                    #if status is Stopped or Failed update, the domain is started
                    log.info('Domain is started in {self.id_hyp_rethink} but in database was Stopped or Failed, updated by status thread')
                    update_domain_status(status='Started',
                                         id_domain='_admin_downloaded_tetros',
                                         detail=f'Domain is started in {self.id_hyp_rethink} but in database was Stopped or Failed, updated by status thread',
                                         hyp_id=self.id_hyp_rethink)

            elif d['hyp_started'] == self.id_hyp_rethink:
                #Domain is started in this hypervisor in database, but is stopped
                if d['status'] == 'Started':
                    update_domain_status(status='Stopped',
                                         id_domain='_admin_downloaded_tetros',
                                         detail=f'Domain is stopped in {self.id_hyp_rethink} but in database was Started, updated by status thread',
                                         )

    def send_stats(self):
        #hypervisors
        send_stats_to_rethink = True
        if self.id_hyp_rethink is None:
            #self.id_hyp_rethink = get_id_hyp_from_uri('qemu+ssh://root@isard-hypervisor:22/system')
            self.id_hyp_rethink = get_id_hyp_from_uri(hostname_to_uri(self.hostname, user=self.user, port=self.port))
        if send_stats_to_rethink:
            update_actual_stats_hyp(self.id_hyp_rethink,
                                    self.stats_hyp_now)

            for id_domain, s in self.stats_domains_now.items():

                means = {'near':   self.stats_domains[id_domain].get('means_near',False),
                         'medium': self.stats_domains[id_domain].get('means_medium',False),
                         'long':   self.stats_domains[id_domain].get('means_long',False),
                         'total':  self.stats_domains[id_domain].get('means_total',False),
                         'boot':   self.stats_domains[id_domain].get('means_boot',False)}
                update_actual_stats_domain(id_domain, s, means)
            #for (h in )

    def get_eval_statistics(self):
        cpu_percent_free = 100 - self.stats_hyp_now.get('cpu_load', 0)
        ram_percent_free = 100 - self.stats_hyp_now.get('mem_load_rate', 0)
        data = {"cpu_percent_free": cpu_percent_free,
                "ram_percent_free": ram_percent_free,
                "domains": list(self.stats_domains_now.keys())}
        return data

    def get_ux_eval_statistics(self, domain_id):
        """
        :param domain_id:
        :return: data {"ram_hyp_usage", "cpu_hyp_usage", "cpu_hyp_iowait", "cpu_usage"} when they are available

        fields = ['num_domains', 'vcpus', 'vcpu_cpu_rate', 'cpu_load', 'cpu_iowait',
                      'mem_load_rate', 'mem_free_gb', 'mem_cached_rate',
                      'mem_balloon_rate', 'mem_domains_gb','mem_domains_max_gb',
                      'disk_wr', 'disk_rd', 'disk_wr_reqs', 'disk_rd_reqs',
                      'net_tx', 'net_rx', ]
        self.stats_hyp_now.get('mem_load_rate')
        """
        data = {}
        data["ram_hyp_usage"] = self.stats_hyp_now.get('mem_load_rate')
        data["cpu_hyp_usage"] = self.stats_hyp_now.get('cpu_load')
        data["cpu_hyp_iowait"] = self.stats_hyp_now.get('cpu_iowait')
        domain_stats = self.stats_domains_now.get(domain_id)
        if domain_stats:
            data["cpu_usage"] = domain_stats.get('cpu_load')
        return data
