import rethinkdb as r

from engine.services.db import new_rethink_connection, close_rethink_connection
from engine.services.log import *

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

def update_status_table(table,status,id_table,detail=""):
    r_conn = new_rethink_connection()
    d={'status':status,
       'detail':detail}
    try:
        r.table(table).get(id_table).update(d).run(r_conn)
    except:
        logs.main.error(f'Error when updated status in table: {table}, status: {status}, id: {id_table}, detail: {detail}')
    close_rethink_connection(r_conn)

def update_status_media_from_path(path,status,detail=''):
    r_conn = new_rethink_connection()
    table = 'media'
    d_status ={'status':status,
               'detail':detail}
    result = []
    l = list(r.table(table).filter({'path_downloaded': path}).run(r_conn))
    if len(l) > 0:
        for d in l:
            result.append(r.table(table).get(d['id']).update(d_status).run(r_conn))
    else:
        result = False
    close_rethink_connection(r_conn)
    return result

def update_download_percent(done,table,id):
    r_conn = new_rethink_connection()
    r.table(table).get(id).update({'progress': done}).run(r_conn)
    close_rethink_connection(r_conn)

