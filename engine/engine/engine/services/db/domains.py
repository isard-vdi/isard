import json
import random
import sys
import time
import traceback
from copy import deepcopy
from pathlib import PurePath
from typing import TypedDict

from cachetools import TTLCache
from engine.config import TRANSITIONAL_STATUS
from engine.services.db import (
    close_rethink_connection,
    create_list_buffer_history_domain,
    new_rethink_connection,
    rethink_conn,
)
from engine.services.db.db import close_rethink_connection, new_rethink_connection
from engine.services.lib.storage import (
    update_domain_createdict_qemu_img_info,
    update_storage_deleted_domain,
)
from engine.services.log import logs
from rethinkdb import r
from rethinkdb.errors import ReqlNonExistenceError

STATUS_STABLE_DOMAIN_RUNNING = ["Started", "ShuttingDown", "Paused"]
ALL_STATUS_RUNNING = ["Stopping", "Started", "Stopping", "Shutting-down"]
STATUS_TO_UNKNOWN = ["Started", "Paused", "Shutting-down", "Stopping", "Unknown"]
STATUS_TO_STOPPED = ["Starting", "CreatingTemplate"]
STATUS_FROM_CAN_START = ["Stopped", "Failed"]
STATUS_TO_FAILED = ["Started", "Stopping", "Shutting-down"]

DEBUG_CHANGES = True if logs.changes.handlers[0].level <= 10 else False
if DEBUG_CHANGES:
    import inspect
    import threading


def delete_domain(id):
    r_conn = new_rethink_connection()
    rtable = r.table("domains")
    results = rtable.get(id).delete().run(r_conn)
    close_rethink_connection(r_conn)
    return results


def delete_incomplete_creating_domains(only_domain_id=None, kind="desktop"):
    status_to_delete = [
        "Creating",
        "CreatingAndStarting",
        "CreatingDiskFromScratch",
    ]
    r_conn = new_rethink_connection()
    rtable = r.table("domains")
    if only_domain_id:
        results = (
            rtable.get_all(only_domain_id, index="id")
            .filter(lambda d: r.expr(status_to_delete).contains(d["status"]))
            .delete()
            .run(r_conn)
        )
    else:
        results = (
            rtable.get_all(r.args(status_to_delete), index="status")
            .filter({"kind": kind})
            .delete()
            .run(r_conn)
        )
    close_rethink_connection(r_conn)
    return results


def fail_incomplete_creating_domains(
    only_domain_id=None, detail="Failed by engine as it was incomplete", kind="desktop"
):
    status_to_failed = [
        "Updating",
        "Deleting",
        "DiskDeleted",
        "CreatingDomain",
        "DeletingDomainDisk",
        "StartingDomainDisposable",
    ]
    r_conn = new_rethink_connection()
    rtable = r.table("domains")
    if only_domain_id:
        results = (
            rtable.get_all(only_domain_id, index="id")
            .filter(lambda d: r.expr(status_to_failed).contains(d["status"]))
            .update({"status": "Failed", "detail": detail})
            .run(r_conn)
        )
    results = (
        rtable.get_all(r.args(status_to_failed), index="status")
        .filter({"kind": kind})
        .update({"status": "Failed", "detail": detail})
        .run(r_conn)
    )
    close_rethink_connection(r_conn)
    return results


def stop_incomplete_starting_domains(
    only_domain_id=None, detail="Stopped by engine as it was incomplete", kind="desktop"
):
    status_to_stopped = ["Starting"]
    r_conn = new_rethink_connection()
    rtable = r.table("domains")
    if only_domain_id:
        results = (
            rtable.get_all(only_domain_id, index="id")
            .filter(lambda d: r.expr(status_to_stopped).contains(d["status"]))
            .update({"status": "Stopped", "detail": detail})
            .run(r_conn)
        )
    else:
        results = (
            rtable.get_all("Starting", index="status")
            .filter({"kind": kind})
            .update({"status": "Stopped", "detail": detail})
            .run(r_conn)
        )
    close_rethink_connection(r_conn)
    return results


def start_incomplete_starting_domains(
    only_domain_id, detail="Started by engine as it was incomplete", kind="desktop"
):
    status_to_started = ["Stopping", "Shutting-down"]
    r_conn = new_rethink_connection()
    rtable = r.table("domains")
    if only_domain_id:
        results = (
            rtable.get_all(only_domain_id, index="id")
            .filter(lambda d: r.expr(status_to_started).contains(d["status"]))
            .update({"status": "Started", "detail": detail})
            .run(r_conn)
        )
    else:
        results = (
            rtable.get_all(r.args(status_to_started), index="status")
            .filter({"kind": kind})
            .update({"status": "Started", "detail": detail})
            .run(r_conn)
        )
    close_rethink_connection(r_conn)
    return results


def fail_started_domains_without_hypervisors(
    detail=f"Set to Failed because did'nt have hyp_started but said started. Reason: engine restart.",
    kind="desktop",
):
    r_conn = new_rethink_connection()
    rtable = r.table("domains")
    results = (
        rtable.get_all(r.args(STATUS_TO_FAILED), index="status")
        .filter({"kind": kind, "hyp_started": False})
        .update({"status": "Failed", "detail": detail})
        .run(r_conn)
    )
    close_rethink_connection(r_conn)
    return results


def unknown_started_domains(
    detail="Set to Unknown. Reason: engine restart.", kind="desktop"
):
    r_conn = new_rethink_connection()
    rtable = r.table("domains")
    results = (
        rtable.get_all([kind, "Started"], index="kind_status")
        .update({"status": "Unknown", "detail": detail})
        .run(r_conn)
    )
    close_rethink_connection(r_conn)
    return results


