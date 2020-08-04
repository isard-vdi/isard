import rethinkdb as r

from engine.services.db import new_rethink_connection, close_rethink_connection


def insert_disk_operation(dict_disk_operation):
    r_conn = new_rethink_connection()
    rtable = r.table('disk_operations')

    result = rtable.insert(dict_disk_operation). \
        run(r_conn)
    close_rethink_connection(r_conn)

    id = result['generated_keys']

    return id


def update_disk_operation(id, dict_fields_update):
    r_conn = new_rethink_connection()
    rtable = r.table('disk_operations')

    results = rtable.get(id).update(dict_fields_update).run(r_conn)
    close_rethink_connection(r_conn)
    return results