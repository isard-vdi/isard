# Copyright 2017 the Isard-vdi project authors:
#      Alberto Larraz Dalmases
#      Josep Maria Viñolas Auquer
# License: AGPLv3

import json
import shlex
import string
from os.path import dirname as extract_dir_path
from pprint import pprint
from random import choices
from uuid import uuid4

from engine.services.db import get_hyp_hostname_user_port_from_id
from engine.services.db.db import get_pool, get_pools_from_hyp
from engine.services.db.storage_pool import get_category_storage_pool
from engine.services.lib.functions import (
    backing_chain_cmd,
    exec_remote_cmd,
    execute_commands,
    size_format,
)
from engine.services.log import *
from isardvdi_common.helpers.default_storage_pool import DEFAULT_STORAGE_POOL_ID

VDESKTOP_DISK_OPERATINOS = CONFIG_DICT["REMOTEOPERATIONS"][
    "host_remote_disk_operatinos"
]

QCOW2_CLUSTER_SIZE = os.environ.get("QCOW2_CLUSTER_SIZE", "4k")
QCOW2_EXTENDED_L2 = os.environ.get("QCOW2_EXTENDED_L2", "off")
QCOW2_LAZY_REFCOUNTS = os.environ.get("QCOW2_LAZY_REFCOUNTS", "off")
QCOW2_PREALLOCATION = os.environ.get("QCOW2_PREALLOCATION", "off")

if QCOW2_EXTENDED_L2 == "on":
    _size_str = QCOW2_CLUSTER_SIZE.upper().strip()
    _multipliers = {"K": 1024, "M": 1024**2}
    _num = int("".join(c for c in _size_str if c.isdigit()))
    _unit = "".join(c for c in _size_str if c.isalpha())
    _cluster_bytes = _num * _multipliers.get(_unit, 1)
    if _cluster_bytes < 16384:
        raise ValueError(
            f"QCOW2_CLUSTER_SIZE={QCOW2_CLUSTER_SIZE} is too small for extended_l2=on "
            f"(minimum 16k). Either set QCOW2_CLUSTER_SIZE>=16k or QCOW2_EXTENDED_L2=off"
        )


def create_cmds_delete_disk(path_disk, mv_to_extension_deleted=False):
    cmds = list()
    path_disk = shlex.quote(path_disk)
    cmd = "ls -l {}".format(path_disk)
    cmds.append(cmd)

    if mv_to_extension_deleted is True:
        cmd = (
            f'if [ -f "{path_disk}" ] ; then mv "{path_disk}" "{path_disk}.deleted; fi'
        )
    else:
        cmd = 'if [ -f "{}" ] ; then rm -f "{}"; fi'.format(path_disk, path_disk)
    log.debug("delete disk or media cmd: {}".format(cmd))
    cmds.append(cmd)

    cmd = 'ls -l "{}"'.format(path_disk)
    cmds.append(cmd)

    return cmds


def extract_list_backing_chain(out_cmd_qemu_img, json_format=True):
    out = out_cmd_qemu_img

    if json_format is True:
        if type(out) is not str:
            out = out.decode("utf-8")
        try:
            out = json.loads(out)
        except Exception as e:
            logs.exception_id.debug("0052")
            log.info("error reading backing chain, disk is created??")
            log.info(e)
            return []
        return out
    else:
        return backing_chain_parse_list(out)


def backing_chain_parse_list(out_cmd):
    l = [t.split("\n")[0] for t in out_cmd.split("image: ")[1:]]
    return l


def backing_chain(path_disk, disk_operations_hostname, json_format=True):
    """
    return list of backing chain: list[0] is the most newer,
    and list[-1] the last qcow in backing chain
    """
    path_disk = shlex.quote(path_disk)
    cmd = backing_chain_cmd(path_disk)

    d = exec_remote_cmd(cmd, disk_operations_hostname)
    if len(d["err"]) == 0:
        output = extract_list_backing_chain(d["out"], json_format=json_format)
        if len(output) == 0:
            log.info(
                "backing_chain info for disk {} fail when executing in host {} and command is {}".format(
                    path_disk, VDESKTOP_DISK_OPERATINOS, cmd
                )
            )
        return output
    else:
        log.error(
            "backing_chain info for disk {} fail when executing in host {} and command is {}".format(
                path_disk, VDESKTOP_DISK_OPERATINOS, cmd
            )
        )