def update_domain_progress(id_domain, percent):
    r_conn = new_rethink_connection()
    rtable = r.table("domains")
    results = (
        rtable.get(id_domain)
        .update({"progress": {"percent": percent, "when": int(time.time())}})
        .run(r_conn)
    )
    close_rethink_connection(r_conn)
    return results


def update_domain_force_update(id_domain, true_or_false=False):
    r_conn = new_rethink_connection()
    rtable = r.table("domains")

    results = (
        rtable.get_all(id_domain, index="id")
        .update({"force_update": true_or_false})
        .run(r_conn)
    )

    close_rethink_connection(r_conn)
    return results


def update_domain_forced_hyp(id_domain, hyp_id=None):
    r_conn = new_rethink_connection()
    rtable = r.table("domains")

    if hyp_id:
        forced_hyp = [hyp_id]
    else:
        forced_hyp = False

    results = (
        rtable.get_all(id_domain, index="id")
        .update({"forced_hyp": forced_hyp})
        .run(r_conn)
    )

    close_rethink_connection(r_conn)
    return results


def update_domain_parents(id_domain):
    with rethink_conn() as conn:
        d = (
            r.table("domains")
            .get(id_domain)
            .pluck({"create_dict": "origin"}, "parents")
            .run(conn)
        )

    if "parents" not in d.keys():
        parents_with_new_origin = []
    elif type(d["parents"]) is not list:
        parents_with_new_origin = []
    else:
        parents_with_new_origin = d["parents"].copy()

    if "origin" in d["create_dict"].keys():
        parents_with_new_origin.append(d["create_dict"]["origin"])
        with rethink_conn() as conn:
            results = (
                r.table("domains")
                .get(id_domain)
                .update({"parents": parents_with_new_origin})
                .run(conn)
            )

    return results


def update_domains_in_deleted_hyper(hyp_id):
    r_conn = new_rethink_connection()
    try:
        r.table("domains").get_all(hyp_id, index="hyp_started").update(
            {
                "status": "Stopped",
                "hyp_started": False,
                "detail": json.dumps(
                    "Set to Stopped by engine as the hypervisor was deleted"
                ),
                "create_dict": {"personal_vlans": False},
            },
        ).run(r_conn)
    except:
        logs.main.error("Unable to set stopped status to domains in deleted hypervisor")
        logs.main.debug("Traceback: \n .{}".format(traceback.format_exc()))
    close_rethink_connection(r_conn)


def update_domain_status(
    status,
    id_domain,
    hyp_id=None,
    detail="",
    keep_hyp_id=False,
    storage_id=None,
):
    if DEBUG_CHANGES:
        thread_name = threading.currentThread().name
        parents = []
        for i in inspect.stack():
            if len(i) > 3:
                p = i[3]
                if p not in [
                    "<module>",
                    "eval_in_context",
                    "evaluate_expression",
                    "do_it",
                    "process_internal_commands",
                    "_do_wait_suspend",
                    "do_wait_suspend",
                    "do_wait_suspend",
                    "trace_dispatch",
                ]:
                    parents.append(p)
        s_parents = " <- ".join(parents)
        logs.changes.debug(
            f"*** update domain {id_domain} to {status}:\n *** {thread_name} - {s_parents}"
        )

    logs.main.debug(
        f"Update domain status -> status: {status} / domain:{id_domain} / hyp_id={hyp_id} / keep_hyp_id?{keep_hyp_id}"
    )
    # INFO TO DEVELOPER TODO: verificar que el estado que te ponen es realmente un estado válido
    # INFO TO DEVELOPER TODO: si es stopped puede interesar forzar resetear hyp_started no??
    # INFO TO DEVELOPER TODO: MOLARÍA GUARDAR UN HISTÓRICO DE LOS ESTADOS COMO EN HYPERVISORES

    # INFO TO DEVELOPER: OJO CON hyp_started a None... peligro si alguien lo chafa, por eso estos if/else

    try:
        if status == "Stopped":
            with rethink_conn() as conn:
                last_hyp_id = (
                    r.table("domains")
                    .get(id_domain)
                    .pluck("hyp_started")
                    .run(conn)["hyp_started"]
                )
            if type(last_hyp_id) is str and len(last_hyp_id) > 0:
                with rethink_conn() as conn:
                    results = (
                        r.table("domains")
                        .get_all(id_domain, index="id")
                        .update({"last_hyp_id": last_hyp_id})
                        .run(conn)
                    )

        if keep_hyp_id == True:
            with rethink_conn() as conn:
                hyp_id = (
                    r.table("domains")
                    .get(id_domain)
                    .pluck("hyp_started")
                    .run(conn)["hyp_started"]
                )

        if hyp_id is None:
            with rethink_conn() as conn:
                results = (
                    r.table("domains")
                    .get(id_domain)
                    .update(
                        {
                            "status": status,
                            "hyp_started": False,
                            "detail": json.dumps(detail),
                        },
                        return_changes=True,
                    )
                    .run(conn)
                )
        else:
            d_update = {
                "hyp_started": hyp_id,
                "status": status,
                "detail": json.dumps(detail),
            }

            with rethink_conn() as conn:
                results = (
                    r.table("domains")
                    .get(id_domain)
                    .update(d_update, return_changes=True)
                    .run(conn)
                )

        if status == "DiskDeleted":
            try:
                update_storage_deleted_domain(
                    storage_id, results.get("changes", [{}])[0].get("new_val")
                )
            except Exception as e:
                logs.main.error("Exception in update_storage_deleted_domain")
                logs.main.error("Traceback: \n .{}".format(traceback.format_exc()))
                logs.main.error("Exception message: {}".format(e))
        if status == "Stopped":
            remove_fieds_when_stopped(id_domain)

        if status == "Failed":
            remove_fieds_when_stopped(id_domain)

        # if results_zero(results):
        #
        #     logs.main.debug('id_domain {} in hyperviros {} does not exist in domain table'.format(id_domain,hyp_id))

        return results

    except r.ReqlNonExistenceError:
        logs.main.error(
            "domain_id {} does not exist in domains table".format(id_domain)
        )
        logs.main.debug("function: {}".format(sys._getframe().f_code.co_name))
        return False


