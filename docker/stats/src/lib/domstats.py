# import docker
import libvirt
import time
import os
import socket
import xmltodict
import logging
from collections import OrderedDict
from datetime import datetime
# import sentry_sdk
# from sentry_sdk.integrations.logging import LoggingIntegration
from lib.functions import timeit
from pprint import pprint

LIBVIRT_DEFAULT_URI="qemu:///system"
# HOSTNAME = os.environ['HOSTNAME']
HOSTNAME = "test"

#@timeit
def domstats_libvirt(uri=None):
    if uri is None:
        uri = LIBVIRT_DEFAULT_URI
    #conn = libvirt.open(uri)
    conn = libvirt.openReadOnly(uri)
    out_cpu = conn.getCPUStats(libvirt.VIR_NODE_CPU_STATS_ALL_CPUS)
    out_memory = conn.getMemoryStats(-1, 0)
    out_all_domains_raw = conn.getAllDomainStats(flags=libvirt.VIR_CONNECT_LIST_DOMAINS_ACTIVE)
    conn.close()
    return out_all_domains_raw,out_cpu,out_memory

#@timeit
def domstats_with_virsh_docker_exec(container_name='isard-hypervisor'):
    cmd_domstats = 'virsh domstats --nowait --raw'
    client = docker.DockerClient(base_url='unix:///var/run/docker.sock')
    container_hyp = client.containers.get(container_name)
    domstats_raw = container_hyp.exec_run(cmd_domstats)
    client.close()
    return domstats_raw


#@timeit
def domain_stats_as_dicts(raw_stats_domains):
    d_stats = dict()
    d_domains_objects = dict()
    d_domains_info = dict()
    d_domains_xml = dict()
    for l in raw_stats_domains:
        #getxml could fail if domain is stopped when libvirt was running stats
        domain = l[0]
        try:
            xml = domain.XMLDesc()
        except Exception as e:
            print(e)
            xml = False

        if xml is not False:
            d_xml = xmltodict.parse(xml)
            d_domain_info = {}
            domain_name = domain.name()
            try:
                d_domain_info['user'] = domain_name.split('-')[3]
                d_domain_info['group'] = domain_name.split('-')[2]
                d_domain_info['category'] = domain_name.split('-')[1]
            except:
                d_domain_info['group'] = 'NO_GROUP'
                d_domain_info['category'] = 'NO_CATEGORY'
                d_domain_info['user'] = 'NO_USER'

            d_stats[domain_name] = l[1]
            d_domains_objects[domain_name]= domain
            d_domains_xml[domain_name]= xml

            try:
                if type(d_xml['domain']['devices']['interface']) is list:
                    d_iface = d_xml['domain']['devices']['interface'][0]
                else:
                    d_iface = d_xml['domain']['devices']['interface']
                d_domain_info['mac'] = d_iface['mac']['@address']
                try:
                    d_domain_info['bridge'] = d_iface['source']['@bridge']
                except:
                    d_domain_info['bridge'] = 'NOBRIDGE'
            except:
                d_domain_info['mac']='00:00:00:00:00:00'
                d_domain_info['bridge']='NOBRIDGE'

            try:
                if type(d_xml['domain']['devices']['disk']) is list:
                    d_disk = d_xml['domain']['devices']['disk'][0]
                else:
                    d_disk = d_xml['domain']['devices']['disk']
                d_domain_info['path_disk'] = d_disk['source']['@file']

            except:
                d_domain_info['path_disk'] = 'NO_PATH_DISK'


            try:
                if type(d_xml['domain']['devices']['graphics']) is list:
                    d_graphics = {d['@type']:d for d in d_xml['domain']['devices']['graphics']}
                else:
                    d_graphics = {d_xml['domain']['devices']['graphics']['@type']:d_xml['domain']['devices']['graphics']}
                d_domain_info['port_spice_tls'] = int(d_graphics.get('spice',{}).get('@tlsPort',0))
                d_domain_info['port_spice'] = int(d_graphics.get('spice',{}).get('@port',0))
                d_domain_info['port_vnc'] = int(d_graphics.get('vnc',{}).get('@port',0))
            except:
                d_domain_info['port_spice_tls'] = 0
                d_domain_info['port_spice'] = 0
                d_domain_info['port_vnc'] = 0

            try:
                d_domain_info['path_template'] = path_template = d_disk['backingStore']['source']['@file']
                d_domain_info['template'] = ('_' + '_'.join(path_template.split('/')[-5:])).split('.qcow')[0]
            except:
                d_domain_info['path_template'] = 'NO_PATH_TEMPLATE'
                d_domain_info['template'] = 'NOTEMPLATE'


            d_domains_info[domain_name] = d_domain_info


    return d_stats,d_domains_info,d_domains_objects,d_domains_xml


