# Copyright 2017 the Isard-vdi project authors:
#      Alberto Larraz Dalmases
#      Josep Maria Viñolas Auquer
# License: AGPLv3

import ctypes
import json
import os
import queue
import shlex
import socket
import sys
import threading
import time
from pprint import pformat
from time import sleep

import libvirt
import paramiko
import xmltodict
from engine.services.db import (
    gen_new_mac,
    get_disks_all_domains,
    update_disk_backing_chain,
    update_domain_status,
)
from engine.services.db.config import table_config_created_and_populated
from engine.services.db.domains import (
    delete_incomplete_creating_domains,
    fail_incomplete_creating_domains,
    fail_started_domains_without_hypervisors,
    start_incomplete_starting_domains,
    stop_incomplete_starting_domains,
    unknown_started_domains,
    update_domain_progress,
    update_domain_status,
)
from engine.services.log import log, logs

QCOW2_CLUSTER_SIZE = os.environ.get("QCOW2_CLUSTER_SIZE", "4k")
QCOW2_EXTENDED_L2 = os.environ.get("QCOW2_EXTENDED_L2", "off")


def check_tables_populated():
    while True:
        if table_config_created_and_populated() is True:
            break
        else:
            log.info("waiting config table created")
            sleep(1)


def backing_chain_cmd(path_disk, json_format=True):
    if json_format is True:
        cmd = 'qemu-img info -U --output json --backing-chain "{}"'.format(path_disk)
    else:
        cmd = 'qemu-img info -U --backing-chain "{}"'.format(path_disk)
    return cmd


def get_threads_running():
    e = threading.enumerate()
    return e


def get_threads_names_running():
    e = threading.enumerate()
    l = [t.name for t in e]
    l.sort()
    return l


def get_pools_threads_running(hypervisors):
    hypervisors_with_thread = []
    for hyp in hypervisors:
        if "worker_" + hyp["id"] in get_threads_names_running():
            hypervisors_with_thread.append(hyp)
    return hypervisors_with_thread


def get_diskoperations_pools_threads_running(hypervisors):
    hypervisors_with_thread = []
    for hyp in hypervisors:
        if "diskop_" + hyp["id"] in get_threads_names_running():
            hypervisors_with_thread.append(hyp)
    return hypervisors_with_thread


def get_tid():
    tid = ctypes.CDLL("libc.so.6").syscall(186)
    return tid


def randomMAC():
    return gen_new_mac()


class TimeLimitExpired(Exception):
    pass


def timelimit(timeout, func, arg1):
    """Run func with the given timeout. If func didn't finish running
    within the timeout, raise TimeLimitExpired
    """

    class FuncThread(threading.Thread):
        def __init__(self):
            threading.Thread.__init__(self)
            self.result = None

        def run(self):
            self.tid = get_tid()
            log.info("starting thread: {} (TID {})".format(self.name, self.tid))
            self.result = func(arg1)

    it = FuncThread()
    it.start()
    it.join(timeout)
    # if it.isAlive():
    #    raise TimeLimitExpired()
    return it.result


def try_socket(hostname, port, timeout):
    try:
        ip = socket.gethostbyname(hostname)

        addr = (ip, int(port))
        sock = socket.socket(2, socket.SOCK_STREAM)
        sock.settimeout(timeout)
        try:
            sock.connect(addr)
            sock.close()
            return True
        except socket.error as e:
            log.error("trying socket has error: {}".format(e))
            return False
        except Exception as e:
            logs.exception_id.debug("0047")
            log.error(e)
            return False
    except socket.error as e:
        log.error(e)
        log.error("not resolves ip from hostname: {}".format(hostname))
        return False


def try_ssh_command(host, user, port):
    # TRY IF SSH COMMAND RUN:
    cmds = [{"cmd": "uname -a"}]
    try:
        array_out_err = exec_remote_list_of_cmds_dict(
            host, cmds, username=user, port=port
        )
        output = array_out_err[0]["out"]
        logs.main.debug(f"cmd: {cmds[0]}, output: {output}")
        if len(output) > 0:
            # TEST OK
            return True, "test cmd ssh ok"
        else:
            error = "output from command uname -a is empty, ssh action failed"
            return False, error
    except Exception as e:
        logs.exception_id.debug("0048")
        error = f"testing ssh connection failed. Host: {host}, cmds: {cmds}, username={user}, port: {port}. Exception: {e}"
        return False, error


def test_hypervisor_conn(uri):
    """test hypervisor connecton, if fail an error message in log"""
    try:
        # time.sleep(5)
        logs.main.debug(f"TRY TO CONNECT URI: {uri}")
        handle = libvirt.open(uri)
        return handle
    except:
        log.error(sys.exc_info()[1])
        return False


