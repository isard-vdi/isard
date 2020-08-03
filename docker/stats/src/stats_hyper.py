import docker
import libvirt
import time
import os
import socket
import xmltodict
import logging
from collections import OrderedDict
from datetime import datetime
import sentry_sdk
from sentry_sdk.integrations.logging import LoggingIntegration

from lib.carbon import Carbon
from lib.functions import timeit
from lib.sockets import ss_detail
from lib.domstats import domain_stats_as_dicts, domstats_libvirt, domstats_with_virsh_docker_exec

# All of this is already happening by default!
sentry_logging = LoggingIntegration(
    level=logging.INFO,        # Capture info and above as breadcrumbs
    event_level=logging.ERROR  # Send errors as events
)
sentry_sdk.init(
    dsn="https://3bcfae76fb6e437fa03e620675375a5c@o379671.ingest.sentry.io/5221821",
    integrations=[sentry_logging]
)

#sentry_sdk.init("https://3bcfae76fb6e437fa03e620675375a5c@o379671.ingest.sentry.io/5221821")














for j in range(6):
    now = '{0:%Y-%m-%d_%H-%M-%S}'.format(datetime.now())
    print(f"\n##SLEEPING 10 MIN FROM {now}  ##########")
    time.sleep(600)
    for i in range(20):
        now = '{0:%Y-%m-%d_%H-%M-%S}'.format(datetime.now())
        print(f"\n####### {now}  ##########")
        raw_stats_domains, raw_stats_cpu, raw_stats_memory = domstats_libvirt()
        d_stats, d_domains_info, d_domains_objects, d_xml = domain_stats_as_dicts(raw_stats_domains)
        print('*** num_desktops: {}'.format(len(d_domains_objects)))
        time.sleep(20)
        raw_ss = ss_detail()
        time.sleep(10)