def update_last_hyp_id(id_domain, last_hyp_id):
    r_conn = new_rethink_connection()
    rtable = r.table("domains")
    try:
        results = (
            rtable.get_all(id_domain, index="id")
            .update({"last_hyp_id": last_hyp_id})
            .run(r_conn)
        )
        close_rethink_connection(r_conn)
        return results
    except Exception as e:
        logs.main.debug(
            f"error updating last_hyp_id in database with id_domain {id_domain} and last_hyp_id: {last_hyp_id}"
        )
    close_rethink_connection(r_conn)


def update_domain_hyp_started(domain_id, hyp_id, detail="", status="Started"):
    results = update_domain_status(status, domain_id, hyp_id, detail=detail)
    return results


def update_domain_hyp_stopped(id_domain, status="Stopped"):
    hyp_id = get_domain_hyp_started(id_domain)
    results = update_domain_status(status, id_domain, hyp_id)
    return results


def update_all_domains_status(reset_status="Stopped", from_status=ALL_STATUS_RUNNING):
    r_conn = new_rethink_connection()
    if from_status is None:
        results = r.table("domains").update({"status": reset_status}).run(r_conn)

    for initial_status in from_status:
        results = (
            r.table("domains")
            .get_all(initial_status, index="status")
            .update({"status": reset_status})
            .run(r_conn)
        )
    close_rethink_connection(r_conn)
    return results


def get_domain_hyp_started(id_domain):
    r_conn = new_rethink_connection()
    rtable = r.table("domains")
    results = rtable.get(id_domain).pluck("hyp_started").run(r_conn)
    close_rethink_connection(r_conn)
    if not results:
        return False
    return results.get("hyp_started")


def get_custom_dict_from_domain(id_domain):
    r_conn = new_rethink_connection()
    rtable = r.table("domains")
    results = rtable.get(id_domain).pluck("custom").run(r_conn)
    close_rethink_connection(r_conn)
    if results is None:
        return False
    if "custom" not in results.keys():
        return False
    if len(results["custom"]) == 0:
        return False

    return results["custom"]


def update_custom_all_dict(id_domain, d_custom):
    r_conn = new_rethink_connection()
    rtable = r.table("domains")
    results = rtable.get(id_domain).update({"custom": d_custom}).run(r_conn)
    close_rethink_connection(r_conn)
    return results


def get_domain_hyp_started_and_status_and_detail(id_domain):
    r_conn = new_rethink_connection()
    rtable = r.table("domains")
    try:
        results = (
            rtable.get(id_domain).pluck("hyp_started", "detail", "status").run(r_conn)
        )
    except:
        # if results is None:
        close_rethink_connection(r_conn)
        return {}
    close_rethink_connection(r_conn)
    return results


def get_domains_with_status(status):
    """
    get domain with status
    :param status
    :return: list id_domains
    """
    r_conn = new_rethink_connection()
    rtable = r.table("domains")
    try:
        results = rtable.get_all(status, index="status").pluck("id")["id"].run(r_conn)
        close_rethink_connection(r_conn)
    except:
        # if results is None:
        close_rethink_connection(r_conn)
        return []
    return results


def get_domains_with_transitional_status(
    list_status=TRANSITIONAL_STATUS, also_started=False
):
    if also_started:
        list_status = list(list_status)
        list_status.append("Started")
        list_status.append("Paused")
    r_conn = new_rethink_connection()
    rtable = r.table("domains")
    # ~ l = list(rtable.filter(lambda d: r.expr(list_status).
    # ~ contains(d['status'])).pluck('status', 'id', 'hyp_started').
    # ~ run
    l = list(
        rtable.get_all(r.args(list_status), index="status")
        .pluck("status", "id", "hyp_started", "accessed")
        .run(r_conn)
    )
    close_rethink_connection(r_conn)
    return l


def get_domains_with_status_in_list(list_status=["Started"]):
    r_conn = new_rethink_connection()
    rtable = r.table("domains")
    # ~ l = list(rtable.filter(lambda d: r.expr(list_status).
    # ~ contains(d['status'])).pluck('status', 'id', 'hyp_started').
    # ~ run
    l = list(
        rtable.get_all(r.args(list_status), index="status")
        .pluck("status", "id", "hyp_started")
        .run(r_conn)
    )
    close_rethink_connection(r_conn)
    return l


def update_domain_dict_create_dict(id, create_dict):
    r_conn = new_rethink_connection()
    rtable = r.table("domains")
    results = rtable.get(id).update({"create_dict": create_dict}).run(r_conn)
    close_rethink_connection(r_conn)
    return results


def update_domain_dict_hardware(domain_id, domain_dict, xml=False):
    r_conn = new_rethink_connection()
    rtable = r.table("domains")
    domain_dict["name"] = domain_id
    if xml is False:
        results = rtable.get(domain_id).update({"hardware": domain_dict}).run(r_conn)

    else:
        results = (
            rtable.get(domain_id)
            .update({"hardware": domain_dict, "xml": xml})
            .run(r_conn)
        )

    # if results_zero(results):
    #     logs.main.debug('id_domain {} does not exist in domain table'.format(id))

    close_rethink_connection(r_conn)
    return results


