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
from lib.functions import timeit


LIBVIRT_DEFAULT_URI="qemu:///system"
#HOSTNAME = os.environ['HOSTNAME']

@timeit
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

@timeit
def domstats_with_virsh_docker_exec(container_name='isard-hypervisor'):
    cmd_domstats = 'virsh domstats --nowait --raw'
    client = docker.DockerClient(base_url='unix:///var/run/docker.sock')
    container_hyp = client.containers.get(container_name)
    domstats_raw = container_hyp.exec_run(cmd_domstats)
    client.close()
    return domstats_raw


@timeit
def domain_stats_as_dicts(raw_stats_domains):
    d_stats = dict()
    d_domains_objects = dict()
    d_domains_info = dict()
    d_domains_xml = dict()
    for l in raw_stats_domains:
        #getxml could fail if domain is stopped when libvirt was running stats
        try:
            xml = domain.XMLDesc()
        except Exception as e:
            xml = False

        if xml is not False:
            d_xml = xmltodict.parse(xml)
            domain = l[0]
            d_domain_info = {}
            domain_name = domain.name()
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
                path = d_disk['source']['@file']

                d_domain_info['user']     = path.split('/')[-2]
                d_domain_info['group']    = path.split('/')[-3]
                d_domain_info['category'] = path.split('/')[-4]

                try:
                    path_template = d_disk['backingStore']['source']['@file']
                    d_domain_info['template'] = '_' + '_'.join(path_template.split('/')[-2:])
                except:
                    d_domain_info['template'] = 'NOTEMPLATE'
            except:
                d_domain_info['user']     = 'NO_USER'
                d_domain_info['group']    = 'NO_GROUP'
                d_domain_info['category'] = 'NO_CATEGORY'
                d_domain_info['template'] = 'NOTEMPLATE'

            d_domains_info[domain_name] = d_domain_info


    return d_stats,d_domains_info,d_domains_objects,d_domains_xml