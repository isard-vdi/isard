# Copyright 2017 the Isard-vdi project authors:
#      Alberto Larraz Dalmases
#      Josep Maria Viñolas Auquer
# License: AGPLv3

# coding=utf-8
"""
a module to control hypervisor functions and state. Overrides libvirt events and

"""

import socket
import threading
import time
import traceback
import uuid
from copy import deepcopy
from datetime import datetime
from io import StringIO
from statistics import mean

import libvirt
import paramiko
import xmltodict
from engine.config import *
from engine.models.nvidia_models import NVIDIA_MODELS
from engine.services.db import (
    get_hyp,
    get_hyp_default_gpu_models,
    get_hyp_info,
    get_id_hyp_from_uri,
    get_vgpu,
    get_vgpu_actual_profile,
    reset_vgpu_created_started,
    update_actual_stats_domain,
    update_actual_stats_hyp,
    update_db_hyp_info,
    update_db_hyp_nvidia_info,
    update_table_field,
    update_vgpu_created,
    update_vgpu_profile,
    update_vgpu_uuid_started_in_domain,
    update_vgpu_uuids,
)
from engine.services.db.domains import (
    get_all_mdev_uuids_from_profile,
    get_domain_status,
    get_domains_started_in_hyp,
    get_domains_with_status_in_list,
    update_domain_status,
)
from engine.services.lib.functions import (
    calcule_cpu_hyp_stats,
    exec_remote_cmd,
    execute_commands,
    get_tid,
    hostname_to_uri,
    new_dict_from_raw_dict_stats,
    state_and_cause_to_str,
    test_hypervisor_conn,
    timelimit,
    try_socket,
)
from engine.services.lib.libvirt_dicts import virDomainState
from engine.services.log import *
from flatten_dict import flatten
from libpci import LibPCI
from lxml import etree

# ~ import pandas as pd


TIMEOUT_QUEUE = 20
TIMEOUT_CONN_HYPERVISOR = (
    4  # int(CONFIG_DICT['HYPERVISORS']['timeout_conn_hypervisor'])
)


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

devid_nvidia_ampere = {}
# Ampere
devid_nvidia_ampere[0x20B0] = "A100"
devid_nvidia_ampere[0x20B2] = "A100DX"
devid_nvidia_ampere[0x20F1] = "A100 PCIe"
devid_nvidia_ampere[0x2230] = "RTX A6000"
devid_nvidia_ampere[0x2231] = "RTX A5000"
devid_nvidia_ampere[0x2235] = "A40"
devid_nvidia_ampere[0x2236] = "A10"
devid_nvidia_ampere[0x2237] = "A10G"
devid_nvidia_ampere[0x20B5] = "A100 80GB PCIe"
devid_nvidia_ampere[0x20B7] = "A30"
devid_nvidia_ampere[0x25B6] = "A16"
# same devid A16 and A2 subsystem:
# ssid: 0x14A9 = "A16"
# ssid: 0x159D = "A2"

devid_nvidia_ampere[0x20B8] = "A100X"
devid_nvidia_ampere[0x20B9] = "A30X"
devid_nvidia_ampere[0x2233] = "RTX A5500"
devid_nvidia_ampere[0x20F5] = "A800 80GB PCIe"
devid_nvidia_ampere[0x20F3] = "A800-SXM4-80GB"
# Hopper
devid_nvidia_ampere[0x2331] = "H100 PCIe"


class HypStats(object):
    def __init__(self):
        self.hyper_stats_history = {}
        self.hyper_stats_current = {}
        self.hyper_libvirt_last_stats = {}

    def get_stats(self, hyp_id, minutes=0):
        if minutes == 0:
            if hyp_id not in self.hyper_stats_current.keys():
                return {
                    "memory": {
                        "available": 0,
                        "buffers": 0,
                        "cached": 0,
                        "free": 0,
                        "total": 0,
                    },
                    "cpu": {
                        "idle": 100.0,
                        "iowait": 0.0,
                        "kernel": 0.0,
                        "user": 0.0,
                    },
                }
            else:
                return self.hyper_stats_current[hyp_id]
        # Get dicts in self.stats_previous["history"] which keys are less than 1 minutes
        minutes_keys = [
            self.hyper_stats_history[hyp_id][k]
            for k in self.hyper_stats_history[hyp_id].keys()
            if time.time() - k < minutes * 60
        ]
        # Get dict of means of all values in cpu_1min_keys dicts
        cpu_minutes_mean = {
            kk: round(
                sum([vv["cpu"][kk] for vv in minutes_keys]) / len(minutes_keys), 3
            )
            for kk in minutes_keys[0]["cpu"].keys()
        }
        memory_minutes_mean = {
            kk: round(
                sum([vv["memory"][kk] for vv in minutes_keys]) / len(minutes_keys), 0
            )
            for kk in minutes_keys[0]["memory"].keys()
        }
        self.remove_old_stats(hyp_id=hyp_id)
        return {"memory": memory_minutes_mean, "cpu": cpu_minutes_mean}

    def remove_old_stats(self, hyp_id=None, minutes=20):
        if hyp_id is None:
            for hyper in self.hyper_stats_history.keys():
                for key in list(self.hyper_stats_history[hyper].keys()):
                    if time.time() - key >= minutes * 60:
                        del self.hyper_stats_history[hyper][key]
        else:
            for key in list(self.hyper_stats_history[hyp_id].keys()):
                if time.time() - key >= minutes * 60:
                    del self.hyper_stats_history[hyp_id][key]

    def set_stats(self, hyp_id, memory, cpu):
        memory["available"] = memory["free"] + memory["cached"]
        current_libvirt_stats = {"memory": memory, "cpu": cpu}
        if hyp_id not in self.hyper_libvirt_last_stats.keys():
            cpu_current, _, _ = calcule_cpu_hyp_stats(
                self.get_stats(hyp_id=hyp_id)["cpu"], current_libvirt_stats["cpu"]
            )
            self.hyper_stats_current[hyp_id] = {"memory": memory, "cpu": cpu_current}
            self.hyper_stats_history[hyp_id] = {
                time.time(): self.hyper_stats_current[hyp_id]
            }
        else:
            cpu_current, _, _ = calcule_cpu_hyp_stats(
                self.hyper_libvirt_last_stats[hyp_id]["cpu"],
                current_libvirt_stats["cpu"],
            )
            self.hyper_stats_current[hyp_id] = {"memory": memory, "cpu": cpu_current}
            self.hyper_stats_history[hyp_id][time.time()] = self.hyper_stats_current[
                hyp_id
            ]
        self.hyper_libvirt_last_stats[hyp_id] = current_libvirt_stats


hyp_stats = HypStats()


