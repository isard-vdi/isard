# Copyright 2017 the Isard-vdi project authors:
#      Alberto Larraz Dalmases
#      Josep Maria Viñolas Auquer
# License: AGPLv3

# coding=utf-8
"""
a module to control hypervisor functions and state. Overrides libvirt events and

"""

import socket
import time
from io import StringIO
from statistics import mean
import libvirt
import paramiko
from lxml import etree

from engine.services.lib.functions import state_and_cause_to_str, hostname_to_uri, try_socket, calcule_cpu_stats
from engine.services.lib.functions import test_hypervisor_conn, timelimit, new_dict_from_raw_dict_stats
from engine.services.log import *
from engine.config import *

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



class hyp(object):
    """
    operates with hypervisor
    """
    def __init__(self, address, user='root', port=22, capture_events=False, try_ssh_autologin=False):

        #dictionary of domains
        # self.id = 0
        self.domains={}
        if (type(port) == int) and port > 1 and port < pow(2,16):
            self.port = port
        else:
            self.port = 22
        self.try_ssh_autologin = try_ssh_autologin
        self.user = user
        self.hostname = address
        self.connected = False
        self.ssh_autologin_fail = False
        self.fail_connected_reason = ''
        self.eventLoopThread = None
        self.info={}
        self.info_stats={}
        self.load={}
        self.capture_events = capture_events
        self.last_load = None
        self.cpu_percent_free = []


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
        if try_socket(self.hostname,self.port,timeout):

            #ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            ssh = paramiko.SSHClient()
            # ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            #INFO TO DEVELOPER: OJO, load_system_host_keys debería ir pero el problema está en que hay ciertos algoritmos de firma
            # que la librería actual de paramiko da error. Seguramente haciendo un update de la librearía en un futuro
            # esto se arreglará espero: si solo existe el hash ecdsa-sha2-nistp256
            # ssh -o "HostKeyAlgorithms ssh-rsa" root@ajenti.escoladeltreball.org

            ssh.load_system_host_keys()
            ssh.load_host_keys(os.path.expanduser('~/.ssh/known_hosts'))
            # time.sleep(1)
            try:
                # timelimit(3,test_hypervisor_conn,self.hostname,
                #             username=self.user,
                #             port= self.port,
                #             timeout=CONFIG_DICT['TIMEOUTS']['ssh_paramiko_hyp_test_connection'])
                ssh.connect(self.hostname,
                            username=self.user,
                            port= self.port,
                            timeout=timeout,banner_timeout=timeout)

                log.debug("host {} with ip {} TEST CONNECTION OK, ssh connect without password".format(self.hostname,self.ip))
                ssh.close()
            except paramiko.SSHException as e:
                log.error("host {} with ip {} can't connect with ssh without password. Reason: {}".format(self.hostname,self.ip,e))
                log.error("")
                self.fail_connected_reason = 'ssh authentication fail when connect: {}'.format(e)
                self.ssh_autologin_fail = True
            except Exception as e:
                log.error("host {} with ip {} can't connect with ssh without password. Reasons? timeout, ssh authentication with keys is needed, port is correct?".format(self.hostname,self.ip))
                log.error('reason: {}'.format(e))
                self.fail_connected_reason = 'ssh authentication fail when connect: {}'.format(e)
                self.ssh_autologin_fail = True

        else:
            self.ssh_autologin_fail = True
            self.fail_connected_reason = 'socket error in ssh port, sshd disabled or firewall'
            log.error('socket error, try if ssh is listen in hostname {} with ip address {} and port {}'.format(self.hostname,self.ip,self.port))

    def connect_to_hyp(self):

        try:
            self.ip =  socket.gethostbyname(self.hostname)

            if self.try_ssh_autologin == True:
                self.try_ssh()

            if self.ssh_autologin_fail is False:
                try:
                    self.uri = hostname_to_uri(self.hostname,user=self.user,port=self.port)

                    timeout_libvirt = float(CONFIG_DICT['TIMEOUTS']['libvirt_hypervisor_timeout_connection'])
                    self.conn=timelimit(timeout_libvirt,test_hypervisor_conn,self.uri)

                    #timeout = float(CONFIG_DICT['TIMEOUTS']['ssh_paramiko_hyp_test_connection'])

                    if (self.conn != False):
                        self.connected = True
                        # prueba de alberto para que indique cuando ha caído y para que mantenga alive la conexión


                        #OJO INFO TO DEVELOPER
                        #self.startEvent()


                        #este setKeepAlive no tengo claro que haga algo, pero bueno...
                        # y al ponerlo da error lo dejo comentado, pero en futuro hay que quitar
                        # esta línea si no sabemos bien que hace...
                        #self.conn.setKeepAlive(5, 3)
                        log.debug("connected to hypervisor: %s" % self.hostname)
                        self.set_status(HYP_STATUS_CONNECTED)
                        self.fail_connected_reason = ''
                        #para que le de tiempo a los eventos a quedarse registrados hay que esperar un poquillo, ya
                        #que se arranca otro thread
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
                    log.error('connection to hypervisor {} fail with unexpected error: {}'.format(self.hostname,e))
                    log.error('libvirt uri: {}'.format(self.uri))
                    self.set_status(HYP_STATUS_ERROR_WHEN_CONNECT)
                    self.fail_connected_reason = 'connection to hypervisor {} fail with unexpected error'.format(self.hostname)
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


    def set_status(self,status_code):
        if status_code > 1:
            self.connected = True
        else:
            self.connected = False

        #set_hyp_status(self.hostname,status_code)
        
    

    def get_hyp_info(self):

        libvirt_version = str(self.conn.getLibVersion())
        self.info['libvirt_version'] = '{}.{}.{}'.format(int(libvirt_version[-9:-6]),
                                              int(libvirt_version[-6:-3]),
                                              int(libvirt_version[-3:]))

        qemu_version = str(self.conn.getVersion())
        self.info['qemu_version'] = '{}.{}.{}'.format(int(qemu_version[-9:-6]),
                                              int(qemu_version[-6:-3]),
                                              int(qemu_version[-3:]))

        inf=self.conn.getInfo()
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

        if tree.xpath('/sysinfo/processor/entry[@name="socket_destination"]'):
            self.info['cpu_model'] = tree.xpath('/sysinfo/processor/entry[@name="socket_destination"]')[0].text

        if tree.xpath('/sysinfo/system/entry[@name="manufacturer"]'):
            self.info['motherboard_manufacturer'] = tree.xpath('/sysinfo/system/entry[@name="manufacturer"]')[0].text

        if tree.xpath('/sysinfo/system/entry[@name="product"]'):
            self.info['motherboard_model'] = tree.xpath('/sysinfo/system/entry[@name="product"]')[0].text

        if tree.xpath('/sysinfo/memory_device'):
            self.info['memory_banks'] = len(tree.xpath('/sysinfo/memory_device'))
            self.info['memory_type'] = tree.xpath('/sysinfo/memory_device/entry[@name="type"]')[0].text
            self.info['memory_speed'] = tree.xpath('/sysinfo/memory_device/entry[@name="speed"]')[0].text

        xml = self.conn.getCapabilities()
        parser = etree.XMLParser(remove_blank_text=True)
        tree = etree.parse(StringIO(xml), parser)

        if tree.xpath('/capabilities/host/cpu/model'):
            self.info['cpu_model_type'] = tree.xpath('/capabilities/host/cpu/model')[0].text

        if tree.xpath('/capabilities/guest/arch/domain[@type="kvm"]/machine[@canonical]'):
            self.info['kvm_type_machine_canonical'] = \
                tree.xpath('/capabilities/guest/arch/domain[@type="kvm"]/machine[@canonical]')[0].get('canonical')


    def define_and_start_paused_xml(self,xml_text):
        #todo alberto: faltan todas las excepciones, y mensajes de log,
        # aquí hay curro y es importante, porque hay que mirar si los discos no están
        # si es un error de conexión con el hypervisor...
        #está el tema de los timeouts...
        #TODO INFO TO DEVELOPER: igual se podría verificar si arrancando el dominio sin definirlo
        # con la opción XML_INACTIVE sería suficiente
        # o quizás lo mejor sería arrancar con createXML(libvirt.VIR_DOMAIN_START_PAUSED)
        xml_stopped = ''
        xml_started = ''
        try:
            d=self.conn.defineXML(xml_text)
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
        """
        if self.connected:
            ##TODO INFO TO DEVELOPER ==> haría falta poner un try por si se ha perdido la conexión??
            ids = self.conn.listDomainsID()
            domains={}
            for id in ids:
                domain = self.conn.lookupByID(id)
                name = domain.name()
                domains[name]=domain

            self.domains=domains


    # def hyp_worker_thread(self,queue_worker):
    #     NOT USED
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

    def get_load(self,l_stats=False,now=False):
        self.domain_stats=dict()
        self.load=dict()

        if self.connected:
            cpu_load = self.conn.getCPUStats(libvirt.VIR_NODE_CPU_STATS_ALL_CPUS)
            l=self.conn.getMemoryStats(-1,0)
            #todo VER QUE HACEMOS CON ESTO...
            self.load['cpu_load'] = cpu_load
            self.load['ram_cached'] = l['cached']
            self.load['ram_free'] = l['free']

            self.load['free_ram_total'] = l['cached'] + l['free']
            self.load['percent_free'] = round(float(self.load['free_ram_total'])*100/l['total'],2)

            if not l_stats:

                l_stats = self.conn.getAllDomainStats(flags=libvirt.VIR_CONNECT_GET_ALL_DOMAINS_STATS_ACTIVE)
                now = time.time()

            if l_stats:
                self.load['total_vm'] = len(l_stats)

                ## getFreeMemory in MB
                self.load['free_memory'] = int(self.conn.getFreeMemory() / (1024 * 1024))
                vm_mem_max_total = 0
                vm_mem_with_ballon_total = 0
                vm_vcpus_total = 0

                for r in l_stats:
                    try:
                        #todo VER QUE HACEMOS SI ESTÁ EN PAUSA, YA QUE TIENE RAM RESERVADA??
                        # libvirt.VIR_DOMAIN_PAUSED
                        domain_sysname = r[0].name()
                        domain_state  = r[0].state()
                        self.domain_stats[domain_sysname]=dict()
                        self.domain_stats[domain_sysname]['raw_stats'] = r[1]
                        self.domain_stats[domain_sysname]['hyp'] = self.hostname
                        state,reason = state_and_cause_to_str(domain_state[0],domain_state[1])
                        self.domain_stats[domain_sysname]['state'] = state
                        self.domain_stats[domain_sysname]['state_reason'] = reason
                        try:
                            self.domain_stats[domain_sysname]['procesed_stats'] = new_dict_from_raw_dict_stats(r[1])
                        except Exception as e:
                            log.warning('Procesing stats for domain {} with state {}({}) failed'.format(domain_sysname,state,reason))

                        #stats_json = json.dumps(r[1])
                        if 'cpu.time' in r[1].keys():
                            time_cpu = r[1]['cpu.time']
                        else:
                            time_cpu = 0

                        #self.domain_stats[domain_sysname]['cputime'] = time_cpu

                        if r[0].state()[0] == libvirt.VIR_DOMAIN_RUNNING:
                            vm_mem_max_total += r[1]['balloon.maximum']
                            if 'balloon.current' in r[1].keys():
                                vm_mem_with_ballon_total += r[1]['balloon.current']
                            vm_vcpus_total += r[1]['vcpu.current']
                    except libvirt.libvirtError as e:

                        log.error('libvirt Error getting domains in hyp class. Other thread stop domain?? {}'.format(e))
                    except Exception as e:
                        log.error(e)
                self.load['vm_mem_max_total'] = int(vm_mem_max_total / 1024)
                self.load['vm_mem_with_ballon_total'] = int(vm_mem_with_ballon_total / 1024)
                self.load['vm_vcpus_total'] = vm_vcpus_total



            else:
                #log.debug('hyp {} have no vms or stats has failed'.format(self.hostname))
                pass

    def get_eval_statistics(self):
        self.get_load()
        if not self.last_load:
            self.last_load = self.load
            cpu_percent_free = 100
        else:
            cpu_percent = calcule_cpu_stats(self.last_load['cpu_load'], self.load['cpu_load'])[0]
            cpu_percent_free = cpu_percent["idle"]

        # Do mean of 3 cpu values. Doing this because CPU load is very sensitive.
        if len(self.cpu_percent_free) == 3:
            self.cpu_percent_free.pop()
        self.cpu_percent_free.append(cpu_percent_free)

        self.last_load = self.load
        data = {"cpu_percent_free":round(mean(self.cpu_percent_free),2),
                "ram_percent_free":self.load["percent_free"]}
        return data

