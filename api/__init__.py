from flask import jsonify
import os
from flask import Flask
import json


if os.path.isfile('config.py'):
    path_config = 'config.py'
elif os.path.isfile('default_config.py'):
    path_config = 'default_config.py'


try:
    from api.config import configure_app

except:
    from api.default_config import configure_app


app = Flask(__name__)

@app.route('/threads/', methods=['GET'])
def get_threads():
    d=[{'prova1':'provando1', 'prova2':'provando2'}]

    return jsonify(d), 200


@app.route('/domains/user/<string:username>', methods=['GET'])
def get_domains(username):
    domains = app.db.get_domains_from_user(username)
    return json.dumps(domains,sort_keys=True, indent=4), 200