def calcule_cpu_hyp_stats(start, end, round_digits=3):
    diff_time = {}
    percent = {}
    total_diff_time = sum(end.values()) - sum(start.values())

    # sum of all times in all cpus, for example for 12 cpus and 5 seconds between samples
    # total_diff_time_in_seconds must be 60
    for k in start.keys():
        diff_time[k] = end[k] - start[k]
        percent[k] = round(
            (diff_time[k] / float(total_diff_time)) * 100.0, round_digits
        )
    percent["used"] = round(
        percent["iowait"] + percent["kernel"] + percent["user"], round_digits
    )
    return percent, diff_time, total_diff_time


DEFAULT_SIZE_TO_DISK = "10G"


def create_new_disk_cmd(
    filename,
    size=DEFAULT_SIZE_TO_DISK,
    clustersize=QCOW2_CLUSTER_SIZE,
    extended_l2=QCOW2_EXTENDED_L2,
):
    filename = shlex.quote(filename)
    cmd = "qemu-img create -f qcow2 -o cluster_size={clustersize},extended_l2={extended_l2} {filename} {size}"
    cmd = cmd.format(
        filename=filename, size=size, clustersize=clustersize, extended_l2=extended_l2
    )
    return cmd


def exec_remote_cmd(command, hostname, username="root", port=22, sudo=False):
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect(hostname, port=port, username=username)
    stdin, stdout, stderr = client.exec_command(command)

    out = stdout.read()
    err = stderr.read()

    client.close()

    return {"out": out, "err": err}


def replace_path_disk(path_original, path_replace):
    return path_original


def exec_remote_updating_progress(
    command, hostname, progress=[], username="root", port=22, sudo=False, id_domain=None
):
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect(hostname, port=port, username=username)
    stdin, stdout, stderr = client.exec_command(command)
    progress.append(0)

    # INFO TO DEVELOPER, AQUÍ FALTA ACTUALIZAR EL PROGRESO A LA BASE DE DATOS
    # A PARTIR DE LA LISTA PROGRESS, COGIENDO EL ÚLTIMO PARÁMETRO
    # SE PODRÍA IR MIRANDO, AUNQUE LO SUYO ES QUE SE ACTUALIZASE AQUÍ??
    log.debug("jujuju {} ".format(type(stdout)))
    while True:
        # out = stdout.readline(64).decode('utf-8')
        out = stdout.readline(64)
        if out.find("%") >= 0:
            tmp = out[: str(out).find("%")]
            percent = tmp[tmp.rfind(" ") + 1 :]
            if len(percent) > 0:
                if percent.isdigit():
                    percent = int(percent)
                    if progress[-1] < percent:
                        progress.append(percent)
                        if id_domain != None:
                            update_domain_progress(id_domain, percent)
        log.debug(out)
        if out == "":
            break

    out = stdout.read()
    err = stderr.read()

    client.close()

    return {"out": out, "err": err}


def exec_remote_list_of_cmds(hostname, commands, username="root", port=22, sudo=False):
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect(hostname, port=port, username=username)

    returned_array = []

    for command in commands:
        log.debug("command to launch in ssh in {}: {}".format(hostname, command))
        # print('command to launch in ssh in {}: {}'.format(hostname, command))
        stdin, stdout, stderr = client.exec_command(command)
        out = stdout.read().decode("utf-8")
        err = stderr.read().decode("utf-8")
        returned_array.append({"out": out, "err": err})
        log.debug("commnad launched / out: {} / error: {}".format(out, err))
        # print('commnad launched / out: {} / error: {}'.format(out, err))

    client.close()

    return returned_array


def exec_remote_list_of_cmds_dict(
    hostname, list_dict_commands, username="root", port=22, ssh_key_str="", sudo=False
):
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    if len(ssh_key_str) > 0:
        # TODO: make ssh_key login
        pass
    else:
        client.connect(hostname, port=port, username=username)

    returned_array = list_dict_commands.copy()

    i = 0
    for command in list_dict_commands:
        log.debug("command to launch in ssh in {}: {}".format(hostname, command["cmd"]))
        # print('command dict to launch in ssh in {}: {}'.format(hostname, command['cmd']))
        stdin, stdout, stderr = client.exec_command(command["cmd"])
        returned_array[i]["out"] = stdout.read().decode("utf-8")
        returned_array[i]["err"] = stderr.read().decode("utf-8")
        log.debug(
            "commnad launched / out: {} / error: {}".format(
                returned_array[i]["out"], returned_array[i]["err"]
            )
        )
        # print('commnad dict launched / out: {} / error: {}'.format(returned_array[i]['out'], returned_array[i]['err']))
        i = i + 1

    client.close()

    return returned_array


