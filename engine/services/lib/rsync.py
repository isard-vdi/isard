import os
import subprocess
import threading

from engine.services.log import log


# NOT USED

class Rsync(object):
    def __init__(self, src, dst, verbose=True, show_progress=True, bwlimit=''):
        cmd = 'rsync -a'
        if verbose:
            cmd += 'v'
        if len(bwlimit) > 0:
            cmd += ' --bwlimit={}'.format(bwlimit)
        if show_progress:
            cmd += ' --progress'
        cmd += ' ' + src + ' '
        cmd += '' + dst + ''

        self.dst = dst
        self.src = src

        self.cmd = cmd
        log.debug('rsync command: ' + self.cmd)

        self.proc = False
        self.status = 0

    def start_process(self):
        self.proc = subprocess.Popen(self.cmd.split(), stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        self.pid = self.proc.pid

    def wait_communicate(self):
        self.stdout, self.stderr = self.proc.communicate()
        self.status = 1
        log.debug('rsync finished: ' + self.stdout)

    def get_process_stdout(self):
        self.stdout = ''
        while True:
            out = self.proc.stdout.readline(64).decode('utf-8')
            if out == '' and self.proc.poll() != None:
                break
            self.update_output(out)
            log.debug(out)
            log.debug(type(out))
            self.stdout += out
        self.stdout = self.stdout.replace('\r', '\n')
        self.status = 1
        log.debug('rsync finished: ' + self.stdout)

    def update_output(self, out):
        self.out_process = out
        # log.debug(out)
        tmp = out[:str(out).find('%')]
        percent = tmp[tmp.rfind(' ') + 1:]
        self.percent = percent
        log.debug('percent: ' + percent + '%     \r')

    def thread(self):
        d = threading.Thread(name='rsync_thread', target=self.get_process_stdout)

        d.setDaemon(True)
        d.start()

    def start_and_wait_silence(self):
        try:
            self.start_process()
            self.wait_communicate()
        except:
            log.debug('call to subprocess rsync failed: ' + self.cmd)

    def start_and_wait_verbose(self):
        try:
            self.start_process()
            self.get_process_stdo
        except:
            log.debug('call to subprocess rsync failed: ' + self.cmd)

    def start_and_continue(self):
        try:
            self.start_process()
            self.thread()
        except:
            log.debug('call to subprocess rsync failed')

    def remove_dst(self):
        if os.path.isdir(self.dst):
            if self.dst.endswith('/'):
                path = self.dst + self.src[self.src.rfind('/') + 1:]
            else:
                path = self.dst + self.src[self.src.rfind('/'):]
        else:
            path = self.dst

        if os.path.isfile(path):
            try:
                os.remove(path)
                log.debug('file removed: ' + path)
            except:
                log.debug('remove fail')
        else:
            log.debug('destination don\'t exist')