def translate_socket_stats_to_domains(d_domains_info,d_socket_by_port):
    d_domains_viewers_stats = {}
    for id_domain, d_domain_info in d_domains_info.items():
        if id_domain not in d_domains_viewers_stats.keys():
            d_domains_viewers_stats[id_domain] = {
                'spice_connections': 0,
                'vnc_connections': 0,
                'total_connections': 0,
                'spice_bytes_sent': 0,
                'vnc_bytes_sent': 0,
                'total_bytes_sent': 0,
                'spice_bytes_received': 0,
                'vnc_bytes_received': 0,
                'total_bytes_received': 0,
                'total_sockets': 0
            }

        if d_domain_info["port_spice_tls"] in d_socket_by_port.keys():
            port = d_domain_info["port_spice_tls"]
            d_domains_viewers_stats[id_domain]['spice_connections']     += 1
            d_domains_viewers_stats[id_domain]['total_connections']    += 1
            d_domains_viewers_stats[id_domain]['spice_bytes_sent']     += d_socket_by_port[port]['bytes_sent']
            d_domains_viewers_stats[id_domain]['total_bytes_sent']     += d_socket_by_port[port]['bytes_sent']
            d_domains_viewers_stats[id_domain]['spice_bytes_received'] += d_socket_by_port[port]['bytes_received']
            d_domains_viewers_stats[id_domain]['total_bytes_received'] += d_socket_by_port[port]['bytes_received']
            d_domains_viewers_stats[id_domain]['total_bytes_received'] += d_socket_by_port[port]['bytes_received']
            d_domains_viewers_stats[id_domain]['total_sockets']        += len(d_socket_by_port[port]['dports'])

        if d_domain_info["port_spice"] in d_socket_by_port.keys():
            port = d_domain_info["port_spice"]
            d_domains_viewers_stats[id_domain]['spice_connections']     += 1
            d_domains_viewers_stats[id_domain]['total_connections']    += 1
            d_domains_viewers_stats[id_domain]['spice_bytes_sent']     += d_socket_by_port[port]['bytes_sent']
            d_domains_viewers_stats[id_domain]['total_bytes_sent']     += d_socket_by_port[port]['bytes_sent']
            d_domains_viewers_stats[id_domain]['spice_bytes_received'] += d_socket_by_port[port]['bytes_received']
            d_domains_viewers_stats[id_domain]['total_bytes_received'] += d_socket_by_port[port]['bytes_received']
            d_domains_viewers_stats[id_domain]['total_bytes_received'] += d_socket_by_port[port]['bytes_received']
            d_domains_viewers_stats[id_domain]['total_sockets']        += len(d_socket_by_port[port]['dports'])

        if d_domain_info["port_vnc"] in d_socket_by_port.keys():
            port = d_domain_info["port_vnc"]
            d_domains_viewers_stats[id_domain]['vnc_connections']       += len(d_socket_by_port[port]['dports'])
            d_domains_viewers_stats[id_domain]['total_connections']    += 1
            d_domains_viewers_stats[id_domain]['vnc_bytes_sent']       += d_socket_by_port[port]['bytes_sent']
            d_domains_viewers_stats[id_domain]['total_bytes_sent']     += d_socket_by_port[port]['bytes_sent']
            d_domains_viewers_stats[id_domain]['vnc_bytes_received']   += d_socket_by_port[port]['bytes_received']
            d_domains_viewers_stats[id_domain]['total_bytes_received'] += d_socket_by_port[port]['bytes_received']
            d_domains_viewers_stats[id_domain]['total_bytes_received'] += d_socket_by_port[port]['bytes_received']
            d_domains_viewers_stats[id_domain]['total_sockets'] += len(d_socket_by_port[port]['dports'])

    return d_domains_viewers_stats