def new_dict_from_raw_dict_stats(raw_values, round_digits=6):
    d = {}

    # old versions of libvirt not suport this key
    if "cpu.time" in raw_values:
        d["cpu_time"] = round(raw_values["cpu.time"] / 1000000000.0, round_digits)
    else:
        log.warning(
            "cpu.time value in domain stats is not available, try update libvirt"
        )
        d["cpu_time"] = 0.0
    d["vcpus"] = raw_values["vcpu.current"]
    if "balloon.current" in raw_values:
        d["ram_current"] = raw_values["balloon.current"]
    else:
        log.warning(
            "cpu.time value in stats of some domain is not available, "
            + "force shutdown could cause this issue"
        )
        d["ram_current"] = 0
    d["ram_defined"] = raw_values["balloon.maximum"]
    d["state"] = raw_values["state.state"]

    # disks write read stats
    r_bytes = 0
    w_bytes = 0
    r_reqs = 0
    w_reqs = 0

    for i in range(raw_values.get("block.count", 0)):
        r_bytes += raw_values.get("block." + str(i) + ".rd.bytes", 0)

        if "block." + str(i) + ".wr.bytes" in raw_values.keys():
            w_bytes += raw_values.get("block." + str(i) + ".wr.bytes", 0)
        else:
            w_bytes += 0

        r_reqs += raw_values.get("block." + str(i) + ".rd.reqs", 0)

        if "block." + str(i) + ".wr.reqs" in raw_values.keys():
            w_reqs += raw_values.get("block." + str(i) + ".wr.reqs", 0)
        else:
            w_reqs += 0

    d["block_r_bytes"] = int(r_bytes)
    d["block_w_bytes"] = int(w_bytes)
    d["block_r_reqs"] = int(r_reqs)
    d["block_w_reqs"] = int(w_reqs)

    # net write read stats
    r_bytes = 0
    w_bytes = 0
    r_pkts = 0
    w_pkts = 0
    r_drop = 0
    w_drop = 0
    r_errs = 0
    w_errs = 0

    for i in range(raw_values.get("net.count", 0)):
        r_bytes += raw_values.get("net." + str(i) + ".rx.bytes", 0)
        w_bytes += raw_values.get("net." + str(i) + ".tx.bytes", 0)
        r_drop += raw_values.get("net." + str(i) + ".rx.drop", 0)
        w_drop += raw_values.get("net." + str(i) + ".tx.drop", 0)
        r_pkts += raw_values.get("net." + str(i) + ".rx.pkts", 0)
        w_pkts += raw_values.get("net." + str(i) + ".tx.pkts", 0)
        r_errs += raw_values.get("net." + str(i) + ".rx.errs", 0)
        w_errs += raw_values.get("net." + str(i) + ".tx.errs", 0)

    d["net_r_bytes"] = round(r_bytes, 2)
    d["net_w_bytes"] = round(w_bytes, 2)
    d["net_r_drop"] = round(r_drop, 2)
    d["net_w_drop"] = round(w_drop, 2)
    d["net_r_pkts"] = round(r_pkts, 2)
    d["net_w_pkts"] = round(w_pkts, 2)
    d["net_r_errs"] = round(r_errs, 2)
    d["net_w_errs"] = round(w_errs, 2)

    return d


# Mappings from state number to string representation
state_mapping = {
    0: "libvirt.VIR_DOMAIN_NOSTATE",
    1: "libvirt.VIR_DOMAIN_RUNNING",
    2: "libvirt.VIR_DOMAIN_BLOCKED",
    3: "libvirt.VIR_DOMAIN_PAUSED",
    4: "libvirt.VIR_DOMAIN_SHUTDOWN",
    5: "libvirt.VIR_DOMAIN_SHUTOFF",
    6: "libvirt.VIR_DOMAIN_CRASHED",
    7: "libvirt.VIR_DOMAIN_PMSUSPENDED",
}

