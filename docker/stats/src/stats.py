# December 2020
# IsardVDI project
# Authors: Alberto Larraz Dalmases
# License: AGPLv3
# coding=utf-8


import time
import copy
import os
import libvirt
import traceback

from influxdb_client import InfluxDBClient, Point, WritePrecision
from influxdb_client.client.write_api import SYNCHRONOUS,WriteOptions

from datetime import datetime
from pprint import pprint
from flatten_dict import flatten, unflatten

from lib.sockets import get_socket_stats
from lib.domstats import domain_stats_as_dicts, translate_socket_stats_to_domains

MAX_DOMAINS_BULK_EXTRACT = int(os.environ.get('STATS_MAX_DOMAINS_BULK_EXTRACT', 100))
INTERVAL_STATS = int(os.environ.get('STATS_INTERVAL_STATS', 10))
GRACE_NOVIEWER_SHUTDOWN_TIME = int(os.environ.get('STATS_GRACE_NOVIEWER_SHUTDOWN_TIME',1800))

CONTAINER_NAME_HYP = 'isard-hypervisor'
HYP_NAME = os.environ.get('DOMAIN')

INFLUXDB_ADMIN_TOKEN_SECRET=os.environ.get('INFLUXDB_ADMIN_TOKEN_SECRET')
INFLUX_HOST = os.environ.get('INFLUXDB_HOST', 'isard-influxdb')
INFLUX_PORT = int(os.environ.get('STATS_INFLUX_PORT', 8086))
INFLUX_RETRY_PERIOD = int(os.environ.get('STATS_INFLUX_RETRY_PERIOD', 2))

INFLUX_BUCKET = os.environ.get('STATS_INFLUX_BUCKET', 'isardvdi')
INFLUX_ORG    = os.environ.get('STATS_INFLUX_ORG',    'isardvdi')
INFLUX_TOKEN  = os.environ.get('STATS_INFLUX_TOKEN',  'xq0Z3MP5ujxrQxtMGxgPiijH9xpuxkyP04R6At/V+g4=')



