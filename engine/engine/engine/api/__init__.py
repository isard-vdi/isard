import base64
import json
import os

from cachetools import TTLCache, cached
from engine.models.balancers import BalancerInterface
from engine.services.db import (
    get_domains_started_in_vgpu,
    get_hyp_hostname_user_port_from_id,
    get_vgpu_info,
    get_vgpu_model_profile_change,
)
from engine.services.db.hypervisors import get_hyp_system_info
from engine.services.lib.functions import execute_commands
from engine.services.log import logs
from flask import Blueprint, current_app, jsonify, request

api = Blueprint("api", __name__)

app = current_app

from .tokens import is_admin

#### NOTE: The /engine paths are publicy open so they need @is_admin decorator!


@api.route("/threads", methods=["GET"])
def get_threads():
    d = {
        "threads_info_hyps": app.m.threads_info_hyps,
        "threads_info_main": app.m.threads_info_main,
    }
    json_d = json.dumps(d)

    return jsonify(threads=json_d), 200


@api.route("/info", methods=["GET"])
def engine_info():
    return "alive", 200


engine_threads = [
    "background",
    "events",
    "broom",
    "downloads_changes",
    "orchestrator",
    "changes_domains",
]

virt_balancer_type = os.environ.get("ENGINE_HYPER_BALANCER", "available_ram_percent")
virt_balancer = BalancerInterface(
    "default",
    balancer_type=virt_balancer_type,
)

disk_balancer_type = os.environ.get("ENGINE_DISK_BALANCER", "less_cpu")
disk_balancer = BalancerInterface(
    "00000000-0000-0000-0000-000000000000",
    balancer_type=disk_balancer_type,
)


@cached(cache=TTLCache(maxsize=1, ttl=5))
@api.route("/engine/status", methods=["GET"])
@is_admin
def engine_status(payload):
    try:
        if not app.m.t_background.is_alive():
            return "Thread Background dead.", 428
        for t in engine_threads:
            if not (
                getattr(app.m, "t_" + t).is_alive()
                if getattr(app.m, "t_" + t) != None
                else False
            ):
                return "Thread {} dead.".format(t), 428
        disk = disk_balancer.get_next_diskoperations()
        virt, _ = virt_balancer.get_next_hypervisor()
        if not disk and not virt:
            return "No hypervisor available.", 428
        if not disk:
            return "No hypervisor for disk operations available.", 428
        if not virt:
            return "No hypervisor for virtualization available.", 428
        return "Ok", 200
    except:
        return "Exception!", 500