# Mappings from cause number to string representation
cause_mapping = {
    0: "libvirt.VIR_DOMAIN_NOSTATE_UNKNOWN",
    1: "libvirt.VIR_DOMAIN_RUNNING_BOOTED",
    2: "libvirt.VIR_DOMAIN_RUNNING_CRASHED",
    3: "libvirt.VIR_DOMAIN_RUNNING_FROM_SNAPSHOT",
    4: "libvirt.VIR_DOMAIN_RUNNING_MIGRATED",
    5: "libvirt.VIR_DOMAIN_RUNNING_MIGRATION_CANCELED",
    6: "libvirt.VIR_DOMAIN_RUNNING_RESTORED",
    7: "libvirt.VIR_DOMAIN_RUNNING_SAVE_CANCELED",
    8: "libvirt.VIR_DOMAIN_RUNNING_UNKNOWN",
    9: "libvirt.VIR_DOMAIN_RUNNING_UNPAUSED",
    10: "libvirt.VIR_DOMAIN_RUNNING_WAKEUP",
    11: "libvirt.VIR_DOMAIN_BLOCKED_UNKNOWN",
    12: "libvirt.VIR_DOMAIN_PAUSED_CRASHED",
    13: "libvirt.VIR_DOMAIN_PAUSED_DUMP",
    14: "libvirt.VIR_DOMAIN_PAUSED_FROM_SNAPSHOT",
    15: "libvirt.VIR_DOMAIN_PAUSED_IOERROR",
    16: "libvirt.VIR_DOMAIN_PAUSED_MIGRATION",
    17: "libvirt.VIR_DOMAIN_PAUSED_SAVE",
    18: "libvirt.VIR_DOMAIN_PAUSED_SHUTTING_DOWN",
    19: "libvirt.VIR_DOMAIN_PAUSED_SNAPSHOT",
    20: "libvirt.VIR_DOMAIN_PAUSED_STARTING_UP",
    21: "libvirt.VIR_DOMAIN_PAUSED_UNKNOWN",
    22: "libvirt.VIR_DOMAIN_PAUSED_USER",
    23: "libvirt.VIR_DOMAIN_PAUSED_WATCHDOG",
    24: "libvirt.VIR_DOMAIN_SHUTDOWN_ACPI_POWER_BTN",
    25: "libvirt.VIR_DOMAIN_SHUTDOWN_DEFAULT",
    26: "libvirt.VIR_DOMAIN_SHUTDOWN_GUEST_AGENT",
    27: "libvirt.VIR_DOMAIN_SHUTDOWN_INITCTL",
    28: "libvirt.VIR_DOMAIN_SHUTDOWN_PARAVIRT",
    29: "libvirt.VIR_DOMAIN_SHUTDOWN_SIGNAL",
    30: "libvirt.VIR_DOMAIN_SHUTDOWN_UNKNOWN",
    31: "libvirt.VIR_DOMAIN_SHUTDOWN_USER",
    32: "libvirt.VIR_DOMAIN_SHUTOFF_CRASHED",
    33: "libvirt.VIR_DOMAIN_SHUTOFF_DESTROYED",
    34: "libvirt.VIR_DOMAIN_SHUTOFF_FAILED",
    35: "libvirt.VIR_DOMAIN_SHUTOFF_FROM_SNAPSHOT",
    36: "libvirt.VIR_DOMAIN_SHUTOFF_MIGRATED",
    37: "libvirt.VIR_DOMAIN_SHUTOFF_SAVED",
    38: "libvirt.VIR_DOMAIN_SHUTOFF_SHUTDOWN",
    39: "libvirt.VIR_DOMAIN_SHUTOFF_UNKNOWN",
    40: "libvirt.VIR_DOMAIN_CRASHED_UNKNOWN",
    41: "libvirt.VIR_DOMAIN_CRASHED_PANICKED",
    42: "libvirt.VIR_DOMAIN_PMSUSPENDED_DISK_UNKNOWN",
    43: "libvirt.VIR_DOMAIN_PMSUSPENDED_UNKNOWN",
}

# Create the dictionary to store state information and cause codes
dict_domain_libvirt_state_to_isard_state = {
    "running": "Started",
    "locked": "Failed",
    "paused": "Paused",
    "shutdown": "Shutting-down",
    "shutoff": "Stopped",
    "crashed": "Failed",
    "nostate": "Failed",
    "pmsuspended": "Failed",
}

dict_state = {}
for a in state_mapping.values():
    dict_state[a] = {"code": a.split("_")[-1].lower(), "cause": {}}
    for b in cause_mapping.values():
        if b.find(a) >= 0:
            dict_state[a]["cause"][b] = b.split("_")[-1].lower()


# Function to convert state_number and cause_number into string representations
def state_and_cause_to_str(state_number, cause_number):
    try:
        state_str = dict_state[state_mapping[state_number]]["code"]
        cause_str = dict_state[state_mapping[state_number]]["cause"][
            cause_mapping[cause_number]
        ]
    except KeyError:
        return "unknown_state", "unknown_cause"
    return state_str, cause_str


