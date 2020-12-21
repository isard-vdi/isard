
import json
from time import sleep

from flask import Blueprint, jsonify
from flask import current_app
from flask import request

from engine.models.manager_hypervisors import ManagerHypervisors
from engine.services.db.db import update_table_field

api = Blueprint('api', __name__)

app = current_app
#from . import evaluate

def shutdown_server():
    func = request.environ.get('werkzeug.server.shutdown')
    if func is None:
        raise RuntimeError('Not running with the Werkzeug Server')
    func()

@api.route('/threads', methods=['GET'])
def get_threads():
    d = [{'prova1': 'provando1', 'prova2': 'provando2'}]
    json_d = json.dumps(d)

    return jsonify(threads=json_d), 200


@api.route('/create_domain/bulk_to_user/<string:username>/<string:template_id>/<int:quantity>/<string:prefix>',
           methods=['POST'])
def create_domain_bulk():
    pass


@api.route('/create_domain/bulk_random_to_user/<string:username>/<int:quantity>/<string:prefix>', methods=['POST'])
def create_domain_bulk_random_to_user():
    pass


@api.route('/create_domain/to_user/<string:username>/<string:template_id>/<string:domain_id>', methods=['POST'])
def create_domain_bulk_to_user():
    pass


@api.route('/create_domain/to_group/<string:group>/<string:template_id>/<int:quantity>/<string:prefix>',
           methods=['POST'])
def create_domain_to_group():
    pass


@api.route('/action_with_domain/<string:action>/<string:domain_id>', methods=['PUT'])
def start_domain():
    pass


@api.route('/action_with_domains_group_by/<string:groupby>/<string:action>/with_prefix/<string:prefix>',
           methods=['PUT'])
def action_with_domains_group_by():
    pass


@api.route('/action_with_domains/<string:action>/from_user/<string:username>', methods=['PUT'])
def start_domain_with_prefix():
    pass


@api.route('/action_with_domains/<string:action>/from_template/<string:template>', methods=['PUT'])
def start_domain_with_prefix_from_template():
    pass


@api.route('/stop_threads', methods=['GET'])
def stop_threads():
    app.m.stop_threads()
    return jsonify({'stop_threads':True}), 200


@api.route('/grafana/restart', methods=['GET'])
def grafana_restart():
    app.m.t_grafana.restart_send_config = True

@api.route('/engine/status')
def engine_status():
    '''all main threads are running'''

    pass


@api.route('/pool/<string:id_pool>/status')
def pool_status(id_pool):
    '''hypervisors ready to start and create disks'''
    pass

@api.route('/grafana/reload')
def grafana_reload():
    '''changes in grafana parameters'''
    pass

@api.route('/engine/events/stop')
def stop_thread_event():
    app.m.t_events.stop = True
    app.t_events.q_event_register.put({'type': 'del_hyp_to_receive_events', 'hyp_id': ''})


@api.route('/engine_info', methods=['GET'])
def engine_info():
    d_engine = {}
    # if len(app.db.get_hyp_hostnames_online()) > 0:
    try:
        if app.m.t_background != None:
            try:
                app.m.t_background.is_alive()
            except AttributeError:
                d_engine['background_is_alive'] = False
                return jsonify(d_engine), 200

            if app.m.t_background.is_alive():
                manager = app.m
                d_engine['background_is_alive'] = True
                d_engine['event_thread_is_alive'] = app.m.t_events.is_alive() if app.m.t_events != None else False
                d_engine['broom_thread_is_alive'] = app.m.t_broom.is_alive() if app.m.t_broom != None else False
                d_engine['download_changes_thread_is_alive'] = app.m.t_downloads_changes.is_alive() \
                                                                    if app.m.t_downloads_changes != None else False

                d_engine['changes_hyps_thread_is_alive'] = app.m.t_changes_hyps.is_alive() \
                                                                    if app.m.t_changes_hyps != None else False
                d_engine[
                    'changes_domains_thread_is_alive'] = app.m.t_changes_domains.is_alive() if app.m.t_changes_domains != None else False
                d_engine['working_threads'] = list(app.m.t_workers.keys())
                d_engine['status_threads'] = list(app.m.t_status.keys())
                d_engine['disk_operations_threads'] = list(app.m.t_disk_operations.keys())
                d_engine['long_operations_threads'] = list(app.m.t_long_operations.keys())

                d_engine['alive_threads'] = dict()
                d_engine['alive_threads']['working_threads'] = {name:t.is_alive() for name,t in app.m.t_workers.items()}
                d_engine['alive_threads']['status_threads'] = {name:t.is_alive() for name,t in app.m.t_status.items()}
                d_engine['alive_threads']['disk_operations_threads'] = {name:t.is_alive() for name,t in app.m.t_disk_operations.items()}
                d_engine['alive_threads']['long_operations_threads'] = {name:t.is_alive() for name,t in app.m.t_long_operations.items()}

                d_engine['queue_size_working_threads'] = {k: q.qsize() for k, q in app.m.q.workers.items()}
                d_engine['queue_disk_operations_threads'] = {k: q.qsize() for k, q in app.m.q_disk_operations.items()}
            else:
                d_engine['is_alive'] = False
        else:
            d_engine['is_alive'] = False
        return jsonify(d_engine), 200
    except AttributeError:
        d_engine['is_alive'] = False
        print('ERROR ----- ENGINE IS DEATH')
        return jsonify(d_engine), 200
    except Exception as e:
        d_engine['is_alive'] = False
        print('ERROR ----- ENGINE IS DEATH AND EXCEPTION DETECTED')
        return jsonify(d_engine), 200


@api.route('/domains/user/<string:username>', methods=['GET'])
def get_domains(username):
    domains = app.db.get_domains_from_user(username)
    json_domains = json.dumps(domains, sort_keys=True, indent=4)

    return jsonify(domains=json_domains)