class StatsHyper():
    def __init__(self,period_for_stats=30,delay_between_stats_and_ss=2):
        self.stop = False
        self.period_for_stats = period_for_stats
        self.delay_between_stats_and_ss = delay_between_stats_and_ss
        self.d_stats = {}
        self.d_stats['domains'] = {}
        self.start_time = datetime.now()
        pass

    def run(self):
        while self.stop is False:
            previous = datetime.now()
            now = '{0:%Y-%m-%d_%H-%M-%S}'.format(previous)
            print(f"\n####### {now}  ##########")
            raw_stats_domains, raw_stats_cpu, raw_stats_memory = domstats_libvirt()
            d_stats, d_domains_info, d_domains_objects, d_xml = domain_stats_as_dicts(raw_stats_domains)
            print('*** num_desktops: {}'.format(len(d_domains_objects)))
            after = datetime.now()
            elapsed = (after-previous).total_seconds()
            if elapsed > (self.period_for_stats - self.delay_between_stats_and_ss):
                logging.warning('Running stats from libvirt greater than ')
            time.sleep()
            raw_ss = ss_detail()
            time.sleep(10)

    def process_stats(self):
        pass


    def process_domains_stats(self, raw_stats_domains):
        if len(self.info) == 0:
            self.get_hyp_info()
        d_all_domain_stats = raw_stats_domains

        previous_domains = set(self.stats_domains.keys())
        current_domains  = set(d_all_domain_stats.keys())
        add_domains      = current_domains.difference(previous_domains)
        remove_domains   = previous_domains.difference(current_domains)

        for d in remove_domains:
            del self.stats_domains[d]
            del self.stats_raw_domains[d]
            del self.stats_domains_now[d]
            # TODO: buen momento para asegurarse que la máquina se quedó en Stopped,
            # podríamos ahorrarnos esa  comprobación en el thread broom ??

            #TODO: también es el momento de guardar en histórico las estadísticas de ese dominio,
            # esto nos permite hacer análisis posterior

        for d in add_domains:
            self.stats_domains[d] = {
                'started'              : datetime.utcfromtimestamp(raw_stats['time_utc']),
                'near_df'              : pd.DataFrame(),
                'medium_df'            : pd.DataFrame(),
                'long_df'              : pd.DataFrame(),
                'boot_df'              : pd.DataFrame(),
                'last_timestamp_near'  : False,
                'last_timestamp_medium': False,
                'last_timestamp_long'  : False,
                'means_near'           : False,
                'means_medium'         : False,
                'means_long'           : False,
                'means_all'            : False,
                'means_boot'           : False
            }
            self.stats_raw_domains[d] = deque(maxlen=self.stats_queue_lenght_domains_raw_stats)
            self.stats_domains_now[d] = dict()

        sum_vcpus = 0
        sum_memory = 0
        sum_domains = 0
        sum_memory_max = 0
        sum_disk_wr = 0
        sum_disk_rd = 0
        sum_net_tx = 0
        sum_net_rx = 0
        sum_disk_wr_reqs = 0
        sum_disk_rd_reqs = 0
        mean_vcpu_load = 0
        mean_vcpu_iowait = 0

        for d, raw in d_all_domain_stats.items():

            raw['stats']['now_utc_time'] = raw_stats['time_utc']
            raw['stats']['now_datetime'] = datetime.utcfromtimestamp(raw_stats['time_utc'])

            self.stats_raw_domains[d].append(raw['stats'])


            if len(self.stats_raw_domains[d]) > 1:

                sum_domains += 1

                d_stats = {}

                current = self.stats_raw_domains[d][-1]
                previous = self.stats_raw_domains[d][-2]

                delta = current['now_utc_time'] - previous['now_utc_time']
                if delta == 0:
                    log.error('same value in now_utc_time, must call get_stats_from_libvirt')
                    break

                timestamp = datetime.utcfromtimestamp(current['now_utc_time'])
                d_stats['time_utc'] = current['now_utc_time']

                sum_vcpus += current['vcpu.current']

                #d_stats['cpu_load'] = round(((current['cpu.time'] - previous['cpu.time']) / 1000000000 / self.info['cpu_threads'])*100,3)
                if current.get('cpu.time') and previous.get('cpu.time'):
                    d_stats['cpu_load'] = round((current['cpu.time'] - previous['cpu.time']) / 1000000000 / self.info['cpu_threads'],3)

                d_balloon={k:v/1024 for k,v in current.items() if k[:5] == 'ballo' }

                # balloon is running and monitorized if balloon.unused key is disposable
                if 'balloon.unused' in d_balloon.keys():
                    mem_used    = round((d_balloon['balloon.current']-d_balloon['balloon.unused'])/1024.0, 3)
                    mem_balloon = round(d_balloon['balloon.current'] / 1024.0, 3)
                    mem_max = round(d_balloon['balloon.maximum'] / 1024.0, 3)

                elif 'balloon.maximum' in d_balloon.keys():
                    mem_used =    round(d_balloon['balloon.maximum'] / 1024.0 ,3)
                    mem_balloon = round(d_balloon['balloon.maximum'] / 1024.0, 3)
                    mem_max = round(d_balloon['balloon.maximum'] / 1024.0, 3)

                else:
                    mem_used = 0
                    mem_balloon = 0
                    mem_max = 0

                d_stats['mem_load']    = round(mem_used / (self.info['memory_in_MB']/1024), 2)
                d_stats['mem_used']    = mem_used
                d_stats['mem_balloon'] = mem_balloon
                d_stats['mem_max']     = mem_max

                sum_memory += mem_used
                sum_memory_max += mem_max

                vcpu_total_time = 0
                vcpu_total_wait = 0

                for n in range(current['vcpu.current']):
                    try:
                        vcpu_total_time += current['vcpu.' +str(n)+ '.time'] - previous['vcpu.' +str(n)+ '.time']
                        vcpu_total_wait += current['vcpu.' +str(n)+ '.wait'] - previous['vcpu.' +str(n)+ '.wait']
                    except KeyError:
                        vcpu_total_time = 0
                        vcpu_total_wait = 0

                d_stats['vcpu_load'] = round((vcpu_total_time / (delta * 1e9) / current['vcpu.current'])*100,2)
                d_stats['vcpu_iowait'] = round((vcpu_total_wait / (delta * 1e9) / current['vcpu.current'])*100,2)

                total_block_wr = 0
                total_block_wr_reqs = 0
                total_block_rd = 0
                total_block_rd_reqs = 0

                if 'block.count' in current.keys():
                    for n in range(current['block.count']):
                        try:
                            total_block_wr += current['block.'+str(n)+'.wr.bytes'] - previous['block.'+str(n)+'.wr.bytes']
                            total_block_rd += current['block.'+str(n)+'.rd.bytes'] - previous['block.'+str(n)+'.rd.bytes']
                            total_block_wr_reqs += current['block.'+str(n)+'.wr.reqs'] - previous['block.'+str(n)+'.wr.reqs']
                            total_block_rd_reqs += current['block.'+str(n)+'.rd.reqs'] - previous['block.'+str(n)+'.rd.reqs']
                        except KeyError:
                            total_block_wr = 0
                            total_block_wr_reqs = 0
                            total_block_rd = 0
                            total_block_rd_reqs = 0

                #KB/s
                d_stats['disk_wr'] = round(total_block_wr / delta / 1024,3)
                d_stats['disk_rd'] = round(total_block_rd / delta / 1024,3)
                d_stats['disk_wr_reqs'] = round(total_block_wr_reqs / delta,3)
                d_stats['disk_rd_reqs'] = round(total_block_rd_reqs / delta,3)
                sum_disk_wr      += d_stats['disk_wr']
                sum_disk_rd      += d_stats['disk_rd']
                sum_disk_wr_reqs += d_stats['disk_wr_reqs']
                sum_disk_rd_reqs += d_stats['disk_rd_reqs']

                total_net_tx = 0
                total_net_rx = 0

                if 'net.count' in current.keys():
                    for n in range(current['net.count']):
                        try:
                            total_net_tx += current['net.' +str(n)+ '.tx.bytes'] - previous['net.' +str(n)+ '.tx.bytes']
                            total_net_rx += current['net.' +str(n)+ '.rx.bytes'] - previous['net.' +str(n)+ '.rx.bytes']
                        except KeyError:
                            total_net_tx = 0
                            total_net_rx = 0

                d_stats['net_tx'] = round(total_net_tx / delta / 1000, 3)
                d_stats['net_rx'] = round(total_net_rx / delta / 1000, 3)
                sum_net_tx += d_stats['net_tx']
                sum_net_rx += d_stats['net_rx']

                self.stats_domains_now[d] = d_stats.copy()
                self.update_domain_means_and_data_frames(d, d_stats, timestamp)


        if len(self.stats_domains_now) > 0:
            try:
                mean_vcpu_load = sum([j['vcpu_load'] for j in self.stats_domains_now.values()]) / len(self.stats_domains_now)
                mean_vcpu_iowait   = sum([j['vcpu_iowait'] for j in self.stats_domains_now.values()]) / len(self.stats_domains_now)
            except KeyError:
                mean_vcpu_iowait = 0.0
                mean_vcpu_load = 0.0

        return sum_vcpus, sum_memory, sum_domains, sum_memory_max, sum_disk_wr, sum_disk_rd, \
               sum_disk_wr_reqs, sum_disk_rd_reqs, sum_net_tx, sum_net_rx, mean_vcpu_load, mean_vcpu_iowait


for i in range(20):
    start_time = time.time()
    domstats_raw = domstats_with_virsh_docker_exec()
    print("--- con docker exec %s seconds ---" % (time.time() - start_time))

    time.sleep(30)

    start_time = time.time()
    domstats_raw = domstats_libvirt()
    print("--- con libvirt python %s seconds ---" % (time.time() - start_time))

    start_time = time.time()
    #conn.getCPUStats(libvirt.VIR_NODE_CPU_STATS_ALL_CPUS)
    conn.getMemoryStats(-1, 0)
    print("--- con libvirt python %s seconds ---" % (time.time() - start_time))


    time.sleep(30)