def calcule_disk_net_domain_load(time_elapsed, raw_stats_after, raw_stats_before):
    block_dict = {}
    net_dict = {}

    block_dict["block_r_bytes_per_sec"] = (
        raw_stats_after["block_r_bytes"] - raw_stats_before["block_r_bytes"]
    ) / time_elapsed
    block_dict["block_w_bytes_per_sec"] = (
        raw_stats_after["block_w_bytes"] - raw_stats_before["block_w_bytes"]
    ) / time_elapsed
    block_dict["block_r_reqs_per_sec"] = (
        raw_stats_after["block_r_reqs"] - raw_stats_before["block_r_reqs"]
    ) / time_elapsed
    block_dict["block_w_reqs_per_sec"] = (
        raw_stats_after["block_w_reqs"] - raw_stats_before["block_w_bytes"]
    ) / time_elapsed

    net_dict["net_r_bytes_per_sec"] = (
        raw_stats_after["net_r_bytes"] - raw_stats_before["net_r_bytes"]
    ) / time_elapsed
    net_dict["net_w_bytes_per_sec"] = (
        raw_stats_after["net_w_bytes"] - raw_stats_before["net_w_bytes"]
    ) / time_elapsed
    net_dict["net_r_drop_per_sec"] = (
        raw_stats_after["net_r_drop"] - raw_stats_before["net_r_drop"]
    ) / time_elapsed
    net_dict["net_w_drop_per_sec"] = (
        raw_stats_after["net_w_drop"] - raw_stats_before["net_w_drop"]
    ) / time_elapsed
    net_dict["net_r_pkts_per_sec"] = (
        raw_stats_after["net_r_pkts"] - raw_stats_before["net_r_pkts"]
    ) / time_elapsed
    net_dict["net_w_pkts_per_sec"] = (
        raw_stats_after["net_w_pkts"] - raw_stats_before["net_w_pkts"]
    ) / time_elapsed
    net_dict["net_r_errs_per_sec"] = (
        raw_stats_after["net_r_errs"] - raw_stats_before["net_r_errs"]
    ) / time_elapsed
    net_dict["net_w_errs_per_sec"] = (
        raw_stats_after["net_w_errs"] - raw_stats_before["net_w_errs"]
    ) / time_elapsed

    return block_dict, net_dict

    total_vcpus = 0
    total_mem_current = 0
    total_mem_defined = 0
    total_mem_usage = 0
    #
    #
    #
    #
    #     time_elapsed = (after - before).total_seconds()
    #
    #     cpu_dict = calcule_cpu_stats(hyp_cpu_stats_before,hyp_cpu_stats_after)[0]
    #
    #     block_dict = {}
    #     net_dict = {}
    #     domain_dict={}
    #
    #
    #     block_dict['block_r_bytes_per_sec']  = 0
    #     block_dict['block_w_bytes_per_sec']  = 0
    #     block_dict['block_r_reqs_per_sec']  = 0
    #     block_dict['block_w_reqs_per_sec']  = 0
    #
    #     net_dict['net_r_bytes_per_sec'] = 0
    #     net_dict['net_w_bytes_per_sec'] = 0
    #     net_dict['net_r_drop_per_sec'] = 0
    #     net_dict['net_w_drop_per_sec'] = 0
    #     net_dict['net_r_pkts_per_sec'] = 0
    #     net_dict['net_w_pkts_per_sec'] = 0
    #     net_dict['net_r_errs_per_sec'] = 0
    #     net_dict['net_w_errs_per_sec'] = 0
    #
    #     total_vcpus = 0
    #     total_mem_current = 0
    #     total_mem_defined = 0
    #     total_mem_usage = 0
    #
    #     if len(domains) > 0:
    #         dict_stats = extract_stats_from_domains(raw_stats_before, raw_stats_after)
    #
    #
    #         for sysname in dict_stats['after'].keys():
    #             if sysname in dict_stats['before'].keys():
    #                 domain_dict[sysname]={}
    #
    #                 diff = dict_stats['after'][sysname]['cpu_time'] - dict_stats['before'][sysname]['cpu_time']
    #                 domain_dict[sysname]['cpu_usage'] = (diff/time_elapsed) * 100 / total_cpu_threads
    #
    #                 #ram in kB
    #                 ram_current = dict_stats['after'][sysname]['ram_current']
    #                 domain_dict[sysname]['ram_usage'] = ram_current * 100 / mem_total
    #                 domain_dict[sysname]['ram_current'] = dict_stats['after'][sysname]['ram_current']
    #                 domain_dict[sysname]['ram_defined'] = dict_stats['after'][sysname]['ram_defined']
    #
    #                 total_mem_current += domain_dict[sysname]['ram_current']
    #                 total_mem_defined += domain_dict[sysname]['ram_defined']
    #                 total_mem_usage   += domain_dict[sysname]['ram_usage']
    #
    #
    #                 domain_dict[sysname]['vcpus'] = dict_stats['after'][sysname]['vcpus']
    #                 domain_dict[sysname]['state'] = dict_stats['after'][sysname]['state']
    #
    #                 total_vcpus += domain_dict[sysname]['vcpus']
    #
    #                 diff = dict_stats['after'][sysname]['block_r_bytes'] - dict_stats['before'][sysname]['block_r_bytes']
    #                 domain_dict[sysname]['block_r_bytes_per_sec'] = (diff/time_elapsed)
    #                 block_dict['block_r_bytes_per_sec'] += (diff/time_elapsed)
    #
    #                 diff = dict_stats['after'][sysname]['block_w_bytes'] - dict_stats['before'][sysname]['block_w_bytes']
    #                 domain_dict[sysname]['block_w_bytes_per_sec'] = (diff/time_elapsed)
    #                 block_dict['block_w_bytes_per_sec'] += (diff/time_elapsed)
    #
    #                 diff = dict_stats['after'][sysname]['block_r_reqs'] - dict_stats['before'][sysname]['block_r_reqs']
    #                 domain_dict[sysname]['block_r_reqs_per_sec'] = (diff/time_elapsed)
    #                 block_dict['block_r_reqs_per_sec'] += (diff/time_elapsed)
    #
    #                 diff = dict_stats['after'][sysname]['block_w_reqs'] - dict_stats['before'][sysname]['block_w_reqs']
    #                 domain_dict[sysname]['block_w_reqs_per_sec'] = (diff/time_elapsed)
    #                 block_dict['block_w_reqs_per_sec'] += (diff/time_elapsed)
    #
    #
    #                 diff = dict_stats['after'][sysname]['net_r_bytes'] - dict_stats['before'][sysname]['net_r_bytes']
    #                 domain_dict[sysname]['net_r_bytes_per_sec'] = (diff/time_elapsed)
    #                 net_dict['net_r_bytes_per_sec'] += (diff/time_elapsed)
    #
    #                 diff = dict_stats['after'][sysname]['net_w_bytes'] - dict_stats['before'][sysname]['net_w_bytes']
    #                 domain_dict[sysname]['net_w_bytes_per_sec'] = (diff/time_elapsed)
    #                 net_dict['net_w_bytes_per_sec'] += (diff/time_elapsed)
    #
    #
    #                 diff = dict_stats['after'][sysname]['net_r_drop'] - dict_stats['before'][sysname]['net_r_drop']
    #                 domain_dict[sysname]['net_r_drop_per_sec'] = (diff/time_elapsed)
    #                 net_dict['net_r_drop_per_sec'] += (diff/time_elapsed)
    #
    #
    #                 diff = dict_stats['after'][sysname]['net_w_drop'] - dict_stats['before'][sysname]['net_w_drop']
    #                 domain_dict[sysname]['net_w_drop_per_sec'] = (diff/time_elapsed)
    #                 net_dict['net_w_drop_per_sec'] += (diff/time_elapsed)
    #
    #
    #                 diff = dict_stats['after'][sysname]['net_r_pkts'] - dict_stats['before'][sysname]['net_r_pkts']
    #                 domain_dict[sysname]['net_r_pkts_per_sec'] = (diff/time_elapsed)
    #                 net_dict['net_r_pkts_per_sec'] += (diff/time_elapsed)
    #
    #
    #                 diff = dict_stats['after'][sysname]['net_w_pkts'] - dict_stats['before'][sysname]['net_w_pkts']
    #                 domain_dict[sysname]['net_w_pkts_per_sec'] = (diff/time_elapsed)
    #                 net_dict['net_w_pkts_per_sec'] += (diff/time_elapsed)
    #
    #
    #                 diff = dict_stats['after'][sysname]['net_r_errs'] - dict_stats['before'][sysname]['net_r_errs']
    #                 domain_dict[sysname]['net_r_errs_per_sec'] = (diff/time_elapsed)
    #                 net_dict['net_r_errs_per_sec'] += (diff/time_elapsed)
    #
    #                 diff = dict_stats['after'][sysname]['net_w_errs'] - dict_stats['before'][sysname]['net_w_errs']
    #                 domain_dict[sysname]['net_w_errs_per_sec'] = (diff/time_elapsed)
    #                 net_dict['net_w_errs_per_sec'] += (diff/time_elapsed)
    #
    #
    #                 #TODO: sería buen momento al actualizar las estadísticas mirar cual es el state del hypervisor
    #                 # y actualizarlo si ha variado
    #
    #
    #     cpu_dict['total_vcpus'] = total_vcpus
    #     mem_dict['total_mem_current'] = total_mem_current
    #     mem_dict['total_mem_defined'] = total_mem_defined
    #     mem_dict['total_mem_usage']   = total_mem_usage
    #
    #     all_stats[hostname] = {}
    #     all_stats[hostname]['cpu'] = cpu_dict
    #     all_stats[hostname]['mem'] = mem_dict
    #     all_stats[hostname]['domains'] = domain_dict
    #     all_stats[hostname]['net'] = net_dict
    #     all_stats[hostname]['block'] = block_dict
    #     all_stats[hostname]['stats_date'] = after
    #
    # return all_stats


