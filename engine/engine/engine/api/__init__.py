import json
import os
from time import sleep

from engine.models.engine import Engine
from engine.services.db import (
    get_domains_started_in_vgpu,
    get_hyp_hostname_user_port_from_id,
    get_vgpu_info,
    get_vgpu_model_profile_change,
)
from engine.services.db.db import get_isardvdi_secret, update_table_field
from engine.services.lib.functions import execute_commands
from engine.services.log import logs
from flask import Blueprint, current_app, jsonify, request

api = Blueprint("api", __name__)

app = current_app
# from . import evaluate
from .tokens import is_admin

#### NOTE: The /engine paths are publicy open so they need @is_admin decorator!


def shutdown_server():
    func = request.environ.get("werkzeug.server.shutdown")
    if func is None:
        raise RuntimeError("Not running with the Werkzeug Server")
    func()


@api.route("/", methods=["GET"])
def get_if_running():
    return jsonify({"running": True}), 200


@api.route("/threads", methods=["GET"])
def get_threads():
    d = {
        "threads_info_hyps": app.m.threads_info_hyps,
        "threads_info_main": app.m.threads_info_main,
    }
    json_d = json.dumps(d)

    return jsonify(threads=json_d), 200


@api.route(
    "/create_domain/bulk_to_user/<string:username>/<string:template_id>/<int:quantity>/<string:prefix>",
    methods=["POST"],
)
def create_domain_bulk():
    pass


@api.route(
    "/create_domain/bulk_random_to_user/<string:username>/<int:quantity>/<string:prefix>",
    methods=["POST"],
)
def create_domain_bulk_random_to_user():
    pass


@api.route(
    "/create_domain/to_user/<string:username>/<string:template_id>/<string:domain_id>",
    methods=["POST"],
)
def create_domain_bulk_to_user():
    pass


@api.route(
    "/create_domain/to_group/<string:group>/<string:template_id>/<int:quantity>/<string:prefix>",
    methods=["POST"],
)
def create_domain_to_group():
    pass


@api.route("/action_with_domain/<string:action>/<string:domain_id>", methods=["PUT"])
def start_domain():
    pass


@api.route(
    "/action_with_domains_group_by/<string:groupby>/<string:action>/with_prefix/<string:prefix>",
    methods=["PUT"],
)
def action_with_domains_group_by():
    pass


@api.route(
    "/action_with_domains/<string:action>/from_user/<string:username>", methods=["PUT"]
)
def start_domain_with_prefix():
    pass


@api.route(
    "/action_with_domains/<string:action>/from_template/<string:template>",
    methods=["PUT"],
)
def start_domain_with_prefix_from_template():
    pass


@api.route("/stop_threads", methods=["GET"])
def stop_threads():
    app.m.stop_threads()
    return jsonify({"stop_threads": True}), 200


@api.route("/grafana/restart", methods=["GET"])
def grafana_restart():
    app.m.t_grafana.restart_send_config = True


@api.route("/status")
def engine_status():
    """all main threads are running"""

    pass


@api.route("/pool/<string:id_pool>/status")
def pool_status(id_pool):
    """hypervisors ready to start and create disks"""
    pass


@api.route("/grafana/reload")
def grafana_reload():
    """changes in grafana parameters"""
    pass


@api.route("/events/stop")
def stop_thread_event():
    app.m.t_events.stop = True
    app.t_events.q_event_register.put(
        {"type": "del_hyp_to_receive_events", "hyp_id": ""}
    )


@api.route("/restart", methods=["GET"])
def engine_restart():
    address_from = request.access_route[0]
    logs.main.info(f"engine_restart api called from {address_from}")
    pass


