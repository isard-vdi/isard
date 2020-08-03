import pprint
import queue
import threading
import traceback

from engine.services.db import update_domain_status
from engine.services.lib.functions import get_tid
from engine.services.log import log
from engine.services.threads.threads import TIMEOUT_QUEUES, launch_action_disk, launch_delete_disk_action, \
    launch_action_create_template_disk


class DiskOperationsThread(threading.Thread):
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
        self.disk_operations_thread()

    def disk_operations_thread(self):
        host = self.hostname
        self.tid = get_tid()
        log.debug('Thread to launchdisks operations in host {} with TID: {}...'.format(host, self.tid))

        while self.stop is not True:
            try:
                action = self.queue_actions.get(timeout=TIMEOUT_QUEUES)
                # for ssh commands
                if action['type'] in ['create_disk']:
                    launch_action_disk(action,
                                       self.hostname,
                                       self.user,
                                       self.port)
                elif action['type'] in ['create_disk_from_scratch']:
                    launch_action_disk(action,
                                       self.hostname,
                                       self.user,
                                       self.port,
                                       from_scratch=True)
                elif action['type'] in ['delete_disk']:
                    launch_delete_disk_action(action,
                                              self.hostname,
                                              self.user,
                                              self.port)

                elif action['type'] in ['create_template_disk_from_domain']:
                    launch_action_create_template_disk(action,
                                                       self.hostname,
                                                       self.user,
                                                       self.port)

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
