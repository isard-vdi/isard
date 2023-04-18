from pprint import pformat

from engine.services.db.db import close_rethink_connection, new_rethink_connection
from engine.services.log import log, logs
from rethinkdb import r


class RethinkHypEvent(object):
    def __init__(self):
        pass

    def update_viewer_client(self, domain_id, phase, ip_client=False, when=False):
        dict_viewer = {}
        r_conn = new_rethink_connection()

        # PHASE == 0 => CONNECTED
        if phase == 0:
            dict_viewer["client_addr"] = ip_client
            dict_viewer["client_since"] = when

        # PHASE == 1 => DISCONNECT
        if phase > 1:
            dict_viewer["client_addr"] = False
            dict_viewer["client_since"] = False

        rtable = r.table("domains")
        results = rtable.get(domain_id).update({"viewer": dict_viewer}).run(r_conn)

        close_rethink_connection(r_conn)
        return results
