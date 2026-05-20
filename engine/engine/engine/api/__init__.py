import base64
import json

from cachetools import TTLCache, cached
from flask import Blueprint, current_app, jsonify, request

from engine.services.db import (
    get_domains_started_in_vgpu,
    get_hyp_hostname_user_port_from_id,
    get_vgpu_info,
    get_vgpu_model_profile_change,
)
from engine.services.db.hypervisors import get_hyp_system_info
from engine.services.lib.functions import execute_commands
from engine.services.lib.status import engine_threads, get_next_hypervisor
from engine.services.log import logs

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
        virt = get_next_hypervisor()
        if not virt:
            return "No hypervisor for virtualization available.", 428
        return "Ok", 200
    except Exception as e:
        logs.main.error("engine_status: {}".format(e))
        return "Exception! Internal error.", 500


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
        "problems": [],
        "hypers_virt": 0,
        "hypervisors": {},
        "virt_th": {},
        "virt_th_alive": 0,
        "virt_queued_total": 0,
        "queued_virtop": 0,
        "alive": True,
        "alive_level": 0,
        "alive_detail": "System operational",
        "hypers_virt_next": False,
        "next_virt": False,
    }
    try:
        # Background thread
        if not app.m.t_background.is_alive():
            engine["status_main"] = 2
            engine["operational"] = False
            engine["alive_detail"] = "Background thread dead"
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
            engine["alive_detail"] = "Main thread(s) dead"
            engine["problems"].append(
                [2, "main", "Dead thread(s): " + ", ".join(deads)]
            )

        # Hypervisor virtualization status from database
        db_hypers = get_hyp_system_info()
        for hyper in db_hypers:
            virtualization = None
            virtualization_queued = 0
            if hyper["status"] == "Online":
                if hyper["capabilities"]["hypervisor"]:
                    if (
                        hyper["id"] in app.m.t_workers
                        and app.m.t_workers[hyper["id"]].is_alive()
                    ):
                        virtualization = True
                        engine["hypers_virt"] += 1
                        virtualization_queued = app.m.q.workers[hyper["id"]].qsize()
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
            engine["hypervisors"][hyper["id"]] = {
                "status": hyper["status"],
                "stats": hyper.get("stats"),
                "virt_cap": virtualization,
                "virt_op_queued": virtualization_queued,
            }
            engine["queued_virtop"] += virtualization_queued

        if engine["hypers_virt"] == 0:
            engine["problems"].append(
                [2, "database", "No virtualization hypervisors registered."]
            )
            engine["operational"] = False
            engine["hypers_virt_next"] = False
        elif len(db_hypers):
            engine["hypers_virt_next"] = get_next_hypervisor()

        # Next host to execute virtualization
        engine["next_virt"] = get_next_hypervisor()
        if not engine["next_virt"]:
            engine["alive_level"] = 2
            engine["operational"] = False
            engine["alive_detail"] = "No hypervisor for virtualization available"

        # Virtualization threads and queues. Disk operations no longer run
        # on engine-side hypervisor threads — they execute as RQ tasks in
        # isard-storage workers (see isardvdi_common.models.storage chains).
        for hyp in db_hypers:
            if hyp["id"] in app.m.t_workers and app.m.t_workers[hyp["id"]].is_alive():
                engine["virt_th"][hyp["id"]] = {}
                engine["virt_th_alive"] += 1
                engine["virt_th"][hyp["id"]]["queued"] = app.m.q.workers[
                    hyp["id"]
                ].qsize()
                engine["virt_queued_total"] += app.m.q.workers[hyp["id"]].qsize()
            else:
                engine["virt_th"][hyp["id"]] = False
        # Compute alive
        engine["alive"] = engine["alive"] and engine["virt_th_alive"] == len(db_hypers)
        return jsonify(engine), 200
    except Exception as e:
        logs.main.error(e)
        logs.main.error("engine_status: {}".format(e))
        return jsonify({"alive": False, "error": str(e)}), 500


@api.route("/engine/profile/gpu/<string:gpu_id>", methods=["PUT"])
@is_admin
def set_gpu_profile(payload, gpu_id):
    logs.main.info("set_gpu_profile: {}".format(gpu_id))
    d = request.get_json(force=True)
    pci_id = gpu_id.split("-")[-1]
    profile_id = d.get("profile_id", False)
    profile = profile_id
    hyp_id = gpu_id[: gpu_id.rfind("-")]

    h = app.m.t_workers[hyp_id].h
    result = h.change_vgpu_profile(gpu_id, profile)
    # change_vgpu_profile returns False on every failure path it reports to
    # the operator and None on the success path (or early-return when the
    # profile is already active). Treat False as a hard failure so the
    # webapp surfaces the real outcome instead of always showing success.
    if result is False:
        return (
            jsonify(
                {
                    "error": "profile_change_failed",
                    "description": (
                        f"Could not switch {gpu_id} to profile {profile!r}. "
                        f"Check engine logs for the underlying error."
                    ),
                }
            ),
            500,
        )
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
    if hypervisor and hypervisor in current_app.m.q.workers:
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
