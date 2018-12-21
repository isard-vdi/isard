import pprint
import queue
import threading
import traceback

from engine.services.db import update_domain_status, update_table_field
from engine.services.lib.functions import get_tid, execute_commands
from engine.services.log import log
from engine.services.threads.threads import TIMEOUT_QUEUES


class LongOperationsThread(threading.Thread):
    def __init__(self, name, hyp_id, hostname, queue_actions, user='root', port=22, queue_master=None):
        threading.Thread.__init__(self)
        self.name = name
        self.hyp_id = hyp_id
        self.hostname = hostname
        self.user = user
        self.port = port
        self.stop = False
        self.queue_actions = queue_actions
        self.queue_master = queue_master

    def run(self):
        self.tid = get_tid()
        log.info('starting thread: {} (TID {})'.format(self.name, self.tid))
        self.long_operations_thread()

    def long_operations_thread(self):
        host = self.hostname
        self.tid = get_tid()
        log.debug('Thread to launchdisks operations in host {} with TID: {}...'.format(host, self.tid))

        while self.stop is not True:
            try:
                action = self.queue_actions.get(timeout=TIMEOUT_QUEUES)
                # for ssh commands
                id_domain = action['domain']
                if action['type'] in ['create_disk_virt_builder']:

                    cmds_done = execute_commands(host=self.hostname,
                                                 ssh_commands=action['ssh_commands'],
                                                 dict_mode=True,
                                                 user=self.user,
                                                 port=self.port
                                                 )

                    if len([d for d in cmds_done if len(d['err']) > 0]) > 1:
                        log.error('some error in virt builder operations')
                        log.error('Virt Builder Failed creating disk file {} in domain {} in hypervisor {}'.format(
                            action['disk_path'], action['domain'], self.hyp_id))
                        log.debug('print cmds_done:')
                        log.debug(pprint.pprint(cmds_done))
                        log.debug('print ssh_commands:')
                        log.debug(pprint.pprint(action['ssh_commands']))
                        update_domain_status('Failed', id_domain,
                                             detail='Virt Builder Failed creating disk file')
                    else:
                        log.info('Disk created from virt-builder. Domain: {} , disk: {}'.format(action['domain'],
                                                                                                action['disk_path']))
                        xml_virt_install = cmds_done[-1]['out']
                        update_table_field('domains', id_domain, 'xml_virt_install', xml_virt_install)

                        update_domain_status('CreatingDomainFromBuilder', id_domain,
                                             detail='disk created from virt-builder')


                elif action['type'] == 'stop_thread':
                    self.stop = True
                else:
                    log.error('type action {} not supported'.format(action['type']))
            except queue.Empty:
                pass
            except Exception as e:
                log.error('Exception when creating disk: {}'.format(e))
                log.error('Action: {}'.format(pprint.pformat(action)))
                log.error('Traceback: {}'.format(traceback.format_exc()))
                return False

        if self.stop is True:
            while self.queue_actions.empty() is not True:
                action = self.queue_actions.get(timeout=TIMEOUT_QUEUES)
                if action['type'] == 'create_disk':
                    disk_path = action['disk_path']
                    id_domain = action['domain']
                    log.error(
                        'operations creating disk {} for new domain {} failed. Commands, outs and errors: {}'.format(
                            disk_path, id_domain))
                    log.error('\n'.join(
                        ['cmd: {}'.format(action['ssh_commands'][i]) for i in range(len(action['ssh_commands']))]))
                    update_domain_status('Failed', id_domain,
                                         detail='new disk create operation failed, thread disk operations is stopping, detail of operations cancelled in logs')
