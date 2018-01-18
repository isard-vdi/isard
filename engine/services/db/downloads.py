import rethinkdb as r

from engine.services.db import new_rethink_connection, close_rethink_connection


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

def update_download_percent(done):
    r_conn = new_rethink_connection()
    r.table(self.table).get(self.id).update({'percentage': done}).run(r_conn)
    close_rethink_connection(r_conn)