def hostname_to_uri(hostname, user="root", port=22):
    if (hostname == "127.0.0.1") or (hostname == "localhost"):
        uri = "qemu:///system"
    else:
        uri = "qemu+ssh://{}@{}:{}/system".format(user, hostname, port)
    return uri


def try_ssh(hostname, port, user, timeout):
    if try_socket(hostname, port, timeout) is True:
        ip = socket.gethostbyname(hostname)
        ssh = paramiko.SSHClient()
        # ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())

        ##INFO TO DEVELOPER TERMINAR DE ENTENDER POR QUE A VECES VA Y A VECES NO
        ssh.load_system_host_keys()
        # ssh.load_host_keys('/home/vimet/.ssh/known_hosts')
        time.sleep(1)
        try:
            # timelimit(3,test_hypervisor_conn,hostname,
            #             username=user,
            #             port= port,
            #             timeout=CONFIG_DICT['TIMEOUTS']['ssh_paramiko_hyp_test_connection'])
            log.debug("@@@@@@@@@@@@@@@@@@@@")
            log.debug("@@@@@@@@@@@@@@@@@@@@")
            log.debug("@@@@@@@@@@@@@@@@@@@@")
            ssh.connect(
                hostname,
                username=user,
                port=port,
                timeout=timeout,
                banner_timeout=timeout,
            )

            log.debug(
                "host {} with ip {} can connect with ssh without password with paramiko".format(
                    hostname, ip
                )
            )
            log.debug("############################################")
            log.debug("############################################")
            log.debug("############################################")
            log.debug("############################################")
            ssh.close()

            return True

        except Exception as e:
            logs.exception_id.debug("0049")
            try:
                ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
                ssh.connect(
                    hostname,
                    username=user,
                    port=port,
                    timeout=timeout,
                    banner_timeout=timeout,
                )

                log.debug(
                    "The authenticity of host '{} ({})' can't be established".format(
                        hostname, ip
                    )
                )
                log.debug(
                    "host {} with ip {} can connect with ssh without password but the key fingerprint must be incorporated in ~/.ssh/known_hosts".format(
                        hostname, ip
                    )
                )
                ssh.close()
                return False

            except:
                log.error(
                    "host {} with ip {} can't connect with ssh without password. Reasons? timeout, ssh authentication with keys is needed, port is correct?".format(
                        hostname, ip
                    )
                )
                log.error("reason: {}".format(e))
                return False

    else:
        log.error(
            "socket error, try if ssh is listen in hostname {} and port {}".format(
                hostname, port
            )
        )
        return False