def remove_domain_viewer_values(domain_id):
    with rethink_conn() as conn:
        try:
            # Single atomic operation with condition check and update
            result = (
                r.table("domains")
                .get(domain_id)
                .replace(
                    lambda domain: r.branch(
                        domain["status"].eq("Stopped"),
                        domain.without("viewer"),
                        domain,
                    )
                )
                .run(conn)
            )
        except ReqlNonExistenceError:
            logs.main.error(
                f"Domain {domain_id} does not exist in domains table, cannot remove viewer values"
            )
            return False
        except Exception as e:
            logs.main.error(
                f"Error removing viewer values for domain {domain_id}: {str(e)}"
            )
            return False

    # Check if operation actually modified the document
    if result.get("replaced", 0) == 0 and result.get("unchanged", 0) > 0:
        logs.main.debug(
            f"Domain {domain_id} is not stopped, cannot remove viewer values"
        )
        return False
    logs.main.info(f"Viewer values removed for domain {domain_id}")
    return True


def update_disk_backing_chain(
    id_domain,
    index_disk,
    path_disk,
    list_backing_chain,
    new_template=False,
    list_backing_chain_template=[],
):
    with rethink_conn() as conn:
        domain = r.table("domains").get(id_domain).run(conn)
    # Domain could be deleted by api and webapp
    # https://gitlab.com/isard/isardvdi/-/blob/main/api/src/api/libv2/ds.py#L60
    # https://gitlab.com/isard/isardvdi/-/blob/main/webapp/webapp/webapp/lib/ds.py#L53
    if domain:
        if new_template == True:
            domain["create_dict"]["template_dict"][
                "disks_info"
            ] = list_backing_chain_template
            update_domain_createdict_qemu_img_info(
                domain.get("create_dict", {})
                .get("template_dict", {})
                .get("create_dict", {}),
                index_disk,
                list_backing_chain_template,
            )
        domain["disks_info"] = list_backing_chain
        update_domain_createdict_qemu_img_info(
            domain.get("create_dict", {}), index_disk, list_backing_chain
        )
        with rethink_conn() as conn:
            results = r.table("domains").replace(domain).run(conn)
    else:
        logs.main.error(
            f"trying to update disk backing chain of non-existent domain {id_domain}"
        )
        results = None

    return results


def update_disk_template_created(id_domain, index_disk):
    with rethink_conn() as conn:
        dict_disk_templates = (
            r.table("domains").get(id_domain).pluck("disk_template_created").run(conn)
        )
    dict_disk_templates["disk_template_created"][index_disk] = 1
    with rethink_conn() as conn:
        results = (
            r.table("domains").get(id_domain).update(dict_disk_templates).run(conn)
        )
    return results


def remove_disk_template_created_list_in_domain(id_domain):
    r_conn = new_rethink_connection()
    rtable = r.table("domains")
    results = (
        rtable.get(id_domain)
        .replace(r.row.without("disk_template_created"))
        .run(r_conn)
    )
    close_rethink_connection(r_conn)
    return results


def update_origin_and_parents_to_new_template(id_domain, template_id):
    r_conn = new_rethink_connection()
    rtable = r.table("domains")
    new_create_dict_origin = {"create_dict": {"origin": template_id}}
    results = rtable.get(id_domain).update(new_create_dict_origin).run(r_conn)
    close_rethink_connection(r_conn)
    return results


def remove_dict_new_template_from_domain(id_domain):
    r_conn = new_rethink_connection()
    rtable = r.table("domains")
    results = (
        rtable.get(id_domain)
        .replace(r.row.without({"create_dict": "template_dict"}))
        .run(r_conn)
    )
    close_rethink_connection(r_conn)
    return results


def get_if_all_disk_template_created(id_domain):
    r_conn = new_rethink_connection()
    rtable = r.table("domains")
    dict_disk_templates = (
        rtable.get(id_domain).pluck("disk_template_created").run(r_conn)
    )
    close_rethink_connection(r_conn)
    created = len(dict_disk_templates["disk_template_created"]) == sum(
        dict_disk_templates["disk_template_created"]
    )
    return created


def create_disk_template_created_list_in_domain(id_domain):
    dict_domain = get_domain(id_domain)
    created_disk_finalished_list = [
        0 for a in range(len(dict_domain["hardware"]["disks"]))
    ]

    r_conn = new_rethink_connection()
    rtable = r.table("domains")
    results = (
        rtable.get(id_domain)
        .update({"disk_template_created": created_disk_finalished_list})
        .run(r_conn)
    )
    close_rethink_connection(r_conn)
    return results


def get_domain_forced_hyp(id_domain):
    r_conn = new_rethink_connection()
    rtable = r.table("domains")

    try:
        d = rtable.get(id_domain).pluck("forced_hyp", "favourite_hyp").run(r_conn)
    except:
        close_rethink_connection(r_conn)
        return False, False
    close_rethink_connection(r_conn)
    forced_hyp = d.get("forced_hyp", False)
    favourite_hyp = d.get("favourite_hyp", False)
    ## By now, even the webapp will update it as a list, only lets
    ## to set one forced_hyp
    if forced_hyp:
        forced_hyp = forced_hyp[0]
    else:
        forced_hyp = False
    if isinstance(favourite_hyp, list) and len(favourite_hyp) > 0:
        ## By now, even the webapp will update it as a list, only lets
        ## to set one forced_hyp
        if favourite_hyp[0] == "false":
            favourite_hyp = False
    elif favourite_hyp == "false":
        favourite_hyp = False
    return forced_hyp, favourite_hyp


def get_domain(id):
    r_conn = new_rethink_connection()
    rtable = r.table("domains")
    try:
        dict_domain = rtable.get(id).without("tag_visible").run(r_conn)
    except ReqlNonExistenceError:
        close_rethink_connection(r_conn)
        return None
    close_rethink_connection(r_conn)
    return dict_domain


