import json

from flask import Blueprint, jsonify

from engine import app


api = Blueprint('api', __name__)

from . import evaluate

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


@api.route('/engine_info', methods=['GET'])
def engine_info():
    d_engine = {}
    # if len(app.db.get_hyp_hostnames_online()) > 0:
    try:
        if app.m.t_background is not None:
            try:
                app.m.t_background.is_alive()
            except AttributeError:
                d_engine['is_alive'] = False
                return jsonify(d_engine), 200

            if app.m.t_background.is_alive():
                d_engine['is_alive'] = True
                d_engine['event_thread_is_alive'] = app.m.t_events.is_alive() if app.m.t_events is not None else False
                d_engine['broom_thread_is_alive'] = app.m.t_broom.is_alive() if app.m.t_broom is not None else False
                d_engine[
                    'changes_hyps_thread_is_alive'] = app.m.t_changes_hyps.is_alive() if app.m.t_changes_hyps is not None else False
                d_engine[
                    'changes_domains_thread_is_alive'] = app.m.t_changes_domains.is_alive() if app.m.t_changes_domains is not None else False
                d_engine['working_threads'] = list(app.m.t_workers.keys())
                d_engine['status_threads'] = list(app.m.t_status.keys())
                d_engine['disk_operations_threads'] = list(app.m.t_disk_operations.keys())
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
