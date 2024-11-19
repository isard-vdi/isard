from engine.services.db import rethink_conn
from engine.services.log import *
from rethinkdb import r


def get_media(id_media):
    with rethink_conn() as conn:
        return r.table("media").get(id_media).run(conn)


def update_status_table(table, status, id_table, detail=""):
    detail = str(detail)
    d = {"status": status, "detail": str(detail)}
    try:
        with rethink_conn() as conn:
            r.table(table).get(id_table).update(d).run(conn)
    except Exception as e:
        logs.exception_id.debug("0042")
        logs.main.error(
            f"Error when updated status in table: {table}, status: {status}, id: {id_table}, detail: {detail}"
        )


def update_status_media_from_path(path, status, detail=""):
    with rethink_conn() as conn:
        r.table("media").filter({"path_downloaded": path}).update(
            {"status": status, "detail": detail}
        ).run(conn)


def update_download_percent(done, table, id):
    with rethink_conn() as conn:
        r.table(table).get(id).update({"progress": done}).run(conn)
