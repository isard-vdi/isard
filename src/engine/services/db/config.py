import rethinkdb as r
import traceback

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
            print(f'rethink host {RETHINK_HOST} and port {RETHINK_PORT} has connected but rethink database {RETHINK_DB} is not created')
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
                    #print('table config populated in database')
                    return True
                else:
                    print('table config not populated in database')
                    return False
            else:
                return False
    except Exception as e:
        print(f'rethink db connectin failed with hostname {RETHINK_HOST} and port {RETHINK_PORT}')
        print(e)
        print('Traceback: \n .{}'.format(traceback.format_exc()))
        return False
