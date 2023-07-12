import json
from pprint import pprint

from engine.services.db import (
    close_rethink_connection,
    get_all_domains_with_id_and_status,
    new_rethink_connection,
    update_domain_status,
)
from rethinkdb import r


def get_domain_name(id_domain):
    try:
        r_conn = new_rethink_connection()
        rtable = r.table("domains")
        results = (
            rtable.get(id_domain)
            .pluck("kind", "name", "description", "user", "status")
            .run(r_conn)
        )
        close_rethink_connection(r_conn)
        if results is None:
            return {}
        else:
            pprint(results)
            return results
    except Exception as e:
        print(Exception)
        return {}


def load_lists(path_json="test_starting_paused.json"):
    try:
        with open(path_json) as json_file:
            data = json.load(json_file)
            l_ok = data.get("l_ok")
            l_failed = data.get("l_failed")
            return l_ok, l_failed
    except FileNotFoundError:
        with open(path_json, "w") as json_file:
            json.dump({"l_ok": [], "l_failed": []}, json_file)
            return [], []


def save_lists(l_ok, l_failed, path_json="test_starting_paused.json"):
    try:
        with open(path_json, "w") as json_file:
            json.dump({"l_ok": l_ok, "l_failed": l_failed}, json_file)
            return [], []
    except Exception as e:
        print(e)


def wait_starting_paused(
    domain_id, total_domains=0, path_json="test_starting_paused.json"
):
    l_ok, l_failed = load_lists(path_json)
    print(
        "total: {}, ok: {}/ failed: {}".format(total_domains, len(l_ok), len(l_failed))
    )
    domain_info = get_domain_name(domain_id)

    if domain_info.get("status", False) == "Started":
        l_ok.append(domain_id)
        save_lists(l_ok, l_failed, path_json)
        return True

    if domain_info.get("status", False) == "Started":
        return False

    r_conn = new_rethink_connection()
    update_domain_status("StartingPaused", domain_id)
    cursor = (
        r.db("isard")
        .table("domains")
        .filter({"id": domain_id})
        .pluck("status")
        .changes()
        .run(r_conn)
    )
    for c in cursor:
        status_new = c.get("new_val", {}).get("status", None)
        # print(status_new)
        if status_new in ["Stopped", "Failed", "Started"]:
            print(f"{domain_id} {status_new}")
            if status_new == "Failed":
                l_failed.append(domain_id)
            if status_new in ["Stopped", "Started"]:
                l_ok.append(domain_id)
            save_lists(l_ok, l_failed, path_json)
            break
    close_rethink_connection(r_conn)
    return True


l_failed = []
l_ok = []
l = get_all_domains_with_id_and_status()

for a in l:
    domain_id = a["id"]
    if domain_id not in l_ok and domain_id not in l_failed:
        print(f"\n---------- {domain_id} -----------------")
        wait_starting_paused(domain_id, total_domains=len(l))
    else:
        print("desktop does not exist")
