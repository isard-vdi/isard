import time
import socket
import json
import pickle
import rethinkdb as r
import os
from pathlib import Path


STATS_RETHINKDB_HOST='isard-db'
STATS_RETHINKDB_PORT=28015
STATS_RETHINKDB_DB='isard'
RETHINKDB_HOST='isard-db'
RETHINKDB_PORT=28015
RETHINKDB_DB='isard'

STATS_DIR_JSONS = '/opt/json_stats'


def timeit(method):
    def test_time_exec(*args,**kwargs):
        start_time = time.time()
        out = method(*args,**kwargs)
        time_elapsed = time.time() - start_time
        method_name = method.__name__
        print(f"--- execution time of method {method_name}: {time_elapsed:.3f} seconds ---")
        return out
    return test_time_exec

def getHost(ip):
    """
    This method returns the 'True Host' name for a
    given IP address
    """
    try:
        data = socket.gethostbyaddr(ip)
        host = repr(data[0])
        return host
    except Exception:
        # fail gracefully
        return False

def get_domain_info_from_rethink_db():
    r_conn = r.connect(RETHINKDB_HOST, RETHINKDB_PORT, RETHINKDB_DB).repl()
    out = r.table('domains').get(id_domain).pluck('parents', 'user', {'viewer': 'base_port'}).run(r_conn)
    parent = out['parents'][-1]
    baseport = out['viewer']['base_port']
    id_user = out['user']
    out = r.table('users').get(id_user).pluck('role', 'group', 'category').run(r_conn)
    role = out['role']
    group = out['group']
    category = out['category']
    r_conn.close()
    return parent,baseport,role,category,group,id_user

def save_dict_to_file(dict_name,d,with_pickle=True):
    base_dir = os.environ.get('DIR_JSONS',STATS_DIR_JSONS)
    path = Path(base_dir)
    path.mkdir(parents=True,exist_ok=True)
    if with_pickle is True:
        path_pickle = path.joinpath(dict_name + '.pickle')
        with open(path_pickle, 'wb') as f:
            pickle.dump(d, f)
    else:
        path_json = path.joinpath(dict_name + '.json')
        with open(path_json, 'w') as file:
            json.dump(d, file)

def load_dict_from_file(dict_name,with_pickle=True):
    base_dir = os.environ.get('DIR_JSONS', STATS_DIR_JSONS)
    path = Path(base_dir)
    if with_pickle is True:
        path_pickle = path.joinpath(dict_name + '.pickle')
        with open(path_pickle,'rb') as f:
            new_d = pickle.load(f)
    else:
        path_json = path.joinpath(dict_name + '.json')
        with open(path_json, 'r') as file:
            new_d = json.load(file)
    return new_d