def get_domain_status(id):
    try:
        with rethink_conn() as conn:
            domain_status = r.table("domains").get(id).pluck("status").run(conn)
    except ReqlNonExistenceError:
        return None

    return domain_status["status"]


def get_storage_ids_and_paths_from_domain(domain_id):
    try:
        with rethink_conn() as conn:
            d_storages_ids = (
                r.table("domains")
                .get(domain_id)
                .pluck({"create_dict": {"hardware": [{"disks": "storage_id"}]}})
                .run(conn)
            )
        l_storage_ids = [
            a["storage_id"]
            for a in d_storages_ids.get("create_dict", {})
            .get("hardware", {})
            .get("disks", {})
            if "storage_id" in a.keys()
        ]

        d_out = {}
        for storage_id in l_storage_ids:
            try:
                with rethink_conn() as conn:
                    storage = (
                        r.table("storage")
                        .get(storage_id)
                        .pluck("directory_path", "type", "readonly")
                        .run(conn)
                    )
                if storage.get("readonly", False) is True:
                    continue
                path = str(
                    PurePath(storage.get("directory_path"))
                    .joinpath(storage_id)
                    .with_suffix(f".{storage.get('type')}")
                )
                d_out[storage_id] = path
            except r.ReqlNonExistenceError:
                continue
        return d_out
    except r.ReqlNonExistenceError:
        return {}


def get_disks_all_domains():
    r_conn = new_rethink_connection()
    rtable = r.table("domains")

    domains_info_disks = list(
        rtable.pluck("id", {"hardware": [{"disks": ["file"]}]}).run(r_conn)
    )
    close_rethink_connection(r_conn)
    tuples_id_disk = [
        (d["id"], d["hardware"]["disks"][0]["file"])
        for d in domains_info_disks
        if "hardware" in d.keys()
    ]
    return tuples_id_disk


## VGPUS


def get_vgpu_uuid_status(uuid, gpu_id=None, profile=None):
    r_conn = new_rethink_connection()
    rtable = r.table("vgpus")
    try:
        if profile is not None and gpu_id is not None:
            d_uuid = (
                rtable.get(gpu_id)
                .pluck({"mdevs": {profile: [uuid]}})
                .run(r_conn)["mdevs"][profile][uuid]
            )
            d_uuid["profile"] = profile
            d_uuid["gpu_id"] = gpu_id
            close_rethink_connection(r_conn)
            return d_uuid

        else:
            if gpu_id is None:
                l_mdevs = list(rtable.pluck("id", "mdevs").run(r_conn))
            else:
                l_mdevs = [rtable.get(gpu_id).pluck("id", "mdevs").run(r_conn)]

            for d_vgpu in l_mdevs:
                d_mdevs = d_vgpu["mdevs"]
                gpu_id = d_vgpu["id"]
                d_uuids = {}
                for profile, e in d_mdevs.items():
                    for u, d_uuid in e.items():
                        d_uuids[u] = d_uuid.copy()
                        d_uuids[u]["profile"] = profile
                        d_uuids[u]["gpu_id"] = gpu_id
                        if u == uuid:
                            close_rethink_connection(r_conn)
                            return d_uuids[u]

    except Exception as e:
        close_rethink_connection(r_conn)
        logs.exception_id.debug("0080")
        logs.main.error(e)
        return False
    close_rethink_connection(r_conn)
    return False


def get_all_mdev_uuids_from_profile(gpu_id, profile):
    r_conn = new_rethink_connection()
    rtable = r.table("vgpus")

    try:
        l = list(
            rtable.get(gpu_id)
            .pluck({"mdevs": [profile]})
            .run(r_conn)["mdevs"][profile]
            .keys()
        )

    except Exception as e:
        close_rethink_connection(r_conn)
        return list()

    close_rethink_connection(r_conn)
    return l


