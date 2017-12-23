import rethinkdb as r

from engine.services.db import new_rethink_connection, close_rethink_connection


def insert_eval_result(obj):
    r_conn = new_rethink_connection()
    rtable = r.table('eval_results')
    rtable.insert(obj).run(r_conn, durability="soft", noreply=True)
    close_rethink_connection(r_conn)
