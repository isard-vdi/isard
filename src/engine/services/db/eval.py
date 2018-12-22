import rethinkdb as r

from engine.services.db import new_rethink_connection, close_rethink_connection


def insert_eval_result(obj):
    r_conn = new_rethink_connection()
    rtable = r.table('eval_results')
    rtable.insert(obj).run(r_conn, durability="soft", noreply=True)
    close_rethink_connection(r_conn)

def insert_eval_initial_ux(obj):
    r_conn = new_rethink_connection()
    rtable = r.table('eval_initial_ux')
    x = rtable.get(obj.get('id')).run(r_conn)
    if x:
        rtable.get(obj.get('id')).update(obj).run(r_conn)
    else:
        rtable.insert(obj).run(r_conn, durability="soft", noreply=True)
    close_rethink_connection(r_conn)

def get_eval_initial_ux(id):
    r_conn = new_rethink_connection()
    rtable = r.table('eval_initial_ux')
    initial_ux = rtable.get(id).run(r_conn)
    close_rethink_connection(r_conn)
    return initial_ux