def update_vgpu_uuid_domain_action(
    gpu_id, mdev_uuid, action, domain_id=False, profile=None
):
    if action not in ["domain_reserved", "domain_started", "domain_stopped"]:
        logs.main.error(
            "action in update_vgpu_uuid_domain_action function is not domain_reserved or domain_started"
        )
        return False
    r_conn = new_rethink_connection()
    rtable = r.table("vgpus")
    try:
        if profile is None:
            d_mdevs = rtable.get(gpu_id).pluck("mdevs").run(r_conn)["mdevs"]
            d_uuids = {}
            for profile, e in d_mdevs.items():
                for u, d_uuid in e.items():
                    d_uuids[u] = d_uuid.copy()
                    d_uuids[u]["profile"] = profile

            if mdev_uuid not in d_uuids.keys():
                logs.main.error(
                    f"domain {domain_id} with gpu {gpu_id} and uuid {mdev_uuid}, but uuid does not exist in vgpus table"
                )
                close_rethink_connection(r_conn)
                return False

            if d_uuids[mdev_uuid]["domain_started"] is False:
                logs.main.error(
                    f"domain {domain_id} with gpu {gpu_id} and uuid {mdev_uuid}, uuid exists but domain_started is False, nothing to update"
                )
                close_rethink_connection(r_conn)
                return False
            profile = d_uuids[mdev_uuid]["profile"]

        if get_vgpu_uuid_status(mdev_uuid, gpu_id, profile) is not False:
            # if mdev_uuid in rtable.get(gpu_id).pluck({"mdevs":[profile]}).run(r_conn)['mdevs'][profile].keys():
            if action == "domain_reserved":
                results = (
                    rtable.get(gpu_id)
                    .update(
                        {"mdevs": {profile: {mdev_uuid: {"domain_started": False}}}}
                    )
                    .run(r_conn)
                )
                results = (
                    rtable.get(gpu_id)
                    .update(
                        {
                            "mdevs": {
                                profile: {mdev_uuid: {"domain_reserved": domain_id}}
                            }
                        }
                    )
                    .run(r_conn)
                )
                if domain_id is not False:
                    results = (
                        r.table("domains")
                        .get(domain_id)
                        .update(
                            {
                                "vgpu_info": {
                                    "gpu_id": gpu_id,
                                    "profile": profile,
                                    "uuid": mdev_uuid,
                                    "started": False,
                                    "reserved": True,
                                }
                            }
                        )
                        .run(r_conn)
                    )
                else:
                    results = (
                        r.table("domains")
                        .get(domain_id)
                        .update(
                            {
                                "vgpu_info": {
                                    "gpu_id": False,
                                    "profile": False,
                                    "uuid": False,
                                    "started": False,
                                    "reserved": False,
                                }
                            }
                        )
                        .run(r_conn)
                    )
                logs.main.info(
                    f"vgpu reserved: domain_id:  {domain_id} / gpu_id: {gpu_id} / profile: {profile} / uuid: {mdev_uuid}"
                )
            if action == "domain_started":
                results = (
                    rtable.get(gpu_id)
                    .update(
                        {"mdevs": {profile: {mdev_uuid: {"domain_reserved": False}}}}
                    )
                    .run(r_conn)
                )
                results = (
                    rtable.get(gpu_id)
                    .update(
                        {"mdevs": {profile: {mdev_uuid: {"domain_started": domain_id}}}}
                    )
                    .run(r_conn)
                )
                if domain_id is not False:
                    results = (
                        r.table("domains")
                        .get(domain_id)
                        .update(
                            {
                                "vgpu_info": {
                                    "gpu_id": gpu_id,
                                    "profile": profile,
                                    "uuid": mdev_uuid,
                                    "started": True,
                                    "reserved": False,
                                }
                            }
                        )
                        .run(r_conn)
                    )
                logs.main.info(
                    f"vgpu started: domain_id:  {domain_id} / gpu_id: {gpu_id} / profile: {profile} / uuid: {mdev_uuid}"
                )
            if action == "domain_stopped":
                results = (
                    rtable.get(gpu_id)
                    .update(
                        {"mdevs": {profile: {mdev_uuid: {"domain_reserved": False}}}}
                    )
                    .run(r_conn)
                )
                results = (
                    rtable.get(gpu_id)
                    .update(
                        {"mdevs": {profile: {mdev_uuid: {"domain_started": False}}}}
                    )
                    .run(r_conn)
                )
                if domain_id is not False:
                    results = (
                        r.table("domains")
                        .get(domain_id)
                        .update(
                            {
                                "vgpu_info": {
                                    "gpu_id": False,
                                    "profile": False,
                                    "uuid": False,
                                    "started": False,
                                    "reserved": False,
                                }
                            }
                        )
                        .run(r_conn)
                    )
                logs.main.info(
                    f"vgpu stopped: domain_id:  {domain_id} / gpu_id: {gpu_id} / profile: {profile} / uuid: {mdev_uuid}"
                )
        else:
            logs.main.error(
                f"domain {domain_id} with gpu {gpu_id} and uuid {mdev_uuid}, but uuid does not exist in vgpus table with profile {profile}"
            )
            close_rethink_connection(r_conn)
            return False

    except Exception as e:
        close_rethink_connection(r_conn)
        logs.exception_id.debug("0080")
        logs.main.error(e)
        print(e)
        return False

    close_rethink_connection(r_conn)
    return True


def get_vgpus_mdevs(id_gpu, type_gpu):
    r_conn = new_rethink_connection()
    rtable = r.table("vgpus")
    try:
        d = rtable.get(id_gpu).pluck("vgpu_profile", {"mdevs": [type_gpu]}).run(r_conn)
    except Exception as e:
        close_rethink_connection(r_conn)
        return False, False, {}
    close_rethink_connection(r_conn)
    return d["vgpu_profile"], d["mdevs"]


def domain_get_vgpu_info(domain_id):
    r_conn = new_rethink_connection()
    rtable_dom = r.table("domains")
    try:
        d = dict(rtable_dom.get(domain_id).pluck("vgpu_info").run(r_conn))
        close_rethink_connection(r_conn)
    except Exception as e:
        close_rethink_connection(r_conn)
        return {}
    return d.get("vgpu_info", {})


def update_vgpu_info_if_stopped(dom_id):
    vgpu_info = domain_get_vgpu_info(dom_id)
    if (
        vgpu_info.get("started", False) is True
        or vgpu_info.get("reserved", False) is True
    ):
        update_vgpu_uuid_domain_action(
            vgpu_info.get("gpu_id", False),
            vgpu_info.get("uuid", False),
            "domain_stopped",
            domain_id=dom_id,
            profile=vgpu_info.get("profile", False),
        )


####


def insert_domain(dict_domain):
    r_conn = new_rethink_connection()
    rtable = r.table("domains")

    result = rtable.insert(dict_domain).run(r_conn)
    close_rethink_connection(r_conn)
    return result


def remove_domain(id):
    r_conn = new_rethink_connection()
    rtable = r.table("domains")

    result = rtable.get(id).delete().run(r_conn)
    close_rethink_connection(r_conn)
    return result


failed_autostarts_cache = TTLCache(maxsize=100, ttl=60)


