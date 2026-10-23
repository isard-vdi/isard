import traceback

from rethinkdb import r

from engine.config import RETHINK_DB, RETHINK_HOST, RETHINK_PORT
from engine.services.db.db import rethink_conn
from engine.services.log import logs


def get_config_branch(key):
    rtable = r.table("config")
    try:
        with rethink_conn() as r_conn:
            d_config = rtable.get(1)[key].run(r_conn)
    except r.ReqlNonExistenceError:
        d_config = False

    return d_config


def table_config_created_and_populated():
    try:
        r_conn_test = r.connect(RETHINK_HOST, RETHINK_PORT)
        try:
            db_created = r.db_list().contains(RETHINK_DB).run(r_conn_test)
        finally:
            r_conn_test.close()
        if not db_created:
            print(
                f"rethink host {RETHINK_HOST} and port {RETHINK_PORT} has connected but rethink database {RETHINK_DB} is not created"
            )
            return False
        else:
            with rethink_conn() as r_conn:
                out = False
                if r.table_list().contains("config").run(r_conn):
                    rtable = r.table("config")
                    out = rtable.get(1).run(r_conn)

            if out is not False:
                if out != None:
                    # print('table config populated in database')
                    return True
                else:
                    print("table config not populated in database")
                    return False
            else:
                return False
    except Exception as e:
        logs.exception_id.debug("0039")
        print(
            f"rethink db connecting failed with hostname {RETHINK_HOST} and port {RETHINK_PORT}"
        )
        print(e)
        print("Traceback: \n .{}".format(traceback.format_exc()))
        return False


def get_shared_storage_stall():
    try:
        with rethink_conn() as r_conn:
            return (
                r.table("config")
                .get(1)
                .pluck("shared_storage_stall")
                .run(r_conn)
                .get("shared_storage_stall")
            )
    except r.ReqlNonExistenceError:
        return None


def set_shared_storage_stall(state):
    with rethink_conn() as r_conn:
        r.table("config").get(1).update({"shared_storage_stall": r.literal(state)}).run(
            r_conn
        )
