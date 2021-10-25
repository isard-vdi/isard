import json
import os
import pickle
import socket
import time
from pathlib import Path

import rethinkdb as r

RETHINKDB_HOST = "isard-db"
RETHINKDB_PORT = 28015
RETHINKDB_DB = "isard"

STATS_DIR_JSONS = "/opt/json_stats"


def timeit(method):
    def test_time_exec(*args, **kwargs):
        start_time = time.time()
        out = method(*args, **kwargs)
        time_elapsed = time.time() - start_time
        method_name = method.__name__
        print(
            f"--- execution time of method {method_name}: {time_elapsed:.3f} seconds ---"
        )
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


def save_dict_to_file(dict_name, d, with_pickle=True):
    base_dir = os.environ.get("DIR_JSONS", STATS_DIR_JSONS)
    path = Path(base_dir)
    path.mkdir(parents=True, exist_ok=True)
    if with_pickle is True:
        path_pickle = path.joinpath(dict_name + ".pickle")
        with open(path_pickle, "wb") as f:
            pickle.dump(d, f)
    else:
        path_json = path.joinpath(dict_name + ".json")
        with open(path_json, "w") as file:
            json.dump(d, file)


def load_dict_from_file(dict_name, with_pickle=True):
    base_dir = os.environ.get("DIR_JSONS", STATS_DIR_JSONS)
    path = Path(base_dir)
    if with_pickle is True:
        path_pickle = path.joinpath(dict_name + ".pickle")
        with open(path_pickle, "rb") as f:
            new_d = pickle.load(f)
    else:
        path_json = path.joinpath(dict_name + ".json")
        with open(path_json, "r") as file:
            new_d = json.load(file)
    return new_d
