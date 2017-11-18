import rethinkdb as r

from engine.services.db import new_rethink_connection, close_rethink_connection


def get_last_hyp_status(id):
    r_conn = new_rethink_connection()
    rtable = r.table('hypervisors_status')

    l = list(rtable. \
             filter({'hyp_id': id}). \
             order_by(r.desc('when')). \
             limit(1). \
             run(r_conn))
    close_rethink_connection(r_conn)
    if len(l) == 0:
        return None
    else:
        return l[0]


def insert_db_hyp_status(dict_hyp_status):
    r_conn = new_rethink_connection()
    rtable = r.table('hypervisors_status')

    rtable.insert(dict_hyp_status). \
        run(r_conn, durability="soft", noreply=True)
    close_rethink_connection(r_conn)