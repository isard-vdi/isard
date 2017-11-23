from flask import jsonify

from engine.controllers.eval_controller import EvalController
from . import api


@api.route('/create_domains', methods=['GET'])
def create_domains():
    eval_ctrl = EvalController()
    data = eval_ctrl.create_domains()
    return jsonify(eval=data), 200


@api.route('/destroy_domains', methods=['GET'])
def destroy_domains():
    eval_ctrl = EvalController()
    data = eval_ctrl.destroy_domains()
    return jsonify(eval=data), 200


@api.route('/stop_domains', methods=['GET'])
def stop_domains():
    eval_ctrl = EvalController()
    data = eval_ctrl.stop_domains()
    return jsonify(eval=data), 200


@api.route('/clear_domains', methods=['GET'])
def clear_domains():
    eval_ctrl = EvalController()
    data = eval_ctrl.clear_domains()
    return jsonify(eval={"clean":data}), 200


@api.route('/eval', methods=['GET'])
def eval():
    eval_ctrl = EvalController()
    data = eval_ctrl.run()
    return jsonify(eval=data), 200


@api.route('/remove-eval', methods=['GET'])
def remove_eval():
    eval_ctrl = EvalController()
    data = eval_ctrl._removeEvalDomains()
    return jsonify(eval=data), 200