class hyp(object):
    """
    operates with hypervisor
    """

    def __init__(
        self,
        address,
        user="root",
        port=22,
        nvidia_enabled=False,
        capture_events=False,
        try_ssh_autologin=False,
        hyp_id=None,
    ):
        # dictionary of domains
        # self.id = 0
        self.domains = {}
        self.domains_states = {}
        port = int(port)
        if (type(port) == int) and port > 1 and port < pow(2, 16):
            self.port = port
        else:
            self.port = 22
        # log.info('El port es: '+str(self.port))
        self.try_ssh_autologin = try_ssh_autologin
        self.user = user
        self.hostname = address
        self.connected = False
        self.ssh_autologin_fail = False
        self.fail_connected_reason = ""
        self.eventLoopThread = None
        self.info = {}
        self.stats = {}
        self.nvidia_enabled = nvidia_enabled
        self.info_nvidia = {}
        self.mdevs = {}
        self.info_stats = {}
        self.capture_events = capture_events
        self.id_hyp_rethink = hyp_id
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
        timeout = float(CONFIG_DICT["TIMEOUTS"]["ssh_paramiko_hyp_test_connection"])
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
                ssh.connect(
                    self.hostname,
                    username=self.user,
                    port=self.port,
                    timeout=timeout,
                    banner_timeout=timeout,
                )

                log.debug(
                    "host {} with ip {} TEST CONNECTION OK, ssh connect without password".format(
                        self.hostname, self.ip
                    )
                )
                ssh.close()
            except paramiko.SSHException as e:
                log.error(
                    "host {} with ip {} can't connect with ssh without password. Paramiko except Reason: {}".format(
                        self.hostname, self.ip, e
                    )
                )
                log.error("")
                # message when host not found or key format not supported: not found in known_hosts
                self.fail_connected_reason = (
                    "ssh authentication fail when connect: {}".format(e)
                )
                self.ssh_autologin_fail = True
            except Exception as e:
                logs.exception_id.debug("0026")
                log.error(
                    "host {} with ip {} can't connect with ssh without password. Reasons? timeout, ssh authentication with keys is needed, port is correct?".format(
                        self.hostname, self.ip
                    )
                )
                log.error("reason: {}".format(e))
                self.fail_connected_reason = (
                    "ssh authentication fail when connect: {}".format(e)
                )
                self.ssh_autologin_fail = True

        else:
            self.ssh_autologin_fail = True
            self.fail_connected_reason = (
                "socket error in ssh port, sshd disabled or firewall"
            )
            log.error(
                "socket error, try if ssh is listen in hostname {} with ip address {} and port {}".format(
                    self.hostname, self.ip, self.port
                )
            )

    def connect_to_hyp(self):
        try:
            self.ip = socket.gethostbyname(self.hostname)

            if self.try_ssh_autologin == True:
                self.try_ssh()

            if self.ssh_autologin_fail is False:
                try:
                    self.uri = hostname_to_uri(
                        self.hostname, user=self.user, port=self.port
                    )
                    if self.id_hyp_rethink is None:
                        try:
                            self.id_hyp_rethink = get_id_hyp_from_uri(self.uri)
                        except Exception as e:
                            logs.exception_id.debug("0027")
                            log.error(
                                "error when hypervisor have not rethink id. {}".format(
                                    e
                                )
                            )
                    # timeout_libvirt = float(CONFIG_DICT['TIMEOUTS']['libvirt_hypervisor_timeout_connection'])
                    # self.conn = timelimit(timeout_libvirt, test_hypervisor_conn, self.uri)
                    self.conn = test_hypervisor_conn(self.uri)

                    # timeout = float(CONFIG_DICT['TIMEOUTS']['ssh_paramiko_hyp_test_connection'])

                    if self.conn != False:
                        self.connected = True
                        # prueba de alberto para que indique cuando ha caído y para que mantenga alive la conexión

                        # OJO INFO TO DEVELOPER
                        # self.startEvent()

                        # este setKeepAlive no tengo claro que haga algo, pero bueno...
                        # y al ponerlo da error lo dejo comentado, pero en futuro hay que quitar
                        # esta línea si no sabemos bien que hace...
                        # self.conn.setKeepAlive(5, 3)
                        log.debug("connected to hypervisor: %s" % self.hostname)
                        self.set_status(HYP_STATUS_CONNECTED)
                        self.fail_connected_reason = ""
                        # para que le de tiempo a los eventos a quedarse registrados hay que esperar un poquillo, ya
                        # que se arranca otro thread
                        # self.get_hyp_info()
                        return True
                    else:
                        log.error(
                            "libvirt can't connect to hypervisor {}".format(
                                self.hostname
                            )
                        )
                        log.info(
                            """connection to hypervisor fail, try policykit or permissions,
                              or try in the hypervisor if libvirtd service is started
                              (in Fedora/Centos: systemctl status libvirtd )
                              or if the port 22 is open"""
                        )
                        self.set_status(HYP_STATUS_ERROR_WHEN_CONNECT)
                        self.fail_connected_reason = "Hypervisor policykit or permissions or libvirtd has not started"

                        return False

                # except TimeLimitExpired:
                #     log.error("""Time Limit Expired connecting to hypervisor""")
                #     self.set_status(HYP_STATUS_ERROR_WHEN_CONNECT_TIMELIMIT)
                #     self.fail_connected_reason = 'Time Limit Expired connecting to hypervisor'
                #     return False

                except Exception as e:
                    logs.exception_id.debug("0028")
                    log.error(
                        "connection to hypervisor {} fail with unexpected error: {}".format(
                            self.hostname, e
                        )
                    )
                    log.error("libvirt uri: {}".format(self.uri))
                    self.set_status(HYP_STATUS_ERROR_WHEN_CONNECT)
                    self.fail_connected_reason = (
                        "connection to hypervisor {} fail with unexpected error".format(
                            self.hostname
                        )
                    )
                    return False

        except socket.error as e:
            log.error(e)
            log.error("not resolves ip from hostname: {}".format(self.hostname))
            self.fail_connected_reason = "not resolves ip from hostname: {}".format(
                self.hostname
            )
            return False

        except Exception as e:
            logs.exception_id.debug("0029")
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

    def get_info_from_hypervisor(
        self, nvidia_enabled=False, force_get_hyp_info=False, init_vgpu_profiles=False
    ):
        info = self.info = get_hyp_info(self.id_hyp_rethink)
        if (
            info is False
            or (type(info) == dict and len(info) < 1)
            or force_get_hyp_info is True
        ):
            self.info = {}
            self.get_kvm_mod()
            self.get_hyp_info(nvidia_enabled)
            logs.workers.debug(
                "hypervisor motherboard: {}".format(
                    self.info["motherboard_manufacturer"]
                )
            )
            update_db_hyp_info(self.id_hyp_rethink, self.info)
            if len(self.info_nvidia) > 0:
                d = update_db_hyp_nvidia_info(self.id_hyp_rethink, self.info_nvidia)
                # CREATE UUIDS and SELECT vgpu_profile
                index_vgpu_profile = {}
                for pci_bus, d_vgpu in self.info_nvidia.items():
                    vgpu_id = "-".join([self.id_hyp_rethink, pci_bus])
                    d_uuids = self.create_uuids(d_vgpu)
                    update_vgpu_uuids(vgpu_id, d_uuids)
                    # self.mdevs[pci_bus] = d_uuids

                    # init vgpu_profile to max gpu profile
                    vgpu_profile = self.info_nvidia[pci_bus]["type_max_gpus"]
                    # if init_vgpu_profiles in hypervisor is defined can change vgpu_profile
                    if type(init_vgpu_profiles) is list:
                        all_profiles = list(self.info_nvidia[pci_bus]["types"])
                        list_profiles_selected = [
                            a for a in init_vgpu_profiles if a in all_profiles
                        ]
                        if len(list_profiles_selected) > 0:
                            model = self.info_nvidia[pci_bus]["model"]
                            if model not in index_vgpu_profile.keys():
                                index_vgpu_profile[model] = 0
                            else:
                                index_vgpu_profile[model] += 1
                            i = index_vgpu_profile[model] % len(list_profiles_selected)
                            vgpu_profile = list_profiles_selected[i]

                    # self.info_nvidia[pci_bus]["vgpu_profile"] = vgpu_profile
                    update_vgpu_profile(vgpu_id, vgpu_profile)

    def load_info_from_db(self):
        self.info = get_hyp_info(self.id_hyp_rethink)

        if self.info is False:
            return False

        if len(self.info.get("nvidia", {})) > 0:
            for pci_bus in self.info["nvidia"].keys():
                vgpu_id = "-".join([self.id_hyp_rethink, pci_bus])
                d_vgpu = get_vgpu(vgpu_id)
                if d_vgpu:
                    self.info_nvidia[pci_bus] = d_vgpu["info"]
                    self.mdevs[pci_bus] = d_vgpu["mdevs"]
                    self.info_nvidia[pci_bus]["vgpu_profile"] = d_vgpu["vgpu_profile"]

        return True

    def change_vgpu_profile(self, gpu_id, new_profile):
        if not new_profile:
            return
        update_table_field("vgpus", gpu_id, "changing_to_profile", new_profile)
        pci_id = gpu_id.split("-")[-1]
        old_profile = self.info_nvidia.get(pci_id, {}).get("vgpu_profile", None)
        if old_profile != new_profile:
            remove_uuids = get_all_mdev_uuids_from_profile(gpu_id, old_profile)
            # GET RUNNING MDEVS AND DOMAINS FROM HYPERVISOR
            d_mdevs_running = self.get_mdevs_with_domains()
            for mdev_uuid in remove_uuids:
                if mdev_uuid in d_mdevs_running.keys():
                    if type(d_mdevs_running[mdev_uuid].get("vm_name", False)) is str:
                        domain_id = d_mdevs_running[mdev_uuid].get("vm_name")
                        if len(domain_id) > 0:
                            try:
                                domain_handler = self.conn.lookupByName(domain_id)
                                domain_handler.destroy()
                            except Exception as e:
                                logs.main.error(
                                    f"domain {domain_id} running can not be destroyed with exception: {e}"
                                )
                                return False

            # REMOVE OLD UUIDS
            cmds_remove_uuids = [
                f"echo 1 > /sys/bus/mdev/devices/{uuid_remove}/remove"
                for uuid_remove in remove_uuids
                if uuid_remove in d_mdevs_running.keys()
            ]
            uuids_that_not_are_running = [
                uuid_remove
                for uuid_remove in remove_uuids
                if uuid_remove not in d_mdevs_running.keys()
            ]

            if len(cmds_remove_uuids) > 0:
                array_out_err = execute_commands(
                    self.hostname, cmds_remove_uuids, port=self.port
                )
                for i, uuid_remove in enumerate(remove_uuids):
                    if len(array_out_err[i]["err"]) == 0:
                        logs.main.info(
                            f"removed uid {uuid_remove} for gpu_id: {gpu_id} ok"
                        )
                        update_vgpu_created(
                            gpu_id, old_profile, uuid_remove, created=False
                        )
                        self.mdevs[pci_id][old_profile][uuid_remove]["created"] = False

            for uuid_not_running in uuids_that_not_are_running:
                logs.main.info(
                    f"removed uid {uuid_not_running} for gpu_id: {gpu_id} ok"
                )
                update_vgpu_created(
                    gpu_id, old_profile, uuid_not_running, created=False
                )
                self.mdevs[pci_id][old_profile][uuid_not_running]["created"] = False

            # CREATE NEW UUIDS
            create_uuids = get_all_mdev_uuids_from_profile(gpu_id, new_profile)

            base_path = self.info_nvidia[pci_id]["path"]
            sub_paths = self.info_nvidia[pci_id].get("sub_paths", False)
            cmds = []
            uuids_create = []
            for uuid_create, d_uuid in self.mdevs[pci_id][new_profile].items():
                type_id = d_uuid["type_id"]
                if uuid_create not in d_mdevs_running.keys():
                    uuids_create.append(uuid_create)
                    if sub_paths is False:
                        path = base_path
                    else:
                        path = [
                            i for i in sub_paths if i.find(d_uuid["pci_mdev_id"]) > 0
                        ][0]
                    cmds.append(
                        f"echo {uuid_create} > '{path}/mdev_supported_types/{type_id}/create'"
                    )
                else:
                    update_vgpu_created(gpu_id, new_profile, uuid_create, created=True)
                    self.mdevs[pci_id][new_profile][uuid_create]["created"] = True

            if len(cmds) > 0:
                array_out_err = execute_commands(self.hostname, cmds, port=self.port)
                for i, uuid_create in enumerate(uuids_create):
                    if len(array_out_err[i]["err"]) == 0:
                        logs.main.info(
                            f"added uid {uuid_create} for gpu_id {gpu_id} with profile {new_profile}"
                        )
                        update_vgpu_created(
                            gpu_id, new_profile, uuid_create, created=True
                        )
                        self.mdevs[pci_id][new_profile][uuid_create]["created"] = True

            self.info_nvidia[pci_id]["vgpu_profile"] = new_profile
            update_table_field("vgpus", gpu_id, "changing_to_profile", False)
            update_table_field("vgpus", gpu_id, "vgpu_profile", new_profile)

    def create_mdevs_from_uuids(self):
        d_mdevs_running = self.get_mdevs_with_domains()
        for pci_id, d_nvidia in self.info_nvidia.items():
            vgpu_id = "-".join([self.id_hyp_rethink, pci_id])
            vgpu_profile = get_vgpu_actual_profile(vgpu_id)
            if vgpu_profile:
                self.change_vgpu_profile(vgpu_id, vgpu_profile)
            else:
                vgpu_profile = d_nvidia["vgpu_profile"]
            cmds = []
            base_path = d_nvidia["path"]
            sub_paths = d_nvidia.get("sub_paths", False)
            for uuid_create, d_uuid in self.mdevs[pci_id][vgpu_profile].items():
                type_id = d_uuid["type_id"]
                if uuid_create not in d_mdevs_running.keys():
                    if sub_paths is False:
                        path = base_path
                    else:
                        path = [
                            i for i in sub_paths if i.find(d_uuid["pci_mdev_id"]) > 0
                        ][0]
                    cmds.append(
                        f"echo {uuid_create} > '{path}/mdev_supported_types/{type_id}/create'"
                    )
            if len(cmds) > 0:
                array_out_err = execute_commands(self.hostname, cmds, port=self.port)
                if len([out for out in array_out_err if len(out["err"]) > 0]) == 0:
                    logs.workers.info(
                        f"uuids created for pci_id {pci_id} in hypervisor {self.id_hyp_rethink} with profile {vgpu_profile} with type_id {type_id}"
                    )

                    for uuid_create in self.mdevs[pci_id][vgpu_profile].keys():
                        results = update_vgpu_created(
                            vgpu_id, vgpu_profile, uuid_create
                        )
                        self.mdevs[pci_id][vgpu_profile][uuid_create]["created"] = True
                else:
                    logs.workers.error(
                        f"uuids NOT created for pci_id {pci_id} in hypervisor {self.id_hyp_rethink} with profile {vgpu_profile} with type_id {type_id}"
                    )
                    for i, d in enumerate(array_out_err):
                        logs.workers.error(
                            f"CMD: {cmds[i]} / OUT: {d['out']} / ERROR: {d['err']}"
                        )

    def init_nvidia(self):
        self.remove_domains_and_gpus_with_invalids_uuids()
        self.create_mdevs_from_uuids()

    def get_kvm_mod(self):
        for i in range(MAX_GET_KVM_RETRIES):
            try:
                d = exec_remote_cmd(
                    "lsmod |grep kvm", self.hostname, username=self.user, port=self.port
                )
                if len(d["err"]) > 0:
                    log.error(
                        "error {} returned from command: lsmod |grep kvm".format(
                            d["err"].decode("utf-8")
                        )
                    )
                else:
                    s = d["out"].decode("utf-8")
                    if s.find("kvm_intel") >= 0:
                        self.info["kvm_module"] = "intel"
                    elif s.find("kvm_amd") >= 0:
                        self.info["kvm_module"] = "amd"
                    elif s.find("kvm") >= 0:
                        self.info["kvm_module"] = "bios_disabled"
                        log.error(
                            "No kvm module kvm_amd or kvm_intel activated. You must review your BIOS"
                        )
                        log.error(
                            "Hardware acceleration is supported, but disabled in the BIOS settings"
                        )
                    else:
                        self.info["kvm_module"] = False
                        log.error(
                            "No kvm module installed. You must review if qemu-kvm is installed and CPU capabilities"
                        )
                return True

            except Exception as e:
                logs.exception_id.debug("0030")
                log.error(
                    "Exception while executing remote command in hypervisor to list kvm modules: {}".format(
                        e
                    )
                )
                log.error(
                    f"Ssh launch command attempt fail: {i+1}/{MAX_GET_KVM_RETRIES}. Retry in one second."
                )
            time.sleep(1)

        self.info["kvm_module"] = False
        log.error(
            f"remote ssh command in hypervisor {self.hostname} fail with {MAX_GET_KVM_RETRIES} retries"
        )
        return False

    def get_nested(self):
        for i in range(MAX_GET_KVM_RETRIES):
            try:
                d = exec_remote_cmd(
                    "cat /sys/module/kvm_intel/parameters/nested",
                    self.hostname,
                    username=self.user,
                    port=self.port,
                )
                if len(d["err"]) > 0:
                    d = exec_remote_cmd(
                        "cat /sys/module/kvm_amd/parameters/nested",
                        self.hostname,
                        username=self.user,
                        port=self.port,
                    )
                    if len(d["err"]) > 0:
                        log.warning(
                            f"Nested virtualization NOT enabled for hypervisor {self.hostname}"
                        )
                        return False
                s = d["out"].decode("utf-8")
                if s.find("1") == 0 or s.find("Y") == 0:
                    log.info(
                        f"Nested virtualization enabled for hypervisor {self.hostname}"
                    )
                    return True
                return False

            except Exception as e:
                logs.exception_id.debug("0036")
                log.error(
                    "Exception while executing remote command in hypervisor to check nested virtualization: {}".format(
                        e
                    )
                )
                log.error(
                    f"Ssh launch command attempt fail: {i+1}/{MAX_GET_KVM_RETRIES}. Retry in one second."
                )
            time.sleep(1)

        log.error(
            f"remote ssh command in hypervisor {self.hostname} fail with {MAX_GET_KVM_RETRIES} retries"
        )
        return False

    def get_storage_used(self):
        for i in range(MAX_GET_KVM_RETRIES):
            try:
                mountpoints = []
                d = exec_remote_cmd(
                    'df -h | awk \'{if ($1 != "Filesystem") print $6 " " $5}\'',
                    self.hostname,
                    username=self.user,
                    port=self.port,
                )
                mroot = d["out"].decode("utf-8")
                for mount in mroot.split("\n"):
                    line = mount.split(" ")
                    if line[0] == "/" or line[0].startswith("/isard"):
                        mountpoints.append(
                            {
                                "mount": line[0],
                                "usage": int(line[1].split("%")[0]),
                            }
                        )
                return mountpoints
            except Exception as e:
                # logs.exception_id.debug("0036")
                log.error(
                    "Exception while executing remote command in hypervisor to check disk usage: {}".format(
                        e
                    )
                )
                log.error(
                    f"Ssh launch command attempt fail: {i+1}/{MAX_GET_KVM_RETRIES}. Retry in one second."
                )
            time.sleep(1)

        log.error(
            f"remote ssh command in hypervisor {self.hostname} fail with {MAX_GET_KVM_RETRIES} retries"
        )
        return False

    def get_hyp_info(self, nvidia_enabled=False):
        libvirt_version = str(self.conn.getLibVersion())
        self.info["libvirt_version"] = "{}.{}.{}".format(
            int(libvirt_version[-9:-6]),
            int(libvirt_version[-6:-3]),
            int(libvirt_version[-3:]),
        )

        try:
            qemu_version = str(self.conn.getVersion())
            self.info["qemu_version"] = "{}.{}.{}".format(
                int(qemu_version[-9:-6]),
                int(qemu_version[-6:-3]),
                int(qemu_version[-3:]),
            )
        except libvirt.libvirtError as e:
            logs.workers.error(
                f"Exception when get qemu_version in hyp {self.id_hyp_rethink}: {e}"
            )
            self.info["qemu_version"] = "0.0.0"

        inf = self.conn.getInfo()
        self.info["arch"] = inf[0]
        self.info["memory_in_MB"] = inf[1]
        self.info["cpu_threads"] = inf[2]
        self.info["cpu_mhz"] = inf[3]
        self.info["numa_nodes"] = inf[4]
        self.info["cpu_cores"] = inf[6]
        self.info["threads_x_core"] = inf[7]
        xml = self.conn.getSysinfo()
        parser = etree.XMLParser(remove_blank_text=True)
        tree = etree.parse(StringIO(xml), parser)

        try:
            if tree.xpath('/sysinfo/processor/entry[@name="socket_destination"]'):
                self.info["cpu_model"] = tree.xpath(
                    '/sysinfo/processor/entry[@name="socket_destination"]'
                )[0].text

            if tree.xpath('/sysinfo/system/entry[@name="manufacturer"]'):
                self.info["motherboard_manufacturer"] = tree.xpath(
                    '/sysinfo/system/entry[@name="manufacturer"]'
                )[0].text

            if tree.xpath('/sysinfo/system/entry[@name="product"]'):
                self.info["motherboard_model"] = tree.xpath(
                    '/sysinfo/system/entry[@name="product"]'
                )[0].text

            if tree.xpath("/sysinfo/memory_device"):
                self.info["memory_banks"] = len(tree.xpath("/sysinfo/memory_device"))
                self.info["memory_type"] = tree.xpath(
                    '/sysinfo/memory_device/entry[@name="type"]'
                )[0].text
                try:
                    self.info["memory_speed"] = tree.xpath(
                        '/sysinfo/memory_device/entry[@name="speed"]'
                    )[0].text
                except:
                    self.info["memory_speed"] = "0"

        except Exception as e:
            logs.exception_id.debug("0031")
            log.error(
                "Exception when extract information with libvirt from hypervisor {}: {}".format(
                    self.hostname, e
                )
            )
            log.error("Traceback: {}".format(traceback.format_exc()))

        xml = self.conn.getCapabilities()
        parser = etree.XMLParser(remove_blank_text=True)
        tree = etree.parse(StringIO(xml), parser)

        if tree.xpath("/capabilities/host/cpu/model"):
            self.info["cpu_model_type"] = tree.xpath("/capabilities/host/cpu/model")[
                0
            ].text

        if tree.xpath(
            '/capabilities/guest/arch/domain[@type="kvm"]/machine[@canonical]'
        ):
            self.info["kvm_type_machine_canonical"] = tree.xpath(
                '/capabilities/guest/arch/domain[@type="kvm"]/machine[@canonical]'
            )[0].get("canonical")

        # intel virtualization => cpu feature vmx
        #   amd virtualization => cpu feature svm
        if tree.xpath('/capabilities/host/cpu/feature[@name="vmx"]'):
            self.info["virtualization_capabilities"] = "vmx"
        elif tree.xpath('/capabilities/host/cpu/feature[@name="svm"]'):
            self.info["virtualization_capabilities"] = "svm"
        else:
            self.info["virtualization_capabilities"] = False

        # read_gpu
        if nvidia_enabled:
            self.get_nvidia_capabilities()

        # nested virtualization
        self.info["nested"] = self.get_nested()

    def get_system_stats(self):
        try:
            start = time.time()
            memory = self.conn.getMemoryStats(-1)
            cpu = self.conn.getCPUStats(-1)
            hyp_stats.set_stats(self.id_hyp_rethink, memory, cpu)
            self.stats = {
                "mem_stats": hyp_stats.get_stats(self.id_hyp_rethink)["memory"],
                "mem_stats_1min": hyp_stats.get_stats(self.id_hyp_rethink, minutes=1)[
                    "memory"
                ],
                "mem_stats_5min": hyp_stats.get_stats(self.id_hyp_rethink, minutes=5)[
                    "memory"
                ],
                "mem_stats_15min": hyp_stats.get_stats(self.id_hyp_rethink, minutes=15)[
                    "memory"
                ],
                "cpu_current": hyp_stats.get_stats(self.id_hyp_rethink)["cpu"],
                "cpu_1min": hyp_stats.get_stats(self.id_hyp_rethink, minutes=1)["cpu"],
                "cpu_5min": hyp_stats.get_stats(self.id_hyp_rethink, minutes=5)["cpu"],
                "cpu_15min": hyp_stats.get_stats(self.id_hyp_rethink, minutes=15)[
                    "cpu"
                ],
                "time": round(time.time() - start, 3),
            }

        except Exception as e:
            log.error(
                "hyp {} with id fail in get stats from libvirt {}".format(
                    self.id_hyp_rethink, traceback.format_exc()
                )
            )

    def get_nvidia_available_instances_of_type(self, vgpu_id):
        self.get_nvidia_capabilities(only_get_availables=True)
        d_available = {}
        for pci_id, info_nvidia in self.info["nvidia"].items():
            d_available[pci_id] = info_nvidia["types"][vgpu_id]["available"]
        return d_available

    def get_nvidia_capabilities(self, only_get_availables=False):
        d_info_nvidia = {}
        libvirt_mdev_names = self.conn.listDevices("mdev_types")
        # libvirt_mdev_names = self.conn.listDevices("pci")
        # libvirt_mdev_names = ['pci_0000_41_00_0','pci_0000_61_00_0']
        # with A40 libvirt detect only subdevices, but not primary device that end with 0
        pci_names = list(set([a[:-3] + "0_0" for a in libvirt_mdev_names]))
        pci_devices = [a for a in self.conn.listAllDevices() if a.name() in pci_names]
        if len(pci_devices) > 0:
            l_dict_mdev = [xmltodict.parse(a.XMLDesc()) for a in pci_devices]
            l_nvidia_devices = [
                a
                for a in l_dict_mdev
                if a["device"].get("driver", {}).get("name", {}) == "nvidia"
            ]
            if len(l_nvidia_devices) > 0:
                self.has_nvidia = True
                for d in l_nvidia_devices:
                    info_nvidia = {}
                    try:
                        try:
                            capability = d["device"]["capability"]["capability"]
                            if type(capability) is list:
                                # T4 and others
                                max_count = capability[0]["@maxCount"]
                            else:
                                # A40 ant others
                                max_count = capability["@maxCount"]
                        except:
                            max_count = 0
                        name = d["device"]["name"]
                        path = d["device"]["path"]
                        parent = d["device"]["parent"]
                        vendor_pci_id = int(
                            d["device"]["capability"]["vendor"]["@id"], base=0
                        )
                        device_pci_id = int(
                            d["device"]["capability"]["product"]["@id"], base=0
                        )
                        if only_get_availables is False:
                            pci = LibPCI()
                            if device_pci_id in devid_nvidia_ampere.keys():
                                device_name = devid_nvidia_ampere[device_pci_id]
                            else:
                                device_name = pci.lookup_device_name(
                                    vendor_pci_id, device_pci_id
                                )
                        else:
                            device_name = "UNKNOWN NVIDIA"
                    except:
                        max_count = 0
                        device_name = "NO DEV NVIDIA"
                        continue

                    try:
                        sub_paths = False
                        path_parent = False
                        if device_pci_id in devid_nvidia_ampere.keys():
                            (
                                l_types,
                                sub_paths,
                                path_parent,
                            ) = self.get_types_from_ampere(d)
                        else:
                            # only C-Series or Q-Series Virtual GPU Types (Required license edition: vWS)
                            if (
                                type(d["device"]["capability"]["capability"]) is list
                            ):  ## T4
                                types = d["device"]["capability"]["capability"][1][
                                    "type"
                                ]
                            else:
                                types = d["device"]["capability"]["capability"]["type"]
                            l_types = [
                                dict(a) for a in types if a["name"][-1] in ["C", "Q"]
                            ]
                            for a in l_types:
                                a["name"] = a["name"].replace("GRID ", "")
                        l_types.sort(key=lambda r: int(r["name"][:-1].split("-")[-1]))
                        type_max_gpus = l_types[0]["name"].split("-")[-1]
                        model_gpu = l_types[0]["name"].split("-")[-2]

                        d_types = {
                            a["name"].split("-")[-1]: {
                                "id": a["@id"],
                                "available": min(
                                    int(a.get("availableInstances", 0)),
                                    NVIDIA_MODELS.get(a["name"], {}).get("max", 0),
                                ),
                                "memory": NVIDIA_MODELS.get(a["name"], {}).get("mb", 0),
                                "max": NVIDIA_MODELS.get(a["name"], {}).get("max", 0),
                            }
                            for a in l_types
                        }
                        info_nvidia["types"] = d_types
                        info_nvidia["type_max_gpus"] = type_max_gpus
                        info_nvidia["device_name"] = device_name
                        info_nvidia["pci_id"] = name
                        info_nvidia["path"] = path
                        info_nvidia["parent"] = parent
                        info_nvidia["max_count"] = max_count
                        info_nvidia["max_gpus"] = d_types[type_max_gpus]["max"]
                        info_nvidia["model"] = model_gpu
                        if sub_paths is not False:
                            info_nvidia["sub_paths"] = sub_paths
                        if path_parent is not False:
                            info_nvidia["path_parent"] = path_parent
                        d_info_nvidia[name] = info_nvidia
                    except Exception as e:
                        logs.exception_id.debug("0074")
                        log.error(f"error extracting info from nvidia: {e}")
                        d_types = {}

        self.info["nvidia"] = {k: v["model"] for k, v in d_info_nvidia.items()}
        self.info_nvidia = d_info_nvidia

        video_dict = {
            "allowed": {
                "categories": False,
                "groups": False,
                "roles": False,
                "users": False,
            },
            "description": "{description}",
            "heads": 1,
            "id": "{video_id}",
            "nvidia": True,
            "model": "{model}",
            "profile": "{profile}",
            "name": "{name}",
            "ram": 1024,
            "vram": 1024,
        }

        for d in d_info_nvidia.values():
            model = d["model"]
            for profile, d_info_model in d["types"].items():
                new_video_dict = deepcopy(video_dict)
                video_id = f"nvidia-{model}-{profile}"
                ram = d_info_model["memory"]
                max = d_info_model["max"]
                ram_gb = int(ram / 1024)
                new_video_dict["id"] = video_id
                new_video_dict["name"] = f"Nvidia vGPU {model} {ram_gb}GB"
                new_video_dict[
                    "description"
                ] = f"Nvidia vGPU {model} with profile {profile} with {ram_gb}GB vRAM with maximum {max} vGPUs per device"
                new_video_dict["model"] = model
                new_video_dict["profile"] = profile
                new_video_dict["ram"] = ram
                new_video_dict["vram"] = ram

    def get_types_from_ampere(self, d):
        parent = d["device"]["parent"]
        dev_parent = self.conn.nodeDeviceLookupByName(parent)
        d_dev_parent = xmltodict.parse(dev_parent.XMLDesc())
        path_parent = d_dev_parent["device"]["path"]
        cmd = f"find \"{path_parent}\" -name nvidia-* | grep mdev_supported_types | xargs -I % sh -c 'echo %; cat %/available_instances; cat %/name;'"
        cmds1 = [{"title": f"extract mdev supported types", "cmd": cmd}]
        array_out_err = execute_commands(
            self.hostname, cmds1, port=self.port, dict_mode=True
        )
        if len(array_out_err[0]["err"]) == 0:
            l_types = []
            d_available_instances = {}
            out = array_out_err[0]["out"]
            paths = set()
            types = {}
            for i, line in enumerate(out.splitlines()):
                if i % 3 == 0:
                    path = line
                elif i % 3 == 1:
                    available_instances = int(line)
                else:
                    name = line.replace("NVIDIA ", "")
                    if name[-1] in ["C", "Q"]:
                        paths.add(path.split("/mdev_supported_types/")[0])
                        id_mdev = path.split("/mdev_supported_types/")[1].split("/")[0]
                        types[name] = id_mdev
                        if name not in d_available_instances.keys():
                            d_available_instances[name] = 0
                        d_available_instances[name] += available_instances
                        # print(f"path: {path} -- {line}")
            for name, id_mdev in types.items():
                l_types.append(
                    {
                        "@id": id_mdev,
                        "name": name,
                        "availableInstances": d_available_instances[name],
                    }
                )
            return l_types, paths, path_parent
        else:
            return False, False, False

    def get_mdevs_with_domains(self):
        cmd = """ls /sys/bus/mdev/devices/ |  xargs -I % bash -c 'echo -n "% / "; cat /sys/bus/mdev/devices/%/nvidia/vm_name' """
        cmd_mdevctl = "mdevctl list"
        array_out_err = execute_commands(
            self.hostname, [cmd, cmd_mdevctl], port=self.port
        )
        uuids_and_vms = array_out_err[0]["out"].splitlines()
        mdev_ctl_list = [
            a for a in array_out_err[1]["out"].splitlines() if len(a.strip()) > 0
        ]
        if len(uuids_and_vms) > 0:
            d_mdevs_domains = {
                b[0].strip(): {"vm_name": b[1].strip()}
                for b in [a.split("/") for a in uuids_and_vms]
            }
            d_mdevs = {
                b[0].strip(): {"type_id": b[2], "pci_id": b[1]}
                for b in [a.split() for a in mdev_ctl_list]
            }
            [d.update(d_mdevs_domains[k]) for k, d in d_mdevs.items()]
            return d_mdevs
        else:
            return {}

    def remove_domains_and_gpus_with_invalids_uuids(self):
        # get running mdevs
        d_mdevs_running = self.get_mdevs_with_domains()

        # get all uuids
        all_uuids = {}
        for pci_id, d_pci in self.mdevs.items():
            reset_vgpu_created_started(self.id_hyp_rethink, pci_id, d_mdevs_running)
            for profile, d in d_pci.items():
                for uuid64, i in d.items():
                    if "type_id" not in i.keys():
                        logs.main.error(f"uuid without type_id: {uuid64}")
                    all_uuids[uuid64] = {
                        "profile": profile,
                        "pci_id": pci_id,
                        "type_id": i["type_id"],
                        "pci_mdev_id": i["pci_mdev_id"],
                    }

        destroy_domains = []
        remove_uuids = []

        for uuid_running, d in d_mdevs_running.items():
            # if uuids not exists in database
            if uuid_running not in all_uuids.keys():
                remove_uuids.append(uuid_running)
                if len(d["vm_name"]) > 0:
                    destroy_domains.append(d["vm_name"])
            else:
                pci_mdev_id_running = d["pci_id"]
                type_id_running = d["type_id"]
                if (
                    type_id_running == all_uuids[uuid_running]["type_id"]
                    and pci_mdev_id_running == all_uuids[uuid_running]["pci_mdev_id"]
                ):
                    if len(d["vm_name"]) > 0:
                        if get_domain_status(d["vm_name"]) is None:
                            destroy_domains.append(d["vm_name"])
                        else:
                            domains = self.get_domains()
                            if d["vm_name"] in domains.keys():
                                update_domain_status(
                                    domains[d["vm_name"]]["status"],
                                    d["vm_name"],
                                    hyp_id=self.id_hyp_rethink,
                                )
                                update_vgpu_uuid_started_in_domain(
                                    hyp_id=self.id_hyp_rethink,
                                    pci_id=all_uuids[uuid_running]["pci_id"],
                                    profile=all_uuids[uuid_running]["profile"],
                                    mdev_uuid=uuid_running,
                                    domain_id=d["vm_name"],
                                )
                else:
                    remove_uuids.append(uuid_running)
                    destroy_domains.append(d["vm_name"])

        for domain_id in destroy_domains:
            domains_to_destroy = {d.name(): d for d in self.conn.listAllDomains()}
            if domain_id in domains_to_destroy.keys():
                try:
                    domains_to_destroy[domain_id].destroy()
                except Exception as e:
                    logs.main.error(
                        f"domain {domain_id} with invalid gpu detected is destroyed "
                    )

        # cmds_remove_uuids = [f"echo 1 > /sys/bus/mdev/devices/{uuid_remove}/remove" for uuid_remove in remove_uuids]
        cmds_remove_uuids = [
            f"echo 1 > /sys/bus/mdev/devices/{uuid_remove}/remove"
            for uuid_remove in remove_uuids
        ]
        if len(cmds_remove_uuids) > 0:
            array_out_err = execute_commands(
                self.hostname, cmds_remove_uuids, port=self.port
            )

    def create_uuids(self, d_info_gpu):
        d_uuids = {}
        sub_paths = d_info_gpu.get("sub_paths", False)
        for name, d_type in d_info_gpu["types"].items():
            d = {}
            # in some nvidia cards as A40 d['max'] is None
            if d_type.get("max") is None:
                d_type["max"] = d_type.get("available", 1)
            total_available = max(d_type.get("max", 1), d_type.get("available", 1))
            l_pci_mdev_id = []
            d = {}
            for i in range(total_available):
                if sub_paths is False:
                    path = d_info_gpu["path"]
                else:
                    path = sorted(sub_paths)[i]
                uuid64 = str(uuid.uuid4())
                d[uuid64] = {
                    "pci_mdev_id": l_pci_mdev_id[i]
                    if len(l_pci_mdev_id) > 0
                    else path.split("/")[-1],
                    "type_id": d_type["id"],
                    "created": False,
                    "domain_started": False,
                    "domain_reserved": False,
                }
            d_uuids[name.split("-")[-1]] = d
        return d_uuids

    def delete_vgpus_devices(
        self, gpu_id, d_uids, info_nvidia, selected_gpu_type, hyp_id
    ):
        cmds_create_delete = []
        d_id_mdev_type = {v["id"]: k for k, v in info_nvidia["types"].items()}

        if info_nvidia["model"] == "A40":
            path_parent = info_nvidia["path_parent"]
            uids_in_hyp_now = {}
            id_mdev_selected = info_nvidia["types"][selected_gpu_type]["id"]
            uids_in_hyp_now[id_mdev_selected] = {}

            cmd = (
                f'find "{path_parent}" -name nvidia-* | grep mdev_supported_types | '
                + f"xargs -I % sh -c 'echo %; ls %/devices;'"
            )
            cmds1 = [{"title": f"find mdev devices", "cmd": cmd}]
            array_out_err = execute_commands(
                self.hostname, cmds1, port=self.port, dict_mode=True
            )
            out = array_out_err[0]["out"]
            lines_out = out.splitlines()
            for i in range(len(lines_out)):
                if lines_out[i].find(path_parent) < 0:
                    path = lines_out[i - 1]
                    uid = lines_out[i]
                    sub_path_dev = path.split("/mdev_supported_types/")[0]
                    id_mdev = path.split("/mdev_supported_types/")[1].split("/")[0]
                    if id_mdev == id_mdev_selected:
                        uids_in_hyp_now[id_mdev_selected][sub_path_dev] = uid
                    else:
                        name = d_id_mdev_type[id_mdev]
                        cmd = f'echo 1 > "{sub_path_dev}/{uid}/remove"'
                        cmds_create_delete.append(
                            {
                                "title": f"remove uuid to {name}: {uid}",
                                "cmd": cmd,
                            }
                        )

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
        xml_stopped = ""
        xml_started = ""
        try:
            d = self.conn.defineXML(xml_text)
            d.undefine()
            try:
                d = self.conn.createXML(xml_text, flags=libvirt.VIR_DOMAIN_START_PAUSED)
                xml_started = d.XMLDesc()
                xml_stopped = d.XMLDesc(libvirt.VIR_DOMAIN_XML_INACTIVE)
                d.destroy()
            except Exception as e:
                logs.exception_id.debug("0032")
                log.error("error starting paused vm: {}".format(e))

        except Exception as e:
            logs.exception_id.debug("0033")
            log.error("error defining vm: {}".format(e))

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
                for d in self.conn.listAllDomains(
                    libvirt.VIR_CONNECT_LIST_DOMAINS_ACTIVE
                ):
                    try:
                        domain_name = d.name()
                        l_libvirt_state = d.state()
                        state_id = l_libvirt_state[0]
                        reason_id = (
                            -1 if len(l_libvirt_state) < 2 else l_libvirt_state[1]
                        )
                        self.domains_states[domain_name] = {
                            "status": virDomainState[state_id]["status"],
                            "detail": virDomainState[state_id]
                            .get("reason", {})
                            .get(reason_id, {})
                            .get("detail", ""),
                        }
                    except:
                        log.info(
                            "unkown domain fail when trying to get his name, power off??"
                        )
                        continue
                    self.domains[domain_name] = d
            except:
                log.error(
                    "error when try to list domain in hypervisor {}".format(
                        self.hostname
                    )
                )
                self.domains = {}

        return self.domains_states

    def update_domain_coherence_in_db(self):
        d_domains_with_states = self.get_domains()
        set_domains_running_in_hyps = set()
        if self.id_hyp_rethink is None:
            try:
                self.id_hyp_rethink = get_id_hyp_from_uri(self.uri)
                if self.id_hyp_rethink is None:
                    log.error("error when hypervisor have not rethink id. {}".format(e))
                    raise TypeError
            except Exception as e:
                logs.exception_id.debug("0034")
                log.error("error when hypervisor have not rethink id. {}".format(e))
                raise e
        for domain_id, d in d_domains_with_states.items():
            update_domain_status(
                d["status"], domain_id, hyp_id=self.id_hyp_rethink, detail=d["detail"]
            )
            set_domains_running_in_hyps.add(domain_id)
        domains_with_hyp_started_in_db = get_domains_started_in_hyp(self.id_hyp_rethink)
        set_domains_with_hyp_started_in_db = set(
            list(domains_with_hyp_started_in_db.keys())
        )
        domains_to_be_stopped = set_domains_with_hyp_started_in_db.difference(
            set_domains_running_in_hyps
        )
        for domain_id in domains_to_be_stopped:
            update_domain_status(
                "Stopped",
                domain_id,
                detail=f"domain not running in hyp {self.id_hyp_rethink}",
            )

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
            log.error("error closing connexion for hypervisor {}".format(self.hostname))
            self.set_status(HYP_STATUS_ERROR_WHEN_CLOSE_CONNEXION)

    def get_stats_from_libvirt(self, exclude_domains_not_isard=True):
        raw_stats = {}
        if self.connected:
            # get CPU Stats
            try:
                raw_stats["cpu"] = self.conn.getCPUStats(
                    libvirt.VIR_NODE_CPU_STATS_ALL_CPUS
                )
            except:
                log.error("getCPUStats fail in hypervisor {}".format(self.hostname))
                return False

            # get Memory Stats
            try:
                raw_stats["memory"] = self.conn.getMemoryStats(-1, 0)
            except:
                log.error("getMemoryStats fail in hypervisor {}".format(self.hostname))
                return False

            # get All Domain Stats
            try:
                # l_stats = self.conn.getAllDomainStats(flags=libvirt.VIR_CONNECT_GET_ALL_DOMAINS_STATS_ACTIVE)
                raw_stats["domains"] = {
                    l[0].name(): {"stats": l[1], "state": l[0].state(), "d": l[0]}
                    for l in self.conn.getAllDomainStats(
                        flags=libvirt.VIR_CONNECT_LIST_DOMAINS_ACTIVE
                    )
                }

                raw_stats["time_utc"] = int(time.time())

            except:
                log.error(
                    "getAllDomainStats fail in hypervisor {}".format(self.hostname)
                )
                return False

            return raw_stats

        else:
            log.error(
                "can not get stats from libvirt if hypervisor {} is not connected".format(
                    self.hostname
                )
            )
            return False

    def process_hypervisor_stats(self, raw_stats):
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

    def create_stats_vars(self, testing=True):
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

    def launch_thread_status_polling(self, polling_interval=0):
        self.polling_thread = self.PollingStats(self, polling_interval)
        self.polling_thread.daemon = True
        self.polling_thread.start()

    class PollingStats(threading.Thread):
        def __init__(self, hyp_obj, polling_interval=0, stop=False):
            threading.Thread.__init__(self)
            self.name = "PollingStats_{}".format(hyp_obj.hostname)
            self.hyp_obj = hyp_obj
            if polling_interval == 0:
                self.polling_interval = self.stats_polling_interval
            else:
                self.polling_interval = polling_interval
            self.stop = stop
            self.tid = False

        def run(self):
            self.tid = get_tid()
            log.info("starting thread: {} (TID {})".format(self.name, self.tid))
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

        domains_with_stats = list(raw_stats["domains"].keys())
        # broom action: domains that are started or stopped in stats that have errors in database
        self.update_domains_started_and_stopped(domains_with_stats)

        self.process_hypervisor_stats(raw_stats)

        if len(self.stats_hyp_now) > 0:
            self.send_stats()

        return True

    def update_domains_started_and_stopped(self, domains_with_stats):
        if self.id_hyp_rethink is None:
            try:
                self.id_hyp_rethink = get_id_hyp_from_uri(
                    hostname_to_uri(self.hostname, user=self.user, port=self.port)
                )
            except Exception as e:
                logs.exception_id.debug("0035")
                log.error("error when hypervisor have not rethink id. {}".format(e))
                return False
        l_all_domains = get_domains_with_status_in_list(
            list_status=["Started", "Shutting-down", "Stopped", "Failed"]
        )
        for d in l_all_domains:
            if d["id"] in domains_with_stats:
                if d["status"] == "Started" or d["status"] == "Shutting-down":
                    # if status started check if has the same hypervisor
                    if d["hyp_started"] != self.id_hyp_rethink:
                        log.error(
                            f"Domain {d['id']} started in hypervisor ({self.id_hyp_rethink}) but database says that is started in {d['hyp_started']} !! "
                        )
                        update_domain_status(
                            status=d["status"],
                            id_domain="_admin_downloaded_tetros",
                            detail=f"Started in other hypervisor!! {self.id_hyp_rethink}. Updated by status thread",
                            hyp_id=self.id_hyp_rethink,
                        )
                else:
                    # if status is Stopped or Failed update, the domain is started
                    log.info(
                        "Domain is started in {self.id_hyp_rethink} but in database was Stopped or Failed, updated by status thread"
                    )
                    update_domain_status(
                        status="Started",
                        id_domain="_admin_downloaded_tetros",
                        detail=f"Domain is started in {self.id_hyp_rethink} but in database was Stopped or Failed, updated by status thread",
                        hyp_id=self.id_hyp_rethink,
                    )

            elif d["hyp_started"] == self.id_hyp_rethink:
                # Domain is started in this hypervisor in database, but is stopped
                if d["status"] == "Started":
                    update_domain_status(
                        status="Stopped",
                        id_domain="_admin_downloaded_tetros",
                        detail=f"Domain is stopped in {self.id_hyp_rethink} but in database was Started, updated by status thread",
                    )

    def send_stats(self):
        # hypervisors
        send_stats_to_rethink = True
        if self.id_hyp_rethink is None:
            # self.id_hyp_rethink = get_id_hyp_from_uri('qemu+ssh://root@isard-hypervisor:22/system')
            self.id_hyp_rethink = get_id_hyp_from_uri(
                hostname_to_uri(self.hostname, user=self.user, port=self.port)
            )
        if send_stats_to_rethink:
            update_actual_stats_hyp(self.id_hyp_rethink, self.stats_hyp_now)

            for id_domain, s in self.stats_domains_now.items():
                means = {
                    "near": self.stats_domains[id_domain].get("means_near", False),
                    "medium": self.stats_domains[id_domain].get("means_medium", False),
                    "long": self.stats_domains[id_domain].get("means_long", False),
                    "total": self.stats_domains[id_domain].get("means_total", False),
                    "boot": self.stats_domains[id_domain].get("means_boot", False),
                }
                update_actual_stats_domain(id_domain, s, means)
            # for (h in )

    def get_eval_statistics(self):
        cpu_percent_free = 100 - self.stats_hyp_now.get("cpu_load", 0)
        ram_percent_free = 100 - self.stats_hyp_now.get("mem_load_rate", 0)
        data = {
            "cpu_percent_free": cpu_percent_free,
            "ram_percent_free": ram_percent_free,
            "domains": list(self.stats_domains_now.keys()),
        }
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
        data["ram_hyp_usage"] = self.stats_hyp_now.get("mem_load_rate")
        data["cpu_hyp_usage"] = self.stats_hyp_now.get("cpu_load")
        data["cpu_hyp_iowait"] = self.stats_hyp_now.get("cpu_iowait")
        domain_stats = self.stats_domains_now.get(domain_id)
        if domain_stats:
            data["cpu_usage"] = domain_stats.get("cpu_load")
        return data
