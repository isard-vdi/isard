from engine.services.db import close_rethink_connection, new_rethink_connection
from engine.services.log import *
from rethinkdb import r


def get_last_hyp_status(id):
    r_conn = new_rethink_connection()
    rtable = r.table("hypervisors_status")

    l = list(
        rtable.filter({"hyp_id": id}).order_by(r.desc("when")).limit(1).run(r_conn)
    )
    close_rethink_connection(r_conn)
    if len(l) == 0:
        return None
    else:
        return l[0]


def update_actual_stats_hyp(id_hyp, hyp_stats, means={}):
    d = {"id": id_hyp, "now": hyp_stats, "means": means}

    r_conn = new_rethink_connection()
    rtable = r.table("hypervisors_status")

    rtable.insert(d, conflict="update").run(r_conn, durability="soft", noreply=True)
    close_rethink_connection(r_conn)


def update_actual_stats_domain(id_domain, domain_stats, means):
    d = {"id": id_domain, "now": domain_stats, "means": means}

    r_conn = new_rethink_connection()
    rtable = r.table("domains_status")

    try:
        rtable.insert(d, conflict="update").run(r_conn, durability="soft", noreply=True)
    except Exception as e:
        logs.exception_id.debug("0045")
        log.debug("Error inserting domain_stats: {}".format(id_domain))
        log.debug(e)
    close_rethink_connection(r_conn)


def insert_db_hyp_status(dict_hyp_status):
    r_conn = new_rethink_connection()
    rtable = r.table("hypervisors_status")

    rtable.insert(dict_hyp_status).run(r_conn, durability="soft", noreply=True)
    close_rethink_connection(r_conn)