def get_domains_flag_autostart_to_starting():
    r_conn = new_rethink_connection()
    rtable = r.table("domains")
    try:
        ids_autostarts_must_start = list(
            rtable.get_all(["desktop", True, "Stopped"], index="kind_autostart_status")
            .pluck("id")["id"]
            .run(r_conn)
        )
        ids_autostarts_failed_retries = list(
            rtable.get_all(["desktop", True, "Failed"], index="kind_autostart_status")
            .pluck("id")["id"]
            .run(r_conn)
        )
        ids_failed_to_be_retried = ids_autostarts_failed_retries.copy()
        for autostart_id in ids_autostarts_failed_retries:
            try:
                failed_autostarts_cache[autostart_id]
                ids_failed_to_be_retried.remove(autostart_id)
            except Exception as e:
                failed_autostarts_cache[autostart_id] = "1"
        if len(ids_failed_to_be_retried) > 0:
            logs.main.error(
                f"We've got {len(ids_failed_to_be_retried)} FAILED AUTOSTART SERVERS to start"
            )
    except Exception as e:
        logs.exception_id.debug("0040")
        logs.main.error(e)
        close_rethink_connection(r_conn)
        return []
    close_rethink_connection(r_conn)
    return ids_autostarts_must_start + ids_failed_to_be_retried


def update_domain_history_from_id_domain(domain_id, new_status, new_detail, date_now):
    r_conn = new_rethink_connection()
    rtable = r.table("domains")

    # domain_fields = rtable.get(domain_id).pluck('status','history_domain','detail','hyp_started').run(r_conn)
    try:
        domain_fields = (
            rtable.get(domain_id).pluck("history_domain", "hyp_started").run(r_conn)
        )
    except Exception as e:
        logs.exception_id.debug("0041")
        logs.main.error(
            f"domain {domain_id} does not exists in db and update_domain_history_from_id_domain is not posible"
        )
        logs.main.error(e)
        close_rethink_connection(r_conn)
        return False
    close_rethink_connection(r_conn)

    if "history_domain" in domain_fields:
        history_domain = domain_fields["history_domain"]
    else:
        history_domain = []

    if new_detail is None:
        new_detail = ""

    if "hyp_started" in domain_fields:
        hyp_started = domain_fields["hyp_started"]
    else:
        hyp_started = False

    # now = date_now.strftime("%Y-%b-%d %H:%M:%S.%f")
    now = int(time.time())
    update_domain_history_status(
        domain_id=domain_id,
        new_status=new_status,
        when=now,
        history_domain=history_domain,
        detail=new_detail,
        hyp_id=hyp_started,
    )
    return True


def update_domain_history_status(
    domain_id, new_status, when, history_domain, detail="", hyp_id=""
):
    list_history_domain = create_list_buffer_history_domain(
        new_status, when, history_domain, detail, hyp_id
    )

    r_conn = new_rethink_connection()
    rtable = r.table("domains")
    results = (
        rtable.get(domain_id)
        .update({"history_domain": list_history_domain})
        .run(r_conn)
    )

    close_rethink_connection(r_conn)
    return results


def get_qos_disk_iotune(qos_id):
    r_conn = new_rethink_connection()
    rtable = r.table("qos_disk")
    try:
        d = rtable.get(qos_id).pluck("iotune").run(r_conn)
    except Exception as e:
        close_rethink_connection(r_conn)
        return False
    close_rethink_connection(r_conn)
    return d["iotune"]


def update_domain_start_after_created(id_domain, do_create=True):
    r_conn = new_rethink_connection()
    rtable = r.table("domains")

    rtable.get(id_domain).update({"start_after_created": do_create}).run(r_conn)
    close_rethink_connection(r_conn)


def update_domains_started_in_hyp_to_unknown(hyp_id):
    # TODO, ASEGURARNOS QUE LOS status DE LOS DOMINIOS ESTÁN EN start,unknown,paused
    # no deberían tener hypervisor activo en otro estado, pero por si las moscas
    # y ya de paso quitar eh hyp_started si queda alguno
    r_conn = new_rethink_connection()
    rtable = r.table("domains")

    result = (
        rtable.get_all(hyp_id, index="hyp_started")
        .update({"status": "Unknown"})
        .run(r_conn)
    )
    close_rethink_connection(r_conn)
    return result


def get_domains_started_in_hyp(hyp_id, only_started=False, only_unknown=False):
    # TODO, ASEGURARNOS QUE LOS status DE LOS DOMINIOS ESTÁN EN start,unknown,paused
    # no deberían tener hypervisor activo en otro estado, pero por si las moscas
    # y ya de paso quitar eh hyp_started si queda alguno
    r_conn = new_rethink_connection()
    rtable = r.table("domains")

    list_domain = list(
        rtable.get_all(hyp_id, index="hyp_started").pluck("id", "status").run(r_conn)
    )
    close_rethink_connection(r_conn)
    if only_started is True:
        d = {
            d["id"]: d["status"]
            for d in list_domain
            if d["status"] in STATUS_STABLE_DOMAIN_RUNNING
        }
    elif only_unknown is True:
        d = {d["id"]: d["status"] for d in list_domain if d["status"] in "Unknown"}
    else:
        d = {d["id"]: d["status"] for d in list_domain}

    return d


def remove_fieds_when_stopped(id_domain):
    with rethink_conn() as conn:
        r.table("domains").get(id_domain).update(
            {
                "create_dict": {"personal_vlans": False},
                "hyp_started": False,
            },
        ).run(conn)
    remove_domain_viewer_values(id_domain)


def domains_with_attached_disk(disk_path):
    r_conn = new_rethink_connection()
    domains = list(
        r.table("domains")
        .get_all(disk_path, index="disk_paths")
        .pluck("id")["id"]
        .run(r_conn)
    )
    close_rethink_connection(r_conn)
    return domains


def domains_with_attached_storage_id(storage_id):
    r_conn = new_rethink_connection()
    domains = list(
        r.table("domains")
        .get_all(storage_id, index="storage_ids")
        .pluck("id")["id"]
        .run(r_conn)
    )
    close_rethink_connection(r_conn)
    return domains


