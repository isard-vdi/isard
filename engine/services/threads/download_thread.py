# Copyright 2017 the Isard-vdi project authors:
#      Alberto Larraz Dalmases
#      Josep Maria Viñolas Auquer
# License: AGPLv3
# coding=utf-8

import threading
import pprint
import os
import requests
import rethinkdb as r

from engine.services.db.db import new_rethink_connection
from engine.services.log import logs
from engine.services.db import get_config_branch


class DownloadThread(threading.Thread, object):
    def __init__(self, table, path, id_down, url, code):
        threading.Thread.__init__(self)
        self.name = '_'.join([table, id_down])
        self.table = table
        self.path = path
        self.id = id_down
        self.url = url
        self.code = code
        self.stop = False

    def run(self):
        r_conn = new_rethink_connection()
        try:
            os.makedirs(self.path.rsplit('/', 1)[0], exist_ok=True)
            with open(self.path, "wb") as f:
                response = requests.get(self.url + '/storage/' + self.table + '/' + self.path.split('/')[-1],
                                        headers={'Authorization': self.code}, stream=True)
                total_length = response.headers.get('content-length')
                r.table(self.table).get(self.id).update({'status':'Downloading'}).run(r_conn)
                if total_length is None:  # no content length header
                    f.write(response.content)
                else:
                    dl = 0
                    total_length = int(total_length)
                    # ~ print('Start: ' + self.path)
                    predl = 0
                    for data in response.iter_content(chunk_size=4096):
                        dl += len(data)
                        f.write(data)
                        done = int(dl * 100 / total_length)
                        if done > predl:
                            r.table(self.table).get(self.id).update({'percentage': done}).run(r_conn)
                        predl = done
                    logs.downloads.info('Finish: ' + self.path)
                    r.table(self.table).get(self.id).update({'status':'Stopped'}).run(r_conn)
                    # ~ time.sleep(2)
                    if self.table == 'domains':
                        r.table(self.table).get(self.id).update({'status':'Updating'}).run(r_conn)
        except Exception as e:
            r.table(self.table).get(self.id).update({'status':'Failed','detail':str(e)}).run(r_conn)
            logs.downloads.info('Download exception: ' + str(e))

        r_conn.close()


class DownloadChangesThread(threading.Thread):
    def __init__(self, name='download_changes'):
        threading.Thread.__init__(self)
        self.name = name
        self.stop = False
        self.downloadThreads = {}
        cfg = get_config_branch('resources')
        if cfg is not False:
            self.url = cfg['url']
            self.code = cfg['code']
        else:
            logs.downloads.error('resources dict not in config, stopping thread download changes')
            self.stop = True

    def run(self):
        if self.stop is False:
            r_conn = new_rethink_connection()
            for c in r.table('media').get_all(r.args(['DownloadStarting', 'Downloading']), index='status').\
                            pluck('id',
                                 'path',
                                 'isard-web',
                                 'status').merge(
                            {'table': 'media'}).changes(include_initial=True).union(
                    r.table('domains').get_all(r.args(['DownloadStarting', 'Downloading']), index='status').\
                            pluck('id',
                                  'create_dict',
                                  'isard-web',
                                  'status').merge(
                            {"table": "domains"}).changes(include_initial=True)).run(r_conn):

                if self.stop:
                    break

                try:
                    if 'old_val' not in c:
                        # Initial status
                        logs.downloads.debug('INITIAL STATUS')
                        logs.downloads.debug(pprint.pformat(c))

                        path = c['new_val']['table'] + '/' + c['new_val']['path'] if c['new_val']['table'] == 'media' else \
                                            c['new_val']['create_dict']['hardware']['disks'][0]['file']
                        
                        if c['new_val']['table'] == 'media':
                            path = '/isard/media/'+path
                        if c['new_val']['table'] == 'domains':
                            path = '/isard/groups/'+path
                        self.downloadThreads[c['new_val']['id']] = DownloadThread(c['new_val']['table'], path,
                                                                                  c['new_val']['id'], self.url, self.code)
                        self.downloadThreads[c['new_val']['id']].daemon = True
                        self.downloadThreads[c['new_val']['id']].start()

                        logs.downloads.debug('DOWNLOAD THREADS: ')
                        logs.downloads.debug(pprint.pformat(self.downloadThreads))

                        continue

                except Exception as e:
                    # ~ exc_type, exc_obj, exc_tb = sys.exc_info()
                    # ~ fname = os.path.split(exc_tb.tb_frame.f_code.co_filename)[1]
                    # ~ log.error(exc_type, fname, exc_tb.tb_lineno)
                    logs.downloads.error('DomainsStatusThread error:' + str(e))

def launch_thread_download_changes():
    t = DownloadChangesThread()
    t.daemon = True
    t.start()
    return t

