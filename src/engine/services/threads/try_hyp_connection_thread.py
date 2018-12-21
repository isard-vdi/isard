import threading

from engine.services.lib.functions import get_tid
from engine.services.log import log
from engine.services.threads.threads import try_hyp_connection


class TryHypConnectionThread(threading.Thread):
    def __init__(self, name, hyp_id, hostname, port, user):
        threading.Thread.__init__(self)
        self.name = name
        self.hyp_id = hyp_id
        self.hostname = hostname
        self.port = port
        self.user = user

    def run(self):
        self.tid = get_tid()
        log.info('starting thread: {} (TID {})'.format(self.name, self.tid))

        self.hyp_obj, self.ok = try_hyp_connection(self.hyp_id, self.hostname, self.port, self.user)

        log.debug('Exiting from thread {} try_hyp {}'.format(self.name, self.hostname))

        return self.ok
