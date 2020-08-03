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


@timeit
def ss_detail(container_name='isard-hypervisor'):
    cmd_ss_detail = 'ss -t state established -p -i "( sport > 5900 )"'
    client = docker.DockerClient(base_url='unix:///var/run/docker.sock')
    container_hyp = client.containers.get(container_name)
    ss_raw = container_hyp.exec_run(cmd_ss_detail)
    client.close()
    return ss_raw