class HypStats():
    """Extract and process information from libvirt hypervisor,
    extract and process socket information to analyze viewers traffic
    and send it to time series database linke InfluxDB or dataframes files"""

    def __init__(self,
                 hyp_hostname,
                 hyp_user='root',
                 hyp_port=22,
                 max_domains_bulk_extract=None,
                 interval_stats=None,
                 send_to_influx=True,
                 type_conn_ss='docker'):
        """
        Parameters
        ----------
        hyp_hostname : str
            hostname of libvirt hypervisor
        hyp_user : str, optional
            user to connect to libvirt hypervisor (default is root)
            no password needed, you need to access without password
            using ssh authorized keys or localhost without password
        hyp_port : int, optional
            ssh port to connect to libvirt hypervisor
        max_domains_bulk_extract: int, optional
            if there are many domains in hypervisor the time to extract
            all stats from all domains can be high and impact in hypervisor performance
            you can limit the number of domains to extract each iteration, and wait
            several interval_stats to obtain all the domain stats
            if is None, the default value is set to environment
            variable or constant MAX_DOMAINS_BULK_EXTRACT
            if is 0 extract all the domains
        interval_stats: int, optional
            time in seconds between samples, wait to next interval_stats to start stats extraction
            if is None, the default value is set to environment
            variable or constant INTERVAL_STATS
        send_to_influx: bool, optional
            send stats to influxDB, the configuration to open influxdb connection use
            constants or environment variables: INFLUX_HOST, INFLUX_PORT, INFLUX_USER,
            INFLUX_PWD, INFLUX_DB
        type_conn_ss: str, optional
            type of connection to extract socket info:
            'docker' => use DockerClient to run ss command
            'ssh' => connect with paramiko and run ss command via ssh
        """

        self.hyp_hostname = hyp_hostname
        self.hyp_port = hyp_port
        self.hyp_user = hyp_user
        if max_domains_bulk_extract is None:
            self.max_domains_bulk_extract = MAX_DOMAINS_BULK_EXTRACT
        else:
            self.max_domains_bulk_extract = max_domains_bulk_extract

        if interval_stats is None:
            self.interval_stats = INTERVAL_STATS
        else:
            self.interval_stats = interval_stats

        # wait to connection to libvirt hypervisor is alive
        self.conn = False
        self.wait_to_libvirt_connection_is_alive()

        # last ID of extracted domain
        self.last_domain_id = 0

        self.client_influxdb = False
        if send_to_influx is True:
            self.write_options=WriteOptions(batch_size=1000,
                                            flush_interval=1000,
                                            jitter_interval=0,
                                            retry_interval=5000,
                                            max_retries=5,
                                            max_retry_delay=30_000,
                                            exponential_base=2)
            ### wait for influx
            while True:
                self.client_influxdb = InfluxDBClient(url=f"http://{INFLUX_HOST}:{INFLUX_PORT}", token=INFLUXDB_ADMIN_TOKEN_SECRET)
                health = self.client_influxdb.health()
                if health.status == 'pass':
                    print('influxdb connection ok: ' + health.message)
                    self.client_influxdb.close()
                    break
                else:
                    print(f'error with influxdb connection with status {health.status}: {health.message}')
                    print(f'retry connect to influxdb in {INFLUX_RETRY_PERIOD}s')
                    time.sleep(INFLUX_RETRY_PERIOD)




        self.grace_noviewer_shutdown_time = os.environ.get('GRACE_NOVIEWER_SHUTDOWN_TIME', GRACE_NOVIEWER_SHUTDOWN_TIME)

        # initialize vars
        self.stop = False
        self.out_raw = False
        self.d_socket_by_port = {}
        self.d_domains_viewers_stats = {}
        self.domain_info = False
        self.total_domains = 0
        self.type_conn_ss = type_conn_ss
        self.domains_noviewer_grace_time = {}
        self.now_domains_with_viewers = {}
        self.domains_noviewer_nograce_time = {}

    def wait_to_libvirt_connection_is_alive(self):
        self.conn = False
        while self.conn is False:
            if self.open_libvirt_connection() is False:
                print(f'waiting {self.interval_stats} seconds to try connect to libvirt hypervisor')
                time.sleep(self.interval_stats)

    def open_libvirt_connection(self):
        if self.hyp_hostname == 'localhost':
            uri = "qemu:///system"
        else:
            uri = 'qemu+ssh://{}@{}:{}/system'.format(self.hyp_user, self.hyp_hostname, self.hyp_port)
        try:
            self.conn = libvirt.openReadOnly(uri)
            return True
        except Exception as e:
            print(f'libvirt connection to hypervirsor failed. uri: {uri}')
            print(f'reason of failed hypervisor connection: {e}')
            return False

    def stats_loop(self):
        while self.stop is False:

            self.launch_actions_in_iterations()

            # SLEEP AND WAKE UP TO NEXT ITERATION
            time_end_iteration = time.time()
            next_iteration = int(time_end_iteration) - int(time_end_iteration) % int(self.interval_stats) + int(
                self.interval_stats)
            sleep_to_next_iteration = next_iteration - time_end_iteration
            time.sleep(sleep_to_next_iteration)
            ## TODO send to influx (time_end_iteration - start_time) and (time_end_iteration - start_time) / self.interval_stats)

        self.conn.close()

    def launch_actions_in_iterations(self):
        start_time = time.time()
        print(datetime.fromtimestamp(start_time))
        phases = {}
        #TODO: send time elapsed between phases to influxDB
        # PHASE 1: EXTRACT LIBVIRT STATS
        phases[1] = result = self.extract_stats_libvirt()
        print('PHASE 1 - {}: extract libvirt stats ({} seconds)'.format('ok' if result is True else 'ko',
                                                                        round(time.time() - start_time, 3)))
        if self.total_domains > 0:
            # PHASE 2: EXTRACT STATS FROM SOCKETS
            phases[2] = result = self.extract_socket_stats()
            print('PHASE 2 - {}: extract socket counters ({} seconds)'.format('ok' if result is True else 'ko',
                                                                              round(time.time() - start_time, 3)))
            # PHASE 3: PROCESS INFO FROM DOMAIN STATS IN DICTS
            phases[3] = result = self.process_domain_info()
            print('PHASE 3 - {}: process domain info ({} seconds)'.format('ok' if result is True else 'ko',
                                                                          round(time.time() - start_time, 3)))
            # PHASE 4: JOIN SOCKETS INFO WITH DOMAINS INFO AND UPDATE VIEWERS DICTS WITH DOMAINS WITH OR WITHOUT GRACE TIME
            if phases[3] is True and phases[2] is True:
                phases[4] = result = self.process_socket_info()
                print('PHASE 4 - {}: process viewers info ({} seconds)'.format('ok' if result is True else 'ko',
                                                                               round(time.time() - start_time, 3)))
            if phases[2] is True and phases[3] is True and phases[4] is True:
                # PHASE 5: PROCESS STATS, SELECT FIELDS AND
                phases[5] = result = self.process_stats()
                print('PHASE 5 - {}: process stats ({} seconds)'.format('ok' if result is True else 'ko',
                                                                        round(time.time() - start_time, 3)))
        # PHASE 6: SEND TO INFLUX
        phases[6] = result = self.send_to_influx(start_time)
        print('PHASE 6 - {}: process stats ({} seconds)'.format('ok' if result is True else 'ko',
                                                                    round(time.time() - start_time, 3)))


    def send_to_influx(self,start_time):
        data = []
        start_time = int(start_time * 1000 * 1000 * 1000)  # nanoseconds
        try:
            flatted_hyp_stats = flatten({'cpu': self.out_raw['cpu'],
                                         'memory': self.out_raw['memory'],
                                         'total_domains': self.total_domains,
                                         },
                                        reducer='underscore',
                                        enumerate_types=(list,))

            data.append({
                "measurement": "hypervisors",
                "tags": {
                    "hypervisor": HYP_NAME,
                },
                "fields": flatted_hyp_stats,
                "time": start_time
            })
            if self.total_domains > 0:
                domains_info = self.domain_info['d_domains_info']
                for id_domain,d_stats in self.processed_stats.items():
                    domain_info = domains_info[id_domain]
                    stats = self.processed_stats[id_domain]
                    flatted = flatten(stats,reducer='underscore',enumerate_types=(list,))
                    data.append({
                        "measurement": "domains",
                        "tags": {
                            "hypervisor": HYP_NAME,
                            "category": domain_info['category'],
                            "group": domain_info['group'],
                            "user": domain_info['group'],
                            "template": domain_info['template'],
                            "id_domain": id_domain,
                        },
                        "fields": flatted,
                        "time": start_time
                    })
        except Exception as e:
            print('Exception preparing flatten dicts to send to influx')
            print('Traceback: \n .{}'.format(traceback.format_exc()))
            print('Exception message: {}'.format(e))
            return False

        try:
            #self.write_api.write(INFLUX_BUCKET, INFLUX_ORG, data)
            #self.write_api = client.write_api(write_options=SYNCHRONOUS)
            with InfluxDBClient(url=f"http://{INFLUX_HOST}:{INFLUX_PORT}", token=INFLUXDB_ADMIN_TOKEN_SECRET) as _client:
                # with _client.write_api(write_options=self.write_options) as _write_client:
                with _client.write_api(write_options=SYNCHRONOUS) as _write_client:
                    _write_client.write(INFLUX_BUCKET, INFLUX_ORG, data)

        except Exception as e:
            print('Exception sending data to InfluxDB')
            print('Traceback: \n .{}'.format(traceback.format_exc()))
            print('Exception message: {}'.format(e))
            return False


        # try:
        #     client.write_points(data, database=INFLUX_DB, time_precision='ms', batch_size=10000, protocol='json')
        # except Exception as e:
        #     print('Exception sending points to InfluxDB')
        #     print('Traceback: \n .{}'.format(traceback.format_exc()))
        #     print('Exception message: {}'.format(e))
        #     return False
        #
        # try:
        #     client.close()
        # except Exception as e:
        #     print('Exception clossing InfluxDB connection')
        #     print('Traceback: \n .{}'.format(traceback.format_exc()))
        #     print('Exception message: {}'.format(e))
        #     return False

        return True

    def process_stats(self):
        self.processed_stats = {}
        for domain, d_stats in self.out_raw['domains_stats']:
            try:
                unflatted = unflatten(d_stats,splitter='dot')
                id_domain = domain.name()
                d_processed_stats = {}
                if 'net' in unflatted.keys():
                    d_processed_stats['nets']={}
                    d_processed_stats['nets']['tx_bytes'] = sum([unflatted['net'][str(i)]['tx']['bytes'] for i in range(unflatted['net']['count'])])
                    d_processed_stats['nets']['rx_bytes'] = sum([unflatted['net'][str(i)]['rx']['bytes'] for i in range(unflatted['net']['count'])])
                    d_processed_stats['nets']['tx_pkts']  = sum([unflatted['net'][str(i)]['tx']['pkts'] for i in range(unflatted['net']['count'])])
                    d_processed_stats['nets']['rx_pkts']  = sum([unflatted['net'][str(i)]['rx']['pkts'] for i in range(unflatted['net']['count'])])
                    d_processed_stats['nets']['tx_errs']  = sum([unflatted['net'][str(i)]['tx']['errs'] for i in range(unflatted['net']['count'])])
                    d_processed_stats['nets']['rx_errs']  = sum([unflatted['net'][str(i)]['rx']['errs'] for i in range(unflatted['net']['count'])])
                    d_processed_stats['nets']['tx_drop']  = sum([unflatted['net'][str(i)]['tx']['drop'] for i in range(unflatted['net']['count'])])
                    d_processed_stats['nets']['rx_drop']  = sum([unflatted['net'][str(i)]['rx']['drop'] for i in range(unflatted['net']['count'])])

                d_processed_stats['vcpus']={}

                d_processed_stats['vcpus']['current'] = unflatted['vcpu']['current']
                d_processed_stats['vcpus']['cpu_time'] = {i:unflatted['vcpu'][str(i)]['time'] for i in range(unflatted['vcpu']['current'])}
                d_processed_stats['vcpus']['sum_cpu_time'] = sum([unflatted['vcpu'][str(i)]['time'] for i in range(unflatted['vcpu']['current'])])
                d_processed_stats['vcpus']['cpu_wait'] = {i:unflatted['vcpu'][str(i)]['wait'] for i in range(unflatted['vcpu']['current'])}
                d_processed_stats['vcpus']['sum_cpu_wait'] = sum([unflatted['vcpu'][str(i)]['wait'] for i in range(unflatted['vcpu']['current'])])

                if 'balloon' in unflatted.keys():
                    d_processed_stats['balloon'] = unflatted['balloon']

                if 'block' in unflatted.keys():
                    d_processed_stats['blocks']={}
                    d_processed_stats['blocks']['rd_bytes'] =   sum([unflatted['block'][str(i)]['rd']['bytes'] for i in range(unflatted['block']['count'])])
                    d_processed_stats['blocks']['wr_bytes'] =   sum([unflatted['block'][str(i)]['wr']['bytes'] for i in range(unflatted['block']['count'])])
                    d_processed_stats['blocks']['rd_reqs']  =   sum([unflatted['block'][str(i)]['rd']['reqs']  for i in range(unflatted['block']['count'])])
                    d_processed_stats['blocks']['wr_reqs']  =   sum([unflatted['block'][str(i)]['wr']['reqs']  for i in range(unflatted['block']['count'])])
                    d_processed_stats['blocks']['fl_reqs']  =   sum([unflatted['block'][str(i)]['fl']['reqs']  for i in range(unflatted['block']['count'])])
                    d_processed_stats['blocks']['rd_times'] =   sum([round(unflatted['block'][str(i)]['rd']['times'] / 1000000000, 3) for i in range(unflatted['block']['count'])])
                    d_processed_stats['blocks']['wr_times'] =   sum([round(unflatted['block'][str(i)]['wr']['times'] / 1000000000, 3) for i in range(unflatted['block']['count'])])
                    d_processed_stats['blocks']['fl_times'] =   sum([round(unflatted['block'][str(i)]['fl']['times'] / 1000000000, 3) for i in range(unflatted['block']['count'])])
                    d_processed_stats['blocks']['allocation'] = sum([unflatted['block'][str(i)]['allocation']  for i in range(unflatted['block']['count']) if unflatted['block'][str(i)]['path'].split('/')[-1].find('qcow')>0])
                    #TODO REVIEW SAME KEY
                    d_processed_stats['blocks']['capacity'] =   sum([unflatted['block'][str(i)]['allocation']  for i in range(unflatted['block']['count']) if unflatted['block'][str(i)]['path'].split('/')[-1].find('qcow')>0])
                    d_processed_stats['blocks']['physical'] =   sum([unflatted['block'][str(i)]['allocation']  for i in range(unflatted['block']['count']) if unflatted['block'][str(i)]['path'].split('/')[-1].find('qcow')>0])

                d_processed_stats['viewers'] = self.d_domains_viewers_stats[id_domain]

                self.processed_stats[id_domain] = d_processed_stats
            except Exception as e:
                self.processed_stats = {}
                print('error processing stats')
                print('Traceback: \n .{}'.format(traceback.format_exc()))
                print('Exception message: {}'.format(e))
                return False
        return True


    def process_socket_info(self):
        start_time = time.time()
        try:
            self.d_domains_viewers_stats = translate_socket_stats_to_domains(self.domain_info['d_domains_info'],
                                                                             self.d_socket_by_port)
        except Exception as e:
            print('error extracting stats from libvirt')
            print('Traceback: \n .{}'.format(traceback.format_exc()))
            print('Exception message: {}'.format(e))
            return False

        try:
            # identify domains with_viewers and with no_viewers
            set_domains_with_viewers = set([k for k, v in self.d_domains_viewers_stats.items() if v['total_connections'] > 0])
            set_domains_with_no_viewers = set(self.d_domains_viewers_stats.keys()) - set_domains_with_viewers

            # identify new domains with viewers and domains that have disconnect viewers
            set_previous_domains_with_viewers = set(self.now_domains_with_viewers.keys())
            set_viewers_switch_off = set_previous_domains_with_viewers - set_domains_with_viewers
            set_viewers_switch_on = set_domains_with_viewers - set_previous_domains_with_viewers

            # if domain was started, with no viewer in grace time period
            for k in set_viewers_switch_on:
                if k in self.domains_noviewer_grace_time.keys():
                    self.domains_noviewer_grace_time.pop(k)
                # update timestamp since viewer is connected
                self.now_domains_with_viewers[k] = {'timestamp_viewer_on': start_time}

            # if domain is just started and viewer connected
            for k in set_domains_with_viewers:
                if k not in self.now_domains_with_viewers.keys():
                    self.now_domains_with_viewers[k] = {'timestamp_viewer_on': start_time}

            # if viewer is disconnected update timestamp and dictionary
            for k in set_viewers_switch_off:
                if k not in self.now_domains_with_viewers.keys():
                    self.now_domains_with_viewers.pop(k)
                self.domains_noviewer_grace_time[k] = {'timestamp_viewer_off': start_time}

            # if new domain without viewer
            for k in set_domains_with_no_viewers:
                if k not in self.domains_noviewer_grace_time.keys():
                    self.domains_noviewer_grace_time[k] = {'timestamp_viewer_off': start_time}

            # MOVE from self.domains_noviewer_grace_time to domains_noviewer_nograce_time
            pop_keys_from_domains_noviewer_grace_time = []
            for k, v in self.domains_noviewer_grace_time.items():
                if v['timestamp_viewer_off'] < (start_time - self.grace_noviewer_shutdown_time):
                    self.domains_noviewer_nograce_time[k] = {'timestamp_to_shutdown': start_time}
                    pop_keys_from_domains_noviewer_grace_time.append(k)

            for k in pop_keys_from_domains_noviewer_grace_time:
                self.domains_noviewer_grace_time.pop(k)

            return True
        except Exception as e:
            print('error processing info from viewers')
            print('Traceback: \n .{}'.format(traceback.format_exc()))
            print('Exception message: {}'.format(e))
            self.out_raw = False
            self.total_domains = -1
            return False

    def process_domain_info(self):
        try:
            # TODO if domains xml are analyzed it is not necessary to reanalyze every loop
            # TODO if domains stats are not retrieved, domain objects of all domains are available in out_raw['domains']
            self.domain_info = {}
            self.domain_info['d_stats'], \
            self.domain_info['d_domains_info'], \
            self.domain_info['d_domains_objects'], \
            self.domain_info['d_domains_xml'] = domain_stats_as_dicts(self.out_raw['domains_stats'])
            return True
        except Exception as e:
            self.domain_info = False
            print('error processing domain info')
            print('Traceback: \n .{}'.format(traceback.format_exc()))
            print('Exception message: {}'.format(e))
            return False


    def extract_socket_stats(self):
        start_time = time.time()
        try:
            self.d_socket_by_port = get_socket_stats(type_conn_ss=self.type_conn_ss,
                                                     container_name=CONTAINER_NAME_HYP,
                                                     host=self.hyp_hostname,
                                                     port=self.hyp_port,
                                                     username=self.hyp_user,
                                                     )
            return True
        except Exception as e:
            self.d_socket_by_port = False
            print('error extracting socket info with ss')
            print('Traceback: \n .{}'.format(traceback.format_exc()))
            print('Exception message: {}'.format(e))
            return False

    def extract_stats_libvirt(self):
        start_time = time.time()
        if self.conn.isAlive() < 1:
            self.wait_to_libvirt_connection_is_alive()

        out_domains_raw = []
        try:
            out_cpu = self.conn.getCPUStats(libvirt.VIR_NODE_CPU_STATS_ALL_CPUS)
            out_memory = self.conn.getMemoryStats(-1, 0)
            # if ID == -1 domain is defined but Stopped
            list_all_domains = [d for d in self.conn.listAllDomains() if d.ID() >= 0]

            if len(list_all_domains) > 0:
                # sort by ID
                list_all_domains.sort(key=lambda d: d.ID())
                if self.max_domains_bulk_extract == 0 or len(list_all_domains) <= self.max_domains_bulk_extract:
                    # out_domains_raw = self.conn.getAllDomainStats(flags=libvirt.VIR_CONNECT_LIST_DOMAINS_ACTIVE)
                    out_domains_raw = self.conn.domainListGetStats(list_all_domains)
                    self.last_domain_id = 0
                else:
                    next_domains_to_extract = [d for d in list_all_domains if d.ID() > self.last_domain_id][
                                              :self.max_domains_bulk_extract]
                    if len(next_domains_to_extract) < self.max_domains_bulk_extract:
                        we_need_more_domains = self.max_domains_bulk_extract - len(next_domains_to_extract)
                        next_domains_to_extract += list_all_domains[:we_need_more_domains]
                    # EXTRACT STATS FROM DOMAINS IN LIST
                    out_domains_raw = self.conn.domainListGetStats(next_domains_to_extract)
                    self.last_domain_id = next_domains_to_extract[-1].ID()
                    print('###### stats extracted ######')
                    pprint([d.ID() for d in next_domains_to_extract])
                    print(f'last_domain_id: {self.last_domain_id}')

            else:
                self.total_domains = 0

            time_elapsed = round(time.time() - start_time, 3)
            self.out_raw = {
                'cpu': out_cpu,
                'memory': out_memory,
                'domains': list_all_domains,
                'domains_stats': out_domains_raw,
                'time_elapsed': time_elapsed,
            }
            self.total_domains = len(list_all_domains)
            return True


        except Exception as e:
            print('error extracting stats from libvirt')
            print('Traceback: \n .{}'.format(traceback.format_exc()))
            print('Exception message: {}'.format(e))
            self.out_raw = False
            self.total_domains = -1
            return False


