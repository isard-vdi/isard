# Copyright 2017 the Isard-vdi project authors:
#      Alberto Larraz Dalmases
#      Josep Maria Viñolas Auquer
# License: AGPLv3
# coding=utf-8

import threading
import pprint
import os
import requests
import subprocess
import rethinkdb as r

from engine.config import CONFIG_DICT
from engine.services.db.db import new_rethink_connection
from engine.services.db.domains import update_domain_status
from engine.services.log import logs
from engine.services.db import get_config_branch, get_hyp_hostname_user_port_from_id
from engine.services.db.downloads import get_downloads_in_progress, update_download_percent, update_status_table
from engine.services.lib.qcow import get_host_disk_operations_from_path, get_path_to_disk


class DownloadThread(threading.Thread, object):
    def __init__(self, hyp_hostname, url, path, table, id_down, dict_header):
        threading.Thread.__init__(self)
        self.name = '_'.join([table, id_down])
        self.table = table
        self.path = path
        self.id = id_down
        self.url = url
        self.dict_header = dict_header
        self.stop = False
        d = get_hyp_hostname_user_port_from_id('isard-hypervisor')
        self.hostname = d['hostname']
        self.user = d['user']
        self.port = d['port']

    def run(self):

        # if self.table == 'domains':
        #     type_path_selected = 'groups'
        # elif self.table in ['isos']:
        #     type_path_selected = 'isos'
        # else:
        #     type_path_selected = 'media'
        #
        # new_file, path_selected = get_path_to_disk(self.path, pool=self.pool, type_path=type_path_selected)
        # logs.downloads.debug("PATHS ___________________________________________________________________")
        # logs.downloads.debug(new_file)
        # logs.downloads.debug(path_selected)
        # logs.downloads.debug(pprint.pformat(self.__dict__))
        #
        # hyp_to_disk_create = get_host_disk_operations_from_path(path_selected, pool=self.pool,
        #                                                                 type_path=type_path_selected)
        header_template = "--header '{header_key}: {header_value}' "
        headers = ''

        for k,v in self.dict_header.items():
            headers += header_template.format(header_key=k, header_value=v)

        ssh_template = """ssh -oBatchMode=yes -p {port} {user}@{hostname} """ \
                       """ "curl -o '{path}' {headers} '{url}' " """


        ssh_command = ssh_template.format(port=self.port,
                                          user=self.user,
                                          hostname=self.hostname,
                                          path= self.path,
                                          headers=headers,
                                          url= self.url)

        logs.downloads.debug("SSH COMMAND: {}".format(ssh_command))

        p = subprocess.Popen(ssh_command, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        rc = p.poll()
        l = []
        update_status_table(self.table,'Downloading',self.id,"downloading in hypervisor: {}".format(self.hostname))
        while rc != 0:
            header = p.stderr.readline().decode('utf8')
            header2 = p.stderr.readline().decode('utf8')
            keys = ['% Total',
                    'Total',
                    '% Received',
                    'Received',
                    '% Xferd',
                    'Xferd',
                    'Average Dload',
                    'Speed Upload',
                    'Time Total',
                    'Time Spent',
                    'Time Left',
                    'Current Speed']

            line = ""

            while True:

                c = p.stderr.read(1).decode('utf8')
                if self.stop is True:
                    update_domain_status(self.table, 'FailedDownload', id, detail="download aborted")
                    break
                if not c:
                    break
                if c == '\r':
                    if len(line) > 60:
                        logs.downloads.debug(line)
                        values = line.split()
                        print(self.url)
                        print(line)
                        d_progress = dict(zip(keys,values))
                        update_download_percent(d_progress, self.table, self.id)
                        line = p.stderr.read(60).decode('utf8')

                else:
                    line = line + c

            rc = p.poll()

        logs.downloads.info('File downloaded: {}'.format(self.path))
        assert rc == 0
        if self.table == 'domains':
            update_domain_status('Downloaded', self.id, detail="downloaded disk")
            update_domain_status('Updating', self.id, detail="downloaded disk")
        else:
            update_status_table(self.table, 'Downloaded', self.id)



class DownloadChangesThread(threading.Thread):
    def __init__(self, name='download_changes'):
        threading.Thread.__init__(self)
        self.name = name
        self.stop = False

        cfg = get_config_branch('resources')
        if cfg is not False:
            self.url_resources = cfg['url']
            if 'code' in cfg:
                self.url_code = cfg['code']
            else:
                self.url_code = ''
        else:
            logs.downloads.error('resources dict not in config, stopping thread download changes')
            self.stop = True

        self.download_threads = {}
        self.finalished_threads = []


    def get_file_path(self,dict_changes):
        table = dict_changes['table']
        if table == 'domains':
            type_path_selected = 'groups'
            pool_id = dict_changes['create_dict']['hypervisors_pools'][0]
            relative_path = dict_changes['create_dict']['hardware']['disks'][0]['file']

        else:
            if 'hypervisors_pools' in dict_changes.keys():
                if type(dict_changes['hypervisors_pools']) is list:
                    pool_id = dict_changes['hypervisors_pools'][0]
                else:
                    pool_id = 'default'
            else:
                pool_id = 'default'

            type_path_selected = 'media'
            relative_path = dict_changes['path']

        new_file_path, path_selected = get_path_to_disk(relative_path,
                                                        pool=pool_id,
                                                        type_path=type_path_selected)
        return new_file_path, path_selected, type_path_selected, pool_id

    def abort_download(self,dict_changes):
        new_file_path, path_selected = self.get_file_path(dict_changes)
        if new_file_path not in self.download_threads:
            self.download_threads[new_file_path].stop = True
        else:
            update_status_table(dict_changes['table'],FailedDownload)

    def start_download(self, dict_changes):

        new_file_path, path_selected, type_path_selected, pool_id = self.get_file_path(dict_changes)

        table = dict_changes['table']
        id_down = dict_changes['id']
        subdir_url = 'storage'

        # all disk downloads create a desktop


        url_base = self.url_resources
        header_dict = {}

        if len(subdir_url) > 0:
            url_base = url_base + '/' + subdir_url


        # hypervisor to launch download command
        hyp_to_disk_create = get_host_disk_operations_from_path(path_selected,
                                                                pool=pool_id,
                                                                type_path=type_path_selected)

        if 'url-web' in dict_changes.keys():
            url = dict_changes['url-web']

        elif 'url-isard' in dict_changes.keys():
            url_isard = dict_changes['url-isard']
            url = url_base + '/' + table + '/' + url_isard
            if len(self.url_code) > 0:
                header_dict['Authorization'] = self.url_code
        else:
            logs.downloads.error(('web-url or isard-url must be keys in dictionary for domain {}'+
                                 ' to download disk file from internet. ').format(id_down))
            exit()

        if new_file_path in self.finalished_threads:
            if new_file_path in self.download_threads.keys():
                c.pop(new_file_path)
            self.finalished_threads.remove(new_file_path)

        # launching download threads
        if new_file_path not in self.download_threads:
            self.download_threads[new_file_path] = DownloadThread(hyp_to_disk_create,
                                                                  url,
                                                                  new_file_path,
                                                                  table,
                                                                  id_down,
                                                                  header_dict)
            self.download_threads[new_file_path].daemon = True
            self.download_threads[new_file_path].start()

        else:
            logs.downloads.error('download thread launched to this path: {}'.format(new_file_path))


    def run(self):
        logs.downloads.debug('RUN-DOWNLOAD-THREAD-------------------------------------')
        if self.stop is False:
            r_conn = new_rethink_connection()
            for c in r.table('media').get_all(r.args(['DownloadStarting', 'Downloading','AbortingDownload']), index='status').\
                    pluck('id',
                          'path',
                          'url-isard',
                          'url-web',
                          'status').merge(
                {'table': 'media'}).changes(include_initial=True).union(
                r.table('domains').get_all(r.args(['DownloadStarting', 'Downloading','AbortingDownload']), index='status').\
                        pluck('id',
                              'create_dict',
                              'url-isard',
                              'url-web',
                              'status').merge(
                    {"table": "domains"}).changes(include_initial=True)).run(r_conn):

                logs.downloads.debug('INITIAL STATUS')
                logs.downloads.debug(pprint.pformat(c))
                if self.stop:
                    break


                if 'old_val' not in c:
                    self.start_download(c['new_val'])
                elif 'new_val' not in c:
                    self.abort_download(c['old_val'])
                elif 'old_val' in c and 'new_val' in c:
                    if c['old_val'] == 'FailedDownload' and c['new_val'] == 'DownloadStarting':
                        self.start_download(c['new_val'])

                    if c['old_val'] == 'Downloading' and c['new_val'] == 'FailedDownload':
                        pass

                    if c['old_val'] == 'Downloading' and c['new_val'] == 'AbortingDownload':
                        self.abort_download(c['new_val'])

                    # # Initial status

                    #
                    # path = c['new_val']['table'] + '/' + c['new_val']['path'] if c['new_val'][
                    #                                                                  'table'] == 'media' else \
                    #     c['new_val']['create_dict']['hardware']['disks'][0]['file']
                    #
                    # if c['new_val']['table'] == 'media':
                    #     path = '/isard/media/' + path
                    # if c['new_val']['table'] == 'domains':
                    #     path = '/isard/groups/' + path
                    # self.downloadThreads[c['new_val']['id']] = DownloadThread(c['new_val']['table'], path,
                    #                                                           c['new_val']['id'], self.url,
                    #                                                           self.code)
                    # self.downloadThreads[c['new_val']['id']].daemon = True
                    # self.downloadThreads[c['new_val']['id']].start()
                    #
                    # logs.downloads.debug('DOWNLOAD THREADS: ')
                    # logs.downloads.debug(pprint.pformat(self.downloadThreads))

                    # continue

                # except Exception as e:
                #     # ~ exc_type, exc_obj, exc_tb = sys.exc_info()
                #     # ~ fname = os.path.split(exc_tb.tb_frame.f_code.co_filename)[1]
                #     # ~ log.error(exc_type, fname, exc_tb.tb_lineno)
                #     logs.downloads.error('DomainsStatusThread error:' + str(e))


def launch_thread_download_changes():
    t = DownloadChangesThread()
    t.daemon = True
    t.start()
    return t
