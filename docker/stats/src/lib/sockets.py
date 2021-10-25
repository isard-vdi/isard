import logging
import os
import socket
import time
from collections import OrderedDict
from datetime import datetime

import libvirt
import paramiko
import xmltodict
import yaml

import docker

# import sentry_sdk
# from sentry_sdk.integrations.logging import LoggingIntegration
# from stats_isard.lib.functions import timeit

DEBUG_STATS = os.environ.get("DEBUG_STATS", False)

# @timeit
def ss_detail(container_name="isard-hypervisor"):
    cmd_ss_detail = (
        'ss -t state established -o state established -t -n -p -i "( sport > 5900 )"'
    )
    client = docker.DockerClient(base_url="unix:///var/run/docker.sock")
    container_hyp = client.containers.get(container_name)
    ss_raw = container_hyp.exec_run(cmd_ss_detail)
    client.close()
    return ss_raw


# @timeit
def ss_detail_ssh(host, username, ssh_key=None, password=None, port=22, **kwargs):
    cmd_ss_detail = (
        'ss -t state established -o state established -t -n -p -i "( sport > 5900 )"'
    )
    ssh_client = paramiko.SSHClient()
    ssh_client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    if password is None and ssh_key is None:
        ssh_client.connect(host, username=username, port=port)
    if password is None:
        ssh_client.connect(host, username=username, key_filename=ssh_key, port=port)
    elif ssh_key is None:
        ssh_client.connect(host, username=username, password=password, port=port)
    stdin, stdout, stderr = ssh_client.exec_command(cmd_ss_detail)
    out = stdout.read().decode("utf-8")
    err = stderr.read().decode("utf-8")
    ssh_client.close()
    if len(err) > 0:
        print("ERROR WITH SS COMMAND")
        return False
    return out


def get_socket_stats(
    type_conn_ss="docker",
    container_name="isard-hypervisor",
    host=None,
    port=22,
    username="root",
    password=None,
    ssh_key=None,
):
    """get socket stats:
    type_conn_ss = 'docker' => use DockerClient
    type_conn_ss = 'ssh' => connect with paramiko and run ss command
    type_conn_ss = 'ssh+docker' => connect with paramiko, and run ss as exec in docker
    """
    if type_conn_ss == "docker":
        raw = ss_detail(container_name)
        data = raw[1].decode("utf-8").splitlines()
    elif type_conn_ss == "ssh":
        raw = ss_detail_ssh(host, username, ssh_key, password, port)
        data = raw.splitlines()

    data.pop(0)
    d_socket_by_port = {}
    for n in range(len(data)):
        if data[n].find("qemu") > 0:
            if DEBUG_STATS:
                print(data[n])
                print(data[n + 1])
            try:
                sport = int(data[n].split(":")[1].split()[0])
                dport = int(data[n].split(":")[2].split()[0])
                bytes_sent = int(data[n + 1].split("bytes_acked:")[1].split()[0])
                bytes_received = int(data[n + 1].split("bytes_received:")[1].split()[0])
                pid = int(data[n].split("pid=")[1].split(",")[0])
            except Exception as e:
                if DEBUG_STATS:
                    print(f"Error when parse ss")
                    print(data[n])
                    print(data[n + 1])
                continue
            if sport not in d_socket_by_port.keys():
                d_socket_by_port[sport] = {
                    "dports": [],
                    "pid": pid,
                    "sent_by_dport": [],
                    "received_by_dport": [],
                    "bytes_sent": 0,
                    "bytes_received": 0,
                }
            d_socket_by_port[sport]["dports"].append(dport)
            d_socket_by_port[sport]["sent_by_dport"].append(bytes_sent)
            d_socket_by_port[sport]["received_by_dport"].append(bytes_received)
            d_socket_by_port[sport]["bytes_sent"] += bytes_sent
            d_socket_by_port[sport]["bytes_received"] += bytes_received

    return d_socket_by_port
