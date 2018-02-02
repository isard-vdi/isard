import rethinkdb as r

from engine.config import RETHINK_HOST, RETHINK_PORT, RETHINK_DB
from engine.services.db import new_rethink_connection, close_rethink_connection


def get_config():
    r_conn = new_rethink_connection()
    rtable = r.table('config')
    config = rtable.get(1).run(r_conn)
    return config


def get_config_branch(key):
    r_conn = new_rethink_connection()
    rtable = r.table('config')
    try:
        d_config = rtable.get(1)[key].run(r_conn)
    except r.ReqlNonExistenceError:
        d_config = False

    close_rethink_connection(r_conn)
    return d_config


def table_config_created_and_populated():
    try:
        r_conn_test = r.connect(RETHINK_HOST, RETHINK_PORT)
        if not r.db_list().contains(RETHINK_DB).run(r_conn_test):
            return False
        else:
            r_conn = new_rethink_connection()

            out = False
            if r.table_list().contains('config').run(r_conn):
                rtable = r.table('config')
                out = rtable.get(1).run(r_conn)

            close_rethink_connection(r_conn)
            if out is not False:
                if out is not None:
                    return True
                else:
                    return False
            else:
                return False
    except Exception as e:
        log.info('rethink db connectin failed')
        log.info(e)
        return False