@cached(cache=TTLCache(maxsize=1, ttl=5))
@api.route("/engine/status/detail", methods=["GET"])
@is_admin
def engine_status_detail(payload):
    # 0: system ok
    # 1: system working with minor problems
    # 2: system malfunctioning
    engine = {
        "operational": True,
        "status_main": 0,
        "status_virt": 0,
        "status_disk": 0,
        "problems": [],
    }
    try:
        # Background thread
        if not app.m.t_background.is_alive():
            engine["status_main"] = 2
            engine["operational"] = False
            engine["problems"].append([2, "main", "Dead thread(s): background"])

        # Main threads
        deads = []
        for t in engine_threads:
            if not (
                getattr(app.m, "t_" + t).is_alive()
                if getattr(app.m, "t_" + t) != None
                else False
            ):
                deads.append(t)
        if len(deads) > 0:
            engine["status_main"] = 2
            engine["operational"] = False
            engine["problems"].append(
                [2, "main", "Dead thread(s): " + ", ".join(deads)]
            )

        # HYPERVISORS VIRT/DISKOP DATABASE
        db_hypers = get_hyp_system_info()
        for hyper in db_hypers:
            virtualization = None
            virtualization_queued = 0
            disk_operations = None
            disk_operations_queued = 0
            if hyper["status"] == "Online":
                if hyper["capabilities"]["hypervisor"]:
                    if (
                        hyp["id"] in app.m.t_workers
                        and app.m.t_workers[hyp["id"]].is_alive()
                    ):
                        virtualization = True
                        engine["hypers_virt"] += 1
                        virtualization_queued = app.m.q.workers[hyp["id"]].qsize()
                    else:
                        virtualization = False
                        engine["problems"].append(
                            [
                                1,
                                "hypervisor",
                                "Hypervisor {} virtualization capability not alive".format(
                                    hyper["id"]
                                ),
                            ]
                        )
                if hyper["capabilities"]["disk_operations"]:
                    if (
                        hyp["id"] in app.m.t_disk_operations
                        and app.m.t_disk_operations[hyp["id"]].is_alive()
                    ):
                        disk_operations = True
                        engine["hypers_diskop"] += 1
                        disk_operations_queued = app.m.q_disk_operations[
                            hyp["id"]
                        ].qsize()
                    else:
                        disk_operations = False
                        engine["problems"].append(
                            [
                                1,
                                "hypervisor",
                                "Hypervisor {} disk operations capability not alive".format(
                                    hyper["id"]
                                ),
                            ]
                        )
            engine["hypervisors"][hyper["id"]] = {
                "status": hyper["status"],
                "stats": hyper["stats"],
                "virt_cap": virtualization,
                "virt_op_queued": virtualization_queued,
                "disk_cap": disk_operations,
                "disk_op_queued": disk_operations_queued,
            }
            engine["queued_virtop"] += virtualization_queued
            engine["queued_diskop"] += disk_operations_queued

        if not len(db_hypers):
            if engine["hypers_virt"] == 0:
                engine["problems"].append(
                    [2, "database", "No virtualization hypervisors registered."]
                )
        else:
            if engine["hypers_virt"] == 0:
                engine["problems"].append(
                    [2, "database", "No virtualization hypervisors registered."]
                )
                engine["hypers_virt_next"] = False
            else:
                engine["hypers_virt_next"] = virt_balancer.get_next_hypervisor()
            if engine["hypers_diskop"] == 0:
                engine["problems"].append(
                    [2, "database", "No disk operations hypervisors registered."]
                )
                engine["hypers_diskop_next"] = False
            else:
                engine["hypers_diskop_next"] = disk_balancer.get_next_diskoperations()

        # Next host to execute virtualization and disk operations
        engine["next_virt"] = virt_balancer.get_next_hypervisor()
        if not engine["next_virt"]:
            engine["alive_level"] = 2
            engine["alive_detail"] = "No hypervisor for virtualization available"
        engine["next_diskop"] = disk_balancer.get_next_diskoperations()
        if not engine["next_diskop"]:
            engine["alive_level"] = 2
            engine["alive_detail"] = "No hypervisor for disk operations available"
        # Virtualization and disk operations threads and queues
        for hyp in db_hypers:
            if hyp["id"] in app.m.t_workers and app.m.t_workers[hyp["id"]].is_alive():
                engine["virt_th"][hyp["id"]] = hyp
                engine["virt_th_alive"] += 1
                engine["virt_th"][hyp["id"]]["queued"] = app.m.q.workers[
                    hyp["id"]
                ].qsize()
                engine["virt_queued_total"] += app.m.q.workers[hyp["id"]].qsize()
            else:
                engine["virt_th"][hyp["id"]] = False
            if (
                hyp["id"] in app.m.t_disk_operations
                and app.m.t_disk_operations[hyp["id"]].is_alive()
            ):
                engine["disk_th"][hyp["id"]] = hyp
                engine["disk_th_alive"] += 1
                engine["disk_th"][hyp["id"]]["queued"] = app.m.q_disk_operations[
                    hyp["id"]
                ].qsize()
                engine["disk_queued_total"] += app.m.q_disk_operations[
                    hyp["id"]
                ].qsize()
            else:
                engine["disk_th"][hyp["id"]] = False
        # Compute alive

        # if engine["main_th"]["background"] == False:

        engine["alive_detail"] = engine["main_th"]
        ## Engine needs restart if any of the virtualization threads is not alive
        engine["alive_detail"].update(engine["virt_th"])
        ## Engine needs restart if any of the disk operations threads is not alive
        engine["alive_detail"].update(engine["disk_th"])
        engine["alive_detail"]
        engine["alive"] = (
            engine["alive"]
            and engine["virt_th_alive"] == len(db_hypers)
            and engine["disk_th_alive"] == len(db_hypers)
        )
        return jsonify(engine), 200
    except Exception as e:
        logs.main.error("engine_status: {}".format(e))
        return jsonify({"alive": False, "error": str(e)}), 500


def _next_hyper(pool_id="default"):
    next_hyp, extra_info = app.m.pools[pool_id].balancer.get_next_hypervisor()
    return next_hyp


def _next_diskop(pool_id="00000000-0000-0000-0000-000000000000"):
    disk_operations = app.m.diskoperations_pools[
        pool_id
    ].balancer.get_next_diskoperations()
    return disk_operations


