from rethinkdb import r

from engine.services.db.db import rethink_conn
from engine.services.log import *


def get_last_hyp_status(id):
    rtable = r.table("hypervisors_status")

    with rethink_conn() as r_conn:
        l = list(
            rtable.filter({"hyp_id": id}).order_by(r.desc("when")).limit(1).run(r_conn)
        )
    if len(l) == 0:
        return None
    else:
        return l[0]


def update_actual_stats_hyp(id_hyp, hyp_stats, means={}):
    d = {"id": id_hyp, "now": hyp_stats, "means": means}

    rtable = r.table("hypervisors_status")

    with rethink_conn() as r_conn:
        rtable.insert(d, conflict="update").run(r_conn, durability="soft", noreply=True)


def update_actual_stats_domain(id_domain, domain_stats, means):
    d = {"id": id_domain, "now": domain_stats, "means": means}

    rtable = r.table("domains_status")

    try:
        with rethink_conn() as r_conn:
            rtable.insert(d, conflict="update").run(
                r_conn, durability="soft", noreply=True
            )
    except Exception as e:
        logs.exception_id.debug("0045")
        log.debug("Error inserting domain_stats: {}".format(id_domain))
        log.debug(e)


def insert_db_hyp_status(dict_hyp_status):
    rtable = r.table("hypervisors_status")

    with rethink_conn() as r_conn:
        rtable.insert(dict_hyp_status).run(r_conn, durability="soft", noreply=True)