def execute_commands(hostname, ssh_commands, dict_mode=False, user="root", port=22):
    before = int(time.time())
    dict_mode = True if type(ssh_commands[0]) is dict else False
    if dict_mode == True:
        array_out_err = exec_remote_list_of_cmds_dict(
            hostname, ssh_commands, username=user, port=port
        )
    else:
        array_out_err = exec_remote_list_of_cmds(
            hostname, ssh_commands, username=user, port=port
        )
    after = int(time.time())
    time_elapsed = after - before
    d_log = {
        "time_elapsed": time_elapsed,
        "host": hostname,
        "commands": ssh_commands,
        "results": array_out_err,
    }
    s_to_log = pformat(d_log)
    logs.main.debug(s_to_log)
    return array_out_err


def execute_command_with_progress(
    hostname, ssh_command, id_domain=None, user="root", port=22
):
    before = int(time.time())
    progress = []
    array_out_err = exec_remote_updating_progress(
        ssh_command, hostname, progress, username=user, port=port, id_domain=id_domain
    )
    after = int(time.time())
    time_elapsed = after - before
    d_log = {
        "time_elapsed": time_elapsed,
        "host": hostname,
        "commands": ssh_command,
        "results": array_out_err,
    }
    s_to_log = pformat(d_log)
    logs.main.debug(s_to_log)

    return array_out_err


def size_format(b):
    if b < 1024:
        return "%i" % b + "B"
    elif pow(1024, 1) <= b < pow(1024, 2):
        return "%.1f" % float(b / pow(1024, 1)) + "KB"
    elif pow(1024, 2) <= b < pow(1024, 3):
        return "%.1f" % float(b / pow(1024, 2)) + "MB"
    elif pow(1024, 3) <= b < pow(1024, 4):
        return "%.1f" % float(b / pow(1024, 3)) + "GB"
    elif pow(1024, 4) <= b:
        return "%.1f" % float(b / pow(1024, 4)) + "TB"


def check_all_backing_chains(hostname, path_to_write_json=None):
    tuples_domain_disk = get_disks_all_domains()
    # pprint(tuples_domain_disk)
    cmds1 = list()
    for domain_id, path_domain_disk in tuples_domain_disk:
        path_domain_disk = shlex.quote(path_domain_disk)
        cmds1.append({"title": domain_id, "cmd": backing_chain_cmd(path_domain_disk)})
        cmds1.append(
            {"title": domain_id, "cmd": 'stat -c %Y "{}"'.format(path_domain_disk)}
        )

    # pprint(cmds1)
    array_out_err = execute_commands(hostname, cmds1, dict_mode=True)
    return array_out_err

    # pprint(array_out_err)
    if path_to_write_json != None:
        dict_stats = analize_backing_chains_outputs(
            array_out_err=array_out_err, path_to_write_json=path_to_write_json
        )
        return dict_stats
    else:
        return array_out_err


def cmd_check_os(path_disk):
    return 'virt-inspector -a "{}"'.format(path_disk)