def get_path_to_disk(
    relative_path=None,
    category_id=None,
    type_path="desktop",
    extension=None,
):
    if not relative_path:
        relative_path = str(uuid4())
    if extension:
        relative_path += f".{extension}"
    pool_paths = get_category_storage_pool(category_id)["paths"]
    paths_for_type = pool_paths[type_path]
    path_selected = choices(
        [path["path"] for path in paths_for_type],
        weights=[path["weight"] for path in paths_for_type],
    )[0]
    path_absolute = path_selected + "/" + relative_path
    return path_absolute, path_selected


def get_host_disk_operations_from_path(
    manager, pool=DEFAULT_STORAGE_POOL_ID, type_path="desktop"
):
    # We should get a random type_path if it has more than one path?
    # d_pool = get_storage_pool(pool)
    # We are not returing the path, so why we need to get it here

    if pool not in manager.diskoperations_pools.keys():
        logs.main.error(
            f"Pool {pool} is not in diskoperations_pools, can not get host for disk_operations"
        )
        return None
    disk_operations = manager.diskoperations_pools[
        pool
    ].balancer.get_next_diskoperations()

    # We should check if it's thread is running
    # This should go into balancer?
    # d_threads_h = {"disk_op_" + h: h for h in hyps if h in disk_operations}
    # disk_operations = sorted(
    #     [d_threads_h[k] for k in set(l_threads).intersection(set(d_threads_h.keys()))]
    # )
    return disk_operations


def test_hypers_disk_operations(hyps_disk_operations):
    list_hyps_ok = list()
    str_random = "".join(choices(string.ascii_uppercase + string.digits, k=8))
    for hyp_id in hyps_disk_operations:
        d_hyp = get_hyp_hostname_user_port_from_id(hyp_id)
        cmds1 = list()
        for pool_id in get_pools_from_hyp(hyp_id):
            # test write permissions in root dir of all paths defined in pool
            paths = {
                k: [l["path"] for l in d] for k, d in get_pool(pool_id)["paths"].items()
            }
            for k, p in paths.items():
                for path in p:
                    path = shlex.quote(path)
                    cmds1.append(
                        {
                            "title": f"try create dir if not exists - pool:{pool_id}, hypervisor: {hyp_id}, path_kind: {k}",
                            "cmd": f"mkdir -p {path}",
                        }
                    )
                    cmds1.append(
                        {
                            "title": f"touch random file - pool:{pool_id}, hypervisor: {hyp_id}, path_kind: {k}",
                            "cmd": f"touch {path}/test_random_{str_random}",
                        }
                    )
                    cmds1.append(
                        {
                            "title": "delete random file - pool:{pool_id}, hypervisor: {hyp_id}, path_kind: {k}",
                            "cmd": f"rm -f {path}/test_random_{str_random}",
                        }
                    )
        try:
            array_out_err = execute_commands(
                d_hyp["hostname"],
                ssh_commands=cmds1,
                dict_mode=True,
                user=d_hyp["user"],
                port=d_hyp["port"],
            )
            # if error in some path hypervisor is not valid
            if len([d["err"] for d in array_out_err if len(d["err"]) > 0]) > 0:
                logs.main.error(
                    f"Hypervisor {hyp_id} can not be disk_operations, some errors when testing if can create files in all paths_"
                )
                for d_cmd_err in [d for d in array_out_err if len(d["err"]) > 0]:
                    cmd = d_cmd_err["cmd"]
                    err = d_cmd_err["err"]
                    logs.main.error(f"Command: {cmd} --  Error: {err}")
            else:
                list_hyps_ok.append(hyp_id)

        except Exception as e:
            logs.exception_id.debug("0053")
            if __name__ == "__main__":
                logs.main.err(
                    f"Error when launch commands to test hypervisor {hyp_id} disk_operations: {e}"
                )

    return list_hyps_ok
