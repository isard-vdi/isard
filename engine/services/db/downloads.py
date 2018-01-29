import rethinkdb as r

from engine.services.db import new_rethink_connection, close_rethink_connection

def get_media(id_media):

    r_conn = new_rethink_connection()
    d = r.table('media').get(id_media).run(r_conn)

    close_rethink_connection(r_conn)
    return d


def get_downloads_in_progress():
    r_conn = new_rethink_connection()
    try:
        d = r.table('media').get_all(r.args(['DownloadStarting', 'Downloading']), index='status'). \
            pluck('id',
                  'path',
                  'isard-web',
                  'status').run(r_conn)
    except r.ReqlNonExistenceError:
        d = []

    close_rethink_connection(r_conn)
    return d

def update_status_table(table,status,id_media,detail=""):
    r_conn = new_rethink_connection()
    d={'status':status,
       'detail':detail}
    r.table(table).get(id_media).update(d).run(r_conn)
    close_rethink_connection(r_conn)

def update_download_percent(done,table,id):
    r_conn = new_rethink_connection()
    r.table(table).get(id).update({'progress': done}).run(r_conn)
    close_rethink_connection(r_conn)

