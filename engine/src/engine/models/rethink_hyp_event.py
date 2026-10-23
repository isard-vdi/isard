from pprint import pformat

from rethinkdb import r

from engine.services.db.db import rethink_conn
from engine.services.log import log, logs


class RethinkHypEvent(object):
    def __init__(self):
        pass

    def update_viewer_client(self, domain_id, phase, ip_client=False, when=False):
        dict_viewer = {}
        with rethink_conn() as r_conn:
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

        return results