@api.route("/engine/profile/gpu/<string:gpu_id>", methods=["PUT"])
@is_admin
def set_gpu_profile(payload, gpu_id):
    logs.main.info("set_gpu_profile: {}".format(gpu_id))
    d = request.get_json(force=True)
    pci_id = gpu_id.split("-")[-1]
    profile_id = d.get("profile_id", False)
    profile = profile_id.split("-")[-1]
    hyp_id = gpu_id[: gpu_id.rfind("-")]

    h = app.m.t_workers[hyp_id].h
    # old_profile = h.info_nvidia.get(pci_id,{}).get('vgpu_profile',None)
    h.change_vgpu_profile(gpu_id, profile)
    h.info_nvidia[pci_id]["model"]
    return jsonify(True)


@api.route("/engine/profile/gpu/<string:gpu_id>", methods=["GET"])
@is_admin
def get_gpu_profile_jwt(payload, gpu_id):
    logs.main.info("get_gpu_profile: {}".format(gpu_id))
    d = get_vgpu_model_profile_change(gpu_id)
    if not d:
        logs.main.error(
            "get_gpu_profile: {} does not exist in table vgpus".format(gpu_id)
        )
        return jsonify({"error": str(gpu_id) + "does not exist in vgpus table"}), 404
    return jsonify(d)


@api.route("/engine/profile/gpu/mdevcmd/<string:gpu_id>", methods=["GET"])
@is_admin
def get_gpu_from_mdevcmd_profile_jwt(payload, gpu_id):
    profile = False
    logs.main.info("get_gpu_profile_from_mdev_command: {}".format(gpu_id))
    cmds_mdev = ["mdevctl list"]
    try:
        d_info = get_vgpu_info(gpu_id)
        hyp_id = d_info["hyp_id"]
        d_types = d_info["info"]["types"]
        d = get_hyp_hostname_user_port_from_id(hyp_id)
        hostname = d["hostname"]
        port = d["port"]
        user = d["user"]
        arra_out_err = execute_commands(hostname, cmds_mdev, port=port, user=user)
        mdevctl_out_lines = [
            l for l in arra_out_err[0]["out"].splitlines() if len(l) > 0
        ]
        extract_pci_model_from_mdev_out = [
            [b.split(" ")[0], b.split(" ")[1]]
            for b in list(
                set(
                    [
                        "_".join(a[0].split(":")[0:2]) + " " + a[1]
                        for a in [l.split(" ")[1:3] for l in mdevctl_out_lines]
                    ]
                )
            )
        ]
        model = [b[1] for b in extract_pci_model_from_mdev_out if gpu_id.find(b[0]) > 0]

        d_model_types = {v["id"]: k for k, v in d_types.items()}

        if len(model) > 0:
            profile = d_model_types[model[0]]

    except Exception as e:
        logs.main.error(f"Exception extracting mdevcmd_profile: {e}")

    return jsonify({"gpu_id": gpu_id, "profile": profile})


@api.route("/engine/profile/gpu/started_domains/<string:gpu_id>", methods=["GET"])
@is_admin
def get_gpu_started_domains(payload, gpu_id):
    logs.main.info("get_gpu_started_domains: {}".format(gpu_id))
    l_domains = get_domains_started_in_vgpu(gpu_id)
    return jsonify(l_domains)


@api.route("/engine/qmp/<string:desktop_id>", methods=["PUT"])
@is_admin
def send_qmp(payload, desktop_id):
    ## This was done at bookings and only used from there.
    ## Should be reformulated as per qmp/notify endpoint
    ## maybe as /qmp/notify/custom/... for custom message.
    command = request.get_json()
    logs.main.info(
        "NOT IMPLEMENTED. send_qmp: action: {}, kwargs: {}".format(
            command["action"], str(command["kwargs"])
        )
    )
    return jsonify(True)


@api.route("/engine/qmp/notify/<string:desktop_id>", methods=["POST"])
@is_admin
def qmp_notify(payload, desktop_id):
    data = request.get_json(force=True)
    _send_message_qmp(data.get("desktop_id"), data.get("message"))
    return jsonify(True)


def _send_message_qmp(desktop_id, message):
    message_base64 = base64.b64encode(bytes(message, "utf-8"))
    hypervisor = current_app.db.get_domain_hyp_started(desktop_id)
    if hypervisor:
        current_app.m.q.workers[hypervisor].put(
            {"type": "notify", "desktop_id": desktop_id, "message": message_base64}, 10
        )
        logs.main.info(f'Notification of {desktop_id} with message "{message}" queued')
        return jsonify(True)
    else:
        logs.main.error(
            f'Cannot notify domain {desktop_id} with message "{message}" due to it '
            "isn't started"
        )
        return jsonify(False)
