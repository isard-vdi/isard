# Copyright 2017 the Isard-vdi project authors:
#      Alberto Larraz Dalmases
#      Josep Maria Viñolas Auquer
# License: AGPLv3

import shlex
from random import choices
from uuid import uuid4

from isardvdi_common.helpers.default_storage_pool import DEFAULT_STORAGE_POOL_ID

from engine.services.db.storage_pool import get_category_storage_pool
from engine.services.log import *

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