@api.route("/info", methods=["GET"])
def engine_info():
    d_engine = {}
    http_code = 503
    # if len(app.db.get_hyp_hostnames_online()) > 0:
    try:
        if app.m.t_background != None:
            try:
                app.m.t_background.is_alive()
            except AttributeError:
                d_engine["background_is_alive"] = False
                return jsonify(d_engine), http_code

            if app.m.t_background.is_alive():
                manager = app.m
                d_engine["background_is_alive"] = True
                d_engine["event_thread_is_alive"] = (
                    app.m.t_events.is_alive() if app.m.t_events != None else False
                )
                d_engine["broom_thread_is_alive"] = (
                    app.m.t_broom.is_alive() if app.m.t_broom != None else False
                )
                d_engine["download_changes_thread_is_alive"] = (
                    app.m.t_downloads_changes.is_alive()
                    if app.m.t_downloads_changes != None
                    else False
                )
                d_engine["orchestrator_thread_is_alive"] = getattr(
                    app.m.t_orchestrator, "is_alive", bool
                )()
                d_engine["changes_domains_thread_is_alive"] = (
                    app.m.t_changes_domains.is_alive()
                    if app.m.t_changes_domains != None
                    else False
                )
                d_engine["grafana_thread_is_alive"] = getattr(
                    app.m.t_grafana, "is_alive", bool
                )()
                d_engine["working_threads"] = list(app.m.t_workers.keys())
                d_engine["status_threads"] = list(app.m.t_status.keys())
                d_engine["disk_operations_threads"] = list(
                    app.m.t_disk_operations.keys()
                )
                d_engine["long_operations_threads"] = list(
                    app.m.t_long_operations.keys()
                )

                d_engine["alive_threads"] = dict()
                d_engine["alive_threads"]["working_threads"] = {
                    name: t.is_alive() for name, t in app.m.t_workers.items()
                }
                d_engine["alive_threads"]["status_threads"] = {
                    name: t.is_alive() for name, t in app.m.t_status.items()
                }
                d_engine["alive_threads"]["disk_operations_threads"] = {
                    name: t.is_alive() for name, t in app.m.t_disk_operations.items()
                }
                d_engine["alive_threads"]["long_operations_threads"] = {
                    name: t.is_alive() for name, t in app.m.t_long_operations.items()
                }

                d_engine["queue_size_working_threads"] = {
                    k: q.qsize() for k, q in app.m.q.workers.items()
                }
                d_engine["queue_disk_operations_threads"] = {
                    k: q.qsize() for k, q in app.m.q_disk_operations.items()
                }
                d_engine["queue_long_operations_threads"] = {
                    k: q.qsize() for k, q in app.m.q_long_operations.items()
                }
                d_engine["is_alive"] = True
                http_code = 200
            else:
                d_engine["is_alive"] = False
        else:
            d_engine["is_alive"] = False
        return jsonify(d_engine), http_code
    except AttributeError:
        d_engine["is_alive"] = False
        print("ERROR ----- ENGINE IS DEATH", flush=True)
        return jsonify(d_engine), http_code
    except Exception as e:
        logs.exception_id.debug("0002")
        d_engine["is_alive"] = False
        print("ERROR ----- ENGINE IS DEATH AND EXCEPTION DETECTED", flush=True)
        return jsonify(d_engine), http_code


@api.route("/domains/user/<string:username>", methods=["GET"])
def get_domains(username):
    domains = app.db.get_domains_from_user(username)
    json_domains = json.dumps(domains, sort_keys=True, indent=4)

    return jsonify(domains=json_domains)


@api.route("/profile/gpu/<string:gpu_id>", methods=["PUT"])
def set_gpu_profile(gpu_id):
    logs.main.info("set_gpu_profile: {}".format(gpu_id))
    d = request.get_json()
    pci_id = gpu_id.split("-")[-1]
    profile_id = d.get("profile_id", False)
    profile = profile_id.split("-")[-1]
    hyp_id = gpu_id[: gpu_id.rfind("-")]

    h = app.m.t_workers[hyp_id].h
    # old_profile = h.info_nvidia.get(pci_id,{}).get('vgpu_profile',None)
    h.change_vgpu_profile(gpu_id, profile)
    h.info_nvidia[pci_id]["model"]
    return jsonify(True)


@api.route("/profile/gpu/<string:gpu_id>", methods=["GET"])
def get_gpu_profile(payload, gpu_id):
    logs.main.info("get_gpu_profile: {}".format(gpu_id))
    d = get_vgpu_model_profile_change(gpu_id)
    if not d:
        logs.main.error(
            "get_gpu_profile: {} does not exist in table vgpus".format(gpu_id)
        )
        return jsonify({"error": str(gpu_id) + "does not exist in vgpus table"}), 404
    return jsonify(d)


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


@api.route("/profile/gpu/started_domains/<string:gpu_id>", methods=["GET"])
def get_gpu_started_domains(gpu_id):
    logs.main.info("get_gpu_started_domains: {}".format(gpu_id))
    l_domains = get_domains_started_in_vgpu(gpu_id)
    return jsonify(l_domains)


@api.route("/qmp/<string:desktop_id>", methods=["PUT"])
def send_qmp(desktop_id):
    command = request.get_json()
    logs.main.info(
        "NOT IMPLEMENTED. send_qmp: action: {}, kwargs: {}".format(
            command["action"], str(command["kwargs"])
        )
    )
