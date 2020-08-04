import inspect
import time
from flask import jsonify, request

from engine.controllers.eval_controller import EvalController
from engine.services.csv.eval import eval_to_csv
from engine.services.db.eval import insert_eval_result
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

@api.route('/start_domains', methods=['GET'])
def start_domains():
    eval_ctrl = EvalController()
    data = eval_ctrl.start_domains()
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

@api.route('/eval/statistics', methods=['GET'])
def eval_statistics():
    eval_ctrl = EvalController()
    data = eval_ctrl._evaluate()
    return jsonify(eval=data), 200

@api.route('/eval', methods=['POST'])
def new_eval():
    """
    templates = [{'id': "_admin_ubuntu_17_eval_wget", 'weight': 100}]
    evaluators = ["load"]
    :return:
    """
    kwargs = request.json
    code = kwargs.get("code")
    eval_ctrl_class = EvalController
    args = inspect.getfullargspec(eval_ctrl_class.__init__).args
    params = {k: v for k, v in kwargs.items() if k in args}
    eval_ctrl = eval_ctrl_class(**params)
    iterations = kwargs.get("iterations", 1)
    objs=[]
    for i in range(iterations):
        data = eval_ctrl.run()
        now = time.time()
        obj = {
            "id": "{}_{}".format(code, now),
            "code": code,
            "params": params,
            "result": data,
            "when": now
        }
        insert_eval_result(obj)
        eval_to_csv(code, data)
        d_load = data["load"]["total_started_domains"] if data.get("load") else None
        d_ux = data["ux"]["total"]["score"] if data.get("ux") else None
        objs.append((d_load, d_ux))
        time.sleep(40)
    return jsonify(objs), 200