def get_and_update_personal_vlan_id_from_domain_id(
    id_domain, id_interface, range_start, range_end
):
    r_conn = new_rethink_connection()
    user_id = dict(r.table("domains").get(id_domain).pluck("user").run(r_conn))["user"]
    vlan_ids = list(
        set(
            list(
                r.table("domains")
                .get_all(user_id, index="user")
                .filter(
                    r.row["status"].eq("Started")
                    | r.row["status"].eq("Shutting-down")
                    | r.row["status"].eq("Starting")
                    | r.row["status"].eq("Stopping")
                )
                .filter(r.row["create_dict"].has_fields("personal_vlans"))
                .filter(~r.row["create_dict"]["personal_vlans"].eq(False))
                .filter(
                    lambda doc: doc["create_dict"]["personal_vlans"].has_fields(
                        id_interface
                    )
                )
                .pluck([{"create_dict": {"personal_vlans": True}}])["create_dict"][
                    "personal_vlans"
                ][id_interface]
                .coerce_to("array")
                .run(r_conn)
            )
        )
    )
    if len(vlan_ids) > 0:
        # check if all vlan_ids are the same
        if len(vlan_ids) > 1:
            logs.main.error(
                f"personal vlan_id {vlan_ids} error: vlan_ids are not the same in user {user_id} started domains"
            )
            close_rethink_connection(r_conn)
            return False
        # check if vlan_id is in range
        if vlan_ids[0] > range_end or vlan_ids[0] < range_start:
            logs.main.error(
                f"personal vlan_id {vlan_ids[0]} error: vlan_id > {range_end} or vlan_id < {range_start} in domain {id_domain}"
            )
            close_rethink_connection(r_conn)
            return False
        # We have a valid vlan_id
        vlan_id = vlan_ids[0]
    else:
        # The user is still not using any vlan_id in this interface
        # We have to get the next vlan_id in range not used in other domains
        used_personal_vlan_ids = set(
            list(
                r.table("domains")
                .get_all(
                    r.args(
                        [
                            "Started",
                            "Starting",
                            "Stopping",
                            "Shutting-down",
                        ]
                    ),
                    index="status",
                )
                .filter(r.row["create_dict"].has_fields("personal_vlans"))
                .filter(~r.row["create_dict"]["personal_vlans"].eq(False))
                .filter(
                    lambda doc: doc["create_dict"]["personal_vlans"].has_fields(
                        id_interface
                    )
                )
                .pluck([{"create_dict": {"personal_vlans": True}}])["create_dict"][
                    "personal_vlans"
                ][id_interface]
                .coerce_to("array")
                .run(r_conn)
            )
        )
        # check if the range is not full
        if len(used_personal_vlan_ids) >= range_end - range_start:
            logs.main.error(
                f"personal vlan_id error: range {range_start}-{range_end} is full in user {user_id} started domains"
            )
            close_rethink_connection(r_conn)
            return False

        # get the next vlan_id in range not used in other domains
        vlan_id = False
        for i in range(range_start, range_end):
            if i not in used_personal_vlan_ids:
                vlan_id = i
                break
    if vlan_id is not False:
        # update the domain with the new vlan_id
        r.table("domains").get(id_domain).update(
            {"create_dict": {"personal_vlans": {id_interface: vlan_id}}}
        ).run(r_conn)
    close_rethink_connection(r_conn)
    return vlan_id


def get_all_mac():
    r_conn = new_rethink_connection()
    all_macs = list(
        r.table("domains")
        .get_all("desktop", index="kind")
        .pluck({"create_dict": {"hardware": {"interfaces": True}}})["create_dict"][
            "hardware"
        ]["interfaces"]
        .concat_map(lambda x: [x["mac"]])
        .run(r_conn)
    )
    close_rethink_connection(r_conn)
    return all_macs


macs_in_use = get_all_mac()

logs.main.info(f"macs_in_use: {len(macs_in_use)}")


def gen_random_mac():
    mac = [
        0x52,
        0x54,
        0x00,
        random.randint(0x00, 0x7F),
        random.randint(0x00, 0xFF),
        random.randint(0x00, 0xFF),
    ]
    return ":".join(map(lambda x: "%02x" % x, mac))


def gen_new_mac():
    new_mac = gen_random_mac()
    # 24 bit combinations = 16777216 ~= 16.7 million. Is this enough macs for your system?
    # Take into account that each desktop could have múltime interfaces... still milions of unique macs
    while macs_in_use.count(new_mac) > 0:
        new_mac = gen_random_mac()
    macs_in_use.append(new_mac)
    return new_mac


## Personal Units


class PersonalUnit(TypedDict):
    user_id: str
    password: str
    dav: str
    tls: bool
    verify_cert: bool
    web: str


def get_personal_unit_from_domain(domain_id: str) -> PersonalUnit:
    """Get the personal unit configuration that applies to a domain"""
    r_conn = new_rethink_connection()

    user_id = (r.table("domains").get(domain_id).pluck("user").run(r_conn)).get("user")

    personal_unit = (
        r.table("users").get(user_id).pluck("user_storage").run(r_conn)
    ).get("user_storage")

    close_rethink_connection(r_conn)
    return personal_unit


## Used only in tests


def get_all_domains_with_id_and_status(status=None, kind="desktop"):
    r_conn = new_rethink_connection()
    rtable = r.table("domains")
    if status is None:
        l = list(rtable.get_all(kind, index="kind").pluck("id", "status").run(r_conn))
    else:
        l = list(
            rtable.get_all([kind, status], index="kind_status")
            .pluck("id", "status")
            .run(r_conn)
        )
    close_rethink_connection(r_conn)
    return l
