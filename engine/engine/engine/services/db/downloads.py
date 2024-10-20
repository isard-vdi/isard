from engine.services.db import close_rethink_connection, new_rethink_connection
from engine.services.log import *
from rethinkdb import r


def get_media(id_media):
    r_conn = new_rethink_connection()
    d = r.table("media").get(id_media).run(r_conn)

    close_rethink_connection(r_conn)
    return d


def update_status_table(table, status, id_table, detail=""):
    r_conn = new_rethink_connection()
    detail = str(detail)
    d = {"status": status, "detail": str(detail)}
    try:
        r.table(table).get(id_table).update(d).run(r_conn)
    except Exception as e:
        logs.exception_id.debug("0042")
        logs.main.error(
            f"Error when updated status in table: {table}, status: {status}, id: {id_table}, detail: {detail}"
        )
    close_rethink_connection(r_conn)


def update_status_media_from_path(path, status, detail=""):
    r_conn = new_rethink_connection()
    r.table("media").filter({"path_downloaded": path}).update(
        {"status": status, "detail": detail}
    ).run(r_conn)
    close_rethink_connection(r_conn)


def update_download_percent(done, table, id):
    r_conn = new_rethink_connection()
    r.table(table).get(id).update({"progress": done}).run(r_conn)
    close_rethink_connection(r_conn)