def check_all_os(hostname, path_to_write_json=None):
    tuples_domain_disk = get_disks_all_domains()
    cmds1 = list()
    for domain_id, path_domain_disk in tuples_domain_disk:
        path_domain_disk = shlex.quote(path_domain_disk)
        cmds1.append({"title": domain_id, "cmd": cmd_check_os(path_domain_disk)})

    # pprint(cmds1)
    array_out_err = execute_commands(hostname, cmds1, dict_mode=True)
    # from pprint import pprint
    # pprint(array_out_err)
    if path_to_write_json != None:
        f = open(path_to_write_json, "w")
        json.dump(array_out_err, f)
        f.close()

    return array_out_err


def analize_check_os_output(array_out_err):
    for d in array_out_err:
        domains_ok = 0
        domains_err = 0
        for d in array_out_err:
            id = d["title"]
            if len(d["err"]) > 0:
                domains_err += 1
                log.info(d["err"])
                update_domain_os("Unknown", id, detail=d["err"])
            else:
                d = xmltodict.parse(d["out"])
                print(
                    "DOMAIN ID: {}, SO product_name: {}".format(
                        id, d["operatingsystems"]["operatingsystem"]["product_name"]
                    )
                )


def analize_backing_chains_outputs(
    array_out_err=[], path_to_write_json=None, path_to_read_json=None
):
    if path_to_write_json != None:
        f = open(path_to_write_json, "w")
        json.dump(array_out_err, f)
        f.close()

    if path_to_read_json != None:
        f = open(path_to_read_json, "r")
        array_out_err = json.load(f)
        log.debug(len(array_out_err))
        f.close()

    domains_ok = 0
    domains_err = 0
    for d in array_out_err:
        id = d["title"]
        if len(d["err"]) > 0:
            domains_err += 1
            log.info(d["err"])
            update_domain_status("Failed", id, detail=d["err"])
        else:
            log.debug(id)
            domains_ok += 1
            if type(d["out"]) is not str:
                out = out.decode("utf-8")
            else:
                out = d["out"]
            l = json.loads(out)

            # from pprint import pprint
            # pprint(l)
            update_disk_backing_chain(id, 0, l[0]["filename"], l)

    return {"ok": domains_ok, "err": domains_err}


def engine_restart():
    exit()


def domain_status_from_started_to_unknown():
    unknown_started_domains()


def clean_started_without_hyp():
    fail_started_domains_without_hypervisors()


def update_status_db_from_running_domains(hyp_obj):
    hyp_obj.get_domains()


def clean_intermediate_status(reason="engine is restarting", only_domain_id=None):
    # Here only to remember the status that apply to each action
    # status_to_delete = [
    #     "Creating",
    #     "CreatingAndStarting",
    #     "CreatingDiskFromScratch",
    #     "CreatingFromBuilder",
    # ]
    # status_to_failed = [
    #     "Updating",
    #     "Deleting",
    #     "DiskDeleted",
    #     "CreatingDomain",
    #     "DeletingDomainDisk",
    #     "StartingDomainDisposable",
    # ]
    # status_to_stopped = ["Starting"]
    # status_to_started = ["Stopping", "Shutting-down"]

    delete_incomplete_creating_domains(only_domain_id=only_domain_id)

    fail_incomplete_creating_domains(
        only_domain_id=only_domain_id,
        detail=f"Domain status set to Failed because {reason}",
    )

    stop_incomplete_starting_domains(
        only_domain_id=only_domain_id,
        detail=f"Domain status set to Stopped because {reason}",
    )

    start_incomplete_starting_domains(
        only_domain_id=only_domain_id,
        detail=f"Domain status set to Started because {reason}",
    )


def flatten_dict(d):
    def items():
        for key, value in list(d.items()):
            if isinstance(value, dict):
                for subkey, subvalue in list(flatten_dict(value).items()):
                    yield key + "." + subkey, subvalue
            else:
                yield key, value

    return dict(items())


def pop_key_if_zero(d):
    pop_elements = []
    for k, v in d.items():
        if type(v) is dict:
            pop_key_if_zero(v)
            if len(v) == 0:
                pop_elements.append(k)
        else:
            try:
                if int(v) == 0:
                    pop_elements.append(k)
            except:
                pass
    for k in pop_elements:
        d.pop(k)
    return d


class QueuesThreads:
    def __init__(self):
        self.background = PriorityQueueIsard()
        self.workers = {}
        self.quit = False
        self.action = ""


class PriorityQueueIsard(queue.PriorityQueue):
    def __init__(self, maxsize=0):
        self.counter = 0
        super().__init__(maxsize=maxsize)

    def put(self, item, priority=100, block=True, timeout=None):
        self.counter += 1
        super().put((priority, self.counter, item), block=block, timeout=timeout)

    def get(self, block=True, timeout=None):
        get_super = super().get(block=block, timeout=timeout)
        return get_super[-1]
